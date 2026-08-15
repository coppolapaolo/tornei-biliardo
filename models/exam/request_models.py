"""
Module: models/exam/request_models.py
Purpose: L'appuntamento d'esame — richiesta a più esaminatori e negoziazione di
         data, ora e sala (ADR-042).
Data Structures: ExamRequest, ExamRequestRecipient, ExamTimeProposal

**Entità gemelle di ``MatchProposal``/``ProposalInvitation``, non un'astrazione
condivisa.** Si riusano pattern, indici e semantica; non le tabelle. Due motivi:

1. ``MatchProposal`` porta sette colonne di configurazione di gioco
   (disciplina, distanza, regola di spacco, multi-set…) e una 1:1 hardcodata
   con ``IndividualMatch``. Un esame non ha nulla di tutto ciò.
2. Soprattutto: **il ciclo di vita diverge nel punto critico.** Là l'orario lo
   fissa il proponente e il destinatario può solo accettare o rifiutare; qui si
   contrattano a oltranza, il che introduce stati e invarianti che
   ``MatchProposal`` non ha e non avrebbe motivo di avere.

La negoziazione regge su due invarianti, entrambi presidiati nel servizio
(``models/exam/request_service.py``) e leggibili qui dai campi che li portano:

- **Può accettare solo chi non ha fatto l'ultima proposta**
  (``last_proposed_by_id``): altrimenti si accetterebbe la propria.
- **La prima controproposta fissa l'interlocutore** (``negotiating_with_id``).
  Da lì la trattativa è a due; gli altri destinatari possono solo accettare
  l'ultima proposta com'è, o lasciar scadere. Senza questo vincolo N
  esaminatori controproporrebbero in parallelo sullo stesso ``scheduled_at`` e
  l'ultimo a scrivere sovrascriverebbe gli altri in silenzio.

Il presidio anti-TOCTOU **non** può essere quello dei match. Là accettare crea
subito l'``IndividualMatch``, quindi è l'indice UNIQUE su
``individual_match.proposal_id`` a far vincere un solo accettante. Qui
accettare fissa **solo** l'appuntamento — l'``ExamAttempt`` nasce molto dopo,
all'apertura della sessione. Da cui i due presidi di questo modulo:

- ``uq_exam_request_accepted (request_id) WHERE status = 'accepted'`` su
  ``exam_request_recipient``: un solo destinatario può risultare accettante;
- l'accettazione come UPDATE condizionato con controllo del rowcount nel
  servizio, così il perdente riceve un ``ConflictError`` invece di
  sovrascrivere silenziosamente il vincitore.
"""

from __future__ import annotations

from typing import List, Optional

from ..base import db, BaseModel, utc_now
from ..status_enum import ExamRequestRecipientStatus, ExamRequestStatus


