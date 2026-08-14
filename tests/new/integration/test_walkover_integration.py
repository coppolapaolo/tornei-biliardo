"""End-to-end integration: walkover routing → event bus → XP + rating handlers.

Spec: `_bmad-output/implementation-artifacts/spec-walkover-side-effects-unified.md`

Verifies the full event-driven side-effect chain for walkover matches:
- `MatchCompletedEvent` published via `MatchStateService.to_completed()`
- Gamification handler: winner gets XP, forfeiters do NOT
- Rating handler: Elo NOT updated for walkover matches
- PlayerEncounter rows recorded so anti-rematch sees walkover pairs as "played"
"""

from __future__ import annotations

from datetime import date

import pytest

from models.base import db
from models.classification.models import PlayerEncounter
from models.competition.models import Gara, Inscription
from models.competition.round_creation import create_matches_from_pairings
from models.events.base import EventBus
from models.events.match_events import MatchCompletedEvent
from models.gamification.event_handlers import GamificationEventHandlers
from models.gamification.models import XPTransaction, XPTransactionType
from models.matchmaking.strategies.base import Pairing
from models.rating.event_handlers import RatingEventHandlers


@pytest.fixture(autouse=True)
def register_walkover_handlers():
    """Register XP + rating handlers for walkover integration tests.

    Preserves and restores handlers to avoid leaking into later tests.
    """
    original_handlers = {k: list(v) for k, v in EventBus._handlers.items()}

    if MatchCompletedEvent not in EventBus._handlers:
        GamificationEventHandlers.register_all_handlers()

    EventBus.register_handler(
        MatchCompletedEvent,
        RatingEventHandlers.handle_match_completed,
        priority=20,
    )

    yield

    EventBus._handlers = original_handlers


def _make_gara(db_session, **overrides) -> Gara:
    existing_count = db_session.query(Gara).count()
    defaults = {
        "name": "Walkover integration gara",
        "number": existing_count + 1,
        "date": date.today(),
        "distance": 5,
        "discipline": "9_ball",
        "matchmaking_strategy": "amalfi",
        "status": "playing",
        "is_race_to": True,
    }
    defaults.update(overrides)
    gara = Gara(**defaults)
    db_session.add(gara)
    db_session.flush()
    return gara


def _xp_for_user(db_session, user_id: int) -> int:
    total = (
        db_session.query(XPTransaction).filter(XPTransaction.user_id == user_id).all()
    )
    return sum(t.xp_amount for t in total)


