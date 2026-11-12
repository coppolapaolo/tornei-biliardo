"""«A tavolino» vuol dire nessun triangolo giocato: né di più, né di meno.

Rilievi della revisione del 2026-11-10 su `Match.is_walkover`, la domanda da
cui dipende se una partita chiusa muove l'ELO.

1. Contava i `Rack` **compresi quelli cancellati**. Un triangolo segnato per
   sbaglio e poi tolto, seguito da un forfait sullo 0-0, faceva risultare
   «giocata» una partita finita 5-0 a tavolino: l'ELO si muoveva per una
   partita che nessuno aveva giocato.
2. Per le partite **a set** guardava la tabella `Rack`, dove i loro triangoli
   non stanno mai: vivono nei set. Ogni partita di gara a set risultava
   quindi a tavolino, e non muoveva l'ELO.

Corretto il secondo, ne emergeva un terzo: l'ELO è a triangoli (ADR-052) ma
riceveva `player*_score`, che nelle partite a set conta i **set**. Un 2-0 nei
set giocato 5-4 5-4 sarebbe valso come un cappotto. Ora, gare e sfide, somma i
triangoli dei set.
"""

from __future__ import annotations

from models.base import utc_now
from models.individual_match.individual_rack_service import IndividualRackService
from models.individual_match.match_lifecycle_service import MatchLifecycleService
from models.individual_match.match_models import IndividualMatch
from models.match.match_service import MatchService
from models.match.models import Match
from models.rating.calculation_service import RatingCalculationService
from models.rating.eligibility import RatingEligibility, RatingExclusion
from models.rating.models import MatchRatingHistory, RatingSystem
from models.status_enum import Discipline, MatchStatus

from tests.new.unit._partite_di_prova import crea_gara, crea_partita, iscrivi


def test_un_triangolo_tolto_non_rende_giocato_il_forfait(db_session, isolated_players):
    p = isolated_players
    gara = crea_gara(db_session)
    partita = crea_partita(db_session, gara, p)
    iscrivi(db_session, gara, p[:2])

    MatchService.add_rack_for_player(partita.id, p[0].id, p[0].id)
    MatchService.remove_rack_for_player(partita.id, p[0].id, p[0].id)
    MatchService.forfeit_match(partita.id, p[1].id)
    db_session.commit()

    partita = db_session.get(Match, partita.id)
    assert (partita.player1_score, partita.player2_score) == (5, 0)
    assert partita.is_walkover is True
    assert RatingEligibility.exclusion_reason(partita) is RatingExclusion.WALKOVER
    assert MatchRatingHistory.query.filter_by(match_id=partita.id).count() == 0


def _gioca_due_set(db_session, giocatori):
    """Partita al meglio di due set «al 2»: 2-1 e 2-0 per il primo giocatore."""
    gara = crea_gara(db_session, distance=2)
    partita = crea_partita(
        db_session, gara, giocatori, is_multi_set=True, match_distance=2
    )
    partita.set_distance = 2
    db_session.commit()
    p0, p1 = giocatori[0].id, giocatori[1].id
    for vincitori in ([p0, p1, p0], [p0, p0]):
        MatchService.start_next_set(partita.id)
        for vincitore in vincitori:
            MatchService.add_rack_to_current_set(partita.id, vincitore)
    db_session.commit()
    return db_session.get(Match, partita.id)


def test_la_partita_a_set_giocata_non_e_a_tavolino(db_session, isolated_players):
    partita = _gioca_due_set(db_session, isolated_players)

    assert partita.status == MatchStatus.CLOSED_UNILATERALLY.value
    assert (partita.player1_score, partita.player2_score) == (2, 0)
    assert partita.is_walkover is False
    assert RatingEligibility.exclusion_reason(partita) is None


def test_la_partita_a_set_muove_l_elo_con_i_triangoli_non_con_i_set(
    db_session, isolated_players
):
    partita = _gioca_due_set(db_session, isolated_players)

    righe = MatchRatingHistory.query.filter_by(
        match_id=partita.id, rating_system=RatingSystem.ELO
    ).all()
    assert len(righe) == 2
    # Cinque triangoli giocati, 4-1: non i due set del 2-0.
    assert {r.robustness_increment for r in righe} == {5}


def test_la_partita_a_set_senza_triangoli_resta_a_tavolino(
    db_session, isolated_players
):
    p = isolated_players
    gara = crea_gara(db_session, distance=2)
    partita = crea_partita(
        db_session,
        gara,
        p,
        is_multi_set=True,
        match_distance=2,
        player1_score=2,
        winner_id=p[0].id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )

    assert partita.is_walkover is True


def test_la_sfida_a_set_muove_l_elo_con_i_triangoli(db_session, isolated_players):
    p = isolated_players
    sfida = IndividualMatch(
        player1_id=p[0].id,
        player2_id=p[1].id,
        scheduled_at=utc_now(),
        status=MatchStatus.SCHEDULED,
        discipline=Discipline.NINE_BALL.value,
        distance=2,
        is_multi_set=True,
        match_distance=1,
        is_race_to_sets=True,
    )
    db_session.add(sfida)
    db_session.commit()
    MatchLifecycleService.start_match(sfida.id, p[0].id)
    for vincitore in (p[0], p[1], p[0]):
        IndividualRackService.add_rack_for_player(sfida.id, p[0].id, vincitore.id)
    db_session.commit()
    sfida = db_session.get(IndividualMatch, sfida.id)
    assert (sfida.player1_score, sfida.player2_score) == (1, 0)

    RatingCalculationService.process_individual_match_result(
        sfida, RatingSystem.ELO_GLOBAL
    )
    db_session.commit()

    righe = MatchRatingHistory.query.filter_by(
        individual_match_id=sfida.id, rating_system=RatingSystem.ELO_GLOBAL
    ).all()
    assert len(righe) == 2
    # Un set vinto 2-1: tre triangoli, non «uno a zero».
    assert {r.robustness_increment for r in righe} == {3}
