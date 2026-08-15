"""Il verso mancante della conversione di fuso: input locale → naive UTC.

Il progetto ha sempre avuto solo **metà** della conversione. In lettura
``utils/jinja.py`` fa il lavoro giusto: prende il naive dal DB, lo interpreta
come UTC e lo mostra in ora italiana. In scrittura invece non c'era nessuno: il
valore di un ``<input type="datetime-local">``, che il browser manda in **ora
locale**, veniva salvato così com'era.

Il risultato è un errore silenzioso e sistematico: chi digita ``21:00`` si vede
poi mostrare ``23:00``, perché il filtro di lettura somma il fuso a un valore
che il fuso non l'ha mai perso. Nessuna eccezione, nessun log — solo un
appuntamento all'ora sbagliata.

Questo modulo chiude il cerchio, e vive qui invece che dentro una route perché
i punti che leggono un ``datetime-local`` sono più d'uno.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

#: Il fuso in cui gli utenti digitano. Non è configurabile per utente e non
#: finge di esserlo: la piattaforma è italiana, e ``utils/jinja.py`` mostra da
#: sempre in ``Europe/Rome``. Il giorno in cui servisse per-utente, si cambia
#: qui e nel filtro di lettura — che sono i due soli posti che lo sanno.
DISPLAY_TIMEZONE = ZoneInfo("Europe/Rome")
UTC = ZoneInfo("UTC")

#: I formati che un ``<input type="datetime-local">`` produce: senza secondi di
#: norma, con i secondi se il campo dichiara uno ``step`` al secondo.
_LOCAL_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S")


def to_utc_naive(local: datetime) -> datetime:
    """Un datetime in ora italiana → naive UTC, come lo vuole il DB.

    Se arriva già con un fuso, quello vale: si converte e basta, senza
    sovrascrivere un'informazione che il chiamante aveva.
    """
    aware = (
        local if local.tzinfo is not None else local.replace(tzinfo=DISPLAY_TIMEZONE)
    )
    return aware.astimezone(UTC).replace(tzinfo=None)


def to_local_naive(utc_naive: datetime) -> datetime:
    """Il verso opposto: naive UTC dal DB → ora italiana, sempre naive.

    Serve per **ripopolare** un ``<input type="datetime-local">``: il campo non
    accetta un fuso, quindi il valore va già portato nell'ora che l'utente si
    aspetta di rileggere. Senza questo passaggio il form di modifica mostra
    l'ora UTC, l'utente la conferma senza toccarla e l'appuntamento arretra di
    un'ora a ogni salvataggio — il bug di scrittura, moltiplicato per il numero
    di modifiche.
    """
    aware = utc_naive.replace(tzinfo=UTC) if utc_naive.tzinfo is None else utc_naive
    return aware.astimezone(DISPLAY_TIMEZONE).replace(tzinfo=None)


def format_local_input(value: Optional[datetime]) -> str:
    """Un naive UTC nel formato che un ``datetime-local`` sa rileggere.

    Stringa vuota su ``None``: è quello che l'attributo ``value`` di un campo
    non compilato vuole, e non ``"None"``.
    """
    if value is None:
        return ""
    return to_local_naive(value).strftime("%Y-%m-%dT%H:%M")


def parse_local_datetime(value: Optional[str]) -> Optional[datetime]:
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
        return to_utc_naive(datetime.fromisoformat(value))
    except ValueError:
        pass

    for fmt in _LOCAL_FORMATS:
        try:
            return to_utc_naive(datetime.strptime(value, fmt))
        except ValueError:
            continue
    return None


__all__ = [
    "parse_local_datetime",
    "to_utc_naive",
    "to_local_naive",
    "format_local_input",
    "DISPLAY_TIMEZONE",
]
