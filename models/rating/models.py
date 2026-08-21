"""Modelli del dominio rating: i punteggi Elo e il registro dei loro delta.

Qui non vivono più le categorie dei giocatori. Fino ad agosto 2026 c'era un
impianto `PlayerCategory` / `HandicapRule` con la scala A/B/C/D cablata in un
enum e la categoria assegnata **globalmente** per utente: nessuna schermata lo
ha mai raggiunto, nessuna riga è mai stata scritta, ed era la forma sbagliata
per il problema — ogni competizione definisce le proprie categorie, con il
vocabolario del proprio paese. Sostituito da `models/categoria/` (ADR-049).
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from enum import Enum


from ..base import db, BaseModel, utc_now

if TYPE_CHECKING:
    pass


class RatingSystem(Enum):
    """Supported rating systems."""

    ELO = "elo"  # Competitivo: SOLO match di torneo. Pilota categoria/handicap.
    ELO_GLOBAL = "elo_global"  # Tornei + casual VALIDATED. SOLO display (dual ELO).
    INTERNAL = "internal"  # Club internal rating
    # A rack, scala FargoRate (base 2/100). Calcolato in parallelo e non
    # mostrato: convive coi pool storici finché non si decide lo scambio
    # (ADR-052). NON è convertibile negli altri due — misura un'altra cosa.
    RACK = "rack"


class PlayerRating(BaseModel):
    """Player rating in various rating systems."""

    __tablename__ = "player_rating"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    rating_system = db.Column(db.Enum(RatingSystem), nullable=False)
    # In virgola mobile per il pool RACK, dove una partita muove il rating di
    # pochi punti e l'arrotondamento a intero sarebbe dello stesso ordine del
    # segnale (ADR-052). Nessuna migration: SQLite ha tipizzazione dinamica e
    # l'affinità INTEGER conserva i decimali — converte a intero solo quando è
    # senza perdita — quindi le righe esistenti restano intere e le nuove
    # scrivono REAL. Su un motore diverso servirebbe un ALTER.
    rating_value = db.Column(db.Float, nullable=False)

    # Rating details
    confidence = db.Column(db.Float, nullable=True)  # Confidence level (0.0-1.0)
    games_played = db.Column(db.Integer, nullable=False, default=0)
    last_updated = db.Column(db.DateTime, nullable=False, default=utc_now)

    # External rating details
    external_id = db.Column(db.String(50), nullable=True)  # ID in external system
    verified = db.Column(db.Boolean, nullable=False, default=False)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    verified_by = db.relationship("User", foreign_keys=[verified_by_id])

    # Unique constraint: one rating per user per system
    __table_args__ = (
        db.UniqueConstraint("user_id", "rating_system", name="uq_user_rating_system"),
    )

    @classmethod
    def get_user_rating(
        cls, user_id: int, rating_system: RatingSystem
    ) -> Optional["PlayerRating"]:
        """Get user's rating in a specific system."""
        return cls.query.filter_by(user_id=user_id, rating_system=rating_system).first()

    def update_rating(self, new_rating: float, games_increment: int = 1) -> None:
        """Update rating value and statistics.

        Nel pool ``RACK`` ``games_increment`` sono i **rack** della partita, non
        uno: lì ``games_played`` è la *robustness*, cioè quanti rack il
        giocatore ha nel sistema, ed è ciò che regola la sensibilità
        dell'aggiornamento. Negli altri pool resta il conteggio delle partite.
        """
        self.rating_value = new_rating
        self.games_played += games_increment
        self.last_updated = utc_now()

    def __repr__(self) -> str:
        return (
            f"<PlayerRating {self.user_id}: "
            f"{self.rating_system.value}={self.rating_value}>"
        )


class MatchRatingHistory(BaseModel):
    """Registro dei delta di rating applicati per ogni match.

    Due scopi:
    1. **Idempotenza**: un match contribuisce al rating ESATTAMENTE una volta.
       Se esiste già un record per (match_id, rating_system) il ricalcolo è un
       no-op — protegge da MatchCompletedEvent ri-emessi (reset→ricompletamento)
       e da recalc_elo lanciato su match già processati.
    2. **Revert**: quando un match viene riaperto/resettato si ripristina
       `old_rating` e si decrementa `games_played`, poi si eliminano i record.

    Nota (Elo è path-dependent): il revert per-match è esatto se il match è
    l'ultimo processato per quei giocatori; altrimenti i rating successivi
    restano approssimati finché non si rilancia `recalc_elo` (ricostruzione
    autorevole). Vedi docstring di RatingCalculationService.
    """

    __tablename__ = "match_rating_history"

    id = db.Column(db.Integer, primary_key=True)
    # Sorgente polimorfa: ESATTAMENTE uno tra match_id / individual_match_id.
    # I match di torneo usano match_id; i casual (dual ELO, pool ELO_GLOBAL)
    # usano individual_match_id. Vedi ADR/dual-ELO.
    match_id = db.Column(
        db.Integer, db.ForeignKey("match.id", ondelete="CASCADE"), nullable=True
    )
    individual_match_id = db.Column(
        db.Integer,
        db.ForeignKey("individual_match.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    rating_system = db.Column(db.Enum(RatingSystem), nullable=False)

    # In virgola mobile per la stessa ragione di `PlayerRating.rating_value`.
    old_rating = db.Column(db.Float, nullable=False)
    new_rating = db.Column(db.Float, nullable=False)
    delta = db.Column(db.Float, nullable=False)
    games_increment = db.Column(db.Integer, nullable=False, default=1)

    user = db.relationship("User", foreign_keys=[user_id])

    # Indici unici parziali: idempotenza per-sorgente senza che le righe con
    # l'altra sorgente NULL collidano tra loro.
    __table_args__ = (
        db.Index(
            "uq_match_user_rating_system",
            "match_id",
            "user_id",
            "rating_system",
            unique=True,
            sqlite_where=db.text("match_id IS NOT NULL"),
        ),
        db.Index(
            "uq_individual_match_user_rating_system",
            "individual_match_id",
            "user_id",
            "rating_system",
            unique=True,
            sqlite_where=db.text("individual_match_id IS NOT NULL"),
        ),
    )

    @classmethod
    def exists_for_match(cls, match_id: int, rating_system: RatingSystem) -> bool:
        """True se esiste già almeno un record per quel match torneo/sistema."""
        return (
            cls.query.filter_by(match_id=match_id, rating_system=rating_system).first()
            is not None
        )

    @classmethod
    def exists_for_individual_match(
        cls, individual_match_id: int, rating_system: RatingSystem
    ) -> bool:
        """True se esiste già almeno un record per quel match individuale/sistema."""
        return (
            cls.query.filter_by(
                individual_match_id=individual_match_id, rating_system=rating_system
            ).first()
            is not None
        )

    def __repr__(self) -> str:
        source = (
            f"match={self.match_id}"
            if self.match_id is not None
            else f"individual_match={self.individual_match_id}"
        )
        return (
            f"<MatchRatingHistory {source} user={self.user_id} "
            f"{self.rating_system.value} {self.old_rating}->{self.new_rating}>"
        )
