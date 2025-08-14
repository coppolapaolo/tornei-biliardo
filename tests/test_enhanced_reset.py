"""
tests/test_enhanced_reset.py — versione aggiornata per Dataset demo v2

Verifica che reset_database_enhanced crei correttamente i dati demo
secondo le nuove specifiche:
- 1 admin, 2 director, 20 player
- 2 tornei (La Garetta, Mercoledì)
- 1 prova per torneo + 1 prova stand‑alone
- La prova di "La Garetta" in stato INSCRIPTION con 8 iscritti
"""

from utils.reset_data import reset_database_enhanced
from models.user.models import User
from models import Tournament
from models.competition.models import Prova, Inscription
from models.status_enum import ProvaStatus


def test_enhanced_reset_functionality(app):
    """L'enhanced reset deve popolare utenti, tornei e prove attesi."""
    with app.app_context():
        reset_database_enhanced()

        # Utenti
        assert User.query.filter_by(role="admin").count() == 1
        assert User.query.filter_by(role="director").count() == 2
        assert User.query.filter_by(role="player").count() == 20

        # Tornei
        assert Tournament.query.count() == 2

        # Prove: 2 di torneo + 1 stand‑alone
        assert Prova.query.count() == 3

        # La Garetta: prova #1 in inscription con 8 iscritti
        t = Tournament.query.filter_by(name="La Garetta").first()
        assert t is not None
        p = Prova.query.filter_by(tournament_id=t.id, number=1).first()
        assert p is not None
        assert p.status == ProvaStatus.INSCRIPTION.value
        assert (
            Inscription.query.filter_by(prova_id=p.id, is_withdrawn=False).count() == 8
        )


def test_enhanced_reset_database(app):
    """Chiamare due volte la funzione non deve sollevare eccezioni."""
    with app.app_context():
        reset_database_enhanced()
        # seconda chiamata (idempotenza sulla creazione schema)
        reset_database_enhanced()
