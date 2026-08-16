"""Il fuso orario del lettore: da dove si ricava, e in che verso si converte.

Il DB tiene i naive come **UTC** — convenzione di progetto, ``utc_now()``. Ogni
orario che entra o esce va quindi convertito, e il fuso di riferimento è
**quello di chi legge**: la piattaforma è pensata anche in inglese, e un
giocatore a Londra deve vedere le sue 20:00, non le 21:00 di Milano (ADR-043).

Il fuso non si chiede all'utente: si **deduce dal browser** e si salva su
``User.timezone``. Salvarlo non è ridondanza — promemoria e notifiche nascono
in uno scheduled task, dove nessun browser esiste, e le caselle di posta non
eseguono JavaScript. Quello che non è scritto in colonna, fuori da una pagina
non esiste.

Le due direzioni sono state a lungo asimmetriche, ed è stato un bug silenzioso
per anni: in lettura la conversione c'era, in scrittura no, quindi chi digitava
``21:00`` se lo rivedeva come ``23:00``. Qui vivono entrambe, insieme, perché
è l'unico modo di non farle divergere di nuovo.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any, Optional
from zoneinfo import ZoneInfo, available_timezones

#: Il ripiego per chi un fuso non ce l'ha: utente anonimo, account creato prima
#: che la colonna esistesse, o browser che non l'ha ancora comunicato. È l'ora
#: italiana perché lì sta la maggioranza dei giocatori ed è il comportamento
#: che la piattaforma ha sempre avuto — ma è un **default**, non la verità.
FALLBACK_TIMEZONE = ZoneInfo("Europe/Rome")
UTC = ZoneInfo("UTC")

#: Nome storico, tenuto perché il codice esistente lo importa. È il ripiego.
DISPLAY_TIMEZONE = FALLBACK_TIMEZONE


@lru_cache(maxsize=1)
def _known_timezones() -> frozenset:
    """L'elenco dei fusi IANA, letto una volta sola.

    ``available_timezones()`` non è memoizzata e a ogni chiamata rilegge il
    database dei fusi da disco. Non sarebbe un problema se la si invocasse
    di rado, ma ``is_valid_timezone`` sta dentro ``resolve_timezone``, che sta
    dentro ogni filtro d'orario: una pagina con venti date la chiamerebbe venti
    volte. L'elenco non cambia mentre il processo vive.
    """
    return frozenset(available_timezones())


def is_valid_timezone(name: Optional[str]) -> bool:
    """Il nome è un fuso IANA vero?

    Serve perché il valore arriva da un client, e un client può mandare
    qualunque cosa. Un nome inventato salvato in colonna farebbe poi sollevare
    ``ZoneInfoNotFoundError`` a ogni pagina che mostra un orario — cioè quasi
    tutte.
    """
    return bool(name) and name in _known_timezones()


def resolve_timezone(user: Any = None) -> ZoneInfo:
    """Il fuso in cui mostrare (e leggere) gli orari per un dato lettore.

    Senza argomento prende ``current_user``, che è il caso di ogni template e
    di ogni route. Fuori da una richiesta — scheduled task, script da console —
    ``current_user`` non esiste: lì il lettore va passato esplicitamente,
    altrimenti si finisce a formattare l'orario di un giocatore nel fuso di
    nessuno.
    """
    if user is None:
        try:
            from flask_login import current_user

            user = current_user if current_user.is_authenticated else None
        except Exception:
            # Fuori da un contesto di richiesta: nessun lettore corrente.
            user = None

    name = getattr(user, "timezone", None) if user is not None else None
    if is_valid_timezone(name):
        return ZoneInfo(name)
    return FALLBACK_TIMEZONE


#: I formati che un ``<input type="datetime-local">`` produce: senza secondi di
#: norma, con i secondi se il campo dichiara uno ``step`` al secondo.
_LOCAL_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S")


def resolve_timezone_for_user_id(user_id: Optional[int]) -> ZoneInfo:
    """Il fuso di un **destinatario preciso**, non del lettore corrente.

    Serve dove il testo si scrive per qualcun altro: una notifica per i due
    giocatori di un match, un promemoria composto da uno scheduled task. Lì
    ``current_user`` o non c'è o è la persona sbagliata, e il risultato — un
    orario plausibile ma di un'altra città — non ha modo di farsi notare.

    Un id assente (riga non ancora persistita) vale il ripiego, e lo dice
    esplicitamente invece di passare per l'eccezione di ``session.get``.
    """
    if not user_id:
        return FALLBACK_TIMEZONE

    try:
        from models.base import db
        from models.user.models import User

        return resolve_timezone(db.session.get(User, user_id))
    except Exception:
        return FALLBACK_TIMEZONE


def to_utc_naive(local: datetime, tz: Optional[ZoneInfo] = None) -> datetime:
    """Un datetime nell'ora del lettore → naive UTC, come lo vuole il DB.

    Se arriva già con un fuso, quello vale: si converte e basta, senza
    sovrascrivere un'informazione che il chiamante aveva.
    """
    zone = tz or resolve_timezone()
    aware = local if local.tzinfo is not None else local.replace(tzinfo=zone)
    return aware.astimezone(UTC).replace(tzinfo=None)


def to_local_naive(utc_naive: datetime, tz: Optional[ZoneInfo] = None) -> datetime:
    """Il verso opposto: naive UTC dal DB → ora del lettore, sempre naive.

    Serve per **ripopolare** un ``<input type="datetime-local">``: il campo non
    accetta un fuso, quindi il valore va già portato nell'ora che l'utente si
    aspetta di rileggere. Senza questo passaggio il form di modifica mostra
    l'ora UTC, l'utente la conferma senza toccarla e l'appuntamento arretra di
    un fuso a ogni salvataggio — il bug di scrittura, moltiplicato per il
    numero di modifiche.
    """
    zone = tz or resolve_timezone()
    aware = utc_naive.replace(tzinfo=UTC) if utc_naive.tzinfo is None else utc_naive
    return aware.astimezone(zone).replace(tzinfo=None)


def format_local_input(value: Optional[datetime], tz: Optional[ZoneInfo] = None) -> str:
    """Un naive UTC nel formato che un ``datetime-local`` sa rileggere.

    Stringa vuota su ``None``: è quello che l'attributo ``value`` di un campo
    non compilato vuole, e non ``"None"``.
    """
    if value is None:
        return ""
    return to_local_naive(value, tz).strftime("%Y-%m-%dT%H:%M")


def parse_local_datetime(
    value: Optional[str], tz: Optional[ZoneInfo] = None
) -> Optional[datetime]:
    """Legge un ``datetime-local`` e lo restituisce naive **UTC**.

    Restituisce ``None`` su valore assente o malformato, invece di sollevare: a
    valle c'è sempre una validazione che sa dire «manca la data» in una lingua
    che l'utente capisce, ed è una risposta migliore del 500 di uno ``strptime``
    che esplode su un campo compilato male.
    """
    value = (value or "").strip()
    if not value:
        return None

    # Il browser può mandare la Z (UTC esplicito) se il valore è stato
    # normalizzato via JS: in quel caso il fuso ce l'ha già e va rispettato.
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    try:
        return to_utc_naive(datetime.fromisoformat(value), tz)
    except ValueError:
        pass

    for fmt in _LOCAL_FORMATS:
        try:
            return to_utc_naive(datetime.strptime(value, fmt), tz)
        except ValueError:
            continue
    return None


__all__ = [
    "parse_local_datetime",
    "to_utc_naive",
    "to_local_naive",
    "format_local_input",
    "resolve_timezone",
    "resolve_timezone_for_user_id",
    "is_valid_timezone",
    "FALLBACK_TIMEZONE",
    "DISPLAY_TIMEZONE",
]
