"""Il limite di tempo di una partita e il suo conto alla rovescia (ADR-077).

Una partita ha **sempre** una distanza: il limite di tempo non la sostituisce,
le si affianca. Tre fatti, tre posti:

* **quanti minuti**: una regola, fissata sulla partita quando nasce come le
  altre (`Match.time_limit_minutes`, ADR-075);
* **quando è partito il conto alla rovescia**: un fatto, scritto una volta
  sola — all'acchito (`ScoringService.register_lag`) oppure, se apre il primo
  giocatore, con «Avvia partita» (`MatchService.avvia_partita`);
* **lo scadere**: si calcola, non si scrive. È **solo visivo** — il timer dei
  giocatori, la card del direttore che sale fra quelle da guardare — e non
  chiude niente: a tempo scaduto è il direttore che decide se interrompere.

Il server dà inizio e durata; il tempo che resta lo calcolano le pagine
(`static/js/conto_alla_rovescia.js`), che così restano allineate fra loro
senza chiedere niente a nessuno.

In questa versione il limite non si applica alle partite a set, al trio e
alla X: è la forma «due giocatori, un set» quella per cui la regola è
pensata. Il valore resta fissato anche lì — è la regola della gara in quel
momento — ma `limite_minuti` risponde None.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from models.status_enum import MatchStatus


def forma_esclusa(match: Any) -> bool:
    """Partite a set, trio e X: fuori dal limite di tempo in questa versione."""
    return bool(
        getattr(match, "is_bye", False)
        or getattr(match, "is_trio", False)
        or getattr(match, "is_multi_set", False)
    )


def limite_minuti(match: Any) -> Optional[int]:
    """I minuti a disposizione della partita, o None se non ha un limite."""
    if forma_esclusa(match):
        return None
    minuti = getattr(match, "time_limit_minutes", None)
    return minuti if minuti and minuti > 0 else None


def ha_limite(match: Any) -> bool:
    return limite_minuti(match) is not None


def scadenza(match: Any) -> Optional[datetime]:
    """Quando scade il tempo; None se non c'è limite o non è ancora partito."""
    minuti = limite_minuti(match)
    inizio = getattr(match, "timer_started_at", None)
    if minuti is None or inizio is None:
        return None
    return inizio + timedelta(minutes=minuti)


def secondi_restanti(match: Any, adesso: Optional[datetime] = None) -> Optional[int]:
    """Secondi alla scadenza: negativi oltre lo scadere, None senza timer."""
    fine = scadenza(match)
    if fine is None:
        return None
    if adesso is None:
        from models.base import utc_now

        adesso = utc_now()
    return int((fine - adesso).total_seconds())


def tempo_scaduto(match: Any, adesso: Optional[datetime] = None) -> bool:
    """Il tempo è finito su una partita ancora da chiudere.

    Una partita chiusa non è «scaduta»: è finita, comunque sia andata. Ed è
    solo un'informazione — nessuno stato cambia per questo.
    """
    if MatchStatus.is_finished(getattr(match, "status", None)):
        return False
    restanti = secondi_restanti(match, adesso)
    return restanti is not None and restanti <= 0


def avvia_conto_alla_rovescia(match: Any, adesso: Optional[datetime] = None) -> bool:
    """Fa partire il conto alla rovescia, se c'è un limite e non è già partito.

    Una volta sola: premere di nuovo, o un acchito registrato dopo un «Avvia»
    del direttore, non sposta l'inizio — sposterebbe la scadenza a chi sta
    già giocando. Restituisce True se l'ha scritto adesso.
    """
    if not ha_limite(match) or getattr(match, "timer_started_at", None) is not None:
        return False
    if MatchStatus.is_finished(getattr(match, "status", None)):
        return False
    if adesso is None:
        from models.base import utc_now

        adesso = utc_now()
    match.timer_started_at = adesso
    return True


def vista(match: Any, adesso: Optional[datetime] = None) -> Optional[dict]:
    """Ciò che serve a disegnare il timer, o None se la partita non ha limite.

    `adesso` viaggia nella pagina: il JavaScript lo confronta con l'orologio
    del dispositivo e corregge lo scarto. Il testo iniziale è lo stesso che il
    JavaScript scriverà al primo giro, così la pagina non salta.
    """
    minuti = limite_minuti(match)
    if minuti is None:
        return None
    if adesso is None:
        from models.base import utc_now

        adesso = utc_now()
    inizio = getattr(match, "timer_started_at", None)
    if inizio is None:
        return {
            "minuti": minuti,
            "inizio": None,
            "adesso": adesso.isoformat() + "Z",
            "restanti": minuti * 60,
            "scaduto": False,
        }
    restanti = secondi_restanti(match, adesso) or 0
    return {
        "minuti": minuti,
        "inizio": inizio.isoformat() + "Z",
        "adesso": adesso.isoformat() + "Z",
        "restanti": restanti,
        "scaduto": tempo_scaduto(match, adesso),
    }


def evento_live(match: Any, autore_id: Optional[int] = None) -> None:
    """La partenza arriva ad avversario, direttore e schermo sala (ADR-057).

    Dentro la transazione del servizio: l'evento si salva col fatto, o non si
    salva affatto.
    """
    from routes.sse import emit_gara_event, emit_match_event

    dati = {
        "match_id": match.id,
        "timer_started_at": (
            match.timer_started_at.isoformat() + "Z" if match.timer_started_at else None
        ),
        "time_limit_minutes": match.time_limit_minutes,
        "autore": autore_id,
    }
    emit_match_event(match.id, "timer_started", dati)
    if match.gara_id:
        emit_gara_event(match.gara_id, "match_updated", dati)


__all__ = [
    "forma_esclusa",
    "limite_minuti",
    "ha_limite",
    "scadenza",
    "secondi_restanti",
    "tempo_scaduto",
    "avvia_conto_alla_rovescia",
    "vista",
    "evento_live",
]
