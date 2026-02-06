"""
Comprehensive tests for models/rating/services.py
Targeting 249 statements with 182 missed (27% coverage) for maximum impact toward 90% goal.
"""

from unittest.mock import Mock, patch
from datetime import datetime

from models.rating.services import RatingService, CategoryService, HandicapService
from models.rating.models import CategoryLevel, RatingSystem
from models.base import utc_now


class TestRatingService:
    """Comprehensive tests for RatingService."""

    @patch("models.rating.services.PlayerRating")
    @patch("models.rating.services.PlayerCategory")
    def test_get_user_rating_profile(self, mock_category_class, mock_rating_class):
        """Test get_user_rating_profile method."""
        mock_current_category = Mock()
        mock_category_class.get_user_current_category.return_value = (
            mock_current_category
        )

        mock_rating1 = Mock()
        mock_rating1.verified = True
        mock_rating2 = Mock()
        mock_rating2.verified = False
        mock_ratings = [mock_rating1, mock_rating2]
        mock_rating_class.query.filter_by.return_value.all.return_value = mock_ratings

        with patch.object(
            RatingService, "get_player_effective_category"
        ) as mock_effective:
            mock_effective.return_value = CategoryLevel.B
            mock_history = [Mock(), Mock()]
            mock_category_class.query.filter_by.return_value.order_by.return_value.all.return_value = (
                mock_history
            )

            result = RatingService.get_user_rating_profile(123)

            assert result["user_id"] == 123
            assert result["current_category"] == mock_current_category
            assert result["effective_category"] == CategoryLevel.B
            assert result["ratings"] == mock_ratings
            assert result["has_verified_rating"] is True

    @patch("models.rating.services.RatingSystem")
    @patch("models.rating.services.PlayerRating")
    def test_get_user_all_ratings(self, mock_rating_class, mock_rating_system):
        """Test get_user_all_ratings method."""
        mock_rating1 = Mock()
        mock_rating1.rating_system.value = "FARGO"
        mock_rating1.get_category_equivalent.return_value = CategoryLevel.A
        mock_rating1.last_updated = datetime(2024, 1, 15)
        mock_rating1.verified = True

        mock_ratings = [mock_rating1]
        mock_rating_class.query.filter_by.return_value.all.return_value = mock_ratings

        mock_rating_system.__iter__ = Mock(
            return_value=iter([Mock(value="FARGO"), Mock(value="ELO")])
        )

        result = RatingService.get_user_all_ratings(123)

        assert "ratings_by_system" in result
        assert result["total_systems"] == 1
        assert result["verified_count"] == 1

    @patch.object(RatingService, "update_player_rating")
    def test_update_user_rating(self, mock_update):
        """Test update_user_rating method."""
        mock_rating = Mock()
        mock_update.return_value = mock_rating

        result = RatingService.update_user_rating(
            user_id=123, rating_system=RatingSystem.FARGO, rating_value=600
        )

        assert result == mock_rating
        mock_update.assert_called_once_with(
            user_id=123,
            rating_system=RatingSystem.FARGO,
            new_rating=600,
            verified=False,
            external_id=None,
        )

    @patch("models.rating.services.db")
    @patch("models.rating.services.PlayerRating")
    def test_verify_rating_success(self, mock_rating_class, mock_db):
        """Test verify_rating method with valid rating."""
        mock_rating = Mock()
        mock_db.session.get.return_value = mock_rating

        result = RatingService.verify_rating(
            rating_id=456, verified_by_id=789, verified=True
        )

        assert result == mock_rating
        assert mock_rating.verified is True
        assert mock_rating.verified_by_id == 789
        mock_db.session.commit.assert_called_once()

    @patch("models.rating.services.abort")
    @patch("models.rating.services.db")
    def test_verify_rating_not_found(self, mock_db, mock_abort):
        """Test verify_rating method with non-existent rating."""
        mock_db.session.get.return_value = None

        RatingService.verify_rating(rating_id=999, verified_by_id=789)

        mock_abort.assert_called_once_with(404)

    @patch("models.rating.services.db")
    @patch("models.rating.services.PlayerRating")
    @patch("models.rating.services.PlayerCategory")
    def test_get_management_overview(
        self, mock_category_class, mock_rating_class, mock_db
    ):
        """Test get_management_overview method."""
        mock_unverified = [Mock(), Mock(), Mock()]
        mock_rating_class.query.filter_by.return_value.order_by.return_value.all.return_value = (
            mock_unverified
        )

        mock_users_without_cats = [(123,), (456,)]
        mock_db.session.query.return_value.outerjoin.return_value.filter.return_value.distinct.return_value.all.return_value = (
            mock_users_without_cats
        )

        mock_recent = [Mock() for _ in range(5)]
        mock_rating_class.query.order_by.return_value.limit.return_value.all.return_value = (
            mock_recent
        )

        result = RatingService.get_management_overview()

        assert result["unverified_ratings"] == mock_unverified
        assert result["users_without_categories"] == [123, 456]
        assert result["recent_updates"] == mock_recent
        assert result["total_unverified"] == 3

    @patch("models.rating.services.HandicapRule")
    @patch("models.rating.services.PlayerCategory")
    @patch("models.rating.services.PlayerRating")
    @patch("models.rating.services.RatingSystem")
    @patch("models.rating.services.CategoryLevel")
    @patch("models.rating.services.datetime")
    def test_get_system_statistics(
        self,
        mock_datetime,
        mock_category_level,
        mock_rating_system,
        mock_rating_class,
        mock_category_class,
        mock_handicap_rule,
    ):
        """Test get_system_statistics method."""
        mock_now = datetime(2024, 1, 15, 12, 0, 0)
        mock_utc_now.return_value = mock_now

        mock_fargo_system = Mock()
        mock_fargo_system.value = "FARGO"
        mock_rating_system.__iter__ = Mock(return_value=iter([mock_fargo_system]))

        mock_fargo_rating = Mock()
        mock_fargo_rating.rating_value = 600
        mock_fargo_rating.verified = True
        mock_fargo_rating.last_updated = datetime(2024, 1, 10, 12, 0, 0)

        mock_rating_class.query.filter_by.return_value.all.return_value = [
            mock_fargo_rating
        ]

        mock_category_a = Mock()
        mock_category_a.value = "A"
        mock_category_level.__iter__ = Mock(return_value=iter([mock_category_a]))

        mock_category_class.query.filter_by.return_value.count.return_value = 5
        mock_handicap_rule.query.filter_by.return_value.count.return_value = 2

        result = RatingService.get_system_statistics()

        assert "rating_systems" in result
        assert "category_distribution" in result
        fargo_stats = result["rating_systems"]["FARGO"]
        assert fargo_stats["total_players"] == 1
        assert fargo_stats["verified_players"] == 1

    @patch("models.rating.services.db")
    @patch("models.rating.services.PlayerCategory")
    def test_assign_player_category(self, mock_category_class, mock_db):
        """Test assign_player_category method."""
        mock_existing = Mock()
        mock_category_class.query.filter_by.return_value.all.return_value = [
            mock_existing
        ]

        with patch(
            "models.rating.services.PlayerCategory"
        ) as mock_category_constructor:
            mock_new_category = Mock()
            mock_category_constructor.return_value = mock_new_category

            result = RatingService.assign_player_category(
                user_id=123, category=CategoryLevel.B, assigned_by_id=456
            )

            mock_existing.expire_category.assert_called_once()
            mock_db.session.add.assert_called_once_with(mock_new_category)
            mock_db.session.commit.assert_called_once()
            assert result == mock_new_category

    @patch("models.rating.services.db")
    @patch("models.rating.services.PlayerRating")
    def test_update_player_rating_existing(self, mock_rating_class, mock_db):
        """Test update_player_rating with existing rating."""
        mock_existing_rating = Mock()
        mock_rating_class.get_user_rating.return_value = mock_existing_rating

        result = RatingService.update_player_rating(
            user_id=123,
            rating_system=RatingSystem.FARGO,
            new_rating=650,
            verified=True,
            verified_by_id=456,
        )

        assert result == mock_existing_rating
        mock_existing_rating.update_rating.assert_called_once_with(650)
        assert mock_existing_rating.verified is True
        mock_db.session.commit.assert_called_once()

    @patch("models.rating.services.PlayerRating")
    @patch("models.rating.services.PlayerCategory")
    def test_get_player_effective_category_assigned(
        self, mock_category_class, mock_rating_class
    ):
        """Test get_player_effective_category with assigned category."""
        mock_assigned_category = Mock()
        mock_assigned_category.category = CategoryLevel.A
        mock_category_class.get_user_current_category.return_value = (
            mock_assigned_category
        )

        result = RatingService.get_player_effective_category(123)

        assert result == CategoryLevel.A

    @patch("models.rating.services.PlayerRating")
    @patch("models.rating.services.PlayerCategory")
    def test_get_player_effective_category_from_rating(
        self, mock_category_class, mock_rating_class
    ):
        """Test get_player_effective_category from rating when no assigned category."""
        mock_category_class.get_user_current_category.return_value = None

        def mock_get_user_rating_side_effect(user_id, rating_system):
            if rating_system == RatingSystem.FARGO:
                return None
            elif rating_system == RatingSystem.ELO:
                mock_rating = Mock()
                mock_rating.get_category_equivalent.return_value = CategoryLevel.B
                return mock_rating
            else:
                return None

        mock_rating_class.get_user_rating.side_effect = mock_get_user_rating_side_effect

        result = RatingService.get_player_effective_category(123)

        assert result == CategoryLevel.B

    @patch("models.rating.services.HandicapService")
    @patch("models.rating.services.db")
    @patch("models.rating.services.HandicapRule")
    def test_calculate_match_handicap_with_rule(
        self, mock_rule_class, mock_db, mock_handicap_service
    ):
        """Test calculate_match_handicap with specific rule."""
        mock_rule = Mock()
        mock_db.session.get.return_value = mock_rule

        mock_category_result = {"handicap": 2, "method": "category"}
        mock_handicap_service._calculate_category_handicap.return_value = (
            mock_category_result
        )

        result = RatingService.calculate_match_handicap(123, 456, handicap_rule_id=789)

        assert result == mock_category_result
        mock_handicap_service._calculate_category_handicap.assert_called_once_with(
            123, 456, mock_rule
        )


