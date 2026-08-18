"""
Module: models/user/role_grant_service.py
Purpose: Meccanismo generico di delega dei ruoli concedibili (ADR-041).

Il servizio è il **punto unico di autorizzazione** per i ruoli concedibili: le
route non contengono logica sui ruoli, chiedono a ``can_grant``/``can_revoke``.
Estendere il meccanismo a un altro ruolo domani è una riga in ``GRANT_POLICY``.

Transazioni: ``@transactional`` solo sui metodi **esterni**; il corpo condiviso
``_grant_unchecked`` è deliberatamente **non** decorato, perché annidare
``@transactional`` crea savepoint che su SQLite possono non persistere (vedi
``models/transaction/CLAUDE.md``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from flask import current_app
from sqlalchemy.exc import IntegrityError

from models.base import db, utc_now
from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from models.status_enum import RoleRequestStatus, RoleRequestRecipientStatus
from models.transaction.manager import transactional
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant import RoleGrant, RoleRequest, RoleRequestRecipient


# ────────────────────────────────────────────────────────────────────────────────
# POLICY
# ────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class GrantPolicy:
    """Regole di concessione **per-ruolo**.

    ``self_propagating`` è la proprietà che decide se il ruolo si diffonde a
    catena. È del ruolo, non del meccanismo: l'esaminatore sì (serve a
    scaricare admin a regime), un ipotetico gestore sala no — nominare altri
    gestori significherebbe decidere su sale non proprie.
    """

    #: True se un titolare del ruolo può concederlo a sua volta.
    self_propagating: bool
    #: Codice ``FeatureConfig`` che sblocca la *richiesta* del ruolo (layer L2).
    #: ``None`` per i ruoli che **non si chiedono**: il beta tester lo si
    #: riceve perche' qualcuno ha deciso di farti provare qualcosa, non
    #: perche' hai raggiunto un traguardo. Un codice fasullo l'avrebbe reso
    #: richiedibile da chiunque sbloccasse quella feature.
    request_feature_code: Optional[str]


GRANT_POLICY: Dict[GrantableRole, GrantPolicy] = {
    GrantableRole.EXAMINER: GrantPolicy(
        self_propagating=True,  # un esaminatore concede esaminatore
        request_feature_code="request_examiner",
    ),
    GrantableRole.BETA_TESTER: GrantPolicy(
        # **Non** propagante, al contrario dell'esaminatore. La differenza non
        # e' di comodita': l'esaminatore concede un lavoro da fare, il beta
        # tester concede di *vedere* cose che gli altri non vedono. Una catena
        # di deleghe allargherebbe quella platea senza che l'admin lo sappia,
        # e la revoca — l'unico punto di contenimento (US-A3) — arriverebbe
        # sempre dopo.
        self_propagating=False,
        # Non si chiede: lo assegna un amministratore.
        request_feature_code=None,
    ),
}


class RoleGrantService:
    """Richiesta → approvazione → grant → revoca → audit, per ruolo generico."""

    # ────────────────────────────────────────────────────────────────────
    # Policy / autorizzazione
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def get_policy(role: GrantableRole) -> GrantPolicy:
        """Policy del ruolo; solleva se il ruolo non è gestito dal meccanismo."""
        policy = GRANT_POLICY.get(role)
        if policy is None:
            raise ValidationError(f"Ruolo non concedibile: {role}")
        return policy

    @staticmethod
    def parse_role(value: str) -> GrantableRole:
        """Converte una stringa (path param, form) in ``GrantableRole``."""
        try:
            role = GrantableRole(value)
        except ValueError as exc:
            raise ValidationError(f"Ruolo sconosciuto: {value}") from exc
        RoleGrantService.get_policy(role)
        return role

    @staticmethod
    def can_grant(actor: Optional[User], role: GrantableRole) -> bool:
        """True se ``actor`` può concedere ``role``.

        Admin sempre; altrimenti solo se il ruolo è ``self_propagating`` e
        l'actor ne è titolare attivo.
        """
        if actor is None or not getattr(actor, "id", None):
            return False
        if actor.is_admin:
            return True
        policy = RoleGrantService.get_policy(role)
        if not policy.self_propagating:
            return False
        return RoleGrantService.has_role(actor.id, role)

    @staticmethod
    def can_revoke(actor: Optional[User], role: GrantableRole) -> bool:
        """True se ``actor`` può revocare ``role``.

        Solo admin (US-A3): con la propagazione il ruolo si diffonde senza
        controllo dall'alto, quindi la revoca resta l'unico punto di
        contenimento e non va data ai pari, che potrebbero disfarsi a vicenda.
        """
        return bool(actor is not None and actor.is_admin)

    # ────────────────────────────────────────────────────────────────────
    # Lettura
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def has_role(user_id: int, role: GrantableRole) -> bool:
        """True se l'utente ha un grant **attivo** per il ruolo."""
        if not user_id:
            return False
        return (
            db.session.query(RoleGrant.id)
            .filter(
                RoleGrant.user_id == user_id,
                RoleGrant.role == role.value,
                RoleGrant.revoked_at.is_(None),
            )
            .first()
            is not None
        )

    @staticmethod
    def get_active_grant(user_id: int, role: GrantableRole) -> Optional[RoleGrant]:
        """Grant attivo dell'utente per il ruolo, se esiste."""
        return RoleGrant.query.filter(
            RoleGrant.user_id == user_id,
            RoleGrant.role == role.value,
            RoleGrant.revoked_at.is_(None),
        ).first()

    # NB: i metodi di lettura restano **non decorati**. ``@read_only`` è pur
    # sempre un ``@transactional``: chiamarli da dentro ``create_request``
    # aprirebbe un savepoint annidato, che su SQLite è la ricetta nota per i
    # rollback silenziosi (models/transaction/CLAUDE.md).
    @staticmethod
    def list_holders(role: GrantableRole) -> List[RoleGrant]:
        """Titolari attivi del ruolo, con l'utente e il concedente caricati.

        Ordinati per data di concessione: la catena delle deleghe si legge
        dall'alto verso il basso (US-A3).
        """
        from sqlalchemy.orm import joinedload

        return (
            RoleGrant.query.options(
                joinedload(RoleGrant.user), joinedload(RoleGrant.granted_by)
            )
            .filter(RoleGrant.role == role.value, RoleGrant.revoked_at.is_(None))
            .order_by(RoleGrant.granted_at.asc())
            .all()
        )

    @staticmethod
    def holder_ids(role: GrantableRole) -> set[int]:
        """Gli id dei titolari attivi, in **una** query.

        Esiste per le liste: ``User.is_examiner`` interroga il DB per ogni
        utente, quindi stampare la colonna «Esaminatore» in una tabella di
        cinquanta righe costa cinquanta query. Qui se ne fa una sola e si
        controlla l'appartenenza all'insieme.
        """
        rows = (
            db.session.query(RoleGrant.user_id)
            .filter(RoleGrant.role == role.value, RoleGrant.revoked_at.is_(None))
            .all()
        )
        return {row[0] for row in rows}

    @staticmethod
    def list_grants_history(role: GrantableRole) -> List[RoleGrant]:
        """Tutti i grant del ruolo, revocati inclusi — audit completo (US-A3)."""
        from sqlalchemy.orm import joinedload

        return (
            RoleGrant.query.options(
                joinedload(RoleGrant.user),
                joinedload(RoleGrant.granted_by),
                joinedload(RoleGrant.revoked_by),
            )
            .filter(RoleGrant.role == role.value)
            .order_by(RoleGrant.granted_at.desc())
            .all()
        )

    @staticmethod
    def get_pending_requests_for(actor: User) -> List[RoleRequest]:
        """Richieste pendenti che ``actor`` può processare.

        Admin vede tutte le pendenti (coda di bootstrap e di ultima istanza);
        un titolare vede solo quelle in cui è destinatario **non ancora
        espresso**.
        """
        from sqlalchemy.orm import joinedload

        # joinedload sul richiedente: il template della coda stampa
        # ``req.user.username`` per riga, che con il lazy di default sarebbe
        # una SELECT per richiesta. ``recipients`` è già selectin.
        query = RoleRequest.query.options(joinedload(RoleRequest.user)).filter(
            RoleRequest.status == RoleRequestStatus.PENDING.value
        )
        if not actor.is_admin:
            query = query.join(RoleRequestRecipient).filter(
                RoleRequestRecipient.recipient_id == actor.id,
                RoleRequestRecipient.status == RoleRequestRecipientStatus.PENDING.value,
            )
        return query.order_by(RoleRequest.requested_at.asc()).all()

    @staticmethod
    def get_pending_request(user_id: int, role: GrantableRole) -> Optional[RoleRequest]:
        """Richiesta pendente dell'utente per il ruolo, se esiste."""
        return RoleRequest.query.filter(
            RoleRequest.user_id == user_id,
            RoleRequest.role == role.value,
            RoleRequest.status == RoleRequestStatus.PENDING.value,
        ).first()

    # ────────────────────────────────────────────────────────────────────
    # Grant / revoca
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _grant_unchecked(
        user_id: int,
        role: GrantableRole,
        granted_by_id: int,
        notes: Optional[str] = None,
        notify: bool = True,
    ) -> RoleGrant:
        """Crea il grant **senza** controlli di autorizzazione.

        Corpo condiviso fra ``grant``, ``process_request`` e
        ``debug_self_grant``. Volutamente **non** decorato: gira dentro la
        transazione già aperta dal chiamante.

        ``notify=False`` per i chiamanti che mandano già una notifica più
        specifica (l'esito della richiesta), così l'utente non ne riceve due.
        """
        target = db.session.get(User, user_id)
        if target is None or target.is_deleted:
            raise NotFoundError("Utente non trovato")

        if RoleGrantService.has_role(user_id, role):
            raise ConflictError("L'utente ha già questo ruolo")

        grant = RoleGrant(
            user_id=user_id,
            role=role.value,
            granted_by_id=granted_by_id,
            granted_at=utc_now(),
            notes=notes,
        )
        db.session.add(grant)

        # Savepoint: fa emergere al flush la violazione dell'indice UNIQUE
        # parziale se un altro concedente ha vinto la corsa (TOCTOU), così il
        # perdente riceve un ConflictError invece di un 500 opaco (ADR-025).
        try:
            with db.session.begin_nested():
                db.session.flush()
        except IntegrityError as exc:
            raise ConflictError("L'utente ha già questo ruolo") from exc

        if notify:
            RoleGrantService._notify_role_granted(target, role)
        RoleGrantService._flash_role_unlock(user_id, role)
        return grant

    @staticmethod
    @transactional(domain="user")
    def grant(
        user_id: int,
        role: GrantableRole,
        granted_by: User,
        notes: Optional[str] = None,
    ) -> RoleGrant:
        """Concede il ruolo. Via diretta (US-A1) e bootstrap del sistema."""
        if not RoleGrantService.can_grant(granted_by, role):
            raise PermissionDeniedError("Non puoi concedere questo ruolo")
        return RoleGrantService._grant_unchecked(
            user_id, role, granted_by.id, notes=notes
        )

    @staticmethod
    @transactional(domain="user")
    def revoke(
        user_id: int,
        role: GrantableRole,
        revoked_by: User,
        notes: Optional[str] = None,
    ) -> RoleGrant:
        """Revoca il ruolo (US-A3).

        Ciò che il titolare ha prodotto mentre lo aveva **resta valido**: qui
        si chiude solo la concessione, non si tocca il lavoro svolto.
        """
        if not RoleGrantService.can_revoke(revoked_by, role):
            raise PermissionDeniedError("Solo un amministratore può revocare un ruolo")

        grant = RoleGrantService.get_active_grant(user_id, role)
        if grant is None:
            raise NotFoundError("Nessun ruolo attivo da revocare per questo utente")

        grant.revoke(revoked_by.id, notes=notes)
        return grant

    @staticmethod
    @transactional(domain="user")
    def debug_self_grant(user: User, role: GrantableRole) -> RoleGrant:
        """Auto-concessione del ruolo in ``DEBUG_MODE`` (US-D1).

        Doppia guardia: la route fa ``abort(404)`` fuori da DEBUG_MODE, e il
        service rifiuta comunque. Il grant creato è **normale** — revocabile e
        visibile nell'audit come ogni altro.
        """
        if not current_app.config.get("DEBUG_MODE", False):
            raise PermissionDeniedError(
                "Auto-concessione disponibile solo in modalità debug"
            )
        return RoleGrantService._grant_unchecked(
            user.id, role, user.id, notes="debug self-grant", notify=False
        )

    # ────────────────────────────────────────────────────────────────────
    # Richieste
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def eligible_recipients(role: GrantableRole, requester_id: int) -> List[User]:
        """Utenti a cui la richiesta può essere indirizzata.

        I titolari attivi del ruolo (escluso il richiedente). Se non ce n'è
        nessuno — il caso di bootstrap, UJ-4 variante 2 — la richiesta può
        andare solo agli admin.
        """
        holder_ids = [
            g.user_id
            for g in RoleGrantService.list_holders(role)
            if g.user_id != requester_id
        ]
        if holder_ids:
            # Passa da User.query e non da grant.user: il filtro automatico
            # sul soft delete esclude così i titolari anonimizzati.
            return User.query.filter(User.id.in_(holder_ids)).all()
        return (
            User.query.filter(User.role == UserRole.ADMIN.value)
            .filter(User.id != requester_id)
            .all()
        )

    @staticmethod
    @transactional(domain="user")
    def create_request(
        user_id: int,
        role: GrantableRole,
        recipient_ids: Optional[Sequence[int]] = None,
        notes: Optional[str] = None,
    ) -> RoleRequest:
        """Crea una richiesta di ruolo indirizzata a uno o più destinatari.

        ``recipient_ids`` vuoto/None = "a tutti" i destinatari eleggibili.
        """
        policy = RoleGrantService.get_policy(role)

        user = db.session.get(User, user_id)
        if user is None or user.is_deleted:
            raise NotFoundError("Utente non trovato")

        if RoleGrantService.has_role(user_id, role):
            raise ConflictError("Hai già questo ruolo")

        # Enforcement server-side del gate L2: non basta nascondere il bottone,
        # la richiesta deve essere rifiutata anche via POST diretto.
        if policy.request_feature_code is None:
            raise PermissionDeniedError(
                "Questo ruolo non si richiede: lo assegna un amministratore"
            )
        if not user.can_access(policy.request_feature_code):
            raise PermissionDeniedError(
                "Non hai ancora sbloccato la richiesta di questo ruolo"
            )

        if RoleGrantService.get_pending_request(user_id, role) is not None:
            raise ConflictError("Hai già una richiesta in attesa per questo ruolo")

        eligible = RoleGrantService.eligible_recipients(role, user_id)
        if not eligible:
            raise ValidationError(
                "Non c'è nessuno a cui indirizzare la richiesta al momento"
            )

        eligible_by_id = {u.id: u for u in eligible}
        if recipient_ids:
            chosen_ids = [
                rid for rid in dict.fromkeys(recipient_ids) if rid in eligible_by_id
            ]
            if not chosen_ids:
                raise ValidationError("Nessun destinatario valido selezionato")
        else:
            chosen_ids = list(eligible_by_id)

        request = RoleRequest(
            user_id=user_id,
            role=role.value,
            status=RoleRequestStatus.PENDING.value,
            requested_at=utc_now(),
            notes=notes,
        )
        db.session.add(request)

        try:
            with db.session.begin_nested():
                db.session.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "Hai già una richiesta in attesa per questo ruolo"
            ) from exc

        # Append sulla relationship (non db.session.add con request_id), così
        # ``request.recipients`` resta coerente per il chiamante senza refresh.
        for recipient_id in chosen_ids:
            request.recipients.append(
                RoleRequestRecipient(
                    recipient_id=recipient_id,
                    status=RoleRequestRecipientStatus.PENDING.value,
                )
            )
        db.session.flush()

        RoleGrantService._notify_request_created(request, user, chosen_ids)
        return request

    @staticmethod
    @transactional(domain="user")
    def process_request(
        request_id: int,
        actor: User,
        approve: bool,
        decision_notes: Optional[str] = None,
    ) -> RoleRequest:
        """Approva o rifiuta una richiesta di ruolo.

        **Il primo che approva concede il ruolo** e chiude la richiesta per gli
        altri destinatari, che ne ricevono notifica (US-A2). Nessun quorum,
        nessun secondo assenso.

        Il rifiuto invece non chiude la richiesta per tutti: vale per il solo
        destinatario che lo esprime, e la richiesta diventa ``rejected`` solo
        quando non resta nessun destinatario in attesa. Un admin che rifiuta
        senza essere destinatario chiude comunque l'intera richiesta.
        """
        request = db.session.get(RoleRequest, request_id)
        if request is None:
            raise NotFoundError("Richiesta non trovata")

        if not request.is_pending:
            raise ConflictError("La richiesta è già stata processata")

        role = RoleGrantService.parse_role(request.role)

        if not RoleGrantService.can_grant(actor, role):
            raise PermissionDeniedError("Non puoi processare questa richiesta")

        own_recipient = next(
            (r for r in request.recipients if r.recipient_id == actor.id), None
        )
        if own_recipient is None and not actor.is_admin:
            raise PermissionDeniedError("Non sei fra i destinatari di questa richiesta")

        if (
            own_recipient is not None
            and own_recipient.status != RoleRequestRecipientStatus.PENDING.value
        ):
            raise ConflictError("Hai già risposto a questa richiesta")

        if approve:
            RoleGrantService._grant_unchecked(
                request.user_id,
                role,
                actor.id,
                notes=decision_notes,
                # L'esito della richiesta è già notificato più sotto.
                notify=False,
            )
            request.status = RoleRequestStatus.APPROVED.value
            if own_recipient is not None:
                own_recipient.status = RoleRequestRecipientStatus.APPROVED.value
            RoleGrantService._close_other_recipients(request, actor.id)
        else:
            if own_recipient is not None:
                own_recipient.status = RoleRequestRecipientStatus.REJECTED.value
            if own_recipient is None or not request.pending_recipients():
                # Admin non destinatario, oppure ultimo destinatario in attesa:
                # la richiesta è definitivamente rifiutata.
                request.status = RoleRequestStatus.REJECTED.value
                RoleGrantService._close_other_recipients(request, actor.id)

        if request.status != RoleRequestStatus.PENDING.value:
            request.processed_at = utc_now()
            request.processed_by_id = actor.id
            request.decision_notes = decision_notes
            db.session.flush()
            RoleGrantService._notify_request_processed(request, actor, approve)
        else:
            db.session.flush()

        return request

    @staticmethod
    def _close_other_recipients(request: RoleRequest, actor_id: int) -> None:
        """Chiude gli altri destinatari in attesa e li avvisa (US-A2)."""
        closed_ids: List[int] = []
        for recipient in request.recipients:
            if recipient.recipient_id == actor_id:
                continue
            if recipient.status == RoleRequestRecipientStatus.PENDING.value:
                recipient.status = RoleRequestRecipientStatus.CLOSED.value
                closed_ids.append(recipient.recipient_id)

        if closed_ids:
            RoleGrantService._notify_recipients_closed(request, closed_ids)

    # ────────────────────────────────────────────────────────────────────
    # Notifiche (best-effort: non devono mai bloccare l'operazione)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _role_label(role: GrantableRole) -> str:
        from flask_babel import _

        labels = {GrantableRole.EXAMINER: _("Esaminatore")}
        return labels.get(role, role.value)

    @staticmethod
    def _notify(user_ids: Sequence[int], **kwargs: Any) -> None:
        if not user_ids:
            return
        try:
            from models.notification.factory import NotificationFactory

            NotificationFactory.create_bulk_notification(
                user_ids=list(user_ids), continue_on_error=True, **kwargs
            )
        except Exception:  # pragma: no cover - le notifiche non bloccano mai
            import logging

            logging.getLogger(__name__).warning(
                "Notifica di delega ruolo non inviata", exc_info=True
            )

    @staticmethod
    def _notify_request_created(
        request: RoleRequest, requester: User, recipient_ids: Sequence[int]
    ) -> None:
        from flask_babel import _
        from models.notification.models import NotificationPriority, NotificationType

        RoleGrantService._notify(
            recipient_ids,
            notification_type=NotificationType.ROLE_REQUEST_RECEIVED,
            title=_("Richiesta di ruolo"),
            message=_(
                "%(user)s chiede il ruolo di %(role)s.",
                user=requester.username,
                role=RoleGrantService._role_label(
                    RoleGrantService.parse_role(request.role)
                ),
            ),
            priority=NotificationPriority.NORMAL,
            action_url="/roles/requests",
            action_text=_("Vedi le richieste"),
        )

    @staticmethod
    def _notify_request_processed(
        request: RoleRequest, actor: User, approve: bool
    ) -> None:
        from flask_babel import _
        from models.notification.models import NotificationPriority, NotificationType

        role_label = RoleGrantService._role_label(
            RoleGrantService.parse_role(request.role)
        )
        if approve:
            message = _(
                "%(actor)s ha approvato la tua richiesta: ora sei %(role)s.",
                actor=actor.username,
                role=role_label,
            )
        else:
            message = _(
                "La tua richiesta per il ruolo di %(role)s non è stata accolta.",
                role=role_label,
            )

        RoleGrantService._notify(
            [request.user_id],
            notification_type=NotificationType.ROLE_REQUEST_PROCESSED,
            title=_("Richiesta di ruolo processata"),
            message=message,
            priority=NotificationPriority.HIGH,
        )

    @staticmethod
    def _notify_recipients_closed(
        request: RoleRequest, recipient_ids: Sequence[int]
    ) -> None:
        from flask_babel import _
        from models.notification.models import NotificationPriority, NotificationType

        RoleGrantService._notify(
            recipient_ids,
            notification_type=NotificationType.ROLE_REQUEST_CLOSED,
            title=_("Richiesta di ruolo chiusa"),
            message=_(
                "La richiesta per il ruolo di %(role)s è stata presa in carico "
                "da un altro titolare.",
                role=RoleGrantService._role_label(
                    RoleGrantService.parse_role(request.role)
                ),
            ),
            priority=NotificationPriority.LOW,
        )

    @staticmethod
    def _notify_role_granted(user: User, role: GrantableRole) -> None:
        from flask_babel import _
        from models.notification.models import NotificationPriority, NotificationType

        RoleGrantService._notify(
            [user.id],
            notification_type=NotificationType.ROLE_GRANTED,
            title=_("Nuovo ruolo"),
            message=_(
                "Hai ottenuto il ruolo di %(role)s.",
                role=RoleGrantService._role_label(role),
            ),
            priority=NotificationPriority.HIGH,
        )

    @staticmethod
    def _flash_role_unlock(user_id: int, role: GrantableRole) -> None:
        """Toast di sblocco 🔓 al titolare del nuovo ruolo.

        Separato dalla notifica: quella resta nella casella e si legge poi, il
        toast è il momento in cui la porta si apre. Il bridge sa già stare zitto
        fuori da un request context — un grant concesso da uno script di console
        non deve rompersi per questo.
        """
        try:
            from models.gamification.frontend_bridge import (
                GamificationFrontendBridge,
            )

            GamificationFrontendBridge.handle_role_granted_event(user_id, role)
        except Exception:  # pragma: no cover - un toast non blocca un grant
            import logging

            logging.getLogger(__name__).warning(
                "Toast di sblocco ruolo non emesso", exc_info=True
            )
