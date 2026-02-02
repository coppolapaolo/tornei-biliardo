
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
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, User
from models.match.models import Match
from models.rating.models import PlayerRating, RatingSystem
from models.status_enum import MatchStatus
from models.rating.calculation_service import RatingCalculationService

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

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
        
        # Reset User model fields
        users = User.query.all()
        for user in users:
            user.elo_rating = None # Or 1200? Let's use None to indicate 'not yet rated' or start fresh
            if commit:
                db.session.add(user)
                
        # Delete PlayerRating entries for ELO
        if commit:
            db.session.query(PlayerRating).filter_by(rating_system=RatingSystem.ELO).delete()
            db.session.commit()
            logger.info("Ratings reset.")
        else:
            logger.info("[Dry Run] Would delete all ELO PlayerRatings and reset User.elo_rating")

        # 2. Get all completed matches sorted by date
        matches = (
            Match.query
            .filter_by(status=MatchStatus.COMPLETED.value)
            .order_by(Match.ended_at.asc(), Match.id.asc())
            .all()
        )
        
        logger.info(f"Found {len(matches)} completed matches to process.")
        
        processed_count = 0
        
        for match in matches:
            try:
                # We need to process it. Logic reuse:
                # RatingCalculationService handles Trio and Standard.
                # It fetches current rating from DB. 
                # Since we cleared DB, it will start from 1200 default in the service logic.
                
                # IMPORTANT: If dry-run, we can't rely on DB updates being visible for next match 
                # unless we flush. But flushing in dry-run might be tricky if we rollback later.
                # Actually, standard transaction rollback works fine.
                
                RatingCalculationService.process_match_result(match)
                processed_count += 1
                
                if processed_count % 10 == 0:
                    logger.info(f"Processed {processed_count} matches...")
                    
            except Exception as e:
                logger.error(f"Error processing match {match.id}: {e}")

        logger.info(f"Processed {processed_count} total matches.")

        if commit:
            db.session.commit()
            logger.info("Successfully committed changes.")
        else:
            db.session.rollback()
            logger.info("Dry run completed. Rolled back changes.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recalculate Elo ratings.")
    parser.add_argument("--commit", action="store_true", help="Commit changes to database")
    args = parser.parse_args()
    
    confirm = input("This will RESET all Elo ratings and recalculate them. Are you sure? [y/N] ")
    if confirm.lower() != 'y':
        print("Aborted.")
        sys.exit(0)

    recalculate_elo(commit=args.commit)
