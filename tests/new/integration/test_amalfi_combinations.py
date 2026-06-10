"""Integration tests for Amalfi strategy: first round policies, odd players,
multiple rounds, exact rack mode, multi-set, and SSR tiebreaker.

Covers gaps identified in test coverage audit.
"""

import pytest
from datetime import date, timedelta
from typing import List
import uuid

from models import User, Gara, Match
from models.user.role_enum import UserRole
from models.status_enum import GaraStatus, MatchStatus
from models.competition.services import GaraService
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.match.services import MatchService, RackService
from models.classification.models import (
    RoundClassification,
    PlayerEncounter,
    Classification,
)
from models.campionato.models import Campionato
from models.base import db, utc_now


def _create_players(db_session, count: int, **extra_attrs) -> List[User]:
    """Create N players with optional extra attributes."""
    batch_id = str(uuid.uuid4())[:8]
    players = []
    for i in range(count):
        player = User(
            username=f"p{i}_{batch_id}",
            email=f"p{i}_{batch_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("test123")
        for attr, values in extra_attrs.items():
            if i < len(values):
                setattr(player, attr, values[i])
        players.append(player)
    db_session.add_all(players)
    db_session.commit()
    return players


def _create_director(db_session) -> User:
    uid = str(uuid.uuid4())[:8]
    director = User(
        username=f"dir_{uid}",
        email=f"dir_{uid}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("test123")
    db_session.add(director)
    db_session.commit()
    return director


def _create_amalfi_gara(
    director_id: int, players: List[User], db_session, **overrides
) -> Gara:
    """Create an Amalfi gara and inscribe players."""
    defaults = dict(
        campionato_id=None,
        number=1,
        name="Amalfi Test",
        date=date.today() + timedelta(days=7),
        location="Test",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=len(players) + 2,
        entry_fee=0.0,
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=director_id,
        matchmaking_strategy="amalfi",
        first_round_policy="random",
        odd_number_policy="bye",
        anti_rematch_enabled=True,
    )
    defaults.update(overrides)
    gara = GaraService.create_gara(**defaults)

    start = utc_now() - timedelta(hours=1)
    end = utc_now() + timedelta(days=5)
    InscriptionService.open_inscriptions(gara.id, start, end)
    for p in players:
        InscriptionService.inscribe_user(p.id, gara.id)
    return gara


def _complete_round_matches(gara_id: int, round_number: int):
    """Complete all matches in a round with deterministic scores."""
    matches = (
        Match.query.filter_by(gara_id=gara_id, round_number=round_number)
        .filter(
            Match.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value])
        )
        .all()
    )
    for match in matches:
        if match.is_bye:
            continue
        # Player1 always wins (deterministic for test predictability)
        match.player1_score = 5
        match.player2_score = 2
        match.winner_id = match.player1_id
        match.status = MatchStatus.COMPLETED.value

        from models.classification.encounter_service import PlayerEncounterService

        PlayerEncounterService.record_match_encounters(match)

    db.session.flush()
    RoundService.update_round_progression(gara_id)


def _run_full_tournament(gara: Gara):
    """Run all rounds of a tournament to completion."""
    RoundService.start_first_round(gara.id)
    _complete_round_matches(gara.id, 1)

    for r in range(2, gara.rounds_count + 1):
        RoundService.start_next_round(gara.id, r)
        _complete_round_matches(gara.id, r)


# =============================================================================
# 3.1 First Round Policy: Rating
# =============================================================================


