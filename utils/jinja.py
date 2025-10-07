# utils/jinja.py — aggiunta di un helper per render accattivante
from markupsafe import Markup, escape
from datetime import datetime, date, time


def display_user_handle(user) -> Markup:
    if getattr(user, "is_deleted", False):
        date = user.deleted_at.strftime("%d/%m/%Y") if user.deleted_at else ""
        prev = escape(user.previous_username or user.username)
        return Markup(f"🗑️ <s>{prev}</s> <small class='text-muted'>· {date}</small>")
    return Markup(escape(user.username))


def format_date_local(value) -> Markup:
    """Formatta una data in formato italiano (dd/mm/yyyy)."""
    if not value:
        return Markup("N/A")

    # Formatta direttamente in Python con formato italiano
    if isinstance(value, datetime):
        formatted = value.strftime('%d/%m/%Y')
    elif isinstance(value, date):
        formatted = value.strftime('%d/%m/%Y')
    else:
        formatted = str(value)

    return Markup(escape(formatted))


def format_datetime_local(value) -> Markup:
    """Formatta data e ora per la visualizzazione locale nel browser usando JavaScript."""
    if not value:
        return Markup("N/A")

    # Converti in stringa ISO per JavaScript
    if isinstance(value, datetime):
        iso_date = value.isoformat()
    elif isinstance(value, date):
        # Se è solo una data, usa mezzanotte
        iso_date = datetime.combine(value, time.min).isoformat()
    else:
        iso_date = str(value)

    # Usa direttamente toLocaleString in Python invece di JavaScript
    # per evitare problemi di parsing nel browser
    if isinstance(value, datetime):
        # Formatta direttamente in Python con formato italiano
        formatted = value.strftime('%d/%m/%Y, %H:%M')
    elif isinstance(value, date):
        formatted = value.strftime('%d/%m/%Y')
    else:
        formatted = iso_date

    return Markup(escape(formatted))


def format_time_local(value) -> Markup:
    """Formatta un orario per la visualizzazione locale."""
    if not value:
        return Markup("N/A")

    # Se è un oggetto time, convertilo in stringa
    if isinstance(value, time):
        time_str = value.strftime('%H:%M')
    else:
        time_str = str(value)

    return Markup(escape(time_str))


def format_distance(distance_obj) -> Markup:
    """Formatta un oggetto Distance per la visualizzazione.

    Args:
        distance_obj: Distance value object or model with distance_config property

    Returns:
        Markup: HTML-safe formatted distance string

    Examples:
        {{ gara.distance_config|format_distance }}
        → "Best of 7 racks"

        {{ match.distance_config|format_distance }}
        → "Best of 3 sets, each set best of 5 racks"
    """
    if not distance_obj:
        return Markup("N/A")

    # Se ha una property distance_config, usala
    if hasattr(distance_obj, 'distance_config'):
        distance_obj = distance_obj.distance_config

    # Usa il metodo to_display_string() se disponibile
    if hasattr(distance_obj, 'to_display_string'):
        return Markup(escape(distance_obj.to_display_string()))

    return Markup("N/A")


def format_score(score_obj) -> Markup:
    """Formatta un oggetto Score per la visualizzazione.

    Args:
        score_obj: RackScore or MatchScore value object, or model with
                   rack_score/match_score property

    Returns:
        Markup: HTML-safe formatted score string

    Examples:
        {{ match.rack_score|format_score }}
        → "4-2"

        {{ match.match_score|format_score }}
        → "2-1"

        {{ set.rack_score|format_score }}
        → "3-1"
    """
    if not score_obj:
        return Markup("0-0")

    # Se ha property rack_score o match_score, usala
    if hasattr(score_obj, 'rack_score'):
        score_obj = score_obj.rack_score
    elif hasattr(score_obj, 'match_score'):
        score_obj = score_obj.match_score

    # Usa il metodo to_display_string() se disponibile
    if hasattr(score_obj, 'to_display_string'):
        return Markup(escape(score_obj.to_display_string()))

    return Markup("N/A")


def format_distance_short(gara_or_distance) -> Markup:
    """Formatta distanza in forma abbreviata (es. "BO7", "X4").

    Args:
        gara_or_distance: Gara model or Distance object

    Returns:
        Markup: Abbreviated distance format

    Examples:
        {{ gara|format_distance_short }}
        → "BO7" (Best of 7)
        → "X4" (Exactly 4)
    """
    if not gara_or_distance:
        return Markup("N/A")

    # Ottieni Distance object
    if hasattr(gara_or_distance, 'distance_config'):
        distance = gara_or_distance.distance_config
    else:
        distance = gara_or_distance

    if hasattr(distance, 'racks') and hasattr(distance, 'racks_best_of'):
        prefix = "BO" if distance.racks_best_of else "X"
        return Markup(f"{prefix}{distance.racks}")

    return Markup("N/A")
