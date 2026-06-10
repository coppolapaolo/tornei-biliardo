#!/usr/bin/env python3
"""Auto-deploy script for PythonAnywhere scheduled task.

This script:
1. Pulls latest code from GitHub
2. Runs pending database migrations — SOLO con la web app disabilitata
3. Reloads the web app

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

import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Optional

# Configuration
PROJECT_DIR = Path(__file__).parent.parent
REMOTE = "origin"
BRANCH = "main"
PA_USERNAME = "paolocoppola"
PA_DOMAIN = "www.torneibiliardo.it"  # domain_name della webapp (vedi WSGI file)


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
    # Custom domain: www.torneibiliardo.it
    wsgi_file = Path("/var/www/www_torneibiliardo_it_wsgi.py")

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
