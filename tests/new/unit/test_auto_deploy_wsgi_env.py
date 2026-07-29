"""Test per scripts/auto_deploy.py: env di produzione lette dal file WSGI.

Lo scheduled task gira in un processo separato che non esegue mai il file
WSGI, quindi non ne eredita le variabili d'ambiente. Senza ENCRYPTION_KEY una
migration sui PII non solleva: `decrypt_data` fallisce, il guard salta la riga
e il backfill resta vuoto, con la migration comunque marcata come applicata.

E' successo il 2026-06-25 con `20260625_add_email_hash`: 0 hash scritti su 37
utenti e recupero password silenziosamente rotto per cinque settimane (il
`request_password_reset` ritorna True anche a utente non trovato, per non
esporre l'enumerazione degli account).
"""

import pytest

import scripts.auto_deploy as auto_deploy


def _write(tmp_path, body: str):
    wsgi = tmp_path / "fake_wsgi.py"
    wsgi.write_text(body, encoding="utf-8")
    return wsgi


@pytest.mark.unit
def test_legge_apici_singoli_e_doppi(tmp_path):
    """Il file WSGI reale mescola i due stili di quoting."""
    wsgi = _write(
        tmp_path,
        "import os\n"
        "os.environ['FLASK_ENV'] = 'production'\n"
        'os.environ["ENCRYPTION_KEY"] = "chiave-segreta"\n',
    )

    env = auto_deploy.read_wsgi_env(wsgi)

    assert env == {"FLASK_ENV": "production", "ENCRYPTION_KEY": "chiave-segreta"}


@pytest.mark.unit
def test_ignora_valori_non_costanti(tmp_path):
    """Un valore calcolato non e' estraibile senza eseguire il file: si salta."""
    wsgi = _write(
        tmp_path,
        "import os\n"
        "os.environ['CALCOLATA'] = os.path.join('a', 'b')\n"
        "os.environ['COSTANTE'] = 'ok'\n",
    )

    assert auto_deploy.read_wsgi_env(wsgi) == {"COSTANTE": "ok"}


@pytest.mark.unit
def test_ignora_subscript_che_non_sono_environ(tmp_path):
    """Solo `os.environ[...]`: altri dizionari non sono variabili d'ambiente."""
    wsgi = _write(
        tmp_path,
        "import os\n"
        "config = {}\n"
        "config['ENCRYPTION_KEY'] = 'non-e-una-env'\n"
        "os.environ['VERA'] = 'si'\n",
    )

    assert auto_deploy.read_wsgi_env(wsgi) == {"VERA": "si"}


@pytest.mark.unit
def test_file_mancante_o_illeggibile_non_solleva(tmp_path):
    """Fuori da PythonAnywhere il file non esiste: deve degradare, non esplodere."""
    assert auto_deploy.read_wsgi_env(tmp_path / "inesistente.py") == {}


@pytest.mark.unit
def test_file_non_parsabile_non_solleva(tmp_path):
    """Un WSGI malformato non deve far crashare il deploy nel parser."""
    wsgi = _write(tmp_path, "questo non e' python valido (((\n")

    assert auto_deploy.read_wsgi_env(wsgi) == {}


@pytest.mark.unit
def test_wsgi_file_derivato_dal_dominio():
    """Il path deve coincidere con quello reale su PythonAnywhere.

    Prima era hardcoded in due punti; ora si deriva da PA_DOMAIN. Se il
    dominio cambia, il path deve seguirlo da solo.
    """
    assert auto_deploy.PA_DOMAIN == "www.torneibiliardo.it"
    assert str(auto_deploy.WSGI_FILE) == "/var/www/www_torneibiliardo_it_wsgi.py"


@pytest.mark.unit
def test_load_applica_le_variabili(tmp_path, monkeypatch):
    wsgi = _write(tmp_path, "import os\nos.environ['DA_WSGI'] = 'valore'\n")
    monkeypatch.setattr(auto_deploy, "WSGI_FILE", wsgi)
    monkeypatch.delenv("DA_WSGI", raising=False)

    letti = auto_deploy.load_wsgi_env()

    assert letti == {"DA_WSGI": "valore"}
    assert auto_deploy.os.environ["DA_WSGI"] == "valore"


@pytest.mark.unit
def test_load_non_sovrascrive_env_gia_presenti(tmp_path, monkeypatch):
    """Chi lancia a mano con `VAR=... python auto_deploy.py` deve vincere."""
    wsgi = _write(tmp_path, "import os\nos.environ['DA_WSGI'] = 'dal-file'\n")
    monkeypatch.setattr(auto_deploy, "WSGI_FILE", wsgi)
    monkeypatch.setenv("DA_WSGI", "forzata-a-mano")

    auto_deploy.load_wsgi_env()

    assert auto_deploy.os.environ["DA_WSGI"] == "forzata-a-mano"
