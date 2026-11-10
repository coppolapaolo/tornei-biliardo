"""Un evento accodato per il JavaScript non può chiudere lo script (2026-11-10).

I toast della gamification e gli eventi di analytics viaggiano in un messaggio
flash come JSON, e `base.html` li scriveva dentro uno `<script>` con `|safe`.
`json.dumps` non neutralizza `</script>`: un testo scelto da un utente dentro
il payload — un nome, un titolo — poteva chiudere lo script e far interpretare
il resto come HTML. Ora il payload si rilegge e si riscrive con `|tojson`, che
codifica `<`, `>` e `&`: il valore resta lo stesso, ma dentro la pagina non
compare più nessuna sequenza che il browser possa leggere come tag.
"""

import json
import re

VELENO = "</script><script>window.intruso=1</script>"


def _accoda(client, categoria, payload):
    with client.session_transaction() as sessione:
        sessione["_flashes"] = [(categoria, json.dumps(payload))]


def _valore_nello_script(pagina, nome_variabile):
    trovato = re.search(rf"{nome_variabile} = (.*);\n", pagina)
    assert trovato, f"{nome_variabile} non è nella pagina"
    return json.loads(trovato.group(1))


def test_il_toast_di_gamification_non_chiude_lo_script(db_session, logged_in_client):
    client, _utente = logged_in_client(role="player", username_prefix="toast")
    payload = {"type": "welcome", "data": {"username": VELENO, "level": 1}}
    _accoda(client, "gamification_event", payload)

    pagina = client.get("/segnalazioni/").get_data(as_text=True)

    assert VELENO not in pagina
    assert "<script>window.intruso" not in pagina
    assert _valore_nello_script(pagina, "const eventData") == payload


def test_un_toast_normale_arriva_com_era(db_session, logged_in_client):
    client, _utente = logged_in_client(role="player", username_prefix="toast")
    payload = {"type": "xp_gained", "data": {"amount": 15, "reason": "l'esame"}}
    _accoda(client, "gamification_event", payload)

    pagina = client.get("/segnalazioni/").get_data(as_text=True)

    assert _valore_nello_script(pagina, "const eventData") == payload
    assert "window.showGamificationEvent(eventData.type, eventData.data)" in pagina


def test_l_evento_di_analytics_non_chiude_lo_script(
    app, db_session, logged_in_client, monkeypatch
):
    monkeypatch.setitem(app.config, "GA_MEASUREMENT_ID", "G-PROVA")
    client, _utente = logged_in_client(role="player", username_prefix="ga")
    payload = {"name": "sign_up", "params": {"method": VELENO}}
    _accoda(client, "analytics_event", payload)

    pagina = client.get("/segnalazioni/").get_data(as_text=True)

    assert VELENO not in pagina
    assert _valore_nello_script(pagina, "var analyticsEvent") == payload
