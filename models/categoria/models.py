"""Modello ``Categoria``: le categorie di gioco di una competizione.

Stessa forma di ``Squadra`` (ADR-039) e per la stessa ragione: l'elenco
appartiene **o** a un campionato — e allora è condiviso da tutte le sue gare —
**o** a una gara standalone, mai a entrambi. Il vincolo è un ``CHECK`` a
livello di DB, perché una riga senza proprietario sarebbe irraggiungibile
dalla UI e invisibile ovunque.

Perché per competizione e non un'anagrafica globale: «C, B, A, N» è la scala
della federazione italiana per il pool, ma aggiungere «E» per gli esordienti è
una scelta arbitraria di chi organizza, e altrove nel mondo il vocabolario è
un altro. Un elenco unico d'istanza renderebbe chi lo cura il collo di
bottiglia di ogni torneo.

Nessuna colonna d'ordinamento: le categorie si mostrano in ordine alfabetico.
La regola che le usa — l'ELO nelle gare con handicap — confronta soltanto
l'uguaglianza, quindi l'ordine non le serve. Scelta presa sapendo che
l'alfabeto mente su questa scala (``A B C E N`` mette gli esordienti prima dei
nazionali). Quando arriverà l'handicap sul punteggio, dove la differenza fra
due categorie *è* il numero di rack, servirà aggiungere l'ordine: è una
colonna, non un rifacimento. Vedi ADR-049.
"""

from __future__ import annotations

from ..base import db, BaseModel  # noqa: F401
from ..shared.naming import clean_display_name, normalize_list_name

#: I nomi delle categorie sono sigle o parole singole: "N", "B", "Esordienti".
MAX_NAME_LENGTH = 50


class Categoria(BaseModel):
    """Una categoria di gioco dentro una competizione."""

    __tablename__ = "categoria"
    __table_args__ = (
        db.CheckConstraint(
            "(campionato_id IS NOT NULL AND gara_id IS NULL) "
            "OR (campionato_id IS NULL AND gara_id IS NOT NULL)",
            name="ck_categoria_owner_exclusive",
        ),
        db.UniqueConstraint(
            "campionato_id", "normalized_name", name="uq_categoria_campionato_name"
        ),
        db.UniqueConstraint(
            "gara_id", "normalized_name", name="uq_categoria_gara_name"
        ),
        db.Index("ix_categoria_campionato", "campionato_id"),
        db.Index("ix_categoria_gara", "gara_id"),
    )

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(MAX_NAME_LENGTH), nullable=False)
    # Denormalizzato invece di calcolato in query: SQLite non ha un indice
    # funzionale portabile, e senza colonna l'unicità case-insensitive non
    # sarebbe imponibile dal DB. È ciò che fa collassare "B", "b" e " B ".
    normalized_name = db.Column(db.String(MAX_NAME_LENGTH), nullable=False)

    campionato_id = db.Column(
        db.Integer,
        db.ForeignKey("campionato.id", ondelete="CASCADE"),
        nullable=True,
    )
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=True
    )

    # Disattivare toglie la categoria dalle scelte future e la conserva dove è
    # già stata usata: le gare giocate non si riscrivono.
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    campionato = db.relationship("Campionato", foreign_keys=[campionato_id])
    gara = db.relationship("Gara", foreign_keys=[gara_id])

    def __init__(self, **kwargs):
        name = kwargs.get("name")
        if name is not None:
            kwargs["name"] = clean_display_name(name)
            kwargs.setdefault("normalized_name", normalize_list_name(name))
        super().__init__(**kwargs)

    def rename(self, new_name: str) -> None:
        """Rinomina mantenendo allineata la forma normalizzata."""
        self.name = clean_display_name(new_name)
        self.normalized_name = normalize_list_name(new_name)

    def __repr__(self) -> str:  # pragma: no cover - diagnostica
        owner = (
            f"campionato={self.campionato_id}"
            if self.campionato_id
            else f"gara={self.gara_id}"
        )
        return f"<Categoria {self.name!r} ({owner})>"
