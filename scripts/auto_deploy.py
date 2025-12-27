#!/usr/bin/env python3
"""Auto-deploy script for PythonAnywhere scheduled task.

This script:
1. Pulls latest code from GitHub
2. Runs pending database migrations
3. Reloads the web app

Setup on PythonAnywhere:
1. Go to Tasks tab
2. Add a new scheduled task (e.g., every hour)
3. Command: cd /home/paolocoppola/mysite && python scripts/auto_deploy.py

Or run manually via Bash console:
    cd /home/paolocoppola/mysite && python scripts/auto_deploy.py
"""

import subprocess
import os
import sys
from pathlib import Path

# Configuration
PROJECT_DIR = Path(__file__).parent.parent
REMOTE = "origin"
BRANCH = "main"


def run_command(cmd: list, cwd: Path = None) -> tuple:
    """Run command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=60
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
    success, local = run_command(["git", "rev-parse", "HEAD"])
    success2, remote = run_command(["git", "rev-parse", f"{REMOTE}/{BRANCH}"])

    if local == remote:
        return True, "Already up to date"

    # Pull changes
    success, output = run_command(["git", "pull", REMOTE, BRANCH])
    return success, output


def run_migrations() -> tuple:
    """Run pending database migrations."""
    print("Running migrations...")

    migrations_runner = PROJECT_DIR / "migrations" / "runner.py"
    if not migrations_runner.exists():
        return True, "No migrations runner found, skipping"

    success, output = run_command([sys.executable, str(migrations_runner)])
    return success, output


def reload_webapp() -> tuple:
    """Reload the PythonAnywhere web app via touch."""
    print("Reloading web app...")

    # On PythonAnywhere, touching the WSGI file reloads the app
    wsgi_file = Path("/var/www/paolocoppola_pythonanywhere_com_wsgi.py")

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

    if "Already up to date" in output:
        print("\nNo changes to deploy.")
        return

    print()

    # Step 2: Run migrations
    success, output = run_migrations()
    print(f"Migrations: {output}")
    if not success:
        print("WARNING: Migrations may have failed")

    print()

    # Step 3: Reload web app
    success, output = reload_webapp()
    print(f"Reload: {output}")

    print()
    print("=" * 60)
    print("Deploy complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
