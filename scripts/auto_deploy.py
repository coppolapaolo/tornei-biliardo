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
3. Command: cd /home/paolocoppola/mysite && python scripts/auto_deploy.py

Or run manually via Bash console:
    cd /home/paolocoppola/mysite && python scripts/auto_deploy.py
"""

import ast
import os
import re
import subprocess
import sys
import urllib.request
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
    print(f"Pulling from {REMOTE}/{BRANCH}...")

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
    """Check if all requirements.txt packages are installed."""
    requirements = PROJECT_DIR / "requirements.txt"
    if not requirements.exists():
        return True

    success, output = run_command(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--dry-run",
            "-q",
            "-r",
            str(requirements),
        ],
    )
    # pip --dry-run outputs "Would install ..." if something is missing
    return success and "Would install" not in output


def install_dependencies() -> tuple:
    """Install/update Python dependencies."""
    print("Installing dependencies...")

    requirements = PROJECT_DIR / "requirements.txt"
    if not requirements.exists():
        return True, "No requirements.txt found"

    success, output = run_command(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(requirements)],
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
    print("Running migrations...")

    migrations_runner = PROJECT_DIR / "migrations" / "runner.py"
    if not migrations_runner.exists():
        return True, "No migrations runner found, skipping"

    success, output = run_command([sys.executable, str(migrations_runner)])
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
    success, output = run_command([sys.executable, str(migrations_runner), "--status"])
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
    print(f"Disable web app: {msg}")
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
        print(f"Enable web app: {msg_enable}")
    if not ok_enable:
        return False, (
            f"web app NON riabilitata dopo le migrations ({msg_enable}): "
            "riabilitala subito dal tab Web (Enable)!"
        )
    return success, output


def reload_webapp() -> tuple:
    """Reload the PythonAnywhere web app via touch."""
    print("Reloading web app...")

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
    print("=" * 60)
    print("Auto-Deploy Script")
    print("=" * 60)
    print(f"Project: {PROJECT_DIR}")
    print()

    # Step 0: env di produzione dal file WSGI. Va fatto PRIMA di qualunque
    # invocazione del runner delle migrations (anche `--status`, che importa i
    # modelli): senza, il processo ripiega sui default di sviluppo.
    wsgi_env = load_wsgi_env()
    if wsgi_env:
        # Solo i NOMI: i valori sono segreti (SECRET_KEY, MAIL_PASSWORD, ...).
        print(f"Env dal WSGI: {', '.join(sorted(wsgi_env))}")
    else:
        print(f"Env dal WSGI: nessuna letta da {WSGI_FILE}")

    # Con FLASK_ENV=production e senza chiave, il primo import dei modelli
    # solleverebbe (fail-fast in utils/encryption.py): meglio dirlo qui che
    # lasciare uno stack trace a meta' deploy.
    if os.environ.get("FLASK_ENV") == "production" and not os.environ.get(
        "ENCRYPTION_KEY"
    ):
        print(
            "ERROR: FLASK_ENV=production ma ENCRYPTION_KEY non disponibile. "
            "Ogni import dei modelli fallirebbe. Deploy interrotto."
        )
        sys.exit(1)

    print()

    # Step 1: Git pull
    success, output = git_pull()
    print(f"Git pull: {output}")
    if not success:
        print("ERROR: Git pull failed, aborting")
        sys.exit(1)

    has_new_code = "Already up to date" not in output

    if not has_new_code:
        # No new commits, but check if deps are out of sync
        # (e.g. manual git pull without pip install)
        if deps_in_sync():
            print("\nNo changes to deploy.")
            return
        print("\nNo new commits, but dependencies are out of sync.")

    print()

    # Step 2: Install dependencies
    success, output = install_dependencies()
    print(f"Dependencies: {output}")
    if not success:
        print("WARNING: Dependencies installation may have failed")

    print()

    # Step 3: Run migrations — solo se pendenti, e MAI con la web app accesa
    pending = count_pending_migrations()
    if pending == 0:
        print("Migrations: nessuna pendente, step saltato")
    else:
        if pending is None:
            print("WARNING: stato migrations non determinabile, assumo pendenti")
        # Una migration che tocca PII (decrypt/compute_email_hash) con la
        # chiave di sviluppo NON solleva: la decifratura fallisce, il guard
        # salta la riga e il backfill resta vuoto lasciando la migration
        # marcata come applicata. E' successo il 2026-06-25 con
        # 20260625_add_email_hash: 0 hash su 37 utenti, recupero password muto
        # per cinque settimane. Meglio un deploy fermo di un guasto invisibile.
        if not os.environ.get("ENCRYPTION_KEY"):
            print(
                "ERROR: migrations pendenti ma ENCRYPTION_KEY non disponibile "
                f"(non letta da {WSGI_FILE}). Una migration sui PII fallirebbe "
                "in silenzio. Deploy interrotto. Procedura manuale: tab Web -> "
                "Disable, `ENCRYPTION_KEY='...' python migrations/runner.py`, "
                "tab Web -> Enable."
            )
            sys.exit(1)
        success, output = run_migrations_safely()
        print(f"Migrations: {output}")
        if not success:
            print("ERROR: migrations non eseguite/fallite, deploy interrotto")
            sys.exit(1)

    print()

    # Step 4: Reload web app
    success, output = reload_webapp()
    print(f"Reload: {output}")

    print()
    print("=" * 60)
    print("Deploy complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
