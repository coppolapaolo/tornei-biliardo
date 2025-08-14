from __future__ import annotations

"""
utils/reset_data.py  – Task 1.6  (fix definitivo + Context Aware)
Crea dati demo completi per la Phase 1.

Modifiche:
• Context-aware: usa contesto esistente se disponibile
• Fix test failures con isolamento database
"""

from typing import Dict, List
from flask import has_app_context

from models.base import db
from models import Tournament
from models.user.models import TournamentDirector, User
from models.user.services import UserService, DirectorRequestService
from models import Prova
from datetime import date
from models.competition.services import ProvaService


# ─────────────────────── USERS ────────────────────────────────────────────────
def _create_users() -> Dict[str, List[User] | User]:
    """Create users using UserService with proper error handling"""
    try:
        admin = UserService.create_user(
            "admin", "admin@tornei.com", "admin123", role="admin"
        )
        print(f"   ✅ Created admin: {admin.username} (role: {admin.role})")

        directors = []
        directors.append(
            UserService.create_user(
                "mario_rossi", "mario@tornei.com", "pwd12345", role="director"
            )
        )
        directors.append(
            UserService.create_user(
                "lucia_verdi", "lucia@tornei.com", "pwd12345", role="director"
            )
        )
        print(f"   ✅ Created {len(directors)} directors")

        players = []
        for n in range(1, 11):
            player = UserService.create_user(
                f"player{n:02d}", f"player{n:02d}@tornei.com", "pwd12345"
            )
            players.append(player)
        print(f"   ✅ Created {len(players)} players")

        aspirant = UserService.create_user(
            "aspirante_director", "aspirante@tornei.com", "pwd12345"
        )
        DirectorRequestService.create_request(aspirant.id)
        print("   ✅ Created aspirant with request")

        return {
            "admin": admin,
            "directors": directors,
            "players": players,
            "aspirant": aspirant,
        }
    except Exception as e:
        print(f"   ❌ Error creating users: {e}")
        raise


# ─────────────────────── TOURNAMENTS ──────────────────────────────────────────
def _create_tournaments(admin: User) -> List[Tournament]:
    """Crea tre tornei senza campi non supportati dal modello Phase 1."""
    tournaments = [
        Tournament(name="Masters 9 Ball"),
        Tournament(name="Open 10 Ball"),
        Tournament(name="Summer Cup 8 Ball"),
    ]
    db.session.add_all(tournaments)
    db.session.flush()  # assegna gli id
    print(f"   ✅ Created {len(tournaments)} tournaments")
    return tournaments


def _create_provas(tournaments: List[Tournament]) -> None:
    """Create sample provas for each tournament"""
    from datetime import date, timedelta

    provas = 0
    disciplines = ["palla 8", "palla 9", "palla 10"]

    for i, tournament in enumerate(tournaments):
        for j in range(2):  # 2 provas per tournament
            ProvaService.create_prova(
                tournament_id=tournament.id,
                number=j + 1,
                name=f"{tournament.name} - Prova {j + 1}",
                date=date.today() + timedelta(days=7 * (i * 2 + j + 1)),
                discipline=disciplines[i % len(disciplines)],
                distance=5 + j * 2,  # 5, 7
                best_of=True,
                rounds_count=3,
                location="Sala Biliardo Centro",
                entry_fee=15.0,
                min_participants=4,
                max_participants=16,
                status="setup",
            )
            provas += 1

    print(f"   ✅ Created {provas} provas")


def _create_standalone_provas(directors: List[User]) -> None:
    """Create standalone competitions for Sprint 2 testing"""
    from datetime import datetime, timedelta

    print("🆕 Creating standalone competitions...")

    # Director1 crea una competizione standalone
    ProvaService.create_prova(
        number=1,
        name="Memorial Rossi 2025",
        director_id=directors[0].id,  # mario_rossi
        tournament_id=None,  # Nessun torneo
        date=date.today() + timedelta(days=45),
        location="Circolo Biliardo Milano",
        description="Competizione in memoria del maestro Rossi",
        discipline="palla 8",
        distance=9,
        best_of=True,
        rounds_count=1,  # Singolo turno
        min_participants=8,
        max_participants=16,
        entry_fee=20.0,
        inscription_start=datetime.now() + timedelta(days=5),
        inscription_end=datetime.now() + timedelta(days=40),
        status="setup",
    )

    # Director2 crea una competizione standalone multi-turno
    ProvaService.create_prova(
        number=2,
        name="Open Estate 2025",
        director_id=directors[1].id,  # lucia_verdi
        tournament_id=None,
        date=date.today() + timedelta(days=60),
        location="Sala Biliardo Roma",
        description="Competizione estiva aperta a tutti",
        discipline="palla 9",
        distance=7,
        best_of=True,
        rounds_count=3,  # 3 turni come Amalfi
        min_participants=12,
        max_participants=32,
        entry_fee=15.0,
        inscription_start=datetime.now() + timedelta(days=10),
        inscription_end=datetime.now() + timedelta(days=55),
        status="inscription",  # Questa è già aperta
    )

    db.session.flush()  # Per avere gli ID
    print("   ✅ Created 2 standalone competitions")