class TestCategoryService:
    """Tests for CategoryService."""

    @patch.object(RatingService, "get_player_effective_category")
    @patch("models.rating.services.PlayerCategory")
    def test_get_user_category_info(self, mock_category_class, mock_effective):
        """Test get_user_category_info method."""
        mock_current_category = Mock()
        mock_category_class.get_user_current_category.return_value = (
            mock_current_category
        )

        mock_history = [Mock(), Mock()]
        mock_category_class.query.filter_by.return_value.order_by.return_value.all.return_value = (
            mock_history
        )

        mock_effective.return_value = CategoryLevel.B

        result = CategoryService.get_user_category_info(123)

        assert result["current_category"] == mock_current_category
        assert result["effective_category"] == CategoryLevel.B
        assert result["is_rating_derived"] is False
        assert result["has_category_history"] is True

    @patch.object(RatingService, "assign_player_category")
    def test_assign_category(self, mock_assign):
        """Test assign_category method."""
        mock_category = Mock()
        mock_assign.return_value = mock_category

        result = CategoryService.assign_category(
            user_id=123, category=CategoryLevel.A, assigned_by_id=456
        )

        assert result == mock_category

    @patch("models.rating.services.db")
    def test_expire_category(self, mock_db):
        """Test expire_category method."""
        mock_category = Mock()
        mock_db.session.get.return_value = mock_category

        CategoryService.expire_category(456)

        mock_category.expire_category.assert_called_once()
        mock_db.session.commit.assert_called_once()


