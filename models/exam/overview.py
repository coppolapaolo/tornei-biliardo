"""
Module: models/exam/overview.py
Purpose: Ciò che catalogo e dettaglio degli esami dicono **a chi li guarda**.

Sola lettura. Il catalogo era un elenco di nomi e il dettaglio chiudeva con
quattro statistiche globali che su un esame giovane sono quattro zeri; al
candidato serve sapere cosa è lui per quell'esame — superato e da chi, provato
da solo, mai provato — e qual è il suo prossimo appuntamento. Sono tutti dati
che c'erano già (ADR-042): qui si leggono soltanto, con un numero di query che
non cresce col numero degli esami.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import joinedload

from ..base import db, utc_now
from ..status_enum import (
    ExamAttemptMode,
    ExamAttemptStatus,
    ExamRequestRecipientStatus,
    ExamRequestStatus,
)
from .models import ExamAttempt
from .request_models import ExamRequest, ExamRequestRecipient


class StandingKind(str, Enum):
    """Cosa è un giocatore per un esame. Non si persiste: si deduce."""

    PASSED = "passed"  # l'ha superato davanti a un esaminatore
    FAILED = "failed"  # l'ha sostenuto davanti a un esaminatore, senza superarlo
    PRACTICED = "practiced"  # l'ha provato solo da solo
    NEVER = "never"


class RecipientStance(str, Enum):
    """Dov'è un esaminatore interpellato dentro una trattativa. Si deduce.

    Lo stato persistito del destinatario ha quattro valori, ma alla pagina ne
    servono cinque: ``pending`` vuol dire sia «sta trattando con te» sia «non
    ha mai risposto», e la differenza la fa ``negotiating_with_id`` sulla
    richiesta — è l'invariante 2, letto dal lato di chi guarda.
    """

    # L'ordine dei membri è l'ordine in cui la pagina li elenca.
    ACCEPTED = "accepted"
    NEGOTIATING = "negotiating"  # è l'interlocutore fissato dalla controproposta
    SILENT = "silent"  # interpellato, non si è ancora espresso
    DECLINED = "declined"
    CLOSED = "closed"  # non ha detto di no: ha accettato prima un altro


@dataclass
class ExamStanding:
    kind: StandingKind = StandingKind.NEVER

    # Davanti a un esaminatore. «Superato» non scade: un non superato venuto
    # dopo non lo cancella, quindi data e nome sono quelli dell'ultimo superato
    # — o, se non ce n'è nessuno, dell'ultimo sostenuto.
    certified_count: int = 0
    certified_at: Optional[datetime] = None
    certified_by: Optional[str] = None

    # Da solo: quante volte, il meglio, e primo e ultimo per dire se migliora.
    practice_count: int = 0
    best_score: Optional[int] = None
    best_max: Optional[int] = None
    first_score: Optional[int] = None
    last_score: Optional[int] = None
    last_max: Optional[int] = None


class ExamOverview:
    """Letture per il catalogo e il dettaglio degli esami."""

    @staticmethod
    def standings(user_id: int, exam_ids: Iterable[int]) -> Dict[int, ExamStanding]:
        """Lo stato del giocatore su ciascun esame. Una query sola.

        Contano i tentativi **conclusi**: uno abbandonato non è una prova, e
        uno aperto non è ancora niente.
        """
        ids = list(exam_ids)
        standings = {exam_id: ExamStanding() for exam_id in ids}
        if not ids:
            return standings

        attempts = (
            ExamAttempt.query.options(joinedload(ExamAttempt.examiner))
            .filter(
                ExamAttempt.user_id == user_id,
                ExamAttempt.exam_id.in_(ids),
                ExamAttempt.status == ExamAttemptStatus.COMPLETED.value,
            )
            .order_by(ExamAttempt.completed_at, ExamAttempt.id)
            .all()
        )

        for attempt in attempts:
            standing = standings[attempt.exam_id]
            if attempt.mode == ExamAttemptMode.CERTIFIED.value:
                ExamOverview._add_certified(standing, attempt)
            else:
                ExamOverview._add_practice(standing, attempt)

        for standing in standings.values():
            if standing.kind == StandingKind.NEVER and standing.practice_count:
                standing.kind = StandingKind.PRACTICED
        return standings

    @staticmethod
    def _add_certified(standing: ExamStanding, attempt: ExamAttempt) -> None:
        if attempt.passed is None:
            return
        standing.certified_count += 1
        if attempt.passed or standing.kind != StandingKind.PASSED:
            standing.kind = (
                StandingKind.PASSED if attempt.passed else StandingKind.FAILED
            )
            standing.certified_at = attempt.certified_at or attempt.completed_at
            standing.certified_by = (
                attempt.examiner.username if attempt.examiner else None
            )

    @staticmethod
    def _add_practice(standing: ExamStanding, attempt: ExamAttempt) -> None:
        score = attempt.total_score or 0
        standing.practice_count += 1
        if standing.first_score is None:
            standing.first_score = score
        standing.last_score = score
        standing.last_max = attempt.max_possible_score
        if standing.best_score is None or score > standing.best_score:
            standing.best_score = score
            standing.best_max = attempt.max_possible_score

    @staticmethod
    def upcoming_appointments(user_id: int) -> List[ExamRequest]:
        """Gli appuntamenti confermati ancora da sostenere, dal più vicino.

        Da entrambi i lati del tavolo: chi sostiene e chi esamina hanno lo
        stesso impegno in agenda. Un appuntamento la cui sessione è già chiusa
        non è più un impegno; uno passato da poco resta, perché la sessione si
        apre *da lì* e un esaminatore in ritardo di mezz'ora deve ritrovarlo.
        """
        requests = (
            ExamRequest.query.options(
                joinedload(ExamRequest.exam),
                joinedload(ExamRequest.requester),
                joinedload(ExamRequest.accepted_by),
                joinedload(ExamRequest.billiard_hall),
                joinedload(ExamRequest.attempt),
            )
            .filter(
                ExamRequest.status == ExamRequestStatus.ACCEPTED.value,
                db.or_(
                    ExamRequest.requester_id == user_id,
                    ExamRequest.accepted_by_id == user_id,
                ),
            )
            .order_by(ExamRequest.scheduled_at)
            .all()
        )
        return [
            request
            for request in requests
            if request.attempt is None
            or ExamAttemptStatus.is_open(request.attempt.status)
        ]

    @staticmethod
    def requests_waiting_for(examiner_id: int) -> List[ExamRequest]:
        """Le richieste in trattativa che aspettano una risposta da lui."""
        return (
            ExamRequest.query.options(
                joinedload(ExamRequest.exam), joinedload(ExamRequest.requester)
            )
            .join(ExamRequestRecipient)
            .filter(
                ExamRequestRecipient.examiner_id == examiner_id,
                ExamRequestRecipient.status == ExamRequestRecipientStatus.PENDING.value,
                ExamRequest.status == ExamRequestStatus.NEGOTIATING.value,
                ExamRequest.expires_at > utc_now(),
            )
            .order_by(ExamRequest.scheduled_at)
            .all()
        )

    @staticmethod
    def recipient_stances(
        request: ExamRequest,
    ) -> List[Tuple[ExamRequestRecipient, RecipientStance]]:
        """Ogni interpellato con la sua posizione: prima chi accetta o tratta."""
        by_status = {
            ExamRequestRecipientStatus.ACCEPTED.value: RecipientStance.ACCEPTED,
            ExamRequestRecipientStatus.REJECTED.value: RecipientStance.DECLINED,
            ExamRequestRecipientStatus.CLOSED.value: RecipientStance.CLOSED,
        }
        stances = []
        for recipient in request.recipients:
            stance = by_status.get(recipient.status, RecipientStance.SILENT)
            if (
                stance is RecipientStance.SILENT
                and recipient.examiner_id == request.negotiating_with_id
            ):
                stance = RecipientStance.NEGOTIATING
            stances.append((recipient, stance))
        order = list(RecipientStance)
        stances.sort(key=lambda pair: order.index(pair[1]))
        return stances