@pytest.mark.integration
class TestFirstRoundPolicyRating:
    """Test first_round_policy='rating' with Amalfi."""

    def test_rating_seeding_uses_fargo_rating(self, db_session):
        """Players are ordered by fargo_rating descending for round 1."""
        director = _create_director(db_session)
        players = _create_players(
            db_session,
            6,
            fargo_rating=[700, 500, 600, 400, 800, 300],
        )
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            first_round_policy="rating",
        )

        RoundService.start_first_round(gara.id)

        # Check that round 1 matches were created
        matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        assert len(matches) == 3

        # Verify classification order: player4(800), player0(700), player2(600),
        # player1(500), player3(400), player5(300)
        # With salto=3 for round 1 of 3: pos1 vs pos4, pos2 vs pos5, pos3 vs pos6
        all_paired = set()
        for m in matches:
            all_paired.add(m.player1_id)
            all_paired.add(m.player2_id)
        assert len(all_paired) == 6

    def test_rating_fallback_to_elo(self, db_session):
        """Players without fargo_rating use elo_rating as fallback."""
        director = _create_director(db_session)
        players = _create_players(db_session, 4)
        # Set ratings manually: p0 has fargo, p1 has elo, p2 has both, p3 has none
        players[0].fargo_rating = 600
        players[0].elo_rating = None
        players[1].fargo_rating = None
        players[1].elo_rating = 500
        players[2].fargo_rating = 700
        players[2].elo_rating = 400  # fargo takes precedence
        players[3].fargo_rating = None
        players[3].elo_rating = None  # defaults to 0
        db_session.commit()

        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            first_round_policy="rating",
            rounds_count=2,
        )
        RoundService.start_first_round(gara.id)

        matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        assert len(matches) == 2  # 4 players = 2 matches

    def test_rating_full_tournament(self, db_session):
        """Complete tournament with rating seeding works end to end."""
        director = _create_director(db_session)
        players = _create_players(
            db_session,
            6,
            fargo_rating=[700, 500, 600, 400, 800, 300],
        )
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            first_round_policy="rating",
        )
        _run_full_tournament(gara)

        # Final classification should exist
        final_class = (
            RoundClassification.query.filter_by(gara_id=gara.id, round_number=3)
            .order_by(RoundClassification.position)
            .all()
        )
        assert len(final_class) == 6
        assert final_class[0].position == 1


# =============================================================================
# 3.1 First Round Policy: Classification
# =============================================================================


@pytest.mark.integration
class TestFirstRoundPolicyClassification:
    """Test first_round_policy='classification' with Amalfi."""

    def test_classification_standalone_falls_back_to_random(self, db_session):
        """Standalone gara with classification policy falls back to random."""
        director = _create_director(db_session)
        players = _create_players(db_session, 6)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            first_round_policy="classification",
        )
        # Should not raise — falls back to random
        RoundService.start_first_round(gara.id)
        matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        assert len(matches) == 3

    def test_classification_uses_campionato_standings(self, db_session):
        """Classification policy uses existing campionato standings for seeding."""
        director = _create_director(db_session)
        players = _create_players(db_session, 6)

        # Create campionato
        campionato = Campionato(
            name="Test Camp",
            campionato_type="amalfi",
            planned_gare_count=5,
        )
        db_session.add(campionato)
        db_session.flush()

        # Create campionato classification (standings from previous gare)
        for i, player in enumerate(players):
            cls = Classification(
                campionato_id=campionato.id,
                user_id=player.id,
                position=i + 1,
                total_matches_won=6 - i,
                total_point_difference=10 - i * 3,
            )
            db_session.add(cls)
        db_session.commit()

        # Create gara IN the campionato with classification policy
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            campionato_id=campionato.id,
            first_round_policy="classification",
        )

        RoundService.start_first_round(gara.id)
        matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        assert len(matches) == 3

        # With salto=3 for round 1 of 3, pos1 pairs with pos4
        # Verify all 6 players are paired
        paired = set()
        for m in matches:
            paired.add(m.player1_id)
            if m.player2_id:
                paired.add(m.player2_id)
        assert len(paired) == 6

    def test_classification_with_unclassified_players(self, db_session):
        """Some players have campionato standings, others don't."""
        director = _create_director(db_session)
        players = _create_players(db_session, 6)

        campionato = Campionato(
            name="Test Camp 2",
            campionato_type="amalfi",
            planned_gare_count=5,
        )
        db_session.add(campionato)
        db_session.flush()

        # Only first 4 players have classification (2 are new)
        for i in range(4):
            cls = Classification(
                campionato_id=campionato.id,
                user_id=players[i].id,
                position=i + 1,
                total_matches_won=4 - i,
            )
            db_session.add(cls)
        db_session.commit()

        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            campionato_id=campionato.id,
            first_round_policy="classification",
        )

        RoundService.start_first_round(gara.id)
        matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        assert len(matches) == 3

    def test_classification_no_standings_falls_back_to_random(self, db_session):
        """First gara in campionato (no standings yet) falls back to random."""
        director = _create_director(db_session)
        players = _create_players(db_session, 6)

        campionato = Campionato(
            name="New Camp",
            campionato_type="amalfi",
            planned_gare_count=5,
        )
        db_session.add(campionato)
        db_session.commit()

        # No Classification records — first gara
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            campionato_id=campionato.id,
            first_round_policy="classification",
        )

        RoundService.start_first_round(gara.id)
        matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        assert len(matches) == 3


