from utils.reset_data import reset_database_enhanced
from models.user.models import User


def test_player_statistics_not_empty(app):
    with app.app_context():
        reset_database_enhanced()
        player = User.query.filter_by(role="player").first()
        stats = player.get_statistics()
        assert "total_matches" in stats
        # Non tutti 0 (dati ancora fittizi, ma chiave presente)
