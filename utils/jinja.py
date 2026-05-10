# utils/jinja.py — aggiunta di un helper per render accattivante
from markupsafe import Markup, escape
from datetime import datetime, date, time
from flask_babel import gettext as _


def display_user_handle(user) -> Markup:
    if getattr(user, "is_deleted", False):
        date = user.deleted_at.strftime("%d/%m/%Y") if user.deleted_at else ""
        prev = escape(user.previous_username or user.username)
        return Markup(f"🗑️ <s>{prev}</s> <small class='text-muted'>· {date}</small>")
    return Markup(escape(user.username))


def format_date_local(value) -> Markup:
    """Formatta una data in formato italiano (dd/mm/yyyy)."""
    if not value:
        return Markup(_("N/A"))

    # Formatta direttamente in Python con formato italiano
    if isinstance(value, datetime):
        formatted = value.strftime('%d/%m/%Y')
    elif isinstance(value, date):
        formatted = value.strftime('%d/%m/%Y')
    else:
        formatted = str(value)

    return Markup(escape(formatted))


def format_datetime_local(value) -> Markup:
    """Formatta data e ora per la visualizzazione locale (Italia).

    IMPORTANT: Database stores naive datetimes as UTC (project convention).
    This filter converts UTC to Italian time using proper DST handling.

    Output format:
        <time datetime="2025-01-15T14:30:00Z" class="datetime-local">15/01/2025, 15:30</time>

    The <time> element:
    - Has semantic meaning for screen readers and search engines
    - Contains ISO 8601 UTC timestamp in datetime attribute
    - Displays Italian local time (Europe/Rome) accounting for DST
    - Can be enhanced by JavaScript to show browser-local time

    For JavaScript enhancement, add to your page:
        <script src="{{ url_for('static', filename='js/datetime-local.js') }}"></script>
    """
    if not value:
        return Markup(_("N/A"))

    if isinstance(value, datetime):
        # Import zoneinfo for proper DST handling (Python 3.9+)
        from zoneinfo import ZoneInfo

        # Treat naive datetime as UTC (project convention)
        if value.tzinfo is None:
            utc_dt = value.replace(tzinfo=ZoneInfo("UTC"))
        else:
            utc_dt = value.astimezone(ZoneInfo("UTC"))

        # Convert to Italian timezone (handles DST automatically)
        italian_tz = ZoneInfo("Europe/Rome")
        italian_time = utc_dt.astimezone(italian_tz)

        # Format for display
        formatted = italian_time.strftime('%d/%m/%Y, %H:%M')
        iso_utc = utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        # Output <time> element with ISO datetime for potential JS enhancement
        return Markup(
            f'<time datetime="{iso_utc}" class="datetime-local">'
            f'{escape(formatted)}</time>'
        )
    elif isinstance(value, date):
        # Just a date, no timezone conversion needed
        formatted = value.strftime('%d/%m/%Y')
        return Markup(escape(formatted))
    else:
        # Fallback for string values
        return Markup(escape(str(value)))


def format_time_local(value) -> Markup:
    """Formatta un orario in formato HH:MM (timezone Italia per i datetime).

    Accetta sia `time` (formattato direttamente) sia `datetime` (convertito
    da UTC al timezone Italia per coerenza con format_datetime_local).
    """
    if not value:
        return Markup(_("N/A"))

    if isinstance(value, datetime):
        from zoneinfo import ZoneInfo

        if value.tzinfo is None:
            utc_dt = value.replace(tzinfo=ZoneInfo("UTC"))
        else:
            utc_dt = value.astimezone(ZoneInfo("UTC"))
        italian_time = utc_dt.astimezone(ZoneInfo("Europe/Rome"))
        time_str = italian_time.strftime('%H:%M')
    elif isinstance(value, time):
        time_str = value.strftime('%H:%M')
    else:
        time_str = str(value)

    return Markup(escape(time_str))


