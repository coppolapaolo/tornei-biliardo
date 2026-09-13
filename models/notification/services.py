"""
Module: models/notification/services.py
Purpose: Notification domain services for notification management
Requirements: SPECIFICHE.md - Notification system for matches and campionati
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from utils.lingua import TestoNotifica, componi, nella_lingua_di

from ..base import db, utc_now
from ..transaction.manager import transactional
from .models import (
    Notification,
    NotificationPreference,
    NotificationType,
    NotificationPriority,
    NotificationStatus,
)


def _annuncia_non_letti(user_id: int, unread_count: int) -> None:
    """Emette l'evento del badge non-letti, nella stessa transazione.

    Fino a settembre 2026 l'emit era rimandato a un listener `after_commit`,
    perché l'archivio degli eventi stava in memoria e non poteva fare rollback
    con la notifica: emesso prima, un rollback lasciava al client un contatore
    fantasma. Ora l'evento è una riga della tabella `live_event` (ADR-057):
    viaggia con la transazione, e se questa salta salta anche lui. Il rinvio
    non serve più — e non sarebbe nemmeno possibile: dentro `after_commit`
    SQLAlchemy non ammette altre query.
    """
    from routes.sse import emit_user_event

    emit_user_event(user_id, "notification", {"unread_count": unread_count})


def _riguarda_una_prova(related_entities: Dict[str, Any]) -> bool:
    """True se le entità collegate puntano a una competizione di prova."""
    from models.prova.guard import campionato_e_di_prova, gara_e_di_prova

    try:
        gara_id = related_entities.get("gara_id")
        if gara_id and gara_e_di_prova(int(gara_id)):
            return True
        campionato_id = related_entities.get("campionato_id")
        return bool(campionato_id) and campionato_e_di_prova(int(campionato_id))
    except (TypeError, ValueError):
        return False


class NotificationService:
    """Service for notification management and delivery."""

    # Default global auto-delete window (giorni) applicato quando l'utente
    # non ha mai configurato la preferenza. Vedi bug 16 docs/debug20260528.md.
    DEFAULT_AUTO_DELETE_DAYS = 30

    @staticmethod
    @transactional(domain="notification")
    def create_notification(
        user_id: int,
        notification_type: NotificationType,
        title: TestoNotifica,
        message: TestoNotifica,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        related_entities: Optional[Dict[str, Any]] = None,
        action_url: Optional[str] = None,
        action_text: Optional[TestoNotifica] = None,
        expires_at: Optional[datetime] = None,
        template_key: Optional[str] = None,
        template_params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Notification]:
        """Create a new notification if user preferences allow it.

        Titolo, messaggio e pulsante si compongono **nella lingua di chi riceve**
        (ADR-062), non in quella di chi ha premuto il pulsante: vanno passati
        da comporre, come ``lazy_gettext`` o come funzione senza argomenti. Una
        stringa semplice passa com'è, ed è giusto solo per il testo scritto da
        un utente, che non si traduce.

        Args:
            template_key: Optional key to NOTIFICATION_TEMPLATES for i18n support.
                         If provided, title/message will be translated at display time.
            template_params: Optional params dict for template substitution.
        """

        # Check user preferences
        if not NotificationPreference.is_notification_enabled(
            user_id, notification_type
        ):
            return None

        preference = NotificationPreference.get_user_preference(
            user_id, notification_type
        )
        if preference and not preference.can_send_notification():
            return None

        # Il testo si compone qui, nella lingua del destinatario (ADR-062): chi
        # ha premuto il pulsante può parlarne un'altra, e uno scheduled task
        # non ne parla nessuna. All'uscita la lingua della pagina torna com'era.
        with nella_lingua_di(user_id):
            testo_titolo = componi(title) or ""
            testo_messaggio = componi(message) or ""
            testo_pulsante = componi(action_text)

            # Una notifica nata dentro una competizione di prova lo dice nel
            # titolo (ADR-058): il direttore impara cosa gli arriva, e non lo
            # scambia per una gara vera.
            if related_entities and _riguarda_una_prova(related_entities):
                from flask_babel import gettext as _

                testo_titolo = _("Prova · %(titolo)s", titolo=testo_titolo)

        # Create notification
        notification = Notification(
            user_id=user_id,
            notification_type=notification_type,
            title=testo_titolo,
            message=testo_messaggio,
            priority=priority,
            action_url=action_url,
            action_text=testo_pulsante,
            expires_at=expires_at,
            template_key=template_key,
        )

        if related_entities:
            notification.set_related_entities(related_entities)

        if template_params:
            notification.set_template_params(template_params)

        db.session.add(notification)

        # Count unread notifications (PENDING or SENT status). L'autoflush
        # include la notifica appena aggiunta; il valore e' corretto post-commit.
        new_count = (
            Notification.query.filter_by(user_id=user_id)
            .filter(
                Notification.status.in_(  # type: ignore[attr-defined]
                    [NotificationStatus.PENDING, NotificationStatus.SENT]
                )
            )
            .count()
        )
        _annuncia_non_letti(user_id, new_count)

        return notification

    @staticmethod
    def get_user_notifications(
        user_id: int, unread_only: bool = False, limit: Optional[int] = None
    ) -> List[Notification]:
        """Get notifications for a user."""

        query = Notification.query.filter_by(user_id=user_id)

        if unread_only:
            query = query.filter(
                Notification.status.in_(  # type: ignore[attr-defined]
                    [
                        NotificationStatus.PENDING,
                        NotificationStatus.SENT,
                    ]
                )
            )

        query = query.order_by(Notification.created_at.desc())

        if limit:
            query = query.limit(limit)

        return query.all()

    @staticmethod
    @transactional(domain="notification")
    def mark_notification_read(
        notification_id: int, user_id: int
    ) -> Optional[Notification]:
        """Mark a notification as read.

        Returns the notification if found, None otherwise.
        Backward compatible: truthy when found, falsy when not.
        """
        notification = Notification.query.filter_by(
            id=notification_id, user_id=user_id
        ).first()

        if not notification:
            return None

        notification.mark_as_read()
        return notification

    @staticmethod
    @transactional(domain="notification")
    def dismiss_notification(notification_id: int, user_id: int) -> bool:
        """Dismiss a notification."""
        notification = Notification.query.filter_by(
            id=notification_id, user_id=user_id
        ).first()

        if not notification:
            return False

        notification.dismiss()
        return True

    @staticmethod
    @transactional(domain="notification")
    def mark_all_read(user_id: int) -> int:
        """Mark all notifications as read for a user."""
        notifications = (
            Notification.query.filter_by(user_id=user_id)
            .filter(
                Notification.status.in_(  # type: ignore[attr-defined]
                    [
                        NotificationStatus.PENDING,
                        NotificationStatus.SENT,
                    ]
                )
            )
            .all()
        )

        count = 0
        for notification in notifications:
            notification.mark_as_read()
            count += 1

        return count

    @staticmethod
    @transactional(domain="notification")
    def mark_pending_as_sent(user_id: int) -> int:
        """Mark all PENDING notifications as SENT for a user.

        Called when the user views the notifications page.
        Returns the number of notifications updated.
        """
        notifications = Notification.query.filter_by(
            user_id=user_id, status=NotificationStatus.PENDING
        ).all()

        count = 0
        for notification in notifications:
            notification.status = NotificationStatus.SENT
            notification.sent_at = utc_now()
            count += 1

        return count

    @staticmethod
    def get_unread_count(user_id: int) -> int:
        """Get count of unread notifications for user."""
        return (
            Notification.query.filter_by(user_id=user_id)
            .filter(
                Notification.status.in_(  # type: ignore[attr-defined]
                    [
                        NotificationStatus.PENDING,
                        NotificationStatus.SENT,
                    ]
                )
            )
            .count()
        )

    @staticmethod
    @transactional(domain="notification")
    def set_user_preference(
        user_id: int,
        notification_type: NotificationType,
        enabled: bool = True,
        email_enabled: bool = False,
        quiet_hours_start: Optional[str] = None,
        quiet_hours_end: Optional[str] = None,
        max_per_day: Optional[int] = None,
        min_interval_minutes: Optional[int] = None,
        auto_delete_days: Optional[int] = None,
    ) -> NotificationPreference:
        """Set user preference for a notification type."""

        preference = NotificationPreference.get_user_preference(
            user_id, notification_type
        )

        if preference:
            preference.enabled = enabled
            preference.email_enabled = email_enabled
            if max_per_day is not None:
                preference.max_per_day = max_per_day
            if min_interval_minutes is not None:
                preference.min_interval_minutes = min_interval_minutes
            if auto_delete_days is not None:
                preference.auto_delete_days = auto_delete_days
        else:
            preference = NotificationPreference(
                user_id=user_id,
                notification_type=notification_type,
                enabled=enabled,
                email_enabled=email_enabled,
                max_per_day=max_per_day,
                min_interval_minutes=min_interval_minutes,
                auto_delete_days=auto_delete_days,
            )
            db.session.add(preference)

        # Parse time strings
        if quiet_hours_start:
            try:
                preference.quiet_hours_start = datetime.strptime(
                    quiet_hours_start, "%H:%M"
                ).time()
            except ValueError:
                pass

        if quiet_hours_end:
            try:
                preference.quiet_hours_end = datetime.strptime(
                    quiet_hours_end, "%H:%M"
                ).time()
            except ValueError:
                pass

        return preference

    @staticmethod
    def get_user_preferences(user_id: int) -> Dict[str, NotificationPreference]:
        """Get all notification preferences for a user."""
        preferences = NotificationPreference.query.filter_by(user_id=user_id).all()
        return {pref.notification_type.value: pref for pref in preferences}

    @staticmethod
    @transactional(domain="notification")
    def expire_old_notifications() -> int:
        """Expire old notifications that have passed their expiry time."""
        expired_notifications = Notification.query.filter(
            Notification.expires_at <= utc_now(),
            Notification.status.in_(  # type: ignore[attr-defined]
                [NotificationStatus.PENDING, NotificationStatus.SENT]
            ),
        ).all()

        count = 0
        for notification in expired_notifications:
            notification.expire()
            count += 1

        return count

    @staticmethod
    @transactional(domain="notification")
    def cleanup_old_notifications(days_old: int = 30) -> int:
        """Delete old notifications to keep database clean."""
        cutoff_date = utc_now() - timedelta(days=days_old)

        old_notifications = Notification.query.filter(
            Notification.created_at <= cutoff_date,
            Notification.status.in_(  # type: ignore[attr-defined]
                [
                    NotificationStatus.READ,
                    NotificationStatus.DISMISSED,
                    NotificationStatus.EXPIRED,
                ]
            ),
        ).all()

        count = len(old_notifications)
        for notification in old_notifications:
            db.session.delete(notification)

        return count

    @staticmethod
    @transactional(domain="notification")
    def delete_notifications_bulk(notification_ids: List[int], user_id: int) -> int:
        """Delete multiple notifications by IDs for a specific user."""
        notifications = Notification.query.filter(
            Notification.id.in_(notification_ids),  # type: ignore[attr-defined]
            Notification.user_id == user_id,
        ).all()

        count = len(notifications)
        for notification in notifications:
            db.session.delete(notification)

        return count

    @staticmethod
    @transactional(domain="notification")
    def auto_delete_by_user_preferences(user_id: Optional[int] = None) -> int:
        """Auto-delete old notifications based on user preferences.

        If user_id is provided, only that user's preferences are processed
        (used for just-in-time cleanup on notification page access). If None,
        all users are processed (cron/scheduled job mode).
        """
        from sqlalchemy import and_

        total_deleted = 0

        query = NotificationPreference.query.filter(
            NotificationPreference.auto_delete_days.isnot(  # type: ignore[attr-defined]
                None
            )
        )
        if user_id is not None:
            query = query.filter(NotificationPreference.user_id == user_id)
        preferences = query.all()

        for preference in preferences:
            if not preference.auto_delete_days:
                continue

            cutoff_date = utc_now() - timedelta(days=preference.auto_delete_days)

            # Bulk DELETE invece di SELECT .all() + db.session.delete per riga:
            # un solo statement per preferenza, niente materializzazione in
            # memoria. Ritorna il numero di righe eliminate.
            deleted = Notification.query.filter(
                and_(
                    Notification.user_id == preference.user_id,
                    Notification.notification_type == preference.notification_type,
                    Notification.created_at <= cutoff_date,
                    Notification.status.in_(  # type: ignore[attr-defined]
                        [
                            NotificationStatus.READ,
                            NotificationStatus.DISMISSED,
                            NotificationStatus.EXPIRED,
                        ]
                    ),
                )
            ).delete(synchronize_session=False)
            total_deleted += deleted

        return total_deleted

    @staticmethod
    def get_global_auto_delete_days(user_id: int) -> Optional[int]:
        """Finestra di auto-cancellazione globale (giorni) dell'utente.

        Convenzione (bug 16):
        - nessuna preferenza configurata → DEFAULT (30 giorni, attivo);
        - preferenza con `auto_delete_days = N` → N giorni;
        - preferenza con `auto_delete_days = None` → disattivata esplicitamente.

        La preferenza globale è memorizzata sulla riga `SYSTEM_ANNOUNCEMENT`.
        """
        preference = NotificationPreference.get_user_preference(
            user_id, NotificationType.SYSTEM_ANNOUNCEMENT
        )
        if preference is None:
            return NotificationService.DEFAULT_AUTO_DELETE_DAYS
        return preference.auto_delete_days

    @staticmethod
    @transactional(domain="notification")
    def set_global_auto_delete_days(
        user_id: int, days: Optional[int]
    ) -> NotificationPreference:
        """Imposta la finestra globale di auto-cancellazione (giorni).

        `days=None` disattiva esplicitamente l'auto-cancellazione. A
        differenza di `set_user_preference`, scrive sempre il valore (anche
        None), così la disattivazione persiste su una preferenza esistente.
        """
        preference = NotificationPreference.get_user_preference(
            user_id, NotificationType.SYSTEM_ANNOUNCEMENT
        )
        if preference is None:
            preference = NotificationPreference(
                user_id=user_id,
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                enabled=True,
            )
            db.session.add(preference)
        preference.auto_delete_days = days
        return preference

    @staticmethod
    @transactional(domain="notification")
    def auto_delete_for_user(user_id: int, default_days: Optional[int] = None) -> int:
        """Cancella TUTTE le notifiche scadute dell'utente (qualsiasi tipo).

        "Scadute" = lette/dismissed/expired più vecchie della finestra di
        auto-cancellazione globale (vedi `get_global_auto_delete_days`).
        Se l'utente non ha mai configurato nulla si applica il default
        (30 giorni); se l'ha disattivata esplicitamente non cancella nulla.

        A differenza di `auto_delete_by_user_preferences` (per-tipo), qui la
        finestra globale si applica a tutti i tipi di notifica (bug 16:
        "cancella tutte quelle scadute").
        """
        days = NotificationService.get_global_auto_delete_days(user_id)
        if days is None:
            days = default_days
        if not days or days <= 0:
            return 0

        cutoff_date = utc_now() - timedelta(days=days)
        old_notifications = Notification.query.filter(
            Notification.user_id == user_id,
            Notification.created_at <= cutoff_date,
            Notification.status.in_(  # type: ignore[attr-defined]
                [
                    NotificationStatus.READ,
                    NotificationStatus.DISMISSED,
                    NotificationStatus.EXPIRED,
                ]
            ),
        ).all()

        count = len(old_notifications)
        for notification in old_notifications:
            db.session.delete(notification)

        return count
