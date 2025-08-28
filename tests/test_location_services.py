"""
Test module for models/location/services.py
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, time
from models.location.services import LocationService
from models.location.models import (
    BilliardHall,
    DayOfWeek,
)


class TestLocationService:
    """Test cases for LocationService class."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        pass

    def test_create_billiard_hall(self):
        """Test creating a billiard hall successfully."""
        with patch("models.location.services.db") as mock_db:
            mock_hall = Mock()

            # Mock the BilliardHall constructor
            with patch(
                "models.location.services.BilliardHall", return_value=mock_hall
            ) as mock_hall_class:
                result = LocationService.create_billiard_hall(
                    name="Test Hall",
                    address="123 Test St",
                    city="Test City",
                    postal_code="12345",
                    country="Italy",
                    phone="123-456-7890",
                    email="test@example.com",
                    website="http://test.com",
                    number_of_tables=5,
                    hourly_rate=10.0,
                    added_by_id=1,
                )

                # Verify the hall was created with correct parameters
                mock_hall_class.assert_called_once_with(
                    name="Test Hall",
                    address="123 Test St",
                    city="Test City",
                    postal_code="12345",
                    country="Italy",
                    phone="123-456-7890",
                    email="test@example.com",
                    website="http://test.com",
                    number_of_tables=5,
                    hourly_rate=10.0,
                    added_by_id=1,
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_hall)
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result == mock_hall

    def test_create_billiard_hall_with_table_types_and_amenities(self):
        """Test creating a billiard hall with table types and amenities."""
        with patch("models.location.services.db") as mock_db:
            mock_hall = Mock()

            # Mock the BilliardHall constructor
            with patch(
                "models.location.services.BilliardHall", return_value=mock_hall
            ) as mock_hall_class:
                result = LocationService.create_billiard_hall(
                    name="Test Hall",
                    table_types=["9-foot", "10-foot"],
                    amenities=["wifi", "bar"],
                )

                # Verify the hall was created
                mock_hall_class.assert_called_once_with(
                    name="Test Hall",
                    address=None,
                    city=None,
                    postal_code=None,
                    country="Italy",
                    phone=None,
                    email=None,
                    website=None,
                    number_of_tables=None,
                    hourly_rate=None,
                    added_by_id=None,
                )

                # Verify table types and amenities were set
                mock_hall.set_table_types.assert_called_once_with(["9-foot", "10-foot"])
                mock_hall.set_amenities.assert_called_once_with(["wifi", "bar"])

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_hall)
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result == mock_hall

    def test_get_nearby_halls(self):
        """Test getting nearby halls."""
        mock_halls = [Mock(), Mock(), Mock()]

        with patch("models.location.services.BilliardHall") as mock_hall_class:
            # Mock the query chain
            mock_query = Mock()
            mock_filtered_query1 = Mock()
            mock_filtered_query2 = Mock()
            mock_filtered_query3 = Mock()
            mock_ordered_query = Mock()

            # Set up the chain of return values
            mock_hall_class.query.filter_by.return_value = mock_query
            mock_query.filter.return_value = mock_filtered_query1
            mock_filtered_query1.filter_by.return_value = mock_filtered_query2
            mock_filtered_query2.filter_by.return_value = mock_filtered_query3
            mock_filtered_query3.order_by.return_value = mock_ordered_query
            mock_ordered_query.all.return_value = mock_halls

            result = LocationService.get_nearby_halls(
                city="Test City", country="Italy", verified_only=True
            )

            # Verify the query chain was called correctly
            mock_hall_class.query.filter_by.assert_called_once_with(is_active=True)
            mock_query.filter.assert_called_once()
            mock_filtered_query1.filter_by.assert_called_once_with(country="Italy")
            mock_filtered_query2.filter_by.assert_called_once_with(verified=True)
            mock_filtered_query3.order_by.assert_called_once()
            mock_ordered_query.all.assert_called_once()

            # Verify the result
            assert result == mock_halls

    def test_set_user_availability_new(self):
        """Test setting user availability for a new availability record."""
        mock_availability = Mock()

        with patch("models.location.services.db") as mock_db:
            # Mock query to return None (no existing availability)
            with patch(
                "models.location.services.UserLocationAvailability"
            ) as mock_availability_class:
                mock_query = Mock()
                mock_query.first.return_value = None
                mock_availability_class.query.filter_by.return_value = mock_query
                mock_availability_class.return_value = mock_availability

                result = LocationService.set_user_availability(
                    user_id=1,
                    billiard_hall_id=2,
                    is_available=True,
                    available_days=[DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY],
                    preferred_time_start="09:00",
                    preferred_time_end="17:00",
                    advance_notice_hours=24,
                    notify_on_proposals=True,
                )

                # Verify the availability was created with correct parameters
                mock_availability_class.assert_called_once_with(
                    user_id=1,
                    billiard_hall_id=2,
                    is_available=True,
                    advance_notice_hours=24,
                    notify_on_proposals=True,
                )

                # Verify available days were set
                mock_availability.set_available_days.assert_called_once_with(
                    [DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY]
                )

                # Verify time preferences were set
                assert mock_availability.preferred_time_start == time(9, 0)
                assert mock_availability.preferred_time_end == time(17, 0)

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_availability)
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result == mock_availability

    def test_set_user_availability_existing(self):
        """Test updating user availability for an existing availability record."""
        mock_availability = Mock()
        mock_availability.is_available = False
        mock_availability.advance_notice_hours = 12
        mock_availability.notify_on_proposals = False

        with patch("models.location.services.db") as mock_db:
            # Mock query to return existing availability
            with patch(
                "models.location.services.UserLocationAvailability"
            ) as mock_availability_class:
                mock_query = Mock()
                mock_query.first.return_value = mock_availability
                mock_availability_class.query.filter_by.return_value = mock_query

                result = LocationService.set_user_availability(
                    user_id=1,
                    billiard_hall_id=2,
                    is_available=True,
                    advance_notice_hours=24,
                    notify_on_proposals=True,
                )

                # Verify the availability was updated
                assert mock_availability.is_available is True
                assert mock_availability.advance_notice_hours == 24
                assert mock_availability.notify_on_proposals is True

                # Verify database operations
                mock_db.session.add.assert_not_called()  # No new record added
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result == mock_availability

    def test_get_user_locations(self):
        """Test getting user locations."""
        mock_availability1 = Mock()
        mock_availability2 = Mock()
        mock_hall1 = Mock()
        mock_hall2 = Mock()

        mock_availability1.billiard_hall = mock_hall1
        mock_availability2.billiard_hall = mock_hall2

        # Mock the availability summary
        mock_availability1.get_availability_summary.return_value = {
            "matches_played_here": 5
        }
        mock_availability2.get_availability_summary.return_value = {
            "matches_played_here": 3
        }

        with patch(
            "models.location.services.UserLocationAvailability"
        ) as mock_availability_class:
            # Mock the query chain
            mock_query = Mock()
            mock_filtered_query1 = Mock()
            mock_filtered_query2 = Mock()

            # Set up the chain of return values
            mock_availability_class.query.filter_by.return_value = mock_query
            mock_query.join.return_value = mock_filtered_query1
            mock_filtered_query1.filter.return_value = mock_filtered_query2
            mock_filtered_query2.all.return_value = [
                mock_availability1,
                mock_availability2,
            ]

            result = LocationService.get_user_locations(user_id=1)

            # Verify the query chain was called correctly
            mock_availability_class.query.filter_by.assert_called_once_with(
                user_id=1, is_available=True
            )
            mock_query.join.assert_called_once_with(BilliardHall)
            mock_filtered_query1.filter.assert_called_once()

            # Verify the result
            assert len(result) == 2
            assert result[0]["billiard_hall"] == mock_hall1
            assert result[0]["availability"] == {"matches_played_here": 5}
            assert result[1]["billiard_hall"] == mock_hall2
            assert result[1]["availability"] == {"matches_played_here": 3}

    def test_find_available_players(self):
        """Test finding available players."""
        mock_availability1 = Mock()
        mock_availability2 = Mock()
        mock_user1 = Mock()
        mock_user2 = Mock()

        mock_availability1.user = mock_user1
        mock_availability2.user = mock_user2
        mock_availability1.user_id = 1
        mock_availability2.user_id = 2
        mock_availability1.matches_played_here = 10
        mock_availability2.matches_played_here = 5
        mock_availability1.last_played_at = datetime(2023, 1, 1)
        mock_availability2.last_played_at = datetime(2023, 1, 2)

        # Mock the is_available_at method
        mock_availability1.is_available_at.return_value = True
        mock_availability2.is_available_at.return_value = True

        with patch(
            "models.location.services.UserLocationAvailability"
        ) as mock_availability_class:
            # Mock the query chain
            mock_query = Mock()
            mock_filtered_query1 = Mock()
            mock_filtered_query2 = Mock()

            # Set up the chain of return values
            mock_availability_class.query.filter_by.return_value = mock_query
            mock_query.join.return_value = mock_filtered_query1
            mock_filtered_query1.filter.return_value = mock_filtered_query2
            mock_filtered_query2.all.return_value = [
                mock_availability1,
                mock_availability2,
            ]

            result = LocationService.find_available_players(
                billiard_hall_id=1,
                proposed_datetime=datetime(2023, 1, 1, 14, 0),
                exclude_user_id=3,
            )

            # Verify the query chain was called correctly
            mock_availability_class.query.filter_by.assert_called_once_with(
                billiard_hall_id=1, is_available=True
            )
            mock_query.join.assert_called_once_with(BilliardHall)
            mock_filtered_query1.filter.assert_called_once()

            # Verify the result is sorted by experience (matches_played_here)
            assert len(result) == 2
            assert result[0]["user"] == mock_user1
            assert result[0]["matches_played_here"] == 10
            assert result[1]["user"] == mock_user2
            assert result[1]["matches_played_here"] == 5

    def test_get_location_statistics(self):
        """Test getting location statistics."""
        mock_hall = Mock()
        mock_hall.id = 1
        mock_hall.name = "Test Hall"
        mock_hall.get_table_types.return_value = ["9-foot"]
        mock_hall.get_amenities.return_value = ["wifi"]

        mock_review1 = Mock()
        mock_review1.rating = 4
        mock_review2 = Mock()
        mock_review2.rating = 5

        # Create a list of reviews that can be iterated over
        mock_reviews = [mock_review1, mock_review2]

        with patch("models.location.services.db") as mock_db:
            # Mock db.session.get to return the hall
            mock_db.session.get.return_value = mock_hall

            # Mock UserLocationAvailability query
            with patch(
                "models.location.services.UserLocationAvailability"
            ) as mock_user_location_class:
                mock_user_location_query = Mock()
                mock_user_location_query.count.return_value = 5
                mock_user_location_class.query.filter_by.return_value = (
                    mock_user_location_query
                )

                # Mock IndividualMatch query
                with patch(
                    "models.individual_match.models.IndividualMatch"
                ) as mock_individual_match_class:
                    mock_individual_match_query = Mock()
                    mock_individual_match_query.count.return_value = 10
                    mock_individual_match_class.query.filter_by.return_value = (
                        mock_individual_match_query
                    )

                    # Mock LocationReview query - properly mock the filter_by call
                    # with all parameters
                    with patch(
                        "models.location.services.LocationReview"
                    ) as mock_location_review_class:
                        mock_filtered_query1 = Mock()
                        mock_filtered_query1.all.return_value = mock_reviews

                        # Set up the filter_by chain with all parameters
                        mock_location_review_class.query.filter_by.return_value = (
                            mock_filtered_query1
                        )

                        result = LocationService.get_location_statistics(
                            billiard_hall_id=1
                        )

                        # Verify database operations
                        mock_db.session.get.assert_called_once_with(
                            BilliardHall, 1
                        )
                        mock_user_location_class.query.filter_by.\
                            assert_called_once_with(
                                billiard_hall_id=1,
                                is_available=True
                            )
                        mock_individual_match_class.query.filter_by.\
                            assert_called_once_with(
                                location="Test Hall"
                            )
                        mock_location_review_class.query.filter_by.\
                            assert_called_once_with(
                                billiard_hall_id=1,
                                is_approved=True,
                                is_hidden=False
                            )

                        # Verify the result
                        assert result["billiard_hall"] == mock_hall
                        assert result["active_users_count"] == 5
                        assert result["total_matches_played"] == 10
                        assert result["reviews_count"] == 2
                        assert result["average_rating"] == 4.5
                        assert result["table_types"] == ["9-foot"]
                        assert result["amenities"] == ["wifi"]

    def test_add_location_review_new(self):
        """Test adding a new location review."""
        with patch("models.location.services.db") as mock_db:
            # Mock query to return None (no existing review)
            with patch("models.location.services.LocationReview") as mock_review_class:
                mock_query = Mock()
                mock_query.first.return_value = None
                mock_review_class.query.filter_by.return_value = mock_query

                mock_review = Mock()
                mock_review_class.return_value = mock_review

                result = LocationService.add_location_review(
                    user_id=1,
                    billiard_hall_id=2,
                    rating=5,
                    title="Great Hall",
                    comment="Excellent facilities",
                    table_quality=5,
                    atmosphere=4,
                    service=5,
                    value_for_money=4,
                )

                # Verify the review was created with correct parameters
                mock_review_class.assert_called_once_with(
                    user_id=1,
                    billiard_hall_id=2,
                    rating=5,
                    title="Great Hall",
                    comment="Excellent facilities",
                    table_quality=5,
                    atmosphere=4,
                    service=5,
                    value_for_money=4,
                )

                # Verify database operations
                mock_db.session.add.assert_called_once_with(mock_review)
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result == mock_review

    def test_add_location_review_existing(self):
        """Test updating an existing location review."""
        mock_review = Mock()
        mock_review.rating = 3
        mock_review.title = "Old Title"
        mock_review.comment = "Old comment"
        mock_review.table_quality = 3
        mock_review.atmosphere = 3
        mock_review.service = 3
        mock_review.value_for_money = 3

        with patch("models.location.services.db") as mock_db:
            # Mock query to return existing review
            with patch("models.location.services.LocationReview") as mock_review_class:
                mock_query = Mock()
                mock_query.first.return_value = mock_review
                mock_review_class.query.filter_by.return_value = mock_query

                result = LocationService.add_location_review(
                    user_id=1,
                    billiard_hall_id=2,
                    rating=5,
                    title="Great Hall",
                    comment="Excellent facilities",
                    table_quality=5,
                    atmosphere=4,
                    service=5,
                    value_for_money=4,
                )

                # Verify the review was updated
                assert mock_review.rating == 5
                assert mock_review.title == "Great Hall"
                assert mock_review.comment == "Excellent facilities"
                assert mock_review.table_quality == 5
                assert mock_review.atmosphere == 4
                assert mock_review.service == 5
                assert mock_review.value_for_money == 4
                assert mock_review.updated_at is not None

                # Verify database operations
                mock_db.session.add.assert_not_called()  # No new record added
                mock_db.session.commit.assert_called_once()

                # Verify the result
                assert result == mock_review

    def test_add_location_review_invalid_rating(self):
        """Test adding a location review with invalid rating."""
        # Should raise ValueError for rating < 1
        with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
            LocationService.add_location_review(user_id=1, billiard_hall_id=2, rating=0)

        # Should raise ValueError for rating > 5
        with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
            LocationService.add_location_review(user_id=1, billiard_hall_id=2, rating=6)

    def test_get_location_reviews(self):
        """Test getting location reviews."""
        mock_reviews = [Mock(), Mock(), Mock()]

        with patch("models.location.services.LocationReview") as mock_review_class:
            # Mock the query chain
            mock_query = Mock()
            mock_filtered_query = Mock()
            mock_ordered_query = Mock()

            # Set up the chain of return values
            mock_review_class.query.filter_by.return_value = mock_query
            mock_query.filter_by.return_value = mock_filtered_query
            mock_filtered_query.order_by.return_value = mock_ordered_query
            mock_ordered_query.all.return_value = mock_reviews

            result = LocationService.get_location_reviews(
                billiard_hall_id=1, approved_only=True
            )

            # Verify the query chain was called correctly
            mock_review_class.query.filter_by.assert_called_once_with(
                billiard_hall_id=1
            )
            mock_query.filter_by.assert_called_once_with(
                is_approved=True, is_hidden=False
            )
            mock_filtered_query.order_by.assert_called_once()
            mock_ordered_query.all.assert_called_once()

            # Verify the result
            assert result == mock_reviews

    def test_update_billiard_hall(self):
        """Test updating billiard hall information."""
        mock_hall = Mock()
        mock_hall.id = 1

        with patch("models.location.services.db") as mock_db:
            # Mock db.session.get to return the hall
            mock_db.session.get.return_value = mock_hall

            result = LocationService.update_billiard_hall(
                hall_id=1,
                name="Updated Hall",
                address="456 Updated St",
                city="Updated City",
                postal_code="67890",
                country="Updated Country",
                phone="987-654-3210",
                email="updated@example.com",
                website="http://updated.com",
                number_of_tables=10,
                hourly_rate=15.0,
                is_active=False,
                verified=True,
                table_types=["7-foot", "8-foot"],
                amenities=["wifi", "bar", "restaurant"],
                business_hours={"monday": "09:00-22:00"},
            )

            # Verify database operation
            mock_db.session.get.assert_called_once_with(BilliardHall, 1)

            # Verify the hall was updated with simple fields
            assert mock_hall.name == "Updated Hall"
            assert mock_hall.address == "456 Updated St"
            assert mock_hall.city == "Updated City"
            assert mock_hall.postal_code == "67890"
            assert mock_hall.country == "Updated Country"
            assert mock_hall.phone == "987-654-3210"
            assert mock_hall.email == "updated@example.com"
            assert mock_hall.website == "http://updated.com"
            assert mock_hall.number_of_tables == 10
            assert mock_hall.hourly_rate == 15.0
            assert mock_hall.is_active is False
            assert mock_hall.verified is True

            # Verify complex fields were set
            mock_hall.set_table_types.assert_called_once_with(["7-foot", "8-foot"])
            mock_hall.set_amenities.assert_called_once_with(
                ["wifi", "bar", "restaurant"]
            )
            mock_hall.set_business_hours.assert_called_once_with(
                {"monday": "09:00-22:00"}
            )

            # Verify database operations
            mock_db.session.commit.assert_called_once()

            # Verify the result
            assert result == mock_hall

    def test_search_billiard_halls(self):
        """Test searching billiard halls."""
        mock_halls = [Mock(), Mock(), Mock()]

        with patch("models.location.services.BilliardHall") as mock_hall_class:
            with patch("models.location.services.db") as mock_db:
                # Mock the query chain
                mock_query = Mock()
                mock_filtered_query1 = Mock()
                mock_filtered_query2 = Mock()
                mock_filtered_query3 = Mock()
                mock_ordered_query = Mock()

                # Set up the chain of return values
                mock_hall_class.query.filter.return_value = mock_query
                mock_query.filter.return_value = mock_filtered_query1
                mock_filtered_query1.filter_by.return_value = mock_filtered_query2
                mock_filtered_query2.filter_by.return_value = mock_filtered_query3
                mock_filtered_query3.order_by.return_value = mock_ordered_query
                mock_ordered_query.all.return_value = mock_halls

                # Mock the ilike method on the mock_db.or_ function
                mock_db.or_ = Mock()

                result = LocationService.search_billiard_halls(
                    query="Test", city="Test City", country="Italy", verified_only=True
                )

                # Verify the query chain was called correctly
                mock_hall_class.query.filter.assert_called_once()
                mock_query.filter.assert_called_once()
                mock_filtered_query1.filter_by.assert_called_once_with(country="Italy")
                mock_filtered_query2.filter_by.assert_called_once_with(verified=True)
                mock_filtered_query3.order_by.assert_called_once()
                mock_ordered_query.all.assert_called_once()

                # Verify the result
                assert result == mock_halls
