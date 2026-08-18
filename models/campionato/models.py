"""
Module: models/campionato/models.py
Purpose: Campionato domain model
Data Structures: Campionato
Dependencies: models.base.db, models.user.models
"""

from typing import TYPE_CHECKING
from models.base import db, utc_now
from models.status_enum import (
    TournamentStatus,
    GaraStatus,
    EntityType,
    ClassificationSystem,
)
from models.matchmaking.configuration import MatchmakingStrategy, OddNumberPolicy

if TYPE_CHECKING:
    pass


class Campionato(db.Model):
    """Core campionato entity with configuration and lifecycle management."""

    __tablename__ = "campionato"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    # Campi configurazione
    campionato_type = db.Column(
        db.String(50), nullable=False, default=MatchmakingStrategy.AMALFI.value
    )  # Matchmaking strategy type (Amalfi, Random, etc.)
    challenge_mode = db.Column(db.Boolean, default=False)  # Challenge drill mode
    planned_gare_count = db.Column(
        db.Integer, nullable=False, default=10
    )  # Target number of gare in campionato

    # Default values inherited by gare
    default_venue_id = db.Column(
        db.Integer, db.ForeignKey("billiard_hall.id"), nullable=True
    )  # Default venue for gare
    default_entry_fee = db.Column(db.Float, nullable=True)  # Default entry fee
    default_rounds_count = db.Column(
        db.Integer, nullable=False, default=3
    )  # Default rounds per gara
    default_odd_policy = db.Column(
        db.String(30), nullable=False, default=OddNumberPolicy.BYE.value
    )  # Default odd number handling (bye, bye_with_challenge, trio)
    default_anti_rematch = db.Column(
        db.Boolean, nullable=False, default=True
    )  # Default anti-rematch setting
    default_classification_system = db.Column(
        db.String(10), nullable=False, default="WINS"
    )  # Default: RACK, WINS, POSITION (see docs/CLASSIFICATION_SYSTEM.md)
    # Punti per posizione delle gare a tabellone, come JSON {"1": 25, ...}
    # (US-17). NULL = usa la tabella di default della spec, che è il caso
    # normale: un campionato non deve configurare nulla per funzionare.
    # Vedi models/classification/position_points.py.
    position_points = db.Column(db.Text, nullable=True)

    # DEPRECATED - To be removed in future migration
    # Use default_odd_policy instead of without_x
    # DEPRECATED: use default_odd_policy
    without_x = db.Column(db.Boolean, default=False)
    # Playoff configuration now in PlayoffConfiguration model
    # DEPRECATED: use PlayoffConfiguration
    final_playoffs = db.Column(db.Boolean, default=True)
    # Scoring is now automatic based on campionato_type
    scoring_policy = db.Column(
        db.String(50), nullable=False, default="classic"
    )  # DEPRECATED: automatic from campionato_type

    # Handicap mode (ereditato da gare/match). Se True i match si giocano con
    # handicap e NON aggiornano il rating Elo. Radice della catena di
    # ereditarietà has_handicap: Campionato → Gara (nullable) → Match (nullable).
    has_handicap = db.Column(db.Boolean, default=False, nullable=False)

    # Status e date
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

    # Termination (manual close before all gare completed)
    terminated_at = db.Column(db.DateTime, nullable=True)

    # Soft delete functionality
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_reason = db.Column(db.String(255), nullable=True)

    # Relazioni
    gare = db.relationship(
        "Gara", backref="campionato", lazy=True, cascade="all, delete-orphan"
    )
    default_venue = db.relationship(
        "BilliardHall", foreign_keys=[default_venue_id], lazy=True
    )

    @property
    def directors(self):
        """Get directors for this campionato."""
        from models.user.models import DirectorAssignment, User

        return (
            db.session.query(User)
            .join(DirectorAssignment, User.id == DirectorAssignment.user_id)
            .filter(
                DirectorAssignment.entity_type == EntityType.CAMPIONATO.value,
                DirectorAssignment.entity_id == self.id,
            )
            .all()
        )

    # Enhanced playoff relationships
    playoff_configurations = db.relationship(
        "PlayoffConfiguration",
        back_populates="campionato",
        cascade="all, delete-orphan",
    )

    def can_be_modified(self):
        """Verifica se il campionato può essere modificato"""
        # Fix: Properly access the relationship collection
        gare = getattr(self, "gare", [])
        for gara in gare:
            # Cannot modify if gara has advanced status or has inscriptions
            if gara.status in [
                GaraStatus.INSCRIPTION.value,
                GaraStatus.PLAYING.value,
                GaraStatus.COMPLETED.value,
            ]:
                return False
            if getattr(gara, "inscriptions", []):  # Se ha iscrizioni
                return False
        return True

    def can_be_deleted(self):
        """Verifica se il campionato può essere cancellato"""
        # Properly access the relationship collection
        gare = getattr(self, "gare", [])
        for gara in gare:
            if getattr(gara, "inscriptions", []):
                return False
        return True

    def get_status(self):
        """Restituisce lo status del campionato.

        Delegates to compute_campionato_status() as single source of truth.
        """
        from models.campionato.statistics_service import compute_campionato_status

        return compute_campionato_status(self)

    def can_create_gara(self) -> bool:
        """Verifica se è possibile creare nuove gare sotto questo campionato."""
        return not self.terminated_at and not self.is_deleted

    def can_be_hard_deleted(self) -> bool:
        """Check if campionato permanently deletable (no matches)."""
        from models.status_enum import MatchStatus

        # Properly access the relationship collections
        gare = getattr(self, "gare", [])
        for gara in gare:
            matches = getattr(gara, "matches", [])
            for match in matches:
                if match.status in [
                    MatchStatus.CLOSED_UNILATERALLY.value,
                    MatchStatus.PLAYING.value,
                ]:
                    return False
        return True

    def get_status_badge_class(self):
        """Restituisce la classe CSS per il badge status"""
        status = self.get_status()
        return {
            TournamentStatus.SETUP.value: "bg-warning",
            TournamentStatus.REGISTRATION_OPEN.value: "bg-info",
            TournamentStatus.IN_PROGRESS.value: "bg-primary",
            TournamentStatus.COMPLETED.value: "bg-success",
            TournamentStatus.TERMINATED.value: "bg-dark",
        }.get(status, "bg-secondary")

    def get_status_text(self):
        """Restituisce il testo dello status"""
        status = self.get_status()
        return {
            TournamentStatus.SETUP.value: "Setup",
            TournamentStatus.REGISTRATION_OPEN.value: "Iscrizioni Aperte",
            TournamentStatus.IN_PROGRESS.value: "In Corso",
            TournamentStatus.COMPLETED.value: "Completato",
            TournamentStatus.TERMINATED.value: "Terminato",
        }.get(status, "Sconosciuto")

    def has_playoff_configurations(self) -> bool:
        """Check if campionato has playoff configurations."""
        configurations = getattr(self, "playoff_configurations", [])
        return len(configurations) > 0

    def can_generate_playoffs(self) -> bool:
        """Check if campionato is ready for playoff generation."""
        return (
            self.get_status() == TournamentStatus.COMPLETED.value
            and self.has_playoff_configurations()
        )

    def all_gare_concluded(self) -> bool:
        """True se tutte le gare attive sono di fatto concluse.

        Una gara è considerata conclusa se ha `status == COMPLETED` oppure
        se il suo stato derivato è `TOURNAMENT_COMPLETED` (tutti i match
        dell'ultimo turno completati ma status ancora PLAYING, non promosso
        — cfr. bug 8 `terminate_campionato`). `ROUND_COMPLETED` NON conta:
        indica un turno finito con altri turni ancora da giocare.

        Ritorna False se non ci sono gare attive.
        """
        from models.status_enum import GaraStatus, ProvaDerivedStatus

        gare = [g for g in (getattr(self, "gare", []) or []) if not g.is_deleted]
        if not gare:
            return False
        for gara in gare:
            if gara.status == GaraStatus.COMPLETED.value:
                continue
            try:
                derived = gara.get_real_status()
            except Exception:
                derived = None
            if derived == ProvaDerivedStatus.TOURNAMENT_COMPLETED.value:
                continue
            return False
        return True

    def is_ready_for_playoff_transition(self) -> bool:
        """True quando il bottone 'Termina Campionato' va presentato come
        'Passa alla fase playoff' (bug 14): campionato non ancora terminato,
        con playoff configurati e tutte le gare di fatto concluse.

        L'azione sottostante resta `terminate_campionato`: è il passo che
        sblocca il successivo 'Avvia Playoff'. Cambia solo il framing UX.
        """
        return (
            not self.terminated_at
            and self.has_playoff_configurations()
            and self.all_gare_concluded()
        )

    def generate_playoff_qualifications(self) -> dict:
        """Generate playoff qualifications for all configurations."""
        if not self.can_generate_playoffs():
            raise ValueError("Campionato is not ready for playoff generation")

        from ..playoff.services import PlayoffService

        return PlayoffService.generate_all_qualifications(self.id)

    def get_playoff_status(self) -> dict:
        """Get comprehensive playoff status."""
        from ..playoff.services import PlayoffService

        return PlayoffService.get_campionato_playoff_status(self.id)

    def soft_delete(self, reason: str = "") -> bool:
        """Perform soft delete on campionato with played matches."""
        if self.is_deleted:
            return False

        self.is_deleted = True
        self.deleted_at = utc_now()
        self.deleted_reason = reason or "Campionato deleted by administrator"
        self.is_active = False

        # Also soft delete related provas
        gare = getattr(self, "gare", [])
        for gara in gare:
            if hasattr(gara, "soft_delete"):
                # Fix: Ensure we pass a string to gara.soft_delete()
                delete_reason = (
                    f"Campionato deleted: {reason}"
                    if reason
                    else "Campionato deleted: Administrator action"
                )
                gara.soft_delete(delete_reason)

        return True

    def restore(self) -> bool:
        """Restore a soft-deleted campionato.

        Also restores all related gare that were soft-deleted with the
        campionato.
        """
        if not self.is_deleted:
            return False

        self.is_deleted = False
        self.deleted_at = None
        self.deleted_reason = None
        self.is_active = True

        # Also restore related gare that were soft-deleted
        gare = getattr(self, "gare", [])
        for gara in gare:
            if hasattr(gara, "is_deleted") and gara.is_deleted:
                if hasattr(gara, "restore"):
                    gara.restore()

        return True

    @property
    def classification_system(self) -> ClassificationSystem:
        """Il sistema di classifica del campionato, normalizzato.

        Unico punto da cui leggere «su cosa si ordina questo campionato». Le
        gare che gli appartengono ereditano il valore e non possono
        cambiarlo dall'interfaccia (`_gara_edit_form.html`), quindi il
        campionato è la fonte per l'intera classifica generale.

        Da non confondere con `campionato_type`, che è la strategia di
        accoppiamento: vedi ADR-047.
        """
        return ClassificationSystem.resolve(self.default_classification_system)

    def get_scoring_system(self) -> dict:
        """Criteri di ordinamento della classifica generale.

        Discendono dal **sistema di classifica**, non dal tipo di campionato.
        Fino al 2026-08 questo metodo derivava i criteri da `campionato_type`
        e si descriveva come «automatic based on campionato type»: era
        l'equivoco all'origine della issue #89, perché tipo e sistema
        coincidono nella configurazione più comune e divergono in silenzio in
        tutte le altre. Vedi ADR-047.
        """
        system = self.classification_system
        if system == ClassificationSystem.RACK:
            return {
                "type": "racks",
                "ordering": ["racks_won", "ssr", "previous_order"],
                "description": "Triangoli totali → SSR → Ordine precedente",
            }
        if system == ClassificationSystem.POSITION:
            return {
                "type": "position",
                "ordering": ["points", "wins", "rack_difference", "previous_order"],
                "description": (
                    "Punti posizione → Vittorie → Differenza triangoli → "
                    "Ordine precedente"
                ),
            }
        return {
            "type": "wins",
            "ordering": ["wins", "rack_difference", "ssr", "previous_order"],
            "description": (
                "Vittorie → Differenza triangoli → SSR → Ordine precedente"
            ),
        }

    def get_scoring_policy_name(self) -> str:
        """DEPRECATED: Use get_scoring_system() instead.

        Get the name of the scoring policy for this campionato.
        Scoring is now automatic based on campionato_type.
        """
        # Return automatic type based on campionato_type
        return self.get_scoring_system()["type"]

    def set_scoring_policy(self, policy_name: str) -> None:
        """DEPRECATED: Scoring policy is now automatic based on campionato_type.

        This method is kept for backwards compatibility but does nothing.
        The scoring system is automatically determined by campionato_type:
        - AMALFI → amalfi scoring
        - RANDOM → random scoring

        Args:
            policy_name: Ignored (kept for API compatibility)
        """
        # No-op: scoring is now automatic

    def _legacy_set_scoring_policy(self, policy_name: str) -> None:
        """Internal legacy method for migration purposes only."""
        valid_policies = ["classic", "elo"]
        if policy_name not in valid_policies:
            raise ValueError(
                f"Invalid scoring policy: {policy_name}. "
                f"Valid options: {valid_policies}"
            )
        self.scoring_policy = policy_name

    @classmethod
    def get_active_campionatos(cls):
        """Get all non-deleted campionati."""
        return cls.query.filter_by(is_deleted=False)

    @classmethod
    def get_deleted_campionatos(cls):
        """Get all soft-deleted campionati."""
        return cls.query.filter_by(is_deleted=True)

    def __repr__(self):
        return f"<Campionato {self.name}>"
