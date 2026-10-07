"""Le catene di default riproducono le classifiche di prima (ADR-078).

Il 2026-10-07 l'utente ha deciso quali classifiche cambiano col motore unico e
quali no. Restano **identiche** la classifica di turno a vittorie e le due
classifiche di gara (a vittorie e a rack). Qui le si confronta, su molti
scenari casuali, con le chiavi di ordinamento che il codice usava prima:

- turno WINS: ``(-vittorie, -differenza, posizione precedente, id)``;
- gara WINS: ``(-vittorie, -differenza, -ssr)``, chi ha la stessa chiave
  condivide la posizione, -1 a chi non ha tirato;
- gara RACK: ``(-rack, -ssr)``, idem.

Lo spareggio si registra, come in produzione, solo per chi era pari in un
gruppo che parte entro il suo posto: è l'unico caso in cui un SSR esiste.

Cambiano invece, per decisione: il turno RACK (via SSR e differenza), l'ultima
risorsa del turno (sorteggio invece dell'id) e la classifica generale a pari
merito (posizione dopo la gara precedente, poi sorteggio, invece dell'ordine di
comparsa). Quelle regole hanno i loro test in `test_ordinamento_motore.py`.
"""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

import pytest

from models.classification.ordinamento import (
    Concorrente,
    Livello,
    catena_di_default,
    criterio_principale,
    normalizza_catena,
    ordina,
)
from models.status_enum import ClassificationSystem

pytestmark = pytest.mark.unit

WINS, RACK = ClassificationSystem.WINS, ClassificationSystem.RACK


def _posizioni_condivise(ordinati, chiave) -> Dict[int, int]:
    """Il vecchio `assign_shared_positions`: stessa chiave, stessa posizione."""
    posizioni: Dict[int, int] = {}
    precedente = None
    posizione = 0
    for indice, c in enumerate(ordinati, 1):
        if chiave(c) != precedente:
            posizione, precedente = indice, chiave(c)
        posizioni[c.player_id] = posizione
    return posizioni


def _nuove(concorrenti, sistema, livello, ssr_fino_al=3) -> Dict[int, int]:
    catena = normalizza_catena(
        catena_di_default(livello, sistema, ssr_fino_al=ssr_fino_al), livello, sistema
    )
    fasce = ordina(concorrenti, criterio_principale(sistema), catena)
    return {g.player_id: f.posizione for f in fasce for g in f.giocatori}


def _giocatori(rng: random.Random, n: int) -> List[Concorrente]:
    return [
        Concorrente(
            player_id=pid,
            vittorie=rng.randint(0, 3),
            rack_vinti=rng.randint(0, 6),
            differenza_rack=rng.randint(-2, 2),
        )
        for pid in range(1, n + 1)
    ]


def _con_ssr(concorrenti, chiave_prima, fino_al, rng) -> List[Concorrente]:
    """Registra lo SSR a chi era pari in un gruppo che parte entro il posto."""
    ordinati = sorted(concorrenti, key=chiave_prima)
    gruppi: Dict[Tuple, List[Concorrente]] = {}
    for c in ordinati:
        gruppi.setdefault(chiave_prima(c), []).append(c)
    ssr: Dict[int, int] = {}
    posizione = 1
    for chiave in sorted(gruppi):
        gruppo = gruppi[chiave]
        if len(gruppo) > 1 and posizione <= fino_al:
            for c in gruppo:
                ssr[c.player_id] = rng.randint(0, 3)
        posizione += len(gruppo)
    return [
        Concorrente(
            player_id=c.player_id,
            vittorie=c.vittorie,
            rack_vinti=c.rack_vinti,
            differenza_rack=c.differenza_rack,
            ssr=ssr.get(c.player_id),
        )
        for c in concorrenti
    ]


def _ssr(c: Concorrente) -> int:
    return -1 if c.ssr is None else c.ssr


@pytest.mark.parametrize("seme", range(200))
def test_turno_a_vittorie_come_prima(seme):
    rng = random.Random(seme)
    n = rng.randint(2, 12)
    precedenti = list(range(1, n + 1))
    rng.shuffle(precedenti)
    concorrenti = [
        Concorrente(
            player_id=c.player_id,
            vittorie=c.vittorie,
            differenza_rack=c.differenza_rack,
            posizione_precedente=precedenti[i],
        )
        for i, c in enumerate(_giocatori(rng, n))
    ]
    prima = sorted(
        concorrenti,
        key=lambda c: (
            -c.vittorie,
            -c.differenza_rack,
            c.posizione_precedente,
            c.player_id,
        ),
    )
    attese = {c.player_id: i for i, c in enumerate(prima, 1)}
    assert _nuove(concorrenti, WINS, Livello.TURNO) == attese


@pytest.mark.parametrize("seme", range(200))
@pytest.mark.parametrize("fino_al", [1, 2, 3])
def test_gara_a_vittorie_come_prima(seme, fino_al):
    rng = random.Random(seme)
    concorrenti = _con_ssr(
        _giocatori(rng, rng.randint(2, 12)),
        lambda c: (-c.vittorie, -c.differenza_rack),
        fino_al,
        rng,
    )

    def chiave(c):
        return (-c.vittorie, -c.differenza_rack, -_ssr(c))

    attese = _posizioni_condivise(sorted(concorrenti, key=chiave), chiave)
    assert _nuove(concorrenti, WINS, Livello.GARA, fino_al) == attese


@pytest.mark.parametrize("seme", range(200))
@pytest.mark.parametrize("fino_al", [1, 2, 3])
def test_gara_a_rack_come_prima(seme, fino_al):
    rng = random.Random(seme)
    concorrenti = _con_ssr(
        _giocatori(rng, rng.randint(2, 12)), lambda c: (-c.rack_vinti,), fino_al, rng
    )

    def chiave(c):
        return (-c.rack_vinti, -_ssr(c))

    attese = _posizioni_condivise(sorted(concorrenti, key=chiave), chiave)
    assert _nuove(concorrenti, RACK, Livello.GARA, fino_al) == attese


@pytest.mark.parametrize("seme", range(100))
@pytest.mark.parametrize("sistema", [WINS, RACK])
def test_gara_senza_spareggio_come_prima(seme, sistema):
    """Spareggio spento: i pari sul principale (e sulla differenza) restano."""
    rng = random.Random(seme)
    concorrenti = _giocatori(rng, rng.randint(2, 12))

    def chiave(c):
        if sistema is RACK:
            return (-c.rack_vinti,)
        return (-c.vittorie, -c.differenza_rack)

    attese = _posizioni_condivise(sorted(concorrenti, key=chiave), chiave)
    assert _nuove(concorrenti, sistema, Livello.GARA, None) == attese