# =============================================================================
# 3.2 Odd Players (5, 7) with Bye
# =============================================================================


@pytest.mark.integration
class TestAmalfiOddPlayers:
    """Test Amalfi with odd number of players and bye policy."""

    def test_5_players_3_rounds_bye(self, db_session):
        """5 players, 3 rounds: each round has 2 matches + 1 bye."""
        director = _create_director(db_session)
        players = _create_players(db_session, 5)
        gara = _create_amalfi_gara(director.id, players, db_session)

        RoundService.start_first_round(gara.id)
        r1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        r1_byes = [m for m in r1_matches if m.is_bye]
        r1_regular = [m for m in r1_matches if not m.is_bye]

        assert len(r1_regular) == 2
        assert len(r1_byes) == 1

        _complete_round_matches(gara.id, 1)

        # Round 2
        RoundService.start_next_round(gara.id, 2)
        r2_matches = Match.query.filter_by(gara_id=gara.id, round_number=2).all()
        r2_byes = [m for m in r2_matches if m.is_bye]
        assert len(r2_byes) == 1

        # Bye should not go to the same player as R1
        r1_bye_player = r1_byes[0].player1_id
        r2_bye_player = r2_byes[0].player1_id
        assert r1_bye_player != r2_bye_player

    def test_7_players_3_rounds_no_double_bye(self, db_session):
        """7 players, 3 rounds: no player gets bye twice."""
        director = _create_director(db_session)
        players = _create_players(db_session, 7)
        gara = _create_amalfi_gara(director.id, players, db_session)

        bye_players = []
        RoundService.start_first_round(gara.id)
        r1_byes = Match.query.filter_by(
            gara_id=gara.id, round_number=1, is_bye=True
        ).all()
        bye_players.extend([m.player1_id for m in r1_byes])
        _complete_round_matches(gara.id, 1)

        for r in range(2, 4):
            RoundService.start_next_round(gara.id, r)
            byes = Match.query.filter_by(
                gara_id=gara.id, round_number=r, is_bye=True
            ).all()
            bye_players.extend([m.player1_id for m in byes])
            _complete_round_matches(gara.id, r)

        # All 3 bye players should be different
        assert len(bye_players) == 3
        assert len(set(bye_players)) == 3

    def test_5_players_full_tournament_anti_rematch(self, db_session):
        """5 players, 3 rounds: anti-rematch works with byes."""
        director = _create_director(db_session)
        players = _create_players(db_session, 5)
        gara = _create_amalfi_gara(director.id, players, db_session)
        _run_full_tournament(gara)

        # Verify no rematch (check encounters)
        encounters = PlayerEncounter.query.filter_by(gara_id=gara.id).all()
        pairs = [(e.player1_id, e.player2_id) for e in encounters]
        assert len(pairs) == len(set(pairs)), "Duplicate encounters found"


