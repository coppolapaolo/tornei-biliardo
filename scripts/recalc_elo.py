"""Ricalcola gli Elo da zero rigiocando tutta la storia delle partite.

    venv/bin/python scripts/recalc_elo.py             # prova generale
    venv/bin/python scripts/recalc_elo.py --commit    # scrive davvero

L'Elo è **path-dependent**: il ricalcolo azzera e rigioca tutto in ordine
cronologico, quindi non è mai un'operazione locale. Cambiare quali partite sono
eleggibili — per esempio assegnando le categorie di una gara con handicap
(ADR-049) — sposta il rating di tutti, non solo dei giocatori toccati.

Da agosto 2026 questo script gira anche **in produzione**, come seguito di
`set_gara_categorie.py`: costruisce quindi l'app con
`prod_env.bootstrap_and_create_app`, che carica le env dal file WSGI **prima**
di importare l'app. Console e scheduled task non ereditano l'ambiente della web
app, e `from app import create_app` in cima al file congelerebbe un ambiente
vuoto. Invariante presidiata da tests/new/unit/test_script_import_order.py.

⚠️  In produzione va eseguito con la web app su **Disabled** (storage NFS, lock
SQLite inaffidabili), riabilitandola subito dopo.
"""

import sys
import os
import argparse
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.prod_env import bootstrap_and_create_app  # noqa: E402

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def matches_to_process():
    """Match conclusi da riprocessare, in ordine cronologico.

    Include SIA `completed` SIA `validated` (`MatchStatus.finished_values()`):
    `validated` è lo stato finale normale dopo la conferma bilaterale dei due
    giocatori, quindi va riprocessato come `completed`. Filtrare solo su
    `completed` faceva sì che il backfill — che prima azzera tutti gli ELO —
    lasciasse a NULL i giocatori i cui match erano già stati validati.
    """
    from models.match.models import Match
    from models.status_enum import MatchStatus

    return (
        Match.query.filter(Match.status.in_(MatchStatus.finished_values()))
        .order_by(Match.ended_at.asc(), Match.id.asc())
        .all()
    )


def recalculate_elo(commit=False):
    # Import ritardati di proposito: l'app (e con lei `config`) va costruita
    # dopo che `bootstrap_and_create_app` ha popolato l'ambiente.
    app = bootstrap_and_create_app()

    from models import db
    from models.rating.calculation_service import RatingCalculationService

    with app.app_context():
        logger.info("Starting Elo recalculation...")

        if commit:
            logger.info("Changes WILL be committed to database.")
        else:
            logger.info("DRY RUN: No changes will be saved.")

        # Reset + replay is done by the pure service method (no commit/I/O), so
        # the same logic is reused by the user-merge flow. The reset happens in
        # the session even in dry-run, so the replay is meaningful; the final
        # rollback undoes everything. Only --commit persists.
        result = RatingCalculationService.recalculate_all_elo()

        logger.info(
            f"Processed {result['processed']} of {result['total']} finished "
            f"matches ({result['skipped']} skipped: walkover/handicap)."
        )

        # Dual ELO: ricalcola anche il pool globale (tornei + casual VALIDATED),
        # fuso cronologicamente. Non tocca l'ELO competitivo né User.elo_rating.
        global_result = RatingCalculationService.recalculate_all_elo_global()
        logger.info(
            f"ELO_GLOBAL: processed {global_result['processed']} of "
            f"{global_result['total']} match ({global_result['skipped']} "
            f"skipped: walkover/handicap)."
        )

        # Pool a rack (ADR-052): calcolato in parallelo e non mostrato, ma va
        # ricostruito insieme agli altri o resterebbe fermo all'ultima
        # riparazione dei dati.
        rack_result = RatingCalculationService.recalculate_all_rack()
        logger.info(
            f"RACK: processed {rack_result['processed']} of "
            f"{rack_result['total']} match ({rack_result['skipped']} "
            f"skipped: walkover/handicap/trii)."
        )

        if commit:
            db.session.commit()
            logger.info("Successfully committed changes.")
        else:
            db.session.rollback()
            logger.info("Dry run completed. Rolled back changes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recalculate Elo ratings.")
    parser.add_argument(
        "--commit", action="store_true", help="Commit changes to database"
    )
    args = parser.parse_args()

    confirm = input(
        "This will RESET all Elo ratings and recalculate them. Are you sure? [y/N] "
    )
    if confirm.lower() != "y":
        print("Aborted.")
        sys.exit(0)

    recalculate_elo(commit=args.commit)
