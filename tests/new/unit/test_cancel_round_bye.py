"""Regression tests for cancel_round ignoring bye matches.

Source: ADR-026 residual (2026-04-19). Spec:
`_bmad-output/implementation-artifacts/spec-cancel-round-ignores-bye.md`.

Il bye è artefatto algoritmico (parity dispari), non input utente:
`player1_score = round_distance` è solo convenzione di persistenza per
la classification. Concettualmente il bye è "in stato iniziale per
definizione" → non deve bloccare `cancel_round` come se fosse un
risultato parziale.

I walkover (2-player forfeit, trio walkover) rappresentano invece
azioni umane (l'iscritto ha fatto forfeit) e continuano a bloccare
`cancel_round` come gli altri match con risultato reale.
"""

from __future__ import annotations

from datetime import date

import pytest

from models.competition.models import Gara, Inscription
from models.competition.round_manager import AdvancedRoundManager
from models.match.models import Match
from models.match.rack_service import RackService
from models.status_enum import GaraStatus, MatchStatus


def _make_playing_gara(db_session) -> Gara:
    """Gara Random (round lock sempre UNLOCKED) in stato PLAYING."""
    existing_count = db_session.query(Gara).count()
    gara = Gara(
        name=f"Cancel-round-bye gara {existing_count + 1}",
        number=existing_count + 1,
        date=date.today(),
        distance=5,
        discipline="palla_9",
        matchmaking_strategy="random",
        status=GaraStatus.PLAYING.value,
        is_race_to=True,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _add_bye(db_session, gara, player, round_number: int = 1) -> Match:
    match = Match(
        gara_id=gara.id,
        player1_id=player.id,
        player2_id=None,
        round_number=round_number,
        is_bye=True,
        status=MatchStatus.PENDING.value,
        player1_score=gara.distance,
        player2_score=0,
        winner_id=player.id,
    )
    db_session.add(match)
    db_session.add(Inscription(gara_id=gara.id, user_id=player.id))
    db_session.flush()
    return match


def _add_pending_match(
    db_session, gara, player1, player2, round_number: int = 1
) -> Match:
    match = Match(
        gara_id=gara.id,
        player1_id=player1.id,
        player2_id=player2.id,
        round_number=round_number,
        status=MatchStatus.PENDING.value,
        player1_score=0,
        player2_score=0,
    )
    db_session.add(match)
    db_session.add(Inscription(gara_id=gara.id, user_id=player1.id))
    db_session.add(Inscription(gara_id=gara.id, user_id=player2.id))
    db_session.flush()
    return match


def _add_completed_match(
    db_session, gara, player1, player2, round_number: int = 1
) -> Match:
    match = Match(
        gara_id=gara.id,
        player1_id=player1.id,
        player2_id=player2.id,
        round_number=round_number,
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


def _add_walkover_match(
    db_session, gara, winner, loser, round_number: int = 1
) -> Match:
    """2-player walkover: loser ha fatto forfeit, winner prende round_distance racks."""
    match = Match(
        gara_id=gara.id,
        player1_id=winner.id,
        player2_id=loser.id,
        round_number=round_number,
        is_bye=False,
        status=MatchStatus.COMPLETED.value,
        player1_score=gara.distance,
        player2_score=0,
        winner_id=winner.id,
    )
    db_session.add(match)
    db_session.add(Inscription(gara_id=gara.id, user_id=winner.id))
    db_session.add(Inscription(gara_id=gara.id, user_id=loser.id, is_forfeit=True))
    db_session.flush()
    return match


def _add_trio_walkover_match(
    db_session, gara, winner, p2, p3, round_number: int = 1
) -> Match:
    """Trio walkover (2/3 o 3/3 forfeit): winner prende round_distance racks."""
    match = Match(
        gara_id=gara.id,
        player1_id=winner.id,
        player2_id=p2.id,
        round_number=round_number,
        is_bye=False,
        is_trio=True,
        status=MatchStatus.COMPLETED.value,
        player1_score=gara.distance,
        player2_score=0,
        winner_id=winner.id,
    )
    db_session.add(match)
    db_session.add(Inscription(gara_id=gara.id, user_id=winner.id))
    db_session.add(Inscription(gara_id=gara.id, user_id=p2.id, is_forfeit=True))
    db_session.add(Inscription(gara_id=gara.id, user_id=p3.id, is_forfeit=True))
    db_session.flush()
    return match


@pytest.mark.unit
class TestCancelRoundIgnoresBye:
    """`cancel_round` esclude i bye dal predicato `matches_with_results`."""

    def test_cancel_round_with_bye_and_pending_succeeds(
        self, db_session, isolated_players
    ):
        """AC1: 1 bye + 3 match pending → cancel_round riesce."""
        gara = _make_playing_gara(db_session)
        p1, p2, p3, p4, p5, p6, p7 = isolated_players[:7]
        _add_bye(db_session, gara, p1)
        _add_pending_match(db_session, gara, p2, p3)
        _add_pending_match(db_session, gara, p4, p5)
        _add_pending_match(db_session, gara, p6, p7)
        gara.current_round = 1
        db_session.commit()

        success, message = AdvancedRoundManager.cancel_round(gara.id, 1)

        assert success is True, f"Expected success, got: {message}"
        assert "cancellato" in message.lower()
        # Verifica che tutti i match siano stati cancellati
        remaining = (
            db_session.query(Match).filter_by(gara_id=gara.id, round_number=1).count()
        )
        assert remaining == 0

    def test_cancel_round_all_bye_succeeds(self, db_session, isolated_players):
        """AC2: round teorico con solo bye → cancel_round riesce."""
        gara = _make_playing_gara(db_session)
        p1, p2 = isolated_players[:2]
        _add_bye(db_session, gara, p1)
        _add_bye(db_session, gara, p2)
        gara.current_round = 1
        db_session.commit()

        success, message = AdvancedRoundManager.cancel_round(gara.id, 1)

        assert success is True, f"Expected success, got: {message}"
        remaining = (
            db_session.query(Match).filter_by(gara_id=gara.id, round_number=1).count()
        )
        assert remaining == 0

    def test_cancel_round_bye_plus_real_score_blocked(
        self, db_session, isolated_players
    ):
        """AC3a: 1 bye + 1 match 5-3 reale → cancel_round bloccato dal match reale."""
        gara = _make_playing_gara(db_session)
        p1, p2, p3 = isolated_players[:3]
        _add_bye(db_session, gara, p1)
        _add_completed_match(db_session, gara, p2, p3)
        gara.current_round = 1
        db_session.commit()

        success, message = AdvancedRoundManager.cancel_round(gara.id, 1)

        assert success is False
        assert "risultati parziali" in message.lower()
        # Match non devono essere stati cancellati
        remaining = (
            db_session.query(Match).filter_by(gara_id=gara.id, round_number=1).count()
        )
        assert remaining == 2

    def test_cancel_round_bye_plus_walkover_blocked(
        self, db_session, isolated_players
    ):
        """AC3b: 1 bye + 1 walkover 2-player → cancel_round bloccato dal walkover.

        Il walkover è azione umana (forfeit), NON artefatto algoritmico:
        va resettato deliberatamente prima di cancellare il round.
        """
        gara = _make_playing_gara(db_session)
        p1, winner, loser = isolated_players[:3]
        _add_bye(db_session, gara, p1)
        _add_walkover_match(db_session, gara, winner, loser)
        gara.current_round = 1
        db_session.commit()

        success, message = AdvancedRoundManager.cancel_round(gara.id, 1)

        assert success is False
        assert "risultati parziali" in message.lower()
        remaining = (
            db_session.query(Match).filter_by(gara_id=gara.id, round_number=1).count()
        )
        assert remaining == 2

    def test_cancel_round_bye_plus_trio_walkover_blocked(
        self, db_session, isolated_players
    ):
        """AC3c: 1 bye + 1 trio walkover → cancel_round bloccato dal trio walkover."""
        gara = _make_playing_gara(db_session)
        p1, winner, p2, p3 = isolated_players[:4]
        _add_bye(db_session, gara, p1)
        _add_trio_walkover_match(db_session, gara, winner, p2, p3)
        gara.current_round = 1
        db_session.commit()

        success, message = AdvancedRoundManager.cancel_round(gara.id, 1)

        assert success is False
        assert "risultati parziali" in message.lower()
        remaining = (
            db_session.query(Match).filter_by(gara_id=gara.id, round_number=1).count()
        )
        assert remaining == 2


@pytest.mark.unit
class TestResetByeStillBlocked:
    """`reset_match_complete` su bye continua a raisare ValueError (status quo)."""

    def test_reset_bye_still_raises_value_error(self, db_session, isolated_players):
        """AC4 regression: reset single-match su bye blocca, coerente con
        "bye è sempre in stato iniziale"."""
        gara = _make_playing_gara(db_session)
        p1 = isolated_players[0]
        bye = _add_bye(db_session, gara, p1)
        db_session.commit()

        with pytest.raises(ValueError, match="Non puoi resettare una partita bye!"):
            RackService.reset_match_complete(bye.id)