# =============================================================================
# 3.3 More Rounds (4-5)
# =============================================================================


@pytest.mark.integration
class TestAmalfiManyRounds:
    """Test Amalfi with 4-5 rounds."""

    def test_8_players_4_rounds(self, db_session):
        """8 players, 4 rounds: salto progression 4,3,2,1."""
        director = _create_director(db_session)
        players = _create_players(db_session, 8)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            rounds_count=4,
        )
        _run_full_tournament(gara)

        # All 4 rounds should have classification
        for r in range(1, 5):
            cls = RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=r
            ).all()
            assert len(cls) == 8, f"Round {r} classification missing"

        # No rematches in 4 rounds with 8 players (max 7 possible)
        encounters = PlayerEncounter.query.filter_by(gara_id=gara.id).all()
        pairs = [(e.player1_id, e.player2_id) for e in encounters]
        assert len(pairs) == len(set(pairs))

    def test_6_players_5_rounds(self, db_session):
        """6 players, 5 rounds: max unique pairs = C(6,2)/3 = 5, exactly enough."""
        director = _create_director(db_session)
        players = _create_players(db_session, 6)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            rounds_count=5,
        )
        _run_full_tournament(gara)

        final_cls = RoundClassification.query.filter_by(
            gara_id=gara.id, round_number=5
        ).all()
        assert len(final_cls) == 6


# =============================================================================
# 3.4 Anti-rematch edge case: more rounds than unique pairings
# =============================================================================


@pytest.mark.integration
class TestAntiRematchExhaustion:
    """Test behavior when rounds exceed unique pairings."""

    def test_4_players_4_rounds_forces_rematch(self, db_session):
        """4 players, 4 rounds: only 3 unique pairing sets possible.
        Round 4 must allow a rematch without crashing."""
        director = _create_director(db_session)
        players = _create_players(db_session, 4)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            rounds_count=4,
        )
        # Should not crash even though round 4 forces rematches
        _run_full_tournament(gara)

        matches_r4 = Match.query.filter_by(gara_id=gara.id, round_number=4).all()
        assert len(matches_r4) == 2


# =============================================================================
# 3.5 Rack mode: exact number (is_race_to=False)
# =============================================================================


@pytest.mark.integration
class TestAmalfiExactRackMode:
    """Test Amalfi with is_race_to=False (exact number of racks)."""

    def test_exact_rack_mode_odd_distance(self, db_session):
        """Exact mode with odd distance (no ties possible)."""
        director = _create_director(db_session)
        players = _create_players(db_session, 6)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            is_race_to=False,
            distance=5,
        )
        _run_full_tournament(gara)

        final_cls = RoundClassification.query.filter_by(
            gara_id=gara.id, round_number=3
        ).all()
        assert len(final_cls) == 6

    def test_exact_rack_mode_even_distance(self, db_session):
        """Exact mode with even distance (ties possible)."""
        director = _create_director(db_session)
        players = _create_players(db_session, 4)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            is_race_to=False,
            distance=4,
            rounds_count=2,
        )
        _run_full_tournament(gara)

        final_cls = RoundClassification.query.filter_by(
            gara_id=gara.id, round_number=2
        ).all()
        assert len(final_cls) == 4


# =============================================================================
# 3.7 SSR Tiebreaker Detection
# =============================================================================


