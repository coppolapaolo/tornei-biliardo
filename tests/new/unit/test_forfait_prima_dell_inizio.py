"""Il forfait chiude anche la partita che non è mai cominciata.

Rilievo della revisione del 2026-11-10. `ScoringService.forfeit_match`
chiudeva con `MatchStateService.to_completed(match_id)` senza dire che era una
chiusura d'ufficio, e su una partita ancora `PENDING` — nessun tavolo, nessun
triangolo — la transizione rifiutava con «Non è possibile completare una
partita che non è ancora iniziata». Il giocatore che non si presenta è proprio
il caso in cui la partita non comincia.

Passa di qui anche il ritiro deciso dal direttore
(`WithdrawPolicyService.ritira_dalla_partita`).
"""

from __future__ import annotations

from models.competition.withdraw_policy_service import WithdrawPolicyService
from models.match.match_service import MatchService
from models.match.models import Match
from models.status_enum import MatchStatus

from tests.new.unit._partite_di_prova import crea_gara, crea_partita, iscrivi


def _partita_mai_iniziata(db_session, giocatori):
    gara = crea_gara(db_session)
    partita = crea_partita(
        db_session, gara, giocatori, status=MatchStatus.PENDING.value
    )
    iscrivi(db_session, gara, giocatori[:2])
    return partita


def _e_un_5_0_a_tavolino(db_session, partita, vincitore):
    partita = db_session.get(Match, partita.id)
    assert partita.status == MatchStatus.CLOSED_UNILATERALLY.value
    assert (partita.player1_score, partita.player2_score) == (5, 0)
    assert partita.winner_id == vincitore.id
    assert partita.is_walkover is True


def test_il_forfait_del_giocatore_chiude_la_partita_in_attesa(
    db_session, isolated_players
):
    p = isolated_players
    partita = _partita_mai_iniziata(db_session, p)

    MatchService.forfeit_match(partita.id, p[1].id)
    db_session.commit()

    _e_un_5_0_a_tavolino(db_session, partita, p[0])


def test_il_ritiro_deciso_dal_direttore_chiude_la_partita_in_attesa(
    db_session, isolated_players
):
    p = isolated_players
    partita = _partita_mai_iniziata(db_session, p)

    WithdrawPolicyService.ritira_dalla_partita(partita.id, p[1].id, p[2].id)
    db_session.commit()

    _e_un_5_0_a_tavolino(db_session, partita, p[0])
