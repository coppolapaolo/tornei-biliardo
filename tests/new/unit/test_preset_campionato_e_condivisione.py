"""Preset di campionato e condivisione fra direttori (ADR-082, parte B).

Cosa difendono questi test:

* il preset di campionato contiene **solo la configurazione** — nome e sede
  restano fuori — e la whitelist è derivata dai campi del modulo del
  campionato (`CampionatoFormParser.CAMPI_DEL_MODULO`), in un posto solo;
* modulo del campionato → preset → modulo è un'andata e ritorno **senza
  perdite**, catene e punti per posizione compresi;
* condividere crea **una copia per destinatario**, indipendente
  dall'originale, che ricorda da chi arriva e quando; il nome già presente
  prende il suffisso «(da X)», e un numero se anche quello c'è;
* si condivide solo con direttori (o admin); un preset che non è tuo non si
  condivide, non si rinomina, non si cancella (404);
* chi riceve ha una notifica nella **propria** lingua (ADR-062).
"""

from __future__ import annotations

import uuid

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
from routes.admin.campionato_form_parser import CampionatoFormParser

GARA = TipoPreset.GARA.value
CAMPIONATO = TipoPreset.CAMPIONATO.value

#: Il campionato del lunedì, come lo scrive il modulo di modifica.
LUNEDI = [
    ("name", "Campionato del lunedì"),
    ("campionato_type", "round_robin"),
    ("planned_gare_count", "8"),
    ("challenge_mode", "on"),
    ("default_classification_system", "POINTS"),
    ("default_venue_id", "4"),
    ("default_entry_fee", "15"),
    ("default_rounds_count", "4"),
    ("default_odd_policy", "bye"),
    ("default_first_round_policy", "classification"),
    ("default_anti_rematch", "on"),
    ("default_start_rule", "lag"),
    ("default_break_rule", "alternate"),
    ("has_handicap", "on"),
    ("default_time_limit_minutes", "30"),
    ("default_points_win", "3"),
    ("default_points_draw", "1"),
    ("default_points_loss", "0"),
    ("default_max_groups", "2"),
    ("default_group_seeding", "elo"),
    ("default_final_phase_mode", "tabellone"),
    ("default_qualifiers_per_group", "2"),
    ("default_third_place_match", "on"),
    ("default_final_phase_time_limit", "minuti"),
    ("default_final_phase_time_limit_minutes", "40"),
    ("default_final_phase_distance_mode", "altra"),
    ("default_final_phase_distance", "4"),
    ("default_final_time_limit", "gironi"),
    ("default_final_time_limit_minutes", ""),
    ("default_final_distance_mode", "altra"),
    ("default_final_distance", "5"),
    ("default_catena_turno", "scontri_diretti,differenza_rack,sorteggio"),
    ("default_catena_gara", "differenza_rack,sorteggio"),
    ("catena_generale", "scontri_diretti,sorteggio"),
    ("position_points_1", "30"),
    ("position_points_2", "20"),
]


def _parse(coppie, ripiego="amalfi"):
    return CampionatoFormParser.parse_configurazione(MultiDict(coppie), ripiego)


def _come_lo_manda_il_browser(coppie_del_preset, base):
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


def _utente(role=UserRole.DIRECTOR.value, language=None) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"pc_{uid}", email=f"pc_{uid}@test.local", role=role)
    if language:
        user.language = language
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.flush()
    return user


@pytest.mark.unit
class TestLaWhitelistDelCampionato:
    def test_nome_e_sede_non_entrano_mai(self):
        ammessi = set(formato.campi_ammessi(CAMPIONATO))
        assert "name" not in ammessi
        assert "default_venue_id" not in ammessi
        for campo in (
            "campionato_type",
            "default_classification_system",
            "default_max_groups",
            "default_catena_gara",
            "catena_generale",
            "position_points",
            "default_points_win",
            "default_first_round_policy",
        ):
            assert campo in ammessi

    def test_e_derivata_dai_campi_del_modulo_del_campionato(self):
        attesi = tuple(
            c
            for c in CampionatoFormParser.CAMPI_DEL_MODULO
            if c not in formato.ESCLUSI_DAL_CAMPIONATO
        )
        assert formato.campi_ammessi(CAMPIONATO) == attesi

    def test_i_campi_del_modulo_sono_quelli_che_il_parser_legge(self, app):
        """La lista e il parser non possono divergere: un campo nuovo del
        modulo del campionato, letto dal parser, deve stare nella lista."""
        with app.test_request_context():
            letti = set(_parse(LUNEDI))
        assert letti | {"name"} == set(CampionatoFormParser.CAMPI_DEL_MODULO)

    def test_il_payload_contiene_solo_i_campi_ammessi(self, app):
        with app.test_request_context():
            dati = formato.componi(CAMPIONATO, {**_parse(LUNEDI), "name": "x"})
        assert set(dati["campi"]) <= set(formato.campi_ammessi(CAMPIONATO))
        assert "default_venue_id" not in dati["campi"]
        assert "name" not in dati["campi"]

    def test_un_campo_della_gara_non_entra_in_un_preset_di_campionato(self):
        dati = formato.componi(CAMPIONATO, {"distance": 3, "default_rounds_count": 4})
        assert dati["campi"] == {"default_rounds_count": 4}


