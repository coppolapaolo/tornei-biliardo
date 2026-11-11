"""Una partita dà i suoi XP una volta sola, anche se si chiude due volte.

Rilievo della review alla #752. Una partita può chiudersi più volte: il
direttore la corregge, toglie un triangolo del perdente, la azzera e la fa
rigiocare. Ogni chiusura riemette `MatchCompletedEvent`, ed è giusto: l'ELO
si annulla alla riapertura e si riapplica. Ma XP e missioni non si annullano,
e il gestore li ridava a ogni chiusura: correggere tre volte un punteggio
valeva tre vittorie.
"""

from __future__ import annotations

from models.events.match_events import MatchCompletedEvent
from models.gamification.event_handlers import GamificationEventHandlers
from models.gamification.models import XPTransaction, XPTransactionType
from models.match.rack_service import RackService
from models.status_enum import MatchStatus

from tests.new.unit._partite_di_prova import crea_gara, crea_partita, segna_triangoli

DI_PARTITA = [XPTransactionType.MATCH_WIN, XPTransactionType.MATCH_LOSS]


def _partita_5_3(db_session, p):
    gara = crea_gara(db_session)
    partita = crea_partita(
        db_session,
        gara,
        p,
        player1_score=5,
        player2_score=3,
        winner_id=p[0].id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )
    racks = segna_triangoli(db_session, partita, [p[1]] * 3 + [p[0]] * 5)
    return partita, racks


def _evento(partita, p):
    return MatchCompletedEvent(
        match_id=partita.id,
        player1_id=p[0].id,
        player1_name=p[0].username,
        player2_id=p[1].id,
        player2_name=p[1].username,
        winner_id=p[0].id,
        gara_id=partita.gara_id,
    )


def _xp_di_partita(p) -> int:
    return XPTransaction.query.filter(
        XPTransaction.user_id.in_([p[0].id, p[1].id]),
        XPTransaction.transaction_type.in_(DI_PARTITA),
    ).count()


def test_la_seconda_chiusura_non_ridà_gli_xp(db_session, isolated_players):
    p = isolated_players
    partita, _racks = _partita_5_3(db_session, p)

    GamificationEventHandlers.handle_match_completed_for_xp(_evento(partita, p))
    db_session.commit()
    assert _xp_di_partita(p) == 2

    GamificationEventHandlers.handle_match_completed_for_xp(_evento(partita, p))
    db_session.commit()
    assert _xp_di_partita(p) == 2


def test_un_altra_partita_dà_i_suoi_xp(db_session, isolated_players):
    p = isolated_players
    prima, _r = _partita_5_3(db_session, p)
    seconda, _r = _partita_5_3(db_session, p)

    GamificationEventHandlers.handle_match_completed_for_xp(_evento(prima, p))
    GamificationEventHandlers.handle_match_completed_for_xp(_evento(seconda, p))
    db_session.commit()

    assert _xp_di_partita(p) == 4


def test_tolto_un_triangolo_del_perdente_gli_xp_non_raddoppiano(
    db_session, isolated_players
):
    p = isolated_players
    partita, racks = _partita_5_3(db_session, p)
    GamificationEventHandlers.handle_match_completed_for_xp(_evento(partita, p))
    db_session.commit()

    RackService.remove_rack_admin(racks[0].id)
    db_session.commit()

    assert _xp_di_partita(p) == 2
