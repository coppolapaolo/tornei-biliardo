"""
Module: models/user/claim_service.py
Purpose: Riscatto di un giocatore non ancora registrato (ADR-086).

Chi si registra e si riconosce in un giocatore creato da un direttore o da un
istruttore (ADR-085) chiede di prenderne le partite. Decide **chi l'ha
creato**, che lo conosce di persona; per i giocatori storici senza creatore, o
col creatore cancellato, decide **l'amministratore**. Approvare vuol dire unire
il giocatore all'account di chi chiede con ``UserMergeService``: iscrizioni,
partite, ELO e classifiche passano a lui, e il giocatore non registrato si
anonimizza come la sorgente di ogni unione.

Non si chiede l'email verificata: la difesa è la conferma di chi decide, che
vede username ed email di chi chiede e se l'email è verificata.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Any, List, Optional

from flask_babel import gettext as _
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.base import db, utc_now
from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from models.status_enum import ClaimRequestStatus
from models.transaction.manager import savepoint, transactional

from .claim_request import ClaimRequest, ClaimRequestRecipient
from .models import User
from .role_enum import UserRole

logger = logging.getLogger(__name__)


def utente_anche_cancellato(user_id: Optional[int]) -> Optional[User]:
    """L'utente con questo id, anche se anonimizzato.

    Un giocatore riscattato è la sorgente di un'unione, quindi anonimizzato: il
    filtro della soft delete lo nasconde anche a ``db.session.get`` appena non
    è più nella sessione. Le richieste devono però continuare a dire chi era.
    """
    if user_id is None:
        return None
    return db.session.execute(
        select(User).where(User.id == user_id).execution_options(include_deleted=True)
    ).scalar_one_or_none()


def _normalizza(testo: Optional[str]) -> str:
    """Nome confrontabile: senza accenti, maiuscole e spazi doppi."""
    decomposto = unicodedata.normalize("NFKD", testo or "")
    senza_accenti = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(senza_accenti.casefold().split())


class ClaimService:
    """Chiedere, approvare e rifiutare il riscatto di un non registrato."""

    # ------------------------------------------------------------ chi decide

    @staticmethod
    def _creatore_attivo(placeholder: User) -> Optional[User]:
        if placeholder.created_by_id is None:
            return None
        creatore = db.session.get(User, placeholder.created_by_id)
        if creatore is None or creatore.is_deleted or creatore.is_placeholder:
            return None
        return creatore

    @staticmethod
    def destinatari(placeholder: User) -> List[User]:
        """Chi decide il riscatto di ``placeholder``.

        Il creatore, se c'è ancora. Altrimenti — giocatore storico senza
        creatore, o creatore cancellato — l'amministratore, e **solo** lui.
        """
        creatore = ClaimService._creatore_attivo(placeholder)
        if creatore is not None:
            return [creatore]
        return (
            User.query.filter(
                User.role == UserRole.ADMIN.value, User.deleted_at.is_(None)
            )
            .order_by(User.id.asc())
            .all()
        )

    @staticmethod
    def puo_decidere(richiesta: ClaimRequest, user: Any) -> bool:
        """Vero per un destinatario della richiesta, o per chi lo è diventato.

        Il secondo caso è l'admin quando il creatore è stato cancellato dopo la
        richiesta: la riserva vale anche per le richieste già aperte.
        """
        if user is None or not getattr(user, "is_authenticated", True):
            return False
        if user.id in richiesta.recipient_ids:
            return True
        placeholder = db.session.get(User, richiesta.placeholder_id)
        if placeholder is None:
            return False
        return user.id in {u.id for u in ClaimService.destinatari(placeholder)}

    @staticmethod
    def puo_vedere(richiesta: ClaimRequest, user: Any) -> bool:
        """La richiesta la leggono chi l'ha fatta, chi la decide e l'admin."""
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        return (
            user.id == richiesta.claimant_id
            or user.is_admin
            or ClaimService.puo_decidere(richiesta, user)
        )

    @staticmethod
    def a_chi(richiesta: ClaimRequest) -> str:
        """A chi è andata la richiesta, per il messaggio di chi l'ha fatta."""
        persone = [r.recipient for r in richiesta.recipients if r.recipient]
        if not persone or all(p.is_admin for p in persone):
            return _("l'amministratore")
        return ", ".join(p.username for p in persone)

    # ---------------------------------------------------------- si può chiedere?

    @staticmethod
    def richiesta_in_attesa(placeholder_id: int) -> Optional[ClaimRequest]:
        return ClaimRequest.query.filter(
            ClaimRequest.placeholder_id == placeholder_id,
            ClaimRequest.status == ClaimRequestStatus.PENDING.value,
        ).first()

    @staticmethod
    def _giocatore_riscattabile(placeholder_id: int) -> User:
        placeholder = utente_anche_cancellato(placeholder_id)
        if (
            placeholder is None
            or not placeholder.is_placeholder
            or placeholder.is_fittizio
        ):
            raise NotFoundError(_("Giocatore non trovato."))
        if placeholder.is_deleted or placeholder.claimed_at is not None:
            raise ConflictError(_("Questo giocatore è già stato riscattato."))
        return placeholder

    @staticmethod
    def _verifica(placeholder: User, claimant: Any) -> None:
        """Solleva se ``claimant`` non può chiedere ``placeholder``."""
        if claimant is None or not getattr(claimant, "is_authenticated", True):
            raise PermissionDeniedError(_("Accedi per riscattare un giocatore."))
        if claimant.id == placeholder.id:
            raise ValidationError(_("Questo giocatore sei tu."))
        if claimant.is_placeholder or claimant.is_fittizio:
            raise PermissionDeniedError(_("Questo account non può riscattare."))
        if claimant.is_admin:
            raise ValidationError(
                _("L'amministratore non gioca: non riscatta giocatori.")
            )
        if placeholder.created_by_id == claimant.id:
            raise ValidationError(
                _("L'hai creato tu: un giocatore non si riscatta da chi l'ha creato.")
            )
        in_attesa = ClaimService.richiesta_in_attesa(placeholder.id)
        if in_attesa is not None:
            if in_attesa.claimant_id == claimant.id:
                raise ConflictError(
                    _(
                        "Hai già chiesto di riscattarlo: la richiesta aspetta "
                        "una risposta."
                    )
                )
            raise ConflictError(
                _(
                    "Qualcun altro ha già chiesto di riscattare questo giocatore: "
                    "la sua richiesta aspetta una risposta."
                )
            )

    @staticmethod
    def motivo_del_no(placeholder_id: int, claimant: Any) -> Optional[str]:
        """Perché ``claimant`` non può chiedere, o None se può."""
        from models.exceptions import DomainError

        try:
            placeholder = ClaimService._giocatore_riscattabile(placeholder_id)
            if claimant is not None and getattr(claimant, "is_authenticated", False):
                ClaimService._verifica(placeholder, claimant)
        except DomainError as exc:
            return str(exc)
        return None

    @staticmethod
    def puo_proporre_riscatto(viewer: Any, giocatore: Any) -> bool:
        """Se accanto a ``giocatore`` va il pulsante «Sei tu? Riscatta».

        ``giocatore`` è un ``User`` o un dizionario di classifica (``user_id``).
        Lo vede chi non è il giocatore né chi l'ha creato, solo per un non
        registrato ancora da riscattare e senza una richiesta già in attesa.
        Il risultato si ricorda per la richiesta HTTP: in una classifica lo
        stesso nome compare più volte.
        """
        if not giocatore:
            return False
        letto = (
            giocatore.get
            if isinstance(giocatore, dict)
            else lambda k, d=None: getattr(giocatore, k, d)
        )
        if not letto("is_placeholder", False):
            return False
        giocatore_id = letto("user_id", None) or letto("id", None)
        if not giocatore_id:
            return False

        from flask import g, has_request_context

        cache: dict = {}
        if has_request_context():
            cache = g.setdefault("_riscatto_proponibile", {})
        if giocatore_id not in cache:
            cache[giocatore_id] = ClaimService._proponibile(int(giocatore_id))
        creatore_id, proponibile = cache[giocatore_id]
        if not proponibile:
            return False

        if viewer is not None and getattr(viewer, "is_authenticated", False):
            if viewer.id == giocatore_id or viewer.id == creatore_id:
                return False
            if viewer.is_admin or viewer.is_placeholder:
                return False
        return True

    @staticmethod
    def _proponibile(giocatore_id: int) -> tuple:
        placeholder = db.session.get(User, giocatore_id)
        if (
            placeholder is None
            or not placeholder.is_placeholder
            or placeholder.is_deleted
            or placeholder.claimed_at is not None
        ):
            return (None, False)
        libero = ClaimService.richiesta_in_attesa(giocatore_id) is None
        return (placeholder.created_by_id, libero)

    @staticmethod
    def omonimi(user: Any) -> List[User]:
        """I non registrati che si chiamano come ``user`` (onboarding).

        Nome e cognome sono cifrati con Fernet, che non è deterministico: in
        SQL non si confrontano. Si leggono i soli non registrati ancora da
        riscattare — pochi — e si confronta qui, senza accenti né maiuscole.
        """
        nome, cognome = _normalizza(user.first_name), _normalizza(user.last_name)
        if not nome or not cognome:
            return []
        candidati = (
            User.query.filter(
                User.is_placeholder.is_(True),
                User.claimed_at.is_(None),
                User.id != user.id,
            )
            .order_by(User.id.asc())
            .all()
        )
        return [
            c
            for c in candidati
            if c.created_by_id != user.id
            and _normalizza(c.first_name) == nome
            and _normalizza(c.last_name) == cognome
        ]

    # ---------------------------------------------------------------- chiedere

    @staticmethod
    @transactional(domain="user")
    def richiedi(placeholder_id: int, claimant: Any) -> ClaimRequest:
        """``claimant`` dice di essere ``placeholder_id`` e ne chiede le partite.

        Raises:
            NotFoundError: il giocatore non esiste o non è un non registrato.
            ConflictError: già riscattato, o una richiesta è già in attesa.
            ValidationError / PermissionDeniedError: chi chiede non può.
        """
        placeholder = ClaimService._giocatore_riscattabile(placeholder_id)
        ClaimService._verifica(placeholder, claimant)

        destinatari = ClaimService.destinatari(placeholder)
        if not destinatari:
            raise ValidationError(
                _("Non c'è nessuno che possa confermare il riscatto, per ora.")
            )

        richiesta = ClaimRequest(
            placeholder_id=placeholder.id,
            claimant_id=claimant.id,
            status=ClaimRequestStatus.PENDING.value,
        )
        db.session.add(richiesta)
        try:
            with savepoint():
                db.session.flush()
        except IntegrityError as exc:
            # Due richieste nello stesso istante: l'indice parziale tiene la
            # prima, e la seconda lo dice come se fosse arrivata dopo.
            raise ConflictError(
                _(
                    "Qualcun altro ha già chiesto di riscattare questo giocatore: "
                    "la sua richiesta aspetta una risposta."
                )
            ) from exc

        for persona in destinatari:
            richiesta.recipients.append(ClaimRequestRecipient(recipient_id=persona.id))
        db.session.flush()

        ClaimService._avvisa_destinatari(richiesta, claimant, placeholder)
        return richiesta

    # ---------------------------------------------------------------- decidere

    @staticmethod
    def _da_decidere(request_id: int, decider: Any) -> ClaimRequest:
        richiesta = db.session.get(ClaimRequest, request_id)
        if richiesta is None:
            raise NotFoundError(_("Richiesta non trovata."))
        if not richiesta.is_pending:
            raise ConflictError(_("Questa richiesta ha già avuto una risposta."))
        if not ClaimService.puo_decidere(richiesta, decider):
            raise PermissionDeniedError(
                _("Questa richiesta la decide chi ha creato il giocatore.")
            )
        return richiesta

    @staticmethod
    @transactional(domain="user")
    def approve(request_id: int, decider: Any) -> ClaimRequest:
        """Conferma: il giocatore passa all'account di chi l'ha chiesto.

        L'unione è quella di ``UserMergeService``, con tutte le sue garanzie:
        se i due hanno giocato l'uno contro l'altro si ferma, le iscrizioni
        alla stessa gara si fondono, ELO e classifiche si ricalcolano.
        """
        from .merge_service import UserMergeService

        richiesta = ClaimService._da_decidere(request_id, decider)
        placeholder_id, claimant_id = richiesta.placeholder_id, richiesta.claimant_id
        ClaimService._giocatore_riscattabile(placeholder_id)

        richiesta.status = ClaimRequestStatus.APPROVED.value
        richiesta.decided_by_id = decider.id
        richiesta.decided_at = utc_now()
        db.session.flush()

        try:
            UserMergeService.merge_users(
                placeholder_id, claimant_id, decider.id, riscatto_approvato=True
            )
        except ConflictError as exc:
            raise ConflictError(
                _(
                    "Chi chiede ha giocato contro questo giocatore: le partite fra "
                    "i due non si possono unire. Rifiuta la richiesta, o chiedi "
                    "all'amministratore di sistemarle prima."
                )
            ) from exc

        # L'unione anonimizza il giocatore: resta la riga, e qui il momento in
        # cui qualcuno l'ha preso. `get` non la vedrebbe più: il filtro della
        # soft delete la nasconde.
        placeholder = utente_anche_cancellato(placeholder_id)
        if placeholder is not None:
            placeholder.claimed_at = utc_now()
        richiesta = db.session.get(ClaimRequest, request_id) or richiesta
        db.session.flush()

        ClaimService._avvisa_chi_ha_chiesto(richiesta, approvata=True)
        logger.info(
            "Riscatto %s: giocatore %s → account %s, confermato da %s",
            request_id,
            placeholder_id,
            claimant_id,
            decider.id,
        )
        return richiesta

    @staticmethod
    @transactional(domain="user")
    def reject(request_id: int, decider: Any) -> ClaimRequest:
        """Rifiuta: il giocatore resta non registrato, e si può richiedere."""
        richiesta = ClaimService._da_decidere(request_id, decider)
        richiesta.status = ClaimRequestStatus.REJECTED.value
        richiesta.decided_by_id = decider.id
        richiesta.decided_at = utc_now()
        db.session.flush()
        ClaimService._avvisa_chi_ha_chiesto(richiesta, approvata=False)
        return richiesta

    # ------------------------------------------------------------------- code

    @staticmethod
    def da_decidere_per(user: Any) -> List[ClaimRequest]:
        """Le richieste in attesa che ``user`` può decidere, dalla più vecchia."""
        if user is None or not getattr(user, "is_authenticated", False):
            return []
        in_attesa = (
            ClaimRequest.query.filter(
                ClaimRequest.status == ClaimRequestStatus.PENDING.value
            )
            .order_by(ClaimRequest.created_at.asc(), ClaimRequest.id.asc())
            .all()
        )
        risultato = []
        for richiesta in in_attesa:
            placeholder = db.session.get(User, richiesta.placeholder_id)
            # Un giocatore unito a mano dall'admin nel frattempo non è più
            # riscattabile: la sua richiesta non è una decisione da prendere.
            if placeholder is None or placeholder.is_deleted:
                continue
            if ClaimService.puo_decidere(richiesta, user):
                risultato.append(richiesta)
        return risultato

    @staticmethod
    def conta_da_decidere(user: Any) -> int:
        """Quante richieste aspettano ``user``: zero senza query per i più."""
        if user is None or not getattr(user, "is_authenticated", False):
            return 0
        if not (
            user.is_admin
            or user.is_director
            or user.is_instructor
            or ClaimRequestRecipient.query.filter_by(recipient_id=user.id).first()
        ):
            return 0
        return len(ClaimService.da_decidere_per(user))

    @staticmethod
    def richieste_di(user: Any) -> List[ClaimRequest]:
        """Le richieste fatte da ``user``, dalla più recente."""
        return (
            ClaimRequest.query.filter(ClaimRequest.claimant_id == user.id)
            .order_by(ClaimRequest.created_at.desc(), ClaimRequest.id.desc())
            .all()
        )

    # --------------------------------------------------------------- notifiche

    @staticmethod
    def _notifica(user_ids: List[int], **kwargs: Any) -> None:
        if not user_ids:
            return
        try:
            from models.notification.factory import NotificationFactory

            NotificationFactory.create_bulk_notification(
                user_ids=list(user_ids), continue_on_error=True, **kwargs
            )
        except Exception:  # pragma: no cover - le notifiche non bloccano mai
            logger.warning("Notifica del riscatto non inviata", exc_info=True)

    @staticmethod
    def _avvisa_destinatari(
        richiesta: ClaimRequest, claimant: Any, placeholder: User
    ) -> None:
        from flask_babel import lazy_gettext as _l
        from models.notification.models import NotificationPriority, NotificationType

        ClaimService._notifica(
            [r.recipient_id for r in richiesta.recipients],
            notification_type=NotificationType.CLAIM_REQUEST_RECEIVED,
            title=_l("Richiesta di riscatto"),
            message=_l(
                "%(chi)s dice di essere %(giocatore)s e chiede le sue partite.",
                chi=claimant.username,
                giocatore=placeholder.username,
            ),
            priority=NotificationPriority.NORMAL,
            action_url=f"/riscatti/{richiesta.id}",
            action_text=_l("Decidi"),
        )

    @staticmethod
    def _avvisa_chi_ha_chiesto(richiesta: ClaimRequest, approvata: bool) -> None:
        from flask_babel import lazy_gettext as _l
        from models.notification.models import NotificationPriority, NotificationType

        placeholder = utente_anche_cancellato(richiesta.placeholder_id)
        nome = (
            (placeholder.previous_username or placeholder.username)
            if placeholder
            else ""
        )
        if approvata:
            messaggio = _l(
                "Riscatto confermato: le partite di %(giocatore)s ora sono tue.",
                giocatore=nome,
            )
        else:
            messaggio = _l(
                "Il riscatto di %(giocatore)s non è stato confermato.",
                giocatore=nome,
            )
        ClaimService._notifica(
            [richiesta.claimant_id],
            notification_type=NotificationType.CLAIM_REQUEST_PROCESSED,
            title=_l("Esito del riscatto"),
            message=messaggio,
            priority=NotificationPriority.HIGH,
            action_url=f"/riscatti/{richiesta.id}",
            action_text=_l("Vedi la richiesta"),
        )
