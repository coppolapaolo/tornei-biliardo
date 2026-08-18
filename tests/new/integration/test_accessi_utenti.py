"""La traccia degli accessi: chi si collega, quando, per quanto.

Prima di questa tabella non c'era modo di rispondere. La scheda «retention»
dei KPI mostra DAU/WAU/MAU da mesi, ma li calcola sui **match giocati**: chi
entra ogni giorno e non gioca risulta dormiente.

I test guardano le tre cose che si possono sbagliare in silenzio, cioe' quelle
che darebbero numeri plausibili e falsi:

- la sessione deve **aprirsi al login**, e il login avviene da tre punti
  diversi: l'aggancio e' al segnale di Flask-Login, non alla route;
- una pausa lunga deve **chiudere** la sessione vecchia e aprirne una nuova,
  altrimenti un «ricordami» fa di una settimana un unico accesso da 7 giorni;
- le risposte non-HTML **non** sono un segno di vita, altrimenti una pagina
  che interroga il server a intervalli tiene «viva» una scheda abbandonata.
"""

from datetime import timedelta

import pytest

from models import db
from models.base import utc_now
from models.user.models import User
from models.user.role_enum import UserRole
from models.user.session_models import INATTIVITA_MASSIMA, UserSession
from models.user.session_service import CHIAVE_VISTO


def _crea_utente(db_session, username="entrante", role=UserRole.PLAYER.value):
    utente = User(username=username, email=f"{username}@test.local", role=role)
    utente.set_password("test123")
    utente.is_verified = True
    db_session.add(utente)
    db_session.commit()
    return utente


def _entra(client, username, password="test123"):
    return client.post(
        "/auth/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


@pytest.mark.integration
def test_il_login_apre_una_sessione(app, db_session):
    """L'aggancio e' al segnale, non alla route: `login_user()` ha tre chiamanti."""
    utente = _crea_utente(db_session, "apre")
    client = app.test_client()

    _entra(client, "apre")

    accessi = UserSession.query.filter_by(user_id=utente.id).all()
    assert len(accessi) == 1
    assert accessi[0].ended_at is None
    assert accessi[0].e_aperta


@pytest.mark.integration
def test_il_logout_chiude_all_ultimo_istante_certo(app, db_session):
    """Chiudere ad «adesso» regalerebbe alla sessione il tempo in cui non c'era."""
    utente = _crea_utente(db_session, "esce")
    client = app.test_client()
    _entra(client, "esce")

    accesso = UserSession.query.filter_by(user_id=utente.id).one()
    ultimo = accesso.last_seen_at

    client.get("/auth/logout", follow_redirects=True)

    db_session.refresh(accesso)
    assert accesso.ended_at == ultimo
    assert not accesso.e_aperta


@pytest.mark.integration
def test_una_pausa_lunga_apre_una_sessione_nuova(app, db_session):
    """Senza questa regola una settimana diventa un unico accesso da 7 giorni."""
    utente = _crea_utente(db_session, "ritorna")
    client = app.test_client()
    _entra(client, "ritorna")

    accesso = UserSession.query.filter_by(user_id=utente.id).one()
    # Lo spostiamo indietro nel tempo: la prossima pagina arriva dopo la pausa.
    vecchio_ultimo = utc_now() - INATTIVITA_MASSIMA - timedelta(minutes=5)
    accesso.started_at = vecchio_ultimo - timedelta(minutes=10)
    accesso.last_seen_at = vecchio_ultimo
    db.session.commit()

    # Anche la strozzatura nel cookie va spostata, o la richiesta non scrive.
    with client.session_transaction() as sessione:
        sessione[CHIAVE_VISTO] = vecchio_ultimo.timestamp()

    client.get("/", follow_redirects=True)

    accessi = (
        UserSession.query.filter_by(user_id=utente.id)
        .order_by(UserSession.started_at)
        .all()
    )
    assert len(accessi) == 2, "la pausa doveva chiudere la vecchia e aprirne una"
    assert accessi[0].ended_at == vecchio_ultimo
    assert accessi[1].ended_at is None


@pytest.mark.integration
def test_le_risposte_non_html_non_sono_un_segno_di_vita(app, db_session):
    """Il polling terrebbe «viva» una scheda abbandonata su un tavolo vuoto."""
    utente = _crea_utente(db_session, "polling")
    client = app.test_client()
    _entra(client, "polling")

    accesso = UserSession.query.filter_by(user_id=utente.id).one()
    fermo = utc_now() - timedelta(minutes=20)
    accesso.last_seen_at = fermo
    db.session.commit()
    with client.session_transaction() as sessione:
        sessione[CHIAVE_VISTO] = fermo.timestamp()

    risposta = client.get("/health")
    assert risposta.mimetype == "application/json"

    db_session.refresh(accesso)
    assert accesso.last_seen_at == fermo, "una risposta JSON non e' una visita"


@pytest.mark.integration
def test_la_pagina_accessi_filtra_per_nome(app, db_session, logged_in_client):
    """Il filtro per nome e' la ragione per cui la pagina sta sotto «Utenti»."""
    cercato = _crea_utente(db_session, "cercato")
    altro = _crea_utente(db_session, "ignorato")
    for utente in (cercato, altro):
        db.session.add(
            UserSession(user_id=utente.id, started_at=utc_now(), last_seen_at=utc_now())
        )
    db.session.commit()

    client, _ = logged_in_client(role=UserRole.ADMIN.value, username_prefix="capo")
    pagina = client.get("/admin/users/accessi?q=cercato")

    assert pagina.status_code == 200
    corpo = pagina.get_data(as_text=True)
    # Sul nome nudo non si puo' asserire: in configurazione di test la barra
    # dei quick-login elenca tutti gli utenti, filtro o non filtro. Il segno
    # che una riga e' *nella tabella* e' il link alla sua scheda.
    assert f"/admin/user/{cercato.id}" in corpo
    assert f"/admin/user/{altro.id}" not in corpo


@pytest.mark.integration
def test_chi_non_e_mai_entrato_compare_a_parte(app, db_session, logged_in_client):
    """E' la domanda che manda in fumo il senso di un'iscrizione."""
    fantasma = _crea_utente(db_session, "fantasma")
    fantasma.created_at = utc_now() - timedelta(days=60)
    fantasma.is_verified = False
    db.session.commit()

    client, _ = logged_in_client(role=UserRole.ADMIN.value, username_prefix="capo2")
    corpo = client.get("/admin/users/accessi").get_data(as_text=True)

    assert "fantasma" in corpo
    assert "Rimanda verifica" in corpo, "senza verifica confermata serve il pulsante"