@pytest.mark.unit
class TestAndataERitornoDelCampionato:
    def test_modulo_preset_modulo_senza_perdite(self, app):
        with app.test_request_context():
            prima = _parse(LUNEDI)
            lettura = formato.leggi(
                CAMPIONATO, formato.componi(CAMPIONATO, prima), formato.SCHEMA_VERSION
            )
            assert lettura.scartati == []
            vuoto = [
                ("name", "Un altro campionato"),
                ("campionato_type", "amalfi"),
                ("default_classification_system", "WINS"),
                ("default_catena_turno", ""),
                ("default_catena_gara", ""),
                ("catena_generale", ""),
            ]
            dopo = _parse(
                _come_lo_manda_il_browser(
                    formato.valori_per_il_modulo(lettura.campi, CAMPIONATO), vuoto
                )
            )
        for campo in formato.campi_ammessi(CAMPIONATO):
            assert dopo.get(campo) == prima.get(campo), campo

    def test_le_catene_arrivano_all_editor_separate_da_virgole(self):
        coppie = dict(
            formato.valori_per_il_modulo(
                {
                    "default_catena_turno": '["scontri_diretti", "sorteggio"]',
                    "catena_generale": "[]",
                },
                CAMPIONATO,
            )
        )
        assert coppie["default_catena_turno"] == "scontri_diretti,sorteggio"
        assert coppie["catena_generale"] == ""

    def test_i_punti_per_posizione_tornano_nelle_sei_caselle(self):
        from models.classification.position_points import DEFAULT_POSITION_POINTS

        coppie = dict(
            formato.valori_per_il_modulo(
                {"position_points": '{"1": 30, "2": 20}'}, CAMPIONATO
            )
        )
        assert coppie["position_points_1"] == 30
        assert coppie["position_points_2"] == 20
        soglia, default = DEFAULT_POSITION_POINTS[-1]
        assert coppie[f"position_points_{soglia}"] == default

    def test_senza_tabella_i_punti_tornano_al_default(self):
        from models.classification.position_points import DEFAULT_POSITION_POINTS

        coppie = dict(
            formato.valori_per_il_modulo({"position_points": None}, CAMPIONATO)
        )
        for soglia, default in DEFAULT_POSITION_POINTS:
            assert coppie[f"position_points_{soglia}"] == default

    def test_l_handicap_del_campionato_e_una_casella(self):
        coppie = dict(formato.valori_per_il_modulo({"has_handicap": True}, CAMPIONATO))
        assert coppie["has_handicap"] is True


@pytest.mark.unit
class TestDalCampionatoEsistente:
    def test_legge_le_colonne_e_le_catene_che_valgono(self, db_session):
        from models import Campionato

        campionato = Campionato(
            name="Lunedì",
            campionato_type="amalfi",
            default_classification_system="WINS",
            default_rounds_count=4,
            default_venue_id=None,
            has_handicap=True,
        )
        db.session.add(campionato)
        db.session.flush()
        campi = formato.dal_campionato(campionato)
        assert campi["default_rounds_count"] == 4
        assert campi["has_handicap"] is True
        assert "name" not in campi and "default_venue_id" not in campi
        # La catena che vale anche senza una scelta del campionato: il default.
        assert campi["default_catena_turno"].startswith("[")

    def test_il_servizio_salva_dal_campionato(self, db_session):
        from models import Campionato

        campionato = Campionato(name="Lunedì", campionato_type="amalfi")
        db.session.add(campionato)
        db.session.flush()
        preset = ConfigPresetService.salva_dal_campionato(
            _utente(), "Come il lunedì", campionato
        )
        assert preset.kind == CAMPIONATO
        assert preset.dati["campi"]["campionato_type"] == "amalfi"


