"""La classifica a gironi di una gara vera: i numeri dal database (ADR-076).

Il calcolo sta in `gironi.py`, puro. Qui si leggono i giocatori di una gara
(da una classifica già aggregata o dalle righe di un turno), le partite
giocate senza la X e gli scontri, e si chiama `ordina_a_gironi`. Lo usano la
classifica di turno (`StrategyBasedClassificationService`) e quella di gara
(`SpareggioService._fasce`): una risposta sola per entrambe.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from .catene import scontri_delle_gare, sistema_della_gara, usa_scontri
from .gironi import ClassificaAGironi, Giocate, ordina_a_gironi
from .ordinamento import (
    Catena,
    Concorrente,
    chiave_di_sorteggio,
    criterio_principale,
    seme_della_gara,
)
from .score_aggregator import ScoreAggregator


def giocate_senza_x(gara_id: int, fino_al_turno: int) -> Dict[int, Giocate]:
    """Le partite giocate da ognuno fino a quel turno, senza la X."""
    return {
        s.player_id: Giocate(
            partite=s.matches_won + s.matches_lost + s.matches_drawn,
            vittorie=s.matches_won,
            rack_vinti=s.racks_won,
            differenza_rack=s.rack_difference,
            punti=s.points,
        )
        for s in ScoreAggregator().aggregate_round_scores(
            gara_id, fino_al_turno, escludi_x=True
        )
    }


def concorrente(
    gara: Any,
    player_id: int,
    *,
    vittorie: int = 0,
    rack_vinti: int = 0,
    differenza_rack: int = 0,
    punti: int = 0,
    ssr: Optional[int] = None,
    posizione_precedente: Optional[int] = None,
) -> Concorrente:
    return Concorrente(
        player_id=player_id,
        vittorie=vittorie,
        rack_vinti=rack_vinti,
        differenza_rack=differenza_rack,
        punti=punti,
        ssr=ssr,
        posizione_precedente=posizione_precedente,
        sorteggio=chiave_di_sorteggio(seme_della_gara(gara), player_id),
    )


def classifica_a_gironi(
    gara: Any,
    concorrenti: Iterable[Concorrente],
    girone: Mapping[int, int],
    catena: Catena,
    fino_al_turno: int,
    *,
    completa: bool,
) -> ClassificaAGironi:
    """La classifica della gara a gironi, con la catena data."""
    scontri = scontri_delle_gare([gara.id], fino_al_turno) if usa_scontri(catena) else ()
    return ordina_a_gironi(
        concorrenti,
        girone,
        giocate_senza_x(gara.id, fino_al_turno),
        criterio_principale(sistema_della_gara(gara)),
        catena,
        scontri=scontri,
        completa=completa,
    )


__all__ = ["classifica_a_gironi", "concorrente", "giocate_senza_x"]
