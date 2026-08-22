"""Le regole del motore di rating a rack (ADR-052).

Il motore è puro — niente DB, niente sessione — quindi le sue regole si
verificano con l'aritmetica. È il motivo per cui è un modulo a sé: un motore
intrecciato alla persistenza si potrebbe solo osservare, non interrogare.
"""

from __future__ import annotations

import pytest

from models.rating import rack_engine


class TestProbabilitaDelRack:
    """`SCALA` punti di differenza = probabilità doppia sul singolo rack."""

    def test_a_pari_rating_e_una_moneta(self):
        base = rack_engine.PARTENZA
        assert rack_engine.probabilita_rack(base, base) == pytest.approx(0.5)

    def test_un_intervallo_di_scala_vale_due_a_uno_sul_singolo_rack(self):
        """È la definizione della scala, non una conseguenza dei parametri.

        Scritto in funzione di `SCALA` di proposito: quel numero è un'unità di
        misura e può cambiare (ADR-052), ma il significato dell'intervallo no.
        """
        base = rack_engine.PARTENZA
        p = rack_engine.probabilita_rack(base + rack_engine.SCALA, base)
        assert p == pytest.approx(2 / 3, abs=1e-9)
        assert p / (1 - p) == pytest.approx(2.0)

    def test_e_simmetrica(self):
        base, scala = rack_engine.PARTENZA, rack_engine.SCALA
        assert rack_engine.probabilita_rack(base, base + scala) == pytest.approx(
            1 - rack_engine.probabilita_rack(base + scala, base)
        )


class TestFattoreK:
    def test_parte_alto_e_cala_coi_rack_accumulati(self):
        nuovo = rack_engine.fattore_k(0, 0)
        esperto = rack_engine.fattore_k(1000, 1000)
        assert nuovo == pytest.approx(rack_engine.K_MAX)
        assert esperto < nuovo
        assert esperto > rack_engine.K_MIN

    def test_alla_mezza_vita_ha_smaltito_meta_dello_scarto(self):
        atteso = rack_engine.K_MIN + (rack_engine.K_MAX - rack_engine.K_MIN) / 2
        k = rack_engine.fattore_k(
            int(rack_engine.N_MEZZA_VITA), int(rack_engine.N_MEZZA_VITA)
        )
        assert k == pytest.approx(atteso)

    def test_e_la_media_dei_due_non_uno_per_ciascuno(self):
        """Un `k` per giocatore romperebbe la conservazione del punteggio."""
        comune = rack_engine.fattore_k(0, 1000)
        assert comune == pytest.approx(
            (rack_engine.fattore_k(0, 0) + rack_engine.fattore_k(1000, 1000)) / 2
        )


class TestVariazione:
    def test_il_totale_del_pool_non_si_muove(self):
        """Quello che uno perde è esattamente quello che l'altro guadagna.

        È la proprietà che rende i rating confrontabili nel tempo, ed è la
        ragione per cui il `k` è comune: la variante con un `k` a testa,
        suggerita dal materiale di partenza, faceva comparire punti dal nulla.
        """
        da_a = rack_engine.variazione(1260, 1200, 5, 2, 40, 300)
        da_b = rack_engine.variazione(1200, 1260, 2, 5, 300, 40)
        assert da_a == pytest.approx(-da_b)

    def test_battere_l_atteso_alza_il_rating(self):
        assert rack_engine.variazione(1200, 1200, 5, 0, 0, 0) > 0

    def test_perdere_lo_abbassa(self):
        assert rack_engine.variazione(1200, 1200, 0, 5, 0, 0) < 0

    def test_a_pari_rating_il_pareggio_non_muove_niente(self):
        assert rack_engine.variazione(1200, 1200, 3, 3, 0, 0) == pytest.approx(0.0)

    def test_il_margine_conta(self):
        """È la ragione d'essere dell'intero motore.

        Nel modello storico un 5-0 e un 5-4 muovono i rating in modo identico,
        perché legge solo chi ha vinto. Qui no.
        """
        netta = rack_engine.variazione(1200, 1200, 5, 0, 0, 0)
        tirata = rack_engine.variazione(1200, 1200, 5, 4, 0, 0)
        assert netta > tirata > 0

    def test_vincere_sotto_le_aspettative_puo_costare_punti(self):
        """Il favorito che vince di misura ha performato sotto l'atteso.

        Non è una stranezza: è cosa significa misurare la prestazione invece
        dell'esito. Contro un avversario molto più debole, vincere 5-4 è una
        brutta serata.
        """
        assert rack_engine.variazione(1400, 1200, 5, 4, 0, 0) < 0

    def test_un_giocatore_nuovo_si_muove_piu_in_fretta_di_uno_con_storico(self):
        nuovo = rack_engine.variazione(1200, 1200, 5, 1, 0, 0)
        rodato = rack_engine.variazione(1200, 1200, 5, 1, 2000, 2000)
        assert nuovo > rodato > 0

    def test_senza_rack_giocati_non_si_muove_niente(self):
        """Il walkover è già escluso a monte: qui è la rete, non la regola."""
        assert rack_engine.variazione(1200, 1300, 0, 0, 0, 0) == 0.0
