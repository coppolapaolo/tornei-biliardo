"""Chi accede resta collegato su quel dispositivo per trenta giorni (ADR-064).

Fino al 17/09/2026 il cookie di sessione nasceva senza scadenza: iOS lo butta
quando chiude la scheda o la web app, e sul telefono voleva dire rifare
l'accesso a ogni apertura — in sala, a gara in corso.

Quattro fatti da tenere fermi:

* la casella «Resta collegato» è spuntata per default, e con la spunta il
  cookie porta una scadenza a trenta giorni;
* senza spunta il cookie resta di sessione, per il computer condiviso;
* il cookie **non** si rimanda a ogni risposta: con i poll ogni tre secondi
  una risposta lenta riscriverebbe la sessione con lo stato vecchio;
* la scadenza si rinnova al più una volta al giorno, sulle pagine e non sui
  poll — una scheda dimenticata aperta non deve tenersi viva da sola.

Le trappole della suite sono quelle di `test_admin_uscita_inattivita.py`:
`g` non è per-richiesta, e l'id di sessione è `user.get_id()` (ADR-055).
"""

from datetime import timedelta

import pytest
from flask import g

import utils.sessione_duratura as duratura
from models.user.models import User
from models.user.role_enum import UserRole

GIORNO = 86_400.0
ORA_ZERO = 1_800_000_000.0
PASSWORD = "password-di-prova"


@pytest.fixture
def orologio(monkeypatch):
    stato = {"t": ORA_ZERO}
    monkeypatch.setattr(duratura, "_adesso", lambda: stato["t"])
    return stato


@pytest.fixture
def giocatore(db_session):
    utente = User(
        username="resta_collegato",
        email="resta_collegato@test.local",
        role=UserRole.PLAYER.value,
    )
    utente.set_password(PASSWORD)
    utente.is_verified = True
    db_session.add(utente)
    db_session.commit()
    return utente


def _nuova_richiesta():
    if hasattr(g, "_login_user"):
        delattr(g, "_login_user")


def _cookie_di_sessione(risposta):
    for intestazione in risposta.headers.getlist("Set-Cookie"):
        if intestazione.startswith("session="):
            return intestazione
    return None


def _accedi(client, utente, resta_collegato):
    dati = {"username": utente.username, "password": PASSWORD}
    if resta_collegato:
        dati["resta_collegato"] = "1"
    _nuova_richiesta()
    return client.post("/auth/login", data=dati)


@pytest.mark.integration
class TestDurataDelCookie:
    def test_la_configurazione_dice_trenta_giorni(self, app):
        assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(days=30)
        assert app.config["SESSION_REFRESH_EACH_REQUEST"] is False

    def test_con_la_spunta_il_cookie_ha_una_scadenza(self, client, giocatore):
        risposta = _accedi(client, giocatore, resta_collegato=True)

        cookie = _cookie_di_sessione(risposta)
        assert cookie is not None
        assert "Expires=" in cookie

    def test_senza_spunta_il_cookie_resta_di_sessione(self, client, giocatore):
        risposta = _accedi(client, giocatore, resta_collegato=False)

        cookie = _cookie_di_sessione(risposta)
        assert cookie is not None
        assert "Expires=" not in cookie
        assert "Max-Age=" not in cookie

    def test_la_casella_nasce_spuntata(self, client):
        pagina = client.get("/auth/login").get_data(as_text=True)

        assert 'name="resta_collegato"' in pagina
        casella = pagina.split('name="resta_collegato"')[1].split(">")[0]
        assert "checked" in casella


@pytest.mark.integration
class TestRinnovo:
    """Si guarda l'orario del rinnovo dentro la sessione, non il `Set-Cookie`.

    Altri `before_request` scrivono nella sessione per conto loro (le
    permanenze di `user_session`, il token CSRF): la presenza del cookie nella
    risposta non dice chi l'ha fatto rimandare.
    """

    def _entra(self, client, utente, rinnovata, duratura_=True):
        with client.session_transaction() as sess:
            sess["_user_id"] = utente.get_id()
            sess.permanent = duratura_
            if rinnovata is not None:
                sess[duratura.CHIAVE] = rinnovata

    def _rinnovata(self, client):
        with client.session_transaction() as sess:
            return sess.get(duratura.CHIAVE)

    def test_entro_il_giorno_la_scadenza_non_si_sposta(
        self, client, giocatore, orologio
    ):
        self._entra(client, giocatore, rinnovata=ORA_ZERO)
        orologio["t"] = ORA_ZERO + GIORNO / 2
        _nuova_richiesta()

        client.get("/aiuto/")

        assert self._rinnovata(client) == ORA_ZERO

    def test_dopo_un_giorno_una_pagina_rinnova_la_scadenza(
        self, client, giocatore, orologio
    ):
        self._entra(client, giocatore, rinnovata=ORA_ZERO)
        orologio["t"] = ORA_ZERO + GIORNO + 1
        _nuova_richiesta()

        risposta = client.get("/aiuto/")

        assert self._rinnovata(client) == ORA_ZERO + GIORNO + 1
        assert "Expires=" in (_cookie_di_sessione(risposta) or "")

    def test_un_poll_non_rinnova(self, client, giocatore, orologio):
        self._entra(client, giocatore, rinnovata=ORA_ZERO)
        orologio["t"] = ORA_ZERO + GIORNO + 1
        _nuova_richiesta()

        risposta = client.get(f"/sse/poll/user/{giocatore.id}")

        assert risposta.status_code == 200
        assert self._rinnovata(client) == ORA_ZERO

    def test_la_sessione_non_duratura_non_si_tocca(self, client, giocatore, orologio):
        self._entra(client, giocatore, rinnovata=None, duratura_=False)
        orologio["t"] = ORA_ZERO + 2 * GIORNO
        _nuova_richiesta()

        client.get("/aiuto/")

        assert self._rinnovata(client) is None
