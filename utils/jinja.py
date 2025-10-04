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
    """Formatta una data per la visualizzazione locale nel browser usando JavaScript."""
    if not value:
        return Markup("N/A")

    # Converti in stringa ISO per JavaScript
    if isinstance(value, datetime):
        iso_date = value.isoformat()
    elif isinstance(value, date):
        iso_date = value.isoformat()
    else:
        iso_date = str(value)

    return Markup(f'<span data-date="{escape(iso_date)}">{escape(iso_date)}</span>')


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

    return Markup(f'<span data-datetime="{escape(iso_date)}">{escape(iso_date)}</span>')


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
