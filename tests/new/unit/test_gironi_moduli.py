"""I gironi multipli nei moduli, nelle proposte e nelle frasi (ADR-076).

Il dominio ha i suoi test (`test_gironi_regole.py`, `test_gironi_avvio_e_turni.py`);
qui il passaggio interfaccia↔server:

* il modulo della gara legge «Gironi: fino a N» e «Composizione dei gironi»
  solo col girone all'italiana, e rifiuta valori fuori scala;
* la separazione dei compagni vale anche per il girone, quando i gironi
  possono essere più di uno;
* il campionato propone tetto e composizione, e la gara li riceve alla
  nascita (ADR-075);
* la gestione dei ritiri e i dispari si leggono nelle parole giuste col girone.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db
from models.campionato.models import Campionato
from models.campionato.proposte import CAMPI_PROPOSTI
from models.competition.campi_modificabili import STRUTTURA
from models.competition.services import GaraService
from routes.admin.campionato_form_parser import CampionatoFormParser
from routes.admin.competition.form_parser import GaraFormParser

BASE = {
    "date": "2026-12-01",
    "time": "20:00",
    "discipline": "8_ball",
    "distance": "3",
    "rounds_count": "3",
    "min_participants": "2",
    "matchmaking_strategy": "round_robin",
    "first_round_policy": "random",
    "odd_number_policy": "bye",
}


def _parse(app, gara=None, **extra):
    with app.test_request_context(method="POST", data={**BASE, **extra}):
        return GaraFormParser(campionato=None, gara=gara).parse()


@pytest.mark.unit
class TestModuloGara:
    def test_tetto_e_composizione(self, app):
        dati = _parse(app, max_groups="2", group_seeding="elo")
        assert dati["max_groups"] == 2
        assert dati["group_seeding"] == "elo"

    def test_assenti_non_si_toccano(self, app):
        dati = _parse(app)
        assert "max_groups" not in dati
        assert "group_seeding" not in dati

    @pytest.mark.parametrize("grezzo", ["0", "9", "tanti"])
    def test_tetto_fuori_scala_si_rifiuta(self, app, grezzo):
        with pytest.raises(ValueError):
            _parse(app, max_groups=grezzo)

    def test_composizione_sconosciuta_si_rifiuta(self, app):
        with pytest.raises(ValueError):
            _parse(app, max_groups="2", group_seeding="serpentina")

    def test_fuori_dal_girone_non_si_leggono(self, app):
        dati = _parse(app, matchmaking_strategy="amalfi", max_groups="2")
        assert "max_groups" not in dati

    def test_compagni_separati_nei_gironi(self, app):
        dati = _parse(app, max_groups="2", separate_teammates="on")
        assert dati["separate_teammates"] is True

    def test_girone_unico_non_separa(self, app):
        dati = _parse(app, max_groups="1", separate_teammates="on")
        assert dati["separate_teammates"] is False

    def test_sono_campi_del_modulo_e_della_struttura(self):
        for campo in ("max_groups", "group_seeding"):
            assert campo in GaraFormParser.CAMPI_DEL_MODULO
            assert campo in STRUTTURA


@pytest.mark.unit
class TestModuloCampionato:
    def _gironi(self, app, **dati):
        with app.test_request_context(method="POST", data=dati):
            from flask import request

            return CampionatoFormParser.parse_gironi(request.form)

    def test_assenti_non_si_toccano(self, app):
        assert self._gironi(app) == {}

    def test_tetto_e_composizione(self, app):
        valori = self._gironi(
            app, default_max_groups="2", default_group_seeding="categoria"
        )
        assert valori == {
            "default_max_groups": 2,
            "default_group_seeding": "categoria",
        }

    def test_fuori_scala_si_rifiuta(self, app):
        with pytest.raises(ValueError):
            self._gironi(app, default_max_groups="12")


@pytest.mark.unit
class TestProposta:
    def test_il_campionato_li_propone(self):
        assert CAMPI_PROPOSTI["default_max_groups"] == "max_groups"
        assert CAMPI_PROPOSTI["default_group_seeding"] == "group_seeding"

    def test_la_gara_li_riceve_alla_nascita(self, app, db_session):
        camp = Campionato(
            name=f"Lunedì al 74 {uuid.uuid4().hex[:6]}",
            campionato_type="round_robin",
            # I gironi li propone solo un campionato a piazzamenti: chi somma
            # i totali resta a girone unico (ADR-080).
            default_classification_system="POSITION",
            is_active=True,
            default_max_groups=2,
            default_group_seeding="elo",
        )
        db.session.add(camp)
        db.session.commit()
        gara = GaraService.create_gara(
            campionato_id=camp.id,
            number=1,
            name="Serata 1",
            date=date.today() + timedelta(days=7),
            discipline="8_ball",
            distance=3,
            matchmaking_strategy="round_robin",
            first_round_policy="random",
            odd_number_policy="bye",
            rounds_count=3,
        )
        assert gara.max_groups == 2
        assert gara.group_seeding == "elo"


@pytest.mark.unit
class TestParole:
    def test_escludere_nel_girone_da_la_vittoria_a_tavolino(self, app):
        from utils.jinja import etichetta_ritiro

        with app.test_request_context():
            girone = etichetta_ritiro("Exclude", "round_robin")
            altro = etichetta_ritiro("Exclude", "amalfi")
        assert "tavolino" in girone and "X" not in girone
        assert "X" in altro

    def test_la_frase_dei_gironi(self, app):
        from models.competition.gironi_service import descrivi_gironi
        from models.matchmaking.gironi import ComposizioneGironi

        with app.test_request_context():
            prima = descrivi_gironi(None, 2, ComposizioneGironi.ELO, False)
            dopo = descrivi_gironi([6, 5], 2, ComposizioneGironi.ELO, True)
        assert "2" in prima and "ELO" in prima
        assert "6" in dopo and "5" in dopo and "compagni" in dopo

    def test_l_anteprima_dice_i_turni(self, app, db_session):
        from models.competition.gironi_service import Anteprima

        anteprima = Anteprima(
            iscritti=11,
            tetto=2,
            massimo=2,
            proposta=2,
            taglie={1: [11], 2: [6, 5]},
        )
        assert anteprima.turni == {1: 11, 2: 5}
