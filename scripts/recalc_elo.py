"""
Script to recalculate Elo ratings from scratch based on match history.

Usage:
    python scripts/recalc_elo.py [--commit]

Options:
    --commit    Commit changes to database. If not provided, runs in dry-run mode.
"""

import sys
import os
import argparse
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from models.match.models import Match  # noqa: E402
from models.status_enum import MatchStatus  # noqa: E402
from models.rating.calculation_service import RatingCalculationService  # noqa: E402

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
    return (
        Match.query.filter(Match.status.in_(MatchStatus.finished_values()))
        .order_by(Match.ended_at.asc(), Match.id.asc())
        .all()
    )


def recalculate_elo(commit=False):
    app = create_app()

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
