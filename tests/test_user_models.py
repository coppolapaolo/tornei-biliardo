from models import (
    User,
    TournamentDirector,
    DirectorRequest,
    Tournament,  # serve per il test di retro-compatibilità
)

# --------------------------------------------------------------------
# 1) Import corretti e alias verso il nuovo dominio user
# --------------------------------------------------------------------
def test_user_imports():
    assert User.__name__ == "User"
    assert TournamentDirector.__name__ == "TournamentDirector"
    assert DirectorRequest.__name__ == "DirectorRequest"
    # lo User importato da models deve essere lo stesso della versione modulare
    from models.user.models import User as ModularUser

    assert User is ModularUser


# --------------------------------------------------------------------
# 2) Backward-compatibility: i vecchi modelli non-utente sono ancora importabili
# --------------------------------------------------------------------
def test_backward_compatibility():
    # Se arriva qui senza eccezioni l’import di Tournament funziona
    assert Tournament.__name__ == "Tournament"


# --------------------------------------------------------------------
# 3) Creazione utente di base, password hashing e proprietà di ruolo
# --------------------------------------------------------------------
def test_user_creation():
    u = User(username="test", email="t@t.com", role="player")
    u.set_password("secret123")
    assert u.role == "player"
    assert u.check_password("secret123")
    assert u.is_player


# Aggiungi questa funzione al file tests/test_user_models.py esistente


def test_user_permission_methods():
    """Test user permission methods"""
    admin = User(username="admin", email="admin@test.com", role="admin")
    director = User(username="director", email="director@test.com", role="director")
    player = User(username="player", email="player@test.com", role="player")

    # Test role properties
    assert admin.is_admin == True
    assert admin.is_director == False
    assert admin.is_player == False

    assert director.is_admin == False
    assert director.is_director == True
    assert director.is_player == False

    assert player.is_admin == False
    assert player.is_director == False
    assert player.is_player == True

    # Test can_view_admin_panel method
    assert admin.can_view_admin_panel() == True
    assert director.can_view_admin_panel() == False
    assert player.can_view_admin_panel() == False


def test_permission_system_integration():
    """Test integration between User model and permission system"""
    from models.user.permissions import PermissionChecker

    admin = User(username="admin", email="admin@test.com", role="admin")

    # Test that User model methods work with PermissionChecker
    assert PermissionChecker.can_view_admin_panel(admin) == admin.can_view_admin_panel()
    assert PermissionChecker.can_manage_users(admin) == True
