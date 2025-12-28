"""
Module: models/user/privacy_service.py
Purpose: Service layer for user privacy settings with @transactional decorator
"""

from __future__ import annotations

from typing import Optional, Dict, Set, List, TYPE_CHECKING

from ..base import db
from ..transaction.manager import transactional
from .privacy_models import (
    UserPrivacySetting,
    HiddenMatch,
    HiddenInscription,
    HiddenCampionato,
)

if TYPE_CHECKING:
    from ..match.models import Match
    from ..competition.models import Inscription
    from ..campionato.models import Campionato


class PrivacyService:
    """Service for managing user privacy settings and hidden elements.

    All methods use @transactional for automatic commit/rollback.
    """

    # ========== Privacy Settings CRUD ==========

    @staticmethod
    @transactional(domain="user")
    def get_privacy_settings(user_id: int) -> UserPrivacySetting:
        """Get or create privacy settings for user.

        Args:
            user_id: User ID to get settings for

        Returns:
            UserPrivacySetting instance
        """
        return UserPrivacySetting.get_or_create(user_id)

    @staticmethod
    @transactional(domain="user")
    def update_privacy_settings(
        user_id: int,
        show_email: Optional[bool] = None,
        show_phone: Optional[bool] = None,
        show_statistics: Optional[bool] = None,
        show_recent_matches: Optional[bool] = None,
        show_classifications: Optional[bool] = None,
        show_challenge_stats: Optional[bool] = None,
    ) -> UserPrivacySetting:
        """Update privacy settings for user.

        Only updates fields that are explicitly passed (not None).

        Args:
            user_id: User ID to update settings for
            show_*: Boolean flags for each privacy setting

        Returns:
            Updated UserPrivacySetting instance
        """
        settings = UserPrivacySetting.get_or_create(user_id)

        if show_email is not None:
            settings.show_email = show_email
        if show_phone is not None:
            settings.show_phone = show_phone
        if show_statistics is not None:
            settings.show_statistics = show_statistics
        if show_recent_matches is not None:
            settings.show_recent_matches = show_recent_matches
        if show_classifications is not None:
            settings.show_classifications = show_classifications
        if show_challenge_stats is not None:
            settings.show_challenge_stats = show_challenge_stats

        return settings

    @staticmethod
    def can_view_field(
        viewer_user_id: Optional[int], target_user_id: int, field: str
    ) -> bool:
        """Check if viewer can see a specific field on target's profile.

        Rules:
        - User can always see their own data
        - Others respect privacy settings
        - No settings = default to visible (backward compatibility)

        Args:
            viewer_user_id: ID of user viewing (None for anonymous/guest)
            target_user_id: ID of user whose profile is being viewed
            field: Field name to check (email, phone, statistics, etc.)

        Returns:
            True if viewer can see the field
        """
        # Self-view: always allowed
        if viewer_user_id is not None and viewer_user_id == target_user_id:
            return True

        # Get privacy settings
        settings = UserPrivacySetting.query.filter_by(user_id=target_user_id).first()

        # No settings = default to visible (backward compatibility)
        if not settings:
            return True

        field_map = {
            "email": settings.show_email,
            "phone": settings.show_phone,
            "statistics": settings.show_statistics,
            "recent_matches": settings.show_recent_matches,
            "classifications": settings.show_classifications,
            "challenge_stats": settings.show_challenge_stats,
        }

        return field_map.get(field, True)

    # ========== Hidden Match Methods ==========

    @staticmethod
    @transactional(domain="user")
    def hide_match(user_id: int, match_id: int) -> HiddenMatch:
        """Hide a match from user's public profile.

        Args:
            user_id: User ID hiding the match (must be participant)
            match_id: Match ID to hide

        Returns:
            HiddenMatch instance

        Raises:
            ValueError: If user is not a participant in the match
        """
        from ..match.models import Match

        match = db.session.get(Match, match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        # Verify user is a participant
        if match.player1_id != user_id and match.player2_id != user_id:
            raise ValueError("Only match participants can hide a match")

        # Check if already hidden
        existing = HiddenMatch.query.filter_by(
            user_id=user_id, match_id=match_id
        ).first()
        if existing:
            return existing

        hidden = HiddenMatch(user_id=user_id, match_id=match_id)
        db.session.add(hidden)
        return hidden

    @staticmethod
    @transactional(domain="user")
    def show_match(user_id: int, match_id: int) -> bool:
        """Unhide a match from user's public profile.

        Args:
            user_id: User ID showing the match
            match_id: Match ID to show

        Returns:
            True if match was unhidden, False if it wasn't hidden
        """
        hidden = HiddenMatch.query.filter_by(
            user_id=user_id, match_id=match_id
        ).first()
        if hidden:
            db.session.delete(hidden)
            return True
        return False

    # ========== Hidden Inscription Methods ==========

    @staticmethod
    @transactional(domain="user")
    def hide_inscription(user_id: int, inscription_id: int) -> HiddenInscription:
        """Hide an inscription (gara) from user's public profile.

        Args:
            user_id: User ID hiding the inscription (must be the inscribed user)
            inscription_id: Inscription ID to hide

        Returns:
            HiddenInscription instance

        Raises:
            ValueError: If user doesn't own this inscription
        """
        from ..competition.models import Inscription

        inscription = db.session.get(Inscription, inscription_id)
        if not inscription:
            raise ValueError(f"Inscription {inscription_id} not found")

        # Verify user owns this inscription
        if inscription.user_id != user_id:
            raise ValueError("Only the inscribed user can hide an inscription")

        # Check if already hidden
        existing = HiddenInscription.query.filter_by(
            user_id=user_id, inscription_id=inscription_id
        ).first()
        if existing:
            return existing

        hidden = HiddenInscription(user_id=user_id, inscription_id=inscription_id)
        db.session.add(hidden)
        return hidden

    @staticmethod
    @transactional(domain="user")
    def show_inscription(user_id: int, inscription_id: int) -> bool:
        """Unhide an inscription from user's public profile.

        Args:
            user_id: User ID showing the inscription
            inscription_id: Inscription ID to show

        Returns:
            True if inscription was unhidden, False if it wasn't hidden
        """
        hidden = HiddenInscription.query.filter_by(
            user_id=user_id, inscription_id=inscription_id
        ).first()
        if hidden:
            db.session.delete(hidden)
            return True
        return False

    # ========== Hidden Campionato Methods ==========

    @staticmethod
    @transactional(domain="user")
    def hide_campionato(user_id: int, campionato_id: int) -> HiddenCampionato:
        """Hide a campionato from user's public profile.

        Hides all gare and matches within the campionato for this user.

        Args:
            user_id: User ID hiding the campionato (must have participated)
            campionato_id: Campionato ID to hide

        Returns:
            HiddenCampionato instance

        Raises:
            ValueError: If campionato not found
        """
        from ..campionato.models import Campionato

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise ValueError(f"Campionato {campionato_id} not found")

        # Check if already hidden
        existing = HiddenCampionato.query.filter_by(
            user_id=user_id, campionato_id=campionato_id
        ).first()
        if existing:
            return existing

        hidden = HiddenCampionato(user_id=user_id, campionato_id=campionato_id)
        db.session.add(hidden)
        return hidden

    @staticmethod
    @transactional(domain="user")
    def show_campionato(user_id: int, campionato_id: int) -> bool:
        """Unhide a campionato from user's public profile.

        Args:
            user_id: User ID showing the campionato
            campionato_id: Campionato ID to show

        Returns:
            True if campionato was unhidden, False if it wasn't hidden
        """
        hidden = HiddenCampionato.query.filter_by(
            user_id=user_id, campionato_id=campionato_id
        ).first()
        if hidden:
            db.session.delete(hidden)
            return True
        return False

    # ========== Query Methods ==========

    @staticmethod
    def get_hidden_ids(user_id: int) -> Dict[str, Set[int]]:
        """Get all hidden element IDs for a user.

        Args:
            user_id: User ID to get hidden elements for

        Returns:
            Dict with keys 'matches', 'inscriptions', 'campionati'
            containing sets of hidden IDs
        """
        hidden_matches = HiddenMatch.query.filter_by(user_id=user_id).all()
        hidden_inscriptions = HiddenInscription.query.filter_by(user_id=user_id).all()
        hidden_campionati = HiddenCampionato.query.filter_by(user_id=user_id).all()

        return {
            "matches": {h.match_id for h in hidden_matches},
            "inscriptions": {h.inscription_id for h in hidden_inscriptions},
            "campionati": {h.campionato_id for h in hidden_campionati},
        }

    @staticmethod
    def is_match_hidden(user_id: int, match_id: int) -> bool:
        """Check if a match is hidden by user.

        Args:
            user_id: User ID to check
            match_id: Match ID to check

        Returns:
            True if match is hidden
        """
        return HiddenMatch.query.filter_by(
            user_id=user_id, match_id=match_id
        ).first() is not None

    @staticmethod
    def is_inscription_hidden(user_id: int, inscription_id: int) -> bool:
        """Check if an inscription is hidden by user.

        Args:
            user_id: User ID to check
            inscription_id: Inscription ID to check

        Returns:
            True if inscription is hidden
        """
        return HiddenInscription.query.filter_by(
            user_id=user_id, inscription_id=inscription_id
        ).first() is not None

    @staticmethod
    def is_campionato_hidden(user_id: int, campionato_id: int) -> bool:
        """Check if a campionato is hidden by user.

        Args:
            user_id: User ID to check
            campionato_id: Campionato ID to check

        Returns:
            True if campionato is hidden
        """
        return HiddenCampionato.query.filter_by(
            user_id=user_id, campionato_id=campionato_id
        ).first() is not None

    @staticmethod
    def filter_visible_matches(
        user_id: int,
        viewer_id: Optional[int],
        matches: List["Match"],
        is_admin: bool = False,
    ) -> List["Match"]:
        """Filter matches to only those visible to the viewer.

        Args:
            user_id: User whose profile is being viewed (owner of hidden settings)
            viewer_id: User viewing the profile (None for guest)
            matches: List of matches to filter
            is_admin: If True, bypass hiding (show all)

        Returns:
            Filtered list of visible matches
        """
        # Admin sees everything
        if is_admin:
            return matches

        # Owner sees everything (including their hidden items)
        if viewer_id == user_id:
            return matches

        # Get hidden IDs
        hidden_ids = PrivacyService.get_hidden_ids(user_id)
        hidden_match_ids = hidden_ids["matches"]
        hidden_campionato_ids = hidden_ids["campionati"]

        # Filter out hidden matches
        visible = []
        for match in matches:
            # Skip if match is directly hidden
            if match.id in hidden_match_ids:
                continue

            # Skip if match belongs to hidden campionato
            if match.gara and match.gara.campionato_id in hidden_campionato_ids:
                continue

            visible.append(match)

        return visible

    @staticmethod
    def filter_visible_inscriptions(
        user_id: int,
        viewer_id: Optional[int],
        inscriptions: List["Inscription"],
        is_admin: bool = False,
    ) -> List["Inscription"]:
        """Filter inscriptions to only those visible to the viewer.

        Args:
            user_id: User whose profile is being viewed
            viewer_id: User viewing the profile (None for guest)
            inscriptions: List of inscriptions to filter
            is_admin: If True, bypass hiding (show all)

        Returns:
            Filtered list of visible inscriptions
        """
        # Admin sees everything
        if is_admin:
            return inscriptions

        # Owner sees everything
        if viewer_id == user_id:
            return inscriptions

        # Get hidden IDs
        hidden_ids = PrivacyService.get_hidden_ids(user_id)
        hidden_inscription_ids = hidden_ids["inscriptions"]
        hidden_campionato_ids = hidden_ids["campionati"]

        # Filter out hidden inscriptions
        visible = []
        for inscription in inscriptions:
            # Skip if inscription is directly hidden
            if inscription.id in hidden_inscription_ids:
                continue

            # Skip if inscription belongs to hidden campionato
            if inscription.gara and inscription.gara.campionato_id in hidden_campionato_ids:
                continue

            visible.append(inscription)

        return visible
