"""Il punteggio del trio a totali (card del direttore): quali totali esistono.

L'ordine del girone e' fisso — 1–2, 1–3, 2–3 — quindi un totale segnato dalla
card corrisponde a una sequenza di triangoli solo se quell'ordine la ammette.
"""

from __future__ import annotations

import pytest

from models.match.trio_config import TrioConfig
from models.match.trio_punteggio import (
    assegna_vincitori,
    massimo_per_giocatore,
    piu_ammessi,
)

pytestmark = pytest.mark.unit


def test_il_primo_triangolo_e_fra_il_primo_e_il_secondo():
    config = TrioConfig(distance=3)
    assert assegna_vincitori(config, (1, 0, 0)) == [0]
    assert assegna_vincitori(config, (0, 1, 0)) == [1]
    assert assegna_vincitori(config, (0, 0, 1)) is None
    assert piu_ammessi(config, (0, 0, 0)) == [True, True, False]


def test_a_girone_finito_ogni_totale_con_la_somma_giusta_esiste():
    config = TrioConfig(distance=5)  # due gironi, sei triangoli
    for punti in [(4, 2, 0), (2, 2, 2), (0, 4, 2), (3, 3, 0), (1, 1, 4)]:
        vincitori = assegna_vincitori(config, punti)
        assert vincitori is not None, punti
        assert [vincitori.count(g) for g in range(3)] == list(punti)


def test_nessuno_vince_piu_dei_triangoli_che_gioca():
    config = TrioConfig(distance=4)
    assert massimo_per_giocatore(config) == 4
    assert assegna_vincitori(config, (5, 1, 0)) is None
    assert piu_ammessi(config, (4, 1, 0))[0] is False


def test_oltre_il_totale_dei_triangoli_il_piu_e_spento():
    config = TrioConfig(distance=2)  # un girone, tre triangoli
    assert piu_ammessi(config, (2, 1, 0)) == [False, False, False]
    assert assegna_vincitori(config, (2, 2, 0)) is None


def test_una_correzione_tiene_i_triangoli_gia_registrati():
    """Chi aggiunge un triangolo non riscrive quelli prima."""
    config = TrioConfig(distance=4)
    # Registrati: il primo lo vince il giocatore 2, il secondo il giocatore 3.
    esistenti = [1, 2]
    # Un triangolo in piu' al giocatore 2: il terzo (2–3) lo vince lui, e i
    # primi due restano come erano.
    assert assegna_vincitori(config, (0, 2, 1), esistenti) == [1, 2, 1]


def test_punteggi_negativi_o_malformati_non_esistono():
    config = TrioConfig(distance=3)
    assert assegna_vincitori(config, (-1, 1, 0)) is None
    assert assegna_vincitori(config, (1, 0)) is None
