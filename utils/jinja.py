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


def format_date_local(value, tz=None) -> Markup:
    """Solo il giorno (dd/mm/yyyy), nel fuso di chi legge (ADR-043).

    La distinzione fra i due rami è il punto:

    - un ``datetime`` è un **istante**, e il DB lo tiene in UTC. Va convertito
      prima di ridurlo a un giorno, altrimenti vicino a mezzanotte la data
      mostrata è quella sbagliata — un tentativo registrato alle 01:30 di
      martedì a Roma risultava fatto di lunedì. Non c'è modo di accorgersene:
      «lunedì» è una data plausibile;
    - una ``date`` **non** è un istante: «il 12 giugno» è il 12 giugno per
      tutti. Riproiettarla la falserebbe, facendo comparire l'11 a chi sta a
      ovest di Greenwich.

    ``tz`` va passato quando il testo è destinato a qualcun altro, come per
    gli altri filtri d'orario.
    """
    if not value:
        return Markup(_("N/A"))

    if isinstance(value, datetime):
        formatted = _to_reader_time(value, tz).strftime("%d/%m/%Y")
    elif isinstance(value, date):
        formatted = value.strftime("%d/%m/%Y")
    else:
        formatted = str(value)

    return Markup(escape(formatted))


def parse_json(value):
    """Deserializza un payload JSON arrivato in un flash message.

    I flash "di trasporto" (gamification, dialog modali) viaggiano come
    stringa JSON perché la sessione va serializzata. Il bridge JavaScript li
    passa a `JSON.parse`; questo filtro fa lo stesso lato Jinja, per i
    payload che diventano HTML invece che animazioni.

    Un payload illeggibile non deve rompere la pagina: restituisce None e il
    componente chiamante lo salta.
    """
    import json as _json

    if isinstance(value, dict):
        return value
    try:
        return _json.loads(value)
    except (TypeError, ValueError):
        return None


def format_datetime_local_text(value, tz=None) -> str:
    """Data e ora nel fuso del lettore, come testo semplice e senza markup.

    Serve dove il risultato non finisce in una pagina ma dentro un messaggio
    costruito in Python (flash, dialog, notifiche): lì il `<time>` di
    `format_datetime_local` verrebbe mostrato come tag grezzo o, peggio,
    escapato a mano.

    ``tz`` va passato **sempre** quando il testo è destinato a qualcun altro:
    una notifica scritta per due giocatori, o un promemoria composto da uno
    scheduled task, non hanno un «lettore corrente» da cui dedurlo, e senza
    argomento finirebbero nel fuso di ripiego (ADR-043).
    """
    if not value:
        return str(_("N/A"))

    if isinstance(value, datetime):
        return _to_reader_time(value, tz).strftime("%d/%m/%Y, %H:%M")

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    return str(value)


def _to_reader_time(value: datetime, tz=None) -> datetime:
    """Il naive UTC del DB portato nel fuso di chi legge.

    Un solo posto lo sa fare, e i filtri lo chiamano tutti: prima ognuno si
    riscriveva la conversione con ``Europe/Rome`` dentro, e tre copie della
    stessa regola sono tre modi di divergere.
    """
    from utils.local_time import UTC, resolve_timezone

    utc_dt = (
        value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    )
    return utc_dt.astimezone(tz or resolve_timezone())


def format_datetime_input(value, tz=None) -> str:
    """Valore per un ``<input type="datetime-local">``, nel fuso di chi legge.

    È la controparte in **ripopolamento** di ``|datetime_local``: quel filtro
    mostra, questo rimette il valore dentro il campo. I due devono usare lo
    stesso fuso della scrittura, altrimenti chi riapre un form e salva senza
    toccare niente sposta l'orario di un fuso — a ogni giro.

    Il ritorno è testo semplice e non ``Markup``: finisce dentro un attributo
    ``value``, dove Jinja lo escapa da sé.
    """
    from utils.local_time import format_local_input

    if not value:
        return ""
    if isinstance(value, datetime):
        return format_local_input(value, tz)
    return str(value)


def format_datetime_local(value, tz=None) -> Markup:
    """Formatta data e ora nel fuso di **chi legge** (ADR-043).

    IMPORTANT: Database stores naive datetimes as UTC (project convention).
    Il fuso di destinazione è quello salvato su `User.timezone`, dedotto dal
    browser; per un lettore anonimo o non ancora dedotto si ripiega sull'ora
    italiana.

    Output format:
        <time datetime="2025-01-15T14:30:00Z" class="datetime-local">15/01/2025,
        15:30</time>

    L'attributo `datetime` resta l'istante in UTC: è l'unica forma che non
    dipende da chi guarda, ed è quella che serve a screen reader, motori di
    ricerca e a qualunque riscrittura lato client.
    """
    if not value:
        return Markup(_("N/A"))

    if isinstance(value, datetime):
        from utils.local_time import UTC

        reader_time = _to_reader_time(value, tz)
        utc_dt = (
            value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        )

        formatted = reader_time.strftime("%d/%m/%Y, %H:%M")
        iso_utc = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        return Markup(
            f'<time datetime="{iso_utc}" class="datetime-local">'
            f"{escape(formatted)}</time>"
        )
    elif isinstance(value, date):
        # Just a date, no timezone conversion needed
        formatted = value.strftime("%d/%m/%Y")
        return Markup(escape(formatted))
    else:
        # Fallback for string values
        return Markup(escape(str(value)))