class TestHandicapService:
    """Tests for HandicapService."""

    @patch.object(RatingService, "calculate_match_handicap")
    def test_calculate_handicap(self, mock_calculate):
        """Test calculate_handicap method."""
        mock_result = {"handicap": 2, "method": "category"}
        mock_calculate.return_value = mock_result

        result = HandicapService.calculate_handicap(123, 456, rule_id=789)

        assert result == mock_result

    @patch("models.rating.services.HandicapRule")
    def test_get_all_rules(self, mock_rule_class):
        """Test get_all_rules method."""
        mock_active_rules = [Mock(), Mock()]
        mock_inactive_rules = [Mock()]

        def mock_filter_by_side_effect(**kwargs):
            if kwargs.get("is_active") is True:
                mock_query = Mock()
                mock_query.all.return_value = mock_active_rules
                return mock_query
            else:
                mock_query = Mock()
                mock_query.all.return_value = mock_inactive_rules
                return mock_query

        mock_rule_class.query.filter_by.side_effect = mock_filter_by_side_effect

        result = HandicapService.get_all_rules()

        assert result["active_rules"] == mock_active_rules
        assert result["total_rules"] == 3

    @patch("models.rating.services.db")
    def test_update_rule_status(self, mock_db):
        """Test update_rule_status method."""
        mock_rule = Mock()
        mock_db.session.get.return_value = mock_rule

        result = HandicapService.update_rule_status(123, is_active=False)

        assert result == mock_rule
        assert mock_rule.is_active is False

    @patch.object(RatingService, "get_player_effective_category")
    def test_calculate_category_handicap_no_categories(self, mock_effective):
        """Test _calculate_category_handicap with missing categories."""
        mock_effective.side_effect = [None, CategoryLevel.B]
        mock_rule = Mock()

        result = HandicapService._calculate_category_handicap(123, 456, mock_rule)

        expected = {
            "player1_handicap": 0,
            "player2_handicap": 0,
            "handicap": 0,
            "method": "no_categories",
            "explanation": "Category information not available",
        }
        assert result == expected

    @patch.object(RatingService, "get_player_effective_category")
    def test_calculate_category_handicap_same_category(self, mock_effective):
        """Test _calculate_category_handicap with same categories."""
        mock_effective.return_value = CategoryLevel.B
        mock_rule = Mock()

        result = HandicapService._calculate_category_handicap(123, 456, mock_rule)

        expected = {
            "player1_handicap": 0,
            "player2_handicap": 0,
            "handicap": 0,
            "method": "same_category",
            "explanation": "Both players are category B",
        }
        assert result == expected

    @patch("models.rating.services.PlayerRating")
    def test_calculate_rating_handicap_no_ratings(self, mock_rating_class):
        """Test _calculate_rating_handicap with no ratings available."""
        mock_rating_class.get_user_rating.return_value = None
        mock_rule = Mock()

        result = HandicapService._calculate_rating_handicap(123, 456, mock_rule)

        expected = {
            "player1_handicap": 0,
            "player2_handicap": 0,
            "handicap": 0,
            "method": "no_ratings",
            "explanation": "No rating information available",
        }
        assert result == expected

    @patch("models.rating.services.db")
    @patch("models.rating.services.CategoryHandicapRule")
    @patch("models.rating.services.RatingHandicapRule")
    @patch("models.rating.services.HandicapRule")
    def test_create_handicap_rule(
        self, mock_rule_class, mock_rating_rule_class, mock_category_rule_class, mock_db
    ):
        """Test create_handicap_rule method."""
        mock_rule = Mock()
        mock_rule.id = 123
        mock_rule_class.return_value = mock_rule

        category_rules = [
            {"higher_category": "A", "lower_category": "B", "handicap_value": 1}
        ]
        rating_rules = [
            {
                "rating_system": "FARGO",
                "rating_difference_threshold": 50,
                "handicap_per_point": 100,
            }
        ]

        result = HandicapService.create_handicap_rule(
            name="Test Rule",
            description="Test Description",
            category_rules=category_rules,
            rating_rules=rating_rules,
        )

        assert result == mock_rule
        mock_db.session.add.assert_called()
        mock_db.session.flush.assert_called_once()
        mock_db.session.commit.assert_called_once()

    @patch("models.rating.services.db")
    @patch("models.rating.services.HandicapRule")
    def test_create_standard_handicap_rule(self, mock_rule_class, mock_db):
        """Test create_standard_handicap_rule method."""
        mock_rule = Mock()
        mock_rule.id = 456
        mock_rule_class.return_value = mock_rule

        result = HandicapService.create_standard_handicap_rule()

        assert result == mock_rule
        mock_db.session.add.assert_called()
        mock_db.session.commit.assert_called_once()

    @patch("models.rating.services.PlayerCategory")
    @patch("models.rating.services.PlayerRating")
    def test_get_player_ratings_summary(self, mock_rating_class, mock_category_class):
        """Test get_player_ratings_summary method."""
        mock_rating = Mock()
        mock_rating.rating_system.value = "FARGO"
        mock_rating.rating_value = 600
        mock_rating.games_played = 10
        mock_rating.verified = True
        mock_rating.last_updated = datetime(2024, 1, 15)
        mock_rating.get_category_equivalent.return_value = CategoryLevel.A

        mock_rating_class.query.filter_by.return_value.all.return_value = [mock_rating]

        mock_category = Mock()
        mock_category.category = CategoryLevel.A
        mock_category_class.get_user_current_category.return_value = mock_category

        with patch.object(
            RatingService, "get_player_effective_category"
        ) as mock_effective:
            mock_effective.return_value = CategoryLevel.A

            result = HandicapService.get_player_ratings_summary(123)

            assert result["assigned_category"] == "A"
            assert result["effective_category"] == "A"
            assert "FARGO" in result["ratings"]
            assert result["ratings"]["FARGO"]["value"] == 600

    @patch.object(RatingService, "update_player_rating")
    def test_bulk_import_fargo_ratings(self, mock_update):
        """Test bulk_import_fargo_ratings method."""
        fargo_data = [
            {"user_id": 123, "fargo_rating": 600, "fargo_id": "FARGO123"},
            {"user_id": 456, "fargo_rating": 550, "fargo_id": "FARGO456"},
            {"user_id": None, "fargo_rating": 500},  # Invalid data
        ]

        result = HandicapService.bulk_import_fargo_ratings(fargo_data)

        assert result == 2  # Only 2 valid entries
        assert mock_update.call_count == 2

    @patch.object(RatingService, "assign_player_category")
    @patch("models.rating.services.PlayerRating")
    @patch("models.rating.services.PlayerCategory")
    @patch("models.rating.services.db")
    def test_auto_assign_categories_from_ratings(
        self, mock_db, mock_category_class, mock_rating_class, mock_assign
    ):
        """Test auto_assign_categories_from_ratings method."""
        # Mock users with ratings
        mock_db.session.query.return_value.distinct.return_value.all.return_value = [
            (123,),
            (456,),
        ]

        # Mock existing categories
        mock_category_class.get_user_current_category.side_effect = [
            None,
            Mock(),
        ]  # First user has no category, second has category

        # Mock rating lookup
        mock_rating = Mock()
        mock_rating.rating_value = 600
        mock_rating.get_category_equivalent.return_value = CategoryLevel.A
        mock_rating_class.get_user_rating.side_effect = [
            mock_rating,
            None,
            None,
        ]  # Only FARGO rating for first user

        result = HandicapService.auto_assign_categories_from_ratings()

        assert result == 1  # Only one user was assigned
        mock_assign.assert_called_once()
