"""Le route di debug devono spegnersi quando l'app non è in debug mode.

Il guard c'era, ma leggeva `Config.DEBUG_MODE` — l'attributo della **classe
base**, che vale `os.environ.get("DEBUG_MODE", "true")`. In produzione l'app
usa `ProductionConfig`, dove `DEBUG_MODE = False`, ma quella classe il guard
non la interrogava mai: bastava che la variabile d'ambiente non fosse
impostata (e in produzione non lo è) perché `Config.DEBUG_MODE` risultasse
`True` e il guard non scattasse.

Restava in piedi solo la difesa dell'allowlist (ADR-028), che nasconde con un
404 gli endpoint non elencati — ma **l'allowlist fa bypass per gli admin**,
quindi un amministratore autenticato poteva raggiungere `/reset` in
produzione. Ora il guard legge la configurazione dell'app attiva.
"""

from __future__ import annotations

import pytest

# Route che non devono esistere fuori dal debug. Sono GET senza effetti
# collaterali finché il guard regge: se un giorno il guard cade, questo test
# fallisce prima che lo faccia la produzione.
DEBUG_ROUTES = [
    "/reset",
    "/debug/login/admin",
    "/debug/create_player",
    "/gamification/test",
]


@pytest.fixture
def debug_off(app):
    """App identica a quella dei test, ma con il debug mode spento."""
    original = app.config.get("DEBUG_MODE")
    app.config["DEBUG_MODE"] = False
    yield app
    app.config["DEBUG_MODE"] = original


@pytest.mark.unit
@pytest.mark.parametrize("path", DEBUG_ROUTES)
def test_route_di_debug_negata_senza_debug_mode(debug_off, client, path):
    response = client.get(path, follow_redirects=False)

    assert response.status_code in (403, 404), (
        f"{path} ha risposto {response.status_code}: la route di debug e'"
        " raggiungibile con DEBUG_MODE spento."
    )


@pytest.mark.unit
def test_quick_login_non_autentica_senza_debug_mode(debug_off, client):
    """Il caso peggiore: `/debug/login/<username>` autentica senza password."""
    client.get("/debug/login/admin", follow_redirects=False)

    # Nessuna sessione: la richiesta successiva e' ancora anonima.
    with client.session_transaction() as session:
        assert "_user_id" not in session


@pytest.mark.unit
@pytest.mark.parametrize("path", DEBUG_ROUTES)
def test_route_di_debug_disponibili_in_debug_mode(app, client, path):
    """Guardia del guardiano: in sviluppo devono continuare a funzionare,
    altrimenti il test qui sopra passerebbe per il motivo sbagliato."""
    app.config["DEBUG_MODE"] = True

    response = client.get(path, follow_redirects=False)

    assert response.status_code not in (403, 404), (
        f"{path} ha risposto {response.status_code} con DEBUG_MODE attivo:"
        " la route di debug non e' piu' raggiungibile in sviluppo."
    )
