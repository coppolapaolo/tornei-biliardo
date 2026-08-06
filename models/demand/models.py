"""Modello del segnale-domanda (ADR-036).

Un ``DemandSignal`` è la richiesta esplicita di un giocatore: "vorrei una gara
qui". Porta le proprie coordinate (risolte alla creazione da GPS effimero o dal
centroide di ``home_city``, ADR-034) — NON coordinate persistite sull'utente.
"""

from __future__ import annotations

from ..base import db, BaseModel, utc_now


class DemandSignalStatus:
    """Stati del segnale (stringhe in DB, cfr. convenzione enum del progetto)."""

    ACTIVE = "active"
    CONSUMED = "consumed"  # una gara vicina è stata aperta
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class DemandSignal(BaseModel):
    """Richiesta geolocalizzata di domanda di gare in una zona (ADR-036)."""

    __tablename__ = "demand_signal"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Coordinate della richiesta (sul record, mai sull'utente — ADR-034).
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    # Etichetta città opzionale (per il raggruppamento/lettura).
    city = db.Column(db.String(100), nullable=True)

    status = db.Column(
        db.String(20), nullable=False, default=DemandSignalStatus.ACTIVE, index=True
    )
    expires_at = db.Column(db.DateTime, nullable=False)
    # Prompt di riconferma pre-scadenza inviato (ADR-036 open item 3): evita
    # re-invii; azzerato quando la richiesta viene rinnovata.
    reminded_at = db.Column(db.DateTime, nullable=True)
    consumed_by_gara_id = db.Column(
        db.Integer,
        db.ForeignKey("gara.id", ondelete="SET NULL"),
        nullable=True,
    )

    user = db.relationship("User", foreign_keys=[user_id])

    # Pre-filtro bounding-box delle query di prossimità.
    __table_args__ = (db.Index("ix_demand_signal_lat_lng", "latitude", "longitude"),)

    def is_active(self) -> bool:
        """Attivo e non scaduto."""
        return self.status == DemandSignalStatus.ACTIVE and self.expires_at > utc_now()
