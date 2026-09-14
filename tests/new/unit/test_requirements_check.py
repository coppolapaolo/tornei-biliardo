"""`requirements_check`: le dipendenze del venv si confrontano senza chiedere a pip.

Fino al 2026-09-14 `auto_deploy.deps_in_sync` lanciava `pip install --dry-run
-q` e cercava nell'output la frase «Would install». Ha sbagliato in due modi
opposti, secondo la versione di pip:

* **pip 22** (produzione fino al 14/09) non conosce `--dry-run`: il comando
  usciva con 2, e l'errore veniva letto come «manca qualcosa». Ogni notte
  `pip install` e reload, anche senza un commit nuovo;
* **pip 26** conosce `--dry-run`, ma «Would install» passa da `logger.info` e
  `-q` la zittisce: uscita 0, nessun testo, quindi «tutto installato» anche con
  un pacchetto mancante. La prima PR con una dipendenza nuova sarebbe arrivata
  in produzione senza che nessuno la installasse.

Il controllo ora legge i metadati dei pacchetti installati e li confronta con
`requirements.txt` usando `packaging`, cioè la stessa grammatica di pip, senza
dipendere da cosa pip stampa.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.requirements_check import missing_requirements

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "requirements_check.py"

#: Ambiente dei marker fissato: il test non deve dipendere dal Python che lo esegue.
AMBIENTE = {"python_version": "3.10", "sys_platform": "linux"}


def _manca(righe: str, installati: dict) -> list:
    return missing_requirements(righe.splitlines(), installati, AMBIENTE)


@pytest.mark.unit
def test_tutto_soddisfatto_e_in_sync():
    assert (
        _manca(
            "Flask==2.3.3\nPyYAML>=6.0,<7.0\n", {"flask": "2.3.3", "pyyaml": "6.0.1"}
        )
        == []
    )


@pytest.mark.unit
def test_pacchetto_mancante():
    mancanti = _manca("Flask==2.3.3\nPyYAML>=6.0,<7.0\n", {"flask": "2.3.3"})
    assert len(mancanti) == 1
    assert "PyYAML" in mancanti[0]


@pytest.mark.unit
def test_versione_fuori_specifica():
    mancanti = _manca("cryptography>=42.0.0,<44.0.0", {"cryptography": "41.0.7"})
    assert len(mancanti) == 1
    assert "41.0.7" in mancanti[0]


@pytest.mark.unit
@pytest.mark.parametrize(
    "riga,installato",
    [
        ("Flask_SQLAlchemy==3.0.5", {"flask-sqlalchemy": "3.0.5"}),
        ("flask-sqlalchemy==3.0.5", {"Flask_SQLAlchemy": "3.0.5"}),
        ("Flask.SQLAlchemy==3.0.5", {"flask_sqlalchemy": "3.0.5"}),
    ],
)
def test_nomi_normalizzati(riga, installato):
    """`Flask_SQLAlchemy` e `flask-sqlalchemy` sono lo stesso pacchetto (PEP 503)."""
    assert _manca(riga, installato) == []


@pytest.mark.unit
def test_extras_controllano_il_pacchetto_base():
    assert _manca("sentry-sdk[flask]>=1.40.0,<3.0.0", {"sentry-sdk": "2.1.0"}) == []


@pytest.mark.unit
def test_marker_non_applicabile_ignorato():
    righe = 'backports.zoneinfo==0.2.1; python_version < "3.9"\nFlask==2.3.3'
    assert _manca(righe, {"flask": "2.3.3"}) == []


@pytest.mark.unit
def test_marker_applicabile_controllato():
    righe = 'tomli==2.0.1; python_version < "3.11"'
    assert len(_manca(righe, {})) == 1


@pytest.mark.unit
def test_commenti_righe_vuote_e_opzioni_non_esplodono():
    righe = """
# commento
--index-url https://pypi.org/simple
-e git+https://example.org/repo.git#egg=locale
-r altro.txt
--requirement altro.txt
Flask==2.3.3  # commento in coda
networkx==3.1 --hash=sha256:abc
"""
    assert _manca(righe, {"flask": "2.3.3", "networkx": "3.1"}) == []


@pytest.mark.unit
def test_riferimento_diretto_controlla_solo_la_presenza():
    riga = "mylib @ https://example.org/mylib-1.0.tar.gz"
    assert _manca(riga, {"mylib": "0.0.1"}) == []
    assert len(_manca(riga, {})) == 1


@pytest.mark.unit
def test_riga_non_interpretabile_e_fuori_sync():
    """Prudenza: una riga che non si capisce non si dà per installata."""
    mancanti = _manca("Flask 2.3.3", {"flask": "2.3.3"})
    assert len(mancanti) == 1
    assert "Flask 2.3.3" in mancanti[0]


@pytest.mark.unit
def test_prerelease_installata_soddisfa_la_specifica():
    """Una prerelease installata non va reinstallata ogni notte."""
    assert _manca("Flask>=2.0", {"flask": "3.0.0rc1"}) == []


def _lancia(tmp_path: Path, contenuto: str) -> subprocess.CompletedProcess:
    requisiti = tmp_path / "requirements.txt"
    requisiti.write_text(contenuto, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(requisiti)],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.unit
def test_eseguibile_in_sync(tmp_path):
    """Lo script gira come sottoprocesso: e' cosi' che guarda il venv giusto."""
    risultato = _lancia(tmp_path, "pytest\n")
    assert risultato.returncode == 0, risultato.stdout + risultato.stderr


@pytest.mark.unit
def test_eseguibile_segue_i_file_inclusi(tmp_path):
    (tmp_path / "base.txt").write_text(
        "pacchetto-che-non-esiste-xyz==1.0\n", encoding="utf-8"
    )
    risultato = _lancia(tmp_path, "-r base.txt\npytest\n")
    assert risultato.returncode == 1
    assert "pacchetto-che-non-esiste-xyz" in risultato.stdout


@pytest.mark.unit
def test_eseguibile_pacchetto_mancante(tmp_path):
    risultato = _lancia(tmp_path, "pytest\npacchetto-che-non-esiste-xyz==1.0\n")
    assert risultato.returncode == 1
    assert "pacchetto-che-non-esiste-xyz" in risultato.stdout


@pytest.mark.unit
def test_eseguibile_file_assente(tmp_path):
    risultato = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "nessuno.txt")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert risultato.returncode == 2
    assert risultato.stdout.strip()
