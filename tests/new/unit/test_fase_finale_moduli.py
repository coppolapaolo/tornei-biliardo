"""La fase finale dopo i gironi nei moduli, nelle proposte e nelle frasi.

Il dominio ha i suoi test (`test_gironi_fase_finale_regole.py`,
`test_gironi_tabellone_finale.py`); qui il passaggio interfaccia↔server
(ADR-081, «Configurazione sulla gara»):

* il modulo della gara legge fase finale, qualificati per girone, finalina e
  limite di tempo della fase finale solo col girone all'italiana, e solo
  quando i gironi possono essere più di uno;
* «finali per piazzamento» ha i suoi test in `test_finali_per_piazzamento_moduli.py`;
* il campionato a piazzamenti propone i quattro valori, e la gara li riceve
  alla nascita (ADR-075);
* un campionato che passa a sommare i totali toglie la fase finale;
* la frase del regolamento e la storia li dicono in parole.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db
from models.campionato.models import Campionato
from models.campionato.proposte import CAMPI_PROPOSTI
from models.competition.campi_modificabili import REGOLE, STRUTTURA
from models.competition.services import GaraService
from models.matchmaking.fase_finale import LimiteDellaFaseFinale, limite_dal_modulo
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
    "max_groups": "2",
}

TABELLONE = {
    "final_phase_mode": "tabellone",
    "qualifiers_per_group": "2",
    "third_place_match": "on",
    "final_phase_time_limit": "gironi",
}


def _parse(app, gara=None, **extra):
    with app.test_request_context(method="POST", data={**BASE, **extra}):
        return GaraFormParser(campionato=None, gara=gara).parse()


@pytest.mark.unit
class TestModuloGara:
    def test_tabellone_con_finalina(self, app):
        dati = _parse(app, **TABELLONE)
        assert dati["final_phase_mode"] == "tabellone"
        assert dati["qualifiers_per_group"] == 2
        assert dati["third_place_match"] is True
        assert dati["final_phase_time_limit_minutes"] is None

    def test_assenti_non_si_toccano(self, app):
        dati = _parse(app)
        for campo in (
            "final_phase_mode",
            "qualifiers_per_group",
            "final_phase_time_limit_minutes",
        ):
            assert campo not in dati

    def test_la_finalina_vuole_il_tabellone(self, app):
        dati = _parse(app, final_phase_mode="nessuna", third_place_match="on")
        assert dati["final_phase_mode"] == "nessuna"
        assert dati["third_place_match"] is False

    def test_col_girone_unico_niente_fase_finale(self, app):
        """Il tabellone è fra i primi di ogni girone: col girone unico non c'è.

        Il blocco della fase finale si spegne quando il tetto scende a 1, e
        il modulo non lo manda: la gara non deve restare col tabellone di
        prima, che il servizio rifiuterebbe.
        """
        dati = _parse(app, max_groups="1")
        assert dati["final_phase_mode"] == "nessuna"
        assert dati["third_place_match"] is False

    def test_piazzamento_con_due_gironi(self, app):
        """Dal 2026-10-12 si sceglie (`test_finali_per_piazzamento_moduli.py`)."""
        dati = _parse(app, final_phase_mode="piazzamento")
        assert dati["final_phase_mode"] == "piazzamento"

    def test_fase_sconosciuta_si_rifiuta(self, app):
        with pytest.raises(ValueError):
            _parse(app, final_phase_mode="semifinali")

    @pytest.mark.parametrize("grezzo", ["0", "9", "tanti"])
    def test_qualificati_fuori_scala_si_rifiutano(self, app, grezzo):
        with pytest.raises(ValueError):
            _parse(app, **{**TABELLONE, "qualifiers_per_group": grezzo})

    @pytest.mark.parametrize(
        "modo,minuti,atteso",
        [("gironi", "", None), ("nessuno", "", 0), ("minuti", "45", 45)],
    )
    def test_limite_della_fase_finale(self, app, modo, minuti, atteso):
        dati = _parse(
            app,
            **{
                **TABELLONE,
                "final_phase_time_limit": modo,
                "final_phase_time_limit_minutes": minuti,
            },
        )
        assert dati["final_phase_time_limit_minutes"] == atteso

    @pytest.mark.parametrize("minuti", ["", "0", "601", "mezzora"])
    def test_minuti_della_fase_finale_fuori_scala(self, app, minuti):
        with pytest.raises(ValueError):
            _parse(
                app,
                **{
                    **TABELLONE,
                    "final_phase_time_limit": "minuti",
                    "final_phase_time_limit_minutes": minuti,
                },
            )

    def test_fuori_dal_girone_non_si_leggono(self, app):
        dati = _parse(app, matchmaking_strategy="amalfi", **TABELLONE)
        assert "final_phase_mode" not in dati
        assert dati["third_place_match"] is False

    def test_sul_tabellone_la_finalina_resta_quella_del_tabellone(self, app):
        dati = _parse(
            app,
            matchmaking_strategy="direct_elimination",
            max_participants="8",
            third_place_match="on",
        )
        assert dati["third_place_match"] is True
        assert "final_phase_mode" not in dati

    def test_sono_campi_del_modulo(self):
        for campo in (
            "final_phase_mode",
            "qualifiers_per_group",
            "final_phase_time_limit_minutes",
        ):
            assert campo in GaraFormParser.CAMPI_DEL_MODULO

    def test_struttura_e_regole_della_gara_avviata(self):
        """Quale fase si gioca è struttura; il limite della fase finale è una
        regola di gioco, che vale dal turno successivo (ADR-075)."""
        assert {"final_phase_mode", "qualifiers_per_group"} <= set(STRUTTURA)
        assert "final_phase_time_limit_minutes" in REGOLE


@pytest.mark.unit
class TestLimiteDalModulo:
    def test_tre_stati(self):
        assert limite_dal_modulo(LimiteDellaFaseFinale.COME_I_GIRONI.value, "") is None
        assert limite_dal_modulo(LimiteDellaFaseFinale.SENZA.value, "30") == 0
        assert limite_dal_modulo(LimiteDellaFaseFinale.MINUTI.value, "30") == 30

    def test_il_modo_del_valore_salvato(self):
        assert LimiteDellaFaseFinale.del_valore(None) is (
            LimiteDellaFaseFinale.COME_I_GIRONI
        )
        assert LimiteDellaFaseFinale.del_valore(0) is LimiteDellaFaseFinale.SENZA
        assert LimiteDellaFaseFinale.del_valore(45) is LimiteDellaFaseFinale.MINUTI


@pytest.mark.unit
class TestGaraAvviata:
    def test_il_limite_della_fase_finale_si_cambia_a_gara_avviata(self, app):
        data = {
            "final_phase_time_limit": "minuti",
            "final_phase_time_limit_minutes": "40",
        }
        with app.test_request_context(method="POST", data=data):
            dati = GaraFormParser(gara=None).parse_a_gara_avviata(
                {"final_phase_time_limit_minutes"}
            )
        assert dati == {"final_phase_time_limit_minutes": 40}


@pytest.mark.unit
class TestModuloCampionato:
    def _gironi(self, app, **dati):
        with app.test_request_context(method="POST", data=dati):
            from flask import request

            return CampionatoFormParser.parse_gironi(request.form)

    def test_assenti_non_si_toccano(self, app):
        assert self._gironi(app) == {}

    def test_la_fase_finale_proposta(self, app):
        valori = self._gironi(
            app,
            default_max_groups="2",
            default_final_phase_mode="tabellone",
            default_qualifiers_per_group="2",
            default_third_place_match="on",
            default_final_phase_time_limit="nessuno",
        )
        assert valori["default_final_phase_mode"] == "tabellone"
        assert valori["default_qualifiers_per_group"] == 2
        assert valori["default_third_place_match"] is True
        assert valori["default_final_phase_time_limit_minutes"] == 0

    def test_col_girone_unico_nessuna(self, app):
        valori = self._gironi(app, default_max_groups="1")
        assert valori["default_final_phase_mode"] == "nessuna"
        assert valori["default_third_place_match"] is False


def _campionato(**extra):
    camp = Campionato(
        name=f"Lunedì al 74 {uuid.uuid4().hex[:6]}",
        campionato_type="round_robin",
        default_classification_system="POSITION",
        is_active=True,
        default_max_groups=2,
        **extra,
    )
    db.session.add(camp)
    db.session.commit()
    return camp


def _gara(camp, numero=1, **extra):
    return GaraService.create_gara(
        campionato_id=camp.id,
        number=numero,
        name=f"Serata {numero}",
        date=date.today() + timedelta(days=7 * numero),
        discipline="8_ball",
        distance=3,
        is_race_to=True,
        matchmaking_strategy=extra.pop("matchmaking_strategy", "round_robin"),
        first_round_policy="random",
        odd_number_policy="bye",
        rounds_count=3,
        **extra,
    )


@pytest.mark.unit
class TestProposta:
    def test_il_campionato_li_propone(self):
        assert CAMPI_PROPOSTI["default_final_phase_mode"] == "final_phase_mode"
        assert CAMPI_PROPOSTI["default_qualifiers_per_group"] == "qualifiers_per_group"
        assert CAMPI_PROPOSTI["default_third_place_match"] == "third_place_match"
        assert (
            CAMPI_PROPOSTI["default_final_phase_time_limit_minutes"]
            == "final_phase_time_limit_minutes"
        )

    def test_la_gara_li_riceve_alla_nascita(self, app, db_session):
        camp = _campionato(
            default_final_phase_mode="tabellone",
            default_qualifiers_per_group=1,
            default_third_place_match=True,
            default_final_phase_time_limit_minutes=0,
        )
        gara = _gara(camp)
        assert gara.final_phase_mode == "tabellone"
        assert gara.qualifiers_per_group == 1
        assert gara.third_place_match is True
        assert gara.final_phase_time_limit_minutes == 0
        assert gara.ha_tabellone_finale

    def test_la_finalina_del_girone_non_arriva_al_tabellone(self, app, db_session):
        """La finalina proposta è quella del tabellone dopo i gironi: una gara
        a eliminazione diretta dello stesso campionato decide la sua."""
        camp = _campionato(
            default_final_phase_mode="tabellone", default_third_place_match=True
        )
        gara = _gara(
            camp, matchmaking_strategy="direct_elimination", max_participants=8
        )
        assert gara.third_place_match is False

    def test_la_proposta_arriva_solo_al_girone(self, app, db_session):
        from models.campionato.proposte import proposta

        camp = _campionato()
        girone = _gara(camp, 1)
        tabellone = _gara(
            camp, 2, matchmaking_strategy="direct_elimination", max_participants=8
        )
        righe = proposta(camp, {"default_third_place_match": (False, True)})
        gare = {riga.gara.id for riga in righe}
        assert girone.id in gare
        assert tabellone.id not in gare

    def test_sommando_i_totali_la_fase_finale_se_ne_va(self, app, db_session):
        """Nei campionati che sommano i totali non c'è fase finale (ADR-081):
        passando a sommare, le gare da avviare la perdono, e la storia lo
        scrive."""
        from models.campionato.tournament_service import TournamentService

        camp = _campionato(default_final_phase_mode="tabellone")
        gara = _gara(camp)
        assert gara.ha_tabellone_finale
        TournamentService().update_campionato(
            camp.id, default_classification_system="WINS"
        )
        db.session.refresh(gara)
        db.session.refresh(camp)
        assert gara.final_phase_mode == "nessuna"
        assert camp.default_final_phase_mode == "nessuna"


@pytest.mark.unit
class TestParole:
    def test_la_frase_dice_il_tabellone(self, app):
        from models.competition.gironi_service import descrivi_fase_finale

        with app.test_request_context():
            frase = descrivi_fase_finale(2, True, None)
        assert "tabellone" in frase and "2" in frase and "finalina" in frase

    def test_la_frase_dice_il_limite_diverso(self, app):
        from models.competition.gironi_service import descrivi_fase_finale

        with app.test_request_context():
            senza = descrivi_fase_finale(1, False, 0)
            minuti = descrivi_fase_finale(2, False, 45)
        assert "finalina" not in senza and "senza limite" in senza
        assert "45" in minuti

    def test_la_frase_dei_gironi_porta_la_fase_finale(self, app, db_session):
        from models.competition.gironi_service import GironiService

        camp = _campionato(
            default_final_phase_mode="tabellone", default_third_place_match=True
        )
        gara = _gara(camp)
        with app.test_request_context():
            frase = GironiService.frase(gara)
        assert frase is not None
        assert "tabellone" in frase and "finalina" in frase

    def test_la_storia_in_parole(self, app):
        from models.storia.etichette import etichetta, valore

        with app.test_request_context():
            assert valore("final_phase_time_limit_minutes", "") == "come i gironi"
            assert valore("final_phase_time_limit_minutes", "0") == "senza limite"
            assert "45" in valore("final_phase_time_limit_minutes", "45")
            assert (
                valore("default_final_phase_time_limit_minutes", "") == "come i gironi"
            )
            assert etichetta("final_phase_mode") != "final_phase_mode"
            assert etichetta("qualifiers_per_group") != "qualifiers_per_group"
            assert etichetta("default_final_phase_mode") != "default_final_phase_mode"
            assert valore("final_phase_mode", "piazzamento") != "piazzamento"


@pytest.mark.unit
class TestRegolamentoDelCampionato:
    def _campi(self, camp):
        from models.storia.regolamento import CAMPI_DEL_CAMPIONATO, _impostazioni

        return {
            i.campo: i.valore for i in _impostazioni(camp, CAMPI_DEL_CAMPIONATO, [])
        }

    def test_senza_tabellone_tacciono(self, app, db_session):
        campi = self._campi(_campionato())
        assert campi["default_final_phase_mode"] == "nessuna"
        assert "default_qualifiers_per_group" not in campi
        assert "default_final_phase_time_limit_minutes" not in campi

    def test_col_tabellone_si_leggono(self, app, db_session):
        campi = self._campi(
            _campionato(
                default_final_phase_mode="tabellone", default_third_place_match=True
            )
        )
        assert campi["default_qualifiers_per_group"] == "2"
        assert campi["default_third_place_match"] == "true"
        # «Come i gironi» si dice anche se il valore è vuoto.
        assert campi["default_final_phase_time_limit_minutes"] == ""