def format_time_local(value, tz=None) -> Markup:
    """Formatta un orario in formato HH:MM, nel fuso di chi legge.

    Accetta sia `time` (formattato direttamente: un orario senza data non ha
    un istante a cui riferirsi, quindi non c'è niente da convertire) sia
    `datetime` (convertito da UTC per coerenza con `format_datetime_local`).
    """
    if not value:
        return Markup(_("N/A"))

    if isinstance(value, datetime):
        time_str = _to_reader_time(value, tz).strftime("%H:%M")
    elif isinstance(value, time):
        time_str = value.strftime("%H:%M")
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
    if hasattr(distance_obj, "distance_config"):
        distance_obj = distance_obj.distance_config

    # Usa il metodo to_display_string() se disponibile
    if hasattr(distance_obj, "to_display_string"):
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
    if hasattr(score_obj, "rack_score"):
        score_obj = score_obj.rack_score
    elif hasattr(score_obj, "match_score"):
        score_obj = score_obj.match_score

    # Usa il metodo to_display_string() se disponibile
    if hasattr(score_obj, "to_display_string"):
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
    if hasattr(gara_or_distance, "distance_config"):
        distance = gara_or_distance.distance_config
    else:
        distance = gara_or_distance

    if hasattr(distance, "racks") and hasattr(distance, "is_race_to_racks"):
        prefix = "BO" if distance.is_race_to_racks else "X"
        return Markup(f"{prefix}{distance.racks}")

    return Markup(_("N/A"))


def gara_display_name(gara) -> Markup:
    """Titolo della gara: il nome se c'è, altrimenti 'Gara <numero>'.

    Delega a `Gara.display_name`, unica fonte per il titolo (issue #56/#57).
    Il fallback usava `gara.id`, cioè la chiave del database: su una gara
    senza nome mostrava "Gara 47" al posto della prova numero 2.

    Args:
        gara: Gara model

    Returns:
        Markup: il titolo, escaped
    """
    if not gara:
        return Markup(_("N/A"))

    return Markup(escape(gara.display_name))


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
        → "<s class='text-muted'>Mario</s> <i class='fas fa-flag text-muted small'
        title='Forfait'>F</i>"

        {{ player|player_name_with_forfeit(gara.id) }}  # Legacy, triggers query
        → "<s class='text-muted'>Mario</s> <i class='fas fa-flag text-muted small'
        title='Forfait'>F</i>"
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
                    '<i class="fas fa-flag text-muted small ms-1" '
                    'title="Forfait">F</i>'
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


def format_tpa(value) -> str:
    """Il TPA come si scrive sul referto: `.780`, `1.000`, `—` se non c'e'.

    Il motore lo tiene in millesimi interi (780 = .780). Il caso pieno e'
    l'unico che sfugge alla regola dei tre decimali dopo il punto: mille
    millesimi sono `1.000`, non `.1000`.

    Esempi:
        {{ 780|tpa_display }}   → ".780"
        {{ 1000|tpa_display }}  → "1.000"
        {{ None|tpa_display }}  → "—"
    """
    if value is None:
        return "—"
    try:
        millesimi = int(value)
    except (TypeError, ValueError):
        return "—"
    if millesimi >= 1000:
        return f"{millesimi // 1000}.{millesimi % 1000:03d}"
    return f".{millesimi:03d}"


def etichetta_dispari(policy) -> str:
    """Il nome, tradotto, della formula che decide chi riposa coi dispari.

    Le schermate mostravano il valore della colonna ripulito a mano
    («Bye With Challenge»): inglese in una pagina italiana, e con la parola
    «bye» che l'interfaccia non usa mai. Un valore sconosciuto torna com'e'.
    """
    from models.matchmaking.configuration import OddNumberPolicy

    valore = getattr(policy, "value", policy)
    etichette = {
        OddNumberPolicy.NO.value: _("Lista d'attesa"),
        OddNumberPolicy.BYE.value: _("X a tavolino"),
        OddNumberPolicy.BYE_WITH_CHALLENGE.value: _("X a tavolino con esercizio"),
        OddNumberPolicy.TRIO.value: _("Trio, partita a tre"),
    }
    return etichette.get(valore, valore or "")


def opzioni_dispari(classification_system=None) -> list[tuple[str, str]]:
    """Le formule dei dispari come voci di un menu: `(valore, nome tradotto)`.

    E' l'unica fonte delle opzioni dei moduli — creazione e modifica di gare e
    campionati — cosi' il nome letto nel menu e' lo stesso che poi compare
    nella pagina della gara (`etichetta_dispari`). Prima ogni modulo aveva il
    suo: «Bye (riposo)», «Riposo (punto gratis)», «X (vinto a tavolino)»,
    «Match a 3 Giocatori».

    Con un sistema di classifica si tolgono le formule che con quel sistema
    non reggono: la X a tavolino semplice col sistema RACK darebbe zero
    triangoli a chi riposa (`validators._validate_rack_system`). Senza, le
    formule ci sono tutte: serve ai moduli in cui il sistema si cambia nella
    stessa pagina.
    """
    from models.matchmaking.configuration import OddNumberPolicy
    from models.status_enum import ClassificationSystem

    sistema = getattr(classification_system, "value", classification_system)
    escluse = {
        ClassificationSystem.RACK.value: {OddNumberPolicy.BYE.value},
    }.get(sistema, set())
    return [
        (policy.value, etichetta_dispari(policy.value))
        for policy in OddNumberPolicy
        if policy.value not in escluse
    ]
