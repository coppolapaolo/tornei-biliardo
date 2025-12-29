# utils/permissions.py
"""
Permission decorators for route protection.

This module centralizes all permission-related decorators used across routes.
Local imports are used intentionally to avoid circular dependencies between
utils and models packages - this is the recommended pattern for Flask applications.

Usage:
    from utils import admin_required, player_only
    # or
    from utils.permissions import admin_required, player_only

Decorator Categories:
    - Role-based: admin_required, director_required, player_only
    - Entity ownership: inscription_owner_required, challenge_attempt_player_required
    - Match participation: match_player_required, rack_player_required
    - Management: campionato_manager_required, gara_manager_required, venue_manager_required
"""

from functools import wraps
from flask import abort, flash, redirect, url_for, request
from flask_login import current_user

from models.user.permissions import PermissionChecker, RoleRequirement

# --------------------------------------------------------------------------
# Role-based decorators (delegate to RoleRequirement)
# --------------------------------------------------------------------------


def admin_required(f):
    """Permette l'accesso solo ad admin."""
    return RoleRequirement.admin_required(f)


def director_required(f):
    """Permette l'accesso solo a direttori."""
    return RoleRequirement.director_required(f)


def director_or_admin_required(f):
    """Permette l'accesso a direttore o admin."""
    return RoleRequirement.director_or_admin_required(f)


def campionato_manager_required(campionato_id_getter):
    """Permette l'accesso a chi gestisce il campionato indicato."""
    return RoleRequirement.campionato_manager_required(campionato_id_getter)


# --------------------------------------------------------------------------
# Entity management decorators
# --------------------------------------------------------------------------


def gara_manager_required(fn):
    """Permette l'accesso solo a chi può gestire la gara specificata.

    Supports both standalone garas (director assignment) and
    campionato garas (via campionato permissions).
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        from models import Gara, db  # Local import to avoid circular dependency

        gara_id = kwargs.get("gara_id") or (
            request.view_args.get("gara_id") if request.view_args else None
        )
        gara = db.session.get(Gara, gara_id)

        if getattr(current_user, "is_admin", False):
            return fn(*args, **kwargs)

        # Standalone: serve essere DIRECTOR e essere il director assegnato o co-direttore
        if gara and getattr(gara, "campionato_id", None) is None:
            if not getattr(current_user, "is_director", False):
                abort(403)

            # Director principale
            if gara.director_id == current_user.id:
                return fn(*args, **kwargs)

            # Co-direttore via DirectorAssignment
            from models.user.models import DirectorAssignment

            is_co_director = (
                db.session.query(DirectorAssignment)
                .filter(
                    DirectorAssignment.entity_type == "gara",
                    DirectorAssignment.entity_id == gara_id,
                    DirectorAssignment.user_id == current_user.id,
                )
                .first()
                is not None
            )
            if not is_co_director:
                abort(403)
            return fn(*args, **kwargs)

        # Campionati: lascia l'implementazione esistente (assegnazione su campionato)
        return fn(*args, **kwargs)

    return wrapper


def match_manager_required(f):
    """Permette l'inserimento dei risultati match solo a chi gestisce il match."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        match_id = kwargs.get("match_id")
        if match_id is None:
            abort(400)  # Bad request if match_id is missing
        if not PermissionChecker.can_insert_match_results(current_user, match_id):
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


