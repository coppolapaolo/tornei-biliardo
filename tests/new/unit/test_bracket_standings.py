"""Classifica per bande ricavata dal tabellone (Step 9, US-16).

Nel tabellone la posizione non si conta, si legge: chi esce allo stesso turno ha
fatto lo stesso percorso, quindi condivide la posizione. I quattro
quartifinalisti sono tutti 5° e la banda successiva riparte da 9, non da 6.

Due eccezioni: la finalina scioglie la banda dei semifinalisti, e nel doppio KO
il terzo posto lo assegna già il tabellone.
"""

from __future__ import annotations

import pytest

from models.classification.bracket_standings import (
    BracketMatch,
    elimination_bands,
    positions_from_bands,
)

pytestmark = pytest.mark.unit


def _match(bracket_type, round_number, winner, loser, order=0, double=None):
    """Un nodo concluso.

    `double` dice quante sconfitte elimina **questo** nodo, e serve solo alla
    formula FISBB, che mescola le due regole: `True` nel girone (c'è il
    recupero), `False` nel tabellone finale. Lasciato a `None` vale la regola
    della gara.
    """
    return BracketMatch(
        bracket_type=bracket_type,
        round_number=round_number,
        players=(winner, loser) if loser else (winner,),
        winner_id=winner,
        loser_id=loser,
        order=order,
        double_elimination=double,
    )


def _positions(matches, **kwargs):
    return positions_from_bands(elimination_bands(matches, **kwargs))


class TestEliminazioneDiretta:
    def _tabellone_da_otto(self):
        """1 vince tutto; 5 perde la finale; 3 e 7 le semifinali."""
        return [
            _match("W", 1, 1, 2, 0),
            _match("W", 1, 3, 4, 1),
            _match("W", 1, 5, 6, 2),
            _match("W", 1, 7, 8, 3),
            _match("W", 2, 1, 3, 4),
            _match("W", 2, 5, 7, 5),
            _match("W", 3, 1, 5, 6),
        ]

    def test_bande_a_pari_merito(self):
        positions = _positions(self._tabellone_da_otto())

        assert positions[1] == 1, "il vincitore"
        assert positions[5] == 2, "il finalista sconfitto"
        assert positions[3] == positions[7] == 3, "i semifinalisti, a pari merito"
        # La banda successiva riparte da 5, non da 4: i pari merito occupano
        # comunque il loro posto.
        assert {positions[p] for p in (2, 4, 6, 8)} == {5}

    def test_la_finalina_scioglie_la_banda(self):
        """Con il 3°/4° i due semifinalisti smettono di essere pari merito."""
        matches = self._tabellone_da_otto() + [_match("3P", 3, 7, 3, 7)]

        positions = _positions(matches)

        assert positions[1] == 1
        assert positions[5] == 2
        assert positions[7] == 3, "vincitore della finalina"
        assert positions[3] == 4, "perdente della finalina"
        assert {positions[p] for p in (2, 4, 6, 8)} == {5}

    def test_gara_in_corso_chi_e_dentro_e_primo(self):
        """Finché non esci il tabellone non ti ha ancora ordinato."""
        matches = self._tabellone_da_otto()[:4]  # solo il primo turno

        positions = _positions(matches)

        assert {positions[p] for p in (1, 3, 5, 7)} == {1}
        assert {positions[p] for p in (2, 4, 6, 8)} == {5}

    def test_bye_non_producono_eliminati(self):
        """Chi passa senza giocare non fa uscire nessuno."""
        matches = [
            BracketMatch("W", 1, (1,), winner_id=1, loser_id=None, order=0),
            _match("W", 1, 3, 4, 1),
            _match("W", 2, 1, 3, 2),
        ]

        positions = _positions(matches)

        assert positions == {1: 1, 3: 2, 4: 3}


