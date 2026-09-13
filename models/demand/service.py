"""Service del segnale-domanda (ADR-036).

Crea richieste geolocalizzate, notifica i director sul fronte di salita ≥ soglia
(con cooldown anti-nag) e consuma le richieste quando una gara apre vicino.
Tutta la prossimità riusa ``utils.geo`` (bounding-box + haversine) e il
centroide città di ``AvailabilityService`` (ADR-034).
"""

from __future__ import annotations

from datetime import timedelta
from typing import List, Optional, Tuple

from flask_babel import lazy_gettext as _l

from models.base import db, utc_now
from models.transaction.manager import transactional
from models.demand.models import DemandSignal, DemandSignalStatus
from utils.geo import haversine_km, bounding_box, clamp_radius

# Tarature (ADR-036 Open Items §4) — affinare sui dati reali.
DEMAND_THRESHOLD = 6
DEMAND_EXPIRY_DAYS = 60
DEMAND_COOLDOWN_DAYS = 7
DEFAULT_DIRECTOR_RADIUS_KM = 30
# Finestra del prompt di riconferma prima della scadenza (open item 3).
DEMAND_REMINDER_WINDOW_DAYS = 7
# Un utente è "attivo" se ha avuto attività entro questi giorni: i suoi segnali
# vengono auto-rinnovati invece di ricevere il prompt di riconferma.
DEMAND_ACTIVE_WITHIN_DAYS = 30


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
        """Notifica i director la cui zona raggiunge (o supera) la soglia con
        questo nuovo segnale, nel rispetto del cooldown anti-nag.

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
            # Soglia raggiunta o superata: notifica quando la zona è "calda".
            # Usiamo >= (non == esatto) perché il conteggio può *saltare* la
            # soglia (creazioni concorrenti, ricalcolo dopo scadenze/consumi):
            # con == esatto il director non verrebbe MAI avvisato in quei casi.
            # Lo spam è già evitato dal cooldown (signal_notified_at) sotto.
            if count_after < DEMAND_THRESHOLD:
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
    @transactional(domain="demand")
    def evaluate_zone_for_new_director(director_id: int) -> bool:
        """Re-eval alla promozione player→director (ADR-036 open item 1).

        Si usa anche dentro una transazione già aperta, come la promozione in
        ``UserPermissionService``: lì diventa un savepoint, e un guasto della
        valutazione annulla solo quello (ADR-061). Fino al 2026-09-13 la
        promozione chiamava ``evaluate_zone_unmanaged`` per paura
        dell'annidamento.
        """
        return DemandSignalService.evaluate_zone_unmanaged(director_id)

    @staticmethod
    def evaluate_zone_unmanaged(director_id: int) -> bool:
        """Il corpo di ``evaluate_zone_for_new_director``, **senza**
        ``@transactional``: esegue le scritture (notifica +
        ``signal_notified_at``) nella transazione del chiamante. Ritorna True
        se ha notificato. Chi lo chiama da un ``try/except`` che deve isolare
        il proprio lavoro usi la variante decorata: un errore di flush
        catturato qui lascia la sessione da annullare.
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
        senza director (ADR-036 open item 2).

        Soglia con ``>=``, non uguaglianza esatta: se due segnali arrivano a
        breve distanza il conteggio può **saltare** il valore soglia (5 → 7) e
        con ``==`` l'avviso non sarebbe partito mai. L'anti-spam non è più
        implicito nel crossing ma esplicito, via cooldown per zona — stesso
        criterio usato per la notifica al director.
        """
        count = DemandSignalService.count_active_within(
            new_signal.latitude, new_signal.longitude, DEFAULT_DIRECTOR_RADIUS_KM
        )
        if count < DEMAND_THRESHOLD:
            return False

        from models.user.models import User
        from models.user.role_enum import UserRole
        from models.notification.factory import NotificationFactory
        from models.notification.models import NotificationType, NotificationPriority

        zone = (new_signal.city or "").strip()
        zone_key = DemandSignalService._zone_dedup_key(new_signal)
        if DemandSignalService._admins_notified_for_zone_recently(zone_key):
            return False

        admin_ids = [
            u.id for u in User.query.filter(User.role == UserRole.ADMIN.value).all()
        ]
        if not admin_ids:
            return False

        if zone:
            message = _l(
                "%(count)s giocatori vorrebbero una gara a %(city)s, una zona "
                "senza un direttore di gara. Valuta di reclutarne o promuoverne uno.",
                count=count,
                city=zone,
            )
        else:
            message = _l(
                "%(count)s giocatori vorrebbero una gara in una zona senza un "
                "direttore di gara. Valuta di reclutarne o promuoverne uno.",
                count=count,
            )

        NotificationFactory.create_bulk_notification(
            user_ids=admin_ids,
            notification_type=NotificationType.DEMAND_ZONE_NO_DIRECTOR,
            title=_l("Domanda in una zona senza direttore di gara"),
            message=message,
            priority=NotificationPriority.NORMAL,
            related_entities={"zone": zone, "zone_key": zone_key, "count": count},
        )
        return True

    @staticmethod
    def _zone_dedup_key(signal: DemandSignal) -> str:
        """Chiave stabile con cui deduplicare gli avvisi agli admin.

        NON si può usare la sola ``city``: è ``None`` per chi non ha impostato
        la città nel profilo (il segnale nasce dal GPS), e una chiave vuota
        collasserebbe **tutte** le zone senza città in un unico secchiello — il
        primo avviso ne sopprimerebbe ogni altro per l'intero cooldown.

        Con la città si usa quella, normalizzata (``Napoli``/``napoli`` sono la
        stessa zona). Senza, si ripiega su un riquadro di coordinate arrotondato
        a 0.1° (~11 km): più fine del raggio di ricerca, quindi due gruppi
        vicini possono generare due avvisi invece di uno — preferibile
        all'opposto, perché un avviso in più si ignora mentre uno mancante non
        si recupera.
        """
        city = (signal.city or "").strip()
        if city:
            return f"city:{city.casefold()}"
        return f"geo:{signal.latitude:.1f},{signal.longitude:.1f}"

    @staticmethod
    def _admins_notified_for_zone_recently(zone_key: str) -> bool:
        """True se gli admin sono già stati avvisati per ``zone_key`` nel cooldown.

        Sostituisce il vecchio anti-spam implicito (``count == soglia``), che
        deduplicava solo per effetto collaterale e perdeva l'avviso quando il
        conteggio saltava la soglia. La chiave è confrontata sul JSON di
        ``related_entities``: le notifiche nella finestra sono poche (solo
        admin), quindi il filtro in Python è più che sufficiente.
        """
        from models.notification.models import Notification, NotificationType

        cutoff = utc_now() - timedelta(days=DEMAND_COOLDOWN_DAYS)
        recent = Notification.query.filter(
            Notification.notification_type == NotificationType.DEMAND_ZONE_NO_DIRECTOR,
            Notification.created_at >= cutoff,
        ).all()
        return any(n.get_related_entities().get("zone_key") == zone_key for n in recent)

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
                title=_l("C'è domanda nella tua zona!"),
                message=_l(
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
            title=_l("Una gara è stata aperta vicino a te!"),
            message=_l(
                "La gara che aspettavi nella tua zona è stata pubblicata: "
                "dai un'occhiata e iscriviti."
            ),
            priority=NotificationPriority.HIGH,
            related_entities={"gara_id": gara_id},
            action_url=action_url,
            action_text=_l("Vedi la gara"),
        )

    # ── ciclo di vita scadenza (ADR-036 open item 3) ─────────────────────────

    @staticmethod
    @transactional(domain="demand")
    def expire_due_signals() -> int:
        """Marca EXPIRED i segnali attivi la cui scadenza è passata.

        Da chiamare via scheduled task. Ritorna il numero di segnali scaduti.
        """
        now = utc_now()
        due = DemandSignal.query.filter(
            DemandSignal.status == DemandSignalStatus.ACTIVE,
            DemandSignal.expires_at <= now,
        ).all()
        for s in due:
            s.status = DemandSignalStatus.EXPIRED
        return len(due)

    @staticmethod
    def _send_expiry_prompt(signal: DemandSignal) -> None:
        """Invia il prompt di riconferma per un singolo segnale (errori isolati)."""
        from models.notification.factory import NotificationFactory
        from models.notification.models import NotificationType, NotificationPriority

        try:
            NotificationFactory.create_bulk_notification(
                user_ids=[signal.user_id],
                notification_type=NotificationType.DEMAND_SIGNAL_EXPIRING,
                title=_l("La tua richiesta sta per scadere"),
                message=_l(
                    "La tua richiesta di una gara nella tua zona sta per "
                    "scadere. Confermala se ti interessa ancora."
                ),
                priority=NotificationPriority.NORMAL,
                related_entities={"demand_signal_id": signal.id},
                continue_on_error=True,
            )
        except Exception:
            pass  # un fallimento notifica non blocca il batch

    @staticmethod
    @transactional(domain="demand")
    def process_expiring_signals(
        within_days: int = DEMAND_REMINDER_WINDOW_DAYS,
        active_within_days: int = DEMAND_ACTIVE_WITHIN_DAYS,
    ) -> dict:
        """Gestisce i segnali prossimi alla scadenza (ADR-036 open item 3).

        Per ogni segnale attivo che scade entro ``within_days``:
        - se il proprietario è **attivo** (``last_active_at`` entro
          ``active_within_days``) → **auto-refresh** (estende, azzera reminder);
        - altrimenti, se non ancora avvisato → invia il **prompt di riconferma**.

        Ritorna ``{"refreshed": int, "reminded": int}``.
        """
        from models.user.models import User

        now = utc_now()
        horizon = now + timedelta(days=within_days)
        active_cutoff = now - timedelta(days=active_within_days)

        expiring = DemandSignal.query.filter(
            DemandSignal.status == DemandSignalStatus.ACTIVE,
            DemandSignal.expires_at > now,
            DemandSignal.expires_at <= horizon,
        ).all()

        refreshed = 0
        reminded = 0
        for s in expiring:
            owner = db.session.get(User, s.user_id)
            is_active = (
                owner is not None
                and owner.last_active_at is not None
                and owner.last_active_at >= active_cutoff
            )
            if is_active:
                s.expires_at = now + timedelta(days=DEMAND_EXPIRY_DAYS)
                s.reminded_at = None
                refreshed += 1
            elif s.reminded_at is None:
                DemandSignalService._send_expiry_prompt(s)
                s.reminded_at = now
                reminded += 1

        return {"refreshed": refreshed, "reminded": reminded}

    @staticmethod
    @transactional(domain="demand")
    def refresh_signal(signal_id: int, user_id: int) -> bool:
        """Rinnova (riconferma) un segnale attivo del proprietario.

        Estende ``expires_at`` di ``DEMAND_EXPIRY_DAYS`` da adesso e azzera il
        flag di promemoria. Ritorna True se rinnovato, False altrimenti (non
        trovato / non proprietario / non attivo).
        """
        signal = db.session.get(DemandSignal, signal_id)
        if signal is None or signal.user_id != user_id:
            return False
        if signal.status != DemandSignalStatus.ACTIVE:
            return False
        signal.expires_at = utc_now() + timedelta(days=DEMAND_EXPIRY_DAYS)
        signal.reminded_at = None
        return True
