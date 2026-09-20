"""Il riepilogo di fine prova (fase 5d): la nuvola letta, e i numeri.

La nuvola dei punti d'arrivo è l'informazione che nessun punteggio riassume, e
qui diventa una frase: **dove** si sbaglia, non quanto. Le due direzioni
vogliono dire due cose diverse — lungo/corto è forza, destra/sinistra è mira —
e sotto una soglia non si dice niente, perché dare una direzione a una nuvola
dispersa è dare una correzione a chi non ne ha bisogno.
"""

from __future__ import annotations

from types import SimpleNamespace as Colpo

import pytest

from models.challenge.dispersion import read_dispersion
from models.challenge.shot_stats import longest_made_streak
from models.challenge.target import Target

# Centro a (600, 200), anelli da 50: raggio esterno 150.
BERSAGLIO = Target(x=600, y=200, step=50, values=(3, 2, 1))


def _colpi(*punti):
    """Un colpo per punto; `None` è una mancata, che non ha posizione."""
    return [
        Colpo(
            made=p is not None,
            x=None if p is None else p[0],
            y=None if p is None else p[1],
        )
        for p in punti
    ]


class TestQuandoNonSiLegge:
    def test_senza_bersaglio_non_c_e_nuvola(self):
        assert read_dispersion(_colpi((600, 200)), None) is None

    def test_senza_imbucate_non_c_e_nuvola(self):
        """Il colpo mancato non ha un punto d'arrivo: non si inventa."""
        assert read_dispersion(_colpi(None, None), BERSAGLIO) is None

    def test_solo_le_imbucate_entrano(self):
        lettura = read_dispersion(_colpi((600, 200), None, (650, 200)), BERSAGLIO)
        assert lettura is not None and lettura.count == 2


class TestLaLettura:
    def test_attorno_al_centro_non_si_dice_una_direzione(self):
        """Scarti che si annullano: nessuna correzione da dare."""
        lettura = read_dispersion(
            _colpi((580, 200), (620, 200), (600, 180), (600, 220)), BERSAGLIO
        )
        assert lettura is not None
        assert lettura.bias_x == 0 and lettura.bias_y == 0
        assert "attorno al centro" in lettura.headline

    def test_sotto_la_soglia_resta_dispersione(self):
        """Lo scarto medio è 30 su un raggio di 150: un quinto, sotto un quarto."""
        lettura = read_dispersion(_colpi((630, 200), (630, 200)), BERSAGLIO)
        assert lettura is not None
        assert lettura.bias_x == 30
        assert "attorno al centro" in lettura.headline

    def test_lungo_e_forza(self):
        """Oltre il centro verso la sponda corta: 60 su 150, due quinti."""
        lettura = read_dispersion(_colpi((660, 200), (660, 205)), BERSAGLIO)
        assert lettura is not None
        assert lettura.headline == "Arrivi lungo"
        assert "è forza, non mira." in lettura.detail
        assert "2 battenti su 2" in lettura.detail

    def test_corto_e_sempre_forza(self):
        lettura = read_dispersion(_colpi((540, 200), (535, 200)), BERSAGLIO)
        assert lettura is not None
        assert lettura.headline == "Arrivi corto"
        assert "è forza, non mira." in lettura.detail

    def test_di_lato_e_mira(self):
        lettura = read_dispersion(_colpi((600, 260), (600, 265)), BERSAGLIO)
        assert lettura is not None
        assert lettura.headline == "Arrivi a destra"
        assert "è mira, non forza." in lettura.detail

    def test_le_due_direzioni_insieme(self):
        lettura = read_dispersion(_colpi((660, 260), (665, 265)), BERSAGLIO)
        assert lettura is not None
        assert lettura.headline == "Arrivi lungo, e a destra"
        assert "è forza e mira insieme." in lettura.detail

    def test_conta_quanti_vanno_dalla_stessa_parte(self):
        """Tre lunghi e uno corto: la frase dice tre su quattro, non quattro."""
        lettura = read_dispersion(
            _colpi((700, 200), (700, 200), (700, 200), (590, 200)), BERSAGLIO
        )
        assert lettura is not None
        assert lettura.headline == "Arrivi lungo"
        assert "3 battenti su 4" in lettura.detail


class TestLaSerie:
    @pytest.mark.parametrize(
        "esiti,attesa",
        [
            ([], 0),
            ([False, False], 0),
            ([True, True, False, True], 2),
            ([False, True, True, True], 3),
            ([True] * 5, 5),
        ],
    )
    def test_la_serie_piu_lunga_di_imbucate(self, esiti, attesa):
        colpi = [Colpo(made=e, x=None, y=None) for e in esiti]
        assert longest_made_streak(colpi) == attesa
