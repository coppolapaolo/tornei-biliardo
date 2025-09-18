"""
utils package – formerly utils.py
Converte il vecchio modulo singolo in un package per permettere import
di sub-module (es. ``utils.reset_data``) senza rompere gli import esistenti.

Tutti i simboli pubblici rimangono invariati, quindi chiamate come
    from utils import admin_required
continuano a funzionare.
"""

# ============================================================================
#  CONTENUTO ORIGINALE DI utils.py  (INVARIATO)
# ============================================================================

# PHASE 1 PERMISSION SYSTEM UPDATE
from functools import wraps
from flask import abort, flash, redirect, url_for, request, current_app
from flask_login import current_user

from models.user.permissions import PermissionChecker, RoleRequirement
from models.user.role_enum import UserRole
from models.competition.services import GaraService

# --------------------------------------------------------------------------
# Decorator aggiornati con il nuovo permission system
# --------------------------------------------------------------------------


def admin_required(f):
    """Permette l’accesso solo ad admin."""
    return RoleRequirement.admin_required(f)


def director_required(f):
    """Permette l'accesso solo a direttori."""
    return RoleRequirement.director_required(f)


def director_or_admin_required(f):
    """Permette l’accesso a direttore o admin."""
    return RoleRequirement.director_or_admin_required(f)


def campionato_manager_required(campionato_id_getter):
    """Permette l’accesso a chi gestisce il campionato indicato."""
    return RoleRequirement.campionato_manager_required(campionato_id_getter)


def gara_manager_required(fn):
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


# --------------------------------------------------------------------------
# Permission helper centralizzato
# --------------------------------------------------------------------------
class UserPermissions:
    """Helper centralizzato per logica di interfaccia / visibilità."""

    @staticmethod
    def can_inscribe_to_gara():
        return current_user.is_authenticated and not current_user.is_admin

    @staticmethod
    def can_view_profile():
        return current_user.is_authenticated and not current_user.is_admin

    @staticmethod
    def can_delete_account():
        return current_user.is_authenticated and not current_user.is_admin

    @staticmethod
    def show_admin_management():
        return current_user.is_authenticated and current_user.is_admin

    @staticmethod
    def show_director_management():
        return current_user.is_authenticated and current_user.is_director

    @staticmethod
    def get_default_dashboard():
        if current_user.is_authenticated:
            return "admin.dashboard" if current_user.is_admin else "player.dashboard"
        return "main.index"


# --------------------------------------------------------------------------
# Decorator vari per route
# --------------------------------------------------------------------------
def player_only(f):
    """Blocca l’accesso admin a route dedicate ai player."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and current_user.is_admin:
            flash(
                "Funzionalità riservata ai giocatori. "
                "Utilizzare la dashboard amministratore.",
                "warning",
            )
            return redirect(url_for("admin.dashboard"))
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


def rack_manager_required(f):
    """Richiede che l'utente possa gestire il campionato collegato al rack."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        from models import Rack  # Local import to avoid circular dependency
        from flask import flash, redirect, url_for
        from flask_login import current_user

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
# Utility varie
# --------------------------------------------------------------------------
# get_database_stats moved to utils.database_utils to avoid circular imports


# --------------------------------------------------------------------------
# Funzioni di dominio campionati / match
# --------------------------------------------------------------------------
def create_round_matches(gara, players_or_inscriptions, round_number):
    """Crea gli abbinamenti per un turno (logica standard)."""
    from models import (
        Inscription,
        Match,
        db,
    )  # Local import to avoid circular dependency

    if isinstance(players_or_inscriptions[0], Inscription):
        players = [insc.user for insc in players_or_inscriptions]
    else:
        players = players_or_inscriptions

    matches = []

    if len(players) % 2 == 1:
        # Numero dispari: ultimo giocatore ha un bye
        bye_player = players[-1]

        bye_score = gara.get_winning_score() if gara.best_of else gara.distance

        match = Match(
            gara_id=gara.id,
            round_number=round_number,
            player1_id=bye_player.id,
            is_bye=True,
            player1_score=bye_score,
            winner_id=bye_player.id,
            status="completed",
            match_distance=gara.distance,
        )
        matches.append(match)
        players = players[:-1]

    for i in range(0, len(players), 2):
        match = Match(
            gara_id=gara.id,
            round_number=round_number,
            player1_id=players[i].id,
            player2_id=players[i + 1].id,
            match_distance=gara.distance,
        )
        matches.append(match)

    db.session.add_all(matches)
    return matches


