"""I preset di configurazione dei direttori: payload e servizio (ADR-082).

Cosa difendono questi test:

* il preset contiene **solo la configurazione** — nome, date, sala, tavoli,
  note e peso non entrano mai, nemmeno quando il modulo li manda;
* modulo → preset → modulo è un'andata e ritorno **senza perdite**: la gara
  che nasce dal modulo precompilato è quella che si era salvata;
* la lettura è **tollerante**: un campo che l'app non conosce più si scarta e
  si segnala, uno che manca resta al default del modulo;
* un preset è del suo proprietario e di nessun altro: per un estraneo non
  esiste (404), un giocatore non ne ha (403).
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from werkzeug.datastructures import MultiDict

from models.base import db
from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from models.preset import payload as formato
from models.preset.models import ConfigPreset, TipoPreset
from models.preset.service import ConfigPresetService
from models.user.models import User
from models.user.role_enum import UserRole
from routes.admin.competition.form_parser import GaraFormParser

GARA = TipoPreset.GARA.value

#: La serata del lunedì al 74, come la scrive il modulo della gara singola.
LUNEDI = [
    ("name", "Lunedì al 74"),
    ("date", "2026-11-02"),
    ("time", "20:30"),
    ("location", "Biliardo 74"),
    ("available_tables", "1,2,3"),
    ("description", "Iscrizioni entro le 20"),
    ("discipline", "9_ball"),
    ("distance", "3"),
    ("rounds_count", "3"),
    ("min_participants", "6"),
    ("max_participants", "12"),
    ("entry_fee", "15"),
    ("withdraw_policy", "Forfeit"),
    ("has_handicap", "true"),
    ("time_limit_minutes", "30"),
    ("start_rule", "lag"),
    ("break_rule", "alternate"),
    ("matchmaking_strategy", "round_robin"),
    ("first_round_policy", "random"),
    ("odd_number_policy", "bye"),
    ("classification_system", "POINTS"),
    ("points_win", "3"),
    ("points_draw", "1"),
    ("points_loss", "0"),
    ("max_groups", "2"),
    ("group_seeding", "elo"),
    ("separate_teammates", "on"),
    ("final_phase_mode", "tabellone"),
    ("qualifiers_per_group", "2"),
    ("third_place_match", "on"),
    ("final_phase_time_limit", "nessuno"),
    ("final_phase_time_limit_minutes", ""),
    ("final_phase_distance_mode", "altra"),
    ("final_phase_distance", "4"),
    ("final_time_limit", "gironi"),
    ("final_time_limit_minutes", ""),
    ("final_distance_mode", "altra"),
    ("final_distance", "5"),
    ("catena_turno", "scontri_diretti,differenza_rack,sorteggio"),
    ("catena_gara", "scontri_diretti,differenza_rack,sorteggio"),
    ("weight", "2"),
]


def _parse(app, coppie):
    with app.test_request_context(method="POST", data=MultiDict(coppie)):
        return GaraFormParser(campionato=None).parse()


def _come_lo_manda_il_browser(coppie_del_preset, base):
    """Il modulo dopo che il JavaScript ha scritto i valori del preset.

    Le caselle spuntate mandano «on» (o il loro `value`), quelle spente non
    mandano niente; il resto manda il testo.
    """
    modulo = MultiDict(base)
    for nome, valore in coppie_del_preset:
        modulo.poplist(nome)
        if valore is True:
            modulo.add(nome, "on")
        elif valore is False:
            continue
        else:
            modulo.add(nome, "" if valore is None else str(valore))
    return modulo


def _utente(role=UserRole.DIRECTOR.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"pre_{uid}", email=f"pre_{uid}@test.local", role=role)
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.flush()
    return user


@pytest.mark.unit
class TestLaWhitelist:
    def test_nome_date_sala_note_e_peso_non_entrano_mai(self):
        ammessi = set(formato.campi_ammessi(GARA))
        for escluso in (
            "name",
            "date",
            "time",
            "location",
            "available_tables",
            "description",
            "weight",
        ):
            assert escluso not in ammessi

    def test_e_derivata_dai_campi_del_modulo(self):
        """Un campo nuovo del modulo entra nel preset senza toccare questa
        lista: la whitelist è il modulo meno gli esclusi."""
        ammessi = formato.campi_ammessi(GARA)
        attesi = tuple(
            c
            for c in GaraFormParser.CAMPI_DEL_MODULO
            if c not in formato.ESCLUSI_DALLA_GARA
        )
        assert ammessi == attesi
        for campo in (
            "distance",
            "max_groups",
            "final_phase_mode",
            "catena_gara",
            "points_win",
            "time_limit_minutes",
        ):
            assert campo in ammessi

    def test_il_payload_contiene_solo_i_campi_ammessi(self, app):
        dati = formato.componi(GARA, _parse(app, LUNEDI))
        assert set(dati["campi"]) <= set(formato.campi_ammessi(GARA))
        assert "name" not in dati["campi"]
        assert "date" not in dati["campi"]
        assert "location" not in dati["campi"]

    def test_componi_scarta_anche_le_chiavi_inventate(self):
        dati = formato.componi(GARA, {"distance": 3, "token": "x", "iscritti": [1]})
        assert dati["campi"] == {"distance": 3}

    def test_il_listino_perde_gli_id_e_le_righe_vuote(self):
        dati = formato.componi(
            GARA,
            {},
            [
                {"nome": "Serie A", "quota": "30", "categoria_id": 7},
                {"nome": "  ", "quota": 10},
                {"nome": "Amatori", "quota": None},
            ],
        )
        assert dati["listino"] == [
            {"nome": "Serie A", "quota": 30.0},
            {"nome": "Amatori", "quota": None},
        ]


@pytest.mark.unit
class TestAndataERitorno:
    def test_modulo_preset_modulo_senza_perdite(self, app):
        """La serata salvata come preset e riapplicata a un modulo vuoto dà la
        stessa gara: stesso parser, stessi valori, campo per campo."""
        prima = _parse(app, LUNEDI)
        salvato = formato.componi(GARA, prima)
        lettura = formato.leggi(GARA, salvato, formato.SCHEMA_VERSION)
        assert lettura.scartati == []

        vuoto = [
            ("name", "Un'altra serata"),
            ("date", "2026-12-07"),
            ("discipline", "8_ball"),
            ("distance", "7"),
            ("matchmaking_strategy", "amalfi"),
            ("catena_turno", ""),
            ("catena_gara", ""),
        ]
        dopo = _parse(
            app,
            _come_lo_manda_il_browser(
                formato.valori_per_il_modulo(lettura.campi), vuoto
            ),
        )
        for campo in formato.campi_ammessi(GARA):
            assert dopo.get(campo) == prima.get(campo), campo
        # Ciò che non è nel preset resta del modulo.
        assert dopo["date"] == date(2026, 12, 7)

    def test_il_listino_fa_il_giro(self):
        dati = formato.componi(GARA, {}, [{"nome": "Serie A", "quota": 30}])
        assert formato.leggi(GARA, dati).listino == [{"nome": "Serie A", "quota": 30.0}]


@pytest.mark.unit
class TestLetturaTollerante:
    def test_un_campo_sconosciuto_si_scarta_e_si_segnala(self):
        lettura = formato.leggi(
            GARA, {"campi": {"distance": 3, "formula_del_2025": "x"}}
        )
        assert lettura.campi == {"distance": 3}
        assert lettura.scartati == ["formula_del_2025"]

    def test_un_campo_mancante_non_si_inventa(self):
        lettura = formato.leggi(GARA, {"campi": {"distance": 3}})
        assert "time_limit_minutes" not in lettura.campi

    def test_un_payload_rovinato_non_rompe(self):
        assert formato.leggi(GARA, {"campi": "boh", "listino": 4}).campi == {}


@pytest.mark.unit
class TestValoriPerIlModulo:
    def test_i_campi_a_due_comandi(self):
        coppie = dict(
            formato.valori_per_il_modulo(
                {
                    "is_race_to": True,
                    "final_phase_time_limit_minutes": 0,
                    "final_time_limit_minutes": 25,
                    "final_phase_distance": None,
                    "final_distance": 5,
                    "has_handicap": False,
                    "time_limit_minutes": 0,
                    "max_participants": None,
                }
            )
        )
        assert coppie["exact_number"] is False
        assert coppie["final_phase_time_limit"] == "nessuno"
        assert coppie["final_phase_time_limit_minutes"] == ""
        assert coppie["final_time_limit"] == "minuti"
        assert coppie["final_time_limit_minutes"] == 25
        assert coppie["final_phase_distance_mode"] == "come"
        assert coppie["final_distance_mode"] == "altra"
        assert coppie["final_distance"] == 5
        assert coppie["has_handicap"] == "false"
        assert coppie["time_limit_minutes"] == ""
        assert coppie["max_participants"] == ""

    def test_la_catena_arriva_all_editor_separata_da_virgole(self):
        coppie = dict(
            formato.valori_per_il_modulo(
                {"catena_gara": '["differenza_rack", "ssr:3"]'}
            )
        )
        assert coppie["catena_gara"] == "differenza_rack,ssr:3"


@pytest.mark.unit
class TestEsplicita:
    def test_dentro_un_campionato_eredita_diventa_esplicito(self):
        from types import SimpleNamespace

        campionato = SimpleNamespace(
            has_handicap=True,
            default_start_rule="lag",
            default_break_rule="winner",
            default_time_limit_minutes=30,
            default_max_groups=None,
            default_group_seeding=None,
            default_final_phase_mode=None,
            default_qualifiers_per_group=None,
        )
        campi = formato.esplicita(
            {"has_handicap": None, "start_rule": None, "time_limit_minutes": None},
            campionato,
        )
        assert campi == {
            "has_handicap": True,
            "start_rule": "lag",
            "time_limit_minutes": 30,
        }

    def test_fuori_dal_campionato_l_handicap_nullo_e_no(self):
        assert formato.esplicita({"has_handicap": None}, None) == {
            "has_handicap": False
        }


@pytest.mark.unit
class TestIlServizio:
    def test_salva_e_ritrova(self, db_session):
        direttore = _utente()
        preset = ConfigPresetService.salva(
            direttore, "  Lunedì   al 74 ", GARA, {"distance": 3, "name": "x"}
        )
        assert preset.name == "Lunedì al 74"
        assert preset.dati == {"campi": {"distance": 3}}
        assert preset.schema_version == formato.SCHEMA_VERSION
        assert ConfigPresetService.preset_di(direttore.id, GARA) == [preset]

    def test_stesso_nome_si_rifiuta_se_non_si_sostituisce(self, db_session):
        direttore = _utente()
        ConfigPresetService.salva(direttore, "Lunedì", GARA, {"distance": 3})
        with pytest.raises(ConflictError):
            ConfigPresetService.salva(direttore, "Lunedì", GARA, {"distance": 5})
        preset = ConfigPresetService.salva(
            direttore, "Lunedì", GARA, {"distance": 5}, sostituisci=True
        )
        assert preset.dati["campi"] == {"distance": 5}
        assert ConfigPreset.query.filter_by(owner_id=direttore.id).count() == 1

    def test_lo_stesso_nome_vale_per_due_direttori_diversi(self, db_session):
        ConfigPresetService.salva(_utente(), "Lunedì", GARA, {})
        ConfigPresetService.salva(_utente(), "Lunedì", GARA, {})

    def test_il_nome_vuoto_si_rifiuta(self, db_session):
        with pytest.raises(ValidationError):
            ConfigPresetService.salva(_utente(), "   ", GARA, {})

    def test_un_giocatore_non_ha_preset(self, db_session):
        with pytest.raises(PermissionDeniedError):
            ConfigPresetService.salva(_utente(UserRole.PLAYER.value), "Mio", GARA, {})

    def test_per_un_estraneo_il_preset_non_esiste(self, db_session):
        preset = ConfigPresetService.salva(_utente(), "Lunedì", GARA, {})
        with pytest.raises(NotFoundError):
            ConfigPresetService.get_mio(preset.id, _utente())
        with pytest.raises(PermissionDeniedError):
            ConfigPresetService.get_mio(preset.id, _utente(UserRole.PLAYER.value))

    def test_per_il_modulo_segnala_cio_che_si_e_perso(self, db_session):
        direttore = _utente()
        preset = ConfigPresetService.salva(direttore, "Vecchio", GARA, {"distance": 3})
        preset.dati = {"campi": {"distance": 3, "campo_sparito": 1}}
        db.session.flush()
        esito = ConfigPresetService.per_il_modulo(preset.id, direttore)
        assert esito["valori"] == [["distance", 3]]
        assert esito["scartati"] == ["campo_sparito"]


@pytest.mark.unit
class TestInterfaccia:
    def test_le_route_si_vedono_dai_direttori_in_produzione(self):
        """ADR-028: senza la voce sarebbero solo dell'admin, in silenzio."""
        from utils.feature_flags import ENDPOINT_ROLES

        for endpoint in (
            "admin.preset.salva_dal_modulo_gara",
            "admin.preset.salva_dalla_gara",
            "admin.preset.valori_per_il_modulo",
        ):
            assert ENDPOINT_ROLES[endpoint] == {"director"}

    def test_la_barra_non_parte_col_modulo_della_gara(self):
        """Selettore e nome del preset stanno dentro il <form> della gara: senza
        `name` non arrivano al server quando si salva la gara."""
        from pathlib import Path

        testo = Path("templates/components/_preset_modulo.html").read_text()
        assert 'name="' not in testo