@pytest.mark.unit
class TestGestione:
    def test_rinomina(self, db_session):
        io = _utente()
        preset = ConfigPresetService.salva(io, "Lunedì", GARA, {"distance": 3})
        ConfigPresetService.rinomina(preset.id, io, "  Lunedì   sera ")
        assert preset.name == "Lunedì sera"

    def test_rinomina_su_un_nome_gia_usato_e_un_conflitto(self, db_session):
        io = _utente()
        ConfigPresetService.salva(io, "Martedì", GARA, {})
        preset = ConfigPresetService.salva(io, "Lunedì", GARA, {})
        with pytest.raises(ConflictError):
            ConfigPresetService.rinomina(preset.id, io, "Martedì")

    def test_duplica_trova_un_nome_libero(self, db_session):
        io = _utente()
        preset = ConfigPresetService.salva(io, "Lunedì", GARA, {"distance": 3})
        prima = ConfigPresetService.duplica(preset.id, io)
        seconda = ConfigPresetService.duplica(preset.id, io)
        assert prima.name != seconda.name
        assert {prima.name, seconda.name}.isdisjoint({"Lunedì"})
        assert prima.dati == preset.dati and prima.kind == preset.kind
        assert prima.received_from_user_id is None

    def test_cancella(self, db_session):
        io = _utente()
        preset = ConfigPresetService.salva(io, "Lunedì", GARA, {})
        ConfigPresetService.cancella(preset.id, io)
        assert db.session.get(ConfigPreset, preset.id) is None

    def test_il_preset_di_un_altro_non_si_tocca(self, db_session):
        preset = ConfigPresetService.salva(_utente(), "Lunedì", GARA, {})
        estraneo = _utente()
        for operazione in (
            lambda: ConfigPresetService.rinomina(preset.id, estraneo, "Mio"),
            lambda: ConfigPresetService.duplica(preset.id, estraneo),
            lambda: ConfigPresetService.cancella(preset.id, estraneo),
            lambda: ConfigPresetService.condividi(preset.id, estraneo, [estraneo.id]),
        ):
            with pytest.raises(NotFoundError):
                operazione()
        giocatore = _utente(UserRole.PLAYER.value)
        with pytest.raises(PermissionDeniedError):
            ConfigPresetService.cancella(preset.id, giocatore)

    def test_l_elenco_mette_insieme_gara_e_campionato(self, db_session):
        io = _utente()
        ConfigPresetService.salva(io, "B gara", GARA, {})
        ConfigPresetService.salva(io, "A campionato", CAMPIONATO, {})
        assert [p.name for p in ConfigPresetService.preset_di(io.id)] == [
            "A campionato",
            "B gara",
        ]


