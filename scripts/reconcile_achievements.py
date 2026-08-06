"""Riconcilia (retroattivamente) gli achievement di tutti gli utenti.

Il sistema achievement è **metric-driven e auto-correttivo**: l'idoneità si
calcola sempre dalla fonte di verità (statistiche, ledger XP, conteggi reali),
non da contatori. Quindi NON serve alcun "reset" della gamification: i dati XP/
livelli/streak restano validi e gli achievement già sbloccati non vanno toccati.

Questo script esegue una **ricalcolo idempotente**: per ogni utente non-admin
chiama `AchievementService.reconcile_achievements`, che sblocca i badge già
meritati (in base ai dati storici) senza aspettare la prossima attività e senza
mai revocare nulla (lo sblocco è monotòno). Va eseguito UNA VOLTA dopo il deploy
del nuovo sistema; ri-eseguirlo è sicuro.

Usage:
    python scripts/reconcile_achievements.py            # esegue e committa
    python scripts/reconcile_achievements.py --dry-run  # solo conteggio, nessun award
"""

import argparse
import logging
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# Radice del progetto (per `app`, `models`) e cartella scripts (per
# `prod_env`): serve entrambe anche quando il file viene caricato per
# path invece che eseguito, come fanno i test.
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)

from prod_env import PRODUCTION_REQUIRED, bootstrap_or_exit  # noqa: E402
from app import create_app  # noqa: E402
from models import db, User  # noqa: E402
from models.gamification.achievement_service import AchievementService  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def reconcile_all(dry_run: bool = False) -> dict:
    """Riconcilia tutti gli utenti non-admin. Ritorna statistiche."""
    users = User.query.filter(User.role != "admin").all()
    total_users = len(users)
    total_unlocked = 0
    users_with_unlocks = 0

    for user in users:
        if dry_run:
            # In dry-run non assegnamo: stimiamo quanti sarebbero sbloccati
            # ri-valutando senza persistere è complesso, quindi ci limitiamo a
            # contare gli utenti. L'award reale avviene solo senza --dry-run.
            continue
        newly = AchievementService.reconcile_achievements(user.id)
        if newly:
            users_with_unlocks += 1
            total_unlocked += len(newly)
            logger.info(f"  user {user.id} ({user.username}): +{len(newly)} → {newly}")

    return {
        "total_users": total_users,
        "users_with_unlocks": users_with_unlocks,
        "total_unlocked": total_unlocked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Non assegna nulla: stampa solo il numero di utenti che verrebbero valutati.",
    )
    args = parser.parse_args()

    # Console: non eredita le env dal file WSGI. ENCRYPTION_KEY è fra i
    # requisiti perché lo script legge gli utenti (email cifrata): con la
    # chiave di sviluppo la decifratura fallisce in silenzio e la
    # riconciliazione girerebbe su dati vuoti (incidente 2026-06-25).
    bootstrap_or_exit(PRODUCTION_REQUIRED + ("ENCRYPTION_KEY",))
    app = create_app(os.environ.get("FLASK_ENV", "production"))
    with app.app_context():
        if args.dry_run:
            count = User.query.filter(User.role != "admin").count()
            logger.info(f"[dry-run] {count} utenti non-admin verrebbero riconciliati.")
            return 0

        logger.info("Riconciliazione achievement per tutti gli utenti…")
        stats = reconcile_all(dry_run=False)
        logger.info(
            "Fatto: %(total_unlocked)s achievement sbloccati per "
            "%(users_with_unlocks)s/%(total_users)s utenti." % stats
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
