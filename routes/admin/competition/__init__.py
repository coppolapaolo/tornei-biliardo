# routes/admin/competition/__init__.py
"""
Competition (Gara) management blueprint - decomposed into sub-modules.

This package organizes competition routes by responsibility:
- crud: Create, edit, delete, cancel gara operations
- detail: Gara detail view (unified for all roles)
- bracket: Vista tabellone (eliminazione diretta / doppio KO), pubblica
- inscriptions: Player inscriptions and director management
- rounds: Round lifecycle, matchmaking, classification
- matches: Match and trio operations
- challenges: Challenge integration with competitions
- squadre: Elenco squadre della competizione e squadra degli iscritti
- vetrina: Locandina, link esterno e indirizzo leggibile della pagina pubblica
"""

from flask import Blueprint

# Main competition blueprint - all sub-modules register routes on this
competition_bp = Blueprint("competition", __name__)

# Import sub-modules AFTER blueprint creation
# Each module registers its routes using @competition_bp.route decorators
from . import crud  # noqa: E402, F401
from . import detail  # noqa: E402, F401
from . import bracket  # noqa: E402, F401
from . import inscriptions  # noqa: E402, F401
from . import rounds  # noqa: E402, F401
from . import matches  # noqa: E402, F401
from . import challenges  # noqa: E402, F401
from . import squadre  # noqa: E402, F401
from . import categorie  # noqa: E402, F401
from . import vetrina  # noqa: E402, F401
from . import prova  # noqa: E402, F401

# Export blueprint for parent package
__all__ = ["competition_bp"]
