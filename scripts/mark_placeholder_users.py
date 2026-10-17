"""Segna non registrati gli utenti storici che hanno giocato ma non sono mai entrati.

    venv/bin/python scripts/mark_placeholder_users.py             # prova generale
    venv/bin/python scripts/mark_placeholder_users.py --commit    # scrive davvero

Prima dell'ADR-085 chi giocava una serata senza account se lo vedeva creare dal
direttore, con email e password che nessuno ha mai usato. Questi utenti sono
non registrati a tutti gli effetti: segnarli ``is_placeholder`` li rende
riscattabili, e non avendo un creatore il riscatto lo conferma **solo
l'admin** (ADR-086). I criteri stanno in ``models/user/placeholder_storici.py``.

⚠️  Segnato non registrato, un utente **non entra più**: il login lo rifiuta
finché qualcuno non lo riscatta. Per questo la prova generale stampa l'elenco
completo, da rivedere prima del ``--commit``. Il segno si toglie a mano
(``is_placeholder = 0``) se qualcuno in elenco l'account lo usa davvero.

⚠️  In produzione va eseguito con la web app su **Disabled** (storage NFS, lock
SQLite inaffidabili), riabilitandola subito dopo.
"""

import argparse
import logging
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.prod_env import (  # noqa: E402
    PRODUCTION_REQUIRED,
    bootstrap_and_create_app,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def esegui(commit: bool = False) -> int:
    # Nome e cognome sono cifrati: senza la chiave vera l'elenco li
    # mostrerebbe vuoti, e l'admin rivedrebbe la scelta al buio.
    app = bootstrap_and_create_app(required=PRODUCTION_REQUIRED + ("ENCRYPTION_KEY",))

    from models import db
    from models.user.placeholder_storici import candidati_storici, segna

    with app.app_context():
        if commit:
            logger.info("Le modifiche VERRANNO scritte sul database.")
        else:
            logger.info("PROVA GENERALE: non viene scritto niente.")

        utenti = candidati_storici()
        if not utenti:
            logger.info("Nessun utente storico da segnare.")
            return 0

        logger.info("Utenti mai entrati che hanno giocato: %s", len(utenti))
        for utente in utenti:
            iscrizioni = len(utente.inscriptions)
            logger.info(
                "  #%s %s — %s · creato %s · %s iscrizioni%s",
                utente.id,
                utente.username,
                utente.full_name or "senza nome e cognome",
                utente.created_at,
                iscrizioni,
                " · email presente" if utente.email else "",
            )

        segna(utenti)
        if commit:
            db.session.commit()
            logger.info("Scritto. Utenti segnati non registrati: %s", len(utenti))
        else:
            db.session.rollback()
            logger.info(
                "Prova generale conclusa, niente scritto. Da segnare: %s",
                len(utenti),
            )
        return len(utenti)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Segna non registrati gli utenti storici mai entrati."
    )
    parser.add_argument(
        "--commit", action="store_true", help="Scrive le modifiche sul database"
    )
    args = parser.parse_args()
    esegui(commit=args.commit)
