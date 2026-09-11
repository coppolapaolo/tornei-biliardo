"""Il campionato come lo vede una persona precisa.

Stessa regola delle gare (`gara_cards.py`, regola 1 del 2026-09-10): la
tessera parte da quella dell'ospite — testa della classifica generale e
prossime gare — e ci aggiunge i fatti di chi guarda. Sono due: è iscritto a una
sua gara (allora la classifica mostra anche la sua riga, sotto i primi tre se
non c'è già), lo dirige (allora il pulsante è «Gestione»). Sui conclusi le
stesse due cose diventano «Hai giocato» e «Hai diretto».

Prima la tessera in dashboard mostrava **meno** di quella dell'ospite: niente
classifica, niente prossime gare, solo la data e tre spie di configurazione.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import Any, Dict, Iterable, List, Optional

from models.campionato.models import Campionato
from models.competition.models import Gara, Inscription
from models.status_enum import ClassificationSystem, TournamentStatus

from .gara_cards import FINESTRA_CONCLUSE

#: Quante righe di classifica sulla tessera. Tre bastano a capire chi
#: comanda; l'elenco intero sta nella pagina del campionato.
TESTA_CLASSIFICA = 3

#: Quante prossime gare sulla tessera.
PROSSIME_MOSTRATE = 2

#: Gli stati in cui un campionato è finito, per chi lo guarda dalla dashboard.
#: `AWAITING_PLAYOFF` conta come concluso: le gare sono tutte giocate e la
#: classifica non cambia più, resta solo la finale.
STATI_CONCLUSI: frozenset[str] = frozenset(
    {TournamentStatus.COMPLETED.value, TournamentStatus.AWAITING_PLAYOFF.value}
)


@dataclass(frozen=True)
class RigaClassificaVM:
    posizione: int
    username: str
    #: Vittorie o triangoli, a seconda del sistema di classifica (ADR-047).
    valore: int
    is_me: bool = False


@dataclass
class CampionatoCardVM:
    campionato: Campionato
    name: str
    can_manage: bool = False
    can_view_details: bool = True
    next_prova_date: Optional[date_cls] = None
    #: Iscritto ad almeno una gara del campionato: è un mio campionato.
    is_inscribed: bool = False
    #: La testa della classifica generale; la riempie `enrich_with_classifica`.
    testa: List[RigaClassificaVM] = field(default_factory=list)
    #: La riga di chi guarda, se non è già fra le prime. `None` se non è in
    #: classifica (o se non c'è ancora una classifica).
    mia_riga: Optional[RigaClassificaVM] = None
    #: Le prossime gare in calendario, poche.
    prossime: List[Gara] = field(default_factory=list)

    @property
    def id(self) -> int:
        return self.campionato.id

    @property
    def status(self) -> str:
        return self.campionato.get_status()

    @property
    def is_concluso(self) -> bool:
        return self.status in STATI_CONCLUSI

    @property
    def is_rack(self) -> bool:
        """Il criterio è il sistema di classifica, non il tipo di campionato:
        mostrare la differenza triangoli come un totale è la issue #89."""
        return self.campionato.classification_system == ClassificationSystem.RACK

    @property
    def hai_giocato(self) -> bool:
        return self.is_concluso and self.is_inscribed

    @property
    def hai_diretto(self) -> bool:
        return self.is_concluso and self.can_manage

    @property
    def ultima_data(self) -> Optional[date_cls]:
        """La data dell'ultima gara: è a questa che si ancora la finestra
        delle concluse, perché un campionato non ha una data di chiusura."""
        date = [g.date for g in (self.campionato.gare or []) if g.date]
        return max(date) if date else None

    @property
    def gare_giocate(self) -> int:
        from models.status_enum import GaraStatus

        return sum(
            1
            for g in (self.campionato.gare or [])
            if g.status == GaraStatus.COMPLETED.value
        )


@dataclass
class ElenchiCampionati:
    attivi: List[CampionatoCardVM] = field(default_factory=list)
    #: L'ultimo concluso più quelli dell'ultimo mese (`finestra_conclusi`).
    conclusi: List[CampionatoCardVM] = field(default_factory=list)
    conclusi_totali: int = 0


