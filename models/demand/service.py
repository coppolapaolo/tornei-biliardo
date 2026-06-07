"""Service del segnale-domanda (ADR-036).

Crea richieste geolocalizzate, notifica i director sul fronte di salita ≥ soglia
(con cooldown anti-nag) e consuma le richieste quando una gara apre vicino.
Tutta la prossimità riusa ``utils.geo`` (bounding-box + haversine) e il
centroide città di ``AvailabilityService`` (ADR-034).
"""

from __future__ import annotations

from datetime import timedelta
from typing import List, Optional, Tuple

from flask_babel import gettext as _

from models.base import db, utc_now
from models.transaction.manager import transactional
from models.demand.models import DemandSignal, DemandSignalStatus
from utils.geo import haversine_km, bounding_box, clamp_radius

# Tarature (ADR-036 Open Items §4) — affinare sui dati reali.
DEMAND_THRESHOLD = 6
DEMAND_EXPIRY_DAYS = 60
DEMAND_COOLDOWN_DAYS = 7
DEFAULT_DIRECTOR_RADIUS_KM = 30


class DemandSignalService:
    """Gestione dei segnali di domanda → director (ADR-036)."""

    # ── creazione ────────────────────────────────────────────────────────────

    @staticmethod
    def resolve_origin(
        user, near_lat=None, near_lng=None
    ) -> Optional[Tuple[float, float]]:
        """Origine della richiesta: GPS effimero se valido, else centroide
        ``home_city`` (ADR-034). Ritorna ``(lat, lng)`` o ``None``."""
        try:
            if near_lat is not None and near_lng is not None:
                return (float(near_lat), float(near_lng))
        except (TypeError, ValueError):
            pass

        from models.individual_match.availability_service import AvailabilityService

        return AvailabilityService.city_centroid_for(getattr(user, "home_city", None))

    @staticmethod
    @transactional(domain="demand")
    def create_signal(
        user_id: int,
        near_lat=None,
        near_lng=None,
        city: Optional[str] = None,
    ) -> DemandSignal:
        """Crea un segnale di domanda per ``user_id`` e valuta i trigger.

        Solleva ``ValueError`` se non si riesce a determinare una posizione
        (né GPS né ``home_city`` geocodificabile).
        """
        from models.user.models import User

        user = db.session.get(User, user_id)
        if user is None:
            raise ValueError(f"Utente {user_id} non trovato")

        origin = DemandSignalService.resolve_origin(user, near_lat, near_lng)
        if origin is None:
            raise ValueError(
                "Posizione non determinabile: concedi il GPS o imposta la "
                "tua città nel profilo."
            )

        lat, lng = origin
        signal = DemandSignal(
            user_id=user_id,
            latitude=lat,
            longitude=lng,
            city=(city or getattr(user, "home_city", None)),
            status=DemandSignalStatus.ACTIVE,
            expires_at=utc_now() + timedelta(days=DEMAND_EXPIRY_DAYS),
        )
        db.session.add(signal)
        db.session.flush()

        covered = DemandSignalService._notify_directors_rising_edge(signal)
        # Zona senza director (ADR-036 open item 2): se nessun director copre il
        # punto e la domanda locale tocca la soglia, avvisa gli admin (dove
        # reclutare/promuovere un director).
        if not covered:
            DemandSignalService._maybe_notify_admins_no_director(signal)
        return signal

    # ── query di prossimità ────────────────────────────────────────────────

    @staticmethod
    def _active_signals_within(
        lat: float, lng: float, radius_km: float
    ) -> List[DemandSignal]:
        """Segnali attivi e non scaduti entro ``radius_km`` da ``(lat, lng)``."""
        min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius_km)
        now = utc_now()
        candidates = DemandSignal.query.filter(
            DemandSignal.status == DemandSignalStatus.ACTIVE,
            DemandSignal.expires_at > now,
            DemandSignal.latitude.between(min_lat, max_lat),
            DemandSignal.longitude.between(min_lng, max_lng),
        ).all()
        return [
            s
            for s in candidates
            if haversine_km(lat, lng, s.latitude, s.longitude) <= radius_km
        ]

    @staticmethod
    def count_active_within(lat: float, lng: float, radius_km: float) -> int:
        """Numero di segnali attivi entro il raggio (per il conteggio zona)."""
        return len(DemandSignalService._active_signals_within(lat, lng, radius_km))

    # ── trigger director (fronte di salita ≥ soglia) ─────────────────────────

    @staticmethod
    def _notify_directors_rising_edge(new_signal: DemandSignal) -> bool:
        """Notifica i director la cui zona raggiunge ESATTAMENTE la soglia con
        questo nuovo segnale (crossing), nel rispetto del cooldown.

        Ritorna ``True`` se almeno un director **copre** il punto del segnale
        (a prescindere dall'invio), così il chiamante sa se la zona ha un
        responsabile (vedi segnale-admin).
        """
        from models.user.models import User
        from models.user.role_enum import UserRole

        directors = User.query.filter(User.role == UserRole.DIRECTOR.value).all()

        now = utc_now()
        cooldown = timedelta(days=DEMAND_COOLDOWN_DAYS)
        covered = False

        for director in directors:
            origin = DemandSignalService._director_origin(director)
            if origin is None:
                continue
            radius = clamp_radius(
                director.signal_radius_km or DEFAULT_DIRECTOR_RADIUS_KM
            )
            d_lat, d_lng = origin
            # Il nuovo segnale deve cadere nella zona del director.
            if (
                haversine_km(d_lat, d_lng, new_signal.latitude, new_signal.longitude)
                > radius
            ):
                continue

            covered = True
            count_after = DemandSignalService.count_active_within(d_lat, d_lng, radius)
            # Fronte di salita: notifica solo al crossing esatto della soglia.
            if count_after != DEMAND_THRESHOLD:
                continue
            # Cooldown anti-nag.
            if director.signal_notified_at and (
                now - director.signal_notified_at < cooldown
            ):
                continue

            DemandSignalService._notify_director_threshold(director, count_after)
            director.signal_notified_at = now

        return covered

    @staticmethod
    def evaluate_zone_for_new_director(director_id: int) -> bool:
        """Re-eval alla promozione player→director (ADR-036 open item 1).

        Se la zona del neo-director ha già ≥ soglia richieste attive, invia una
        notifica una-tantum (rispetta il cooldown). Pensata per essere chiamata
        *dentro* la transazione di promozione. Ritorna True se ha notificato.
        """
        from models.user.models import User

        director = db.session.get(User, director_id)
        if director is None:
            return False

        origin = DemandSignalService._director_origin(director)
        if origin is None:
            return False

        radius = clamp_radius(director.signal_radius_km or DEFAULT_DIRECTOR_RADIUS_KM)
        count = DemandSignalService.count_active_within(origin[0], origin[1], radius)
        if count < DEMAND_THRESHOLD:
            return False

        now = utc_now()
        cooldown = timedelta(days=DEMAND_COOLDOWN_DAYS)
        if director.signal_notified_at and (
            now - director.signal_notified_at < cooldown
        ):
            return False

        DemandSignalService._notify_director_threshold(director, count)
        director.signal_notified_at = now
        return True

    @staticmethod
    def _maybe_notify_admins_no_director(new_signal: DemandSignal) -> bool:
        """Avvisa gli admin se la domanda locale tocca la soglia in una zona
        senza director (ADR-036 open item 2). Crossing-only per limitare lo spam.
        """
        count = DemandSignalService.count_active_within(
            new_signal.latitude, new_signal.longitude, DEFAULT_DIRECTOR_RADIUS_KM
        )
        if count != DEMAND_THRESHOLD:
            return False

        from models.user.models import User
        from models.user.role_enum import UserRole
        from models.notification.factory import NotificationFactory
        from models.notification.models import NotificationType, NotificationPriority

        admin_ids = [
            u.id for u in User.query.filter(User.role == UserRole.ADMIN.value).all()
        ]
        if not admin_ids:
            return False

        zone = (new_signal.city or "").strip()
        if zone:
            message = _(
                "%(count)s giocatori vorrebbero una gara a %(city)s, una zona "
                "senza un director. Valuta di reclutarne o promuoverne uno.",
                count=count,
                city=zone,
            )
        else:
            message = _(
                "%(count)s giocatori vorrebbero una gara in una zona senza un "
                "director. Valuta di reclutarne o promuoverne uno.",
                count=count,
            )

        NotificationFactory.create_bulk_notification(
            user_ids=admin_ids,
            notification_type=NotificationType.DEMAND_ZONE_NO_DIRECTOR,
            title=_("Domanda in una zona senza director"),
            message=message,
            priority=NotificationPriority.NORMAL,
        )
        return True

    @staticmethod
    def _director_origin(director) -> Optional[Tuple[float, float]]:
        """Centroide delle sale della ``home_city`` del director (ADR-034)."""
        from models.individual_match.availability_service import AvailabilityService

        return AvailabilityService.city_centroid_for(
            getattr(director, "home_city", None)
        )

    @staticmethod
    def _notify_director_threshold(director, count: int) -> None:
        """Notifica persistente azionabile (§11) al director."""
        from models.notification.services import NotificationService
        from models.notification.models import NotificationType, NotificationPriority

        try:
            NotificationService.create_notification(
                user_id=director.id,
                notification_type=NotificationType.DEMAND_THRESHOLD_REACHED,
                title=_("C'è domanda nella tua zona!"),
                message=_(
                    "%(count)s giocatori vorrebbero una gara vicino a te. "
                    "Potrebbe essere il momento di organizzarne una.",
                    count=count,
                ),
                priority=NotificationPriority.HIGH,
            )
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Impossibile notificare il director %s (soglia domanda)",
                director.id,
            )

    # ── consumo (gara aperta vicino) ─────────────────────────────────────────

    @staticmethod
    @transactional(domain="demand")
    def consume_signals_for_gara(
        gara_id: int,
        venue_lat: float,
        venue_lng: float,
        radius_km: Optional[int] = None,
    ) -> int:
        """Consuma i segnali attivi entro il raggio della sala della gara e
        notifica i giocatori ("gara aperta vicino a te"). Idempotente.

        Ritorna il numero di segnali consumati.
        """
        radius = clamp_radius(radius_km or DEFAULT_DIRECTOR_RADIUS_KM)
        signals = DemandSignalService._active_signals_within(
            venue_lat, venue_lng, radius
        )
        if not signals:
            return 0

        user_ids = []
        for s in signals:
            s.status = DemandSignalStatus.CONSUMED
            s.consumed_by_gara_id = gara_id
            user_ids.append(s.user_id)

        DemandSignalService._notify_players_gara_nearby(user_ids, gara_id)
        return len(signals)

    @staticmethod
    def _notify_players_gara_nearby(user_ids: List[int], gara_id: int) -> None:
        from flask import url_for
        from models.notification.factory import NotificationFactory
        from models.notification.models import NotificationType, NotificationPriority

        try:
            action_url = url_for("main.gara_detail_public", gara_id=gara_id)
        except Exception:
            action_url = None

        NotificationFactory.create_bulk_notification(
            user_ids=user_ids,
            notification_type=NotificationType.DEMAND_GARA_NEARBY,
            title=_("Una gara è stata aperta vicino a te!"),
            message=_(
                "La gara che aspettavi nella tua zona è stata pubblicata: "
                "dai un'occhiata e iscriviti."
            ),
            priority=NotificationPriority.HIGH,
            related_entities={"gara_id": gara_id},
            action_url=action_url,
            action_text=_("Vedi la gara"),
        )
