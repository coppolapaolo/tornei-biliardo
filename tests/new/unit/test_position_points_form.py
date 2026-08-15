"""Tabella punti per posizione configurabile sul campionato (US-17).

La colonna `campionato.position_points`, i default della spec e il calcolo
esistevano già: mancava il modo di configurarli, quindi nessun director poteva
scostarsi dai 25/18/15/12. Qui si copre il giro form → colonna.

Si chiedono le **soglie** e non le sedici posizioni, perché
`points_for_position` risolve già una posizione scoperta con la prima soglia
che la contiene: sei caselle bastano a dire tutto.
"""

import json

import pytest
from werkzeug.datastructures import MultiDict

from models.classification.position_points import (
    DEFAULT_POSITION_POINTS,
    form_rows,
    points_for_position,
)
from routes.admin.campionato_form_parser import parse_position_points

pytestmark = pytest.mark.unit


def _form(valori):
    """Form con una casella per soglia (le chiavi sono interi, non kwargs)."""
    return MultiDict(
        {f"position_points_{soglia}": str(punti) for soglia, punti in valori.items()}
    )


class TestParsing:
    def test_i_valori_di_default_non_si_salvano(self):
        """Un campionato non configurato deve **seguire** il default.

        Salvarne una copia lo congelerebbe: se un domani la tabella di default
        cambia, quel campionato resterebbe indietro senza che nessuno l'abbia
        deciso.
        """
        form = _form({soglia: punti for soglia, punti in DEFAULT_POSITION_POINTS})
        assert parse_position_points(form) is None

    def test_un_form_vuoto_vale_il_default(self):
        assert parse_position_points(MultiDict()) is None

    def test_una_tabella_diversa_si_salva(self):
        form = _form({1: 30, 2: 18, 3: 15, 4: 12, 8: 8, 16: 4})
        salvata = parse_position_points(form)
        assert salvata is not None
        assert json.loads(salvata)["1"] == 30

    def test_le_soglie_non_toccate_restano_al_default(self):
        """Cambiarne una non deve azzerare le altre cinque."""
        form = _form({1: 30})
        salvata = parse_position_points(form)
        assert salvata is not None
        decoded = json.loads(salvata)
        assert decoded["1"] == 30
        assert decoded["8"] == 8  # default della banda 5°-8°

    def test_un_valore_illeggibile_ricade_sul_default_di_quella_soglia(self):
        form = MultiDict({"position_points_1": "tanti", "position_points_2": "20"})
        salvata = parse_position_points(form)
        assert salvata is not None
        decoded = json.loads(salvata)
        assert decoded["1"] == 25
        assert decoded["2"] == 20

    def test_i_punti_negativi_diventano_zero(self):
        form = _form({16: -5})
        salvata = parse_position_points(form)
        assert salvata is not None
        assert json.loads(salvata)["16"] == 0


class TestRigheDelForm:
    def test_senza_campionato_valgono_i_default(self):
        righe = form_rows(None)
        assert [(soglia, punti) for soglia, _label, punti in righe] == list(
            DEFAULT_POSITION_POINTS
        )

    def test_le_etichette_descrivono_la_banda(self):
        """La banda è la posizione: chi esce insieme prende gli stessi punti."""
        etichette = [label for _s, label, _p in form_rows(None)]
        assert etichette == ["1°", "2°", "3°", "4°", "5°-8°", "9°-16°"]

    def test_i_valori_configurati_prevalgono(self):
        class Campionato:
            position_points = json.dumps({"1": 30, "8": 6})

        valori = {soglia: punti for soglia, _label, punti in form_rows(Campionato())}
        assert valori[1] == 30
        assert valori[8] == 6
        assert valori[2] == 18  # non configurata → default


class TestGiroCompleto:
    def test_le_soglie_salvate_coprono_le_posizioni_intermedie(self):
        """Sei soglie bastano: il 6° prende i punti della banda 5°-8°."""
        salvata = parse_position_points(_form({1: 30, 8: 6}))
        assert salvata is not None
        tabella = {int(k): v for k, v in json.loads(salvata).items()}

        assert points_for_position(1, tabella) == 30
        assert points_for_position(6, tabella) == 6
        assert points_for_position(8, tabella) == 6
        assert points_for_position(12, tabella) == 4  # banda 9°-16°