def _assign_directors(
    admin: User, directors: List[User], tournaments: List[Tournament]
) -> None:
    assignments = [
        TournamentDirector(
            user_id=directors[0].id,
            tournament_id=tournaments[0].id,
            assigned_by_id=admin.id,
        ),
        TournamentDirector(
            user_id=directors[1].id,
            tournament_id=tournaments[1].id,
            assigned_by_id=admin.id,
        ),
        TournamentDirector(
            user_id=directors[0].id,
            tournament_id=tournaments[2].id,
            assigned_by_id=admin.id,
        ),
        TournamentDirector(
            user_id=directors[1].id,
            tournament_id=tournaments[2].id,
            assigned_by_id=admin.id,
        ),
    ]
    db.session.add_all(assignments)
    print(f"   ✅ Created {len(assignments)} director assignments")


# ─────────────────────── CONTEXT-AWARE API ───────────────────────────────────
def _reset_database_core() -> None:
    """Core reset logic that assumes Flask context is already active"""
    print("🗑️ Dropping all tables...")
    db.drop_all()

    print("🏗️ Creating all tables...")
    db.create_all()

    print("👥 Creating users...")
    data = _create_users()

    print("🏆 Creating tournaments...")
    tournaments = _create_tournaments(data["admin"])  # type: ignore[arg-type]

    print("🎯 Assigning directors...")
    _assign_directors(
        data["admin"], data["directors"], tournaments  # type: ignore[arg-type]
    )

    # AGGIUNGI QUESTA PARTE
    print("🎱 Creating provas...")
    _create_provas(tournaments)

    print("💾 Committing to database...")
    db.session.commit()

    print("🏁 Creating standalone provas...")
    _create_standalone_provas(data["directors"])  # type: ignore[arg-type]

    print("💾 Committing to database...")
    db.session.commit()

    # Verify results
    user_count = User.query.count()
    admin_count = User.query.filter_by(role="admin").count()
    director_count = User.query.filter_by(role="director").count()
    player_count = User.query.filter_by(role="player").count()
    tournament_count = Tournament.query.count()
    assignment_count = TournamentDirector.query.count()
    prova_count = Prova.query.count()
    standalone_count = Prova.query.filter_by(tournament_id=None).count()  # NUOVO

    print("✅ Enhanced data ready!")
    print(f"   - Total Users: {user_count}")
    print(f"   - Admin users: {admin_count}")
    print(f"   - Director users: {director_count}")
    print(f"   - Player users: {player_count}")
    print(f"   - Tournaments: {tournament_count}")
    print(f"   - Directors assigned: {assignment_count}")
    print(f"   - Provas created: {prova_count}")
    print(f"   - Standalone provas: {standalone_count}")  # NUOVO
    print("   - Admin user: admin / admin123")


def reset_database_enhanced() -> None:
    """
    Context-aware database reset.

    If called within existing Flask app context (like in tests),
    uses that context. Otherwise creates its own context.
    """
    print("⚠️ RESET DATABASE (enhanced)…")

    if has_app_context():
        print("🔧 Using existing Flask application context...")
        _reset_database_core()
    else:
        print("🔧 Creating new Flask application context...")
        from app import create_app

        app = create_app("development")
        with app.app_context():
            _reset_database_core()


def reset_database_enhanced_cli() -> None:
    """CLI wrapper per reset database che gestisce application context."""
    try:
        reset_database_enhanced()
    except Exception as e:
        print(f"❌ Error during database reset: {e}")
        print("💡 Tip: Ensure Flask app can be created and database is accessible")
        raise


__all__ = ["reset_database_enhanced", "reset_database_enhanced_cli"]


# CLI execution
if __name__ == "__main__":
    reset_database_enhanced_cli()
