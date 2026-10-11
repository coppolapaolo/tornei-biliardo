"""Quale partita di un turno del tabellone è la finale (ADR-081, emendamento).

Regola pura: l'unico nodo dei vincenti del turno, senza girone. La finalina
sta nello stesso turno e non è la finale.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.matchmaking.bracket import BRACKET_THIRD_PLACE, BRACKET_WINNERS
from models.matchmaking.fase_finale import (
    DistanzaDellaFase,
    distanza_dal_modulo,
    la_finale_del_turno,
    limite_dal_modulo,
)

pytestmark = pytest.mark.unit


def _nodo(tipo, gruppo=None):
    return SimpleNamespace(bracket_type=tipo, bracket_group=gruppo)


def test_finale_e_finalina():
    finale = _nodo(BRACKET_WINNERS)
    assert la_finale_del_turno([_nodo(BRACKET_THIRD_PLACE), finale]) is finale


def test_le_semifinali_non_sono_la_finale():
    assert la_finale_del_turno([_nodo(BRACKET_WINNERS), _nodo(BRACKET_WINNERS)]) is None


def test_i_nodi_di_un_girone_non_contano():
    assert la_finale_del_turno([_nodo(BRACKET_WINNERS, gruppo=1)]) is None


def test_un_turno_dei_gironi_non_ha_finale():
    assert la_finale_del_turno([_nodo(None), _nodo(None)]) is None


class TestDalModulo:
    def test_distanza(self, app):
        with app.test_request_context():
            assert distanza_dal_modulo(DistanzaDellaFase.COME_PRIMA.value, "9") is None
            assert distanza_dal_modulo(DistanzaDellaFase.ALTRA.value, "7") == 7
            for sbagliata in ("0", "16", "", "x"):
                with pytest.raises(ValueError):
                    distanza_dal_modulo(DistanzaDellaFase.ALTRA.value, sbagliata)
            with pytest.raises(ValueError):
                distanza_dal_modulo("boh", "7")

    def test_limite_della_finale(self, app):
        with app.test_request_context():
            assert limite_dal_modulo("gironi", "", finale=True) is None
            assert limite_dal_modulo("nessuno", "", finale=True) == 0
            assert limite_dal_modulo("minuti", "50", finale=True) == 50
            with pytest.raises(ValueError, match="finale"):
                limite_dal_modulo("minuti", "0", finale=True)

    def test_il_modo_del_valore(self):
        assert DistanzaDellaFase.del_valore(None) is DistanzaDellaFase.COME_PRIMA
        assert DistanzaDellaFase.del_valore(7) is DistanzaDellaFase.ALTRA