def calculate_round_classification(gara_id, round_number):
    """Calcola la classifica dopo un turno."""
    from models import Match, Inscription  # Local import to avoid circular dependency

    matches = Match.query.filter_by(gara_id=gara_id, round_number=round_number).all()
    players_stats = {}

    for match in matches:
        if match.is_bye:
            if match.player1_id not in players_stats:
                players_stats[match.player1_id] = {
                    "matches_won": 0,
                    "point_diff": 0,
                    "initial_order": 0,
                }
            players_stats[match.player1_id]["matches_won"] += 1
            players_stats[match.player1_id]["point_diff"] += match.player1_score
        else:
            for player_id in [match.player1_id, match.player2_id]:
                if player_id not in players_stats:
                    inscription = Inscription.query.filter_by(
                        user_id=player_id, gara_id=gara_id
                    ).first()
                    players_stats[player_id] = {
                        "matches_won": 0,
                        "point_diff": 0,
                        "initial_order": (
                            inscription.initial_order if inscription else 999
                        ),
                    }

            if match.status == "completed" and match.winner_id:
                players_stats[match.winner_id]["matches_won"] += 1
                if match.winner_id == match.player1_id:
                    diff = match.player1_score - match.player2_score
                    players_stats[match.player1_id]["point_diff"] += diff
                    players_stats[match.player2_id]["point_diff"] -= diff
                else:
                    diff = match.player2_score - match.player1_score
                    players_stats[match.player2_id]["point_diff"] += diff
                    players_stats[match.player1_id]["point_diff"] -= diff

    sorted_players = sorted(
        players_stats.items(),
        key=lambda x: (
            -x[1]["matches_won"],
            -x[1]["point_diff"],
            x[1]["initial_order"],
        ),
    )
    return [(pid, stats) for pid, stats in sorted_players]


# --------------------------------------------------------------------------
# Funzioni di bootstrap / sample data
# --------------------------------------------------------------------------
def create_default_users():
    """Crea tre utenti di base (admin + 2 player)."""
    from models import User, db  # Local import to avoid circular dependency

    admin = User(username="admin", email="admin@campionato.com", role="admin")
    admin.set_password("admin123")

    mario = User(username="mario", email="mario@test.com", role="player")
    mario.set_password("mario123")

    pino = User(username="pino", email="pino@test.com", role="player")
    pino.set_password("pino123")

    db.session.add_all([admin, mario, pino])
    db.session.commit()
    return admin, mario, pino


