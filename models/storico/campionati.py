"""La spia della partecipazione sull'elenco dei campionati.

`/campionatos` è lo storico dei campionati (regola 2 del 2026-09-10): mostra
tutti i campionati di tutti, e chi guarda deve riconoscere i suoi. Le parole
sono quelle della tessera in dashboard — «Iscritto» e «Dirigi» finché il
campionato è aperto, «Hai giocato» e «Hai diretto» quando è concluso — così
la stessa cosa si chiama allo stesso modo nelle due pagine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Set

from models.base import db
from models.campionato.models import Campionato
from models.competition.models import Gara, Inscription
from models.status_enum import EntityType, TournamentStatus
from models.user.models import DirectorAssignment


@dataclass(frozen=True)
class SpiaPartecipazione:
    giocato: bool = False
    diretto: bool = False
    concluso: bool = False

    @property
    def vuota(self) -> bool:
        return not (self.giocato or self.diretto)


def spie_partecipazione(
    campionati: Iterable[Campionato], user_id: Optional[int]
) -> Dict[int, SpiaPartecipazione]:
    """Per ogni campionato, i fatti di chi guarda. Due query in tutto.

    «Giocato» è un'iscrizione non ritirata a una gara del campionato;
    «diretto» è l'assegnazione al campionato, la stessa che in dashboard
    dà «Dirigi». L'ospite non ha fatti: la mappa è vuota.
    """
    elenco = list(campionati)
    if user_id is None or not elenco:
        return {}
    ids = [c.id for c in elenco]
    giocati: Set[int] = {
        cid
        for (cid,) in db.session.query(Gara.campionato_id)
        .join(Inscription, Inscription.gara_id == Gara.id)
        .filter(
            Inscription.user_id == user_id,
            Inscription.is_withdrawn.is_(False),
            Gara.campionato_id.in_(ids),
        )
        .distinct()
        .all()
    }
    diretti: Set[int] = {
        eid
        for (eid,) in db.session.query(DirectorAssignment.entity_id)
        .filter(
            DirectorAssignment.user_id == user_id,
            DirectorAssignment.entity_type == EntityType.CAMPIONATO.value,
            DirectorAssignment.entity_id.in_(ids),
        )
        .all()
    }
    return {
        c.id: SpiaPartecipazione(
            giocato=c.id in giocati,
            diretto=c.id in diretti,
            concluso=c.get_status() == TournamentStatus.COMPLETED.value,
        )
        for c in elenco
    }
