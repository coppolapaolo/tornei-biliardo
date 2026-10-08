"""Un deploy interrotto dopo il pull rimette sul disco il codice di prima.

Incidente 2026-10-08. Il `git pull` aveva portato 131 file e due migration;
il `disable` della web app, chiesto all'API di PythonAnywhere, ha risposto
`502 Bad Gateway`. Lo script si è fermato come doveva — niente migration con
la web app accesa — ma il codice nuovo era **già sul disco**, e una web app
che non viene ricaricata non resta «sul codice precedente»: resta in uno stato
misto. I moduli già importati sono quelli vecchi, ma i template e i moduli
importati più tardi si leggono dal disco, quindi sono nuovi. Il risultato sono
stati i 500 per `ClassificationSystem.POINTS` mancante e per `ssr_fino_al`
non definito, mentre ogni processo nuovo — `daily_jobs` — partiva col codice
nuovo su uno schema senza `gara.points_win`.

La regola: se il deploy si ferma dopo il pull, il disco torna al commit da cui
era partito. Il giro successivo trova di nuovo commit da portare e ritenta da
capo, invece di trovare «Already up to date» con l'app rotta.
"""

from __future__ import annotations

import urllib.error

import pytest

import scripts.auto_deploy as auto_deploy

pytestmark = pytest.mark.unit


# --- l'API di PythonAnywhere: un 502 si riprova --------------------------------


class _Risposta:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _errore_http(codice):
    return urllib.error.HTTPError("url", codice, "errore", {}, None)


def test_un_502_si_riprova(monkeypatch):
    """Il 502 del 2026-10-08 era dell'API, non nostro: un secondo tentativo basta."""
    monkeypatch.setenv("API_TOKEN", "token")
    monkeypatch.setattr(auto_deploy.time, "sleep", lambda _s: None)
    tentativi = []

    def urlopen(_request, timeout):
        tentativi.append(1)
        if len(tentativi) == 1:
            raise _errore_http(502)
        return _Risposta()

    monkeypatch.setattr(auto_deploy.urllib.request, "urlopen", urlopen)

    ok, _ = auto_deploy.webapp_api("disable")

    assert ok is True
    assert len(tentativi) == 2


def test_un_errore_del_client_non_si_riprova(monkeypatch):
    """Un 401 è un token sbagliato: ripeterlo non lo aggiusta."""
    monkeypatch.setenv("API_TOKEN", "token")
    monkeypatch.setattr(auto_deploy.time, "sleep", lambda _s: None)
    tentativi = []

    def urlopen(_request, timeout):
        tentativi.append(1)
        raise _errore_http(401)

    monkeypatch.setattr(auto_deploy.urllib.request, "urlopen", urlopen)

    ok, _ = auto_deploy.webapp_api("disable")

    assert ok is False
    assert len(tentativi) == 1


def test_i_tentativi_finiscono(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "token")
    monkeypatch.setattr(auto_deploy.time, "sleep", lambda _s: None)
    tentativi = []

    def urlopen(_request, timeout):
        tentativi.append(1)
        raise _errore_http(502)

    monkeypatch.setattr(auto_deploy.urllib.request, "urlopen", urlopen)

    ok, msg = auto_deploy.webapp_api("disable")

    assert ok is False
    assert len(tentativi) == auto_deploy.API_TENTATIVI
    assert "502" in msg


# --- il ripristino dentro le migration ----------------------------------------


def _registra(calls, nome, esito=(True, "ok")):
    def finto(*_args, **_kwargs):
        calls.append(nome)
        return esito

    return finto


def test_disable_fallito_ripristina_il_codice(monkeypatch):
    calls = []
    monkeypatch.setattr(
        auto_deploy,
        "webapp_api",
        lambda action: _registra(calls, action, (False, "HTTP 502"))(),
    )
    monkeypatch.setattr(auto_deploy, "run_migrations", _registra(calls, "migrate"))

    success, _ = auto_deploy.run_migrations_safely(_registra(calls, "ripristina"))

    assert success is False
    assert calls == ["disable", "ripristina"]


def test_migration_fallita_ripristina_prima_di_riaccendere(monkeypatch):
    """L'enable fa ripartire i worker dal disco: il disco dev'essere già tornato
    al codice che va d'accordo con lo schema che c'è."""
    calls = []
    monkeypatch.setattr(
        auto_deploy, "webapp_api", lambda action: _registra(calls, action)()
    )
    monkeypatch.setattr(
        auto_deploy, "run_migrations", _registra(calls, "migrate", (False, "boom"))
    )

    success, _ = auto_deploy.run_migrations_safely(_registra(calls, "ripristina"))

    assert success is False
    assert calls == ["disable", "migrate", "ripristina", "enable"]


def test_migration_riuscita_non_ripristina(monkeypatch):
    calls = []
    monkeypatch.setattr(
        auto_deploy, "webapp_api", lambda action: _registra(calls, action)()
    )
    monkeypatch.setattr(auto_deploy, "run_migrations", _registra(calls, "migrate"))

    success, _ = auto_deploy.run_migrations_safely(_registra(calls, "ripristina"))

    assert success is True
    assert "ripristina" not in calls


# --- main(): ogni uscita dopo il pull riporta il disco indietro ----------------


@pytest.fixture
def deploy_con_codice_nuovo(monkeypatch):
    """`main()` con il pull che porta codice nuovo e ogni passo finto."""
    comandi: list[list[str]] = []

    monkeypatch.setenv("ENCRYPTION_KEY", "chiave-di-prova")
    monkeypatch.setattr(auto_deploy, "load_wsgi_env", lambda: {"ENCRYPTION_KEY": "x"})
    monkeypatch.setattr(auto_deploy, "git_head", lambda: "aaaa111")
    monkeypatch.setattr(
        auto_deploy, "git_pull", lambda: (True, "Updating aaaa111..bbbb222")
    )
    monkeypatch.setattr(auto_deploy, "count_pending_migrations", lambda: 2)
    monkeypatch.setattr(auto_deploy, "reload_webapp", lambda: (True, "ok"))

    def run_command(cmd, cwd=None):
        comandi.append(cmd)
        return True, ""

    monkeypatch.setattr(auto_deploy, "run_command", run_command)
    return comandi


def test_dipendenze_fallite_ripristinano_il_codice(
    deploy_con_codice_nuovo, monkeypatch
):
    monkeypatch.setattr(
        auto_deploy, "install_dependencies", lambda: (False, "pip rotto")
    )

    with pytest.raises(SystemExit):
        auto_deploy.main()

    assert ["git", "reset", "--keep", "aaaa111"] in deploy_con_codice_nuovo


def test_disable_fallito_in_main_ripristina_il_codice(
    deploy_con_codice_nuovo, monkeypatch
):
    """Il caso esatto del 2026-10-08."""
    monkeypatch.setattr(auto_deploy, "install_dependencies", lambda: (True, ""))
    monkeypatch.setattr(auto_deploy, "webapp_api", lambda action: (False, "HTTP 502"))

    with pytest.raises(SystemExit):
        auto_deploy.main()

    assert ["git", "reset", "--keep", "aaaa111"] in deploy_con_codice_nuovo


def test_deploy_riuscito_non_ripristina(deploy_con_codice_nuovo, monkeypatch):
    monkeypatch.setattr(auto_deploy, "install_dependencies", lambda: (True, ""))
    monkeypatch.setattr(auto_deploy, "run_migrations_safely", lambda *_a: (True, "ok"))

    auto_deploy.main()

    assert not any(cmd[:2] == ["git", "reset"] for cmd in deploy_con_codice_nuovo)
