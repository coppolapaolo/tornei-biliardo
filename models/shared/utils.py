# models/shared/utils.py
"""Common utility functions shared across domains."""

from typing import List, Optional, Any, Dict
from datetime import datetime
import re


def parse_date_string(
    date_str: str, formats: Optional[List[str]] = None
) -> Optional[datetime]:
    """Parse a date string using multiple formats.

    Args:
        date_str: Date string to parse
        formats: List of format strings to try (defaults to common formats)

    Returns:
        Parsed datetime object or None if parsing fails
    """
    if formats is None:
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
        ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None


def format_datetime_for_display(
    dt: datetime, format_str: str = "%d/%m/%Y %H:%M"
) -> str:
    """Format datetime for display to users.

    Args:
        dt: Datetime object to format
        format_str: Format string (defaults to Italian format)

    Returns:
        Formatted date string
    """
    return dt.strftime(format_str)


def validate_email(email: str) -> bool:
    """Basic email validation.

    Args:
        email: Email string to validate

    Returns:
        True if email is valid, False otherwise
    """
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def calculate_rack_difference(winner_score: int, loser_score: int) -> int:
    """Calculate rack difference between winner and loser scores.

    Args:
        winner_score: Score of the winner
        loser_score: Score of the loser

    Returns:
        Rack difference (positive integer)
    """
    return abs(winner_score - loser_score)


def safe_get_attr(obj: Any, attr_path: str, default: Any = None) -> Any:
    """Safely get nested attribute values.

    Args:
        obj: Object to get attribute from
        attr_path: Dot-separated attribute path (e.g., 'user.profile.name')
        default: Default value if attribute not found

    Returns:
        Attribute value or default
    """
    attrs = attr_path.split(".")
    current = obj

    try:
        for attr in attrs:
            current = getattr(current, attr)
        return current
    except (AttributeError, TypeError):
        return default


def merge_dicts(dict1: Dict, dict2: Dict) -> Dict:
    """Merge two dictionaries, with dict2 values overriding dict1 values.

    Args:
        dict1: First dictionary
        dict2: Second dictionary (overrides dict1)

    Returns:
        Merged dictionary
    """
    result = dict1.copy()
    result.update(dict2)
    return result