def create_sample_campionato():
    """Crea due campionati di esempio con gare collegate."""
    from models import Campionato, db  # Local import to avoid circular dependency

    tournament1 = Campionato(
        name="Campionato Primavera 2025",
        campionato_type="Amalfi",
        without_x=False,
        final_playoffs=True,
        challenge_mode=False,
        is_active=True,
    )
    db.session.add(tournament1)
    db.session.commit()

    tournament2 = Campionato(
        name="Coppa Estate 2025",
        campionato_type="Amalfi",
        without_x=True,
        final_playoffs=False,
        challenge_mode=True,
        is_active=True,
    )
    db.session.add(tournament2)
    db.session.commit()

    from datetime import date, timedelta

    today = date.today()

    GaraService.create_gara(
        campionato_id=tournament1.id,
        number=1,
        name="Prima Gara",
        date=today + timedelta(days=7),
        location="Circolo Biliardo Centro",
        description="Prima gara del campionato primaverile",
        rounds_count=3,
        min_participants=4,
        max_participants=16,
        entry_fee=15.0,
        discipline="palla 9",
        distance=7,
        best_of=True,
        status="setup",
    )

    GaraService.create_gara(
        campionato_id=tournament1.id,
        number=2,
        name="Seconda Gara",
        date=today + timedelta(days=14),
        location="Circolo Biliardo Centro",
        description="Seconda gara del campionato primaverile",
        rounds_count=3,
        min_participants=4,
        max_participants=16,
        entry_fee=15.0,
        discipline="palla 8",
        distance=5,
        best_of=False,
        status="setup",
    )

    GaraService.create_gara(
        campionato_id=tournament2.id,
        number=1,
        name="Coppa Opening",
        date=today + timedelta(days=21),
        location="Sala Biliardo Elite",
        description="Gara di apertura della coppa estiva",
        rounds_count=2,
        min_participants=6,
        max_participants=12,
        entry_fee=20.0,
        discipline="palla 10",
        distance=9,
        best_of=True,
        status="setup",
    )

    db.session.commit()
    print("✅ Creati 2 campionati di esempio:")
    print(f"   - {tournament1.name} (ID: {tournament1.id}) con 2 gare")
    print(f"   - {tournament2.name} (ID: {tournament2.id}) con 1 gara")
    return tournament1, tournament2


def create_admin_if_not_exists():
    """Garantisce la presenza di un admin nel DB, leggendo credenziali da config/env.

    Regole:
    - Se ADMIN_PASSWORD_REQUIRED=True (produzione) e
        mancano ADMIN_USERNAME/ADMIN_PASSWORD → errore.
    - Crea l'admin solo se assente (idempotente).
    - Non stampa mai la password.
    - NON crea un secondo admin.
    """
    from models import User, db  # Local import to avoid circular dependency

    cfg = current_app.config
    require_pwd = bool(cfg.get("ADMIN_PASSWORD_REQUIRED", False))
    username = (cfg.get("ADMIN_USERNAME") or "").strip() or None
    password = (cfg.get("ADMIN_PASSWORD") or "").strip() or None
    email = (cfg.get("ADMIN_EMAIL") or "").strip() or None

    if require_pwd and (not username or not password):
        raise RuntimeError(
            "Admin bootstrap richiede ADMIN_USERNAME"
            "e ADMIN_PASSWORD in configurazione."
        )

    existing_admin = (
        User.query.filter_by(role=UserRole.ADMIN.value)
        .filter(User.deleted_at.is_(None))
        .first()
    )
    if existing_admin:
        return existing_admin

    if not username or not password:
        # in sviluppo senza variabili non creiamo nulla
        return None

    admin = User(
        username=username,
        email=email or f"{username}@campionato.local",
        role=UserRole.ADMIN.value,
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    return admin


def create_round_matches_amalfi_compatible(gara, players_or_inscriptions, round_number):
    """Versione compatibile 'Amalfi'. Differisce per campo ``amalfi_round``."""
    from models import (
        Inscription,
        Match,
        db,
    )  # Local import to avoid circular dependency

    if isinstance(players_or_inscriptions[0], Inscription):
        players = [insc.user for insc in players_or_inscriptions]
    else:
        players = players_or_inscriptions

    matches = []

    if len(players) % 2 == 1:
        bye_player = players[-1]
        bye_score = gara.get_winning_score() if gara.best_of else gara.distance
        match = Match(
            gara_id=gara.id,
            round_number=round_number,
            player1_id=bye_player.id,
            is_bye=True,
            player1_score=bye_score,
            winner_id=bye_player.id,
            status="completed",
            amalfi_round=round_number,
            match_distance=gara.distance,
        )
        matches.append(match)
        players = players[:-1]

    for i in range(0, len(players), 2):
        match = Match(
            gara_id=gara.id,
            round_number=round_number,
            player1_id=players[i].id,
            player2_id=players[i + 1].id,
            amalfi_round=round_number,
            match_distance=gara.distance,
        )
        matches.append(match)

    db.session.add_all(matches)
    return matches


# ============================================================================
#  Note: reset_data module available for direct import (utils.reset_data)
#  Removed automatic import to avoid circular dependencies
# ============================================================================
