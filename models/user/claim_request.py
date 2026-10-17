"""
Module: models/user/claim_request.py
Purpose: Riscatto di un giocatore non ancora registrato (ADR-086).

Data Structures: ClaimRequest, ClaimRequestRecipient

Chi si registra e si riconosce in un giocatore creato da un direttore o da un
istruttore (ADR-085) **chiede** di prenderne le partite. Sullo schema di
``RoleRequest`` (ADR-041): una richiesta, N destinatari, la prima decisione la
chiude. I destinatari sono chi ha creato il giocatore oppure, per i giocatori
storici senza creatore o col creatore cancellato, l'amministratore. Le regole
stanno in ``models/user/claim_service.py``.
"""

from __future__ import annotations

from ..base import db, BaseModel
from ..status_enum import ClaimRequestStatus


class ClaimRequest(BaseModel):
    """Qualcuno dice di essere un giocatore non registrato.

    ``placeholder_id`` resta sul giocatore riscattato anche dopo l'unione:
    ``UserMergeService`` non lo riassegna, così la richiesta continua a dire
    **chi** è stato riscattato, e non punta all'account che l'ha preso.
    """

    __tablename__ = "claim_request"

    id = db.Column(db.Integer, primary_key=True)
    placeholder_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    claimant_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    status = db.Column(
        db.String(20), nullable=False, default=ClaimRequestStatus.PENDING.value
    )
    decided_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    decided_at = db.Column(db.DateTime, nullable=True)

    placeholder = db.relationship("User", foreign_keys=[placeholder_id])
    claimant = db.relationship("User", foreign_keys=[claimant_id])
    decided_by = db.relationship("User", foreign_keys=[decided_by_id])
    recipients = db.relationship(
        "ClaimRequestRecipient",
        back_populates="request",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Una sola richiesta in attesa per giocatore: se due persone dicessero di
    # essere la stessa, chi decide avrebbe davanti due richieste fra cui
    # scegliere, e una delle due sarebbe comunque sbagliata. Parziale come in
    # RoleRequest: le richieste chiuse restano, come storia.
    __table_args__ = (
        db.Index(
            "uq_claim_request_pending",
            "placeholder_id",
            unique=True,
            sqlite_where=db.text("status = 'pending'"),
        ),
    )

    @property
    def is_pending(self) -> bool:
        return self.status == ClaimRequestStatus.PENDING.value

    @property
    def nome_giocatore(self) -> str:
        """Il nome del giocatore, anche dopo il riscatto.

        Riscattato, il giocatore è anonimizzato: il filtro della soft delete
        lo nasconde e lo username è diventato tecnico. Si legge includendo i
        cancellati, e ``previous_username`` ha il nome.
        """
        from .claim_service import utente_anche_cancellato

        giocatore = utente_anche_cancellato(self.placeholder_id)
        if giocatore is None:
            return ""
        return giocatore.previous_username or giocatore.username

    @property
    def recipient_ids(self) -> set[int]:
        return {r.recipient_id for r in self.recipients}

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ClaimRequest {self.id} {self.claimant_id}→{self.placeholder_id} "
            f"{self.status}>"
        )


class ClaimRequestRecipient(BaseModel):
    """Chi può decidere una ``ClaimRequest``: il creatore, o l'admin."""

    __tablename__ = "claim_request_recipient"

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(
        db.Integer, db.ForeignKey("claim_request.id"), nullable=False, index=True
    )
    recipient_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )

    request = db.relationship("ClaimRequest", back_populates="recipients")
    recipient = db.relationship("User", foreign_keys=[recipient_id])

    __table_args__ = (
        db.UniqueConstraint(
            "request_id", "recipient_id", name="uq_claim_request_recipient"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ClaimRequestRecipient req={self.request_id} user={self.recipient_id}>"
