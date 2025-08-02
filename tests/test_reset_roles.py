from utils.reset_data import reset_database_enhanced
from models.user.models import User


def test_roles_created(app):
    with app.app_context():
        reset_database_enhanced()
        assert User.query.filter_by(role="admin").count() == 1
        assert User.query.filter_by(role="director").count() >= 2
        assert User.query.filter_by(role="player").count() >= 10
