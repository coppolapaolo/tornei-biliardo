"""Sfida a set finita: «Rifiuta» toglie davvero l'ultimo triangolo.

Rilievo della revisione del 2026-11-10. Nelle sfide rifiutare il risultato
vuol dire «l'ultimo triangolo non è andato così»: le firme si azzerano e
l'ultimo triangolo si toglie. Nella sfida a set, però,
`IndividualMatch._remove_last_rack` cercava il set **in corso** — e a sfida
finita non ce n'è nessuno, l'ultimo set è chiuso. Le firme sparivano, il
triangolo restava: il risultato rifiutato tornava identico a chiedere la
conferma.

`IndividualRackService._set_da_correggere` conosceva già la risposta per
l'annulla dal segnapunti: il set in corso, o l'ultimo chiuso che ha triangoli.
Ora la scelta sta sul modello e la usano tutti e due.
"""

from __future__ import annotations

from models.base import utc_now
from models.individual_match.individual_rack_service import IndividualRackService
from models.individual_match.match_lifecycle_service import MatchLifecycleService
from models.individual_match.match_models import IndividualMatch
from models.status_enum import Discipline, MatchStatus


def test_rifiutare_la_sfida_a_set_riapre_l_ultimo_set(db_session, isolated_players):
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
    IndividualRackService.add_rack_for_player(sfida.id, p[0].id, p[0].id)
    IndividualRackService.add_rack_for_player(sfida.id, p[0].id, p[0].id)
    db_session.commit()
    sfida = db_session.get(IndividualMatch, sfida.id)
    assert sfida.player1_score == 1 and sfida.is_ready_for_validation()

    MatchLifecycleService.reject_match_result(sfida.id, p[1].id)
    db_session.commit()

    sfida = db_session.get(IndividualMatch, sfida.id)
    assert sfida.player1_confirmed is False
    assert sfida.player1_score == 0, "il set riaperto non è più un set vinto"
    assert not sfida.is_ready_for_validation()
    ultimo = sfida.get_current_set()
    assert ultimo is not None, "il set chiuso dal triangolo tolto torna in corso"
    assert (ultimo.player1_racks, ultimo.player2_racks) == (1, 0)
