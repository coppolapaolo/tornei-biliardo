# tests/new/integration/test_admin.py
import pytest
from sqlalchemy import select


def _get_admin(db_session, app):
    from models.user.models import User
    admin_username = app.config.get("ADMIN_USERNAME", "admin")
    return db_session.execute(
        select(User).where(User.username == admin_username)
    ).scalar_one_or_none()


def _ensure_admin_in_testing(app):
    # in testing il bootstrap automatico non gira: usiamo il reset (idempotente)
    from utils.reset_data import reset_database_enhanced
    reset_database_enhanced()


def test_admin_exists_on_empty_db_production_bootstrap():
    import os
    # usa un DB effimero ma modalità non-testing
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    from app import create_app
    prod_app = create_app("development")  # TESTING=False qui

    with prod_app.app_context():
        from models import db
        from models.user.models import User
        admin_username = prod_app.config.get("ADMIN_USERNAME", "admin")
        admin = db.session.execute(
            select(User).where(User.username == admin_username)
        ).scalar_one_or_none()

        assert admin is not None, "L'admin deve essere creato all'avvio non-testing"
        assert (getattr(admin, "role", "") or "").lower() == "admin"


def test_admin_exists_after_reset(app):
    from utils.reset_data import reset_database_enhanced
    from sqlalchemy import select
    from models import db
    from models.user.models import User

    reset_database_enhanced()  # garantisce admin anche in TESTING

    admin_username = app.config.get("ADMIN_USERNAME", "admin")
    admin = db.session.execute(
        select(User).where(User.username == admin_username)
    ).scalar_one_or_none()

    assert admin is not None
    assert (getattr(admin, "role", "") or "").lower() == "admin"


@pytest.mark.parametrize("op", ["delete", "change_email", "change_password"])
def test_admin_restrictions(app, db_session, op):
    """
    L'admin non può cancellarsi, cambiare email o password.
    Nota: usiamo i metodi REALI del service:
      - soft_delete_user
      - update_user
      - change_password
    """
    _ensure_admin_in_testing(app)
    admin = _get_admin(db_session, app)
    assert (
        admin is not None
    ), "Prerequisito: admin inesistente; controlla il bootstrap dell'app"

    original_email = getattr(admin, "email", None)
    original_hash = getattr(admin, "password_hash", None)

    from models.user.services import UserService  # <-- classe reale nel repo

    with pytest.raises(ValueError):
        if op == "delete":
            UserService.soft_delete_user(admin.id)
        elif op == "change_email":
            UserService.update_user(admin.id, email="nuova@example.com")
        elif op == "change_password":
            # Passo la password corretta da config per evitare falsi positivi
            old_pw = app.config.get("ADMIN_PASSWORD", "admin123")
            if not UserService.change_password(
                admin.id, old_password=old_pw, new_password="NuovaP@ss1!"
            ):
                raise ValueError("Change password failed unexpectedly")

    # Ricarico l'admin e verifico che nulla sia cambiato
    from models.user.models import User

    reloaded = db_session.execute(select(User).where(User.id == admin.id)).scalar_one()
    assert getattr(reloaded, "deleted_at", None) is None
    assert getattr(reloaded, "email", None) == original_email
    assert getattr(reloaded, "password_hash", None) == original_hash
