# tests/new/integration/test_admin_anagrafica_utente.py
"""Nome e cognome scritti dall'admin sulla scheda utente.

L'anagrafica è nata come campo del **proprio** profilo (issue #156): serve al
direttore che deve iscrivere la persona giusta fra tre username simili. Ma chi
non compila il profilo resta indistinguibile, e l'admin — che il nome lo sa —
non aveva modo di scriverlo. Da qui la stessa operazione dalla scheda utente.

Il servizio è lo stesso del profilo (`UserService.update_user`): qui si verifica
che la route esista, che scriva davvero, che il vuoto cancelli, e che resti
admin-only in produzione (ADR-028).
"""

import uuid

import pytest
from sqlalchemy import select


@pytest.fixture
def giocatore(db_session):
    from models import User
    from models.user.role_enum import UserRole

    user = User(
        username=f"marco_{uuid.uuid4().hex[:8]}",
        email=f"marco_{uuid.uuid4().hex[:8]}@example.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("password-di-prova")
    db_session.add(user)
    db_session.commit()
    return user


def _admin_client(logged_in_client):
    from models.user.role_enum import UserRole

    client, _ = logged_in_client(role=UserRole.ADMIN.value, username_prefix="admin")
    return client


def _ricarica(db_session, user_id):
    from models import User

    db_session.expire_all()
    return db_session.execute(select(User).where(User.id == user_id)).scalar_one()


def test_admin_scrive_nome_e_cognome(logged_in_client, db_session, giocatore):
    client = _admin_client(logged_in_client)
    user_id = giocatore.id

    risposta = client.post(
        f"/admin/user/{user_id}/anagrafica",
        data={"first_name": "Marco", "last_name": "Bianchi"},
        follow_redirects=False,
    )

    assert risposta.status_code == 302
    aggiornato = _ricarica(db_session, user_id)
    assert aggiornato.first_name == "Marco"
    assert aggiornato.last_name == "Bianchi"
    assert aggiornato.full_name == "Marco Bianchi"


def test_campo_vuoto_cancella_il_nome(logged_in_client, db_session, giocatore):
    """Nome e cognome sono facoltativi: svuotarli è un gesto sensato.

    Diversamente da username ed email, che il service rifiuta di azzerare.
    """
    giocatore.first_name = "Marco"
    giocatore.last_name = "Bianchi"
    db_session.commit()
    user_id = giocatore.id

    client = _admin_client(logged_in_client)
    client.post(
        f"/admin/user/{user_id}/anagrafica",
        data={"first_name": "", "last_name": ""},
    )

    aggiornato = _ricarica(db_session, user_id)
    assert aggiornato.first_name is None
    assert aggiornato.last_name is None


def test_il_form_compare_nella_scheda(logged_in_client, giocatore):
    client = _admin_client(logged_in_client)

    pagina = client.get(f"/admin/user/{giocatore.id}").get_data(as_text=True)

    assert f"/admin/user/{giocatore.id}/anagrafica" in pagina
    assert 'name="first_name"' in pagina
    assert 'name="last_name"' in pagina


def test_un_giocatore_non_puo_scrivere_l_anagrafica_altrui(
    logged_in_client, db_session, giocatore
):
    from models.user.role_enum import UserRole

    client, _ = logged_in_client(role=UserRole.PLAYER.value)
    user_id = giocatore.id

    risposta = client.post(
        f"/admin/user/{user_id}/anagrafica",
        data={"first_name": "Impostore", "last_name": "Qualunque"},
    )

    assert risposta.status_code in (302, 403)
    assert _ricarica(db_session, user_id).first_name is None


def test_endpoint_admin_only_in_produzione(app, monkeypatch):
    """ADR-028: non in `ENDPOINT_ROLES` ⇒ invisibile a tutti tranne l'admin."""
    from utils.feature_flags import is_endpoint_visible

    class _FakeUser:
        def __init__(self, *, is_director=False, is_admin=False):
            self.is_authenticated = True
            self.is_director = is_director
            self.is_admin = is_admin

    with app.test_request_context():
        monkeypatch.setitem(app.config, "TESTING", False)
        monkeypatch.setitem(app.config, "DEBUG_MODE", False)

        assert not is_endpoint_visible(
            "admin.user.update_anagrafica", _FakeUser(is_director=True)
        )
        assert is_endpoint_visible(
            "admin.user.update_anagrafica", _FakeUser(is_admin=True)
        )
