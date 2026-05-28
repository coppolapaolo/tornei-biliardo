"""
Database utility functions that require model imports.
Separated to avoid circular imports.
"""


def get_database_stats():
    """Restituisce conteggio rapido entità DB (per debug)."""
    # Import here to avoid circular imports
    from models import User, Campionato, Gara, Inscription, Match

    try:
        return {
            "users": User.query.count(),
            "campionati": Campionato.query.count(),
            "gare": Gara.query.count(),
            "inscriptions": Inscription.query.count(),
            "matches": Match.query.count(),
        }
    except Exception:
        return {"error": "Database not accessible"}


def get_quick_login_users(limit=16, max_directors=4):
    """Return users for debug quick-login: admin, then directors, then players."""
    from models import User
    from models.user.role_enum import UserRole

    try:
        admin = (
            User.query.filter_by(role=UserRole.ADMIN.value)
            .order_by(User.id)
            .first()
        )
        directors = (
            User.query.filter_by(role=UserRole.DIRECTOR.value)
            .order_by(User.id)
            .limit(max_directors)
            .all()
        )
        remaining = limit - (1 if admin else 0) - len(directors)
        players = (
            User.query.filter_by(role=UserRole.PLAYER.value)
            .order_by(User.id)
            .limit(remaining)
            .all()
            if remaining > 0
            else []
        )

        result = []
        if admin:
            result.append(admin)
        result.extend(directors)
        result.extend(players)
        return result
    except Exception:
        return []