def venue_manager_required(f):
    """Permette l'accesso solo a chi gestisce la venue specificata."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated first
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))

        venue_id = kwargs.get("venue_id")
        if venue_id is None:
            abort(400)  # Bad request if venue_id is missing

        # Check if user can manage this venue
        if not current_user.can_manage_venue(venue_id):
            abort(403)

        return f(*args, **kwargs)

    return decorated_function


def rack_manager_required(f):
    """Richiede che l'utente possa gestire il campionato collegato al rack."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import Rack  # Local import to avoid circular dependency

        rack_id = kwargs.get("rack_id")
        rack = Rack.query.get_or_404(rack_id)
        gara = rack.match.gara
        campionato_id = gara.campionato_id

        # Admin può sempre gestire
        if getattr(current_user, "is_admin", False):
            return f(*args, **kwargs)

        # Standalone: serve essere DIRECTOR e essere il director assegnato o co-direttore
        if campionato_id is None:  # Gara standalone
            if not getattr(current_user, "is_director", False):
                flash("Non puoi gestire i rack di questa gara.", "error")
                return redirect(url_for("dashboard.dashboard"))

            # Director principale
            if hasattr(gara, "director_id") and gara.director_id == current_user.id:
                return f(*args, **kwargs)

            # Co-direttore via DirectorAssignment
            from models.user.models import DirectorAssignment
            from models import db  # Local import to avoid circular dependency

            gara_id = gara.id
            is_co_director = (
                db.session.query(DirectorAssignment)
                .filter(
                    DirectorAssignment.entity_type == "gara",
                    DirectorAssignment.entity_id == gara_id,
                    DirectorAssignment.user_id == current_user.id,
                )
                .first()
                is not None
            )
            if not is_co_director:
                flash("Non puoi gestire i rack di questa gara.", "error")
                return redirect(url_for("dashboard.dashboard"))
            return f(*args, **kwargs)

        # Gara con campionato: usa la logica standard
        def _get_tid(**_ignored):
            return campionato_id

        return campionato_manager_required(_get_tid)(f)(*args, **kwargs)

    return decorated_function


def trio_manager_required(f):
    """Accesso a admin / direttore per trio."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import TrioMatch  # Local import to avoid circular dependency

        trio_id = kwargs.get("trio_id")
        trio = TrioMatch.query.get_or_404(trio_id)
        campionato_id = trio.match.gara.campionato_id

        def _get_tid(**_ignored):
            return campionato_id

        return campionato_manager_required(_get_tid)(f)(*args, **kwargs)

    return decorated_function


# --------------------------------------------------------------------------
# Player access decorators
# --------------------------------------------------------------------------


def player_only(f):
    """Blocca l'accesso admin a route dedicate ai player."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and current_user.is_admin:
            flash(
                "Funzionalità riservata ai giocatori. "
                "Utilizzare la dashboard amministratore.",
                "warning",
            )
            return redirect(url_for("dashboard.dashboard"))
        return f(*args, **kwargs)

    return decorated_function


def player_required(f):
    """Permette l'accesso solo a giocatori iscritti alla gara specificata."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import Inscription  # Local import to avoid circular dependency

        gara_id = kwargs.get("gara_id")
        if not gara_id:
            abort(400)  # Bad request if gara_id is missing

        # Check if user is enrolled in this gara
        inscription = Inscription.query.filter_by(
            user_id=current_user.id, gara_id=gara_id
        ).first()

        if not inscription:
            flash("Non sei iscritto a questa gara.", "error")
            return redirect(url_for("dashboard.dashboard"))

        return f(*args, **kwargs)

    return decorated_function


def match_player_required(f):
    """Permette l'accesso solo ai giocatori della partita specificata."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import Match  # Local import to avoid circular dependency

        match_id = kwargs.get("match_id")
        if not match_id:
            abort(400)  # Bad request if match_id is missing

        # Check if user is a player in this match
        match = Match.query.get(match_id)
        if not match:
            abort(404)

        if current_user.id not in [match.player1_id, match.player2_id]:
            flash("Non sei un giocatore di questa partita.", "error")
            return redirect(url_for("dashboard.dashboard"))

        return f(*args, **kwargs)

    return decorated_function


def rack_player_required(f):
    """Permette l'accesso solo ai giocatori del rack specificato."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import Rack  # Local import to avoid circular dependency

        rack_id = kwargs.get("rack_id")
        if not rack_id:
            abort(400)  # Bad request if rack_id is missing

        # Check if user is a player in the match associated with this rack
        rack = Rack.query.get(rack_id)
        if not rack:
            abort(404)

        match = rack.match
        if current_user.id not in [match.player1_id, match.player2_id]:
            flash("Non sei un giocatore di questa partita.", "error")
            return redirect(url_for("dashboard.dashboard"))

        return f(*args, **kwargs)

    return decorated_function


def inscription_owner_required(f):
    """Permette l'accesso solo al proprietario dell'iscrizione specificata."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import Inscription  # Local import to avoid circular dependency

        inscription_id = kwargs.get("inscription_id")
        if not inscription_id:
            abort(400)  # Bad request if inscription_id is missing

        # Check if user is the owner of this inscription
        inscription = Inscription.query.get(inscription_id)
        if not inscription:
            abort(404)

        if current_user.id != inscription.user_id:
            flash("Non sei il proprietario di questa iscrizione.", "error")
            return redirect(url_for("dashboard.dashboard"))

        return f(*args, **kwargs)

    return decorated_function


