"""
utils package – formerly utils.py

Converts the old single module into a package to allow imports
of sub-modules (e.g., ``utils.reset_data``) without breaking existing imports.

All public symbols remain unchanged, so calls like:
    from utils import admin_required
continue to work.

Sub-modules:
    - utils.permissions: Permission decorators (circular import workarounds isolated
        here)
    - utils.reset_data: Database reset utilities
    - utils.database_utils: Database statistics utilities

CIRCULAR IMPORT WORKAROUNDS (13 local imports)
----------------------------------------------
This package uses local imports inside functions to avoid circular dependencies.
This is the RECOMMENDED Flask pattern for this situation.

Why local imports are necessary:
1. Permission decorators need to query models at RUNTIME (Model.query, db.session.get)
2. TYPE_CHECKING cannot be used because imports are for runtime, not type hints

Distribution:
- utils.permissions: 10 local imports (permission checks need model queries)
- utils.__init__: 3 local imports (bootstrap functions)

The remaining local imports are intentional and represent the minimum necessary
to break the circular dependency while keeping related code together.

See also: ADR-XXX (planned) for detailed architecture decision.
"""

from flask import current_app

from models.competition.services import GaraService
from models.transaction.manager import transactional
from models.user.role_enum import UserRole

# --------------------------------------------------------------------------
# Re-export all permission decorators from dedicated module
# This maintains backward compatibility: `from utils import admin_required`
# --------------------------------------------------------------------------
from .permissions import (  # noqa: F401  (re-export di compatibilita', vedi sopra)
    # Role-based
    admin_required,
    director_required,
    director_or_admin_required,
    # Entity management
    campionato_manager_required,
    gara_manager_required,
    match_manager_required,
    venue_manager_required,
    examiner_required,
    rack_manager_required,
    trio_manager_required,
    # Gamification progression (layer L2)
    feature_required,
    # Player access
    player_only,
    player_required,
    match_player_required,
    trio_player_required,
    inscription_owner_required,
    challenge_player_required,
    challenge_attempt_player_required,
    individual_match_player_required,
    # Helper class
    UserPermissions,
)

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
        # Nomina solo ciò che manca davvero: in produzione ADMIN_USERNAME ha
        # un default ("admin", config.py) e l'unica che può mancare è la
        # password — dirle entrambe manda a cercare un problema inesistente.
        mancanti = " e ".join(
            name
            for name, value in (
                ("ADMIN_USERNAME", username),
                ("ADMIN_PASSWORD", password),
            )
            if not value
        )
        raise RuntimeError(
            f"Admin bootstrap richiede {mancanti} in configurazione. "
            "In produzione arriva dalle env var omonime, che vivono nel file "
            "WSGI: da console o scheduled task usa scripts/prod_env.py, "
            "che le carica da lì."
        )

    existing_admin = (
        User.query.filter_by(role=UserRole.ADMIN.value)
        .filter(User.deleted_at.is_(None))
        .first()
    )
    if existing_admin:
        # In produzione la password dell'admin è quella della variabile
        # d'ambiente: la si riallinea, ma solo se è davvero diversa. Riscrivere
        # lo stesso valore cambia comunque l'hash, perché il sale è casuale, e
        # con l'hash cambia l'impronta di sessione dell'ADR-055: l'admin
        # veniva scollegato a ogni avvio dell'app e a ogni scheduled task.
        if require_pwd and password and not existing_admin.check_password(password):
            existing_admin.set_password(password)
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


# ============================================================================
#  Note: reset_data module available for direct import (utils.reset_data)
#  Removed automatic import to avoid circular dependencies
# ============================================================================
