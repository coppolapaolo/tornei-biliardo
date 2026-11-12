"""
Module: models/individual_match/availability_service.py
Purpose: Service layer for player availability (venue-based) and match requests

ADR-033: la disponibilità è solo per sala (UserLocationAvailability /
BilliardHall). Il vecchio modello a testo libero (PlayerAvailability) è stato
rimosso.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, time
from typing import List, Optional, Dict, Any

from flask_babel import gettext as _

from models.base import db, transactional, utc_now
from models.exceptions import ValidationError
from models.individual_match.models import MatchProposal
from models.location.models import BilliardHall, UserLocationAvailability
from models.status_enum import Discipline
from models.user.models import User
from models.notification.factory import NotificationFactory
from models.notification.models import NotificationType, NotificationPriority


def _format_time_range(start, end) -> Optional[str]:
    """Format a (start, end) time pair back to 'HH:MM-HH:MM', or None."""
    if start and end:
        return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
    return None


# Un orario: ore, e i minuti se ci sono, separati da due punti o da un punto.
_ORARIO = r"(\d{1,2})(?:[:.](\d{2}))?"
# Il trattino può essere quello della tastiera o uno dei due lunghi che il
# telefono sostituisce da solo; attorno, gli spazi che uno vuole.
_FASCIA = re.compile(rf"^\s*{_ORARIO}\s*[-–—]\s*{_ORARIO}\s*$")


def parse_fascia_oraria(testo: Optional[str]) -> Optional[tuple[time, time]]:
    """Legge «18:00-22:00» e le sue scritture ragionevoli.

    Vuoto vuol dire nessuna fascia. Ciò che non si capisce si rifiuta con una
    `ValidationError`: fino al 2026-11-10 veniva scartato in silenzio, e chi
    scriveva «18:00 - 22:00» — il suggerimento del campo, con gli spazi —
    vedeva «salvato» e poi il campo vuoto (#216).
    """
    if not testo or not testo.strip():
        return None
    trovato = _FASCIA.match(testo)
    try:
        if trovato is None:
            raise ValueError(testo)
        h1, m1, h2, m2 = (int(g) if g else 0 for g in trovato.groups())
        return time(h1, m1), time(h2, m2)
    except ValueError:
        raise ValidationError(
            _(
                "Non ho capito la fascia oraria «%(testo)s». Scrivila come "
                "18:00-22:00.",
                testo=testo.strip(),
            )
        ) from None


class AvailabilityService:
    """Service for managing player availability and match requests."""

    @staticmethod
    @transactional(domain="individual_match")
    def set_venue_availability(
        user_id: int,
        billiard_hall_id: int,
        is_available: bool = True,
        available_days: Optional[List[int]] = None,
        preferred_times: Optional[str] = None,
    ) -> UserLocationAvailability:
        """Set player availability for a specific venue."""
        fascia = parse_fascia_oraria(preferred_times)
        preferred_time_start, preferred_time_end = fascia or (None, None)

        # Check for existing availability
        existing = UserLocationAvailability.query.filter_by(
            user_id=user_id, billiard_hall_id=billiard_hall_id
        ).first()

        if existing:
            existing.is_available = is_available
            existing.available_days = (
                json.dumps(available_days) if available_days else None
            )
            existing.preferred_time_start = preferred_time_start
            existing.preferred_time_end = preferred_time_end
            existing.updated_at = utc_now()
        else:
            existing = UserLocationAvailability(
                user_id=user_id,
                billiard_hall_id=billiard_hall_id,
                is_available=is_available,
                available_days=json.dumps(available_days) if available_days else None,
                preferred_time_start=preferred_time_start,
                preferred_time_end=preferred_time_end,
            )
            db.session.add(existing)

        return existing

    @staticmethod
    def get_available_players_at_venue(
        billiard_hall_id: int, exclude_user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get players available at a specific venue."""
        query = (
            db.session.query(UserLocationAvailability, User, BilliardHall)
            .join(User, UserLocationAvailability.user_id == User.id)
            .join(
                BilliardHall,
                UserLocationAvailability.billiard_hall_id == BilliardHall.id,
            )
            .filter(
                UserLocationAvailability.billiard_hall_id == billiard_hall_id,
                UserLocationAvailability.is_available.is_(True),
            )
        )

        if exclude_user_id:
            query = query.filter(User.id != exclude_user_id)

        results = query.all()

        players = []
        for availability, user, venue in results:
            available_days = None
            if availability.available_days:
                try:
                    available_days = json.loads(availability.available_days)
                except (json.JSONDecodeError, TypeError):
                    available_days = None

            preferred_times_str = _format_time_range(
                availability.preferred_time_start, availability.preferred_time_end
            )

            players.append(
                {
                    "user_id": user.id,
                    "username": user.username,
                    "venue_id": venue.id,
                    "venue_name": venue.name,
                    "available_days": available_days,
                    "preferred_times": preferred_times_str,
                    "updated_at": availability.updated_at,
                }
            )

        return players

    @staticmethod
    def get_venues_with_available_players(
        exclude_user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Active venues that have at least one available player.

        Each item: venue_id, venue_name, city, latitude, longitude, players.
        Used by the discovery page; proximity ranking is applied by the caller
        (ADR-034) using ``utils.geo`` on this already-small working set.
        """
        venues = (
            db.session.query(BilliardHall)
            .join(
                UserLocationAvailability,
                UserLocationAvailability.billiard_hall_id == BilliardHall.id,
            )
            .filter(
                UserLocationAvailability.is_available.is_(True),
                BilliardHall.is_active.is_(True),
            )
            .distinct()
            .all()
        )

        result = []
        for venue in venues:
            players = AvailabilityService.get_available_players_at_venue(
                billiard_hall_id=venue.id, exclude_user_id=exclude_user_id
            )
            if players:
                result.append(
                    {
                        "venue_id": venue.id,
                        "venue_name": venue.name,
                        "city": venue.city,
                        "latitude": venue.latitude,
                        "longitude": venue.longitude,
                        "players": players,
                    }
                )
        return result

    @staticmethod
    def city_centroid_for(city: str):
        """Approximate origin = centroid of known venue coords in a city.

        Network-free fallback (ADR-034) when the user has no GPS fix but has a
        self-declared home city. Returns (lat, lng) or None.
        """
        from utils.geo import city_centroid

        if not city:
            return None
        rows = (
            db.session.query(BilliardHall.latitude, BilliardHall.longitude)
            .filter(
                BilliardHall.is_active.is_(True),
                db.func.lower(db.func.trim(BilliardHall.city)) == city.strip().lower(),
                BilliardHall.latitude.isnot(None),
                BilliardHall.longitude.isnot(None),
            )
            .all()
        )
        return city_centroid(rows)

    @staticmethod
    def get_players_who_played_at_location(
        location: str, exclude_user_id: Optional[int] = None
    ) -> List[int]:
        """Return ids of users who have played an individual match at a location.

        Used to pick eligible recipients for open proposals / availability
        notifications when the proposal carries a free-text ``location`` rather
        than a venue FK (ADR-033: there is no more location-based availability).
        """
        from models.individual_match.models import IndividualMatch

        rows = (
            db.session.query(IndividualMatch.player1_id, IndividualMatch.player2_id)
            .filter(IndividualMatch.location == location)
            .all()
        )

        user_ids = set()
        for player1_id, player2_id in rows:
            if player1_id:
                user_ids.add(player1_id)
            if player2_id:
                user_ids.add(player2_id)
        if exclude_user_id:
            user_ids.discard(exclude_user_id)
        if not user_ids:
            return []

        # La query sopra seleziona solo colonne id di IndividualMatch, quindi il
        # filtro soft-delete a livello di sessione del modello User NON si
        # applica: escludiamo esplicitamente gli account anonimizzati/cancellati
        # così non ricevono notifiche di proposta.
        from models.user.models import User

        active_ids = {
            uid
            for (uid,) in db.session.query(User.id)
            .filter(User.id.in_(user_ids), User.deleted_at.is_(None))
            .all()
        }
        return list(active_ids)

    @staticmethod
    @transactional(domain="individual_match")
    def notify_players_of_availability(
        user_id: int, location: str, message: Optional[str] = None
    ) -> int:
        """Notify players who have played at this location about availability."""
        user_ids = AvailabilityService.get_players_who_played_at_location(
            location, exclude_user_id=user_id
        )

        from flask_babel import gettext as _, lazy_gettext as _l

        requesting_user = db.session.get(User, user_id)
        requester_name = requesting_user.username if requesting_user else None

        def messaggio_predefinito() -> str:
            # Composto nella lingua di ciascun giocatore avvisato (ADR-062).
            return _(
                "%(nome)s è disponibile a giocare presso %(luogo)s",
                nome=requester_name or _("Un giocatore"),
                luogo=location,
            )

        notifications = NotificationFactory.create_bulk_notification(
            user_ids=user_ids,
            notification_type=NotificationType.MATCH_PROPOSAL,
            title=_l("Giocatore Disponibile"),
            # Un messaggio scritto dal giocatore passa com'è: non si traduce.
            message=message or messaggio_predefinito,
            priority=NotificationPriority.NORMAL,
            continue_on_error=True,
        )

        stats = NotificationFactory.get_notification_stats(notifications)
        return int(stats["successful"])

    @staticmethod
    def get_user_availability_preferences(user_id: int) -> Dict[str, Any]:
        """Get all (venue-based) availability preferences for a user."""
        venue_availabilities = (
            db.session.query(UserLocationAvailability, BilliardHall)
            .join(BilliardHall)
            .filter(
                UserLocationAvailability.user_id == user_id,
                UserLocationAvailability.is_available.is_(True),
            )
            .all()
        )

        venues = []
        for availability, venue in venue_availabilities:
            available_days = None
            if availability.available_days:
                try:
                    available_days = json.loads(availability.available_days)
                except (json.JSONDecodeError, TypeError):
                    available_days = None

            preferred_times_str = _format_time_range(
                availability.preferred_time_start, availability.preferred_time_end
            )

            venues.append(
                {
                    "id": availability.id,
                    "venue_id": venue.id,
                    "venue_name": venue.name,
                    "available_days": available_days,
                    "preferred_times": preferred_times_str,
                    "type": "venue",
                }
            )

        return {"venues": venues}

    @staticmethod
    @transactional(domain="individual_match")
    def remove_venue_availability(user_id: int, availability_id: int) -> bool:
        """Delete a venue-based availability record owned by the user.

        Returns True if a record was deleted, False if not found or not owned
        by the user (callers should treat False as a 404).
        """
        availability = UserLocationAvailability.query.filter_by(
            id=availability_id, user_id=user_id
        ).first()
        if availability is None:
            return False
        db.session.delete(availability)
        return True

    @staticmethod
    @transactional(domain="individual_match")
    def create_availability_based_match_request(
        requesting_user_id: int,
        target_user_id: int,
        location: str,
        proposed_datetime: Optional[datetime] = None,
        message: Optional[str] = None,
    ) -> MatchProposal:
        """Create a match request based on availability discovery."""
        from models.individual_match.services import IndividualMatchService
        from datetime import timedelta

        # Use a future datetime if none provided
        if proposed_datetime is None:
            proposed_datetime = utc_now() + timedelta(days=1)

        # Create direct match proposal to target user
        proposal = IndividualMatchService.create_direct_proposal(
            proposer_id=requesting_user_id,
            invited_user_ids=[target_user_id],
            location=location,
            scheduled_at=proposed_datetime,
            description=message or "Richiesta di match basata su disponibilità",
            discipline=Discipline.EIGHT_BALL.value,
            distance=7,  # Default
            is_race_to=True,
        )

        return proposal
