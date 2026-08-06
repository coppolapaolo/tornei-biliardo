"""Variabili d'ambiente di produzione per gli script da console/scheduled task.

Su PythonAnywhere le env di produzione (``SECRET_KEY``, ``ENCRYPTION_KEY``,
credenziali mail...) vivono nel **file WSGI**, che viene eseguito solo dalla web
app. Console e scheduled task sono processi separati e **non le ereditano**:
senza di esse ``create_app("production")`` solleva subito
``RuntimeError: SECRET_KEY env var must be set in production``, e i percorsi che
toccano i PII degraderebbero sulla chiave di sviluppo (incidente 2026-06-25).

``auto_deploy.py`` risolveva già il problema per sé, leggendo il file WSGI via
AST. Qui quella logica viene riusata — non ricopiata — e resa disponibile agli
altri script. La dipendenza va in questa direzione (``prod_env`` →
``auto_deploy``) di proposito: ``auto_deploy`` è il punto d'ingresso del deploy
e deve restare autonomo, senza import verso il resto del progetto.
"""

from __future__ import annotations

import os
from typing import Iterable, List, Tuple

try:  # importato come package (test: ``import scripts.prod_env``)
    from scripts.auto_deploy import WSGI_FILE, read_wsgi_env
except ImportError:  # eseguito come script: ``scripts/`` è già sys.path[0]
    from auto_deploy import WSGI_FILE, read_wsgi_env


def load_production_env(required: Iterable[str] = ()) -> Tuple[List[str], List[str]]:
    """Popola ``os.environ`` con le env lette dal file WSGI.

    Le variabili già presenti nell'ambiente **non** vengono sovrascritte: un
    valore passato a mano sulla riga di comando resta prioritario.

    Args:
        required: nomi che devono risultare valorizzati dopo il caricamento.

    Returns:
        ``(caricate, mancanti)`` — i nomi presi dal file WSGI e quelli fra i
        ``required`` che restano vuoti. Sta al chiamante decidere se fermarsi.
    """
    loaded: List[str] = []
    for name, value in read_wsgi_env(WSGI_FILE).items():
        if not os.environ.get(name):
            os.environ[name] = value
            loaded.append(name)

    missing = [name for name in required if not os.environ.get(name)]
    return sorted(loaded), missing


def bootstrap_or_exit(required: Iterable[str] = ("SECRET_KEY",)) -> None:
    """Carica le env di produzione o esce con un messaggio utile.

    Pensata per gli script lanciati da console o scheduled task: senza questo,
    l'errore che l'utente vede è un traceback su ``SECRET_KEY`` che non spiega
    né da dove dovrebbe arrivare né come rimediare.
    """
    loaded, missing = load_production_env(required)
    if loaded:
        print(f"Env di produzione lette da {WSGI_FILE}: {', '.join(loaded)}")

    if missing:
        raise SystemExit(
            f"Variabili mancanti: {', '.join(missing)}.\n"
            f"Di norma arrivano da {WSGI_FILE}; se il file non esiste o non è "
            f"leggibile, passale a mano:\n"
            f"    {' '.join(f'{n}=...' for n in missing)} python <script>"
        )
