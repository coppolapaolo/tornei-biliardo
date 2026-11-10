"""La finale dei playoff decide la classifica generale solo da conclusa.

Difetto trovato il 2026-11-10 in `ClassificationService.playoff_finali`. Il
docstring diceva «finché la gara di playoff non è chiusa la lista è vuota»,
ma il codice guardava soltanto se la finale avesse righe `GaraClassification`.
Quelle righe nascono **prima** della chiusura: registrare i punteggi di uno
spareggio le crea per i soli giocatori a pari merito, con la gara ancora in
`AWAITING_SSR`. Nella modalità «solo playoff» la classifica generale metteva
così in cima quei due o tre finalisti — non tutti — nell'ordine di una finale
che il direttore poteva ancora cambiare.

Alla chiusura normale non cambia niente: `StateService.complete` segna la gara
conclusa prima di scrivere la classifica finale e di ricalcolare il campionato.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models import Campionato
from models.classification.campionato_classification import ClassificationService
from models.classification.models import GaraClassification
from models.competition.models import Gara
from models.matchmaking.configuration import MatchmakingStrategy
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffRankingMode,
    PlayoffType,
)
from models.status_enum import ClassificationSystem, Discipline, GaraStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _utente(db_session) -> User:
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"fin_{sigla}",
        email=f"fin_{sigla}@test.local",
        role=UserRole.PLAYER.value,
    )
    utente.set_password("prova1234")
    db_session.add(utente)
    db_session.flush()
    return utente


def _campionato_con_finale(db_session, stato_della_finale: str):
    """Campionato «solo playoff» con la finale nello stato dato e due righe."""
    campionato = Campionato(
        name=f"Campionato {uuid.uuid4().hex[:8]}",
        campionato_type=MatchmakingStrategy.AMALFI.value,
        is_active=True,
        default_classification_system=ClassificationSystem.WINS.value,
    )
    db_session.add(campionato)
    db_session.flush()
    configurazione = PlayoffConfiguration(
        campionato_id=campionato.id,
        name="Finale",
        playoff_type=PlayoffType.TOP_N,
        max_participants=4,
        positions_from=1,
        positions_to=4,
        is_active=True,
        auto_generate=True,
        final_ranking_mode=PlayoffRankingMode.PLAYOFF_ONLY.value,
    )
    db_session.add(configurazione)
    db_session.flush()
    finale = Gara(
        campionato_id=campionato.id,
        playoff_config_id=configurazione.id,
        name="Finale",
        number=9,
        date=date(2026, 1, 9),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=True,
        status=stato_della_finale,
        rounds_count=1,
        current_round=1,
        classification_system=ClassificationSystem.WINS.value,
        matchmaking_strategy=MatchmakingStrategy.AMALFI.value,
    )
    db_session.add(finale)
    db_session.flush()
    finalisti = [_utente(db_session), _utente(db_session)]
    for posizione, finalista in enumerate(finalisti, start=1):
        db_session.add(
            GaraClassification(
                gara_id=finale.id,
                user_id=finalista.id,
                position=posizione,
                matches_won=2 - posizione,
                spot_shot_wins=3 - posizione,
            )
        )
    db_session.commit()
    return campionato, finale, finalisti


@pytest.mark.parametrize(
    "stato",
    [GaraStatus.AWAITING_SSR.value, GaraStatus.PLAYING.value],
)
def test_la_finale_non_conclusa_non_decide_niente(db_session, stato):
    campionato, _finale, _finalisti = _campionato_con_finale(db_session, stato)

    assert ClassificationService.playoff_finali(campionato) == []
    assert ClassificationService.playoff_final_blocks(campionato) == []


def test_la_finale_conclusa_decide_l_ordine(db_session):
    campionato, finale, finalisti = _campionato_con_finale(
        db_session, GaraStatus.COMPLETED.value
    )

    finali = ClassificationService.playoff_finali(campionato)

    assert [gara.id for gara, _righe in finali] == [finale.id]
    assert ClassificationService.playoff_final_blocks(campionato) == [
        [finalista.id for finalista in finalisti]
    ]
