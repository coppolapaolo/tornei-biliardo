"""«Annulla» e il cestino dello storico tolgono solo prove del catalogo (2026-11-10).

Il difetto, trovato da una revisione il 2026-11-10: «Annulla l'ultima» della
schermata di allenamento prendeva l'ultima prova completata dell'esercizio
senza guardare da dove venisse, e `ChallengeService.delete_attempt` non aveva
guardie. Due conseguenze:

* una prova nata in una **scheda** (ADR-072) spariva da sotto la sua casella
  anche a seduta chiusa: la casella restava «4 su 5» con quattro prove dietro;
* la prova giocata **al posto della X** nello storico figurava come prova del
  catalogo, col cestino accanto, pur valendo per la classifica di una gara.

Le prove di scheda si correggono dalla seduta, quelle di gara le tocca chi
dirige: nessuna delle due si toglie da qui.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.services import ChallengeService
from models.challenge.training_service import TrainingHistoryService
from models.competition.gara_bye_challenge import GaraByeChallenge
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.exceptions import ConflictError
from models.match.models import Match
from models.training_sheet import TrainingSessionService
from models.training_sheet.models import TrainingEntry, TrainingSheetItem
from models.training_sheet.services import TrainingSheetService
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration

AJAX = {"X-Requested-With": "XMLHttpRequest"}


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


def _login(client, utente):
    from flask import g

    g.pop("_login_user", None)
    with client.session_transaction() as sess:
        sess["_user_id"] = utente.get_id()
        sess["_fresh"] = True


def _esercizio(db_session, autore, **campi):
    esercizio = Challenge(
        title=f"E {uuid.uuid4().hex[:6]}",
        description="d",
        image_path="x.png",
        created_by_id=autore.id,
        is_active=True,
        **campi,
    )
    db_session.add(esercizio)
    db_session.commit()
    return esercizio


@pytest.fixture
def giocatore(db_session):
    return _utente(db_session, "gioc")


@pytest.fixture
def seduta_chiusa(db_session, giocatore):
    """Una scheda con una voce «4 su 5», segnata e chiusa."""
    esercizio = _esercizio(db_session, giocatore, pass_fail_only=True)
    scheda = TrainingSheetService.create_sheet(giocatore, "Scheda")
    voce = TrainingSheetItem(
        sheet_id=scheda.id,
        challenge_id=esercizio.id,
        position=1,
        measure="made",
        amount=5,
    )
    db_session.add(voce)
    db_session.commit()
    seduta = TrainingSessionService.start(scheda.id, giocatore)
    TrainingSessionService.record(seduta.id, voce.id, giocatore, value=4)
    TrainingSessionService.close(seduta.id, giocatore)
    casella = TrainingEntry.query.filter_by(session_id=seduta.id).one()
    return {"esercizio": esercizio, "casella_id": casella.id}


@pytest.fixture
def prova_della_x(db_session):
    """Gara Amalfi a cinque, con la prova della X dichiarata dal giocatore."""
    direttore = _utente(db_session, "dir", UserRole.DIRECTOR.value)
    giocatori = [_utente(db_session, f"p{i}") for i in range(5)]
    esercizio = _esercizio(db_session, direttore)
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
    di_turno = db.session.get(User, match_x.player1_id)
    prova = ChallengeService.create_x_replacement_attempt(
        user_id=di_turno.id, gara_id=gara.id, round_number=1
    )
    ChallengeService.complete_x_replacement_attempt(prova.id, score=4)
    db_session.commit()
    return {
        "gara": gara,
        "giocatore": di_turno,
        "esercizio": esercizio,
        "prova_id": prova.id,
    }


class TestLeProveDiScheda:
    def test_annulla_dal_catalogo_non_tocca_la_casella_chiusa(
        self, client, db_session, giocatore, seduta_chiusa
    ):
        esercizio = seduta_chiusa["esercizio"]
        _login(client, giocatore)

        risposta = client.post(f"/challenges/{esercizio.id}/train/undo", headers=AJAX)

        assert risposta.status_code == 404
        db_session.expire_all()
        casella = db_session.get(TrainingEntry, seduta_chiusa["casella_id"])
        assert casella.value == 4
        assert len(casella.attempts) == 5

    def test_annulla_toglie_la_prova_di_catalogo_e_non_quella_di_scheda(
        self, client, db_session, giocatore, seduta_chiusa
    ):
        """La prova di catalogo più vecchia delle prove di scheda resta la sola
        che «Annulla» può togliere."""
        esercizio = seduta_chiusa["esercizio"]
        libera = ChallengeAttempt(
            user_id=giocatore.id,
            challenge_id=esercizio.id,
            completed=True,
            passed=True,
            score=1,
            attempted_at=utc_now() - timedelta(days=2),
        )
        db_session.add(libera)
        db_session.commit()
        libera_id = libera.id
        _login(client, giocatore)

        risposta = client.post(f"/challenges/{esercizio.id}/train/undo", headers=AJAX)

        assert risposta.status_code == 200
        db_session.expire_all()
        assert db_session.get(ChallengeAttempt, libera_id) is None
        casella = db_session.get(TrainingEntry, seduta_chiusa["casella_id"])
        assert len(casella.attempts) == 5

    def test_il_servizio_rifiuta_di_cancellare_una_prova_di_scheda(
        self, db_session, giocatore, seduta_chiusa
    ):
        casella = db_session.get(TrainingEntry, seduta_chiusa["casella_id"])
        prova_id = casella.attempts[0].id

        with pytest.raises(ConflictError):
            ChallengeService.delete_attempt(attempt_id=prova_id, actor_id=giocatore.id)

        db_session.expire_all()
        assert db_session.get(ChallengeAttempt, prova_id) is not None


class TestLaProvaDellaX:
    def test_annulla_dal_catalogo_non_la_toglie(
        self, client, db_session, prova_della_x
    ):
        _login(client, prova_della_x["giocatore"])

        risposta = client.post(
            f"/challenges/{prova_della_x['esercizio'].id}/train/undo", headers=AJAX
        )

        assert risposta.status_code == 404
        db_session.expire_all()
        assert db_session.get(ChallengeAttempt, prova_della_x["prova_id"]) is not None

    def test_il_cestino_dello_storico_non_la_toglie(
        self, client, db_session, prova_della_x
    ):
        _login(client, prova_della_x["giocatore"])

        client.post(f"/player/history/drill/{prova_della_x['prova_id']}/delete")

        db_session.expire_all()
        assert db_session.get(ChallengeAttempt, prova_della_x["prova_id"]) is not None
        ponte = GaraByeChallenge.query.filter_by(gara_id=prova_della_x["gara"].id).one()
        assert ponte.challenge_attempt_id == prova_della_x["prova_id"]

    def test_nello_storico_non_e_una_prova_del_catalogo(
        self, db_session, prova_della_x
    ):
        voci = TrainingHistoryService.get_drill_attempts(prova_della_x["giocatore"].id)

        assert len(voci) == 1
        assert voci[0]["source"] == "x"
        assert voci[0]["attempt_id"] is None
        assert voci[0]["gara_name"] == prova_della_x["gara"].name


class TestIlCatalogoFunzionaAncora:
    def test_registra_e_annulla_l_ultima(self, client, db_session, giocatore):
        esercizio = _esercizio(db_session, giocatore, max_score=10)
        _login(client, giocatore)
        registrata = client.post(
            f"/challenges/{esercizio.id}/train", json={"score": 6}, headers=AJAX
        )
        assert registrata.status_code == 200
        prova_id = registrata.get_json()["attempt"]["id"]

        annullata = client.post(f"/challenges/{esercizio.id}/train/undo", headers=AJAX)

        assert annullata.status_code == 200
        assert annullata.get_json()["attempts_count"] == 0
        db_session.expire_all()
        assert db_session.get(ChallengeAttempt, prova_id) is None

    def test_la_prova_di_catalogo_nello_storico_ha_ancora_il_cestino(
        self, db_session, giocatore
    ):
        esercizio = _esercizio(db_session, giocatore, max_score=10)
        prova = ChallengeService.record_attempt(
            user_id=giocatore.id, challenge_id=esercizio.id, score=3
        )

        voci = TrainingHistoryService.get_drill_attempts(giocatore.id)

        assert voci[0]["source"] == "catalog"
        assert voci[0]["attempt_id"] == prova.id
