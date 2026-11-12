"""Amalfi con un numero dispari di giocatori: una X sola, a ogni turno.

Trovato il 12/11/2026 da un test diventato intermittente. Nel caso dispari
l'abbinamento passava dal greedy del salto, che non segnava la X come presa:
se il primo ci arrivava scartando un reincontro, ci arrivavano anche gli
altri. Con tre giocatori attivi uscivano tre X e nessuna partita; con sette,
tre X e due partite. Il difetto restava coperto finché la matrice degli
incontri era incompleta.

Ora la X è un posto in più in fondo alla classifica e l'abbinamento è lo
stesso matching del caso pari.
"""

import itertools
import random
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from models.matchmaking.strategies.amalfi import AmalfiStrategy

pytestmark = pytest.mark.unit

MATRICE = (
    "models.classification.encounter_service."
    "PlayerEncounterService.get_encounter_matrix"
)


def _abbina(ordine, incontri, con_la_x, turno, max_turni):
    classifica = [
        SimpleNamespace(user_id=giocatore, position=i, gara_id=1)
        for i, giocatore in enumerate(ordine, 1)
    ]
    matrice = {}
    for a, b in incontri:
        matrice[(a, b)] = True
        matrice[(b, a)] = True
    with patch(MATRICE, return_value=matrice), patch.object(
        AmalfiStrategy, "_get_players_with_bye", return_value=set(con_la_x)
    ):
        return AmalfiStrategy()._amalfi_pairing(
            classifica, turno=turno, max_turni=max_turni
        )


def _da_evitare(abbinamenti, incontri, con_la_x):
    visti = {frozenset(coppia) for coppia in incontri}
    return sum(
        (p.players[0] in con_la_x) if p.is_bye else (frozenset(p.players) in visti)
        for p in abbinamenti
    )


def test_tre_giocatori_due_gia_incontrati_una_partita_e_una_x():
    """Il caso del test intermittente: quattro iscritti, uno escluso."""
    abbinamenti = _abbina([3, 2, 4], [(3, 4)], [], turno=2, max_turni=3)

    assert sum(1 for p in abbinamenti if p.is_bye) == 1
    assert sorted(len(p.players) for p in abbinamenti) == [1, 2]
    assert _da_evitare(abbinamenti, [(3, 4)], []) == 0


def test_sette_giocatori_non_escono_tre_x():
    """Una storia in cui il greedy dava tre X e due sole partite."""
    incontri = [(1, 3), (1, 4), (2, 3), (2, 5), (2, 6), (4, 5), (5, 7), (6, 7)]
    con_la_x = [1, 3, 4]
    abbinamenti = _abbina(
        [3, 7, 4, 6, 5, 1, 2], incontri, con_la_x, turno=4, max_turni=5
    )

    assert sum(1 for p in abbinamenti if p.is_bye) == 1
    assert len(abbinamenti) == 4
    assert _da_evitare(abbinamenti, incontri, con_la_x) == 0


def test_chi_ha_gia_avuto_la_x_non_la_riprende_se_un_altro_puo():
    abbinamenti = _abbina([1, 2, 3, 4, 5], [], [5], turno=3, max_turni=3)

    con_la_x = [p.players[0] for p in abbinamenti if p.is_bye]
    assert len(con_la_x) == 1 and con_la_x != [5]


def test_senza_storia_la_x_va_dove_la_metteva_il_salto():
    """Turno 2 di 5 con cinque giocatori: salto 4, la X al secondo."""
    abbinamenti = _abbina([1, 2, 3, 4, 5], [], [], turno=2, max_turni=5)

    assert [p.players for p in abbinamenti if p.is_bye] == [(2,)]


def _minimo_da_evitare(ordine, incontri, con_la_x):
    """Il minimo vero, per forza bruta: ogni modo di abbinare tutti."""
    visti = {frozenset(coppia) for coppia in incontri}
    migliore = None
    for permutazione in itertools.permutations(ordine):
        costo = int(permutazione[-1] in con_la_x) + sum(
            frozenset(coppia) in visti
            for coppia in zip(permutazione[0:-1:2], permutazione[1:-1:2])
        )
        migliore = costo if migliore is None else min(migliore, costo)
    return migliore


def test_storie_a_caso_una_x_tutti_in_campo_e_il_minimo_di_eccezioni():
    rng = random.Random(20261112)
    for _ in range(300):
        n = rng.choice([3, 5, 7])
        ordine = list(range(1, n + 1))
        max_turni = rng.choice([3, 4, 5])
        turno = rng.randint(2, max_turni)
        incontri, con_la_x = [], set()
        for _turno_passato in range(turno - 1):
            giro = ordine[:]
            rng.shuffle(giro)
            con_la_x.add(giro[-1])
            incontri += list(zip(giro[0:-1:2], giro[1:-1:2]))
        rng.shuffle(ordine)

        abbinamenti = _abbina(ordine, incontri, con_la_x, turno, max_turni)

        in_campo = Counter(g for p in abbinamenti for g in p.players)
        assert sum(1 for p in abbinamenti if p.is_bye) == 1, (ordine, incontri)
        assert in_campo == Counter(ordine), (ordine, incontri)
        assert _da_evitare(abbinamenti, incontri, con_la_x) == _minimo_da_evitare(
            ordine, incontri, con_la_x
        ), (ordine, incontri, sorted(con_la_x))
