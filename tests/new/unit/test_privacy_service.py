"""Unit tests for user privacy service.

Tests the PrivacyService class methods for managing user privacy settings
and hidden elements (matches, inscriptions, campionati).
"""

import pytest
from datetime import datetime
import uuid

from models.user.privacy_models import (
    UserPrivacySetting,
    HiddenMatch,
    HiddenInscription,
    HiddenCampionato,
)
from models.user.privacy_service import PrivacyService


@pytest.fixture
def test_player(db_session):
    """Create a test player."""
    from models import User
    from models.user.role_enum import UserRole

    unique_id = str(uuid.uuid4())[:8]
    player = User(
        username=f"privacy_test_{unique_id}",
        email=f"privacy_{unique_id}@test.com",
        role=UserRole.PLAYER.value,
    )
    player.set_password("test123")
    db_session.add(player)
    db_session.commit()
    return player


@pytest.fixture
def test_gara(db_session):
    """Create a test gara."""
    from models import Gara
    from models.status_enum import GaraStatus

    unique_id = str(uuid.uuid4())[:8]
    gara = Gara(
        name=f"Test Gara {unique_id}",
        number=1,
        date=datetime.utcnow().date(),
        discipline="palla_8",
        distance=5,
        is_race_to=True,
        status=GaraStatus.INSCRIPTION.value,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


@pytest.fixture
def test_campionato(db_session):
    """Create a test campionato."""
    from models import Campionato

    unique_id = str(uuid.uuid4())[:8]
    campionato = Campionato(
        name=f"Test Campionato {unique_id}",
    )
    db_session.add(campionato)
    db_session.commit()
    return campionato


@pytest.fixture
def test_match(db_session, test_player, test_gara):
    """Create a test match."""
    from models import Match

    # Create another player for the match
    from models import User
    from models.user.role_enum import UserRole

    unique_id = str(uuid.uuid4())[:8]
    player2 = User(
        username=f"opponent_{unique_id}",
        email=f"opponent_{unique_id}@test.com",
        role=UserRole.PLAYER.value,
    )
    player2.set_password("test123")
    db_session.add(player2)
    db_session.commit()

    match = Match(
        gara_id=test_gara.id,
        player1_id=test_player.id,
        player2_id=player2.id,
        round_number=1,
    )
    db_session.add(match)
    db_session.commit()
    return match


@pytest.fixture
def test_inscription(db_session, test_player, test_gara):
    """Create a test inscription."""
    from models import Inscription

    inscription = Inscription(
        user_id=test_player.id,
        gara_id=test_gara.id,
    )
    db_session.add(inscription)
    db_session.commit()
    return inscription


class TestPrivacyServiceSettings:
    """Tests for privacy settings CRUD operations."""

    def test_get_privacy_settings_creates_default_when_missing(self, db_session, test_player):
        """Should create default settings with all fields visible."""
        settings = PrivacyService.get_privacy_settings(test_player.id)

        assert settings is not None
        assert settings.user_id == test_player.id
        assert settings.show_email is True
        assert settings.show_phone is True
        assert settings.show_statistics is True
        assert settings.show_recent_matches is True
        assert settings.show_classifications is True
        assert settings.show_challenge_stats is True

    def test_get_privacy_settings_returns_existing(self, db_session, test_player):
        """Should return existing settings without creating new ones."""
        # Create custom settings
        existing = UserPrivacySetting(
            user_id=test_player.id,
            show_email=False,
            show_phone=False,
            show_statistics=True,
            show_recent_matches=True,
            show_classifications=False,
            show_challenge_stats=True,
        )
        db_session.add(existing)
        db_session.commit()

        settings = PrivacyService.get_privacy_settings(test_player.id)

        assert settings.id == existing.id
        assert settings.show_email is False
        assert settings.show_phone is False
        assert settings.show_classifications is False

    def test_update_privacy_settings(self, db_session, test_player):
        """Should update existing settings."""
        # Ensure settings exist
        PrivacyService.get_privacy_settings(test_player.id)

        updated = PrivacyService.update_privacy_settings(
            user_id=test_player.id,
            show_email=False,
            show_statistics=False,
        )

        assert updated.show_email is False
        assert updated.show_statistics is False
        # Other fields should remain at default
        assert updated.show_phone is True
        assert updated.show_recent_matches is True

    def test_update_privacy_settings_creates_if_missing(self, db_session, test_player):
        """Should create settings if they don't exist on update."""
        updated = PrivacyService.update_privacy_settings(
            user_id=test_player.id,
            show_email=False,
        )

        assert updated is not None
        assert updated.show_email is False


class TestPrivacyServiceHideMatch:
    """Tests for hiding/showing individual matches."""

    def test_hide_match_success(self, db_session, test_player, test_match):
        """Should hide a match the user participated in."""
        result = PrivacyService.hide_match(test_player.id, test_match.id)

        # Returns HiddenMatch instance
        assert result is not None
        assert isinstance(result, HiddenMatch)
        hidden = HiddenMatch.query.filter_by(
            user_id=test_player.id, match_id=test_match.id
        ).first()
        assert hidden is not None

    def test_hide_match_already_hidden(self, db_session, test_player, test_match):
        """Should return existing HiddenMatch if already hidden (idempotent)."""
        existing = HiddenMatch(user_id=test_player.id, match_id=test_match.id)
        db_session.add(existing)
        db_session.commit()

        result = PrivacyService.hide_match(test_player.id, test_match.id)

        # Returns the existing record
        assert result is not None
        assert result.id == existing.id

    def test_hide_match_not_participant_raises_error(self, db_session, test_player, test_gara):
        """Should raise ValueError if user is not a participant in the match."""
        from models import User, Match
        from models.user.role_enum import UserRole

        # Create two other players for a match that doesn't include test_player
        unique_id = str(uuid.uuid4())[:8]
        other1 = User(
            username=f"other1_{unique_id}",
            email=f"other1_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        other2 = User(
            username=f"other2_{unique_id}",
            email=f"other2_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        other1.set_password("test123")
        other2.set_password("test123")
        db_session.add_all([other1, other2])
        db_session.commit()

        other_match = Match(
            gara_id=test_gara.id,
            player1_id=other1.id,
            player2_id=other2.id,
            round_number=1,
        )
        db_session.add(other_match)
        db_session.commit()

        with pytest.raises(ValueError, match="Only match participants can hide a match"):
            PrivacyService.hide_match(test_player.id, other_match.id)

    def test_show_match_success(self, db_session, test_player, test_match):
        """Should unhide a previously hidden match."""
        db_session.add(HiddenMatch(user_id=test_player.id, match_id=test_match.id))
        db_session.commit()

        result = PrivacyService.show_match(test_player.id, test_match.id)

        assert result is True
        hidden = HiddenMatch.query.filter_by(
            user_id=test_player.id, match_id=test_match.id
        ).first()
        assert hidden is None

    def test_show_match_not_hidden(self, db_session, test_player, test_match):
        """Should return False if not hidden (nothing to unhide)."""
        result = PrivacyService.show_match(test_player.id, test_match.id)

        # Returns False when nothing was deleted
        assert result is False


class TestPrivacyServiceHideInscription:
    """Tests for hiding/showing inscriptions."""

    def test_hide_inscription_success(self, db_session, test_player, test_inscription):
        """Should hide an inscription the user owns."""
        result = PrivacyService.hide_inscription(test_player.id, test_inscription.id)

        # Returns HiddenInscription instance
        assert result is not None
        assert isinstance(result, HiddenInscription)
        hidden = HiddenInscription.query.filter_by(
            user_id=test_player.id, inscription_id=test_inscription.id
        ).first()
        assert hidden is not None

    def test_hide_inscription_not_owner_raises_error(self, db_session, test_player, test_gara):
        """Should raise ValueError if user doesn't own the inscription."""
        from models import User, Inscription
        from models.user.role_enum import UserRole

        unique_id = str(uuid.uuid4())[:8]
        other = User(
            username=f"other_{unique_id}",
            email=f"other_{unique_id}@test.com",
            role=UserRole.PLAYER.value,
        )
        other.set_password("test123")
        db_session.add(other)
        db_session.commit()

        other_inscription = Inscription(
            user_id=other.id,
            gara_id=test_gara.id,
        )
        db_session.add(other_inscription)
        db_session.commit()

        with pytest.raises(ValueError, match="Only the inscribed user can hide an inscription"):
            PrivacyService.hide_inscription(test_player.id, other_inscription.id)

    def test_show_inscription_success(self, db_session, test_player, test_inscription):
        """Should unhide a previously hidden inscription."""
        db_session.add(
            HiddenInscription(user_id=test_player.id, inscription_id=test_inscription.id)
        )
        db_session.commit()

        result = PrivacyService.show_inscription(test_player.id, test_inscription.id)

        assert result is True
        hidden = HiddenInscription.query.filter_by(
            user_id=test_player.id, inscription_id=test_inscription.id
        ).first()
        assert hidden is None


class TestPrivacyServiceHideCampionato:
    """Tests for hiding/showing campionati."""

    def test_hide_campionato_success(
        self, db_session, test_player, test_campionato, test_gara, test_inscription
    ):
        """Should hide a campionato the user participates in."""
        # Link gara to campionato
        test_gara.campionato_id = test_campionato.id
        db_session.commit()

        result = PrivacyService.hide_campionato(test_player.id, test_campionato.id)

        # Returns HiddenCampionato instance
        assert result is not None
        assert isinstance(result, HiddenCampionato)
        hidden = HiddenCampionato.query.filter_by(
            user_id=test_player.id, campionato_id=test_campionato.id
        ).first()
        assert hidden is not None

    def test_show_campionato_success(
        self, db_session, test_player, test_campionato, test_gara, test_inscription
    ):
        """Should unhide a previously hidden campionato."""
        test_gara.campionato_id = test_campionato.id
        db_session.add(
            HiddenCampionato(user_id=test_player.id, campionato_id=test_campionato.id)
        )
        db_session.commit()

        result = PrivacyService.show_campionato(test_player.id, test_campionato.id)

        assert result is True
        hidden = HiddenCampionato.query.filter_by(
            user_id=test_player.id, campionato_id=test_campionato.id
        ).first()
        assert hidden is None


class TestPrivacyServiceFiltering:
    """Tests for filtering visible matches and inscriptions."""

    def test_filter_visible_matches_owner_sees_all(
        self, db_session, test_player, test_match
    ):
        """Owner should see all their matches including hidden ones."""
        db_session.add(HiddenMatch(user_id=test_player.id, match_id=test_match.id))
        db_session.commit()

        visible = PrivacyService.filter_visible_matches(
            user_id=test_player.id,
            viewer_id=test_player.id,  # Viewing own profile
            matches=[test_match],
            is_admin=False,
        )

        assert len(visible) == 1
        assert test_match in visible

    def test_filter_visible_matches_admin_sees_all(
        self, db_session, test_player, test_match
    ):
        """Admin should see all matches including hidden ones."""
        db_session.add(HiddenMatch(user_id=test_player.id, match_id=test_match.id))
        db_session.commit()

        visible = PrivacyService.filter_visible_matches(
            user_id=test_player.id,
            viewer_id=999,  # Different user
            matches=[test_match],
            is_admin=True,  # But is admin
        )

        assert len(visible) == 1

    def test_filter_visible_matches_hides_from_others(
        self, db_session, test_player, test_match
    ):
        """Other users should not see hidden matches."""
        db_session.add(HiddenMatch(user_id=test_player.id, match_id=test_match.id))
        db_session.commit()

        visible = PrivacyService.filter_visible_matches(
            user_id=test_player.id,
            viewer_id=test_player.id + 100,  # Different user
            matches=[test_match],
            is_admin=False,
        )

        assert len(visible) == 0

    def test_filter_visible_inscriptions_owner_sees_all(
        self, db_session, test_player, test_inscription
    ):
        """Owner should see all their inscriptions including hidden ones."""
        db_session.add(
            HiddenInscription(user_id=test_player.id, inscription_id=test_inscription.id)
        )
        db_session.commit()

        visible = PrivacyService.filter_visible_inscriptions(
            user_id=test_player.id,
            viewer_id=test_player.id,
            inscriptions=[test_inscription],
            is_admin=False,
        )

        assert len(visible) == 1

    def test_filter_visible_inscriptions_hides_from_others(
        self, db_session, test_player, test_inscription
    ):
        """Other users should not see hidden inscriptions."""
        db_session.add(
            HiddenInscription(user_id=test_player.id, inscription_id=test_inscription.id)
        )
        db_session.commit()

        visible = PrivacyService.filter_visible_inscriptions(
            user_id=test_player.id,
            viewer_id=test_player.id + 100,
            inscriptions=[test_inscription],
            is_admin=False,
        )

        assert len(visible) == 0


class TestPrivacyServiceHelpers:
    """Tests for helper methods."""

    def test_get_hidden_ids_returns_all_hidden_elements(
        self, db_session, test_player, test_match, test_inscription, test_campionato, test_gara
    ):
        """Should return dict with all hidden IDs."""
        test_gara.campionato_id = test_campionato.id

        db_session.add(HiddenMatch(user_id=test_player.id, match_id=test_match.id))
        db_session.add(
            HiddenInscription(user_id=test_player.id, inscription_id=test_inscription.id)
        )
        db_session.add(
            HiddenCampionato(user_id=test_player.id, campionato_id=test_campionato.id)
        )
        db_session.commit()

        hidden = PrivacyService.get_hidden_ids(test_player.id)

        assert test_match.id in hidden["matches"]
        assert test_inscription.id in hidden["inscriptions"]
        assert test_campionato.id in hidden["campionati"]

    def test_is_match_hidden_returns_correct_status(
        self, db_session, test_player, test_match
    ):
        """Should correctly identify hidden vs visible matches."""
        db_session.add(HiddenMatch(user_id=test_player.id, match_id=test_match.id))
        db_session.commit()

        assert PrivacyService.is_match_hidden(test_player.id, test_match.id) is True
        assert PrivacyService.is_match_hidden(test_player.id, 99999) is False

    def test_is_inscription_hidden_returns_correct_status(
        self, db_session, test_player, test_inscription
    ):
        """Should correctly identify hidden vs visible inscriptions."""
        db_session.add(
            HiddenInscription(user_id=test_player.id, inscription_id=test_inscription.id)
        )
        db_session.commit()

        assert PrivacyService.is_inscription_hidden(test_player.id, test_inscription.id) is True
        assert PrivacyService.is_inscription_hidden(test_player.id, 99999) is False

    def test_is_campionato_hidden_returns_correct_status(
        self, db_session, test_player, test_campionato
    ):
        """Should correctly identify hidden vs visible campionati."""
        db_session.add(
            HiddenCampionato(user_id=test_player.id, campionato_id=test_campionato.id)
        )
        db_session.commit()

        assert PrivacyService.is_campionato_hidden(test_player.id, test_campionato.id) is True
        assert PrivacyService.is_campionato_hidden(test_player.id, 99999) is False
