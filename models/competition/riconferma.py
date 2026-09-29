"""La riconferma degli iscritti: «ci sei ancora?» (ADR-075, punto 7).

Scatta solo per ciò che può cambiare la decisione di esserci: la data, un
orario spostato di più di un'ora, la sala, una quota che sale. Regole di gioco
e formato arrivano con la notifica e basta; nome, tavoli, una quota che scende,
un piccolo ritocco d'orario restano nella storia.

Ogni iscrizione — e ogni invito ai playoff accettato — conserva le condizioni
che il giocatore ha accettato (`accepted_terms`): data, ora, sala, quota. La
riconferma serve solo se quelle di adesso ne differiscono oltre soglia, quindi
più modifiche danno **una sola** richiesta, e tornando ai valori accettati la
richiesta sparisce da sola. Non è una colonna di stato: si calcola.

Chi non riconferma resta iscritto, «da riconfermare»: nessun ritiro
automatico, decide il direttore. Il direttore può riconfermare al posto del
giocatore, e resta nella storia della gara. Non è un voto sulla modifica, che
resta del direttore: chiede solo «ci sei ancora?».
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional

from ..base import db
from ..transaction.manager import transactional

#: Uno spostamento d'orario fino a qui non chiede riconferma.
SPOSTAMENTO_PICCOLO = timedelta(hours=1)
#: I campi che contano, nell'ordine in cui si mostrano.
CAMPI = ("date", "time", "location", "entry_fee")


def _testo(valore: Any) -> str:
    from ..storia.service import serializza

    return serializza(valore)


def termini(date_: Any, time_: Any, location: Any, entry_fee: Any) -> Dict[str, str]:
    return {
        "date": _testo(date_),
        "time": _testo(time_),
        "location": _testo(location),
        "entry_fee": _testo(entry_fee),
    }


def termini_della_gara(gara: Any) -> Dict[str, str]:
    return termini(gara.date, gara.time, gara.location, gara.entry_fee)


def termini_della_config(config: Any) -> Dict[str, str]:
    """Le condizioni dei playoff prima che la finale esista."""
    quando = config.scheduled_date
    return termini(
        quando.date() if quando else None,
        quando.time() if quando else None,
        config.location,
        config.entry_fee,
    )


def _numero(testo: str) -> Optional[float]:
    try:
        return float(testo)
    except (TypeError, ValueError):
        return None


def _ora(testo: str) -> Optional[datetime]:
    try:
        return datetime.strptime(testo, "%H:%M")
    except (TypeError, ValueError):
        return None


def differenze(
    accettati: Optional[Dict[str, str]], attuali: Dict[str, str]
) -> List[str]:
    """I campi per cui serve riconfermare. Vuota: niente da chiedere."""
    if not accettati:
        return []
    campi = []
    if accettati.get("date", "") != attuali["date"]:
        campi.append("date")
    elif accettati.get("time", "") != attuali["time"]:
        prima, dopo = _ora(accettati.get("time", "")), _ora(attuali["time"])
        if prima is None or dopo is None or abs(dopo - prima) > SPOSTAMENTO_PICCOLO:
            campi.append("time")
    if accettati.get("location", "") != attuali["location"]:
        campi.append("location")
    # La quota chiede riconferma solo se sale: pagare meno non cambia la
    # decisione di esserci.
    vecchia = _numero(accettati.get("entry_fee", "")) or 0.0
    nuova = _numero(attuali["entry_fee"]) or 0.0
    if nuova > vecchia:
        campi.append("entry_fee")
    return campi


def leggi(testo: Optional[str]) -> Optional[Dict[str, str]]:
    if not testo:
        return None
    try:
        return json.loads(testo)
    except ValueError:
        return None


def scrivi(valori: Dict[str, str]) -> str:
    return json.dumps(valori, sort_keys=True)


def _gara_in_attesa(gara: Any) -> bool:
    """Si chiede finché la gara non è avviata: dopo, decide il direttore."""
    from .campi_modificabili import e_avviata, e_chiusa

    return not e_avviata(gara) and not e_chiusa(gara)


def da_riconfermare(inscription: Any) -> List[str]:
    """I campi per cui questo iscritto deve dire se c'è ancora."""
    if inscription.is_withdrawn or not _gara_in_attesa(inscription.gara):
        return []
    return differenze(
        leggi(inscription.accepted_terms), termini_della_gara(inscription.gara)
    )


