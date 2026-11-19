"""Amalfi: fra abbinamenti ugualmente buoni vince quello del salto dall'alto.

Trovato il 18/11/2026 in sala, alla Ronin Cup 2, gara 3: dieci giocatori, turno
2 di 3, salto 2. La specifica dice di scorrere la classifica dall'alto, l'n-esimo
con l'(n+2)-esimo: 1º–3º, 2º–4º, 5º–7º, 6º–8º, 9º–10º, e nessuna di queste
coppie era un reincontro. In sala invece si è giocato 1º–2º, 3º–5º, 4º–6º,
7º–9º, 8º–10º.

Il matching dell'ADR-029 pesa ogni coppia con lo scostamento dal salto, e i due
abbinamenti si scostano di uno in tutto: pari peso, e `networkx` ne sceglieva
uno qualsiasi. Il peso diceva *quanto* ci si scosta, non *chi*. Ora, a parità,
il posto più alto della classifica sceglie per primo, e sceglie come il salto:
il bersaglio, oppure il primo libero scorrendo in avanti.

La garanzia dell'ADR-029 resta com'era: prima zero reincontri (e zero seconde
X), poi lo scostamento minimo. Il criterio nuovo decide solo fra abbinamenti
che quelle due regole non distinguono.
"""

import itertools
import random
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from models.matchmaking.strategies.amalfi import AmalfiStrategy

pytestmark = pytest.mark.unit

MATRICE = (
    "models.classification.encounter_service."
    "PlayerEncounterService.get_encounter_matrix"
)


def _abbina(ordine, incontri, turno, max_turni, con_la_x=()):
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


def _coppie(abbinamenti):
    return sorted(
        ("X",) + tuple(p.players) if p.is_bye else tuple(p.players) for p in abbinamenti
    )


def test_ronin_cup_2_gara_3_turno_2():
    """La serata vera: la classifica dopo il turno 1 e i suoi incontri."""
    classifica = [
        "DANIELE M",
        "MAX T",
        "MAX P",
        "Dino Rossi",
        "FLAVIO",
        "MARCO",
        "Josef",
        "NICO",
        "WILLY",
        "GABRIELE",
    ]
    turno_1 = [
        ("MAX T", "Josef"),
        ("MARCO", "MAX P"),
        ("Dino Rossi", "NICO"),
        ("GABRIELE", "DANIELE M"),
        ("FLAVIO", "WILLY"),
    ]

    abbinamenti = _abbina(classifica, turno_1, turno=2, max_turni=3)

    assert _coppie(abbinamenti) == sorted(
        [
            ("DANIELE M", "MAX P"),
            ("MAX T", "Dino Rossi"),
            ("FLAVIO", "Josef"),
            ("MARCO", "NICO"),
            ("WILLY", "GABRIELE"),
        ]
    )


def test_senza_incontri_il_primo_gioca_col_terzo_non_col_secondo():
    """Il caso più semplice dello stesso difetto: nessun incontro alle spalle."""
    abbinamenti = _abbina(list(range(1, 11)), [], turno=2, max_turni=3)

    assert _coppie(abbinamenti) == [(1, 3), (2, 4), (5, 7), (6, 8), (9, 10)]


# --- Il salto come lo scrive la specifica, per confronto ----------------------


def _salto_della_specifica(n, salto, incontri, con_la_x=frozenset(), dispari=False):
    """«Abbina l'n-esimo con l'(n+i)-esimo; se l'hanno già giocato, scorre
    l'elenco in modo ciclico» (SPECIFICHE.md, «Strategia di abbinamento»).

    Lavora sugli indici 0..n-1; nel dispari la X è il posto n, in fondo.
    Restituisce None se il salto incontra un'eccezione che non sa evitare.
    """
    posti = n + 1 if dispari else n
    x = n if dispari else None
    presi: set[int] = set()
    coppie = []
    for p1 in range(n):
        if p1 in presi:
            continue
        presi.add(p1)
        p2 = (p1 + salto) % posti
        tentativi = 0
        while (
            p2 in presi
            or (p2 != x and frozenset((p1, p2)) in incontri)
            or (p2 == x and p1 in con_la_x)
        ):
            p2 = (p2 + 1) % posti
            tentativi += 1
            if tentativi >= posti:
                return None
        presi.add(p2)
        coppie.append((p1, "X") if p2 == x else (p1, p2))
    return coppie


def _scostamento(coppie, salto, posti):
    """Quanto l'abbinamento si allontana dal salto, nell'ordine in cui conta.

    Prima lo scostamento complessivo; poi, nel dispari, se la X è rimasta a
    chi dista dal fondo esattamente il salto (SPECIFICHE.md, «Caso dispari con
    la X»: «a parità … la X resta a chi dista dal fondo esattamente il
    salto»). Quella regola viene prima dell'ordine dall'alto.
    """
    totale = 0
    x_sul_salto = False
    for a, b in coppie:
        j = posti - 1 if b == "X" else b
        totale += abs(abs(j - a) - salto)
        if b == "X" and j - a == salto:
            x_sul_salto = True
    return (totale, not x_sul_salto)


def _abbinamento_come_indici(abbinamenti):
    risultato = []
    for p in abbinamenti:
        if p.is_bye:
            risultato.append((p.players[0], "X"))
        else:
            risultato.append(tuple(sorted(p.players)))
    return sorted(risultato, key=lambda c: c[0])


@pytest.mark.parametrize("dispari", [False, True], ids=["pari", "dispari con la X"])
def test_quando_il_salto_non_ha_eccezioni_l_abbinamento_e_il_salto(dispari):
    """La proprietà generale, su storie casuali.

    Se il salto della specifica non produce né reincontri né seconde X, e il
    matching non trova niente che si scosti di meno, l'abbinamento **è** quello
    del salto. Prima della correzione, sulle stesse storie, divergeva circa una
    volta su tre.
    """
    rng = random.Random(20261118)
    verificati = 0
    for _ in range(400):
        n = rng.choice([5, 7, 9, 11, 13] if dispari else [4, 6, 8, 10, 12, 14])
        max_turni = rng.randint(2, 6)
        turno = rng.randint(2, max_turni)
        salto = max_turni - turno + 1
        tutte = [frozenset(c) for c in itertools.combinations(range(n), 2)]
        incontri = set(
            rng.sample(
                tutte, rng.randint(0, min(len(tutte) // 3, n * (turno - 1) // 2))
            )
        )
        con_la_x = (
            frozenset(rng.sample(range(n), min(n, turno - 1)))
            if dispari
            else frozenset()
        )

        atteso = _salto_della_specifica(n, salto, incontri, con_la_x, dispari)
        if atteso is None:
            continue

        abbinamenti = _abbina(
            list(range(n)),
            [tuple(c) for c in incontri],
            turno=turno,
            max_turni=max_turni,
            con_la_x=con_la_x,
        )
        ottenuto = _abbinamento_come_indici(abbinamenti)
        posti = n + 1 if dispari else n
        # Il matching può trovare un abbinamento che si scosta *meno* del
        # salto (ADR-029): lì vince lui, ed è giusto. Qui si verifica solo la
        # parità, che è dove decideva il caso.
        if _scostamento(ottenuto, salto, posti) < _scostamento(atteso, salto, posti):
            continue

        assert ottenuto == sorted(atteso, key=lambda c: c[0]), (n, salto, incontri)
        verificati += 1

    assert verificati > 100
