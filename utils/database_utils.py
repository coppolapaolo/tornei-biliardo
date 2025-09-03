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
