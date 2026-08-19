# tests/new/integration/test_campionato_classification_pruning.py
"""`update_campionato_classification` toglie chi non è più in classifica.

Fino al 2026-08-19 la funzione era **solo upsert**: aggiornava e creava, mai
toglieva. Nel flusso normale non si nota — da un campionato un giocatore non
sparisce — ma succede quando una gara viene cancellata, un'iscrizione ritirata,
o una partecipazione spostata su un altro account (ADR-048).

E una riga rimasta indietro non è inerte: `start_playoff` qualifica leggendo
proprio queste righe, e il profilo giocatore le mostra.
"""

import uuid
from datetime import date, time, timedelta

import pytest

from models import db
from models.base import utc_now
from models.campionato.models import Campionato
from models.classification.campionato_classification import ClassificationService
from models.classification.gara_classification import (
    StrategyBasedClassificationService,
)
from models.classification.models import Classification
from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _user():
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"player_{suffix}",
        email=f"player_{suffix}@example.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("secret123")
    db.session.add(user)
    db.session.flush()
    return user


@pytest.fixture
def campionato_giocato(app, db_session):
    """Un campionato con una gara conclusa fra due giocatori."""
    campionato = Campionato(
        name=f"Campionato {uuid.uuid4().hex[:6]}",
        planned_gare_count=1,
        default_rounds_count=1,
    )
    db.session.add(campionato)
    db.session.flush()

    gara = Gara(
        name="Gara 1",
        number=1,
        campionato_id=campionato.id,
        date=date.today() - timedelta(days=5),
        time=time(18, 0),
        discipline="8_ball",
        distance=5,
        rounds_count=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="random",
        status=GaraStatus.COMPLETED.value,
        current_round=1,
        inscription_start=utc_now() - timedelta(days=10),
        inscription_end=utc_now() - timedelta(days=8),
    )
    db.session.add(gara)
    db.session.flush()

    vincitore, perdente = _user(), _user()
    for order, user in enumerate((vincitore, perdente), start=1):
        db.session.add(
            Inscription(gara_id=gara.id, user_id=user.id, initial_order=order)
        )
    db.session.add(
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=vincitore.id,
            player2_id=perdente.id,
            player1_score=5,
            player2_score=2,
            winner_id=vincitore.id,
            status=MatchStatus.CONFIRMED_BY_BOTH.value,
            ended_at=utc_now() - timedelta(days=5),
        )
    )
    db.session.flush()

    classification = StrategyBasedClassificationService()
    classification.calculate_round_classification(gara.id, 1)
    classification.calculate_gara_classification(gara.id)
    db.session.commit()

    return {"campionato": campionato, "gara": gara, "giocatori": (vincitore, perdente)}


def test_toglie_la_riga_di_chi_non_e_piu_in_classifica(campionato_giocato, db_session):
    campionato_id = campionato_giocato["campionato"].id
    estraneo = _user()

    # Riga di un giocatore che l'aggregato non produce: è lo stato che restava
    # indietro quando qualcuno usciva dalla classifica.
    db.session.add(
        Classification(
            campionato_id=campionato_id,
            user_id=estraneo.id,
            position=99,
            gare_played=1,
            total_matches_won=1,
        )
    )
    db.session.commit()

    ClassificationService.update_campionato_classification(campionato_id)
    db.session.commit()

    rimasti = {
        row.user_id
        for row in Classification.query.filter_by(campionato_id=campionato_id).all()
    }
    assert estraneo.id not in rimasti, "la riga orfana è sopravvissuta"
    assert {u.id for u in campionato_giocato["giocatori"]} == rimasti


def test_un_aggregato_vuoto_non_cancella_niente(campionato_giocato, db_session):
    """«Non so niente» e «non c'è più nessuno» sono due cose diverse.

    Se l'aggregazione non produce punteggi la funzione esce prima, e le righe
    esistenti restano dove sono: potarle su un risultato vuoto vorrebbe dire
    svuotare una classifica per un guasto a monte.
    """
    campionato_id = campionato_giocato["campionato"].id
    ClassificationService.update_campionato_classification(campionato_id)
    db.session.commit()
    prima = Classification.query.filter_by(campionato_id=campionato_id).count()
    assert prima > 0

    # Nessuna gara conclusa da aggregare più.
    campionato_giocato["gara"].status = GaraStatus.INSCRIPTION.value
    db.session.commit()

    ClassificationService.update_campionato_classification(campionato_id)
    db.session.commit()

    assert Classification.query.filter_by(campionato_id=campionato_id).count() == prima