class ExamRequest(BaseModel):
    """Richiesta di sostenere un esame certificato, rivolta a N esaminatori.

    ``scheduled_at`` e ``billiard_hall_id`` sono lo slot **corrente** in
    negoziazione, non lo storico: quello sta in ``ExamTimeProposal``, perché il
    ciclo può durare più giri e va mostrato a entrambe le parti.
    """

    __tablename__ = "exam_request"

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(
        db.Integer,
        db.ForeignKey("exam.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requester_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    status = db.Column(
        db.String(20), nullable=False, default=ExamRequestStatus.NEGOTIATING.value
    )

    # Slot corrente: l'ultima proposta sul tavolo. La sala non è opzionale —
    # l'esame certificato è un evento di persona, e senza un posto dove
    # trovarsi non c'è appuntamento. (Diverso da ``MatchProposal``, dove il
    # campo è nullable solo per compatibilità con la vecchia ``location`` a
    # testo libero.)
    billiard_hall_id = db.Column(
        db.Integer, db.ForeignKey("billiard_hall.id"), nullable=False
    )
    scheduled_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)

    # Invariante 1: non può accettare chi ha fatto l'ultima proposta.
    last_proposed_by_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    # Invariante 2: NULL finché nessuno ha controproposto; poi è l'unico
    # esaminatore ammesso a proseguire lo scambio.
    negotiating_with_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    accepted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)

    exam = db.relationship("Exam")
    requester = db.relationship("User", foreign_keys=[requester_id])
    last_proposed_by = db.relationship("User", foreign_keys=[last_proposed_by_id])
    negotiating_with = db.relationship("User", foreign_keys=[negotiating_with_id])
    accepted_by = db.relationship("User", foreign_keys=[accepted_by_id])
    billiard_hall = db.relationship("BilliardHall")

    recipients = db.relationship(
        "ExamRequestRecipient",
        back_populates="request",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    time_proposals = db.relationship(
        "ExamTimeProposal",
        back_populates="request",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ExamTimeProposal.created_at",
    )
    # La sessione nata da questo appuntamento, se è stata aperta. uselist=False
    # perché l'indice UNIQUE su ``exam_attempt.exam_request_id`` ne ammette una
    # sola: dallo stesso appuntamento non nascono due sessioni.
    attempt = db.relationship(
        "ExamAttempt", back_populates="exam_request", uselist=False
    )

    @property
    def is_open(self) -> bool:
        """True se la richiesta è ancora in trattativa."""
        return ExamRequestStatus.is_open(self.status)

    def is_expired(self) -> bool:
        """True se il tempo per trovare l'accordo è finito."""
        return utc_now() > self.expires_at

    @property
    def is_accepted(self) -> bool:
        return self.status == ExamRequestStatus.ACCEPTED.value

    def recipient_for(self, user_id: Optional[int]) -> Optional["ExamRequestRecipient"]:
        """Il destinatario corrispondente all'utente, se è fra gli interpellati."""
        if user_id is None:
            return None
        return next((r for r in self.recipients if r.examiner_id == user_id), None)

    def pending_recipients(self) -> List["ExamRequestRecipient"]:
        """Destinatari che non si sono ancora espressi."""
        return [
            r
            for r in self.recipients
            if r.status == ExamRequestRecipientStatus.PENDING.value
        ]

    def recipient_ids(self) -> List[int]:
        return [r.examiner_id for r in self.recipients]

    @property
    def current_proposal(self) -> Optional["ExamTimeProposal"]:
        """La proposta sul tavolo: l'unica non ancora superata."""
        live = [p for p in self.time_proposals if p.superseded_at is None]
        return live[-1] if live else None

    def __repr__(self) -> str:  # pragma: no cover - banale
        return (
            f"<ExamRequest {self.id} exam={self.exam_id} "
            f"requester={self.requester_id} {self.status}>"
        )


class ExamRequestRecipient(BaseModel):
    """Un esaminatore interpellato da una ``ExamRequest``.

    Semantica gemella di ``ProposalInvitation``: la richiesta è una, i
    destinatari N, e la prima accettazione chiude le altre — con la notifica
    che nei match individuali manca (US-E4b).
    """

    __tablename__ = "exam_request_recipient"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer,
        db.ForeignKey("exam_request.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    examiner_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    status = db.Column(
        db.String(20),
        nullable=False,
        default=ExamRequestRecipientStatus.PENDING.value,
    )
    responded_at = db.Column(db.DateTime, nullable=True)

    request = db.relationship("ExamRequest", back_populates="recipients")
    examiner = db.relationship("User", foreign_keys=[examiner_id])

    __table_args__ = (
        db.UniqueConstraint(
            "request_id", "examiner_id", name="uq_exam_request_recipient"
        ),
        # Presidio anti-TOCTOU: **un solo accettante per richiesta**. Parziale,
        # perché gli altri destinatari devono poter coesistere in `pending`,
        # `rejected` o `closed` quanti sono. È l'equivalente, per l'esame, di
        # ciò che nei match fa l'indice su ``individual_match.proposal_id``:
        # là accettare crea il match, qui accettare fissa solo l'appuntamento.
        db.Index(
            "uq_exam_request_accepted",
            "request_id",
            unique=True,
            sqlite_where=db.text("status = 'accepted'"),
        ),
    )

    @property
    def is_pending(self) -> bool:
        return self.status == ExamRequestRecipientStatus.PENDING.value

    def __repr__(self) -> str:  # pragma: no cover - banale
        return (
            f"<ExamRequestRecipient req={self.request_id} "
            f"examiner={self.examiner_id} {self.status}>"
        )


class ExamTimeProposal(BaseModel):
    """Una proposta di data, ora e sala dentro la negoziazione.

    Lo storico serve: il ciclo può durare più giri e va mostrato a entrambe le
    parti, che devono poter vedere *chi* ha proposto *cosa* e quando — non solo
    l'ultimo slot rimasto in piedi.
    """

    __tablename__ = "exam_time_proposal"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer,
        db.ForeignKey("exam_request.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    billiard_hall_id = db.Column(
        db.Integer, db.ForeignKey("billiard_hall.id"), nullable=False
    )
    # Valorizzato quando arriva la controproposta successiva: la proposta viva
    # è l'unica con questo campo a NULL.
    superseded_at = db.Column(db.DateTime, nullable=True)

    request = db.relationship("ExamRequest", back_populates="time_proposals")
    proposed_by = db.relationship("User", foreign_keys=[proposed_by_id])
    billiard_hall = db.relationship("BilliardHall")

    def supersede(self) -> None:
        """Ritira la proposta perché ne è arrivata una nuova."""
        if self.superseded_at is None:
            self.superseded_at = utc_now()

    def __repr__(self) -> str:  # pragma: no cover - banale
        return (
            f"<ExamTimeProposal req={self.request_id} "
            f"by={self.proposed_by_id} at={self.scheduled_at}>"
        )