class TestDoppioKO:
    def test_serve_la_seconda_sconfitta_per_uscire(self):
        """Tabellone da 4: chi perde una volta è ancora in gioco."""
        matches = [
            _match("W", 1, 1, 2, 0),
            _match("W", 1, 3, 4, 1),
            _match("W", 2, 1, 3, 2),  # 3 scende nel losers, non esce
            _match("L", 2, 2, 4, 3),  # 4 esce (seconda sconfitta)
            _match("L", 3, 3, 2, 4),  # 2 esce
            _match("GF", 4, 1, 3, 5),  # 3 esce
        ]

        positions = _positions(matches, double_elimination=True)

        assert positions == {1: 1, 3: 2, 2: 3, 4: 4}

    def test_a_meta_gara_chi_ha_una_sconfitta_e_ancora_dentro(self):
        matches = [
            _match("W", 1, 1, 2, 0),
            _match("W", 1, 3, 4, 1),
        ]

        positions = _positions(matches, double_elimination=True)

        # Nessuno è ancora eliminato: tutti primi a pari merito.
        assert set(positions.values()) == {1}

    def test_la_bella_decide_il_primo_posto(self):
        """Se il ripescato vince la finale, conta l'esito della bella."""
        matches = [
            _match("W", 1, 1, 2, 0),
            _match("W", 1, 3, 4, 1),
            _match("W", 2, 1, 3, 2),
            _match("L", 2, 2, 4, 3),
            _match("L", 3, 3, 2, 4),
            _match("GF", 4, 3, 1, 5),  # vince il campione del losers
            _match("GFR", 5, 3, 1, 6),  # e vince anche la bella
        ]

        positions = _positions(matches, double_elimination=True)

        assert positions[3] == 1
        assert positions[1] == 2, "eliminato alla seconda sconfitta, nella bella"


class TestFormulaFisbb:
    """Due fasi, due regole di eliminazione (Step 12).

    Nel girone c'è il recupero e servono due sconfitte; nel tabellone finale
    ne basta una. Senza questa distinzione chi si qualifica imbattuto e perde
    subito il primo match del tabellone finale risulterebbe "ancora in gioco"
    a gara conclusa, cioè primo a pari merito col vincitore.
    """

    def _girone(self):
        """Un girone da 8 giocato per intero: 1 e 3 diretti, 2 e 4 dal recupero.

        Turno 1 = `W1`, turno 2 = `W2` + `L1`, turno 3 = `L2`. `W3` non si
        gioca: i due imbattuti sono già qualificati.
        """
        return [
            _match("W", 1, 1, 2, 0, double=True),
            _match("W", 1, 3, 4, 1, double=True),
            _match("W", 1, 5, 6, 2, double=True),
            _match("W", 1, 7, 8, 3, double=True),
            _match("W", 2, 1, 5, 4, double=True),
            _match("W", 2, 3, 7, 5, double=True),
            _match("L", 2, 2, 6, 6, double=True),  # 6 esce: seconda sconfitta
            _match("L", 2, 4, 8, 7, double=True),  # 8 esce
            _match("L", 3, 2, 7, 8, double=True),  # 7 esce
            _match("L", 3, 4, 5, 9, double=True),  # 5 esce
        ]

    def _gara(self):
        """Girone da 8 più tabellone finale da 4 fra i suoi qualificati."""
        finale = [
            _match("W", 4, 1, 4, 10, double=False),
            _match("W", 4, 3, 2, 11, double=False),
            _match("W", 5, 1, 3, 12, double=False),
        ]
        return self._girone() + finale

    def test_nel_tabellone_finale_basta_una_sconfitta(self):
        """1 e 3 arrivano imbattuti: la prima sconfitta li elimina lo stesso.

        Senza la distinzione fra le due fasi, 3 risulterebbe "ancora in gioco"
        a gara conclusa — cioè primo a pari merito col vincitore — e 2 e 4,
        che una sconfitta ce l'avevano già dal girone, sarebbero gli unici a
        uscire dal tabellone finale.
        """
        positions = _positions(self._gara(), double_elimination=True)

        assert positions[1] == 1, "il vincitore"
        assert positions[3] == 2, "sconfitto in finale, pur essendo imbattuto prima"
        assert positions[2] == positions[4] == 3, "usciti in semifinale, pari merito"

    def test_nel_girone_la_prima_sconfitta_non_elimina(self):
        """2 e 4 perdono al turno 1 e si qualificano lo stesso, dal recupero."""
        positions = _positions(self._gara(), double_elimination=True)

        assert positions[2] < positions[5], "il ripescato sta davanti a chi è uscito"
        assert positions[4] < positions[5]

    def test_chi_non_passa_il_girone_sta_sotto_a_tutti(self):
        positions = _positions(self._gara(), double_elimination=True)

        # 5 e 7 escono al turno 3, 6 e 8 al turno 2: chi resiste di più sta
        # davanti, e i qualificati stanno davanti a entrambe le coppie.
        assert positions[5] == positions[7] == 5
        assert positions[6] == positions[8] == 7


class TestPosizioniDalleBande:
    def test_la_banda_vale_la_sua_posizione_piu_alta(self):
        bande = [[1], [2], [3, 4], [5, 6, 7, 8]]

        assert positions_from_bands(bande) == {
            1: 1,
            2: 2,
            3: 3,
            4: 3,
            5: 5,
            6: 5,
            7: 5,
            8: 5,
        }

    def test_nessuna_banda_nessuna_posizione(self):
        assert positions_from_bands([]) == {}
