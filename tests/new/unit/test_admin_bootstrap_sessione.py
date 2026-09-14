"""Il bootstrap dell'admin non deve scollegare l'admin a ogni avvio.

`create_app` chiama `create_admin_if_not_exists()` a ogni reload della web app,
e in produzione anche ogni ora (`send_match_reminders.py`) e ogni giorno
(`daily_jobs.py`). Con `ADMIN_PASSWORD_REQUIRED` la funzione riallinea la
password dell'admin a quella della configurazione.

Riscrivere la **stessa** password non è innocuo: `generate_password_hash` usa
un sale casuale, quindi l'hash cambia, e dall'ADR-055 l'id di sessione porta
un'impronta di quell'hash. Ogni avvio equivaleva a un cambio password: in sei
giorni di access log la sessione dell'admin è rimasta viva due minuti.

L'impronta si verifica qui con `User.from_session_id`, la stessa funzione che
usa `load_user`: a livello di richiesta servirebbe ripulire `g._login_user`
(vedi `test_recupero_password.py`), altrimenti il controllo non girerebbe.
"""

import pytest

from models.base import db
from models.user.models import User
from models.user.role_enum import UserRole
from utils import create_admin_if_not_exists


@pytest.fixture
def admin(app, db_session, monkeypatch):
    monkeypatch.setitem(app.config, "ADMIN_PASSWORD_REQUIRED", True)
    monkeypatch.setitem(app.config, "ADMIN_USERNAME", "admin_bootstrap")
    monkeypatch.setitem(app.config, "ADMIN_PASSWORD", "password-di-produzione")

    utente = User(
        username="admin_bootstrap",
        email="admin_bootstrap@test.local",
        role=UserRole.ADMIN.value,
    )
    utente.set_password("password-di-produzione")
    db_session.add(utente)
    db_session.commit()
    return utente


def test_stessa_password_non_invalida_la_sessione(admin):
    hash_prima = admin.password_hash
    id_di_sessione = admin.get_id()

    for _ in range(2):  # un reload e poi un task orario
        assert create_admin_if_not_exists() is admin
        db.session.commit()

    assert admin.password_hash == hash_prima
    assert User.from_session_id(id_di_sessione) is admin


def test_password_cambiata_invalida_la_sessione(app, admin, monkeypatch):
    hash_prima = admin.password_hash
    id_di_sessione = admin.get_id()

    monkeypatch.setitem(app.config, "ADMIN_PASSWORD", "password-nuova")
    create_admin_if_not_exists()
    db.session.commit()

    assert admin.password_hash != hash_prima
    assert admin.check_password("password-nuova")
    assert User.from_session_id(id_di_sessione) is None
