"""
Unit-test per i servizi introdotti dal Task 1.4
(UserService e DirectorRequestService).

Verifiche coperte:
- creazione utente, promozione a director, retrocessione
- workflow richiesta di promozione a director
"""

import pytest
from models.user.services import UserService, DirectorRequestService
from models.base import db

pytestmark = pytest.mark.unit


# ------------------------------------------------------------------ #
#                            UserService                             #
# ------------------------------------------------------------------ #
class TestUserServiceBasics:
    def test_create_user(self, app):
        with app.app_context():
            user = UserService.create_user(
                "alice", "alice@example.com", "password123"
            )
            assert user.username == "alice"
            assert user.is_player
            assert user.check_password("password123")

    def test_promote_and_demote_user(self, app):
        with app.app_context():
            admin = UserService.create_user(
                "admin", "admin@example.com", "admin123", role="admin"
            )
            player = UserService.create_user(
                "bob", "bob@example.com", "player123"
            )

            # promozione
            assert UserService.promote_to_director(player.id, admin) is True
            db.session.refresh(player)
            assert player.is_director

            # retrocessione
            assert UserService.demote_from_director(player.id, admin) is True
            db.session.refresh(player)
            assert player.is_player


# ------------------------------------------------------------------ #
#                      DirectorRequestService                        #
# ------------------------------------------------------------------ #
class TestDirectorRequestServiceBasics:
    def test_create_and_process_request(self, app):
        with app.app_context():
            admin = UserService.create_user(
                "admin", "admin@example.com", "admin123", role="admin"
            )
            player = UserService.create_user(
                "charlie", "charlie@example.com", "player123"
            )

            # creazione richiesta
            req = DirectorRequestService.create_request(player.id)
            assert req.status == "pending"

            # approvazione
            processed = DirectorRequestService.process_request(
                req.id, admin, approve=True
            )
            assert processed.status == "approved"
            db.session.refresh(player)
            assert player.is_director


# ------------------------------------------------------------------ #
#                       Service integration                          #
# ------------------------------------------------------------------ #
class TestServiceIntegration:
    def test_user_promotion_workflow(self, app):
        with app.app_context():
            # creiamo admin e player
            admin = UserService.create_user(
                "admin", "admin@example.com", "admin123", role="admin"
            )
            player = UserService.create_user(
                "dave", "dave@example.com", "player123"
            )

            # richiesta di promozione
            req = DirectorRequestService.create_request(player.id)
            # admin approva
            DirectorRequestService.process_request(req.id, admin, True)
            db.session.refresh(player)
            assert player.is_director
