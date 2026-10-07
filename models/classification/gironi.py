"""La classifica di una gara a più gironi (ADR-076).

Due classifiche in una:

1. **dentro il girone**: ognuno si ordina con il sistema della gara (vittorie,
   triangoli o punti) e con la catena del livello — di turno o di gara — come
   in un girone unico. Lo scontro diretto vale fra i pari dello stesso
   girone, che si sono incontrati;
2. **della gara**, senza fase finale: prima tutti i primi dei gironi, ordinati
   fra loro, poi tutti i secondi, e così via. Fra gironi di taglia diversa il
   confronto si fa **per partita giocata**: vittorie, triangoli e punti
   divisi per le partite giocate, senza la X — la X non è una partita, e in
   un girone dispari ognuno ne ha una, quindi dentro il girone non sposta
   niente ma fra gironi regalerebbe una vittoria a chi sta in quello dispari.
   Lo scontro diretto fra gironi diversi non decide: non si sono incontrati, e
   il motore passa da solo al criterio dopo.

Il modulo è puro come `ordinamento.py`: chi lo chiama aggrega i numeri.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from .ordinamento import Concorrente, Criterio, Fascia, Scontro, Voce, ordina


@dataclass(frozen=True)
class Giocate:
    """Le partite giocate da un giocatore senza la X, e cosa ci ha fatto."""

    partite: int = 0
    vittorie: int = 0
    rack_vinti: int = 0
    differenza_rack: int = 0
    punti: int = 0


@dataclass(frozen=True)
class ClassificaAGironi:
    """L'esito: le fasce della gara, e per ognuno girone e posizione nel girone."""

    fasce: List[Fascia]
    girone: Dict[int, int]
    posizione_nel_girone: Dict[int, int]


def per_partita(c: Concorrente, giocate: Optional[Giocate]) -> Concorrente:
    """Il concorrente con i numeri divisi per le partite giocate.

    Chi non ha ancora giocato (solo la X, al primo turno) vale zero.
    """
    g = giocate or Giocate()
    if g.partite <= 0:
        return replace(c, vittorie=0, rack_vinti=0, differenza_rack=0, punti=0)
    return replace(
        c,
        vittorie=Fraction(g.vittorie, g.partite),
        rack_vinti=Fraction(g.rack_vinti, g.partite),
        differenza_rack=Fraction(g.differenza_rack, g.partite),
        punti=Fraction(g.punti, g.partite),
    )


def ordina_a_gironi(
    concorrenti: Iterable[Concorrente],
    girone: Mapping[int, int],
    giocate: Mapping[int, Giocate],
    principale: Criterio,
    catena: Sequence[Voce],
    *,
    scontri: Sequence[Scontro] = (),
    completa: bool = False,
) -> ClassificaAGironi:
    """Ordina una gara a più gironi.

    Args:
        concorrenti: tutti i giocatori, con i numeri di sempre (X compresa).
        girone: giocatore → girone. Chi manca non entra in classifica.
        giocate: giocatore → partite giocate senza la X, per il confronto fra
            gironi.
        principale, catena, scontri, completa: come in `ordinamento.ordina`.

    Returns:
        Le fasce della gara e, per ognuno, girone e posizione nel girone.
    """
    concorrenti_tutti = list(concorrenti)
    per_girone: Dict[int, List[Concorrente]] = {}
    for c in concorrenti_tutti:
        if c.player_id in girone:
            per_girone.setdefault(girone[c.player_id], []).append(c)

    posizione_nel_girone: Dict[int, int] = {}
    strati: Dict[int, List[Concorrente]] = {}
    for gruppo in sorted(per_girone):
        for fascia in ordina(
            per_girone[gruppo], principale, catena, scontri=scontri, completa=completa
        ):
            for c in fascia.giocatori:
                posizione_nel_girone[c.player_id] = fascia.posizione
                strati.setdefault(fascia.posizione, []).append(c)

    fasce: List[Fascia] = []
    posizione = 1
    # Chi non ha un girone (un dato storico o scritto a mano) non sparisce:
    # viene dopo tutti, ordinato fra i suoi.
    senza_girone = [c for c in concorrenti_tutti if c.player_id not in girone]
    for posto, giocatori in [(p, strati[p]) for p in sorted(strati)] + (
        [(None, senza_girone)] if senza_girone else []
    ):
        normalizzati = [per_partita(c, giocate.get(c.player_id)) for c in giocatori]
        for fascia in ordina(
            normalizzati,
            principale,
            catena,
            scontri=scontri,
            completa=completa,
            da_posizione=posizione,
        ):
            fasce.append(fascia)
            posizione += len(fascia.giocatori)

    # Le fasce portano i concorrenti normalizzati: chi legge vuole quelli veri.
    originali = {c.player_id: c for c in concorrenti_tutti}
    fasce = [
        Fascia(f.posizione, tuple(originali[c.player_id] for c in f.giocatori))
        for f in fasce
    ]
    return ClassificaAGironi(
        fasce=fasce,
        girone={pid: girone[pid] for pid in posizione_nel_girone},
        posizione_nel_girone=posizione_nel_girone,
    )


__all__ = ["ClassificaAGironi", "Giocate", "ordina_a_gironi", "per_partita"]
