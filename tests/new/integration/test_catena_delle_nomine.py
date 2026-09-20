"""La catena delle nomine si vede, e l'admin può farla partire (ADR-041 em.).

Due difetti trovati dall'utente guardando la propagazione decisa nell'ADR-069:

1. **l'admin non poteva assegnare il ruolo di istruttore.** I pulsanti
   dell'amministrazione erano scritti a mano per l'esaminatore e il beta
   tester, quindi un ruolo nuovo non compariva da nessuna parte — e senza un
   primo titolare la catena non parte mai;
2. **la catena era invisibile.** `RoleGrant.granted_by_id` si scrive da sempre
   e c'è pure una pagina che lo mostra, ma nessun collegamento la raggiungeva e
   la vedeva solo l'admin. Un ruolo che si propaga senza che i titolari possano
   vedere da dove arriva un collega è una delega al buio.

La revoca resta dell'admin (US-A3): con la propagazione è l'unico punto di
contenimento, e i pari non devono potersi disfare a vicenda.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import GRANT_POLICY, RoleGrantService

PASSWORD = "prova123"


def _make_user(role: str = UserRole.PLAYER.value, **kwargs) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"c_{suffix}",
        email=f"{suffix}@example.com",
        role=role,
        is_verified=True,
        onboarding_completed=True,
        gamification_override=True,
        **kwargs,
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def _client_for(app, username: str):
    db.session.commit()
    client = app.test_client()
    client.post(
        "/auth/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=True,
    )
    return client


@pytest.fixture
def admin(db_session):
    user = _make_user(UserRole.ADMIN.value)
    db_session.commit()
    return user


# ────────────────────────────────────────────────────────────────────────────
# 1 · L'admin fa partire la catena
# ────────────────────────────────────────────────────────────────────────────
def test_l_admin_puo_assegnare_ogni_ruolo_concedibile(app, db_session, admin):
    """Il primo titolare lo nomina l'admin: senza, il ruolo non parte mai."""
    tizio = _make_user()
    db_session.commit()
    client = _client_for(app, admin.username)

    client.post(
        f"/roles/grant/{GrantableRole.INSTRUCTOR.value}/{tizio.id}",
        follow_redirects=True,
    )

    assert RoleGrantService.has_role(tizio.id, GrantableRole.INSTRUCTOR)


def test_l_elenco_utenti_offre_un_pulsante_per_ogni_ruolo(app, db_session, admin):
    """I pulsanti si ricavano da `GRANT_POLICY`, non si scrivono a mano.

    È questo che è mancato: aggiungere un ruolo al meccanismo non bastava a
    farlo comparire dove lo si assegna.
    """
    _make_user()
    client = _client_for(app, admin.username)

    pagina = client.get("/admin/users").get_data(as_text=True)

    for ruolo in GRANT_POLICY:
        assert f"/roles/grant/{ruolo.value}/" in pagina, ruolo.value


def test_un_non_admin_non_concede_dalla_route(app, db_session, admin):
    """Il pulsante non c'è, e la POST diretta nemmeno basta."""
    tizio = _make_user()
    estraneo = _make_user()
    db_session.commit()

    client = _client_for(app, estraneo.username)
    client.post(
        f"/roles/grant/{GrantableRole.INSTRUCTOR.value}/{tizio.id}",
        follow_redirects=True,
    )

    assert not RoleGrantService.has_role(tizio.id, GrantableRole.INSTRUCTOR)


def test_un_istruttore_puo_nominarne_un_altro(app, db_session, admin):
    """La propagazione decisa nell'ADR-069, vista dalla route."""
    luca = _make_user()
    RoleGrantService.grant(luca.id, GrantableRole.INSTRUCTOR, admin)
    giada = _make_user()
    db_session.commit()

    client = _client_for(app, luca.username)
    client.post(
        f"/roles/grant/{GrantableRole.INSTRUCTOR.value}/{giada.id}",
        follow_redirects=True,
    )

    assert RoleGrantService.has_role(giada.id, GrantableRole.INSTRUCTOR)
    grant = RoleGrantService.get_active_grant(giada.id, GrantableRole.INSTRUCTOR)
    assert grant is not None and grant.granted_by_id == luca.id


def test_in_produzione_un_istruttore_arriva_dove_si_propaga(app):
    """L'allowlist non deve fermare la via da cui il ruolo si propaga.

    Le tre route erano dichiarate per il solo esaminatore: in produzione un
    istruttore avrebbe preso 404 proprio sull'approvazione della richiesta di
    un collega, cioè sull'unico percorso che un titolare ha per nominarne un
    altro (l'elenco utenti è dell'admin).
    """
    from utils.feature_flags import is_endpoint_visible

    class _Finto:
        is_authenticated = True
        is_admin = False
        is_director = False
        is_player = True
        is_examiner = False
        is_instructor = True

    with app.app_context():
        app.config["TESTING"] = False
        app.config["DEBUG_MODE"] = False
        try:
            for endpoint in (
                "roles.role_requests",
                "roles.process_role_request",
                "roles.grant_role",
                "roles.role_holders",
            ):
                assert is_endpoint_visible(endpoint, _Finto()) is True, endpoint
        finally:
            app.config["TESTING"] = True
            app.config["DEBUG_MODE"] = True


