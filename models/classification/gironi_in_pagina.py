"""Le classifiche di una gara a più gironi, come le mostrano le pagine (ADR-076).

Le righe di classifica di una gara a gironi sono nell'ordine **della gara**:
prima i primi di ogni girone, poi i secondi (`classification/gironi.py`). Ogni
riga porta però anche il suo girone (`group_index`) e la posizione dentro il
girone (`group_position`). Da lì le pagine ricavano due viste:

* **mentre si gioca**, una classifica per girone: «Girone A», «Girone B»,
  ciascuna nell'ordine del girone — il sistema e la catena della gara, già
  applicati da chi ha scritto le righe;
* **a gara finita**, la classifica della gara così com'è, con accanto a ogni
  nome girone e posizione nel girone («1º girone A»).

Con il girone unico le righe non hanno girone, e qui non succede niente: la
pagina resta quella di sempre.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import (
    Any,
    Collection,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from models.matchmaking.gironi import nome_del_girone

from .models import posizione_mostrata_nel_girone
from models.status_enum import GaraStatus


@dataclass(frozen=True)
class RigaDelGirone:
    """Una riga di classifica vista dentro il suo girone."""

    riga: Any
    #: La posizione nel girone da mostrare: i pari merito, anche quelli che
    #: solo il sorteggio separa, stanno sulla più alta (1, 1, 3; nota del
    #: 2026-10-11 in SPECIFICHE.md).
    posizione: int
    #: La posizione mostrata nel girone dopo il turno prima, se c'era.
    precedente: Optional[int] = None
    #: Col tabellone dopo i gironi, quando si sa chi passa (ADR-081): True
    #: «al tabellone», False «fuori», None se non si sa ancora.
    taglio: Optional[bool] = None
    #: La riga del taglio sta sopra questa: è il primo dei «fuori».
    primo_fuori: bool = False


@dataclass(frozen=True)
class GironeInPagina:
    """Un girone con le sue righe, in ordine di girone."""

    indice: int
    nome: str
    righe: Tuple[RigaDelGirone, ...]


def dividi_per_girone(
    righe: Iterable[Any],
    precedenti: Optional[Mapping[int, int]] = None,
) -> List[GironeInPagina]:
    """Le righe divise per girone, o una lista vuota se i gironi non ci sono.

    Vuota anche quando una riga non ha girone (un dato storico, una gara a
    girone unico) o quando i gironi distinti sono meno di due: allora la
    classifica si mostra intera, e nessuno sparisce dalla pagina.

    Args:
        righe: righe di classifica con ``group_index``, ``group_position``,
            ``position`` e ``user_id``.
        precedenti: giocatore → posizione nel girone dopo il turno prima.
    """
    tutte = list(righe)
    if not tutte or any(getattr(r, "group_index", None) is None for r in tutte):
        return []
    per_girone: Dict[int, List[Any]] = {}
    for r in tutte:
        per_girone.setdefault(int(r.group_index), []).append(r)
    if len(per_girone) < 2:
        return []
    precedenti = precedenti or {}
    gironi = []
    for indice in sorted(per_girone):
        ordinate = sorted(
            per_girone[indice],
            key=lambda r: (r.group_position or r.position, r.position),
        )
        gironi.append(
            GironeInPagina(
                indice=indice,
                nome=nome_del_girone(indice),
                righe=tuple(
                    RigaDelGirone(
                        riga=r,
                        posizione=posizione_mostrata_nel_girone(r) or pos,
                        precedente=precedenti.get(r.user_id),
                    )
                    for pos, r in enumerate(ordinate, start=1)
                ),
            )
        )
    return gironi


def _gara_in_gioco(gara: Any) -> bool:
    """Si gioca ancora? Allora si guardano i gironi, non la gara intera."""
    return getattr(gara, "status", None) == GaraStatus.PLAYING.value


def _posizioni_nel_girone_prima(righe: Sequence[Any]) -> Dict[int, int]:
    """La posizione mostrata nel girone di ognuno dopo il turno prima."""
    turno = getattr(righe[0], "round_number", None) if righe else None
    gara_id = getattr(righe[0], "gara_id", None) if righe else None
    if not turno or turno <= 1 or gara_id is None:
        return {}
    from models.base import db

    from .models import RoundClassification

    return {
        user_id: mostrata if mostrata is not None else posizione
        for user_id, posizione, mostrata in db.session.query(
            RoundClassification.user_id,
            RoundClassification.group_position,
            RoundClassification.shown_group_position,
        )
        .filter(
            RoundClassification.gara_id == gara_id,
            RoundClassification.round_number == turno - 1,
            RoundClassification.group_position.isnot(None),
        )
        .all()
    }


def segna_il_taglio(
    gironi: Sequence[GironeInPagina], qualificati: Optional[Collection[int]]
) -> List[GironeInPagina]:
    """Chi va al tabellone e chi no, in ogni girone, con la riga del taglio.

    Chi passa lo decide la catena di turno all'ultimo turno dei gironi, che
    finisce col sorteggio (`fase_finale_service.semina`): due «2º pari
    merito» — la posizione mostrata è la stessa — possono stare uno sopra e
    uno sotto il taglio. Dentro un girone i qualificati vengono prima, nel
    loro ordine: fra due pari merito l'ordine lo dà proprio quella catena.

    Args:
        gironi: le classifiche per girone (`dividi_per_girone`).
        qualificati: chi gioca il tabellone, o None se non si sa ancora: allora
            le righe restano come sono.
    """
    if qualificati is None:
        return list(gironi)
    segnati = []
    for g in gironi:
        dentro = [v for v in g.righe if v.riga.user_id in qualificati]
        fuori = [v for v in g.righe if v.riga.user_id not in qualificati]
        righe = [replace(v, taglio=True) for v in dentro] + [
            replace(v, taglio=False, primo_fuori=bool(dentro) and i == 0)
            for i, v in enumerate(fuori)
        ]
        segnati.append(replace(g, righe=tuple(righe)))
    return segnati


def _chi_va_al_tabellone(gara: Any) -> Optional[Collection[int]]:
    """I qualificati al tabellone dopo i gironi, se la gara ne ha uno."""
    if getattr(gara, "ha_tabellone_finale", False) is not True:
        return None
    from models.competition.fase_finale_service import chi_va_al_tabellone

    return chi_va_al_tabellone(gara)


def gironi_in_pagina(gara: Any, righe: Optional[Iterable[Any]]) -> List[GironeInPagina]:
    """Le classifiche per girone da mostrare, o vuota se va mostrata la gara.

    Mentre la gara si gioca, una classifica per girone; a gara finita (o in
    attesa dello spareggio, che guarda la posizione nella gara) la classifica
    della gara intera, che chi la mostra correda con `girone_della_riga`.
    """
    if righe is None or not _gara_in_gioco(gara):
        return []
    tutte = list(righe)
    gironi = dividi_per_girone(tutte)
    if not gironi:
        return []
    return segna_il_taglio(
        dividi_per_girone(tutte, _posizioni_nel_girone_prima(tutte)),
        _chi_va_al_tabellone(gara),
    )


def girone_della_riga(riga: Any) -> Optional[Tuple[str, int]]:
    """(nome del girone, posizione nel girone) di una riga, o None col girone unico.

    La posizione è quella mostrata: due primi a pari merito sono «1º» entrambi.
    """
    indice = getattr(riga, "group_index", None)
    posizione = posizione_mostrata_nel_girone(riga)
    if indice is None or not posizione:
        return None
    return nome_del_girone(int(indice)), int(posizione)


__all__ = [
    "GironeInPagina",
    "RigaDelGirone",
    "dividi_per_girone",
    "girone_della_riga",
    "gironi_in_pagina",
    "segna_il_taglio",
]
