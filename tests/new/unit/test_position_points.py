"""Punti di campionato per posizione (Step 9, US-17).

I valori di default sono quelli della spec; un campionato può sovrascriverli, e
chi non lo fa non deve configurare nulla. Un campo scritto male non deve
impedire il calcolo della classifica: si degrada al default e lo si dice al log.
"""

from __future__ import annotations

import pytest

from models.classification.position_points import (
    default_table,
    describe_default,
    parse_points_table,
    points_for_position,
    points_table_for_campionato,
    serialize_points_table,
)

pytestmark = pytest.mark.unit


class TestTabellaDiDefault:
    @pytest.mark.parametrize(
        "position,expected",
        [
            (1, 25),
            (2, 18),
            (3, 15),
            (4, 12),
            (5, 8),
            (8, 8),
            (9, 4),
            (16, 4),
        ],
    )
    def test_valori_della_spec(self, position, expected):
        assert points_for_position(position) == expected

    def test_oltre_la_sedicesima_nessun_punto(self):
        """Aver partecipato non è di per sé un punteggio."""
        assert points_for_position(17) == 0
        assert points_for_position(64) == 0

    def test_posizione_assente_o_assurda(self):
        assert points_for_position(None) == 0
        assert points_for_position(0) == 0
        assert points_for_position(-3) == 0

    def test_i_pari_merito_di_una_banda_prendono_lo_stesso(self):
        """I quattro quartifinalisti sono tutti 5°: stessi punti per tutti."""
        assert len({points_for_position(5) for _ in range(4)}) == 1
        assert points_for_position(5) == points_for_position(8) == 8

    def test_tabella_espansa(self):
        table = default_table()
        assert table[1] == 25
        assert table[16] == 4
        assert max(table) == 16

    def test_descrizione_leggibile(self):
        assert describe_default()[:2] == ["1° = 25 punti", "2° = 18 punti"]
        assert "5°-8° = 8 punti" in describe_default()


class TestTabellaConfigurata:
    def test_sovrascrive_il_default(self):
        table = {1: 100, 2: 50}
        assert points_for_position(1, table) == 100
        assert points_for_position(2, table) == 50

    def test_le_soglie_coprono_le_posizioni_intermedie(self):
        """`{1: 10, 4: 3}` significa "dal 2° al 4° valgono 3"."""
        table = {1: 10, 4: 3}
        assert points_for_position(2, table) == 3
        assert points_for_position(4, table) == 3
        assert points_for_position(5, table) == 0


class TestPersistenza:
    def test_andata_e_ritorno(self):
        table = {1: 30, 2: 20, 4: 10}
        assert parse_points_table(serialize_points_table(table)) == table

    def test_assente_significa_default(self):
        assert parse_points_table(None) is None
        assert parse_points_table("") is None
        assert serialize_points_table(None) is None
        assert serialize_points_table({}) is None

    @pytest.mark.parametrize(
        "raw", ["non json", "[1, 2, 3]", "{}", '{"primo": 25}', '{"1": "molti"}']
    )
    def test_contenuto_illeggibile_degrada_al_default(self, raw):
        """La classifica di un campionato non smette di calcolarsi per un
        campo di configurazione scritto male."""
        assert parse_points_table(raw) is None

    def test_lettura_dal_campionato(self):
        class _Campionato:
            position_points = '{"1": 40}'

        assert points_table_for_campionato(_Campionato()) == {1: 40}
        assert points_table_for_campionato(None) is None
