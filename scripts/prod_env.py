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
import sys
from typing import Iterable, List, Tuple

try:  # importato come package (test: ``import scripts.prod_env``)
    from scripts.auto_deploy import WSGI_FILE, read_wsgi_env
except ModuleNotFoundError:  # eseguito come script: ``scripts/`` è su sys.path
    # Volutamente NON ``ImportError``: quello catturerebbe anche un import
    # fallito *dentro* auto_deploy (dipendenza mancante, refuso su un nome),
    # ritentando da un percorso diverso e mascherando l'errore vero.
    from auto_deploy import WSGI_FILE, read_wsgi_env


#: Variabili senza le quali ``create_app("production")`` non arriva in fondo.
#:
#: ``ADMIN_PASSWORD`` non serve a Flask ma a ``create_admin_if_not_exists()``,
#: che ``create_app`` invoca all'avvio: in ``ProductionConfig`` non ha fallback
#: (``os.environ.get("ADMIN_PASSWORD") or None``), quindi senza di essa lo
#: script muore comunque — solo più tardi e con un errore che non dice da dove
#: dovrebbe arrivare la variabile. ``ADMIN_USERNAME`` invece un default ce l'ha
#: (``"admin"``, in ``config.py``) e non va richiesta.
PRODUCTION_REQUIRED: Tuple[str, ...] = ("SECRET_KEY", "ADMIN_PASSWORD")


def targets_production() -> bool:
    """Vero se l'app verrà avviata in configurazione di produzione.

    Da valutare **dopo** ``load_production_env``: ``FLASK_ENV`` è essa stessa
    una delle variabili che arrivano dal file WSGI, quindi prima del
    caricamento la risposta sarebbe basata su un ambiente incompleto. Il
    default è ``production`` perché è quello che usano gli script chiamanti.
    """
    return os.environ.get("FLASK_ENV", "production") == "production"


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


def bootstrap_or_exit(required: Iterable[str] = PRODUCTION_REQUIRED) -> None:
    """Carica le env di produzione o esce con un messaggio utile.

    Pensata per gli script lanciati da console o scheduled task: senza questo,
    l'errore che l'utente vede è un traceback su ``SECRET_KEY`` che non spiega
    né da dove dovrebbe arrivare né come rimediare.

    Il controllo sui ``required`` vale **solo** se l'ambiente risolve a
    produzione: le altre configurazioni hanno dei default per queste variabili,
    e fermare uno script lanciato con ``FLASK_ENV=development`` sarebbe un
    falso negativo. Le variabili vengono comunque caricate dal file WSGI in
    ogni caso, così un valore passato a mano resta prioritario ovunque.
    """
    loaded, missing = load_production_env(required)
    if loaded:
        # Diagnostica su stderr: stdout resta pulito per gli script il cui
        # output può essere letto o messo in pipe (il riepilogo dei job).
        print(
            f"Env di produzione lette da {WSGI_FILE}: {', '.join(loaded)}",
            file=sys.stderr,
        )

    if missing and targets_production():
        raise SystemExit(
            f"Variabili mancanti: {', '.join(missing)}.\n"
            f"Di norma arrivano da {WSGI_FILE}; se il file non esiste o non è "
            f"leggibile, passale a mano:\n"
            f"    {' '.join(f'{n}=...' for n in missing)} python <script>"
        )


def bootstrap_and_create_app(
    config_name: str | None = None,
    required: Iterable[str] = PRODUCTION_REQUIRED,
):
    """Carica le env di produzione e **poi** costruisce l'app.

    L'ordine è tutta la sostanza di questa funzione, ed è il motivo per cui
    esiste invece di lasciare due righe a ogni script.

    ``from app import create_app`` scritto in cima a un file tira dentro
    ``config``, ``utils.encryption`` e mezzo dominio *prima* che
    ``bootstrap_or_exit()`` abbia messo qualcosa in ``os.environ``. Chi legge
    l'ambiente durante l'import si porta a casa un ambiente vuoto, e non lo
    rilegge mai più. Sono usciti due guasti da lì:

    * ``config.py`` congelava ``SECRET_KEY`` a stringa vuota →
      ``RuntimeError: SECRET_KEY env var must be set in production`` a ogni
      esecuzione di ``daily_jobs.py`` (giornaliero) e
      ``send_match_reminders.py`` (orario), con nel log la riga che dichiara
      di aver letto proprio ``SECRET_KEY``: le due righe raccontano momenti
      diversi;
    * ``utils.encryption`` derivava il cipher dalla chiave di sviluppo → PII
      decifrati a stringa vuota, senza errori da nessuna parte.

    Entrambi i moduli sono stati resi indifferenti all'ordine (``config`` legge
    l'ambiente in ``environment_settings()``, il cipher si deriva al primo
    uso), quindi questa funzione non è più l'unica difesa: è però il modo per
    non dover riscoprire la cosa a ogni script nuovo. Uno script che vuole
    l'app in produzione chiama questa, e non importa ``app`` a livello di
    modulo — invariante verificata da
    ``tests/new/unit/test_script_import_order.py``.

    Args:
        config_name: nome della configurazione; per default quella indicata da
            ``FLASK_ENV`` **dopo** il caricamento (il file WSGI la contiene).
        required: variabili senza le quali fermarsi. Uno script che tocca i
            PII passa ``PRODUCTION_REQUIRED + ("ENCRYPTION_KEY",)``.
    """
    bootstrap_or_exit(required)

    # Import ritardato di proposito: vedi docstring.
    from app import create_app

    # `da_script`: l'app non riporta il log a WARNING, come fa per il server
    # web — lo script lo ha alzato a INFO per il proprio resoconto.
    return create_app(
        config_name or os.environ.get("FLASK_ENV", "production"), da_script=True
    )
