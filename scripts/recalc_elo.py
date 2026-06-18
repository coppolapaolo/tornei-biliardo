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
from models import db, User  # noqa: E402
from models.match.models import Match  # noqa: E402
from models.rating.models import PlayerRating, RatingSystem  # noqa: E402
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

        # 1. Reset all ratings
        logger.info("Resetting existing Elo ratings...")

        # Il reset avviene SEMPRE nella sessione (anche in dry-run): così il
        # replay successivo è significativo. Senza azzerare anche la history,
        # l'idempotenza di process_match_result skipperebbe i match già
        # processati lasciando i rating a zero. In dry-run il rollback finale
        # annulla tutto; solo con --commit si persiste.
        from models.rating.models import MatchRatingHistory

        # Reset User model fields
        users = User.query.all()
        for user in users:
            # None = "non ancora valutato" (ricalcolo da capo)
            user.elo_rating = None
            db.session.add(user)

        # Delete PlayerRating entries for ELO + la history
        db.session.query(PlayerRating).filter_by(
            rating_system=RatingSystem.ELO
        ).delete()
        db.session.query(MatchRatingHistory).filter_by(
            rating_system=RatingSystem.ELO
        ).delete()
        db.session.flush()
        logger.info(
            "Ratings + history reset (%s)."
            % ("commit pending" if commit else "dry-run, sarà rollbackato")
        )

        # 2. Get all finished matches (completed + validated) sorted by date
        matches = matches_to_process()

        logger.info(f"Found {len(matches)} finished matches to process.")

        processed_count = 0

        skipped_count = 0
        for match in matches:
            try:
                # Coerente con RatingEventHandlers: walkover e match con
                # handicap (effective_has_handicap, ereditato da gara/campionato)
                # NON contribuiscono al rating.
                if match.is_walkover or match.effective_has_handicap:
                    skipped_count += 1
                    continue

                # RatingCalculationService handles Trio and Standard. Fetches
                # current rating from DB; avendo azzerato i rating + history,
                # riparte dal default 1200 e riprocessa in ordine cronologico.
                RatingCalculationService.process_match_result(match)
                processed_count += 1

                if processed_count % 10 == 0:
                    logger.info(f"Processed {processed_count} matches...")

            except Exception as e:
                logger.error(f"Error processing match {match.id}: {e}")

        logger.info(
            f"Processed {processed_count} total matches "
            f"({skipped_count} skipped: walkover/handicap)."
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
