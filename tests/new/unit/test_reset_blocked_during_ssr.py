"""Il reset è bloccato mentre la gara è in fase di spareggio SSR.

ADR-026 stabilisce che lo spareggio certifica implicitamente i risultati
della gara: finché non è concluso, i match non si toccano. La regola era
però implementata leggendo la tabella `tiebreaker`, che nessun percorso
vivo popola — l'SSR di `SpareggioService` salva i punteggi sulle
classification e segna la gara `AWAITING_SSR`. Risultato: il predicato era
sempre falso in esercizio.

`can_modify_match` restava protetto per un'altra via (rifiuta ogni stato
diverso da PLAYING), ma `cancel_round` non controlla lo stato della gara:
durante l'SSR il director non poteva resettare un singolo match, però
poteva cancellare l'intero turno che lo conteneva.

I test con match PENDING sono i discriminanti: senza il fix `cancel_round`
li accetta, perché nessun risultato parziale lo blocca.
"""

from __future__ import annotations

from datetime import date

import pytest

from models.competition.models import Gara, Inscription
from models.competition.round_manager import AdvancedRoundManager
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus


def _make_gara(db_session, status: str) -> Gara:
    """Gara Random (round lock sempre UNLOCKED) nello stato richiesto."""
    existing_count = db_session.query(Gara).count()
    gara = Gara(
        name=f"SSR-reset gara {existing_count + 1}",
        number=existing_count + 1,
        date=date.today(),
        distance=5,
        discipline="palla_9",
        matchmaking_strategy="random",
        status=status,
        is_race_to=True,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _add_pending_match(db_session, gara, player1, player2) -> Match:
    match = Match(
        gara_id=gara.id,
        player1_id=player1.id,
        player2_id=player2.id,
        round_number=1,
        status=MatchStatus.PENDING.value,
        player1_score=0,
        player2_score=0,
    )
    db_session.add(match)
    db_session.add(Inscription(gara_id=gara.id, user_id=player1.id))
    db_session.add(Inscription(gara_id=gara.id, user_id=player2.id))
    db_session.flush()
    return match


def _add_completed_match(db_session, gara, player1, player2) -> Match:
    match = Match(
        gara_id=gara.id,
        player1_id=player1.id,
        player2_id=player2.id,
        round_number=1,
        status=MatchStatus.COMPLETED.value,
        player1_score=5,
        player2_score=3,
        winner_id=player1.id,
    )
    db_session.add(match)
    db_session.add(Inscription(gara_id=gara.id, user_id=player1.id))
    db_session.add(Inscription(gara_id=gara.id, user_id=player2.id))
    db_session.flush()
    return match


@pytest.mark.unit
class TestCancelRoundDuringSsr:
    def test_cancel_round_blocked_in_awaiting_ssr(self, db_session, isolated_players):
        """Discriminante: senza risultati parziali, solo l'SSR può bloccare."""
        gara = _make_gara(db_session, GaraStatus.AWAITING_SSR.value)
        p1, p2 = isolated_players[:2]
        _add_pending_match(db_session, gara, p1, p2)
        db_session.commit()

        success, message = AdvancedRoundManager.cancel_round(gara.id, 1)

        assert success is False
        assert "spareggio" in message.lower()

    def test_cancel_round_blocked_with_completed_matches(
        self, db_session, isolated_players
    ):
        """Con match completati il turno era già bloccato, ma per il motivo
        sbagliato: il director leggeva "risultati parziali" invece dello
        spareggio in corso."""
        gara = _make_gara(db_session, GaraStatus.AWAITING_SSR.value)
        p1, p2 = isolated_players[:2]
        _add_completed_match(db_session, gara, p1, p2)
        db_session.commit()

        success, message = AdvancedRoundManager.cancel_round(gara.id, 1)

        assert success is False
        assert "spareggio" in message.lower()

    def test_cancel_round_still_works_while_playing(self, db_session, isolated_players):
        """Non-regressione: in PLAYING il turno senza risultati resta cancellabile."""
        gara = _make_gara(db_session, GaraStatus.PLAYING.value)
        p1, p2 = isolated_players[:2]
        _add_pending_match(db_session, gara, p1, p2)
        db_session.commit()

        success, message = AdvancedRoundManager.cancel_round(gara.id, 1)

        assert success is True, f"cancel_round non deve essere bloccato: {message}"

    def test_cancel_round_blocked_when_completed(self, db_session, isolated_players):
        """A gara conclusa i risultati sono definitivi: niente cancellazione."""
        gara = _make_gara(db_session, GaraStatus.COMPLETED.value)
        p1, p2 = isolated_players[:2]
        _add_pending_match(db_session, gara, p1, p2)
        db_session.commit()

        success, message = AdvancedRoundManager.cancel_round(gara.id, 1)

        assert success is False
        assert message


@pytest.mark.unit
class TestSingleMatchResetDuringSsr:
    def test_can_modify_match_blocked_in_awaiting_ssr(
        self, db_session, isolated_players
    ):
        """Contratto già rispettato via check di stato: lo fissiamo esplicitamente
        perché è la controparte di `cancel_round`."""
        gara = _make_gara(db_session, GaraStatus.AWAITING_SSR.value)
        p1, p2 = isolated_players[:2]
        match = _add_completed_match(db_session, gara, p1, p2)
        db_session.commit()

        can_modify, reason = AdvancedRoundManager.can_modify_match(match.id)

        assert can_modify is False
        assert "spareggio" in reason.lower()

    def test_bulk_reset_blocked_in_awaiting_ssr(self, db_session, isolated_players):
        """Il bulk falliva match per match, con un messaggio che non nominava
        lo spareggio."""
        gara = _make_gara(db_session, GaraStatus.AWAITING_SSR.value)
        p1, p2 = isolated_players[:2]
        _add_completed_match(db_session, gara, p1, p2)
        db_session.commit()

        success, message, stats = AdvancedRoundManager.bulk_reset_round_matches(
            gara.id, 1
        )

        assert success is False
        assert "spareggio" in message.lower()
        assert stats.get("reset_count", 0) == 0
