"""Una data che scavalca le gare successive diventa una proposta (ADR-075).

Le gare di un campionato restano in ordine di data (ADR-016). Fino al
2026-09-29 una data che superava la gara dopo veniva rifiutata, e il direttore
doveva spostare a mano le successive una alla volta, partendo dall'ultima.
Ora l'app propone di spostarle dello stesso numero di giorni («Spostare anche
le gare 8 e 9 di 10 giorni, al 27/10 e al 3/11?»). Il direttore accetta — ogni
gara spostata ha la sua voce e le sue notifiche —, rifiuta, e il cambio non si
salva, o torna al modulo e fa a mano.

Si spostano solo quelle che servono: la prima gara scavalcata, poi la
successiva se la prima, spostata, la scavalca a sua volta, e così via. Una
gara già avviata o conclusa non si sposta: in quel caso la proposta non c'è e
vale il rifiuto di sempre.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, List, Optional

from ..base import db
from ..transaction.manager import transactional

_ORA_PREDEFINITA = time(20, 0)


def _quando(giorno: date, ora: Optional[time]) -> datetime:
    return datetime.combine(giorno, ora or _ORA_PREDEFINITA)


@dataclass
class Spostamento:
    gara: Any
    da: date
    a: date


@dataclass
class PianoSpostamento:
    giorni: int
    spostamenti: List[Spostamento] = field(default_factory=list)
    #: Una gara da spostare è già avviata o conclusa: niente proposta.
    bloccata_da: Optional[Any] = None

    @property
    def numeri(self) -> List[int]:
        return [s.gara.number for s in self.spostamenti]


def piano(
    gara: Any, nuova_data: date, nuova_ora: Optional[time]
) -> Optional[PianoSpostamento]:
    """Le gare da spostare perché la nuova data non le scavalchi. `None`: niente."""
    from .campi_modificabili import e_avviata, e_chiusa
    from .models import Gara

    if not gara.campionato_id or gara.date is None or nuova_data is None:
        return None
    giorni = (nuova_data - gara.date).days
    limite = _quando(nuova_data, nuova_ora if nuova_ora is not None else gara.time)
    successive = (
        Gara.query.filter(
            Gara.campionato_id == gara.campionato_id,
            Gara.number > gara.number,
            Gara.deleted_at.is_(None),
        )
        .order_by(Gara.number)
        .all()
    )
    risultato = PianoSpostamento(giorni=giorni)
    for successiva in successive:
        if successiva.date is None or _quando(successiva.date, successiva.time) >= (
            limite
        ):
            break
        if giorni <= 0:
            # Stesso giorno, ora più tardi della gara dopo: non c'è un numero
            # di giorni da proporre, vale il rifiuto dell'ADR-016.
            return None
        if e_avviata(successiva) or e_chiusa(successiva):
            risultato.bloccata_da = successiva
            return risultato
        nuova = successiva.date + timedelta(days=giorni)
        risultato.spostamenti.append(
            Spostamento(gara=successiva, da=successiva.date, a=nuova)
        )
        limite = _quando(nuova, successiva.time)
    return risultato if risultato.spostamenti else None


@transactional(domain="competition")
def sposta(
    piano_: PianoSpostamento, autore: Any = None, motivo: Optional[str] = None
) -> None:
    """Sposta le successive, dall'ultima: così l'ordine regge a ogni passo."""
    from .services import GaraService

    for spostamento in reversed(piano_.spostamenti):
        GaraService.update_gara(
            spostamento.gara.id,
            autore=autore,
            motivo=motivo,
            date=spostamento.a,
        )
    db.session.flush()


__all__ = ["PianoSpostamento", "Spostamento", "piano", "sposta"]
