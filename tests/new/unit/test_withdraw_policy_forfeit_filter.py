"""Regression tests for WithdrawPolicyService.get_forfeit_inscriptions.

Source: deferred-work.md (2026-04-19 ECH residual from fix-forfeit-first-round
review). `get_forfeit_inscriptions` must exclude waitlist entries so that
a promoted waitlist player carrying `is_forfeit=True` from a prior state is
not silently routed to walkover creation. Today such a combination is
unreachable through production flows, but defensive filtering documents the
contract and prevents future regressions.
"""

from __future__ import annotations

from datetime import date

import pytest

from models.competition.models import Gara, Inscription
from models.competition.withdraw_policy_service import WithdrawPolicyService


def _make_gara(db_session) -> Gara:
    existing_count = db_session.query(Gara).count()
    gara = Gara(
        name=f"Forfeit-filter gara {existing_count + 1}",
        number=existing_count + 1,
        date=date.today(),
        distance=5,
        discipline="palla_9",
        matchmaking_strategy="amalfi",
        status="inscription",
        is_race_to=True,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


@pytest.mark.unit
class TestGetForfeitInscriptionsWaitlistFilter:
    def test_excludes_waitlist_forfeit_inscription(self, db_session, isolated_players):
        """Waitlist+forfeit combo must not appear in forfeit set."""
        gara = _make_gara(db_session)
        active, waitlisted = (p.id for p in isolated_players[:2])
        db_session.add(
            Inscription(gara_id=gara.id, user_id=active, is_forfeit=True)
        )
        db_session.add(
            Inscription(
                gara_id=gara.id,
                user_id=waitlisted,
                is_forfeit=True,
                is_waitlist=True,
                waitlist_position=1,
                waitlist_reason="capacity",
            )
        )
        db_session.commit()

        result = WithdrawPolicyService.get_forfeit_inscriptions(gara.id)

        user_ids = {ins.user_id for ins in result}
        assert user_ids == {active}, (
            "Waitlist inscriptions must be excluded from the forfeit set even "
            "when is_forfeit=True (pre-emptive guard against waitlist promotion "
            "preserving is_forfeit)."
        )

    def test_includes_active_forfeit_inscription(self, db_session, isolated_players):
        """Sanity: active non-waitlist forfeit inscriptions still returned."""
        gara = _make_gara(db_session)
        active = isolated_players[0].id
        db_session.add(
            Inscription(gara_id=gara.id, user_id=active, is_forfeit=True)
        )
        db_session.commit()

        result = WithdrawPolicyService.get_forfeit_inscriptions(gara.id)

        assert [ins.user_id for ins in result] == [active]

    def test_excludes_withdrawn_inscription(self, db_session, isolated_players):
        """Sanity: withdrawn inscriptions already filtered (pre-existing behavior)."""
        gara = _make_gara(db_session)
        withdrawn = isolated_players[0].id
        db_session.add(
            Inscription(
                gara_id=gara.id,
                user_id=withdrawn,
                is_forfeit=True,
                is_withdrawn=True,
            )
        )
        db_session.commit()

        result = WithdrawPolicyService.get_forfeit_inscriptions(gara.id)

        assert result == []
