"""«Azzera il turno» azzera tutte le partite concluse, e lascia stare la X.

Due difetti trovati il 2026-11-10 in
`AdvancedRoundManager.bulk_reset_round_matches`, che cercava le partite da
azzerare con `status == CLOSED_UNILATERALLY`:

* le partite chiuse **dai due giocatori** (`CONFIRMED_BY_BOTH`) sono concluse
  quanto le altre, ma restavano fuori: il turno si azzerava a metà, e se erano
  tutte così il direttore leggeva «Nessuna partita conclusa nel turno»;
* la X nasce `CLOSED_UNILATERALLY`, quindi entrava nell'elenco, e il reset
  della singola partita la rifiuta — non c'è niente da rigiocare. Un turno con
  la X finiva sempre con «errori: 1» anche quando era andato tutto bene.

La X non si azzera, né prima né adesso: resta com'è. Per toglierla c'è
«Annulla il turno», che la cancella con le altre.
"""

from __future__ import annotations

from datetime import date

import pytest

from models.competition.models import Gara, Inscription
from models.competition.round_manager import AdvancedRoundManager
from models.match.models import Match
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import Discipline, GaraStatus, MatchStatus

pytestmark = pytest.mark.unit


def _gara(db_session) -> Gara:
    """Gara casuale in corso: lì il turno non è mai bloccato dal successivo."""
    quante = db_session.query(Gara).count()
    gara = Gara(
        name=f"Azzera turno {quante + 1}",
        number=quante + 1,
        date=date.today(),
        distance=5,
        discipline=Discipline.NINE_BALL.value,
        matchmaking_strategy=MatchmakingStrategy.RANDOM.value,
        status=GaraStatus.PLAYING.value,
        current_round=1,
        is_race_to=True,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _partita(db_session, gara, primo, secondo, stato: str) -> Match:
    match = Match(
        gara_id=gara.id,
        player1_id=primo.id,
        player2_id=secondo.id,
        round_number=1,
        status=stato,
        player1_score=5,
        player2_score=3,
        winner_id=primo.id,
    )
    db_session.add(match)
    for giocatore in (primo, secondo):
        db_session.add(Inscription(gara_id=gara.id, user_id=giocatore.id))
    db_session.flush()
    return match


def _x(db_session, gara, giocatore) -> Match:
    match = Match(
        gara_id=gara.id,
        player1_id=giocatore.id,
        player2_id=None,
        round_number=1,
        is_bye=True,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
        player1_score=0,
        player2_score=0,
        winner_id=giocatore.id,
    )
    db_session.add(match)
    db_session.add(Inscription(gara_id=gara.id, user_id=giocatore.id))
    db_session.flush()
    return match


def test_azzera_anche_le_partite_chiuse_dai_due_giocatori(db_session, isolated_players):
    gara = _gara(db_session)
    a, b, c, d = isolated_players[:4]
    confermate = [
        _partita(db_session, gara, a, b, MatchStatus.CONFIRMED_BY_BOTH.value),
        _partita(db_session, gara, c, d, MatchStatus.CONFIRMED_BY_BOTH.value),
    ]
    db_session.commit()

    riuscito, _messaggio, conti = AdvancedRoundManager.bulk_reset_round_matches(
        gara.id, 1
    )

    assert riuscito is True
    assert conti["reset_count"] == 2
    assert conti["error_count"] == 0
    for match in confermate:
        azzerata = db_session.get(Match, match.id)
        assert not MatchStatus.is_finished(azzerata.status)
        assert (azzerata.player1_score, azzerata.player2_score) == (0, 0)
        assert azzerata.winner_id is None


def test_un_turno_misto_si_azzera_per_intero(db_session, isolated_players):
    gara = _gara(db_session)
    a, b, c, d = isolated_players[:4]
    _partita(db_session, gara, a, b, MatchStatus.CONFIRMED_BY_BOTH.value)
    _partita(db_session, gara, c, d, MatchStatus.CLOSED_UNILATERALLY.value)
    db_session.commit()

    riuscito, _messaggio, conti = AdvancedRoundManager.bulk_reset_round_matches(
        gara.id, 1
    )

    assert riuscito is True
    assert conti["reset_count"] == 2
    assert conti["total_matches"] == 2


def test_la_x_non_e_un_errore_e_resta_com_e(db_session, isolated_players):
    gara = _gara(db_session)
    a, b, c = isolated_players[:3]
    giocata = _partita(db_session, gara, a, b, MatchStatus.CLOSED_UNILATERALLY.value)
    x = _x(db_session, gara, c)
    db_session.commit()

    riuscito, _messaggio, conti = AdvancedRoundManager.bulk_reset_round_matches(
        gara.id, 1
    )

    assert riuscito is True, "la X non deve far dire «errori: 1»"
    assert conti["error_count"] == 0
    assert conti["reset_count"] == 1
    assert conti["total_matches"] == 1
    assert not MatchStatus.is_finished(db_session.get(Match, giocata.id).status)
    # La X non si azzera: resta una vittoria a zero differenza.
    la_x = db_session.get(Match, x.id)
    assert la_x.status == MatchStatus.CLOSED_UNILATERALLY.value
    assert la_x.winner_id == c.id


def test_con_la_sola_x_non_c_e_niente_da_azzerare(db_session, isolated_players):
    gara = _gara(db_session)
    _x(db_session, gara, isolated_players[0])
    db_session.commit()

    riuscito, _messaggio, conti = AdvancedRoundManager.bulk_reset_round_matches(
        gara.id, 1
    )

    assert riuscito is False
    assert conti == {}
