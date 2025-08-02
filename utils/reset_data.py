from __future__ import annotations  # ← nuova riga

"""
utils/reset_data.py  – Task 1.6  (fix definitivo)
Crea dati demo completi per la Phase 1.

Modifiche:
• tolti parametri 'location' e 'start_date' non presenti su Tournament
"""

from typing import Dict, List

from models.base import db
from models.legacy_models import Tournament
from models.user.models import TournamentDirector, User
from models.user.services import UserService, DirectorRequestService


# ─────────────────────── USERS ────────────────────────────────────────────────
def _create_users() -> Dict[str, List[User] | User]:
    admin = UserService.create_user(
        "admin", "admin@tornei.com", "admin123", role="admin"
    )

    directors = [
        UserService.create_user(
            "mario_rossi", "mario@tornei.com", "pwd12345", role="director"
        ),
        UserService.create_user(
            "lucia_verdi", "lucia@tornei.com", "pwd12345", role="director"
        ),
    ]

    players = [
        UserService.create_user(
            f"player{n:02d}", f"player{n:02d}@tornei.com", "pwd12345"
        )
        for n in range(1, 11)
    ]

    aspirant = UserService.create_user(
        "aspirante_director", "aspirante@tornei.com", "pwd12345"
    )
    DirectorRequestService.create_request(aspirant.id)

    return {
        "admin": admin,
        "directors": directors,
        "players": players,
        "aspirant": aspirant,
    }


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
    return tournaments


def _assign_directors(
    admin: User, directors: List[User], tournaments: List[Tournament]
) -> None:
    db.session.add_all(
        [
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
    )


# ─────────────────────── PUBLIC API ───────────────────────────────────────────
def reset_database_enhanced() -> None:
    """Drop → Create → Populate dataset completo Phase 1."""
    print("⚠️ RESET DATABASE (enhanced)…")
    db.drop_all()
    db.create_all()

    data = _create_users()
    tournaments = _create_tournaments(data["admin"])  # type: ignore[arg-type]
    _assign_directors(
        data["admin"], data["directors"], tournaments
    )  # type: ignore[arg-type]

    db.session.commit()
    print("✅ Enhanced data ready!")


__all__ = ["reset_database_enhanced"]
