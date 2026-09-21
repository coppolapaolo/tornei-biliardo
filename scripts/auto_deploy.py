#!/usr/bin/env python3
"""Auto-deploy script for PythonAnywhere scheduled task.

This script:
0. Legge le env di produzione dal file WSGI
1. Pulls latest code from GitHub
2. Runs pending database migrations — SOLO con la web app disabilitata
3. Reloads the web app

Il task gira in un processo separato che il file WSGI non esegue mai, quindi
NON eredita le sue variabili d'ambiente (ENCRYPTION_KEY, FLASK_ENV, ...): le
legge da li' e le applica, cosi' il runner delle migrations — che e' un
subprocess e eredita os.environ — vede la stessa configurazione della web app.
Il file WSGI resta la fonte unica: nessuna chiave duplicata, nessun rischio
che le due divergano.

Senza ENCRYPTION_KEY una migration sui PII non fallisce, il che e' peggio:
`decrypt_data` non decifra, il guard salta la riga e il backfill resta vuoto
mentre la migration viene marcata come applicata (incidente 2026-06-25,
`20260625_add_email_hash`: 0 hash su 37 utenti). Per questo, se ci sono
migrations pendenti e la chiave non e' disponibile, il deploy si ferma.

Le migrations scrivono sul DB SQLite mentre la web app scrive anche lei:
su PythonAnywhere (storage NFS, lock inaffidabili) due writer concorrenti
possono corrompere il file (incidente 2026-06-10). Quindi: se ci sono
migrations pendenti, lo script disabilita la web app via API, le esegue e
la riabilita. Senza token API NON esegue le migrations e esce con errore.

Il token API e' letto da $API_TOKEN, che PythonAnywhere imposta
automaticamente nei task e nelle console quando un token esiste
(Account -> API Token -> Create).

Setup on PythonAnywhere:
1. Go to Tasks tab
2. Add a new scheduled task (e.g., every hour)
3. Command:
   cd /home/paolocoppola/mysite && venv/bin/python scripts/auto_deploy.py

Or run manually via Bash console:
    cd /home/paolocoppola/mysite && venv/bin/python scripts/auto_deploy.py

Il `venv/bin/python` **non e' pignoleria**: fino al 2026-08-17 qui c'era
scritto `python scripts/auto_deploy.py`, e un `python` nudo su PythonAnywhere
e' l'interprete di sistema. Lo script installava allora le dipendenze con
`sys.executable -m pip`, cioe' con un interprete che nel virtualenv della web
app non puo' scrivere: `pip install` senza `--user` non ha i permessi per i
site-packages di sistema, quindi falliva — e il fallimento era **un WARNING**,
dopo il quale il deploy proseguiva fino al reload.

Il difetto e' rimasto invisibile da febbraio ad agosto perche' in quei sei mesi
non e' stata aggiunta nessuna dipendenza nuova: ogni installazione era un
no-op, e un no-op fallito non si distingue da uno riuscito. Quando PyYAML e'
arrivato, `/aiuto` ha risposto 500 per due giorni
(`ModuleNotFoundError: No module named 'yaml'`) sopravvivendo a due deploy
consecutivi. Verificato dopo il fatto: il pacchetto non era ne' in `venv/` ne'
in `~/.local` — non era stato installato affatto.

Stessa causa, altro sintomo: gli scheduled task che *importano l'app* col
python di sistema si portano dietro i pacchetti di sistema di PythonAnywhere,
fra cui un `pyOpenSSL` incompatibile con la `cryptography` del progetto (vedi
`auto_enabling_integrations` in `app.py`). Anche `daily_jobs.py` e
`send_match_reminders.py` vanno quindi lanciati con `venv/bin/python`.
"""

import ast
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

# Configuration
PROJECT_DIR = Path(__file__).parent.parent
REMOTE = "origin"
BRANCH = "main"
PA_USERNAME = "paolocoppola"
PA_DOMAIN = "www.torneibiliardo.it"  # domain_name della webapp (vedi WSGI file)

