"""La prova della X si salva anche se l'XP non parte (2026-11-10).

Il difetto, trovato da una revisione il 2026-11-10:
`ChallengeService.complete_x_replacement_attempt` e
`create_x_replacement_attempt` non avevano `@transactional`. Il punteggio
dichiarato dal giocatore finiva su disco solo perché, subito dopo, l'handler
dell'XP chiamava `LevelService.award_xp`: fuori da ogni transazione quello è
«il più esterno» (ADR-061) e salvava l'intera sessione, prova compresa.

Il salvataggio di un dato di gara dipendeva quindi dalla buona riuscita di un
premio. Se `award_xp` solleva — o un giorno non viene più chiamato — la route
risponde «registrato» e alla fine della richiesta la sessione viene buttata
via con la prova dentro.

Qui si fa fallire l'XP e si butta via la sessione come fa la fine della
richiesta: la prova deve essere rimasta.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.services import ChallengeService
from models.competition.gara_bye_challenge import GaraByeChallenge
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.events.base import EventBus
from models.match.models import Match
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def preserve_handlers():
    """Gli handler sono globali: si preservano, non si azzerano."""
    original = {k: list(v) for k, v in EventBus._handlers.items()}
    yield
    EventBus._handlers = original


def _utente(db_session, prefisso, ruolo=UserRole.PLAYER.value):
    s = uuid.uuid4().hex[:8]
    u = User(
        username=f"{prefisso}_{s}",
        email=f"{prefisso}_{s}@test.com",
        role=ruolo,
        onboarding_completed=True,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def gara_con_x(db_session):
    direttore = _utente(db_session, "dir", UserRole.DIRECTOR.value)
    giocatori = [_utente(db_session, f"p{i}") for i in range(5)]
    esercizio = Challenge(
        description="Spot Shot Rally",
        image_path="test.jpg",
        pass_fail_only=False,
        created_by_id=direttore.id,
        is_active=True,
    )
    db_session.add(esercizio)
    db_session.commit()
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Gara X {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=7),
        location="Test",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=8,
        entry_fee=0.0,
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=direttore.id,
        matchmaking_strategy="amalfi",
        first_round_policy="random",
        odd_number_policy="bye_with_challenge",
        anti_rematch_enabled=True,
        x_challenge_id=esercizio.id,
    )
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(days=5)
    )
    for g in giocatori:
        InscriptionService.inscribe_user(g.id, gara.id)
    db_session.commit()
    RoundService.start_first_round(gara.id)
    db_session.commit()
    match_x = Match.query.filter_by(gara_id=gara.id, round_number=1, is_bye=True).one()
    return {"gara_id": gara.id, "giocatore_id": match_x.player1_id}


def _login(client, utente):
    from flask import g

    g.pop("_login_user", None)
    with client.session_transaction() as sess:
        sess["_user_id"] = utente.get_id()
        sess["_fresh"] = True


def test_il_punteggio_resta_anche_se_l_xp_fallisce(client, db_session, gara_con_x):
    gara_id, giocatore_id = gara_con_x["gara_id"], gara_con_x["giocatore_id"]
    prova_id = ChallengeService.create_x_replacement_attempt(
        user_id=giocatore_id, gara_id=gara_id, round_number=1
    ).id
    db_session.commit()
    _login(client, db.session.get(User, giocatore_id))

    with patch(
        "models.gamification.level_service.LevelService.award_xp",
        side_effect=RuntimeError("XP non disponibile"),
    ):
        risposta = client.post(
            f"/challenges/x-replacement/{prova_id}/complete", json={"score": 4}
        )
    assert risposta.status_code == 200
    assert risposta.get_json()["success"] is True

    # La fine della richiesta butta via ciò che nessuno ha salvato.
    db.session.rollback()
    db.session.expire_all()

    prova = db.session.get(ChallengeAttempt, prova_id)
    assert prova.completed is True
    assert prova.score == 4
    ponte = GaraByeChallenge.query.filter_by(challenge_attempt_id=prova_id).one()
    assert ponte.is_completed is True


def test_la_prova_aperta_resta_anche_senza_altro_che_salvi(db_session, gara_con_x):
    gara_id, giocatore_id = gara_con_x["gara_id"], gara_con_x["giocatore_id"]

    prova_id = ChallengeService.create_x_replacement_attempt(
        user_id=giocatore_id, gara_id=gara_id, round_number=1
    ).id
    db.session.rollback()
    db.session.expire_all()

    assert db.session.get(ChallengeAttempt, prova_id) is not None
    assert GaraByeChallenge.query.filter_by(challenge_attempt_id=prova_id).count() == 1