def challenge_player_required(f):
    """Permette l'accesso solo ai giocatori della sfida specificata."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import Challenge  # Local import to avoid circular dependency

        challenge_id = kwargs.get("challenge_id")
        if not challenge_id:
            abort(400)  # Bad request if challenge_id is missing

        # Check if user has access to this challenge
        challenge = Challenge.query.get(challenge_id)
        if not challenge:
            abort(404)

        # For now, allow all authenticated players to access challenges
        # This could be extended to check if user is enrolled in a gara that uses this challenge
        return f(*args, **kwargs)

    return decorated_function


def challenge_attempt_player_required(f):
    """Permette l'accesso solo al proprietario del tentativo di sfida specificato."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import ChallengeAttempt  # Local import to avoid circular dependency

        attempt_id = kwargs.get("attempt_id")
        if not attempt_id:
            abort(400)  # Bad request if attempt_id is missing

        # Check if user is the owner of this attempt
        attempt = ChallengeAttempt.query.get(attempt_id)
        if not attempt:
            abort(404)

        if current_user.id != attempt.user_id:
            flash("Non sei il proprietario di questo tentativo.", "error")
            return redirect(url_for("dashboard.dashboard"))

        return f(*args, **kwargs)

    return decorated_function


def individual_match_player_required(f):
    """Permette l'accesso solo ai giocatori della partita individuale specificata."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import IndividualMatch  # Local import to avoid circular dependency

        match_id = kwargs.get("match_id")
        if not match_id:
            abort(400)  # Bad request if match_id is missing

        # Check if user is a player in this individual match
        match = IndividualMatch.query.get(match_id)
        if not match:
            abort(404)

        if current_user.id not in [match.player1_id, match.player2_id]:
            flash("Non sei un giocatore di questa partita.", "error")
            return redirect(url_for("dashboard.dashboard"))

        return f(*args, **kwargs)

    return decorated_function


# --------------------------------------------------------------------------
# Permission helper class
# --------------------------------------------------------------------------


class UserPermissions:
    """Helper centralizzato per logica di interfaccia / visibilità.

    This class provides static methods for common permission checks
    used in templates and routes.
    """

    @staticmethod
    def can_inscribe_to_gara():
        """Check if current user can inscribe to garas."""
        return current_user.is_authenticated and not current_user.is_admin

    @staticmethod
    def can_view_profile():
        """Check if current user can view their profile."""
        return current_user.is_authenticated and not current_user.is_admin

    @staticmethod
    def can_delete_account():
        """Check if current user can delete their account."""
        return current_user.is_authenticated and not current_user.is_admin

    @staticmethod
    def show_admin_management():
        """Check if admin management UI should be shown."""
        return current_user.is_authenticated and current_user.is_admin

    @staticmethod
    def show_director_management():
        """Check if director management UI should be shown."""
        return current_user.is_authenticated and current_user.is_director

    @staticmethod
    def get_default_dashboard():
        """Get the default dashboard route for current user."""
        if current_user.is_authenticated:
            return "dashboard.dashboard" if current_user.is_admin else "player.dashboard"
        return "main.index"


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

__all__ = [
    # Role-based
    "admin_required",
    "director_required",
    "director_or_admin_required",
    # Entity management
    "campionato_manager_required",
    "gara_manager_required",
    "match_manager_required",
    "venue_manager_required",
    "rack_manager_required",
    "trio_manager_required",
    # Player access
    "player_only",
    "player_required",
    "match_player_required",
    "rack_player_required",
    "inscription_owner_required",
    "challenge_player_required",
    "challenge_attempt_player_required",
    "individual_match_player_required",
    # Helper class
    "UserPermissions",
]