# Il file WSGI e' la fonte unica delle env di produzione (ENCRYPTION_KEY,
# FLASK_ENV, credenziali mail...). Questo script NON le eredita: gira in un
# processo separato che il file WSGI non esegue mai.
WSGI_FILE = Path("/var/www") / f"{PA_DOMAIN.replace('.', '_')}_wsgi.py"


def log(msg: str = "") -> None:
    """Stampa con l'orario UTC davanti a ogni riga.

    Senza orari il log del task non diceva quanto dura ogni passo: nelle notti
    con migration i worker risultano fermati da uno a quattro secondi dopo la
    fine del task, segno che il `disable` dell'API e' asincrono, ma senza un
    orario per riga il ritardo non si misura. UTC come i log di
    PythonAnywhere, cosi' le righe si incrociano senza conti.

    Niente `utc_now()` da `models.base`: questo script non importa l'app, e non
    deve — le env di produzione si leggono solo dopo, e le dipendenze che l'app
    importa sono proprio quelle che lo script deve ancora controllare.
    """
    orario = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    for riga in msg.splitlines() or [""]:
        print(f"{orario}  {riga}" if riga else "", flush=True)


def venv_python() -> str:
    """L'interprete del virtualenv del progetto, non quello che ci esegue.

    Sono due cose diverse ogni volta che il task e' configurato con un `python`
    nudo, ed e' la differenza fra installare una dipendenza dove la web app la
    cerca e installarla dove non guardera' mai nessuno: `sys.executable` e' chi
    esegue *questo script*, mentre la web app importa da `venv/`.

    Ripiega su `sys.executable` se il virtualenv non c'e' — e lo dice, perche'
    in produzione quel ripiego e' esattamente la condizione che ha rotto
    `/aiuto`. In sviluppo, dove spesso si lancia lo script gia' dentro un venv
    con un altro nome, e' invece il comportamento giusto.
    """
    candidato = PROJECT_DIR / "venv" / "bin" / "python"
    if candidato.exists():
        return str(candidato)
    log(
        f"WARNING: nessun interprete in {candidato}. Uso {sys.executable}: "
        "se questa e' la produzione, pip installera' fuori dal virtualenv "
        "della web app e le dipendenze nuove non arriveranno mai."
    )
    return sys.executable


