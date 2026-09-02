"""Gli eventi live attraversano i processi, e non si perdono per strada.

In produzione la web app gira su tre worker uWSGI, cioè tre **processi** con
tre memorie separate (server log del 2026-09-02: worker 1 pid 29, worker 2 pid
32, worker 3 pid 35). L'archivio degli eventi di `routes/sse.py` era un
dizionario Python a livello di modulo: un rack segnato sul worker 29 lo vedeva
solo un poll servito dal worker 29. E siccome il cursore del client avanza a
ogni poll, anche vuoto, un evento mancato una volta era perso per sempre. In
sviluppo — un processo solo — funzionava sempre, ed è per questo che il difetto
si presentava come «a volte non si aggiorna».

L'archivio ora è la tabella `live_event`, l'unica cosa che i tre processi
condividono. Da qui discendono le altre proprietà verificate in questo file:

* il cursore è l'**id** dell'ultima riga vista, non un orologio: SQLite ha un
  solo scrittore per volta, quindi gli id si committano in ordine e «id
  maggiore del cursore» non salta niente; l'orologio del telefono non c'entra
  più;
* gli id **non si riusano** dopo la pulizia (AUTOINCREMENT): con il rowid
  semplice, cancellata la riga più alta, la successiva ne prenderebbe il
  numero e un cursore fermo lì non vedrebbe più nulla;
* un evento emesso **dentro** una transazione compare solo al commit, insieme
  al fatto che lo ha generato: prima, un poll fra emit e commit ricaricava una
  pagina che leggeva ancora lo stato vecchio, e consumava l'evento;
* la tabella tiene un minuto di attività e non cresce: la pulizia gira a ogni
  emit, con lo stesso limite di 60 secondi di prima.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from routes import sse
from routes.sse import (
    MAX_EVENT_AGE,
    EventScope,
    _current_cursor,
    _get_events_since,
    emit_event,
)

RADICE = Path(__file__).resolve().parents[3]

#: Costruisce l'app dei test su un database **su file**: è quello che un
#: secondo processo può aprire. Testo condiviso fra padre e figlio, così i due
#: costruiscono la stessa app.
APP_SU_FILE = textwrap.dedent("""
    def app_su_file(percorso):
        import config as modulo_config
        from config import TestingConfig

        class SuFile(TestingConfig):
            @classmethod
            def environment_settings(cls):
                valori = super().environment_settings()
                valori["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + percorso
                return valori

        modulo_config.config["testing_su_file"] = SuFile
        from app import create_app

        return create_app("testing_su_file")
    """)

_spazio: dict = {}
exec(APP_SU_FILE, _spazio)
app_su_file = _spazio["app_su_file"]


@pytest.fixture(autouse=True)
def _archivio_pulito(db_session):
    """Ogni test parte da una tabella vuota e da una pulizia mai eseguita."""
    from models.live_event import LiveEvent

    LiveEvent.query.delete()
    db_session.commit()
    sse._last_sweep = 0.0
    yield
    sse._last_sweep = 0.0


@pytest.fixture
def app_su_file_tmp(tmp_path):
    percorso = str(tmp_path / "eventi.db")
    app = app_su_file(percorso)
    from models import db

    with app.app_context():
        db.create_all()
    return app, percorso


# ═══════════════════════════════════════════════════════════════════════════
# Un processo emette, un altro legge
# ═══════════════════════════════════════════════════════════════════════════


def test_un_evento_emesso_da_un_altro_processo_arriva_al_poll(app_su_file_tmp):
    """Il worker che scrive e quello che risponde al poll non sono lo stesso."""
    app, percorso = app_su_file_tmp

    figlio = APP_SU_FILE + textwrap.dedent(f"""
        app = app_su_file({percorso!r})
        with app.app_context():
            from routes.sse import EventScope, emit_event

            emit_event(EventScope.GARA, 42, "match_updated", {{"match_id": 7}})
        print("emesso")
        """)
    esito = subprocess.run(
        [sys.executable, "-c", figlio],
        cwd=RADICE,
        env={**os.environ, "FLASK_ENV": "testing"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert esito.returncode == 0, esito.stderr
    assert "emesso" in esito.stdout

    with app.app_context():
        eventi = _get_events_since(EventScope.GARA, 42, 0)

    assert [(e["type"], e["data"]) for e in eventi] == [
        ("match_updated", {"match_id": 7})
    ]


def test_dentro_una_transazione_l_evento_compare_solo_al_commit(app_su_file_tmp):
    """Il bridge emette dentro `@transactional`: l'evento viaggia col fatto.

    Un altro processo — qui una connessione sqlite3 indipendente — non deve
    vedere l'evento prima del commit, altrimenti un poll in quella finestra
    ricarica una pagina che legge ancora lo stato vecchio.
    """
    app, percorso = app_su_file_tmp
    from models.transaction.manager import transaction_manager

    def righe():
        with sqlite3.connect(percorso) as conn:
            return conn.execute("SELECT COUNT(*) FROM live_event").fetchone()[0]

    with app.app_context():
        with transaction_manager.transaction():
            emit_event(EventScope.GARA, 1, "match_updated", {"match_id": 1})
            assert righe() == 0, "visibile prima del commit"
        assert righe() == 1


def test_fuori_da_una_transazione_l_evento_si_salva_da_solo(app_su_file_tmp):
    """Le route emettono dopo che il servizio ha già committato.

    Se `emit_event` si limitasse ad aggiungere la riga alla sessione, il
    teardown della richiesta la butterebbe via con un rollback.
    """
    app, percorso = app_su_file_tmp
    from models import db

    with app.app_context():
        emit_event(EventScope.MATCH, 5, "rack_added", {"match_id": 5})
        db.session.remove()  # quello che fa Flask a fine richiesta

    with sqlite3.connect(percorso) as conn:
        assert conn.execute("SELECT COUNT(*) FROM live_event").fetchone()[0] == 1


# ═══════════════════════════════════════════════════════════════════════════
# Cursore
# ═══════════════════════════════════════════════════════════════════════════


def test_il_cursore_e_l_id_e_non_salta_niente():
    emit_event(EventScope.GARA, 42, "match_updated", {"n": 1})
    emit_event(EventScope.GARA, 42, "match_updated", {"n": 2})
    emit_event(EventScope.GARA, 99, "match_updated", {"n": 3})  # altra gara

    primi = _get_events_since(EventScope.GARA, 42, 0)
    assert [e["data"]["n"] for e in primi] == [1, 2]

    emit_event(EventScope.GARA, 42, "match_completed", {"n": 4})
    dopo = _get_events_since(EventScope.GARA, 42, primi[-1]["id"])
    assert [e["data"]["n"] for e in dopo] == [4]
    assert dopo[0]["id"] > primi[-1]["id"]


def test_il_cursore_iniziale_e_l_ultimo_id_scritto():
    assert _current_cursor() == 0
    emit_event(EventScope.USER, 1, "xp_gained", {"xp": 10})
    emit_event(EventScope.USER, 2, "xp_gained", {"xp": 20})
    assert _current_cursor() == _get_events_since(EventScope.USER, 2, 0)[0]["id"]


def test_gli_id_non_si_riusano_dopo_la_pulizia():
    """Rowid semplice: cancellata la riga più alta, la prossima ne prende il
    numero, e il client col cursore fermo lì non vede più nulla."""
    with patch("routes.sse.time.time", return_value=1000.0):
        emit_event(EventScope.GARA, 42, "match_updated", {"n": 1})
    primo = _get_events_since(EventScope.GARA, 42, 0)[0]["id"]

    sse._last_sweep = 0.0
    with patch("routes.sse.time.time", return_value=1000.0 + MAX_EVENT_AGE + 1):
        emit_event(EventScope.GARA, 42, "match_updated", {"n": 2})

    eventi = _get_events_since(EventScope.GARA, 42, primo)
    assert [e["data"]["n"] for e in eventi] == [2]
    assert eventi[0]["id"] > primo


# ═══════════════════════════════════════════════════════════════════════════
# Pulizia: un minuto di attività, non di più
# ═══════════════════════════════════════════════════════════════════════════


def test_gli_eventi_piu_vecchi_di_un_minuto_spariscono():
    from models.live_event import LiveEvent

    with patch("routes.sse.time.time", return_value=1000.0):
        emit_event(EventScope.GARA, 42, "match_completed", {"n": 1})
        emit_event(EventScope.USER, 7, "xp_gained", {"n": 2})

    sse._last_sweep = 0.0
    with patch("routes.sse.time.time", return_value=1000.0 + MAX_EVENT_AGE + 1):
        emit_event(EventScope.TRIO, 3, "rack_added", {"n": 3})

    assert [(r.scope, r.scope_id) for r in LiveEvent.query.order_by(LiveEvent.id)] == [
        ("trio", 3)
    ]


def test_la_pulizia_non_gira_a_ogni_emit():
    """È ammortizzata: una DELETE per ogni SWEEP_INTERVAL, non per ogni rack."""
    from models.live_event import LiveEvent

    with patch("routes.sse.time.time", return_value=1000.0):
        emit_event(EventScope.GARA, 42, "match_completed", {"n": 1})

    # Prima pulizia: la riga è ancora fresca.
    sse._last_sweep = 0.0
    with patch("routes.sse.time.time", return_value=1001.0):
        emit_event(EventScope.GARA, 42, "match_completed", {"n": 2})

    # Un minuto e un secondo dopo, ma dentro l'intervallo di pulizia:
    # la vecchia resta, la DELETE non è partita.
    with patch("routes.sse.time.time", return_value=1001.0 + sse.SWEEP_INTERVAL - 1):
        emit_event(EventScope.GARA, 42, "match_completed", {"n": 3})
    assert LiveEvent.query.count() == 3


# ═══════════════════════════════════════════════════════════════════════════
# Endpoint di poll: il protocollo col client
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def client_loggato(app, db_session):
    from models import User
    from models.user.role_enum import UserRole

    utente = User(
        username="poller", email="poller@test.local", role=UserRole.PLAYER.value
    )
    utente.set_password("x")
    db_session.add(utente)
    db_session.commit()

    client = app.test_client()
    with client.session_transaction() as sessione:
        sessione["_user_id"] = utente.get_id()
        sessione["_fresh"] = True
    return client, utente


def test_il_primo_poll_senza_cursore_non_consegna_il_passato(client_loggato):
    """Il client non ha più un orologio da confrontare con quello del server:
    al primo giro riceve solo il cursore, e da lì in poi gli eventi nuovi."""
    client, _ = client_loggato
    emit_event(EventScope.GARA, 42, "match_updated", {"n": "vecchio"})

    primo = client.get("/sse/poll/gara/42").get_json()
    assert primo["events"] == []
    assert primo["cursor"] == _current_cursor()
    assert primo["retention"] == MAX_EVENT_AGE

    emit_event(EventScope.GARA, 42, "match_updated", {"n": "nuovo"})
    secondo = client.get(f"/sse/poll/gara/42?since={primo['cursor']}").get_json()
    assert [e["data"]["n"] for e in secondo["events"]] == ["nuovo"]
    assert secondo["cursor"] == secondo["events"][-1]["id"]

    # Senza eventi il cursore resta dov'era: non c'è più un orologio che
    # lo faccia avanzare oltre un evento non ancora committato.
    terzo = client.get(f"/sse/poll/gara/42?since={secondo['cursor']}").get_json()
    assert terzo["events"] == []
    assert terzo["cursor"] == secondo["cursor"]


def test_una_pagina_col_vecchio_client_riceve_ancora_gli_eventi(client_loggato):
    """Il vecchio client manda un timestamp come `since` e legge `timestamp`
    dalla risposta: nella finestra del deploy deve continuare a funzionare col
    criterio di prima, altrimenti resta muta finché qualcuno non ricarica."""
    client, _ = client_loggato
    with patch("routes.sse.time.time", return_value=1000.0):
        emit_event(EventScope.GARA, 42, "match_updated", {"n": 1})

    prima = client.get("/sse/poll/gara/42?since=999.5").get_json()
    assert [e["data"]["n"] for e in prima["events"]] == [1]
    assert isinstance(prima["timestamp"], float)

    dopo = client.get("/sse/poll/gara/42?since=1000.5").get_json()
    assert dopo["events"] == []


def test_un_cursore_non_numerico_vale_come_primo_poll(client_loggato):
    client, _ = client_loggato
    emit_event(EventScope.GARA, 42, "match_updated", {"n": 1})
    risposta = client.get("/sse/poll/gara/42?since=boh").get_json()
    assert risposta["events"] == []
    assert risposta["cursor"] == _current_cursor()


def test_il_poll_utente_resta_solo_del_proprietario(client_loggato):
    client, utente = client_loggato
    assert client.get(f"/sse/poll/user/{utente.id + 1}").status_code == 403
    assert client.get(f"/sse/poll/user/{utente.id}").status_code == 200
