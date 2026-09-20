"""Il bersaglio a riquadro (redesign TPA ed esercizi, fase 9b; ADR-066).

Gli schemi di riferimento della disciplina — i drill F1–F5 di Billiard
University — non segnano quasi mai un centro con dei cerchi: segnano una
**zona**, e la domanda è «ci sei dentro o no». Il disegnatore sapeva disegnare
solo i cerchi, e chi voleva una zona la scriveva con la linea libera: un
disegno che il server non legge, quindi un esercizio che non si può fare colpo
per colpo.

Qui si prova la metà che vive sul server: la zona come **dato**, con le stesse
garanzie dei cerchi — un bersaglio solo per scena, misure in quarti di
diamante, e un punteggio che discende dal disegno invece che dal browser.

I riquadri che *non* valgono punti non si convalidano affatto: sono disegno,
come una linea o un testo, e il server non ha motivo di sindacarli.
"""

from __future__ import annotations

import json

import pytest

from models.challenge.diagram import parse_scene
from models.challenge.target import Target, target_from_scene
from models.exceptions import ValidationError


def _riquadro(**campi) -> dict:
    voce = {"type": "zone", "id": "z1", "x": 400, "y": 200, "w": 200, "h": 100}
    voce.update({"value": 1}, **campi)
    return voce


def _scena(*voci) -> str:
    return json.dumps({"v": 4, "orient": "h", "items": list(voci)})


class TestIlRiquadroComeDato:
    def test_si_legge_dalla_scena(self):
        t = target_from_scene(_scena(_riquadro()))
        assert t == Target(x=400, y=200, shape="zone", w=200, h=100, value=1)
        assert t.is_zone and not t.graded
        assert t.max_points == 1

    def test_dentro_vale_fuori_no(self):
        t = target_from_scene(_scena(_riquadro(value=3)))
        assert t is not None
        assert t.points_at(400, 200) == 3  # il centro
        assert t.points_at(495, 245) == 3  # dentro, vicino all'angolo
        assert t.points_at(520, 200) == 0  # oltre il lato lungo
        assert t.points_at(400, 260) == 0  # sotto il lato corto

    def test_sul_bordo_non_e_dentro(self):
        """Stessa regola degli anelli: chi tocca la riga è fuori."""
        t = target_from_scene(_scena(_riquadro()))
        assert t is not None
        assert t.points_at(500, 200) == 0
        assert t.points_at(400, 150) == 0

    def test_la_vicinanza_non_ha_gradazione(self):
        """«Quanto vicino» è una domanda dei cerchi: qui è uno o zero.

        Non è una mancanza da colmare: una gradazione su un rettangolo
        misurerebbe una cosa che l'esercizio non chiede, e la percentuale
        «Posizione» direbbe un numero che nessuno ha deciso.
        """
        t = target_from_scene(_scena(_riquadro()))
        assert t is not None
        assert t.closeness(400, 200) == 1.0
        assert t.closeness(401, 201) == 1.0
        assert t.closeness(700, 200) == 0.0

    def test_le_due_misure_normalizzano_i_due_scarti(self):
        """Lungo e basso: lo scarto in larghezza pesa meno di quello in altezza."""
        t = target_from_scene(_scena(_riquadro(w=400, h=100)))
        assert t is not None
        assert t.scale_x == 200
        assert t.scale_y == 50

    def test_ruotare_e_scambiare_le_misure(self):
        """Non c'è un campo «ruotato»: 90° è w e h scambiate.

        Un dato in meno è un dato che non può contraddire il disegno — e nel
        disegnatore la rotazione resta un pulsante, che scambia le due misure.
        """
        dritto = target_from_scene(_scena(_riquadro(w=200, h=100)))
        girato = target_from_scene(_scena(_riquadro(w=100, h=200)))
        assert dritto is not None and girato is not None
        assert dritto.points_at(480, 200) == 1 and girato.points_at(480, 200) == 0
        assert girato.points_at(400, 280) == 1 and dritto.points_at(400, 280) == 0


class TestCosaSiRifiuta:
    @pytest.mark.parametrize(
        "difetto",
        [
            {"w": 30},  # non è un multiplo di un quarto di diamante
            {"h": 0},
            {"w": 900},  # più lungo del tavolo
            {"h": 500},
            {"value": 0},  # un riquadro che vale zero non è un bersaglio
            {"value": -1},
            {"value": "tre"},
            {"x": 900},  # centro fuori dal panno
            {"y": -1},
        ],
    )
    def test_un_riquadro_storto_si_rifiuta_al_salvataggio(self, difetto):
        with pytest.raises(ValidationError):
            parse_scene(_scena(_riquadro(**difetto)))

    def test_un_bersaglio_solo_anche_fra_forme_diverse(self):
        """Cerchi *e* un riquadro che vale punti sono comunque due bersagli."""
        cerchi = {
            "type": "target",
            "id": "t1",
            "x": 600,
            "y": 200,
            "step": 50,
            "values": [3, 2, 1],
        }
        with pytest.raises(ValidationError):
            parse_scene(_scena(cerchi, _riquadro()))

    def test_due_riquadri_che_valgono_punti_si_rifiutano(self):
        with pytest.raises(ValidationError):
            parse_scene(_scena(_riquadro(), _riquadro(id="z2", x=200)))


class TestIRiquadriDiDisegno:
    """Senza `value` sono disegno: il server non li guarda nemmeno."""

    def test_non_sono_bersagli(self):
        scena = _scena(_riquadro(value=None), _riquadro(id="z2", x=200, value=None))
        assert parse_scene(scena) is not None
        assert target_from_scene(scena) is None

    def test_uno_solo_vale_punti_e_gli_altri_restano(self):
        scena = _scena(
            _riquadro(value=None),
            _riquadro(id="z2", x=200, value=2),
            _riquadro(id="z3", x=650, value=None),
        )
        assert parse_scene(scena) is not None
        bersaglio = target_from_scene(scena)
        assert bersaglio is not None and bersaglio.x == 200 and bersaglio.value == 2

    def test_un_riquadro_di_disegno_storto_non_blocca_il_salvataggio(self):
        """È disegno: sindacarlo sarebbe riscrivere le regole del disegnatore."""
        assert parse_scene(_scena(_riquadro(w=7, h=3, value=None))) is not None

    def test_le_voci_nuove_del_disegnatore_passano(self):
        """Posizioni numerate, richiami e marcatori sono disegno (#179)."""
        scena = _scena(
            {"type": "positions", "id": "p1", "points": [{"x": 100, "y": -46}]},
            {"type": "callout", "id": "c1", "x": 400, "y": 300, "tx": 560, "ty": 360},
            {"type": "marker", "id": "m1", "x": 400, "y": 200},
        )
        assert parse_scene(scena) is not None
        assert target_from_scene(scena) is None