def run_command(cmd: list, cwd: Path = None) -> tuple:
    """Run command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd or PROJECT_DIR, capture_output=True, text=True, timeout=60
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def git_pull() -> tuple:
    """Pull latest code from remote."""
    log(f"Pulling from {REMOTE}/{BRANCH}...")

    # Fetch first
    success, output = run_command(["git", "fetch", REMOTE])
    if not success:
        return False, f"Fetch failed: {output}"

    # Check if there are changes
    _, local = run_command(["git", "rev-parse", "HEAD"])
    _, remote = run_command(["git", "rev-parse", f"{REMOTE}/{BRANCH}"])

    if local == remote:
        return True, "Already up to date"

    # Pull changes
    success, output = run_command(["git", "pull", REMOTE, BRANCH])
    return success, output


def deps_in_sync() -> bool:
    """I pacchetti di requirements.txt sono tutti nel venv, alla versione giusta?

    Risponde `scripts/requirements_check.py`, lanciato con l'interprete del
    venv perche' i pacchetti che contano sono quelli da cui importa la web app.
    Fino al 2026-09-14 qui c'era `pip install --dry-run -q` con la ricerca di
    «Would install» nell'output, e ha sbagliato nei due sensi: pip 22 non
    conosceva l'opzione, il comando falliva e ogni notte si reinstallava e
    ricaricava tutto; pip 26 la conosce, ma `-q` zittisce proprio quella frase,
    quindi un pacchetto mancante risultava installato.

    Se il controllo non riesce a rispondere la risposta e' «fuori sync»: una
    reinstallazione in piu' costa un reload, una dipendenza mai installata
    costa la web app in 500. Il motivo si stampa sempre.
    """
    requirements = PROJECT_DIR / "requirements.txt"
    if not requirements.exists():
        return True

    checker = PROJECT_DIR / "scripts" / "requirements_check.py"
    success, output = run_command([venv_python(), str(checker), str(requirements)])
    if success:
        return True
    log(
        "Dipendenze da installare nel venv:\n"
        + (output or "controllo non riuscito senza messaggio: installo per prudenza")
    )
    return False


def install_dependencies() -> tuple:
    """Install/update Python dependencies."""
    log("Installing dependencies...")

    requirements = PROJECT_DIR / "requirements.txt"
    if not requirements.exists():
        return True, "No requirements.txt found"

    success, output = run_command(
        [venv_python(), "-m", "pip", "install", "-q", "-r", str(requirements)],
    )
    return success, output


def read_wsgi_env(wsgi_path: Path) -> Dict[str, str]:
    """Estrae gli `os.environ[...] = "..."` dal file WSGI senza eseguirlo.

    Parsing via AST invece che regex o exec: il file WSGI importa l'app Flask,
    quindi eseguirlo qui avvierebbe una seconda istanza applicativa; una regex
    invece si romperebbe sul quoting o sull'indentazione. L'AST legge solo le
    assegnazioni con valore costante e ignora tutto il resto.

    Ritorna {} se il file manca, non e' leggibile o non e' parsabile: sta a chi
    chiama decidere se in quel contesto sia un errore fatale.
    """
    try:
        tree = ast.parse(wsgi_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return {}

    env: Dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            # Serve `os.environ[...]` per intero: fermarsi a `.attr ==
            # "environ"` accetterebbe qualunque oggetto con quell'attributo
            # (es. una libreria WSGI che espone un proprio `environ`) e ne
            # applicherebbe le chiavi come variabili d'ambiente reali.
            if not (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Attribute)
                and target.value.attr == "environ"
                and isinstance(target.value.value, ast.Name)
                and target.value.value.id == "os"
            ):
                continue
            key_node = target.slice
            if isinstance(key_node, ast.Index):  # Python < 3.9
                key_node = key_node.value  # type: ignore[attr-defined]
            try:
                name = ast.literal_eval(key_node)
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                continue  # valore non costante (es. os.path.join(...)): ignora
            if isinstance(name, str) and isinstance(value, str):
                env[name] = value
    return env


def load_wsgi_env() -> Dict[str, str]:
    """Porta le env del WSGI nel processo corrente e nei suoi subprocess.

    Il runner delle migrations e' un subprocess e eredita `os.environ`, quindi
    questo passo e' sufficiente perche' veda la stessa configurazione della web
    app. `setdefault` e non assegnazione diretta: una variabile gia' presente
    nell'ambiente vince, cosi' resta possibile forzarne una da riga di comando
    per un singolo run.

    Ritorna le variabili LETTE dal WSGI (non quelle effettivamente applicate).
    """
    env = read_wsgi_env(WSGI_FILE)
    for name, value in env.items():
        os.environ.setdefault(name, value)
    return env


def run_migrations() -> tuple:
    """Run pending database migrations."""
    log("Running migrations...")

    migrations_runner = PROJECT_DIR / "migrations" / "runner.py"
    if not migrations_runner.exists():
        return True, "No migrations runner found, skipping"

    success, output = run_command([venv_python(), str(migrations_runner)])
    return success, output


def parse_pending(status_output: str) -> Optional[int]:
    """Estrae il numero di migrations pendenti dall'output di --status.

    Ritorna None se l'output non e' riconoscibile (chi chiama deve assumere
    prudenzialmente che CI SIANO migrations pendenti).
    """
    match = re.search(r"Pending:\s*(\d+)", status_output)
    return int(match.group(1)) if match else None


def count_pending_migrations() -> Optional[int]:
    """Numero di migrations pendenti, o None se non determinabile."""
    migrations_runner = PROJECT_DIR / "migrations" / "runner.py"
    if not migrations_runner.exists():
        return 0
    # Se il DB non esiste, niente migrations (come run_pending_migrations):
    # invocare --status connetterebbe a sqlite creando un file vuoto.
    db_path = Path(os.environ.get("DATABASE_PATH", "instance/billiard_campionato.db"))
    if not db_path.is_absolute():
        db_path = PROJECT_DIR / db_path
    if not db_path.exists():
        return 0
    success, output = run_command([venv_python(), str(migrations_runner), "--status"])
    if not success:
        return None
    return parse_pending(output)


def webapp_api(action: str) -> tuple:
    """POST all'API PythonAnywhere per la webapp: disable / enable / reload."""
    token = os.environ.get("API_TOKEN") or os.environ.get("PYTHONANYWHERE_API_TOKEN")
    if not token:
        return False, (
            f"{action}: token API non disponibile "
            "($API_TOKEN o $PYTHONANYWHERE_API_TOKEN)"
        )

    url = (
        f"https://www.pythonanywhere.com/api/v0/user/{PA_USERNAME}"
        f"/webapps/{PA_DOMAIN}/{action}/"
    )
    request = urllib.request.Request(
        url, method="POST", headers={"Authorization": f"Token {token}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            ok = 200 <= response.status < 300
            return ok, f"{action}: HTTP {response.status}"
    except Exception as e:
        return False, f"{action}: {e}"


def run_migrations_safely() -> tuple:
    """Esegue le migrations con la web app disabilitata.

    Disable -> migrations -> Enable (sempre, anche su errore). Se il disable
    fallisce (es. token mancante) le migrations NON vengono eseguite: meglio
    un deploy fermo che un DB corrotto da writer concorrenti.
    """
    ok, msg = webapp_api("disable")
    log(f"Disable web app: {msg}")
    if not ok:
        return False, (
            "web app NON disabilitata: migrations NON eseguite per evitare "
            "scritture concorrenti su SQLite. Procedura manuale: tab Web -> "
            "Disable, `python migrations/runner.py`, tab Web -> Enable + Reload."
        )
    try:
        success, output = run_migrations()
    finally:
        # L'enable gira anche se run_migrations solleva un'eccezione.
        ok_enable, msg_enable = webapp_api("enable")
        log(f"Enable web app: {msg_enable}")
    if not ok_enable:
        return False, (
            f"web app NON riabilitata dopo le migrations ({msg_enable}): "
            "riabilitala subito dal tab Web (Enable)!"
        )
    return success, output


def reload_webapp() -> tuple:
    """Reload the PythonAnywhere web app via touch."""
    log("Reloading web app...")

    # On PythonAnywhere, touching the WSGI file reloads the app
    wsgi_file = WSGI_FILE

    if wsgi_file.exists():
        try:
            wsgi_file.touch()
            return True, "Web app reloaded"
        except Exception as e:
            return False, f"Could not touch WSGI file: {e}"
    else:
        return True, "WSGI file not found (may not be on PythonAnywhere)"


def main():
    log("=" * 60)
    log("Auto-Deploy Script")
    log("=" * 60)
    log(f"Project: {PROJECT_DIR}")
    log()

    # Step 0: env di produzione dal file WSGI. Va fatto PRIMA di qualunque
    # invocazione del runner delle migrations (anche `--status`, che importa i
    # modelli): senza, il processo ripiega sui default di sviluppo.
    wsgi_env = load_wsgi_env()
    if wsgi_env:
        # Solo i NOMI: i valori sono segreti (SECRET_KEY, MAIL_PASSWORD, ...).
        log(f"Env dal WSGI: {', '.join(sorted(wsgi_env))}")
    else:
        log(f"Env dal WSGI: nessuna letta da {WSGI_FILE}")

    # Con FLASK_ENV=production e senza chiave, il primo import dei modelli
    # solleverebbe (fail-fast in utils/encryption.py): meglio dirlo qui che
    # lasciare uno stack trace a meta' deploy.
    if os.environ.get("FLASK_ENV") == "production" and not os.environ.get(
        "ENCRYPTION_KEY"
    ):
        log(
            "ERROR: FLASK_ENV=production ma ENCRYPTION_KEY non disponibile. "
            "Ogni import dei modelli fallirebbe. Deploy interrotto."
        )
        sys.exit(1)

    log()

    # Step 1: Git pull
    success, output = git_pull()
    log(f"Git pull: {output}")
    if not success:
        log("ERROR: Git pull failed, aborting")
        sys.exit(1)

    has_new_code = "Already up to date" not in output

    if not has_new_code:
        # No new commits, but check if deps are out of sync
        # (e.g. manual git pull without pip install)
        #
        # E soprattutto: una migration puo' essere pendente anche senza codice
        # nuovo, perche' il codice e' arrivato ieri e la migration e' fallita.
        # Uscire qui la lasciava pendente per sempre: il retry non arriva col
        # giro successivo, ma col prossimo merge che porta codice — e fino ad
        # allora l'app gira su uno schema che non ha le colonne che i modelli
        # dichiarano. E' successo il 2026-09-20 (due migration fuori ordine,
        # vedi `migrations/runner.py`): le pagine delle schede di allenamento
        # rispondevano 500 e nessun giro dello scheduled task le avrebbe
        # rimesse in piedi.
        pendenti = count_pending_migrations()
        if deps_in_sync() and pendenti == 0:
            log()
            log("No changes to deploy.")
            return
        log()
        if pendenti != 0:
            log(
                f"No new commits, ma {pendenti if pendenti else 'forse'} "
                "migration risultano pendenti: proseguo."
            )
        else:
            log("No new commits, but dependencies are out of sync.")

    log()

    # Step 2: Install dependencies
    success, output = install_dependencies()
    log(f"Dependencies: {output}")
    if not success:
        # Prima era un WARNING e il deploy proseguiva: la web app ripartiva
        # con il codice nuovo e le dipendenze vecchie, e l'unica traccia era
        # una riga nel log di un task che nessuno legge. Un'app ricaricata
        # senza cio' che importa e' peggio di un'app ferma su codice vecchio:
        # la seconda continua a funzionare, la prima risponde 500 su tutto
        # quello che tocca il pacchetto mancante.
        log(
            "ERROR: installazione delle dipendenze fallita. Deploy interrotto "
            "senza reload: la web app resta sul codice precedente, che con le "
            "dipendenze attuali funziona.\n"
            f"       Riprova a mano: {venv_python()} -m pip install -r "
            f"{PROJECT_DIR / 'requirements.txt'}"
        )
        sys.exit(1)

    log()

    # Step 3: Run migrations — solo se pendenti, e MAI con la web app accesa
    pending = count_pending_migrations()
    if pending == 0:
        log("Migrations: nessuna pendente, step saltato")
    else:
        if pending is None:
            log("WARNING: stato migrations non determinabile, assumo pendenti")
        # Una migration che tocca PII (decrypt/compute_email_hash) con la
        # chiave di sviluppo NON solleva: la decifratura fallisce, il guard
        # salta la riga e il backfill resta vuoto lasciando la migration
        # marcata come applicata. E' successo il 2026-06-25 con
        # 20260625_add_email_hash: 0 hash su 37 utenti, recupero password muto
        # per cinque settimane. Meglio un deploy fermo di un guasto invisibile.
        if not os.environ.get("ENCRYPTION_KEY"):
            log(
                "ERROR: migrations pendenti ma ENCRYPTION_KEY non disponibile "
                f"(non letta da {WSGI_FILE}). Una migration sui PII fallirebbe "
                "in silenzio. Deploy interrotto. Procedura manuale: tab Web -> "
                "Disable, `ENCRYPTION_KEY='...' python migrations/runner.py`, "
                "tab Web -> Enable."
            )
            sys.exit(1)
        success, output = run_migrations_safely()
        log(f"Migrations: {output}")
        if not success:
            log("ERROR: migrations non eseguite/fallite, deploy interrotto")
            sys.exit(1)

    log()

    # Step 4: Reload web app
    success, output = reload_webapp()
    log(f"Reload: {output}")

    log()
    log("=" * 60)
    log("Deploy complete!")
    log("=" * 60)


if __name__ == "__main__":
    main()
