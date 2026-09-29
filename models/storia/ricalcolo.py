"""Le correzioni che ricalcolano la classifica a gare già finite (ADR-075).

A gara finita **come si è giocato** non si tocca; si corregge solo **quanto
conta** la gara nel campionato: il suo peso, i punti per posizione del
campionato, il peso della finale. Una correzione così cambia una classifica
che i giocatori hanno già visto, quindi la pagina lo dice: il vecchio peso
barrato nell'elenco delle gare, e sopra la classifica una riga per ogni
ricalcolo, con chi e perché.

Le voci si riconoscono dall'azione `ricalcolo`, scritta da chi fa la
correzione: `GaraService.update_gara`, `TournamentService.update_campionato`,
`PlayoffService.update_scoring`.
"""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import or_

from ..base import db
from .models import SettingsChange, SettingsChangeAction


def ricalcola_campionato(campionato_id: int | None) -> None:
    """La classifica generale e la sua copia nelle righe `Classification`.

    La pagina calcola al volo (ADR-073); le righe sono la copia che leggono
    profilo, export e inviti: si riscrivono subito, invece di aspettare il
    prossimo risultato.
    """
    if not campionato_id:
        return
    from ..classification.campionato_classification import ClassificationService

    ClassificationService.invalidate_campionato_cache(campionato_id)
    ClassificationService.update_campionato_classification(campionato_id)


def gara_finita_nel_campionato(campionato: Any) -> bool:
    """Almeno una gara del campionato è conclusa: la classifica esiste già."""
    from ..status_enum import GaraStatus

    return any(
        not g.is_deleted and g.status == GaraStatus.COMPLETED.value
        for g in campionato.gare
    )


def voci_di_ricalcolo(campionato: Any) -> List[SettingsChange]:
    """Le correzioni che hanno ricalcolato la classifica, dalla più recente."""
    from ..playoff.models import PlayoffConfiguration

    gare = [g.id for g in campionato.gare]
    configurazioni = [
        c.id for c in PlayoffConfiguration.query.filter_by(campionato_id=campionato.id)
    ]
    condizioni = [SettingsChange.campionato_id == campionato.id]
    if gare:
        condizioni.append(SettingsChange.gara_id.in_(gare))
    if configurazioni:
        condizioni.append(SettingsChange.playoff_config_id.in_(configurazioni))
    return (
        SettingsChange.query.filter(
            SettingsChange.action == SettingsChangeAction.RICALCOLO,
            or_(*condizioni),
        )
        .order_by(SettingsChange.created_at.desc(), SettingsChange.id.desc())
        .all()
    )


def pesi_corretti(voci: List[SettingsChange]) -> Dict[int, str]:
    """Per ogni gara il cui peso è stato corretto a gara finita, il peso di prima.

    È il valore prima dell'**ultima** correzione: quello che la classifica
    usava fino a lì. `voci` sono quelle di `voci_di_ricalcolo`.
    """
    prima: Dict[int, str] = {}
    for voce in voci:  # dalla più recente
        if voce.gara_id is None or voce.gara_id in prima:
            continue
        for riga in voce.fields:
            if riga.field == "weight":
                prima[voce.gara_id] = riga.old_value or "1"
    return prima


class Ricalcoli:
    """Quello che la pagina del campionato mostra dei ricalcoli."""

    def __init__(self, campionato: Any):
        # Solo un campionato vero ha una storia: un oggetto di prova passato
        # al template, senza id, non ne ha.
        persistito = campionato is not None and getattr(campionato, "id", None)
        self.voci = voci_di_ricalcolo(campionato) if persistito else []
        self.pesi_prima = pesi_corretti(self.voci)


def ricalcoli_del_campionato(campionato: Any) -> Ricalcoli:
    """Per i template: una lettura sola, con voci e pesi di prima."""
    return Ricalcoli(campionato)


def gara_della_voce(voce: SettingsChange) -> Any:
    from ..competition.models import Gara

    return db.session.get(Gara, voce.gara_id) if voce.gara_id else None


__all__ = [
    "ricalcola_campionato",
    "gara_finita_nel_campionato",
    "voci_di_ricalcolo",
    "pesi_corretti",
    "gara_della_voce",
    "ricalcoli_del_campionato",
]
