"""
tests/test_enhanced_reset.py
Verifica che reset_database_enhanced crei correttamente i dati demo.
(aggiornato: importa dal percorso corretto utils.reset_data)
"""

from utils.reset_data import reset_database_enhanced
from models.user.models import User
from models import Tournament


def test_enhanced_reset_functionality(app):
    """L'enhanced reset deve popolare utenti e tornei attesi."""
    with app.app_context():
        reset_database_enhanced()

        # utenti
        assert User.query.filter_by(role="admin").count() == 1
        assert User.query.filter_by(role="director").count() == 2
        assert User.query.filter_by(role="player").count() == 11

        # tornei
        assert Tournament.query.count() == 3


def test_enhanced_reset_database(app):
    """Chiamare due volte la funzione non deve sollevare eccezioni."""
    with app.app_context():
        reset_database_enhanced()
        # seconda chiamata (idempotenza sulla creazione schema)
        reset_database_enhanced()
