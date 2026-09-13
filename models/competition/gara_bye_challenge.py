"""
Module: models/competition/gara_bye_challenge.py
Purpose: Model for linking challenge attempts to gara rounds for bye replacement
Requirements: Replace the X (bye) in Amalfi strategy with challenge scores

Design Note (Sprint 11 - December 2025):
    This model was created to decouple the Challenge domain from the Competition
    domain. Previously, ChallengeAttempt had gara_id and round_number fields
    that violated domain separation.

    Now, the Competition domain owns the link between challenge attempts and
    gare through this bridge entity. The Challenge domain remains pure and
    doesn't know about competitions.

    Bye Replacement in Amalfi Strategy:
    When a tournament has an odd number of players, one player gets a "bye"
    (plays against X). Instead of a free win, the player can complete a
    challenge and their score is converted to rack difference.

    See ADR-004-challenge-gara-decoupling.md for rationale.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..base import db, BaseModel, utc_now

if TYPE_CHECKING:
    pass


class GaraByeChallenge(BaseModel):
    """Links a challenge attempt to a gara round for bye replacement.

    This is a bridge entity owned by the Competition domain that creates
    a unidirectional relationship: Competition → Challenge.

    The Challenge domain has no knowledge of this entity or of competitions.

    Usage in Amalfi Strategy:
        When creating a bye match, if challenge_based_bye is enabled:
        1. Player completes a challenge (creates ChallengeAttempt)
        2. This entity links that attempt to the specific gara round
        3. Match result service uses the challenge score for classification
    """

    __tablename__ = "gara_bye_challenge"

    id = db.Column(db.Integer, primary_key=True)

    # Link to the gara (competition)
    gara_id = db.Column(
        db.Integer,
        db.ForeignKey("gara.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Link to the challenge attempt (the actual challenge result)
    challenge_attempt_id = db.Column(
        db.Integer,
        db.ForeignKey("challenge_attempt.id", ondelete="SET NULL"),
        nullable=True,  # Nullable until player completes the challenge
    )

    # Context within the competition
    round_number = db.Column(db.Integer, nullable=False)

    # The user who has the bye in this round
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Link to the bye match (for cross-reference)
    match_id = db.Column(
        db.Integer,
        db.ForeignKey("match.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Status tracking
    is_completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Validazione del direttore. Il punteggio della prova diventa la differenza
    # triangoli di quel turno, cioe' entra dritto in classifica — ma a
    # dichiararlo e' il giocatore stesso, e qui manca il controllo che una
    # partita ha per costruzione: l'avversario. Finche' queste due sono NULL la
    # prova e' giocata ma **non conta**, ed e' uno stato legittimo, non un dato
    # mancante. Il punteggio arriva sul match solo con `validated_at`.
    validated_by_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    validated_at = db.Column(db.DateTime, nullable=True)

    # Relationships (Competition → Challenge direction)
    # Stessa cascata di `RoundConfiguration.gara`: vedi li'.
    gara = db.relationship(
        "Gara",
        backref=db.backref(
            "bye_challenges", cascade="all, delete-orphan", passive_deletes=True
        ),
    )
    challenge_attempt = db.relationship("ChallengeAttempt")
    user = db.relationship("User", foreign_keys=[user_id])
    match = db.relationship("Match")
    validated_by = db.relationship("User", foreign_keys=[validated_by_id])

    # Unique constraint: one bye challenge per user per gara per round
    __table_args__ = (
        db.UniqueConstraint(
            "gara_id", "user_id", "round_number", name="uq_gara_bye_challenge"
        ),
    )

    @classmethod
    def create_for_bye(
        cls,
        gara_id: int,
        user_id: int,
        round_number: int,
        match_id: Optional[int] = None,
    ) -> "GaraByeChallenge":
        """Create a bye challenge entry for a player.

        Called when creating a bye match in Amalfi strategy.

        Args:
            gara_id: The competition ID
            user_id: The player who has the bye
            round_number: The round number
            match_id: Optional link to the bye match

        Returns:
            GaraByeChallenge instance (not yet committed)
        """
        return cls(
            gara_id=gara_id,
            user_id=user_id,
            round_number=round_number,
            match_id=match_id,
            is_completed=False,
        )

    @property
    def is_validated(self) -> bool:
        """La prova conta in classifica solo se il direttore l'ha validata."""
        return self.validated_at is not None

    def validate(self, validated_by_id: int) -> None:
        """Il direttore conferma il punteggio: da qui la prova conta."""
        self.validated_by_id = validated_by_id
        self.validated_at = utc_now()

    def clear_validation(self) -> None:
        """Azzera la validazione. La prova resta registrata, ma non conta piu'."""
        self.validated_by_id = None
        self.validated_at = None

    def complete_with_attempt(self, challenge_attempt_id: int) -> None:
        """Mark bye challenge as completed with a challenge attempt.

        Called when the player completes their challenge.

        Args:
            challenge_attempt_id: The ID of the completed challenge attempt
        """
        self.challenge_attempt_id = challenge_attempt_id
        self.is_completed = True
        self.completed_at = utc_now()

    @classmethod
    def get_pending_for_user(
        cls, gara_id: int, user_id: int
    ) -> Optional["GaraByeChallenge"]:
        """Get pending bye challenge for a user in a gara.

        Args:
            gara_id: The competition ID
            user_id: The player ID

        Returns:
            Pending GaraByeChallenge or None
        """
        return cls.query.filter_by(
            gara_id=gara_id, user_id=user_id, is_completed=False
        ).first()

    @classmethod
    def get_for_round(cls, gara_id: int, round_number: int) -> list["GaraByeChallenge"]:
        """Get all bye challenges for a specific round.

        Args:
            gara_id: The competition ID
            round_number: The round number

        Returns:
            List of GaraByeChallenge for this round
        """
        return cls.query.filter_by(gara_id=gara_id, round_number=round_number).all()

    def __repr__(self) -> str:
        status = "completed" if self.is_completed else "pending"
        return (
            f"<GaraByeChallenge gara={self.gara_id} user={self.user_id} "
            f"round={self.round_number} ({status})>"
        )
