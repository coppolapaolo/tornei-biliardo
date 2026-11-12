"""Il direttore toglie un triangolo da una partita chiusa: l'ELO lo segue.

Rilievo della revisione del 2026-11-10. `RackService.remove_rack_admin`
riapriva solo le partite `CLOSED_UNILATERALLY`. Su una partita chiusa dai due
giocatori (`CONFIRMED_BY_BOTH`) 5-3, togliere un triangolo del vincitore la
lasciava «conclusa» sul 4-3, senza vincitore e senza `MatchReopenedEvent`:
l'ELO restava quello di un risultato che non esisteva più. È lo stesso
equivoco fra i due stati finali già corretto altrove (`finished_values`).

Secondo caso: il triangolo tolto è del **perdente** (5-3 → 5-2). Il vincitore
non cambia e la partita resta chiusa, ma l'ELO è a triangoli (ADR-052): si
annulla e si riapplica sul punteggio nuovo, con gli stessi due mattoni della
correzione del direttore (`to_playing` e `to_completed`).
"""

from __future__ import annotations

import pytest

from models.events.base import EventBus
from models.events.match_events import MatchReopenedEvent
from models.match.models import Match
from models.match.rack_service import RackService
from models.rating.models import MatchRatingHistory, RatingSystem
from models.status_enum import MatchStatus

from tests.new.unit._partite_di_prova import crea_gara, crea_partita, segna_triangoli


@pytest.fixture
def riaperture():
    """Gli id delle partite riaperte, senza togliere gli handler veri."""
    originali = {k: list(v) for k, v in EventBus._handlers.items()}
    viste: list = []
    EventBus.subscribe(MatchReopenedEvent)(lambda e: viste.append(e.match_id))
    yield viste
    EventBus._handlers = originali


def _partita_5_3(db_session, giocatori, stato):
    gara = crea_gara(db_session)
    partita = crea_partita(
        db_session,
        gara,
        giocatori,
        player1_score=5,
        player2_score=3,
        winner_id=giocatori[0].id,
        status=stato,
        player1_confirmed=True,
        player2_confirmed=True,
    )
    # I primi tre al perdente, gli ultimi cinque al vincitore.
    racks = segna_triangoli(
        db_session, partita, [giocatori[1]] * 3 + [giocatori[0]] * 5
    )
    return partita, racks


@pytest.mark.parametrize(
    "stato",
    [MatchStatus.CLOSED_UNILATERALLY.value, MatchStatus.CONFIRMED_BY_BOTH.value],
)
def test_tolto_il_triangolo_decisivo_la_partita_torna_in_corso(
    db_session, isolated_players, riaperture, stato
):
    partita, racks = _partita_5_3(db_session, isolated_players, stato)

    RackService.remove_rack_admin(racks[-1].id)
    db_session.commit()

    partita = db_session.get(Match, partita.id)
    assert (partita.player1_score, partita.player2_score) == (4, 3)
    assert partita.winner_id is None
    assert partita.status == MatchStatus.PLAYING.value
    assert riaperture == [partita.id]


@pytest.mark.parametrize(
    "stato",
    [MatchStatus.CLOSED_UNILATERALLY.value, MatchStatus.CONFIRMED_BY_BOTH.value],
)
def test_tolto_un_triangolo_del_perdente_l_elo_si_riapplica(
    db_session, isolated_players, riaperture, stato
):
    from models.rating.calculation_service import RatingCalculationService

    p = isolated_players
    partita, racks = _partita_5_3(db_session, p, stato)
    RatingCalculationService.process_match_result(partita)
    db_session.commit()

    RackService.remove_rack_admin(racks[0].id)
    db_session.commit()

    partita = db_session.get(Match, partita.id)
    assert (partita.player1_score, partita.player2_score) == (5, 2)
    assert partita.winner_id == p[0].id
    assert MatchStatus.is_finished(partita.status)
    assert riaperture == [partita.id]
    righe = MatchRatingHistory.query.filter_by(
        match_id=partita.id, rating_system=RatingSystem.ELO
    ).all()
    assert len(righe) == 2
    # La robustness conta i triangoli della partita: sette, non più otto.
    assert {r.robustness_increment for r in righe} == {7}