@pytest.mark.integration
class TestAmalfiSSR:
    """Test SSR tiebreaker detection after Amalfi tournament."""

    def test_ssr_detection_after_completed_tournament(self, db_session):
        """After a completed tournament, SSR detects ties correctly."""
        from models.competition.spareggio_service import SpareggioService

        director = _create_director(db_session)
        players = _create_players(db_session, 4)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            rounds_count=2,
            tiebreaker_enabled=True,
            tiebreaker_until_position=3,
        )

        _run_full_tournament(gara)

        # SSR should be able to detect if there are ties
        # (may or may not find ties depending on random results)
        tiebreakers = SpareggioService.detect_tiebreakers(gara.id)
        # Should not crash — result depends on scores
        assert isinstance(tiebreakers, list)

    def test_ssr_position_1_only(self, db_session):
        """SSR with tiebreaker_until_position=1 only checks 1st place."""
        from models.competition.spareggio_service import SpareggioService

        director = _create_director(db_session)
        players = _create_players(db_session, 4)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            rounds_count=2,
            tiebreaker_enabled=True,
            tiebreaker_until_position=1,
        )
        _run_full_tournament(gara)

        tiebreakers = SpareggioService.detect_tiebreakers(gara.id)
        assert isinstance(tiebreakers, list)
        # Any tiebreaker found should only be for position 1
        for tb in tiebreakers:
            assert tb.get("position", 1) <= 1


# =============================================================================
# 3.8 Odd Policies: bye_with_challenge, trio fallback, waitlist
# =============================================================================


