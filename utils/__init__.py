"""
utils package – formerly utils.py

Converts the old single module into a package to allow imports
of sub-modules (e.g., ``utils.reset_data``) without breaking existing imports.

All public symbols remain unchanged, so calls like:
    from utils import admin_required
continue to work.

Sub-modules:
    - utils.permissions: Permission decorators (circular import workarounds isolated here)
    - utils.reset_data: Database reset utilities
    - utils.database_utils: Database statistics utilities
"""

from functools import wraps
from flask import current_app
from flask_login import current_user

from models.competition.services import GaraService
from models.transaction.manager import transactional
from models.user.role_enum import UserRole

# --------------------------------------------------------------------------
# Re-export all permission decorators from dedicated module
# This maintains backward compatibility: `from utils import admin_required`
# --------------------------------------------------------------------------
from .permissions import (
    # Role-based
    admin_required,
    director_required,
    director_or_admin_required,
    # Entity management
    campionato_manager_required,
    gara_manager_required,
    match_manager_required,
    venue_manager_required,
    rack_manager_required,
    trio_manager_required,
    # Player access
    player_only,
    player_required,
    match_player_required,
    rack_player_required,
    inscription_owner_required,
    challenge_player_required,
    challenge_attempt_player_required,
    individual_match_player_required,
    # Helper class
    UserPermissions,
)

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

        bye_score = gara.distance_config.get_winning_racks()

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


@transactional(domain="utils")
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
    return admin, mario, pino


@transactional(domain="utils")
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

    tournament2 = Campionato(
        name="Coppa Estate 2025",
        campionato_type="Amalfi",
        without_x=True,
        final_playoffs=False,
        challenge_mode=True,
        is_active=True,
    )
    db.session.add(tournament2)

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
        is_race_to=True,
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
        is_race_to=False,
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
        is_race_to=True,
        status="setup",
    )

    print("✅ Creati 2 campionati di esempio:")
    print(f"   - {tournament1.name} (ID: {tournament1.id}) con 2 gare")
    print(f"   - {tournament2.name} (ID: {tournament2.id}) con 1 gara")
    return tournament1, tournament2


@transactional(domain="utils")
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
        bye_score = gara.distance_config.get_winning_racks()
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


# ============================================================================
#  Note: reset_data module available for direct import (utils.reset_data)
#  Removed automatic import to avoid circular dependencies
# ============================================================================
