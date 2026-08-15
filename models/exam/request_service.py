"""
Module: models/exam/request_service.py
Purpose: L'appuntamento d'esame — richiesta a più esaminatori, negoziazione di
         data e ora, accettazione (ADR-042).

Il servizio è il **punto unico** dove vivono i due invarianti della
negoziazione: le route (Fase 5) chiedono qui, non li reimplementano.

- **Invariante 1** — può accettare o controproporre solo chi *non* ha fatto
  l'ultima proposta. Senza, ci si accetterebbe la propria.
- **Invariante 2** — la prima controproposta fissa l'interlocutore. Da lì lo
  *scambio* è a due; gli altri destinatari possono ancora accettare la proposta
  sul tavolo com'è, o lasciar scadere, ma non inserirsi nella trattativa.

Il presidio anti-TOCTOU è doppio e non è quello dei match individuali — la
ragione sta nel docstring di ``request_models.py``, il test in
``tests/new/integration/test_exam_request_toctou.py``.

Transazioni: ``@transactional`` solo sui metodi esterni; i corpi condivisi
(``_close_other_recipients``, le notifiche) girano dentro la transazione già
aperta dal chiamante — annidare crea savepoint che su SQLite sanno di rollback
silenziosi (``models/transaction/CLAUDE.md``).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from ..base import db, utc_now
from ..exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from ..status_enum import ExamRequestRecipientStatus, ExamRequestStatus
from ..transaction.manager import transactional
from ..user.models import User
from .request_models import ExamRequest, ExamRequestRecipient, ExamTimeProposal

logger = logging.getLogger(__name__)

#: Quanto resta aperta una richiesta se non si dice altro. Una settimana: il
#: tempo di sentirsi, senza lasciare appuntamenti fantasma in giro per mesi.
DEFAULT_EXPIRY_DAYS = 7


class ExamRequestService:
    """Ciclo di vita dell'appuntamento: richiesta → trattativa → accordo."""

    # ────────────────────────────────────────────────────────────────────
    # Lookup
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def get_request(request_id: int) -> ExamRequest:
        """Richiesta per id, o ``NotFoundError``."""
        request = db.session.get(ExamRequest, request_id)
        if request is None:
            raise NotFoundError("Richiesta d'esame non trovata")
        return request

    @staticmethod
    def eligible_examiners(exam_id: int, requester_id: int) -> List[User]:
        """A chi la richiesta può essere indirizzata.

        Gli esaminatori *di quell'esame* — creatore e co-esaminatori — meno il
        richiedente, che non può somministrarsi un esame.
        """
        from .services import ExamService

        exam = ExamService.get_exam(exam_id)
        candidate_ids = exam.examiner_ids - {requester_id}
        if not candidate_ids:
            return []
        # Via User.query: il filtro automatico sul soft delete esclude così gli
        # esaminatori anonimizzati.
        return User.query.filter(User.id.in_(candidate_ids)).all()

    @staticmethod
    def available_examiners_at_venue(
        exam_id: int, billiard_hall_id: int
    ) -> List[Dict[str, Any]]:
        """Chi è disponibile in questa sala **ed** è esaminatore di questo esame.

        US-E3/3.4: le disponibilità non si duplicano. ``UserLocationAvailability``
        è già agnostica al match e si riusa identica; qui serve solo
        l'intersezione con gli esaminatori dell'esame.
        """
        from ..individual_match.availability_service import AvailabilityService
        from .services import ExamService

        exam = ExamService.get_exam(exam_id)
        available = AvailabilityService.get_available_players_at_venue(billiard_hall_id)
        return [p for p in available if p["user_id"] in exam.examiner_ids]

    @staticmethod
    def get_requests_for_examiner(
        user_id: int, include_closed: bool = False
    ) -> List[ExamRequest]:
        """Richieste che riguardano un esaminatore, dalla più recente.

        Quelle ancora da rispondere e quelle che ha accettato — cioè i suoi
        appuntamenti. Fuori restano le richieste che gli sono state chiuse
        sotto il naso: comparirebbero come impegni che non sono suoi.
        """
        query = (
            ExamRequest.query.options(
                joinedload(ExamRequest.exam), joinedload(ExamRequest.requester)
            )
            .join(ExamRequestRecipient)
            .filter(ExamRequestRecipient.examiner_id == user_id)
        )
        if not include_closed:
            query = query.filter(
                db.or_(
                    db.and_(
                        ExamRequest.status == ExamRequestStatus.NEGOTIATING.value,
                        ExamRequestRecipient.status
                        == ExamRequestRecipientStatus.PENDING.value,
                    ),
                    ExamRequest.accepted_by_id == user_id,
                )
            )
        return query.order_by(ExamRequest.created_at.desc()).all()

    @staticmethod
    def get_requests_for_requester(
        user_id: int, only_negotiating: bool = False
    ) -> List[ExamRequest]:
        """Richieste inviate dal candidato, dalla più recente."""
        query = ExamRequest.query.options(
            joinedload(ExamRequest.exam), joinedload(ExamRequest.accepted_by)
        ).filter(ExamRequest.requester_id == user_id)
        if only_negotiating:
            query = query.filter(
                ExamRequest.status == ExamRequestStatus.NEGOTIATING.value
            )
        return query.order_by(ExamRequest.created_at.desc()).all()

    @staticmethod
    def get_open_request(user_id: int, exam_id: int) -> Optional[ExamRequest]:
        """La richiesta ancora in trattativa per questo esame, se c'è."""
        return ExamRequest.query.filter(
            ExamRequest.requester_id == user_id,
            ExamRequest.exam_id == exam_id,
            ExamRequest.status == ExamRequestStatus.NEGOTIATING.value,
        ).first()

    # ────────────────────────────────────────────────────────────────────
    # Richiesta (US-P4)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="exam")
    def create_request(
        actor: User,
        exam_id: int,
        scheduled_at: datetime,
        billiard_hall_id: int,
        recipient_ids: Optional[Sequence[int]] = None,
        expires_at: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> ExamRequest:
        """Chiede di sostenere un esame certificato.

        ``recipient_ids`` vuoto/None = «a qualsiasi esaminatore»: la richiesta
        va a tutti quelli dell'esame e **il primo che accetta chiude gli altri**.
        """
        from .services import ExamService

        exam = ExamService.get_exam(exam_id)
        if not exam.is_active:
            raise ConflictError("Questo esame non è più disponibile")
        if exam.challenges.count() == 0:
            raise ValidationError("L'esame non contiene ancora nessun drill")

        # Auto-somministrazione vietata **a monte**: chi somministra l'esame non
        # può chiederlo. Il divieto in sessione (3.5) è l'ultima rete, non la
        # prima — qui non deve nemmeno nascere la richiesta.
        if exam.is_examined_by(actor.id):
            raise PermissionDeniedError(
                "Un esaminatore non può sostenere un esame che somministra"
            )

        ExamRequestService._require_future(scheduled_at)
        hall_id = ExamRequestService._require_hall(billiard_hall_id)

        if ExamRequestService.get_open_request(actor.id, exam_id) is not None:
            raise ConflictError("Hai già una richiesta in corso per questo esame")

        eligible = ExamRequestService.eligible_examiners(exam_id, actor.id)
        if not eligible:
            raise ValidationError("Questo esame non ha esaminatori a cui rivolgersi")

        eligible_by_id = {u.id: u for u in eligible}
        if recipient_ids:
            chosen_ids = [
                rid for rid in dict.fromkeys(recipient_ids) if rid in eligible_by_id
            ]
            if not chosen_ids:
                raise ValidationError("Nessun esaminatore valido selezionato")
        else:
            chosen_ids = list(eligible_by_id)

        expiry = expires_at or (utc_now() + timedelta(days=DEFAULT_EXPIRY_DAYS))
        if expiry <= utc_now():
            raise ValidationError("La scadenza della richiesta è già passata")

        request = ExamRequest(
            exam_id=exam_id,
            requester_id=actor.id,
            status=ExamRequestStatus.NEGOTIATING.value,
            billiard_hall_id=hall_id,
            scheduled_at=scheduled_at,
            expires_at=expiry,
            last_proposed_by_id=actor.id,
        )
        db.session.add(request)
        db.session.flush()

        # Append sulla relationship: ``request.recipients`` resta coerente per
        # il chiamante senza doverlo ricaricare.
        for recipient_id in chosen_ids:
            request.recipients.append(
                ExamRequestRecipient(
                    examiner_id=recipient_id,
                    status=ExamRequestRecipientStatus.PENDING.value,
                )
            )
        request.time_proposals.append(
            ExamTimeProposal(
                proposed_by_id=actor.id,
                scheduled_at=scheduled_at,
                billiard_hall_id=hall_id,
            )
        )
        db.session.flush()

        ExamRequestService._notify_request_created(request, actor, chosen_ids, notes)
        return request

    # ────────────────────────────────────────────────────────────────────
    # Negoziazione (US-E5, US-P5)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="exam")
    def counter_propose(
        request_id: int,
        actor: User,
        scheduled_at: datetime,
        billiard_hall_id: Optional[int] = None,
    ) -> ExamTimeProposal:
        """Contropropone un altro slot (e, volendo, un'altra sala).

        Si alternano finché uno accetta o la richiesta scade. La sala si
        eredita se non se ne propone una nuova: il più delle volte è il tempo a
        non andare bene, non il posto.
        """
        request = ExamRequestService._require_negotiable(request_id)
        actor_id = ExamRequestService._require_actor_id(actor)

        # Invariante 1: chi ha appena proposto aspetta la risposta.
        if actor_id == request.last_proposed_by_id:
            raise ConflictError("Hai già fatto l'ultima proposta: attendi una risposta")

        if actor_id != request.requester_id:
            recipient = request.recipient_for(actor_id)
            if recipient is None:
                raise PermissionDeniedError("Non sei fra gli esaminatori interpellati")
            if not recipient.is_pending:
                raise ConflictError("Hai già risposto a questa richiesta")

            # Invariante 2: la prima controproposta fissa l'interlocutore.
            if request.negotiating_with_id is None:
                request.negotiating_with_id = actor_id
            elif request.negotiating_with_id != actor_id:
                raise ConflictError(
                    "La trattativa è in corso con un altro esaminatore: "
                    "puoi solo accettare la proposta attuale"
                )

        ExamRequestService._require_future(scheduled_at)
        hall_id = (
            request.billiard_hall_id
            if billiard_hall_id is None
            else ExamRequestService._require_hall(billiard_hall_id)
        )

        current = request.current_proposal
        if current is not None:
            current.supersede()

        proposal = ExamTimeProposal(
            proposed_by_id=actor_id,
            scheduled_at=scheduled_at,
            billiard_hall_id=hall_id,
        )
        request.time_proposals.append(proposal)

        request.scheduled_at = scheduled_at
        request.billiard_hall_id = hall_id
        request.last_proposed_by_id = actor_id
        db.session.flush()

        ExamRequestService._notify_counter_proposal(request, actor)
        return proposal

    # ────────────────────────────────────────────────────────────────────
    # Accettazione (US-E4, US-E4b, US-P5b)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="exam")
    def accept(request_id: int, actor: User) -> ExamRequest:
        """Accetta la proposta sul tavolo e fissa l'appuntamento.

        Accetta un esaminatore interpellato, oppure il candidato quando è un
        esaminatore ad aver controproposto — senza quest'ultimo caso la
        trattativa non convergerebbe mai dal lato del candidato, che potrebbe
        solo rilanciare uno slot identico e aspettare.

        Il primo che accetta vince: gli altri destinatari passano a ``closed``
        e **lo vengono a sapere** (US-E4b), il candidato riceve la conferma con
        data, ora e sala (US-P5b).
        """
        request = ExamRequestService._require_negotiable(request_id)
        actor_id = ExamRequestService._require_actor_id(actor)

        # Invariante 1: non si accetta la propria proposta.
        if actor_id == request.last_proposed_by_id:
            raise ConflictError(
                "Non puoi accettare la tua stessa proposta: attendi una risposta"
            )

        if actor_id == request.requester_id:
            # Accetta il candidato: l'appuntamento è con chi ha proposto.
            winner_id = request.last_proposed_by_id
        else:
            winner_id = actor_id

        winner_row = request.recipient_for(winner_id)
        if winner_row is None:
            raise PermissionDeniedError("Non sei fra gli esaminatori interpellati")
        if not winner_row.is_pending:
            if actor_id == request.requester_id:
                # Ha controproposto e poi si è sfilato: non c'è più niente da
                # accettare *con lui*, ma la richiesta può ancora vivere con
                # gli altri destinatari.
                raise ConflictError(
                    "L'esaminatore che aveva proposto non è più disponibile"
                )
            raise ConflictError("Hai già risposto a questa richiesta")

        now = utc_now()

        # Presidio anti-TOCTOU 2 — UPDATE condizionato: se un altro ha già
        # accettato, il rowcount è 0 e il perdente riceve un ConflictError
        # invece di sovrascrivere l'appuntamento del vincitore.
        updated = (
            db.session.query(ExamRequest)
            .filter(
                ExamRequest.id == request.id,
                ExamRequest.accepted_by_id.is_(None),
                ExamRequest.status == ExamRequestStatus.NEGOTIATING.value,
            )
            .update(
                {
                    "status": ExamRequestStatus.ACCEPTED.value,
                    "accepted_by_id": winner_id,
                    "accepted_at": now,
                    "negotiating_with_id": winner_id,
                },
                synchronize_session=False,
            )
        )
        if not updated:
            raise ConflictError("La richiesta è già stata presa in carico")
        # L'UPDATE è passato dal DB scavalcando l'ORM: senza expire, l'istanza
        # in sessione mostrerebbe ancora lo stato precedente.
        db.session.expire(request)

        # Presidio anti-TOCTOU 1 — l'indice UNIQUE parziale
        # ``(request_id) WHERE status='accepted'``. Il savepoint fa emergere la
        # violazione al flush per poterla tradurre (ADR-025).
        try:
            with db.session.begin_nested():
                winner_row.status = ExamRequestRecipientStatus.ACCEPTED.value
                winner_row.responded_at = now
                db.session.flush()
        except IntegrityError as exc:
            raise ConflictError("La richiesta è già stata presa in carico") from exc

        ExamRequestService._close_other_recipients(request, winner_id)
        db.session.flush()

        ExamRequestService._notify_accepted(request, actor_id, winner_id)
        return request

    @staticmethod
    @transactional(domain="exam")
    def decline(request_id: int, actor: User) -> ExamRequest:
        """Un esaminatore si sfila.

        Un rifiuto solo non chiude niente: gli altri interpellati possono
        ancora accettare. Quando non resta più nessuno la richiesta si chiude
        senza appuntamento — stesso esito della scadenza, ed è per questo che
        usa ``expired`` invece di inventare un quinto stato.
        """
        request = ExamRequestService._require_negotiable(request_id)
        actor_id = ExamRequestService._require_actor_id(actor)

        recipient = request.recipient_for(actor_id)
        if recipient is None:
            raise PermissionDeniedError("Non sei fra gli esaminatori interpellati")
        if not recipient.is_pending:
            raise ConflictError("Hai già risposto a questa richiesta")

        recipient.status = ExamRequestRecipientStatus.REJECTED.value
        recipient.responded_at = utc_now()

        # Chi si sfila libera la trattativa: l'invariante 2 esiste per evitare
        # controproposte in parallelo, non per lasciare la richiesta ostaggio di
        # un esaminatore che si è tirato indietro. Gli altri destinatari possono
        # tornare a controproporre — uno alla volta, come prima.
        if request.negotiating_with_id == actor_id:
            request.negotiating_with_id = None

        if not request.pending_recipients():
            from flask_babel import _

            request.status = ExamRequestStatus.EXPIRED.value
            ExamRequestService._notify_requester_closed(
                request,
                _("Nessun esaminatore ha potuto accogliere la tua richiesta."),
            )
        db.session.flush()
        return request

    @staticmethod
    @transactional(domain="exam")
    def cancel(request_id: int, actor: User) -> ExamRequest:
        """Il candidato ritira la richiesta (o lo fa un admin)."""
        request = ExamRequestService._require_negotiable(request_id)
        actor_id = ExamRequestService._require_actor_id(actor)

        if actor_id != request.requester_id and not getattr(actor, "is_admin", False):
            raise PermissionDeniedError("Solo chi l'ha inviata può ritirarla")

        from flask_babel import _

        request.status = ExamRequestStatus.CANCELLED.value
        ExamRequestService._close_other_recipients(
            request,
            winner_id=None,
            message=_("Il candidato ha ritirato la richiesta d'esame."),
        )
        db.session.flush()
        return request

    @staticmethod
    @transactional(domain="exam")
    def expire_pending_requests() -> int:
        """Chiude le richieste per cui il tempo è finito senza accordo.

        Da chiamare periodicamente (``scripts/daily_jobs.py``): senza, una
        trattativa mai conclusa resterebbe aperta per sempre e bloccherebbe le
        richieste successive per lo stesso esame.
        """
        from flask_babel import _

        now = utc_now()
        expired = ExamRequest.query.filter(
            ExamRequest.status == ExamRequestStatus.NEGOTIATING.value,
            ExamRequest.expires_at <= now,
        ).all()

        closed_message = _("La richiesta d'esame è scaduta senza accordo.")
        for request in expired:
            request.status = ExamRequestStatus.EXPIRED.value
            ExamRequestService._close_other_recipients(
                request, winner_id=None, message=closed_message
            )
            ExamRequestService._notify_requester_closed(
                request,
                _(
                    "La tua richiesta d'esame è scaduta senza che si trovasse "
                    "un accordo su data e ora."
                ),
            )
        db.session.flush()
        return len(expired)

    # ────────────────────────────────────────────────────────────────────
    # Interno
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _require_actor_id(actor: Optional[User]) -> int:
        actor_id = getattr(actor, "id", None)
        if actor_id is None:
            raise PermissionDeniedError("Operazione non consentita")
        return actor_id

    @staticmethod
    def _require_negotiable(request_id: int) -> ExamRequest:
        """La richiesta esiste, è in trattativa e non è scaduta."""
        request = ExamRequestService.get_request(request_id)
        if not request.is_open:
            raise ConflictError("Questa richiesta non è più in trattativa")
        if request.is_expired():
            raise ConflictError("Questa richiesta è scaduta")
        return request

    @staticmethod
    def _require_future(scheduled_at: Optional[datetime]) -> datetime:
        if scheduled_at is None:
            raise ValidationError("Serve una data e un'ora per l'appuntamento")
        if scheduled_at <= utc_now():
            raise ValidationError("L'appuntamento deve essere nel futuro")
        return scheduled_at

    @staticmethod
    def _require_hall(billiard_hall_id: Optional[int]) -> int:
        """La sala non è opzionale: l'esame certificato è un evento di persona."""
        from ..location.models import BilliardHall

        if not billiard_hall_id:
            raise ValidationError("Serve una sala per l'appuntamento")
        hall = db.session.get(BilliardHall, billiard_hall_id)
        if hall is None:
            raise NotFoundError("Sala non trovata")
        return hall.id

    @staticmethod
    def _close_other_recipients(
        request: ExamRequest,
        winner_id: Optional[int],
        message: Optional[str] = None,
    ) -> None:
        """Chiude i destinatari rimasti in attesa e li avvisa (US-E4b).

        ``closed`` e non ``rejected``: non hanno detto di no, non hanno fatto in
        tempo. Vederli sparire in silenzio è la lacuna dei match individuali che
        questo dominio non ripete.
        """
        closed_ids: List[int] = []
        for recipient in request.recipients:
            if winner_id is not None and recipient.examiner_id == winner_id:
                continue
            if recipient.is_pending:
                recipient.status = ExamRequestRecipientStatus.CLOSED.value
                closed_ids.append(recipient.examiner_id)

        if closed_ids:
            ExamRequestService._notify_recipients_closed(request, closed_ids, message)

    # ────────────────────────────────────────────────────────────────────
    # Notifiche (best-effort: non devono mai bloccare l'operazione)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _notify(user_ids: Sequence[int], **kwargs: Any) -> None:
        if not user_ids:
            return
        try:
            from ..notification.factory import NotificationFactory

            NotificationFactory.create_bulk_notification(
                user_ids=list(user_ids), continue_on_error=True, **kwargs
            )
        except Exception:  # pragma: no cover - le notifiche non bloccano mai
            logger.warning(
                "Notifica di appuntamento d'esame non inviata", exc_info=True
            )

    @staticmethod
    def _slot_text(request: ExamRequest) -> str:
        """«giovedì 12/06/2026, 21:00 — Biliardo Centrale», in ora italiana."""
        from utils.jinja import format_datetime_local_text

        when = format_datetime_local_text(request.scheduled_at)
        hall = request.billiard_hall.name if request.billiard_hall else ""
        return f"{when} — {hall}" if hall else when

    #: Le route dell'esame arrivano in Fase 5 (blueprint ``exam``, prefix
    #: ``/exam``): questi URL vanno tenuti allineati a quelli veri quando
    #: nascono, altrimenti la notifica porta a un 404.
    @staticmethod
    def _request_url(request: ExamRequest) -> str:
        return f"/exam/requests/{request.id}"

    @staticmethod
    def _notify_request_created(
        request: ExamRequest,
        requester: User,
        recipient_ids: Sequence[int],
        notes: Optional[str],
    ) -> None:
        from flask_babel import _
        from ..notification.models import NotificationPriority, NotificationType

        message = _(
            "%(user)s chiede di sostenere «%(exam)s»: %(slot)s.",
            user=requester.username,
            exam=request.exam.name,
            slot=ExamRequestService._slot_text(request),
        )
        if notes:
            message = f"{message} {notes}"

        ExamRequestService._notify(
            recipient_ids,
            notification_type=NotificationType.EXAM_REQUEST_RECEIVED,
            title=_("Richiesta d'esame"),
            message=message,
            priority=NotificationPriority.NORMAL,
            action_url=ExamRequestService._request_url(request),
            action_text=_("Vedi la richiesta"),
        )

    @staticmethod
    def _notify_counter_proposal(request: ExamRequest, actor: User) -> None:
        from flask_babel import _
        from ..notification.models import NotificationPriority, NotificationType

        if actor.id == request.requester_id:
            # Il candidato rilancia: risponde a chi ha controproposto.
            targets = (
                [request.negotiating_with_id]
                if request.negotiating_with_id
                else [r.examiner_id for r in request.pending_recipients()]
            )
        else:
            targets = [request.requester_id]

        ExamRequestService._notify(
            [t for t in targets if t],
            notification_type=NotificationType.EXAM_TIME_PROPOSED,
            title=_("Nuova proposta di appuntamento"),
            message=_(
                "%(user)s propone «%(exam)s»: %(slot)s.",
                user=actor.username,
                exam=request.exam.name,
                slot=ExamRequestService._slot_text(request),
            ),
            priority=NotificationPriority.NORMAL,
            action_url=ExamRequestService._request_url(request),
            action_text=_("Rispondi"),
        )

    @staticmethod
    def _notify_accepted(request: ExamRequest, actor_id: int, winner_id: int) -> None:
        """Conferma alla controparte: chi accetta sa già com'è andata."""
        from flask_babel import _
        from ..notification.models import NotificationPriority, NotificationType

        target = winner_id if actor_id == request.requester_id else request.requester_id
        ExamRequestService._notify(
            [target],
            notification_type=NotificationType.EXAM_REQUEST_ACCEPTED,
            title=_("Appuntamento d'esame confermato"),
            message=_(
                "«%(exam)s»: appuntamento confermato per %(slot)s.",
                exam=request.exam.name,
                slot=ExamRequestService._slot_text(request),
            ),
            priority=NotificationPriority.HIGH,
            action_url=ExamRequestService._request_url(request),
            action_text=_("Vedi l'appuntamento"),
        )

    @staticmethod
    def _notify_recipients_closed(
        request: ExamRequest, recipient_ids: Sequence[int], message: Optional[str]
    ) -> None:
        from flask_babel import _
        from ..notification.models import NotificationPriority, NotificationType

        ExamRequestService._notify(
            recipient_ids,
            notification_type=NotificationType.EXAM_REQUEST_CLOSED,
            title=_("Richiesta d'esame chiusa"),
            message=message
            or _(
                "La richiesta per «%(exam)s» è stata presa in carico da un "
                "altro esaminatore.",
                exam=request.exam.name,
            ),
            priority=NotificationPriority.LOW,
        )

    @staticmethod
    def _notify_requester_closed(request: ExamRequest, message: str) -> None:
        from flask_babel import _
        from ..notification.models import NotificationPriority, NotificationType

        ExamRequestService._notify(
            [request.requester_id],
            notification_type=NotificationType.EXAM_REQUEST_CLOSED,
            title=_("Richiesta d'esame chiusa"),
            message=message,
            priority=NotificationPriority.NORMAL,
        )


__all__ = ["ExamRequestService", "DEFAULT_EXPIRY_DAYS"]
