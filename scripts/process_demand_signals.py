"""Ciclo di vita dei segnali-domanda (ADR-036 open item 3).

Da eseguire come scheduled task (es. una volta al giorno):
1. invia il prompt di riconferma per i segnali prossimi alla scadenza;
2. marca EXPIRED i segnali scaduti.

Usage:
    python scripts/process_demand_signals.py

PythonAnywhere scheduled task:
    Command: cd /home/paolocoppola/mysite && python scripts/process_demand_signals.py
    Frequency: giornaliera
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models.demand.service import DemandSignalService


def main():
    app = create_app()
    with app.app_context():
        reminded = DemandSignalService.send_expiry_reminders()
        expired = DemandSignalService.expire_due_signals()
        print(f"Demand: {reminded} promemoria inviati, {expired} segnali scaduti")


if __name__ == "__main__":
    main()
