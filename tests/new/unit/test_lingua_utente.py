"""La lingua dell'utente: da dove si ricava e quando si scrive (ADR-062).

Gemella del fuso di ADR-043. Una notifica, un promemoria, un avviso composto
da uno scheduled task non hanno davanti il browser del destinatario: la lingua
in cui scrivergli deve stare in colonna, altrimenti fuori da una pagina non
esiste.

Due fonti, con un ordine preciso: la **scelta** fatta col selettore vince
sempre; la lingua **dedotta** dal browser riempie solo un vuoto e non
sovrascrive mai una scelta.
"""

import uuid

import pytest

from models.base import db
from models.user.models import User
from models.user.role_enum import UserRole
from models.user.services import UserService
from utils.lingua import (
    LINGUA_DI_RIPIEGO,
    lingua_per_user_id,
    normalizza_lingua,
    ricorda_lingua_dedotta,
)


def _utente(db_session, lingua=None):
    codice = uuid.uuid4().hex[:8]
    utente = User(
        username=f"u_{codice}",
        email=f"{codice}@test.local",
        role=UserRole.PLAYER.value,
    )
    utente.set_password("password-di-prova")
    utente.language = lingua
    db_session.add(utente)
    db_session.commit()
    return utente


@pytest.mark.parametrize(
    "valore,attesa",
    [
        ("it", "it"),
        ("en", "en"),
        ("EN", "en"),
        ("en-GB", "en"),
        ("en_US", "en"),
        ("it-IT", "it"),
        ("de", None),
        ("", None),
        (None, None),
        ("inglese", None),
    ],
)
def test_una_lingua_si_normalizza_o_si_scarta(valore, attesa):
    assert normalizza_lingua(valore) == attesa


def test_il_ripiego_e_l_italiano(db_session):
    senza = _utente(db_session)
    assert LINGUA_DI_RIPIEGO == "it"
    assert lingua_per_user_id(senza.id) == "it"
    assert lingua_per_user_id(None) == "it"
    assert lingua_per_user_id(10_000_000) == "it"
    assert lingua_per_user_id(_utente(db_session, "en").id) == "en"


def test_la_lingua_dedotta_riempie_solo_un_vuoto(db_session):
    utente = _utente(db_session)

    assert UserService.remember_language(utente.id, "en-GB") is True
    assert db.session.get(User, utente.id).language == "en"

    assert UserService.remember_language(utente.id, "it") is False
    assert db.session.get(User, utente.id).language == "en"


def test_la_scelta_vince_sulla_deduzione(db_session):
    utente = _utente(db_session, "en")

    assert UserService.remember_language(utente.id, "it", esplicita=True) is True
    assert db.session.get(User, utente.id).language == "it"


def test_una_lingua_che_l_app_non_parla_si_scarta(db_session):
    utente = _utente(db_session, "it")

    assert UserService.remember_language(utente.id, "de", esplicita=True) is False
    assert db.session.get(User, utente.id).language == "it"


def test_il_selettore_salva_la_scelta_di_chi_e_collegato(app, client, db_session):
    from flask import g

    utente = _utente(db_session, "it")
    with client.session_transaction() as sessione:
        sessione["_user_id"] = utente.get_id()
    g.pop("_login_user", None)

    risposta = client.get("/set_language/en")

    assert risposta.status_code == 302
    db.session.expire_all()
    assert db.session.get(User, utente.id).language == "en"


def test_il_selettore_funziona_anche_per_un_anonimo(client):
    from flask import g

    g.pop("_login_user", None)
    risposta = client.get("/set_language/en")
    assert risposta.status_code == 302


def test_al_primo_accesso_la_lingua_si_deduce_dal_browser(app, db_session):
    utente = _utente(db_session)

    with app.test_request_context(
        "/", headers={"Accept-Language": "en-GB,en;q=0.9,it;q=0.5"}
    ):
        ricorda_lingua_dedotta(utente)

    assert db.session.get(User, utente.id).language == "en"


def test_la_lingua_di_sessione_vale_piu_del_browser(app, db_session):
    from flask import session

    utente = _utente(db_session)

    with app.test_request_context("/", headers={"Accept-Language": "en"}):
        session["language"] = "it"
        ricorda_lingua_dedotta(utente)

    assert db.session.get(User, utente.id).language == "it"


def test_una_lingua_gia_salvata_non_si_riscrive_col_browser(app, db_session):
    utente = _utente(db_session, "it")

    with app.test_request_context("/", headers={"Accept-Language": "en"}):
        ricorda_lingua_dedotta(utente)

    assert db.session.get(User, utente.id).language == "it"


def test_un_anonimo_non_scrive_niente(app):
    from flask_login import AnonymousUserMixin

    with app.test_request_context("/", headers={"Accept-Language": "en"}):
        ricorda_lingua_dedotta(AnonymousUserMixin())
