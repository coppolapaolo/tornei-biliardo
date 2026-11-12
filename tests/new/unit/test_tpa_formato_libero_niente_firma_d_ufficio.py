"""Referto TPA su una sfida in formato libero: nessuno firma al posto di nessuno.

Rilievo della revisione del 2026-11-10. Nel formato libero (`distance is None`)
non c'è un traguardo: la sfida finisce quando lo decidono i giocatori, e
`is_ready_for_validation()` è vera dal primo triangolo. `_sync_match_score`
però la usava da sola per decidere la firma d'ufficio, quindi ogni triangolo
annotato sul referto firmava per chi era in vantaggio — e contro un giocatore
non registrato, che non firma, la sfida si chiudeva al primo triangolo: il
secondo non aveva più dove andare.

È lo stesso difetto già corretto nel segnapunti normale
(`IndividualRackService.add_rack_for_player`) con la guardia
`match.distance is not None`; il referto era rimasto indietro.
"""

from __future__ import annotations

from models.base import utc_now
from models.individual_match.match_models import IndividualMatch
from models.status_enum import Discipline, MatchStatus
from models.tpa.models import TpaReferto
from models.tpa.services import TpaRefertoService


class _Conto:
    def __init__(self, vinti):
        self.racks_won = vinti


class _Stato:
    """Quel che `_sync_match_score` chiede allo stato: i triangoli per posto."""

    def __init__(self, primo, secondo):
        self._conti = {1: _Conto(primo), 2: _Conto(secondo)}

    def tally(self, seat):
        return self._conti[seat]


def _sfida_con_referto(db_session, giocatori, distance=None):
    sfida = IndividualMatch(
        player1_id=giocatori[0].id,
        player2_id=giocatori[1].id,
        scheduled_at=utc_now(),
        started_at=utc_now(),
        status=MatchStatus.IN_PROGRESS,
        discipline=Discipline.NINE_BALL.value,
        distance=distance,
    )
    db_session.add(sfida)
    db_session.commit()
    referto = TpaReferto(
        individual_match_id=sfida.id, compiler_id=giocatori[0].id, game_type=9
    )
    db_session.add(referto)
    db_session.commit()
    return sfida, referto


def test_nel_formato_libero_il_triangolo_non_firma_per_chi_e_avanti(
    db_session, isolated_players
):
    sfida, referto = _sfida_con_referto(db_session, isolated_players)

    TpaRefertoService._sync_match_score(referto, _Stato(1, 0))
    db_session.commit()

    assert (sfida.player1_score, sfida.player2_score) == (1, 0)
    assert sfida.player1_confirmed is False
    assert sfida.player2_confirmed is False
    assert sfida.status == MatchStatus.IN_PROGRESS


def test_contro_un_non_registrato_la_sfida_libera_non_si_chiude_al_primo_triangolo(
    db_session, isolated_players
):
    p = isolated_players
    p[1].is_placeholder = True
    db_session.commit()
    sfida, referto = _sfida_con_referto(db_session, p)

    TpaRefertoService._sync_match_score(referto, _Stato(1, 0))
    db_session.commit()
    assert sfida.status == MatchStatus.IN_PROGRESS

    # Il secondo triangolo trova la sfida ancora aperta.
    TpaRefertoService._sync_match_score(referto, _Stato(2, 0))
    db_session.commit()
    assert (sfida.player1_score, sfida.player2_score) == (2, 0)
    assert sfida.status == MatchStatus.IN_PROGRESS


def test_alla_distanza_chi_e_avanti_firma_come_prima(db_session, isolated_players):
    """La guardia non tocca le sfide con un traguardo."""
    sfida, referto = _sfida_con_referto(db_session, isolated_players, distance=2)

    TpaRefertoService._sync_match_score(referto, _Stato(2, 0))
    db_session.commit()

    assert sfida.player1_confirmed is True
    assert sfida.player2_confirmed is False