def invito_da_riconfermare(qualification: Any) -> List[str]:
    """Lo stesso per un invito accettato, finché la finale non esiste.

    Creata la finale, chi ha accettato ci è iscritto: vale la sua iscrizione.
    """
    from ..playoff.models import QualificationStatus

    config = qualification.configuration
    if (
        qualification.status != QualificationStatus.CONFIRMED
        or config is None
        or config.gara is not None
    ):
        return []
    return differenze(leggi(qualification.accepted_terms), termini_della_config(config))


def valori_accettati(inscription: Any) -> Dict[str, str]:
    return leggi(inscription.accepted_terms) or {}


@transactional(domain="competition")
def riconferma(inscription_id: int, autore: Any = None) -> Any:
    """Il giocatore — o il direttore per lui — dice che c'è ancora."""
    from ..exceptions import ConflictError, NotFoundError
    from .models import Inscription

    inscription = db.session.get(Inscription, inscription_id)
    if inscription is None:
        raise NotFoundError("Iscrizione non trovata")
    if not _gara_in_attesa(inscription.gara):
        raise ConflictError("La gara è già avviata: decide il direttore.")
    campi = da_riconfermare(inscription)
    prima = valori_accettati(inscription)
    inscription.accepted_terms = scrivi(termini_della_gara(inscription.gara))
    per_conto = autore is not None and getattr(autore, "id", None) != (
        inscription.user_id
    )
    if per_conto and campi:
        from ..storia.models import SettingsChangeAction
        from ..storia.service import StoriaModificheService

        StoriaModificheService.registra(
            cambi={
                "giocatore": (None, inscription.user_id),
                **{
                    c: (prima.get(c), termini_della_gara(inscription.gara)[c])
                    for c in campi
                },
            },
            gara_id=inscription.gara_id,
            autore=autore,
            azione=SettingsChangeAction.RICONFERMA,
        )
    return inscription


@transactional(domain="playoff")
def riconferma_invito(qualification_id: int, autore: Any = None) -> Any:
    """Come `riconferma`, per un invito ai playoff accettato."""
    from ..exceptions import NotFoundError
    from ..playoff.models import PlayoffQualification

    qualification = db.session.get(PlayoffQualification, qualification_id)
    if qualification is None:
        raise NotFoundError("Invito non trovato")
    campi = invito_da_riconfermare(qualification)
    prima = leggi(qualification.accepted_terms) or {}
    attuali = termini_della_config(qualification.configuration)
    qualification.accepted_terms = scrivi(attuali)
    per_conto = autore is not None and getattr(autore, "id", None) != (
        qualification.user_id
    )
    if per_conto and campi:
        from ..storia.models import SettingsChangeAction, SettingsChangeSource
        from ..storia.service import StoriaModificheService

        StoriaModificheService.registra(
            cambi={
                "giocatore": (None, qualification.user_id),
                **{c: (prima.get(c), attuali[c]) for c in campi},
            },
            playoff_config_id=qualification.configuration_id,
            autore=autore,
            provenienza=SettingsChangeSource.PLAYOFF,
            azione=SettingsChangeAction.RICONFERMA,
        )
    return qualification


def _alla_nascita(mapper: Any, connection: Any, target: Any) -> None:
    """Un'iscrizione nasce con le condizioni della gara di quel momento.

    Un ascoltatore e non una riga in `inscribe_user`: le iscrizioni nascono da
    più strade (iscrizione, direttore, playoff, lista d'attesa, test), e tutte
    devono ricordare cosa è stato accettato.
    """
    if target.accepted_terms or not target.gara_id:
        return
    riga = connection.execute(
        db.text("SELECT date, time, location, entry_fee FROM gara WHERE id = :id"),
        {"id": target.gara_id},
    ).first()
    if riga is None:
        return
    data, ora, sala, quota = riga
    target.accepted_terms = scrivi(
        {
            "date": data if isinstance(data, str) else _testo(data),
            "time": _normalizza_ora(ora),
            "location": sala or "",
            "entry_fee": _testo(quota),
        }
    )


def _normalizza_ora(ora: Any) -> str:
    """SQLite restituisce l'ora come testo `HH:MM:SS.ffffff`."""
    if ora is None:
        return ""
    if isinstance(ora, time):
        return ora.strftime("%H:%M")
    return str(ora)[:5]


def registra_ascoltatore() -> None:
    from sqlalchemy import event

    from .models import Inscription

    if not event.contains(Inscription, "before_insert", _alla_nascita):
        event.listen(Inscription, "before_insert", _alla_nascita)


__all__ = [
    "CAMPI",
    "differenze",
    "da_riconfermare",
    "invito_da_riconfermare",
    "riconferma",
    "riconferma_invito",
    "termini_della_gara",
    "termini_della_config",
]
