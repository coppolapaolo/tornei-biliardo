"""Promemoria per i match individuali in programma.

Pensato per girare come scheduled task **ogni ora**. La cadenza non è una
scelta di comodo: su PythonAnywhere gli scheduled task non scendono sotto
l'ora, e lo script nasceva invece con una finestra di 15 minuti, presupponendo
di girare ogni quarto d'ora. Registrato così avrebbe coperto 15 minuti su 60 e
tre promemoria su quattro non sarebbero partiti; la finestra è quindi allineata
alla cadenza reale (60 minuti, cfr. ``send_match_reminders``). Il promemoria
arriva fra le 2 e le 3 ore prima del match invece che a due ore esatte — per
questo il messaggio riporta l'orario dell'incontro invece di promettere "fra
due ore".

Non è accorpabile a ``daily_jobs.py``: quello è il runner dei lavori
*giornalieri*, questo ha una cadenza sua.

Usage:
    python scripts/send_match_reminders.py

PythonAnywhere scheduled task setup:
    Command: cd /home/paolocoppola/mysite && python scripts/send_match_reminders.py
    Frequency: oraria
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# Servono entrambe: la radice del progetto (per `app`, `models`) e la cartella
# scripts (per `prod_env`). La radice va inserita per ultima così da restare
# davanti a `scripts/` in sys.path — stessa ragione spiegata in daily_jobs.py.
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from prod_env import bootstrap_or_exit  # noqa: E402
from app import create_app  # noqa: E402
from models.individual_match.match_lifecycle_service import (  # noqa: E402
    MatchLifecycleService,
)


def main() -> int:
    """Send reminders for upcoming matches."""
    # Lo scheduled task è un processo separato e non eredita le variabili del
    # file WSGI: senza questo, `create_app` in production muore su SECRET_KEY.
    bootstrap_or_exit()
    app = create_app(os.environ.get("FLASK_ENV", "production"))

    with app.app_context():
        reminded_ids = MatchLifecycleService.send_match_reminders()

        if reminded_ids:
            print(f"Sent reminders for {len(reminded_ids)} matches: {reminded_ids}")
        else:
            # Nessun match nella finestra, oppure nessun giocatore
            # raggiungibile: `send_match_reminders` conta solo i match per cui
            # è uscita almeno una notifica.
            print("No reminders sent")

    return 0


if __name__ == "__main__":
    sys.exit(main())
