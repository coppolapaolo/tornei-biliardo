"""«Elimina l'account» sta solo nel profilo, fra le azioni irreversibili.

Nel menu utente la voce stava fra il cambio di lingua e il logout: un comando
distruttivo a un tocco di distanza dai due che si usano di più. Il posto
giusto è in fondo al profilo, nella sezione «Azioni irreversibili», dove si
arriva solo cercandolo.
"""

from __future__ import annotations

import uuid

import pytest
from flask import g, url_for

from models.base import db
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def giocatore(db_session) -> User:
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"menu_{sigla}",
        email=f"menu_{sigla}@example.com",
        role=UserRole.PLAYER.value,
        onboarding_completed=True,
    )
    utente.set_password("x")
    db.session.add(utente)
    db.session.commit()
    return utente


def _apri(client, utente, endpoint):
    with client.session_transaction() as sess:
        # `get_id()` e non l'id nudo: l'id di sessione porta un'impronta della
        # credenziale (ADR-055), e senza il client resta non autenticato.
        sess["_user_id"] = utente.get_id()
        sess["_fresh"] = True
    # In questa suite `g` non è per-richiesta: senza ripulirlo Flask-Login
    # riusa l'utente in cache.
    g.pop("_login_user", None)
    with client.application.test_request_context():
        url = url_for(endpoint)
        url_elimina = url_for("player.delete_account")
    risposta = client.get(url)
    assert risposta.status_code == 200
    return risposta.get_data(as_text=True), url_elimina


def _menu_utente(html: str) -> str:
    """Il solo menu utente: la pagina lo include due volte (barra e testata)."""
    inizio = html.index('<ul class="dropdown-menu dropdown-menu-end">')
    return html[inizio : html.index("</ul>", inizio)]


def test_il_menu_utente_non_offre_di_eliminare_l_account(client, giocatore):
    html, url_elimina = _apri(client, giocatore, "dashboard.dashboard")

    menu = _menu_utente(html)
    assert "logout" in menu, "ritaglio del menu sbagliato"
    assert url_elimina not in menu


def test_il_profilo_la_offre_fra_le_azioni_irreversibili(client, giocatore):
    html, url_elimina = _apri(client, giocatore, "player.profile")

    sezione = html[html.index("Azioni irreversibili") :]
    assert url_elimina in sezione