def format_discipline(value) -> Markup:
    """B3: render a discipline value (enum or raw string) using its display_name.

    Centralizes the discipline → "8-Ball"/"9-Ball" mapping so templates
    don't need to repeat ``.replace('_', ' ')|title`` ad-hoc.

    Examples:
        {{ gara.discipline|discipline_display }}     → "8-Ball"
        {{ '9_ball'|discipline_display }}            → "9-Ball"
    """
    if not value:
        return Markup(_("N/A"))

    # Lazy import to avoid circular dependency at module load
    from models.status_enum import Discipline

    if isinstance(value, Discipline):
        return Markup(escape(value.display_name))

    raw = str(value)
    try:
        return Markup(escape(Discipline(raw).display_name))
    except ValueError:
        return Markup(escape(raw.replace("_", " ").title()))


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
        return Markup(_("N/A"))

    # Se ha una property distance_config, usala
    if hasattr(distance_obj, 'distance_config'):
        distance_obj = distance_obj.distance_config

    # Usa il metodo to_display_string() se disponibile
    if hasattr(distance_obj, 'to_display_string'):
        return Markup(escape(distance_obj.to_display_string()))

    return Markup(_("N/A"))


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

    return Markup(_("N/A"))


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
        return Markup(_("N/A"))

    # Ottieni Distance object
    if hasattr(gara_or_distance, 'distance_config'):
        distance = gara_or_distance.distance_config
    else:
        distance = gara_or_distance

    if hasattr(distance, 'racks') and hasattr(distance, 'is_race_to_racks'):
        prefix = "BO" if distance.is_race_to_racks else "X"
        return Markup(f"{prefix}{distance.racks}")

    return Markup(_("N/A"))


def gara_display_name(gara) -> Markup:
    """Restituisce il nome della gara oppure 'Gara N' se il nome non c'e'.

    Args:
        gara: Gara model

    Returns:
        Markup: Formatted gara name with details
    """
    if not gara:
        return Markup(_("N/A"))

    name = gara.name or _("Gara %(id)s") % {'id': gara.id}
    return Markup(escape(name))


def player_name_with_forfeit(user, gara_id=None, is_forfeit=False) -> Markup:
    """Formatta il nome del giocatore con indicatore forfait se necessario.

    Args:
        user: User model
        gara_id: Optional gara ID (deprecated - use is_forfeit instead)
        is_forfeit: Boolean indicating if player has forfeited (preferred)

    Returns:
        Markup: Player name with forfeit indicator if applicable

    Examples:
        {{ player|player_name_with_forfeit(is_forfeit=True) }}
        → "<s class='text-muted'>Mario</s> <i class='fas fa-flag text-muted small' title='Forfait'>F</i>"

        {{ player|player_name_with_forfeit(gara.id) }}  # Legacy, triggers query
        → "<s class='text-muted'>Mario</s> <i class='fas fa-flag text-muted small' title='Forfait'>F</i>"
    """
    if not user:
        return Markup('<span class="text-muted">Bye</span>')

    username = escape(user.username)

    # Use is_forfeit directly if provided (no query)
    if is_forfeit:
        return Markup(
            f'<s class="text-muted">{username}</s> '
            f'<i class="fas fa-flag text-muted small ms-1" title="Forfait">F</i>'
        )

    # Fallback: query if gara_id provided but not is_forfeit (legacy)
    if gara_id:
        try:
            from models.competition.withdraw_policy_service import WithdrawPolicyService
            is_forfeit_db = WithdrawPolicyService.is_player_forfeit(gara_id, user.id)

            if is_forfeit_db:
                return Markup(
                    f'<s class="text-muted">{username}</s> '
                    f'<i class="fas fa-flag text-muted small ms-1" title="Forfait">F</i>'
                )
        except Exception:
            # Se c'è un errore nel controllo forfait, mostra solo il nome
            pass

    return Markup(username)


def trio_config_for_distance(distance: int):
    """Get TrioConfig for a given distance.

    Args:
        distance: The distance value from gara

    Returns:
        TrioConfig object if trio is allowed for this distance, None otherwise

    Examples:
        {% set config = gara.distance|trio_config_for_distance %}
        {% if config %}
            {{ config.num_rounds }} gironi, max {{ config.max_racks_per_player }} rack
        {% endif %}
    """
    from models.match.trio_config import TrioConfig

    config = TrioConfig(distance=distance)
    return config if config.is_trio_allowed else None
