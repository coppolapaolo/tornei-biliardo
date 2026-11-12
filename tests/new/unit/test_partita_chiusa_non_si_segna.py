"""A partita chiusa il giocatore non segna più triangoli.

Rilievo della revisione del 2026-11-10. `ScoringService.add_rack_for_player`
non guardava lo stato: l'unico freno era la distanza. Una partita chiusa
**sotto** la distanza — interrotta a tempo sul 3-2, ADR-077 — accettava quindi
un altro triangolo da un giocatore: il punteggio passava a 3-3 a partita già
agli atti, senza riapertura e senza il revert dell'ELO che la chiusura aveva
mosso. La rimozione il controllo l'ha sempre avuto.

Vale per tutte e due le chiusure, quella del direttore e quella dei due
giocatori, e per la X a tavolino, che non ha triangoli da segnare.
"""

from __future__ import annotations

import pytest

from models.exceptions import ConflictError
from models.match.match_service import MatchService
from models.match.models import Match, Rack
from models.status_enum import MatchStatus

from tests.new.unit._partite_di_prova import crea_gara, crea_partita


@pytest.mark.parametrize(
    "stato",
    [MatchStatus.CLOSED_UNILATERALLY.value, MatchStatus.CONFIRMED_BY_BOTH.value],
)
def test_la_partita_chiusa_a_tempo_rifiuta_il_triangolo(
    db_session, isolated_players, stato
):
    p = isolated_players
    gara = crea_gara(db_session)
    partita = crea_partita(
        db_session,
        gara,
        p,
        player1_score=3,
        player2_score=2,
        winner_id=p[0].id,
        status=stato,
        closed_on_time=True,
    )

    with pytest.raises(ConflictError):
        MatchService.add_rack_for_player(partita.id, p[1].id, p[1].id)
    db_session.rollback()

    partita = db_session.get(Match, partita.id)
    assert (partita.player1_score, partita.player2_score) == (3, 2)
    assert partita.status == stato
    assert Rack.query.filter_by(match_id=partita.id).count() == 0


def test_la_x_a_tavolino_rifiuta_il_triangolo(db_session, isolated_players):
    p = isolated_players
    gara = crea_gara(db_session)
    partita = crea_partita(
        db_session,
        gara,
        p,
        player2_id=None,
        is_bye=True,
        winner_id=p[0].id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
    )

    with pytest.raises(ConflictError):
        MatchService.add_rack_for_player(partita.id, p[0].id, p[0].id)


def test_la_partita_in_corso_si_segna_come_sempre(db_session, isolated_players):
    p = isolated_players
    gara = crea_gara(db_session)
    partita = crea_partita(db_session, gara, p)

    MatchService.add_rack_for_player(partita.id, p[0].id, p[0].id)
    db_session.commit()

    partita = db_session.get(Match, partita.id)
    assert (partita.player1_score, partita.player2_score) == (1, 0)
