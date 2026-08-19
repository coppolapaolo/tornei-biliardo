"""Modello ``Squadra``: elenco squadre di una competizione.

Ogni riga appartiene **o** a un campionato (e allora è condivisa da tutte le
sue gare) **o** a una gara standalone — mai a entrambi, mai a nessuno dei due.
Il vincolo è espresso a livello di DB da un ``CHECK``, non solo in Python:
una riga senza proprietario sarebbe invisibile ovunque e impossibile da
raggiungere dalla UI.
"""

from __future__ import annotations

from ..base import db, BaseModel  # noqa: F401
from ..shared.naming import normalize_list_name


def normalize_squadra_name(name: str) -> str:
    """Forma normalizzata usata per l'unicità e per il confronto.

    Minuscole e spazi interni compattati: "Circolo  X" e "circolo x" sono la
    stessa squadra. Serve a prevenire i doppioni al momento della creazione
    (il campo mostra i nomi simili prima di confermare) invece di doverli
    rincorrere dopo con l'unione.

    Delega a ``normalize_list_name``: squadre e categorie devono normalizzare
    allo stesso modo, altrimenti lo stesso refuso si comporta in modo diverso
    nei due elenchi. Il nome specifico resta come punto d'ingresso storico.
    """
    return normalize_list_name(name)


class Squadra(BaseModel):
    """Una squadra dentro una competizione."""

    __tablename__ = "squadra"
    __table_args__ = (
        db.CheckConstraint(
            "(campionato_id IS NOT NULL AND gara_id IS NULL) "
            "OR (campionato_id IS NULL AND gara_id IS NOT NULL)",
            name="ck_squadra_owner_exclusive",
        ),
        db.UniqueConstraint(
            "campionato_id", "normalized_name", name="uq_squadra_campionato_name"
        ),
        db.UniqueConstraint("gara_id", "normalized_name", name="uq_squadra_gara_name"),
        db.Index("ix_squadra_campionato", "campionato_id"),
        db.Index("ix_squadra_gara", "gara_id"),
    )

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)
    # Denormalizzato invece di calcolato in query: SQLite non ha un indice
    # funzionale portabile, e senza colonna l'unicità case-insensitive non
    # sarebbe imponibile dal DB.
    normalized_name = db.Column(db.String(100), nullable=False)

    campionato_id = db.Column(
        db.Integer,
        db.ForeignKey("campionato.id", ondelete="CASCADE"),
        nullable=True,
    )
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=True
    )

    # Disattivare toglie la squadra dalle scelte future ma la conserva dove è
    # già stata usata: lo storico delle gare giocate non va riscritto.
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    campionato = db.relationship("Campionato", foreign_keys=[campionato_id])
    gara = db.relationship("Gara", foreign_keys=[gara_id])

    def __init__(self, **kwargs):
        name = kwargs.get("name")
        if name is not None:
            kwargs["name"] = " ".join(name.split())
            kwargs.setdefault("normalized_name", normalize_squadra_name(name))
        super().__init__(**kwargs)

    def rename(self, new_name: str) -> None:
        """Rinomina mantenendo allineata la forma normalizzata."""
        self.name = " ".join((new_name or "").split())
        self.normalized_name = normalize_squadra_name(new_name)

    def __repr__(self) -> str:  # pragma: no cover - diagnostica
        owner = (
            f"campionato={self.campionato_id}"
            if self.campionato_id
            else f"gara={self.gara_id}"
        )
        return f"<Squadra {self.name!r} ({owner})>"