# ────────────────────────────────────────────────────────────────────────────
# 2 · La catena si vede
# ────────────────────────────────────────────────────────────────────────────
def test_un_titolare_legge_la_catena_del_suo_ruolo(app, db_session, admin):
    """Chi può nominare deve poter vedere da dove arriva un collega."""
    luca = _make_user()
    RoleGrantService.grant(luca.id, GrantableRole.INSTRUCTOR, admin)
    giada = _make_user()
    RoleGrantService.grant(giada.id, GrantableRole.INSTRUCTOR, luca)
    db_session.commit()

    pagina = (
        _client_for(app, luca.username)
        .get(f"/roles/holders/{GrantableRole.INSTRUCTOR.value}")
        .get_data(as_text=True)
        .split('<footer class="debug-footer"')[0]
    )

    assert giada.username in pagina
    assert luca.username in pagina  # «concesso da»


def test_il_titolare_di_un_altro_ruolo_non_la_legge(app, db_session, admin):
    """Essere esaminatore non dà diritto a guardare gli istruttori."""
    esaminatore = _make_user()
    RoleGrantService.grant(esaminatore.id, GrantableRole.EXAMINER, admin)
    db_session.commit()

    client = _client_for(app, esaminatore.username)
    risposta = client.get(f"/roles/holders/{GrantableRole.INSTRUCTOR.value}")

    assert risposta.status_code == 403


def test_chi_non_ha_il_ruolo_non_la_legge(app, db_session, admin):
    tizio = _make_user()
    db_session.commit()

    client = _client_for(app, tizio.username)

    assert (
        client.get(f"/roles/holders/{GrantableRole.INSTRUCTOR.value}").status_code
        == 403
    )


def test_la_revoca_resta_dell_admin(app, db_session, admin):
    """US-A3: con la propagazione è l'unico punto di contenimento."""
    luca = _make_user()
    RoleGrantService.grant(luca.id, GrantableRole.INSTRUCTOR, admin)
    giada = _make_user()
    RoleGrantService.grant(giada.id, GrantableRole.INSTRUCTOR, luca)
    db_session.commit()

    client = _client_for(app, luca.username)
    pagina = client.get(f"/roles/holders/{GrantableRole.INSTRUCTOR.value}").get_data(
        as_text=True
    )
    assert "/roles/revoke/" not in pagina

    client.post(
        f"/roles/revoke/{GrantableRole.INSTRUCTOR.value}/{giada.id}",
        follow_redirects=True,
    )
    assert RoleGrantService.has_role(giada.id, GrantableRole.INSTRUCTOR)


def test_l_admin_vede_la_catena_e_il_comando_di_revoca(app, db_session, admin):
    luca = _make_user()
    RoleGrantService.grant(luca.id, GrantableRole.INSTRUCTOR, admin)
    db_session.commit()

    pagina = (
        _client_for(app, admin.username)
        .get(f"/roles/holders/{GrantableRole.INSTRUCTOR.value}")
        .get_data(as_text=True)
    )

    assert "/roles/revoke/" in pagina


# ────────────────────────────────────────────────────────────────────────────
# 3 · Ciascuno vede chi ha nominato lui
# ────────────────────────────────────────────────────────────────────────────
def test_la_pagina_ruoli_dice_chi_ti_ha_nominato(app, db_session, admin):
    luca = _make_user()
    RoleGrantService.grant(luca.id, GrantableRole.INSTRUCTOR, admin)
    db_session.commit()

    pagina = (
        _client_for(app, luca.username)
        .get("/player/ruoli")
        .get_data(as_text=True)
        .split('<footer class="debug-footer"')[0]
    )

    assert admin.username in pagina


def test_chi_ha_il_ruolo_trova_la_catena_dalla_sua_pagina(app, db_session, admin):
    luca = _make_user()
    RoleGrantService.grant(luca.id, GrantableRole.INSTRUCTOR, admin)
    db_session.commit()

    pagina = _client_for(app, luca.username).get("/player/ruoli").get_data(as_text=True)

    assert f"/roles/holders/{GrantableRole.INSTRUCTOR.value}" in pagina


def test_chi_non_ha_il_ruolo_non_trova_il_collegamento(app, db_session, admin):
    tizio = _make_user()
    db_session.commit()

    pagina = (
        _client_for(app, tizio.username).get("/player/ruoli").get_data(as_text=True)
    )

    assert "/roles/holders/" not in pagina
