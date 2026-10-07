"""Il girone all'italiana a più gironi: le regole, senza database (ADR-076).

Un girone all'italiana può dividere gli iscritti in **gironi** che si giocano
in parallelo: ognuno incontra tutti gli altri del suo girone, una volta.

Tre domande, tre risposte di questo modulo:

1. **Quanti gironi** (`gironi_possibili`, `proposta_di_gironi`,
   `verifica_numero_di_gironi`). La gara dice un tetto («fino a N»,
   `Gara.max_groups`); all'avvio il direttore fissa il numero esatto, da 1 al
   tetto, con almeno `MINIMO_PER_GIRONE` giocatori per girone. La proposta è
   un girone ogni sei iscritti, arrotondato per eccesso, dentro quei limiti.
2. **Chi va in quale girone** (`ordine_di_composizione`, `componi_gironi`).
   Gli iscritti si mettono in fila secondo la **composizione** scelta —
   sorteggio, ELO o categoria — e si distribuiscono uno per girone a turno,
   andata e ritorno (`group_phase.distribute_into_groups`), separando i
   compagni di squadra quando la gara lo chiede (ADR-039). I primi della fila
   finiscono in gironi diversi.
3. **Quanti turni** (`turni_dei_gironi`): quelli del girone più numeroso. Un
   girone che ha finito il suo calendario non gioca più.

Nell'interfaccia l'opzione si chiama «Composizione dei gironi»: non
«abbinamenti», che nell'app vuol dire chi gioca contro chi.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence

from .bracket import group_player_counts
from .group_phase import distribute_into_groups

#: Il minimo di giocatori in un girone: con due sarebbe una partita sola.
MINIMO_PER_GIRONE = 3

#: Il tetto più alto che si può scrivere su una gara.
MASSIMO_DI_GIRONI = 8

#: La proposta automatica: un girone ogni sei iscritti, per eccesso.
GIOCATORI_PER_GIRONE_PROPOSTI = 6


class ComposizioneGironi(str, Enum):
    """L'ordine in cui gli iscritti si mettono in fila prima di distribuirli."""

    SORTEGGIO = "sorteggio"
    ELO = "elo"
    CATEGORIA = "categoria"

    def __str__(self) -> str:  # pragma: no cover – banale
        return str(self.value)

    @classmethod
    def resolve(cls, valore: object) -> "ComposizioneGironi":
        """Il valore salvato, o il sorteggio se manca o non si riconosce."""
        try:
            return cls(str(valore))
        except ValueError:
            return cls.SORTEGGIO


def nome_del_girone(indice: int) -> str:
    """Il nome di un girone: A, B, C… (l'indice parte da 0)."""
    if indice < 0:
        raise ValueError(f"indice di girone negativo: {indice}")
    nome = ""
    numero = indice + 1
    while numero:
        numero, resto = divmod(numero - 1, 26)
        nome = chr(ord("A") + resto) + nome
    return nome


def tetto_di_gironi(max_groups: Optional[int]) -> int:
    """Il tetto della gara, letto con tolleranza: NULL o meno di 1 vale 1."""
    try:
        valore = int(max_groups) if max_groups is not None else 1
    except (TypeError, ValueError):
        return 1
    return max(1, min(valore, MASSIMO_DI_GIRONI))