def finestra_conclusi(
    cards: Iterable[CampionatoCardVM], oggi: Optional[date_cls] = None
) -> List[CampionatoCardVM]:
    """L'ultimo concluso, sempre, più quelli dell'ultimo mese: la stessa
    regola delle gare, misurata sulla data dell'ultima gara."""
    oggi = oggi or date_cls.today()
    ordinati = sorted(
        (c for c in cards if c.is_concluso),
        key=lambda c: (
            c.ultima_data is None,
            -(c.ultima_data.toordinal() if c.ultima_data else 0),
        ),
    )
    if not ordinati:
        return []
    soglia = oggi - FINESTRA_CONCLUSE
    ultimo, altri = ordinati[0], ordinati[1:]
    return [ultimo] + [
        c for c in altri if c.ultima_data is not None and c.ultima_data >= soglia
    ]


def build_campionato_cards(
    unified_items: Iterable[Any],
    my_inscriptions: Optional[Iterable[Inscription]],
    *,
    oggi: Optional[date_cls] = None,
) -> ElenchiCampionati:
    """I campionati della dashboard, attivi e conclusi, con i fatti di chi
    guarda. Non tocca il database: la classifica arriva dopo, con
    `enrich_with_classifica`."""
    miei_campionati = {
        ins.gara.campionato_id
        for ins in (my_inscriptions or [])
        if ins.gara is not None and not ins.is_withdrawn and ins.gara.campionato_id
    }
    elenchi = ElenchiCampionati()
    tutti_i_conclusi: List[CampionatoCardVM] = []
    for item in unified_items or []:
        if item.type != "campionato":
            continue
        card = CampionatoCardVM(
            campionato=item.entity,
            name=item.name,
            can_manage=item.can_manage,
            can_view_details=item.can_view_details,
            next_prova_date=item.next_prova_date,
            is_inscribed=item.id in miei_campionati,
            prossime=_prossime(item.entity, oggi),
        )
        if card.is_concluso:
            tutti_i_conclusi.append(card)
        else:
            elenchi.attivi.append(card)
    elenchi.conclusi = finestra_conclusi(tutti_i_conclusi, oggi)
    elenchi.conclusi_totali = len(tutti_i_conclusi)
    return elenchi


def _prossime(campionato: Campionato, oggi: Optional[date_cls]) -> List[Gara]:
    oggi = oggi or date_cls.today()
    future = [g for g in (campionato.gare or []) if g.date and g.date >= oggi]
    future.sort(key=lambda g: (g.date, g.number or 0))
    return future[:PROSSIME_MOSTRATE]


def enrich_with_classifica(cards: Iterable[CampionatoCardVM], user_id: int) -> None:
    """La testa della classifica generale e la riga di chi guarda.

    Una chiamata a `calculate_general_classification` per campionato: è la
    stessa che fa la home dell'ospite, e qui i campionati sono pochi — gli
    attivi più i conclusi nella finestra.
    """
    from models.campionato.tournament_service import TournamentService

    service = TournamentService()
    for card in cards:
        classifica = service.calculate_general_classification(card.campionato.id)
        righe: List[RigaClassificaVM] = []
        mia: Optional[RigaClassificaVM] = None
        for posizione, dati in classifica:
            riga = _riga(posizione, dati, card.is_rack, user_id)
            if riga.is_me:
                mia = riga
            righe.append(riga)
        card.testa = righe[:TESTA_CLASSIFICA]
        # La mia riga si aggiunge sotto solo se non è già in testa: la
        # regola è «la tessera dell'ospite più il fatto mio», non due volte.
        card.mia_riga = mia if mia is not None and mia not in card.testa else None


def _riga(
    posizione: int, dati: Dict[str, Any], is_rack: bool, user_id: int
) -> RigaClassificaVM:
    valore = dati.get("total_racks_won" if is_rack else "total_matches_won", 0) or 0
    return RigaClassificaVM(
        posizione=posizione,
        username=str(dati.get("username", "")),
        valore=int(valore),
        is_me=dati.get("user_id") == user_id,
    )


__all__ = [
    "CampionatoCardVM",
    "ElenchiCampionati",
    "PROSSIME_MOSTRATE",
    "RigaClassificaVM",
    "STATI_CONCLUSI",
    "TESTA_CLASSIFICA",
    "build_campionato_cards",
    "enrich_with_classifica",
    "finestra_conclusi",
]
