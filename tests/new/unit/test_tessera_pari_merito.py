"""La tessera della gara dice il pari merito, alla posizione più alta (2026-10-11).

Regola dell'utente: «Se uno è pari merito col primo allora è primo pari merito,
non secondo. La tessera deve dire che è n-esimo pari merito.»

Il caso vero (`test_gironi_tabelle_in_pagina.py`): dopo il turno 2 due
giocatori avevano 2 vinte e +6, il sorteggio della catena li aveva messi 1° e
2°, e la tessera diceva «Sei 2°».
"""

from __future__ import annotations

import pytest

from models.dashboard.gara_cards import PiazzamentoVM, PosizioneVM, dove_sei

pytestmark = pytest.mark.unit


class TestDoveSei:
    def test_separato_solo_dal_sorteggio_e_primo_pari_merito(self):
        # (utente, posizione mostrata, girone, posizione mostrata nel girone)
        righe = [(10, 1, None, None), (20, 1, None, None), (30, 3, None, None)]
        assert dove_sei(righe, 20) == (1, 3, True, None)
        assert dove_sei(righe, 10) == (1, 3, True, None)
        assert dove_sei(righe, 30) == (3, 3, False, None)

    def test_nel_girone_si_conta_dentro_il_girone(self):
        righe = [
            (10, 1, 0, 1),
            (20, 2, 1, 1),
            (30, 3, 0, 1),
            (40, 4, 1, 2),
            (50, 5, 0, 3),
        ]
        assert dove_sei(righe, 30) == (1, 3, True, 0)
        assert dove_sei(righe, 20) == (1, 2, False, 1)

    def test_chi_non_c_e(self):
        assert dove_sei([(10, 1, None, None)], 99) is None


class TestIlTesto:
    """Il testo vive nel template della tessera: qui si legge quel template."""

    def _template(self):
        from pathlib import Path

        radice = Path(__file__).resolve().parents[3]
        return (radice / "templates/components/_tessera_gara.html").read_text(
            encoding="utf-8"
        )

    def test_la_tessera_dice_pari_merito_in_classifica(self):
        testo = self._template()
        assert "Sei %(pos)s° pari merito su %(tot)s'" in testo
        assert "Sei %(pos)s° pari merito su %(tot)s nel girone %(nome)s" in testo
        assert "card.classifica.pari_merito" in testo

    def test_la_tessera_dice_pari_merito_a_gara_finita(self):
        testo = self._template()
        assert "Sei arrivato %(pos)s° pari merito su %(tot)s" in testo
        assert "card.piazzamento.pari_merito" in testo

    def test_i_view_model_portano_il_pari_merito(self):
        assert PosizioneVM(posizione=1, su=4, turno=2, pari_merito=True).pari_merito
        assert not PosizioneVM(posizione=1, su=4, turno=2).pari_merito
        assert PiazzamentoVM(
            posizione=2, su=8, vinte=3, giocate=5, pari_merito=True
        ).pari_merito