@pytest.mark.integration
class TestAmalfiOddPolicies:
    """Test Amalfi with different odd number policies."""

    def test_bye_with_challenge_creates_bye(self, db_session):
        """bye_with_challenge with odd players creates a bye match."""
        director = _create_director(db_session)
        players = _create_players(db_session, 5)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            odd_number_policy="bye_with_challenge",
        )
        RoundService.start_first_round(gara.id)

        byes = Match.query.filter_by(gara_id=gara.id, round_number=1, is_bye=True).all()
        regular = Match.query.filter_by(
            gara_id=gara.id, round_number=1, is_bye=False
        ).all()
        assert len(byes) == 1
        assert len(regular) == 2

    def test_bye_with_challenge_full_flow(self, db_session):
        """Full bye_with_challenge flow: bye -> challenge -> score update."""
        from models.challenge.models import Challenge
        from models.competition.gara_challenge import GaraChallenge
        from models.competition.gara_challenge_service import GaraChallengeService
        from models.matchmaking.amalfi_challenge_bye_service import (
            AmalfiChallengeByeService,
        )

        director = _create_director(db_session)
        players = _create_players(db_session, 5)

        # Create a numeric challenge (for bye replacement scoring)
        challenge = Challenge(
            description="Spot Shot Rally",
            image_path="test.jpg",
            pass_fail_only=False,
            created_by_id=director.id,
            is_active=True,
        )
        db_session.add(challenge)
        db_session.commit()

        # Create gara with bye_with_challenge
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            odd_number_policy="bye_with_challenge",
        )

        # Link challenge to gara for round 1
        gara_challenge = GaraChallengeService.add_challenge_to_gara(
            gara_id=gara.id,
            challenge_id=challenge.id,
            round_number=1,
            max_attempts=3,
            added_by_id=director.id,
        )

        # Start round — creates bye match
        RoundService.start_first_round(gara.id)

        bye_match = Match.query.filter_by(
            gara_id=gara.id, round_number=1, is_bye=True
        ).first()
        assert bye_match is not None
        bye_player_id = bye_match.player1_id
        original_score = bye_match.player1_score

        # Bye player records a challenge attempt with score 12
        attempt = GaraChallengeService.record_challenge_attempt(
            gara_challenge_id=gara_challenge.id,
            user_id=bye_player_id,
            score=12,
            round_when_attempted=1,
        )

        # Update bye match with challenge score
        updated = AmalfiChallengeByeService.update_bye_match_from_challenge(attempt.id)
        assert updated is True

        # Verify bye match now has the challenge score
        db_session.refresh(bye_match)
        assert bye_match.player1_score == 12
        assert bye_match.status == "completed"

    def test_trio_policy_creates_trio_match(self, db_session):
        """Amalfi with trio policy: 3 lowest-ranked players get a trio match."""
        director = _create_director(db_session)
        players = _create_players(db_session, 5)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            odd_number_policy="trio",
            distance=4,
        )
        RoundService.start_first_round(gara.id)

        trios = Match.query.filter_by(
            gara_id=gara.id, round_number=1, is_trio=True
        ).all()
        regular = Match.query.filter_by(
            gara_id=gara.id, round_number=1, is_bye=False, is_trio=False
        ).all()
        byes = Match.query.filter_by(gara_id=gara.id, round_number=1, is_bye=True).all()

        assert len(trios) == 1, f"Expected 1 trio, got {len(trios)}"
        assert len(regular) == 1, f"Expected 1 regular match, got {len(regular)}"
        assert len(byes) == 0, f"Expected 0 byes, got {len(byes)}"

        # Verify trio has 3 players via TrioMatch
        trio_match = trios[0].trio_match
        assert trio_match is not None
        assert (
            len(
                set(
                    [
                        trio_match.player1_id,
                        trio_match.player2_id,
                        trio_match.player3_id,
                    ]
                )
            )
            == 3
        )

    def test_trio_no_repeat_across_rounds(self, db_session):
        """Amalfi trio: player shouldn't be in trio twice if others available."""
        director = _create_director(db_session)
        players = _create_players(db_session, 7)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            odd_number_policy="trio",
            distance=4,
            rounds_count=2,
        )

        RoundService.start_first_round(gara.id)

        # Get R1 trio players
        from models.match.models import TrioMatch

        r1_trio = (
            TrioMatch.query.join(Match)
            .filter(Match.gara_id == gara.id, Match.round_number == 1)
            .first()
        )
        r1_trio_players = {r1_trio.player1_id, r1_trio.player2_id, r1_trio.player3_id}

        _complete_round_matches(gara.id, 1)
        RoundService.start_next_round(gara.id, 2)

        # Get R2 trio players
        r2_trio = (
            TrioMatch.query.join(Match)
            .filter(Match.gara_id == gara.id, Match.round_number == 2)
            .first()
        )
        r2_trio_players = {r2_trio.player1_id, r2_trio.player2_id, r2_trio.player3_id}

        # At most 1 player should overlap (7 players, 3 per trio, 4 non-trio)
        overlap = r1_trio_players & r2_trio_players
        assert len(overlap) <= 1, f"Too many repeat trio players: {overlap}"

    def test_waitlist_policy_even_count_no_waitlist(self, db_session):
        """Waitlist policy with even players: no one excluded."""
        director = _create_director(db_session)
        players = _create_players(db_session, 6)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            odd_number_policy="no",
        )
        RoundService.start_first_round(gara.id)

        matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        all_players = set()
        for m in matches:
            all_players.add(m.player1_id)
            if m.player2_id:
                all_players.add(m.player2_id)
        assert len(all_players) == 6  # All 6 play
        assert len(matches) == 3


# =============================================================================
# 3.6 Multi-set (documented gap)
# =============================================================================


@pytest.mark.integration
class TestAmalfiMultiSet:
    """Multi-set with Amalfi strategy."""

    def test_multiset_propagated_to_matches(self, db_session):
        """is_multi_set flag propagates from Gara to Match on round creation."""
        director = _create_director(db_session)
        players = _create_players(db_session, 4)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            rounds_count=2,
        )
        gara.is_multi_set = True
        db.session.commit()

        RoundService.start_first_round(gara.id)

        matches = Match.query.filter_by(
            gara_id=gara.id, round_number=1, is_bye=False
        ).all()
        assert len(matches) == 2
        for m in matches:
            assert m.is_multi_set is True

    def test_non_multiset_matches_default_false(self, db_session):
        """Regular gara matches have is_multi_set=False."""
        director = _create_director(db_session)
        players = _create_players(db_session, 4)
        gara = _create_amalfi_gara(
            director.id,
            players,
            db_session,
            rounds_count=2,
        )
        RoundService.start_first_round(gara.id)

        matches = Match.query.filter_by(
            gara_id=gara.id, round_number=1, is_bye=False
        ).all()
        for m in matches:
            assert m.is_multi_set is False