class TestWalkoverXPFiltering:
    """Forfeit players must not receive XP from walkover completions."""

    def test_two_player_forfeit_winner_xp_forfeiter_none(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        winner, forfeiter = isolated_players[0], isolated_players[1]
        db_session.add(Inscription(gara_id=gara.id, user_id=winner.id))
        db_session.add(
            Inscription(gara_id=gara.id, user_id=forfeiter.id, is_forfeit=True)
        )
        db_session.flush()

        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(forfeiter.id, winner.id), is_bye=False)],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={forfeiter.id},
        )
        db_session.commit()

        winner_xp = _xp_for_user(db_session, winner.id)
        forfeiter_xp = _xp_for_user(db_session, forfeiter.id)

        # Winner: at least MATCH_WIN XP (50). Forfeiter: zero.
        assert winner_xp > 0
        assert forfeiter_xp == 0

        # Audit: the winner transaction type should be MATCH_WIN, not MATCH_LOSS.
        txns = (
            db_session.query(XPTransaction)
            .filter(XPTransaction.user_id == winner.id)
            .all()
        )
        assert any(t.transaction_type == XPTransactionType.MATCH_WIN for t in txns)

    def test_trio_three_thirds_walkover_no_xp_for_anyone(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        p0, p1, p2 = isolated_players[0], isolated_players[1], isolated_players[2]
        for p in (p0, p1, p2):
            db_session.add(Inscription(gara_id=gara.id, user_id=p.id, is_forfeit=True))
        db_session.flush()

        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(p0.id, p1.id, p2.id), is_bye=False)],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0.id, p1.id, p2.id},
        )
        db_session.commit()

        # Nominal winner is p0 (also in forfeit set) → no XP.
        for p in (p0, p1, p2):
            assert _xp_for_user(db_session, p.id) == 0

        # Positive control: to_completed() did run (proven by encounter rows).
        # Without this, a silently-crashed handler would also produce zero XP
        # and the test would trivially pass on a broken implementation.
        assert db_session.query(PlayerEncounter).filter_by(gara_id=gara.id).count() == 3

    def test_trio_two_thirds_survivor_gets_match_win_xp(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        p0, p1, p2 = isolated_players[0], isolated_players[1], isolated_players[2]
        # p0 and p2 forfeit, p1 is the survivor → nominal winner.
        for p in (p0, p1, p2):
            db_session.add(
                Inscription(
                    gara_id=gara.id, user_id=p.id, is_forfeit=p.id in (p0.id, p2.id)
                )
            )
        db_session.flush()

        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(p0.id, p1.id, p2.id), is_bye=False)],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0.id, p2.id},
        )
        db_session.commit()

        # Survivor received MATCH_WIN XP, forfeiters received zero.
        survivor_txns = (
            db_session.query(XPTransaction).filter(XPTransaction.user_id == p1.id).all()
        )
        assert any(
            t.transaction_type == XPTransactionType.MATCH_WIN for t in survivor_txns
        )
        assert _xp_for_user(db_session, p0.id) == 0
        assert _xp_for_user(db_session, p2.id) == 0

    def test_two_player_2_2_forfeit_no_xp_for_anyone(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        p0, p1 = isolated_players[0], isolated_players[1]
        db_session.add(Inscription(gara_id=gara.id, user_id=p0.id, is_forfeit=True))
        db_session.add(Inscription(gara_id=gara.id, user_id=p1.id, is_forfeit=True))
        db_session.flush()

        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(p0.id, p1.id), is_bye=False)],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0.id, p1.id},
        )
        db_session.commit()

        # Nominal winner is p0 — also in forfeit set → zero XP for both.
        assert _xp_for_user(db_session, p0.id) == 0
        assert _xp_for_user(db_session, p1.id) == 0
        # Positive control: handler executed (encounter recorded).
        assert db.session.query(PlayerEncounter).filter_by(gara_id=gara.id).count() == 1


class TestWalkoverRatingSkip:
    """Rating updates must not fire for walkover matches."""

    def test_walkover_match_does_not_trigger_rating_calculation(
        self, db_session, isolated_players, monkeypatch
    ):
        from models.rating.calculation_service import RatingCalculationService

        gara = _make_gara(db_session)
        winner, forfeiter = isolated_players[0], isolated_players[1]
        db_session.add(Inscription(gara_id=gara.id, user_id=winner.id))
        db_session.add(
            Inscription(gara_id=gara.id, user_id=forfeiter.id, is_forfeit=True)
        )
        db_session.flush()

        calls: list[int] = []

        def fake_process(match):
            calls.append(match.id)

        monkeypatch.setattr(
            RatingCalculationService, "process_match_result", staticmethod(fake_process)
        )

        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(forfeiter.id, winner.id), is_bye=False)],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={forfeiter.id},
        )
        db_session.commit()

        assert calls == []


class TestWalkoverEncounterRecording:
    """PlayerEncounter must be recorded so anti-rematch sees walkover pairs."""

    def test_trio_walkover_records_three_encounters(self, db_session, isolated_players):
        gara = _make_gara(db_session)
        p0, p1, p2 = isolated_players[0], isolated_players[1], isolated_players[2]
        for p in (p0, p1, p2):
            db_session.add(
                Inscription(
                    gara_id=gara.id, user_id=p.id, is_forfeit=p.id in (p0.id, p2.id)
                )
            )
        db_session.flush()

        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(p0.id, p1.id, p2.id), is_bye=False)],
            round_number=1,
            round_distance=5,
            forfeit_user_ids={p0.id, p2.id},
        )
        db_session.commit()

        encounters = db.session.query(PlayerEncounter).filter_by(gara_id=gara.id).all()
        assert len(encounters) == 3