def gironi_possibili(iscritti: int, max_groups: Optional[int]) -> int:
    """Il numero più alto di gironi che si può scegliere all'avvio.

    È il tetto della gara, ridotto finché ogni girone ha almeno
    `MINIMO_PER_GIRONE` giocatori. Mai meno di 1: con pochi iscritti resta il
    girone unico.
    """
    return max(1, min(tetto_di_gironi(max_groups), iscritti // MINIMO_PER_GIRONE))


def proposta_di_gironi(iscritti: int, max_groups: Optional[int]) -> int:
    """Quanti gironi propone il foglio di avvio: uno ogni sei, per eccesso."""
    voluti = math.ceil(iscritti / GIOCATORI_PER_GIRONE_PROPOSTI) if iscritti else 1
    return max(1, min(voluti, gironi_possibili(iscritti, max_groups)))


def verifica_numero_di_gironi(
    iscritti: int, gironi: int, max_groups: Optional[int]
) -> Optional[str]:
    """Perché quel numero di gironi non va, o None se va bene.

    Il motivo è una chiave (``"minimo"``, ``"tetto"``, ``"giocatori"``): le
    parole le mette chi lo mostra.
    """
    if gironi < 1:
        return "minimo"
    if gironi > tetto_di_gironi(max_groups):
        return "tetto"
    if gironi > 1 and iscritti < gironi * MINIMO_PER_GIRONE:
        return "giocatori"
    return None


def taglie_dei_gironi(iscritti: int, gironi: int) -> List[int]:
    """Quanti giocatori in ogni girone: i primi ne hanno uno in più."""
    if iscritti <= 0:
        return [0] * max(gironi, 1)
    return group_player_counts(iscritti, gironi)


def turni_del_girone(giocatori: int) -> int:
    """I turni di un girone all'italiana: N-1 se pari, N se dispari."""
    if giocatori < 2:
        return 0
    return giocatori if giocatori % 2 else giocatori - 1


def turni_dei_gironi(taglie: Sequence[int]) -> int:
    """I turni della gara: quelli del girone più numeroso."""
    return max((turni_del_girone(t) for t in taglie), default=0)


@dataclass(frozen=True)
class Iscritto:
    """Ciò che la composizione guarda di un iscritto.

    ``categoria`` è il posto della sua categoria nell'ordine delle categorie
    (0 = la prima), None se non ne ha una: chi non ha categoria viene dopo.
    """

    player_id: int
    elo: Optional[float] = None
    categoria: Optional[int] = None
    squadra: Optional[object] = None


def ordine_di_composizione(
    iscritti: Sequence[Iscritto],
    composizione: ComposizioneGironi,
    seme: object,
) -> List[int]:
    """La fila da cui si distribuiscono i gironi.

    - **sorteggio**: un ordine casuale;
    - **per ELO**: dal più alto, chi non ha ELO in fondo;
    - **per categoria**: nell'ordine delle categorie, chi non ne ha in fondo,
      e dentro la categoria per ELO.

    A pari merito decide il sorteggio. Il caso viene da un generatore con il
    ``seme`` (il `draw_seed` della gara), e i giocatori entrano in ordine di id:
    lo stesso seme dà la stessa fila.
    """
    rng = random.Random(str(seme))
    per_id = sorted(iscritti, key=lambda i: i.player_id)
    sorteggio: Dict[int, float] = {i.player_id: rng.random() for i in per_id}

    def chiave_elo(i: Iscritto) -> tuple:
        return (i.elo is None, -(i.elo or 0))

    if composizione is ComposizioneGironi.ELO:
        ordinati = sorted(per_id, key=lambda i: (*chiave_elo(i), sorteggio[i.player_id]))
    elif composizione is ComposizioneGironi.CATEGORIA:
        ordinati = sorted(
            per_id,
            key=lambda i: (
                i.categoria is None,
                i.categoria or 0,
                *chiave_elo(i),
                sorteggio[i.player_id],
            ),
        )
    else:
        ordinati = sorted(per_id, key=lambda i: sorteggio[i.player_id])
    return [i.player_id for i in ordinati]


def componi_gironi(
    iscritti: Sequence[Iscritto],
    gironi: int,
    composizione: ComposizioneGironi,
    seme: object,
    *,
    separa_compagni: bool = False,
) -> List[List[int]]:
    """I gironi: una lista di id per girone, nell'ordine della fila.

    Con ``separa_compagni`` i compagni di squadra si spostano fra i gironi
    della stessa riga della distribuzione, che hanno giocatori vicini nella
    fila: così si separano senza toccare l'equilibrio (ADR-039).
    """
    fila = ordine_di_composizione(iscritti, composizione, seme)
    squadre: Mapping[int, Optional[object]] = (
        {i.player_id: i.squadra for i in iscritti} if separa_compagni else {}
    )
    return distribute_into_groups(fila, gironi, squadre)


__all__ = [
    "ComposizioneGironi",
    "GIOCATORI_PER_GIRONE_PROPOSTI",
    "Iscritto",
    "MASSIMO_DI_GIRONI",
    "MINIMO_PER_GIRONE",
    "componi_gironi",
    "gironi_possibili",
    "nome_del_girone",
    "ordine_di_composizione",
    "proposta_di_gironi",
    "taglie_dei_gironi",
    "tetto_di_gironi",
    "turni_dei_gironi",
    "turni_del_girone",
    "verifica_numero_di_gironi",
]
