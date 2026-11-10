"""Trio chiuso dai tre giocatori e poi riaperto: l'ELO torna indietro.

Rilievo della revisione del 2026-11-10. Dopo la tripla conferma il trio è
`CONFIRMED_BY_BOTH` e l'ELO si è già mosso. Finché il direttore non mette agli
atti, i giocatori possono ancora annullare l'ultimo triangolo
(`TrioScoringService.remove_last_rack`): la partita tornava in corso ma
nessuno emetteva `MatchReopenedEvent`, quindi i delta restavano applicati. Alla
chiusura successiva — magari con un altro vincitore — l'idempotenza del motore
(«questa partita l'ho già contata») lasciava per sempre l'ELO del risultato
sbagliato.

La partita a due lo fa da sempre (`ScoringService.remove_rack_for_player`,
ramo `riapri`); qui si chiede lo stesso al trio.
"""

from __future__ import annotations

from models.match.models import Match, TrioMatch
from models.match.trio_scoring_service import TrioScoringService
from models.rating.models import MatchRatingHistory
from models.status_enum import MatchStatus

from tests.new.unit.test_trio_chiusura_come_il_due import (
    _crea_trio,
    _gioca_fino_alla_distanza,
)


def _chiude_con_le_tre_conferme(db_session, trio, players):
    for giocatore in players:
        trio = db_session.get(TrioMatch, trio.id)
        if not trio.is_completed:
            trio.confirm_result_by_player(giocatore.id)
            db_session.commit()
    return db_session.get(TrioMatch, trio.id)


def test_annullato_l_ultimo_triangolo_i_delta_non_restano(db_session, isolated_players):
    trio, match, players = _crea_trio(db_session, isolated_players)
    trio = _gioca_fino_alla_distanza(db_session, trio, players)
    trio = _chiude_con_le_tre_conferme(db_session, trio, players)
    assert db_session.get(Match, match.id).status == (
        MatchStatus.CONFIRMED_BY_BOTH.value
    )
    assert (
        MatchRatingHistory.query.filter_by(match_id=match.id).count() > 0
    ), "premessa: la tripla conferma ha mosso l'ELO"

    TrioScoringService.remove_last_rack(trio.id, players[1].id)
    db_session.commit()

    assert db_session.get(Match, match.id).status == MatchStatus.PLAYING.value
    assert MatchRatingHistory.query.filter_by(match_id=match.id).count() == 0


def test_la_nuova_chiusura_conta_il_risultato_nuovo(db_session, isolated_players):
    trio, match, players = _crea_trio(db_session, isolated_players)
    trio = _gioca_fino_alla_distanza(db_session, trio, players)
    trio = _chiude_con_le_tre_conferme(db_session, trio, players)
    prima = {
        r.user_id: r.delta
        for r in MatchRatingHistory.query.filter_by(match_id=match.id).all()
    }

    # L'ultimo triangolo (P1 contro P2) era di P1: lo si ridà a P2.
    TrioScoringService.remove_last_rack(trio.id, players[1].id)
    db_session.commit()
    TrioScoringService.add_rack_win(trio.id, players[2].id)
    db_session.commit()
    trio = _chiude_con_le_tre_conferme(
        db_session, db_session.get(TrioMatch, trio.id), players
    )
    assert trio.is_completed

    dopo = {
        r.user_id: r.delta
        for r in MatchRatingHistory.query.filter_by(match_id=match.id).all()
    }
    assert dopo and dopo != prima
