"""La classifica finale di una gara a gironi con il tabellone (piano gironi, PR 5).

La gara ha due fasi: i gironi, poi il tabellone fra i primi `K` di ogni
girone. La classifica finale le compone così (SPECIFICHE.md, «La classifica a
gironi», nota del 2026-10-11):

1. **chi ha giocato il tabellone**, nell'ordine in cui ne è uscito (le bande
   di `bracket_standings.elimination_bands`): 1° e 2° dalla finale, 3° e 4°
   dalla finalina; senza finalina i due semifinalisti sconfitti sono **terzi
   a pari merito**. Chi esce allo stesso turno prima della semifinale — i
   quarti, gli ottavi — si ordina per **piazzamento nel girone**, e a pari
   piazzamento per partita giocata: è l'ordine della classifica a gironi;
2. **i non qualificati**, nell'ordine della classifica a gironi.

Mentre il tabellone si gioca, chi è ancora in corsa sta in cima, ordinato
come la classifica a gironi: è la classifica provvisoria del turno.

Il modulo è puro come `gironi.py`: chi lo chiama porta le bande del tabellone
e la classifica a gironi già fatta, in fasce.
"""

from __future__ import annotations

from typing import AbstractSet, Dict, List, Sequence, Tuple

#: Una fascia: (posizione, giocatori a pari merito).
FasciaDiId = Tuple[int, List[int]]


def classifica_con_tabellone(
    bande: Sequence[Sequence[int]],
    fasce_dei_gironi: Sequence[Tuple[int, Sequence[int]]],
    *,
    pari_merito: AbstractSet[int] = frozenset(),
) -> List[FasciaDiId]:
    """Compone la classifica finale: prima il tabellone, poi gli altri.

    Args:
        bande: le bande del tabellone, dalla migliore (chi è ancora in corsa,
            poi il finalista, …).
        fasce_dei_gironi: la classifica a gironi, in fasce ``(posizione,
            giocatori)``: dà il piazzamento di tutti.
        pari_merito: i giocatori che restano a pari merito anche se il loro
            piazzamento nel girone è diverso — i due semifinalisti sconfitti,
            quando non c'è la finalina.

    Returns:
        Le fasce della gara, con le posizioni «a competizione» (1, 2, 3, 3, 5).
    """
    posto: Dict[int, int] = {}
    for posizione, giocatori in fasce_dei_gironi:
        for pid in giocatori:
            posto[pid] = posizione
    fondo = max(posto.values(), default=0) + 1

    fasce: List[FasciaDiId] = []
    posizione = 1

    def aggiungi(giocatori: List[int]) -> None:
        nonlocal posizione
        fasce.append((posizione, giocatori))
        posizione += len(giocatori)

    qualificati = set()
    for banda in bande:
        membri = [pid for pid in banda if pid not in qualificati]
        qualificati.update(membri)
        if not membri:
            continue
        if len(membri) > 1 and set(membri) <= set(pari_merito):
            aggiungi(sorted(membri, key=lambda p: (posto.get(p, fondo), p)))
            continue
        per_posto: Dict[int, List[int]] = {}
        for pid in membri:
            per_posto.setdefault(posto.get(pid, fondo), []).append(pid)
        for chiave in sorted(per_posto):
            aggiungi(sorted(per_posto[chiave]))

    for _posizione, giocatori in fasce_dei_gironi:
        altri = [pid for pid in giocatori if pid not in qualificati]
        if altri:
            aggiungi(list(altri))
    return fasce


__all__ = ["FasciaDiId", "classifica_con_tabellone"]
