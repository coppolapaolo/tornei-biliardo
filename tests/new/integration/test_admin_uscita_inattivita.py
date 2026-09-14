"""L'admin viene scollegato dopo 30 minuti di inattività (ADR-063).

Solo l'admin: può fare tutto, quindi è la sessione dimenticata che costa di
più. Direttori e giocatori restano come prima.

Due trappole di questa suite, entrambe già costate test che passavano sempre:

* `g` non è per-richiesta: Flask-Login trova l'utente in cache e non rilegge
  la sessione. Ogni richiesta qui parte da `_nuova_richiesta()`, come
  `_simula_richiesta_nuova()` in `test_recupero_password.py`;
* l'id di sessione è `user.get_id()`, non l'id nudo (ADR-055).

L'orologio è quello del modulo (`_adesso`), non `time.time`: patcharlo
sposterebbe l'ora di tutto il processo, rate limiter compreso.
"""

import pytest
from flask import g

import utils.inattivita_admin as inattivita
from models.user.models import User
from models.user.role_enum import UserRole

MINUTO = 60.0
ORA_ZERO = 1_800_000_000.0


@pytest.fixture
def orologio(monkeypatch):
    stato = {"t": ORA_ZERO}
    monkeypatch.setattr(inattivita, "_adesso", lambda: stato["t"])
    return stato


def _utente(db_session, username, ruolo):
    utente = User(username=username, email=f"{username}@test.local", role=ruolo)
    utente.set_password("password-di-prova")
    utente.is_verified = True
    db_session.add(utente)
    db_session.commit()
    return utente


@pytest.fixture
def admin(db_session):
    return _utente(db_session, "admin_inattivo", UserRole.ADMIN.value)


def _nuova_richiesta():
    if hasattr(g, "_login_user"):
        delattr(g, "_login_user")


def _entra(client, utente, ultima_attivita=None):
    with client.session_transaction() as sess:
        sess["_user_id"] = utente.get_id()
        if ultima_attivita is not None:
            sess[inattivita.CHIAVE] = ultima_attivita


def _get(client, url):
    _nuova_richiesta()
    return client.get(url)


def _ultima_attivita(client):
    with client.session_transaction() as sess:
        return sess.get(inattivita.CHIAVE)


def _flash(client):
    with client.session_transaction() as sess:
        return [messaggio for _categoria, messaggio in sess.get("_flashes", [])]


def _al_login(risposta):
    return risposta.status_code == 302 and "/auth/login" in risposta.headers.get(
        "Location", ""
    )


def _poll(utente):
    return f"/sse/poll/user/{utente.id}"


def test_admin_attivo_resta_dentro_e_la_pagina_rinnova_l_attivita(
    client, admin, orologio
):
    _entra(client, admin, ultima_attivita=ORA_ZERO - 29 * MINUTO)

    risposta = _get(client, "/dashboard")

    assert not _al_login(risposta)
    assert _ultima_attivita(client) == ORA_ZERO


def test_admin_fermo_oltre_il_limite_viene_scollegato(client, admin, orologio):
    _entra(client, admin, ultima_attivita=ORA_ZERO - 31 * MINUTO)

    risposta = _get(client, "/dashboard")

    assert _al_login(risposta)
    assert "next=/dashboard" in risposta.headers["Location"].replace("%2F", "/")
    assert any("30 minuti" in messaggio for messaggio in _flash(client))
    assert _ultima_attivita(client) is None
    # La richiesta dopo è anonima: la sessione è chiusa davvero, non solo
    # rimandata al login una volta.
    assert _get(client, _poll(admin)).status_code == 401


def test_post_scaduto_va_al_login_senza_next(client, admin, orologio):
    """Dopo il login un `next` verso un POST diventerebbe un GET sbagliato."""
    _entra(client, admin, ultima_attivita=ORA_ZERO - 31 * MINUTO)
    _nuova_richiesta()

    risposta = client.post("/dashboard")

    assert _al_login(risposta)
    assert "next=" not in risposta.headers["Location"]


def test_poll_oltre_il_limite_risponde_401(client, admin, orologio):
    _entra(client, admin, ultima_attivita=ORA_ZERO - 31 * MINUTO)

    risposta = _get(client, _poll(admin))

    assert risposta.status_code == 401


def test_i_poll_non_contano_come_attivita(client, admin, orologio):
    """Una scheda aperta che interroga il server non deve tenere viva la sessione."""
    inizio = ORA_ZERO - 20 * MINUTO
    _entra(client, admin, ultima_attivita=inizio)

    assert _get(client, _poll(admin)).status_code == 200
    assert _ultima_attivita(client) == inizio

    orologio["t"] = ORA_ZERO + 11 * MINUTO
    assert _get(client, _poll(admin)).status_code == 401


@pytest.mark.parametrize("ruolo", [UserRole.DIRECTOR.value, UserRole.PLAYER.value])
def test_direttori_e_giocatori_non_scadono(client, db_session, orologio, ruolo):
    utente = _utente(db_session, f"fermo_{ruolo}", ruolo)
    _entra(client, utente, ultima_attivita=ORA_ZERO - 120 * MINUTO)

    assert _get(client, _poll(utente)).status_code == 200


def test_login_nuovo_non_scollega_per_una_chiave_vecchia(client, admin, orologio):
    with client.session_transaction() as sess:
        sess[inattivita.CHIAVE] = ORA_ZERO - 120 * MINUTO
    _nuova_richiesta()

    risposta = client.post(
        "/auth/login",
        data={"username": admin.username, "password": "password-di-prova"},
    )

    assert risposta.status_code == 302 and not _al_login(risposta)
    assert _ultima_attivita(client) == ORA_ZERO
    assert _get(client, _poll(admin)).status_code == 200


def test_admin_gia_dentro_senza_chiave_viene_inizializzato(client, admin, orologio):
    """Le sessioni aperte prima del deploy non hanno la chiave: non si scollegano."""
    _entra(client, admin)

    risposta = _get(client, _poll(admin))

    assert risposta.status_code == 200
    assert _ultima_attivita(client) == ORA_ZERO
