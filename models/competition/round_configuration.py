"""
Module: models/competition/round_configuration.py
Purpose: Override per turno della configurazione di gioco di una gara
Requirements: ADR-027 (round-level configuration enforcement)

Ogni colonna nullable rappresenta un override: NULL = eredita dal default
della gara. La conversione concreta in valori effettivi avviene tramite
`get_effective_*` o tramite `to_match_overrides()`, che fornisce un dict
pronto per essere espanso negli kwarg di `Match(...)`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from models.base import db, BaseModel

if TYPE_CHECKING:
    pass


class RoundConfiguration(BaseModel):
    """Override per un turno specifico di una gara."""

    __tablename__ = "round_configuration"

    id = db.Column(db.Integer, primary_key=True)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=False
    )
    round_number = db.Column(db.Integer, nullable=False)

    # Override: NULL = eredita da gara
    discipline = db.Column(db.String(50), nullable=True)
    distance = db.Column(db.Integer, nullable=True)
    is_race_to = db.Column(db.Boolean, nullable=True)
    is_multi_set = db.Column(db.Boolean, nullable=True)
    match_distance = db.Column(db.Integer, nullable=True)
    is_race_to_sets = db.Column(db.Boolean, nullable=True)

    # Deprecated: pre-ADR-027 usava `best_of` ma era dead code (mai popolato).
    # Lo manteniamo per compat schema, la migration ne ha già travasato i
    # valori in `is_race_to`.
    best_of = db.Column(db.Boolean, nullable=True)

    notes = db.Column(db.Text, nullable=True)

    gara = db.relationship("Gara", backref="round_configurations")

    __table_args__ = (
        db.UniqueConstraint(
            "gara_id", "round_number", name="uq_gara_round_configuration"
        ),
    )

    @classmethod
    def get_for_gara_round(
        cls, gara_id: int, round_number: int
    ) -> Optional["RoundConfiguration"]:
        return cls.query.filter_by(gara_id=gara_id, round_number=round_number).first()

    @classmethod
    def get_all_for_gara(cls, gara_id: int) -> List["RoundConfiguration"]:
        return cls.query.filter_by(gara_id=gara_id).order_by(cls.round_number).all()

    @classmethod
    def create_or_update(
        cls,
        gara_id: int,
        round_number: int,
        *,
        discipline: Optional[str] = None,
        distance: Optional[int] = None,
        is_race_to: Optional[bool] = None,
        is_multi_set: Optional[bool] = None,
        match_distance: Optional[int] = None,
        is_race_to_sets: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> "RoundConfiguration":
        """Upsert. Solo i campi non-None sovrascrivono lo stato esistente.

        Per cancellare un override esistente passare il valore esplicito
        (es. distance=gara.distance) oppure usare delete_for_round.
        """
        config = cls.get_for_gara_round(gara_id, round_number)
        if not config:
            config = cls(gara_id=gara_id, round_number=round_number)
            db.session.add(config)

        if discipline is not None:
            config.discipline = discipline
        if distance is not None:
            config.distance = distance
        if is_race_to is not None:
            config.is_race_to = is_race_to
        if is_multi_set is not None:
            config.is_multi_set = is_multi_set
        if match_distance is not None:
            config.match_distance = match_distance
        if is_race_to_sets is not None:
            config.is_race_to_sets = is_race_to_sets
        if notes is not None:
            config.notes = notes

        return config

    @classmethod
    def delete_for_round(cls, gara_id: int, round_number: int) -> bool:
        """Rimuove l'override per un singolo turno. True se cancellato."""
        deleted = cls.query.filter_by(
            gara_id=gara_id, round_number=round_number
        ).delete()
        return deleted > 0

    @classmethod
    def delete_for_gara(cls, gara_id: int) -> None:
        cls.query.filter_by(gara_id=gara_id).delete()

    def get_effective_discipline(self, fallback_discipline: str) -> str:
        return self.discipline if self.discipline else fallback_discipline

    def get_effective_distance(self, fallback_distance: int) -> int:
        return self.distance if self.distance is not None else fallback_distance

    def get_effective_is_race_to(self, fallback_is_race_to: bool) -> bool:
        return self.is_race_to if self.is_race_to is not None else fallback_is_race_to

    def get_effective_is_multi_set(self, fallback: bool) -> bool:
        return self.is_multi_set if self.is_multi_set is not None else fallback

    def get_effective_match_distance(self, fallback: Optional[int]) -> Optional[int]:
        return self.match_distance if self.match_distance is not None else fallback

    def get_effective_is_race_to_sets(self, fallback: bool) -> bool:
        return self.is_race_to_sets if self.is_race_to_sets is not None else fallback

    # Deprecated: usa get_effective_is_race_to. Mantenuto per back-compat.
    def get_effective_best_of(self, fallback_best_of: bool) -> bool:
        return self.get_effective_is_race_to(fallback_best_of)

    def distanza_effettiva(self, gara):
        """La distanza di questo turno come `Distance`, con i ripieghi della gara.

        Serve a descrivere il turno dove si descrive la gara — testata e
        informazioni — senza riscrivere la regola dei ripieghi
        (`to_match_overrides` la conosce gia').
        """
        from models.match.distance import Distance

        valori = self.to_match_overrides(gara)
        if valori["is_multi_set"]:
            return Distance(
                racks=self.get_effective_distance(gara.distance),
                is_race_to_racks=valori["is_race_to"],
                is_multi_set=True,
                sets=valori["match_distance"] or 1,
                is_race_to_sets=valori["is_race_to_sets"],
            )
        return Distance(
            racks=self.get_effective_distance(gara.distance),
            is_race_to_racks=valori["is_race_to"],
        )

    def has_overrides(self) -> bool:
        return any(
            v is not None
            for v in (
                self.discipline,
                self.distance,
                self.is_race_to,
                self.is_multi_set,
                self.match_distance,
                self.is_race_to_sets,
            )
        )

    def to_match_overrides(self, gara) -> Dict[str, Any]:
        """Materializza la config effettiva (override + fallback gara) come
        kwargs per Match(...). Risolve qui i fallback in modo da centralizzare
        la regola in un solo punto, evitando duplicazione in round_creation.
        """
        return {
            "discipline": self.get_effective_discipline(gara.discipline),
            "match_distance": self.get_effective_match_distance(gara.distance),
            "is_race_to": self.get_effective_is_race_to(gara.is_race_to),
            "is_multi_set": self.get_effective_is_multi_set(gara.is_multi_set),
            "is_race_to_sets": self.get_effective_is_race_to_sets(
                getattr(gara, "is_race_to_sets", True)
            ),
        }

    def __repr__(self) -> str:
        return (
            f"<RoundConfiguration gara_id={self.gara_id} "
            f"round={self.round_number} discipline={self.discipline} "
            f"distance={self.distance} is_race_to={self.is_race_to}>"
        )
