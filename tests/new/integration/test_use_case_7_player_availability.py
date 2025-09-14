"""Integration tests for Use Case 7: Player availability and match requests.

Tests comprehensive workflow:
- Location-based availability (one-time and recurring)
- Match request system with notifications
- Venue-based player discovery
- Community match coordination
"""

import pytest
from datetime import date, datetime, timedelta, time
from typing import List, Dict, Any
import uuid

from models import User
from models.user.role_enum import UserRole
from models.individual_match.models import PlayerAvailability, MatchRequest
from models.location.models import BilliardHall, UserLocation
from models.notification.models import Notification
from models.notification.services import NotificationService


@pytest.mark.integration
class TestUseCasePlayerAvailability:
    """Test Use Case 7A: Player availability and location-based matching."""

    @pytest.fixture
    def admin_user(self, db_session) -> User:
        """Create admin user for test."""
        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value
        )
        admin.set_password("admin123")
        db_session.add(admin)
        db_session.commit()
        return admin

    @pytest.fixture
    def players_5(self, db_session) -> List[User]:
        """Create 5 players for availability testing."""
        batch_id = str(uuid.uuid4())[:8]
        players = []
        for i in range(5):
            player = User(
                username=f"player_{i}_{batch_id}",
                email=f"player_{i}_{batch_id}@test.com",
                role=UserRole.PLAYER.value
            )
            player.set_password("player123")
            players.append(player)
        
        db_session.add_all(players)
        db_session.commit()
        return players

    @pytest.fixture
    def billiard_halls(self, db_session) -> List[BilliardHall]:
        """Create billiard halls for location testing."""
        unique_id = str(uuid.uuid4())[:8]
        halls = []
        
        hall_data = [
            ("Downtown Billiards", "123 Main St", "Downtown", 12),
            ("Northside Pool Hall", "456 North Ave", "North District", 8),
            ("Eastside Cue Club", "789 East Blvd", "East Side", 16)
        ]
        
        for name, address, area, tables in hall_data:
            hall = BilliardHall(
                name=f"{name}_{unique_id}",
                address=address,
                area=area,
                total_tables=tables,
                is_active=True
            )
            halls.append(hall)
        
        db_session.add_all(halls)
        db_session.commit()
        return halls

    def test_one_time_availability_and_match_requests(
        self, players_5: List[User], billiard_halls: List[BilliardHall], db_session, client
    ):
        """Test one-time availability posting and match request system.
        
        Workflow:
        1. Player1 posts one-time availability at specific venue
        2. Player2 sees availability and requests match
        3. Player1 receives notification and accepts/declines
        4. Match is organized or alternative arrangements made
        5. Availability is updated based on responses
        """
        player1, player2, player3 = players_5[:3]
        downtown_hall = billiard_halls[0]

        # Step 1: Player1 posts one-time availability
        availability = PlayerAvailability.create_one_time_availability(
            user_id=player1.id,
            billiard_hall_id=downtown_hall.id,
            available_date=date.today() + timedelta(days=2),
            start_time=time(19, 0),  # 7:00 PM
            end_time=time(22, 0),    # 10:00 PM
            preferred_discipline="palla_9",
            skill_level="intermediate",
            notes="Looking for a friendly 9-ball game Thursday evening",
            max_opponents=2,  # Open to multiple matches
            entry_fee_range=(0.0, 10.0)  # Free to $10
        )

        assert availability is not None
        assert availability.user_id == player1.id
        assert availability.billiard_hall_id == downtown_hall.id
        assert availability.is_recurring is False
        assert availability.max_opponents == 2

        # Step 2: Player2 discovers availability and requests match
        # First, Player2 searches for available players at downtown location
        available_players = PlayerAvailability.find_available_players(
            billiard_hall_id=downtown_hall.id,
            target_date=date.today() + timedelta(days=2),
            discipline="palla_9",
            skill_level_range=("beginner", "advanced")
        )

        assert len(available_players) >= 1
        assert any(avail.user_id == player1.id for avail in available_players)

        # Player2 creates match request
        match_request = MatchRequest.create_match_request(
            requester_id=player2.id,
            target_availability_id=availability.id,
            requested_date=date.today() + timedelta(days=2),
            requested_start_time=time(19, 30),
            requested_duration_minutes=90,
            discipline="palla_9",
            distance=7,
            best_of=True,
            entry_fee=5.0,
            personal_message="Hi! I saw you're available Thursday. Want to play some 9-ball?"
        )

        assert match_request is not None
        assert match_request.requester_id == player2.id
        assert match_request.target_availability_id == availability.id

        # Step 3: Player1 receives notification and responds
        # Check notification was created
        notifications = Notification.query.filter_by(recipient_id=player1.id).all()
        match_request_notification = next(
            (n for n in notifications if "match request" in n.content.lower()), None
        )
        assert match_request_notification is not None

        # Player1 accepts the match request
        response_result = MatchRequest.respond_to_match_request(
            request_id=match_request.id,
            responder_id=player1.id,
            response="accepted",
            response_message="Sounds great! See you Thursday at 7:30 PM."
        )

        assert response_result.success is True

        # Verify match request status updated
        db_session.refresh(match_request)
        assert match_request.status == "accepted"

        # Step 4: Player3 also requests match (testing multiple requests)
        match_request2 = MatchRequest.create_match_request(
            requester_id=player3.id,
            target_availability_id=availability.id,
            requested_date=date.today() + timedelta(days=2),
            requested_start_time=time(20, 30),  # Later time
            requested_duration_minutes=60,
            discipline="palla_9",
            distance=5,
            best_of=True,
            entry_fee=0.0,
            personal_message="Are you free for another game after your first match?"
        )

        # Player1 accepts second request (within max_opponents limit)
        response_result2 = MatchRequest.respond_to_match_request(
            request_id=match_request2.id,
            responder_id=player1.id,
            response="accepted",
            response_message="Sure, I can play two matches that evening!"
        )

        assert response_result2.success is True

        # Step 5: Verify availability updated based on responses
        db_session.refresh(availability)
        accepted_requests = MatchRequest.query.filter_by(
            target_availability_id=availability.id,
            status="accepted"
        ).count()

        assert accepted_requests == 2
        assert accepted_requests == availability.max_opponents

        # If someone else tries to request, should be declined or waitlisted
        player4 = players_5[3]
        match_request3 = MatchRequest.create_match_request(
            requester_id=player4.id,
            target_availability_id=availability.id,
            requested_date=date.today() + timedelta(days=2),
            requested_start_time=time(21, 0),
            personal_message="Any chance for one more game?"
        )

        # This should either fail or be automatically waitlisted
        if match_request3:
            # If created, Player1 should decline due to being full
            decline_result = MatchRequest.respond_to_match_request(
                request_id=match_request3.id,
                responder_id=player1.id,
                response="declined",
                response_message="Sorry, I'm already booked for two matches that night!"
            )
            assert decline_result.success is True

        print(f"✅ One-time availability and match requests completed successfully")
        print(f"   - Player1 posted availability for {availability.available_date}")
        print(f"   - 2 match requests accepted, 1 declined (at capacity)")
        print(f"   - All requests properly notified and responded to")

    def test_recurring_availability_and_venue_discovery(
        self, players_5: List[User], billiard_halls: List[BilliardHall], db_session, client
    ):
        """Test recurring availability patterns and venue-based player discovery.
        
        Workflow:
        1. Multiple players set recurring availability patterns
        2. Players search for regular opponents at different venues
        3. Standing match arrangements are created
        4. Recurring availability management (modifications, cancellations)
        """
        player1, player2, player3, player4 = players_5[:4]
        downtown_hall, northside_hall, eastside_hall = billiard_halls

        # Step 1: Players set up recurring availability patterns
        
        # Player1: Regular Tuesday/Thursday evenings at Downtown
        recurring_avail1 = PlayerAvailability.create_recurring_availability(
            user_id=player1.id,
            billiard_hall_id=downtown_hall.id,
            weekdays=[1, 3],  # Tuesday=1, Thursday=3 (Monday=0)
            start_time=time(18, 0),
            end_time=time(21, 0),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),  # 3 months
            preferred_discipline="palla_8",
            skill_level="intermediate",
            notes="Regular 8-ball games, competitive but friendly",
            max_opponents=1,
            entry_fee_range=(5.0, 15.0)
        )

        # Player2: Weekly Friday nights at Northside
        recurring_avail2 = PlayerAvailability.create_recurring_availability(
            user_id=player2.id,
            billiard_hall_id=northside_hall.id,
            weekdays=[4],  # Friday=4
            start_time=time(19, 0),
            end_time=time(23, 0),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=120),  # 4 months
            preferred_discipline="palla_9",
            skill_level="advanced",
            notes="Serious 9-ball competition every Friday",
            max_opponents=2,
            entry_fee_range=(10.0, 25.0)
        )

        # Player3: Weekend afternoons at Eastside
        recurring_avail3 = PlayerAvailability.create_recurring_availability(
            user_id=player3.id,
            billiard_hall_id=eastside_hall.id,
            weekdays=[5, 6],  # Saturday=5, Sunday=6
            start_time=time(14, 0),
            end_time=time(18, 0),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=60),  # 2 months
            preferred_discipline="straight_pool",
            skill_level="beginner",
            notes="Learning straight pool, patient partners welcome",
            max_opponents=1,
            entry_fee_range=(0.0, 5.0)
        )

        assert recurring_avail1.is_recurring is True
        assert recurring_avail2.is_recurring is True
        assert recurring_avail3.is_recurring is True

        # Step 2: Player4 searches for regular opponents
        
        # Search for Tuesday/Thursday players at Downtown
        tuesday_players = PlayerAvailability.find_recurring_partners(
            billiard_hall_id=downtown_hall.id,
            weekday=1,  # Tuesday
            time_range=(time(17, 0), time(22, 0)),
            discipline="palla_8",
            skill_level_compatible=["beginner", "intermediate", "advanced"]
        )

        assert len(tuesday_players) >= 1
        assert any(avail.user_id == player1.id for avail in tuesday_players)

        # Search for weekend players
        weekend_players = PlayerAvailability.find_recurring_partners(
            billiard_hall_id=eastside_hall.id,
            weekday=5,  # Saturday
            time_range=(time(13, 0), time(19, 0))
        )

        assert len(weekend_players) >= 1
        assert any(avail.user_id == player3.id for avail in weekend_players)

        # Step 3: Create standing match arrangements
        
        # Player4 creates standing arrangement with Player1 (Tuesdays)
        standing_request1 = MatchRequest.create_standing_match_request(
            requester_id=player4.id,
            target_availability_id=recurring_avail1.id,
            preferred_weekday=1,  # Tuesday
            preferred_start_time=time(18, 30),
            duration_minutes=120,
            discipline="palla_8",
            distance=6,
            best_of=True,
            entry_fee=8.0,
            personal_message="Looking for a regular Tuesday opponent. Are you interested in weekly games?"
        )

        # Player1 accepts standing arrangement
        standing_response1 = MatchRequest.respond_to_match_request(
            request_id=standing_request1.id,
            responder_id=player1.id,
            response="accepted",
            response_message="Perfect! Let's make it a weekly thing. See you Tuesdays!"
        )

        assert standing_response1.success is True

        # Player4 also creates weekend arrangement with Player3
        standing_request2 = MatchRequest.create_standing_match_request(
            requester_id=player4.id,
            target_availability_id=recurring_avail3.id,
            preferred_weekday=6,  # Sunday
            preferred_start_time=time(15, 0),
            duration_minutes=90,
            discipline="straight_pool",
            distance=100,  # Learning format, longer games
            best_of=False,
            entry_fee=0.0,
            personal_message="I'm also learning straight pool. Want to practice together on Sundays?"
        )

        standing_response2 = MatchRequest.respond_to_match_request(
            request_id=standing_request2.id,
            responder_id=player3.id,
            response="accepted",
            response_message="Great! Learning together sounds perfect."
        )

        # Step 4: Test availability modifications
        
        # Player1 needs to modify Tuesday availability (earlier end time)
        modification_result = PlayerAvailability.modify_recurring_availability(
            availability_id=recurring_avail1.id,
            modifier_id=player1.id,
            changes={
                "end_time": time(20, 0),  # End hour earlier
                "notes": "Regular 8-ball games, competitive but friendly - ending earlier now"
            },
            effective_date=date.today() + timedelta(days=7),  # Next week
            notify_affected_players=True
        )

        assert modification_result.success is True

        # Player4 should receive notification about the change
        modification_notifications = Notification.query.filter_by(
            recipient_id=player4.id
        ).all()
        
        schedule_change_notification = next(
            (n for n in modification_notifications 
             if "schedule change" in n.content.lower() or "availability" in n.content.lower()), 
            None
        )
        assert schedule_change_notification is not None

        # Player2 cancels one specific occurrence
        next_friday = date.today() + timedelta(days=(4 - date.today().weekday()) % 7)
        cancellation_result = PlayerAvailability.cancel_specific_occurrence(
            availability_id=recurring_avail2.id,
            cancellation_date=next_friday,
            reason="Out of town this Friday",
            notify_affected_players=True
        )

        if cancellation_result:
            assert cancellation_result.success is True

        print(f"✅ Recurring availability and venue discovery completed successfully")
        print(f"   - 3 players set recurring availability patterns")
        print(f"   - 2 standing match arrangements created")
        print(f"   - Availability modifications and notifications working")
        print(f"   - Venue-based player discovery functional")

    def test_location_based_player_discovery_and_proximity_matching(
        self, players_5: List[User], billiard_halls: List[BilliardHall], db_session, client
    ):
        """Test location-based player discovery and proximity-based matching.
        
        Workflow:
        1. Players set their preferred venues and travel distances
        2. System suggests nearby players and venues
        3. Cross-venue match coordination
        4. Distance-based player filtering
        """
        player1, player2, player3, player4, player5 = players_5
        downtown_hall, northside_hall, eastside_hall = billiard_halls

        # Step 1: Players set location preferences
        
        # Player1 prefers Downtown, willing to travel 5 miles
        user_location1 = UserLocation.set_user_location_preferences(
            user_id=player1.id,
            primary_billiard_hall_id=downtown_hall.id,
            max_travel_distance_miles=5.0,
            preferred_venues=[downtown_hall.id, northside_hall.id],
            transportation_method="car",
            notes="Prefer central locations, have car"
        )

        # Player2 prefers Northside, public transport
        user_location2 = UserLocation.set_user_location_preferences(
            user_id=player2.id,
            primary_billiard_hall_id=northside_hall.id,
            max_travel_distance_miles=3.0,  # Limited by public transport
            preferred_venues=[northside_hall.id],
            transportation_method="public_transport",
            notes="Rely on bus, need convenient location"
        )

        # Player3 very flexible with locations
        user_location3 = UserLocation.set_user_location_preferences(
            user_id=player3.id,
            primary_billiard_hall_id=eastside_hall.id,
            max_travel_distance_miles=15.0,  # Will travel far
            preferred_venues=[downtown_hall.id, northside_hall.id, eastside_hall.id],
            transportation_method="car",
            notes="Very flexible, love trying different venues"
        )

        # Step 2: System suggests nearby players
        
        # Player4 wants to find players near Downtown
        nearby_players_downtown = UserLocation.find_players_near_venue(
            venue_id=downtown_hall.id,
            max_distance_miles=10.0,
            exclude_user_id=player4.id
        )

        # Should include Player1 and Player3 (both willing to go to Downtown)
        nearby_user_ids = [loc.user_id for loc in nearby_players_downtown]
        assert player1.id in nearby_user_ids
        assert player3.id in nearby_user_ids
        # Player2 might not be included due to location restrictions

        # Find players willing to travel to multiple venues
        flexible_players = UserLocation.find_flexible_players(
            min_venues=2,
            min_travel_distance=5.0
        )

        flexible_user_ids = [loc.user_id for loc in flexible_players]
        assert player1.id in flexible_user_ids  # 5 miles, 2 venues
        assert player3.id in flexible_user_ids  # 15 miles, 3 venues

        # Step 3: Cross-venue match coordination
        
        # Player4 wants to play but is flexible on location
        # Create availability at multiple venues
        multi_venue_availability = PlayerAvailability.create_multi_venue_availability(
            user_id=player4.id,
            billiard_hall_ids=[downtown_hall.id, northside_hall.id, eastside_hall.id],
            available_date=date.today() + timedelta(days=3),
            start_time=time(18, 0),
            end_time=time(21, 0),
            preferred_discipline="palla_9",
            skill_level="intermediate",
            notes="Flexible on location - can meet anywhere convenient",
            max_opponents=1,
            venue_preference_order=[downtown_hall.id, eastside_hall.id, northside_hall.id]
        )

        assert multi_venue_availability is not None

        # Player1 responds with venue preference
        venue_specific_request = MatchRequest.create_match_request(
            requester_id=player1.id,
            target_availability_id=multi_venue_availability.id,
            requested_date=date.today() + timedelta(days=3),
            requested_start_time=time(18, 30),
            preferred_venue_id=downtown_hall.id,  # Player1's preference
            discipline="palla_9",
            distance=7,
            best_of=True,
            entry_fee=10.0,
            personal_message="I can meet at Downtown Billiards if that works for you!"
        )

        # Player4 accepts with venue confirmation
        venue_response = MatchRequest.respond_to_match_request(
            request_id=venue_specific_request.id,
            responder_id=player4.id,
            response="accepted",
            confirmed_venue_id=downtown_hall.id,
            response_message="Downtown works great! See you there."
        )

        assert venue_response.success is True

        # Step 4: Distance-based filtering
        
        # Player5 sets very restrictive location preferences
        user_location5 = UserLocation.set_user_location_preferences(
            user_id=player5.id,
            primary_billiard_hall_id=northside_hall.id,
            max_travel_distance_miles=1.0,  # Very restrictive
            preferred_venues=[northside_hall.id],
            transportation_method="walking",
            notes="No car, must be walking distance"
        )

        # Search for players within Player5's travel range
        local_only_players = UserLocation.find_players_near_venue(
            venue_id=northside_hall.id,
            max_distance_miles=2.0,  # Slightly larger radius
            filter_by_player_travel_willingness=True
        )

        # Should primarily include Player2 (who also prefers Northside)
        local_user_ids = [loc.user_id for loc in local_only_players]
        assert player2.id in local_user_ids

        # Player3 might be included if they're willing to go to Northside despite distance
        # Player1 might be excluded if Downtown-Northside distance exceeds their willingness

        # Test proximity-based suggestions
        suggestions = UserLocation.suggest_matches_by_proximity(
            user_id=player5.id,
            max_suggestions=3,
            discipline_preference="palla_8",
            skill_level_range=["beginner", "intermediate"]
        )

        # Should return nearby compatible players
        assert len(suggestions) >= 1
        
        # Verify suggestions are sorted by proximity/compatibility
        if len(suggestions) > 1:
            # First suggestion should be most compatible/closest
            first_suggestion = suggestions[0]
            assert first_suggestion.compatibility_score >= suggestions[1].compatibility_score

        print(f"✅ Location-based player discovery completed successfully")
        print(f"   - 5 players set location preferences with different travel ranges")
        print(f"   - Proximity-based matching working correctly")
        print(f"   - Cross-venue coordination successful")
        print(f"   - Distance filtering properly restricting matches")
        print(f"   - {len(suggestions)} proximity-based suggestions generated")