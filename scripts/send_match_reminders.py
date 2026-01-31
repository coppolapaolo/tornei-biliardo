"""Script to send match reminders for upcoming individual matches.

Designed to be run as a scheduled task (e.g., every 15 minutes).

Usage:
    python scripts/send_match_reminders.py

PythonAnywhere scheduled task setup:
    Command: cd /home/paolocoppola/mysite && python scripts/send_match_reminders.py
    Frequency: Every 15 minutes (or adjust based on window_minutes)
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models.individual_match.match_lifecycle_service import MatchLifecycleService


def main():
    """Send reminders for upcoming matches."""
    app = create_app()

    with app.app_context():
        reminded_ids = MatchLifecycleService.send_match_reminders(
            hours_before=2, window_minutes=15
        )

        if reminded_ids:
            print(f"Sent reminders for {len(reminded_ids)} matches: {reminded_ids}")
        else:
            print("No matches found in reminder window")


if __name__ == "__main__":
    main()
