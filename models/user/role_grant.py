"""
Module: models/user/role_grant.py
Purpose: Ruoli concedibili e delega generica (ADR-041).

Data Structures: RoleGrant, RoleRequest, RoleRequestRecipient

Il meccanismo è **generico**: richiesta → approvazione → grant → revoca →
audit. Se la concessione sia a catena (un titolare ne nomina un altro) o
riservata ad admin è una proprietà del **singolo ruolo**
(``GrantPolicy.self_propagating``), non del meccanismo — vedi
``models/user/role_grant_service.py``.

Le tabelle non nominano mai l'esaminatore: ``role`` è una stringa presa da
``GrantableRole``, così che altri ruoli possano adottare lo stesso flusso
senza DDL. ``VenueManagerRequest`` resta fuori: la sua richiesta è *per una
sala*, quindi servirebbe uno scope (``scope_type``/``scope_id``) che qui non
c'è ancora.
"""

from __future__ import annotations

from typing import Optional

from ..base import db, BaseModel, utc_now
from ..status_enum import RoleRequestStatus, RoleRequestRecipientStatus


# ────────────────────────────────────────────────────────────────────────────────
# ROLE GRANT
# ────────────────────────────────────────────────────────────────────────────────
class RoleGrant(BaseModel):
    """Concessione attiva (o revocata) di un ruolo ortogonale a un utente.

    La revoca è **soft**: la riga resta con ``revoked_at``/``revoked_by_id``
    valorizzati, perché US-A3 chiede di poter ricostruire la catena delle
    deleghe (chi ha concesso a chi e quando) anche dopo la revoca.
    """

    __tablename__ = "role_grant"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    role = db.Column(db.String(30), nullable=False, index=True)
    granted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    granted_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])
    granted_by = db.relationship("User", foreign_keys=[granted_by_id])
    revoked_by = db.relationship("User", foreign_keys=[revoked_by_id])

    # Indice UNIQUE **parziale**: un solo grant attivo per (utente, ruolo),
    # ma quante revoche si vuole. Un UniqueConstraint su una colonna booleana
    # (come fa VenueManagement con `is_active`) permetterebbe invece una sola
    # riga revocata per utente/ruolo, rendendo impossibile la seconda revoca.
    __table_args__ = (
        db.Index(
            "uq_role_grant_active",
            "user_id",
            "role",
            unique=True,
            sqlite_where=db.text("revoked_at IS NULL"),
        ),
    )

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def revoke(self, revoked_by_id: int, notes: Optional[str] = None) -> None:
        """Revoca il grant conservando la traccia di chi e quando."""
        self.revoked_at = utc_now()
        self.revoked_by_id = revoked_by_id
        if notes:
            self.notes = notes

    def __repr__(self) -> str:  # pragma: no cover
        state = "active" if self.is_active else "revoked"
        return f"<RoleGrant {self.user_id} {self.role} ({state})>"


# ────────────────────────────────────────────────────────────────────────────────
# ROLE REQUEST
# ────────────────────────────────────────────────────────────────────────────────
class RoleRequest(BaseModel):
    """Richiesta di ottenere un ruolo concedibile.

    A differenza di ``DirectorRequest``, che va implicitamente ad admin, questa
    è **indirizzabile a più destinatari** (US-P8): il richiedente sceglie se
    rivolgersi a tutti i titolari del ruolo o solo ad alcuni. Il primo che
    approva concede il ruolo e chiude la richiesta per gli altri.
    """

    __tablename__ = "role_request"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    role = db.Column(db.String(30), nullable=False, index=True)
    status = db.Column(
        db.String(20), nullable=False, default=RoleRequestStatus.PENDING.value
    )
    requested_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    notes = db.Column(db.Text, nullable=True)
    processed_at = db.Column(db.DateTime, nullable=True)
    processed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    decision_notes = db.Column(db.Text, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])
    processed_by = db.relationship("User", foreign_keys=[processed_by_id])
    recipients = db.relationship(
        "RoleRequestRecipient",
        back_populates="request",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Una sola richiesta pendente per (utente, ruolo). Parziale per lo stesso
    # motivo di RoleGrant: le richieste chiuse devono poter coesistere.
    __table_args__ = (
        db.Index(
            "uq_role_request_pending",
            "user_id",
            "role",
            unique=True,
            sqlite_where=db.text("status = 'pending'"),
        ),
    )

    @property
    def is_pending(self) -> bool:
        return self.status == RoleRequestStatus.PENDING.value

    def pending_recipients(self) -> list["RoleRequestRecipient"]:
        """Destinatari che non si sono ancora espressi."""
        return [
            r
            for r in self.recipients
            if r.status == RoleRequestRecipientStatus.PENDING.value
        ]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RoleRequest {self.id} {self.role} {self.status}>"


# ────────────────────────────────────────────────────────────────────────────────
# ROLE REQUEST RECIPIENT
# ────────────────────────────────────────────────────────────────────────────────
class RoleRequestRecipient(BaseModel):
    """Un destinatario interpellato da una ``RoleRequest``.

    Semantica gemella di ``ProposalInvitation`` nei match individuali: la
    richiesta è una, i destinatari N, e la prima risposta positiva chiude le
    altre.
    """

    __tablename__ = "role_request_recipient"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer, db.ForeignKey("role_request.id"), nullable=False, index=True
    )
    recipient_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    status = db.Column(
        db.String(20), nullable=False, default=RoleRequestRecipientStatus.PENDING.value
    )

    request = db.relationship("RoleRequest", back_populates="recipients")
    recipient = db.relationship("User", foreign_keys=[recipient_id])

    __table_args__ = (
        db.UniqueConstraint(
            "request_id", "recipient_id", name="uq_role_request_recipient"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RoleRequestRecipient req={self.request_id} "
            f"user={self.recipient_id} {self.status}>"
        )