@pytest.mark.unit
class TestCondivisione:
    def test_crea_una_copia_per_ogni_destinatario(self, db_session):
        io, anna, bruno = _utente(), _utente(), _utente(UserRole.ADMIN.value)
        preset = ConfigPresetService.salva(io, "Lunedì", GARA, {"distance": 3})
        copie = ConfigPresetService.condividi(preset.id, io, [anna.id, bruno.id])
        assert {c.owner_id for c in copie} == {anna.id, bruno.id}
        for copia in copie:
            assert copia.id != preset.id
            assert copia.name == "Lunedì"
            assert copia.dati == preset.dati
            assert copia.received_from_user_id == io.id
            assert copia.received_at is not None
        assert preset.received_from_user_id is None

    def test_le_copie_sono_indipendenti(self, db_session):
        io, anna = _utente(), _utente()
        preset = ConfigPresetService.salva(io, "Lunedì", GARA, {"distance": 3})
        (copia,) = ConfigPresetService.condividi(preset.id, io, [anna.id])
        ConfigPresetService.salva(io, "Lunedì", GARA, {"distance": 7}, sostituisci=True)
        assert copia.dati["campi"] == {"distance": 3}
        ConfigPresetService.rinomina(copia.id, anna, "Il mio lunedì")
        assert preset.name == "Lunedì"
        ConfigPresetService.cancella(preset.id, io)
        assert db.session.get(ConfigPreset, copia.id) is not None

    def test_nome_gia_presente_prende_il_suffisso_e_poi_un_numero(self, db_session):
        io, anna = _utente(), _utente()
        ConfigPresetService.salva(anna, "Lunedì", GARA, {})
        preset = ConfigPresetService.salva(io, "Lunedì", GARA, {})
        (prima,) = ConfigPresetService.condividi(preset.id, io, [anna.id])
        assert prima.name == f"Lunedì (da {io.username})"
        (seconda,) = ConfigPresetService.condividi(preset.id, io, [anna.id])
        assert seconda.name == f"Lunedì (da {io.username}) 2"

    def test_il_suffisso_resta_dentro_la_lunghezza_massima(self, db_session):
        io, anna = _utente(), _utente()
        lungo = "L" * 100
        ConfigPresetService.salva(anna, lungo, GARA, {})
        preset = ConfigPresetService.salva(io, lungo, GARA, {})
        (copia,) = ConfigPresetService.condividi(preset.id, io, [anna.id])
        assert len(copia.name) <= 100
        assert copia.name.endswith(f"(da {io.username})")

    def test_con_un_giocatore_si_rifiuta(self, db_session):
        io = _utente()
        preset = ConfigPresetService.salva(io, "Lunedì", GARA, {})
        with pytest.raises(ValidationError):
            ConfigPresetService.condividi(
                preset.id, io, [_utente(UserRole.PLAYER.value).id]
            )
        assert ConfigPreset.query.count() == 1

    def test_con_se_stessi_o_con_nessuno_si_rifiuta(self, db_session):
        io = _utente()
        preset = ConfigPresetService.salva(io, "Lunedì", GARA, {})
        with pytest.raises(ValidationError):
            ConfigPresetService.condividi(preset.id, io, [io.id])
        with pytest.raises(ValidationError):
            ConfigPresetService.condividi(preset.id, io, [])

    def test_un_destinatario_che_non_esiste_e_404(self, db_session):
        io = _utente()
        preset = ConfigPresetService.salva(io, "Lunedì", GARA, {})
        with pytest.raises(NotFoundError):
            ConfigPresetService.condividi(preset.id, io, [987654])

    def test_la_notifica_arriva_nella_lingua_di_chi_riceve(self, db_session):
        from models.notification.models import Notification, NotificationType

        io = _utente()
        anna = _utente(language="en")
        preset = ConfigPresetService.salva(io, "Lunedì", GARA, {})
        ConfigPresetService.condividi(preset.id, io, [anna.id])
        notifica = Notification.query.filter_by(user_id=anna.id).one()
        assert notifica.notification_type == NotificationType.PRESET_SHARED
        assert io.username in notifica.message and "Lunedì" in notifica.message
        assert "preset" in notifica.title.lower()
        assert "ti ha mandato" not in notifica.message
        assert notifica.action_url == "/admin/preset/"

    def test_cerca_solo_direttori_e_admin_e_non_se_stessi(self, db_session):
        io = _utente()
        sigla = io.username[3:7]
        d = _utente()
        d.username = f"zz{sigla}dir"
        g = _utente(UserRole.PLAYER.value)
        g.username = f"zz{sigla}gio"
        db.session.flush()
        trovati = ConfigPresetService.cerca_direttori(f"zz{sigla}", io)
        assert [u.id for u in trovati] == [d.id]
        assert ConfigPresetService.cerca_direttori("z", io) == []


@pytest.mark.unit
class TestInterfaccia:
    def test_le_route_nuove_si_vedono_dai_direttori(self):
        """ADR-028: senza la voce sarebbero solo dell'admin, in silenzio."""
        from utils.feature_flags import ENDPOINT_ROLES

        for endpoint in (
            "admin.preset.salva_dal_modulo_campionato",
            "admin.preset.salva_dal_campionato",
            "admin.preset.miei",
            "admin.preset.rinomina",
            "admin.preset.duplica",
            "admin.preset.cancella",
            "admin.preset.condividi",
            "admin.preset.cerca_direttori",
        ):
            assert ENDPOINT_ROLES[endpoint] == {"director"}, endpoint

    def test_il_link_della_notifica_e_la_pagina(self, app):
        from flask import url_for

        from models.preset.service import PAGINA_DEI_PRESET

        with app.test_request_context():
            assert url_for("admin.preset.miei") == PAGINA_DEI_PRESET

    def test_il_menu_porta_alla_pagina_solo_se_visibile(self):
        from pathlib import Path

        testo = Path("templates/components/_user_menu.html").read_text()
        assert "feature_visible('admin.preset.miei')" in testo

    def test_la_cancellazione_usa_il_foglio_dell_app(self):
        """ADR-074: mai il `confirm()` del browser, che può essere zittito."""
        import re
        from pathlib import Path

        testo = Path("templates/admin/preset_miei.html").read_text()
        assert "confirmSubmit(" in testo
        assert not re.search(r"(?<![A-Za-z])confirm\(", testo)
