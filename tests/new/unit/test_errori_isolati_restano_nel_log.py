"""Un errore isolato non ferma l'operazione, ma resta scritto nel log.

In alcuni punti un lavoro secondario — il ricalcolo di una classifica, il
passaggio di stato di una partita, gli achievement — è avvolto in un
`try/except` perché il suo fallimento non deve annullare il lavoro principale.
È una scelta giusta, ed è sicura per i dati: dall'ADR-061 il `@transactional`
interno chiude il proprio savepoint.

Fino al 2026-11-10 però l'`except` faceva `pass`: l'errore spariva, e di un
ricalcolo non riuscito restava solo l'effetto — righe di classifica vecchie, un
tavolo assegnato a una partita mai partita — senza una riga di log da cui
risalire alla causa. È la classe dei guasti silenziosi che è già costata gli
inviti ai playoff del campionato 5.

Ogni test qui provoca l'errore e chiede due cose: che l'operazione principale
riesca comunque, e che il log lo racconti con il traceback.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime

import pytest

from models import Campionato
from models.challenge.models import Challenge
from models.challenge.services import ChallengeService
from models.competition.models import Gara, WithdrawPolicy
from models.individual_match import proposal_service
from models.location.models import BilliardHall
from models.match.models import Match
from models.match.table_assignment_service import TableAssignmentService
from models.status_enum import Discipline, GaraStatus
from models.campionato.services import TournamentService
from models.user.models import User

pytestmark = pytest.mark.unit


def _esplode(*_args, **_kwargs):
    raise RuntimeError("guasto provocato dal test")


def _errori_con_traceback(caplog, modulo: str) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.name == modulo and r.levelno >= logging.ERROR and r.exc_info
    ]


def _utente(db_session, prefisso: str) -> User:
    s = uuid.uuid4().hex[:8]
    u = User(
        username=f"{prefisso}_{s}",
        email=f"{prefisso}_{s}@test.com",
        password_hash="x",
    )
    db_session.add(u)
    db_session.commit()
    return u


def test_terminare_il_campionato_registra_il_ricalcolo_fallito(
    db_session, monkeypatch, caplog
):
    from models.classification.campionato_classification import (
        ClassificationService,
    )

    campionato = Campionato(
        name=f"Camp {uuid.uuid4().hex[:8]}",
        campionato_type="amalfi",
        is_active=True,
    )
    db_session.add(campionato)
    db_session.flush()
    db_session.add(
        Gara(
            campionato_id=campionato.id,
            number=1,
            name="Gara 1",
            date=date(2026, 1, 1),
            discipline=Discipline.NINE_BALL.value,
            status=GaraStatus.COMPLETED.value,
            rounds_count=3,
            current_round=1,
            distance=5,
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        ClassificationService, "update_campionato_classification", _esplode
    )

    with caplog.at_level(logging.ERROR):
        esito = TournamentService().terminate_campionato(campionato.id)

    assert esito is True
    assert db_session.get(Campionato, campionato.id).terminated_at is not None
    errori = _errori_con_traceback(caplog, "models.campionato.tournament_service")
    assert errori, "il ricalcolo fallito non ha lasciato traccia nel log"
    assert str(campionato.id) in errori[0].getMessage()


def test_assegnare_il_tavolo_registra_la_partita_che_non_parte(
    db_session, monkeypatch, caplog
):
    from models.match.match_service import MatchService

    sala = BilliardHall(
        name=f"Sala {uuid.uuid4().hex[:6]}",
        number_of_tables=3,
        table_names='["1", "2", "3"]',
    )
    db_session.add(sala)
    gara = Gara(
        number=1,
        date=datetime(2025, 10, 15, 19, 0),
        location=sala.name,
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
        status=GaraStatus.PLAYING.value,
        current_round=1,
        rounds_count=3,
        withdraw_policy=WithdrawPolicy.EXCLUDE.value,
    )
    db_session.add(gara)
    db_session.commit()
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=_utente(db_session, "tav_a").id,
        player2_id=_utente(db_session, "tav_b").id,
        table_assignment=None,
    )
    db_session.add(match)
    db_session.commit()
    monkeypatch.setattr(MatchService, "to_playing", _esplode)

    with caplog.at_level(logging.ERROR):
        riuscito, _messaggio, _altro = TableAssignmentService.reassign_table(
            match.id, "1"
        )

    assert riuscito is True
    assert db_session.get(Match, match.id).table_assignment == "1"
    errori = _errori_con_traceback(caplog, "models.match.table_assignment_service")
    assert errori, "la partita rimasta ferma non ha lasciato traccia nel log"
    assert str(match.id) in errori[0].getMessage()


def test_chiudere_una_prova_registra_gli_achievement_falliti(
    db_session, monkeypatch, caplog
):
    from models.gamification.achievement_service import AchievementService

    giocatore = _utente(db_session, "prova")
    esercizio = Challenge(
        title=f"Esercizio {uuid.uuid4().hex[:5]}",
        description="x",
        image_path="t.jpg",
        pass_fail_only=False,
        max_score=10,
        is_active=True,
    )
    db_session.add(esercizio)
    db_session.commit()
    monkeypatch.setattr(AchievementService, "reconcile_achievements", _esplode)

    with caplog.at_level(logging.ERROR):
        prova = ChallengeService.record_attempt(
            user_id=giocatore.id, challenge_id=esercizio.id, score=7
        )

    assert prova.completed is True
    assert prova.score == 7
    errori = _errori_con_traceback(caplog, "models.challenge.services")
    assert errori, "gli achievement falliti non hanno lasciato traccia nel log"
    assert str(giocatore.id) in errori[0].getMessage()


def test_le_proposte_registrano_gli_achievement_falliti(monkeypatch, caplog):
    from models.gamification.achievement_service import AchievementService

    monkeypatch.setattr(AchievementService, "reconcile_achievements", _esplode)

    with caplog.at_level(logging.ERROR):
        proposal_service._reconcile_user_achievements(4242)

    errori = _errori_con_traceback(caplog, "models.individual_match.proposal_service")
    assert errori, "gli achievement falliti non hanno lasciato traccia nel log"
    assert "4242" in errori[0].getMessage()
