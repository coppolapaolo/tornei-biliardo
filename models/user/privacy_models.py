"""
Module: models/user/privacy_models.py
Purpose: User privacy settings and hidden elements models
Requirements: Allow users to control visibility of profile data and hide specific
elements
"""

from __future__ import annotations

from typing import Dict, Any, TYPE_CHECKING

from ..base import db, BaseModel, utc_now

if TYPE_CHECKING:
    pass


class UserPrivacySetting(BaseModel):
    """User privacy preferences for profile visibility.

    Controls which data categories are visible to other users
    on the public profile. Quasi tutte le impostazioni nascono a False
    (private) per il GDPR: si condivide per scelta esplicita.

    L'eccezione dichiarata e' ``show_elo`` (opt-out) — il perche' e' scritto
    accanto alla colonna.
    """

    __tablename__ = "user_privacy_setting"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One-to-one relationship
    )

    # Privacy toggles - all default to private for GDPR compliance (opt-in)
    show_email = db.Column(db.Boolean, nullable=False, default=False)
    show_phone = db.Column(db.Boolean, nullable=False, default=False)
    show_statistics = db.Column(db.Boolean, nullable=False, default=False)
    show_recent_matches = db.Column(db.Boolean, nullable=False, default=False)
    show_classifications = db.Column(db.Boolean, nullable=False, default=False)
    show_challenge_stats = db.Column(db.Boolean, nullable=False, default=False)

    #: L'unica preferenza **opt-out** del gruppo, e l'eccezione va spiegata.
    #: Le altre nascondono dati che il giocatore ha dato di suo (email,
    #: telefono) o che raccontano come gioca; l'Elo invece e' il numero con cui
    #: due avversari si misurano prima di cominciare, e sul tabellone della
    #: partita serve a tutti e due. Nasconderlo di default vorrebbe dire
    #: spegnere la funzione per chiunque non abbia mai aperto questa pagina —
    #: cioe' per quasi tutti. Chi non lo vuole lo toglie, e da quel momento non
    #: si vede piu' da nessuna parte.
    #:
    #: Conseguenza per chi legge il dato: `can_view_field(..., "elo")` deve
    #: rispondere **True** anche quando la riga di impostazioni non esiste
    #: ancora, al contrario di tutti gli altri campi.
    show_elo = db.Column(db.Boolean, nullable=False, default=True)

    # Relationship
    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        backref=db.backref("privacy_setting", uselist=False),
    )

    @classmethod
    def get_or_create(cls, user_id: int) -> "UserPrivacySetting":
        """Get existing settings or create with defaults.

        Handles race conditions during concurrent creation.

        Args:
            user_id: User ID to get/create settings for

        Returns:
            UserPrivacySetting instance
        """
        setting = cls.query.filter_by(user_id=user_id).first()
        if not setting:
            from sqlalchemy.exc import IntegrityError
            from ..transaction.manager import savepoint

            # Use a savepoint to protect the outer transaction from the IntegrityError
            try:
                with savepoint():
                    setting = cls(user_id=user_id)
                    db.session.add(setting)
            except IntegrityError:
                # If someone else created it in the meantime, fetch it
                setting = cls.query.filter_by(user_id=user_id).first()
                if not setting:
                    # Should not happen if it was an IntegrityError on user_id
                    raise
        return setting

    def to_dict(self) -> Dict[str, Any]:
        """Return settings as dictionary for template use."""
        return {
            "show_email": self.show_email,
            "show_phone": self.show_phone,
            "show_statistics": self.show_statistics,
            "show_recent_matches": self.show_recent_matches,
            "show_classifications": self.show_classifications,
            "show_challenge_stats": self.show_challenge_stats,
            "show_elo": self.show_elo,
        }


class HiddenMatch(BaseModel):
    """Tracks matches hidden by a user from their public profile.

    Users can hide specific matches they participated in.
    The match is still visible to admins and in tournament results,
    but won't appear on the user's public profile.
    """

    __tablename__ = "hidden_match"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_id = db.Column(
        db.Integer,
        db.ForeignKey("match.id", ondelete="CASCADE"),
        nullable=False,
    )
    hidden_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint("user_id", "match_id", name="uq_hidden_match_user_match"),
    )

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    match = db.relationship("Match", foreign_keys=[match_id])


class HiddenInscription(BaseModel):
    """Tracks inscriptions (gare) hidden by a user from their public profile.

    Users can hide their participation in specific gare.
    The inscription is still visible to directors and in tournament results,
    but won't appear on the user's public profile.
    """

    __tablename__ = "hidden_inscription"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    inscription_id = db.Column(
        db.Integer,
        db.ForeignKey("inscription.id", ondelete="CASCADE"),
        nullable=False,
    )
    hidden_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "inscription_id", name="uq_hidden_inscription_user_inscription"
        ),
    )

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    inscription = db.relationship("Inscription", foreign_keys=[inscription_id])


class HiddenCampionato(BaseModel):
    """Tracks campionati hidden by a user from their public profile.

    Users can hide their participation in entire campionati.
    All gare and matches within the campionato will be hidden
    from the user's public profile.
    """

    __tablename__ = "hidden_campionato"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    campionato_id = db.Column(
        db.Integer,
        db.ForeignKey("campionato.id", ondelete="CASCADE"),
        nullable=False,
    )
    hidden_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "campionato_id", name="uq_hidden_campionato_user_campionato"
        ),
    )

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    campionato = db.relationship("Campionato", foreign_keys=[campionato_id])
