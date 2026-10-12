"""I playoff nel preset di campionato (ADR-082, emendamento del 2026-10-12).

Cosa difendono questi test:

* del playoff entra **solo la configurazione** — criteri di qualificazione,
  modalità di classifica finale, peso, formula e regole della finale — mai
  id, campionato, gara creata, stato, date, sala, qualificati e inviti: la
  whitelist è positiva e sta in `payload.CAMPI_DEL_PLAYOFF`;
* un preset salvato prima (``schema_version`` 1) si legge ancora: senza
  playoff vuol dire **nessuna configurazione**, non un errore;
* wizard → preset → wizard è un'andata e ritorno senza perdite: i playoff del
  passo 1 tornano negli stessi interruttori, e il campionato creato dal
  preset ha le configurazioni attese, criteri e regole della finale compresi;
* il preset **non scavalca** i controlli della finale, e nella modifica del
  campionato non tocca i playoff: lo dice, e dice se lì gli inviti sono già
  partiti (ADR-075);
* duplicare e condividere portano anche i playoff; «I miei preset» dice se il
  preset li comprende.
"""

from __future__ import annotations

import uuid

import pytest

from models import Campionato
from models.base import db
from models.exceptions import ValidationError
from models.playoff.models import (
    PlayoffConfiguration,
    PlayoffQualification,
    QualificationStatus,
)
from models.preset import payload as formato
from models.preset.models import ConfigPreset, TipoPreset
from models.preset.service import ConfigPresetService, playoff_del_preset
from models.user.models import DirectorAssignment, User
from models.user.role_enum import UserRole

CAMPIONATO = TipoPreset.CAMPIONATO.value
AJAX = {"X-Requested-With": "XMLHttpRequest"}

#: Elite e Academy come le scrive un direttore che ha toccato tutto.
ELITE = {
    "name": "Playoff Elite",
    "positions_from": 1,
    "positions_to": 8,
    "max_participants": 8,
    "min_garas_played": 3,
    "final_ranking_mode": "playoff_only",
    "playoff_weight": 2,
    "discipline": "9_ball",
    "distance": 7,
    "rounds_count": 3,
    "strategy_type": "direct_elimination",
    "odd_number_policy": "bye",
    "classification_system": "WINS",
    "entry_fee": 20,
}
ACADEMY = {
    "name": "Playoff Academy",
    "positions_from": 9,
    "positions_to": 14,
    "max_participants": 6,
    "min_garas_played": 2,
    "final_ranking_mode": "campionato_plus_playoff",
    "playoff_weight": 1,
}


def _utente(role=UserRole.DIRECTOR.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"pp_{uid}",
        email=f"pp_{uid}@test.local",
        role=role,
        onboarding_completed=True,
    )
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.flush()
    return user


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "pwd12345"},
        follow_redirects=True,
    )


def _campionato(direttore=None, **campi) -> Campionato:
    campionato = Campionato(name="Lunedì", campionato_type="amalfi", **campi)
    db.session.add(campionato)
    db.session.flush()
    if direttore is not None:
        db.session.add(
            DirectorAssignment(
                entity_type="campionato",
                entity_id=campionato.id,
                user_id=direttore.id,
                assigned_by_id=direttore.id,
            )
        )
        db.session.flush()
    return campionato


def _senza_vuoti(config):
    return {k: v for k, v in config.items() if v is not None}


def _playoff(campionato, **campi) -> PlayoffConfiguration:
    from models.playoff.models import PlayoffType

    config = PlayoffConfiguration(
        campionato_id=campionato.id, playoff_type=PlayoffType.TOP_N, **campi
    )
    db.session.add(config)
    db.session.flush()
    return config


@pytest.mark.unit
class TestLaWhitelistDeiPlayoff:
    def test_solo_la_configurazione(self):
        ammessi = set(formato.CAMPI_DEL_PLAYOFF)
        for fuori in (
            "id",
            "campionato_id",
            "gara",
            "is_active",
            "scheduled_date",
            "response_deadline",
            "location",
            "qualifications",
            "playoff_type",
            "qualification_criteria",
            "auto_generate",
            "created_at",
            "updated_at",
        ):
            assert fuori not in ammessi, fuori
        for dentro in (
            "positions_from",
            "positions_to",
            "max_participants",
            "min_garas_played",
            "final_ranking_mode",
            "playoff_weight",
            "strategy_type",
            "distance",
            "classification_system",
        ):
            assert dentro in ammessi, dentro

    def test_ogni_campo_ammesso_e_una_colonna_della_configurazione(self):
        colonne = set(PlayoffConfiguration.__table__.columns.keys())
        assert set(formato.CAMPI_DEL_PLAYOFF) <= colonne

    def test_il_payload_tiene_solo_i_campi_ammessi(self):
        sporco = {
            **ELITE,
            "id": 7,
            "campionato_id": 3,
            "scheduled_date": "2026-12-01",
            "response_deadline": "2026-11-20",
            "location": "Biliardo 74",
            "is_active": False,
            "qualifications": [1, 2],
        }
        dati = formato.componi(CAMPIONATO, {}, playoff=[sporco])
        assert dati["playoff"] == [ELITE]

    def test_il_campionato_scrive_sempre_l_elenco_anche_vuoto(self):
        assert formato.componi(CAMPIONATO, {})["playoff"] == []

    def test_un_preset_di_gara_non_ha_playoff(self):
        dati = formato.componi(TipoPreset.GARA.value, {}, playoff=[ELITE])
        assert "playoff" not in dati

    def test_i_numeri_restano_numeri(self):
        dati = formato.componi(
            CAMPIONATO, {}, playoff=[{"max_participants": "6", "entry_fee": "12.5"}]
        )
        assert dati["playoff"] == [{"max_participants": 6, "entry_fee": 12.5}]


@pytest.mark.unit
class TestLetturaTollerante:
    def test_un_preset_della_versione_1_si_legge_senza_playoff(self):
        lettura = formato.leggi(CAMPIONATO, {"campi": {"default_rounds_count": 4}}, 1)
        assert lettura.playoff == []
        assert lettura.scartati == []
        assert lettura.campi == {"default_rounds_count": 4}

    def test_la_versione_e_salita(self):
        assert formato.SCHEMA_VERSION == 2

    def test_un_campo_sconosciuto_del_playoff_si_scarta_e_si_dice(self):
        lettura = formato.leggi(
            CAMPIONATO, {"campi": {}, "playoff": [{**ACADEMY, "colore": "blu"}]}, 2
        )
        assert lettura.playoff == [ACADEMY]
        assert lettura.scartati == ["playoff.colore"]

    def test_un_elenco_illeggibile_vale_nessuna_configurazione(self):
        lettura = formato.leggi(CAMPIONATO, {"campi": {}, "playoff": "boh"}, 2)
        assert lettura.playoff == []

    def test_un_preset_vecchio_salvato_si_usa_ancora(self, db_session):
        io = _utente()
        vecchio = ConfigPreset(
            owner_id=io.id, name="Del 2025", kind=CAMPIONATO, schema_version=1
        )
        vecchio.dati = {"campi": {"default_rounds_count": 4}}
        db.session.add(vecchio)
        db.session.flush()
        dati = ConfigPresetService.per_il_modulo(vecchio.id, io)
        valori = dict(map(tuple, dati["valori"]))
        assert valori["default_rounds_count"] == 4
        assert valori["playoff_elite_enabled"] is False
        assert valori["playoff_academy_enabled"] is False
        assert dati["playoff"] == []
        assert playoff_del_preset(vecchio) == []


@pytest.mark.unit
class TestNelPasso1DelWizard:
    def test_due_configurazioni_vanno_su_elite_e_academy(self):
        coppie = dict(formato.valori_dei_playoff([ELITE, ACADEMY]))
        assert coppie == {
            "playoff_elite_enabled": True,
            "playoff_elite_participants": 8,
            "playoff_academy_enabled": True,
            "playoff_academy_participants": 6,
        }

    def test_una_sola_e_elite(self):
        coppie = dict(formato.valori_dei_playoff([ACADEMY]))
        assert coppie["playoff_elite_enabled"] is True
        assert coppie["playoff_elite_participants"] == 6
        assert coppie["playoff_academy_enabled"] is False

    def test_nessuna_spegne_tutti_e_due(self):
        coppie = dict(formato.valori_dei_playoff([]))
        assert coppie == {
            "playoff_elite_enabled": False,
            "playoff_academy_enabled": False,
        }

    def test_oltre_la_seconda_il_passo_1_lo_dice(self, db_session):
        io = _utente()
        terzo = {"name": "Coppa di consolazione", "max_participants": 4}
        preset = ConfigPresetService.salva(
            io, "Tre playoff", CAMPIONATO, {}, playoff=[ELITE, ACADEMY, terzo]
        )
        dati = ConfigPresetService.per_il_modulo(preset.id, io)
        assert "Coppa di consolazione" in dati["nota_playoff_wizard"]


@pytest.mark.unit
class TestLeConfigurazioniDelWizard:
    def test_senza_preset_come_sempre(self, app):
        passo_1 = {
            "playoff_elite_enabled": True,
            "playoff_elite_participants": 6,
            "playoff_academy_enabled": True,
            "playoff_academy_participants": 4,
        }
        with app.test_request_context():
            elite, academy = formato.configurazioni_dal_wizard(passo_1)
        assert (elite["positions_from"], elite["positions_to"]) == (1, 6)
        assert (academy["positions_from"], academy["positions_to"]) == (7, 10)
        assert elite["name"] == "Playoff Elite"
        assert academy["max_participants"] == 4

    def test_dal_preset_criteri_e_regole_della_finale(self, app):
        passo_1 = {
            "playoff_elite_enabled": True,
            "playoff_elite_participants": 8,
            "playoff_academy_enabled": True,
            "playoff_academy_participants": 6,
            "playoff_dal_preset": [ELITE, ACADEMY],
        }
        with app.test_request_context():
            elite, academy = formato.configurazioni_dal_wizard(passo_1)
        assert elite == ELITE
        assert academy == ACADEMY

    def test_i_posti_li_decide_il_modulo(self, app):
        passo_1 = {
            "playoff_elite_enabled": True,
            "playoff_elite_participants": 4,
            "playoff_academy_enabled": True,
            "playoff_academy_participants": 6,
            "playoff_dal_preset": [ELITE, ACADEMY],
        }
        with app.test_request_context():
            elite, academy = formato.configurazioni_dal_wizard(passo_1)
        assert (elite["positions_to"], elite["max_participants"]) == (4, 4)
        assert academy["positions_from"] == 5
        # Il resto viene dal preset.
        assert elite["final_ranking_mode"] == "playoff_only"
        assert academy["min_garas_played"] == 2

    def test_academy_senza_elite_non_c_e(self, app):
        passo_1 = {"playoff_academy_enabled": True, "playoff_dal_preset": [ELITE]}
        with app.test_request_context():
            assert formato.configurazioni_dal_wizard(passo_1) == []

    def test_oltre_la_seconda_non_si_crea(self, app):
        passo_1 = {
            "playoff_elite_enabled": True,
            "playoff_elite_participants": 8,
            "playoff_academy_enabled": True,
            "playoff_academy_participants": 6,
            "playoff_dal_preset": [ELITE, ACADEMY, {"name": "Terzo"}],
        }
        with app.test_request_context():
            assert len(formato.configurazioni_dal_wizard(passo_1)) == 2


@pytest.mark.unit
class TestLaCreazioneControlla:
    def test_crea_con_la_configurazione_del_preset(self, db_session):
        from models.campionato.services import TournamentService

        campionato = _campionato()
        config = TournamentService.create_playoff_config(
            campionato_id=campionato.id, **ELITE
        )
        for campo, valore in ELITE.items():
            atteso = valore
            letto = getattr(config, campo)
            if campo == "entry_fee":
                letto = float(letto)
            assert letto == atteso, campo

    def test_un_valore_sconosciuto_si_rifiuta(self, db_session):
        from models.campionato.services import TournamentService

        campionato = _campionato()
        with pytest.raises(ValidationError):
            TournamentService.create_playoff_config(
                campionato_id=campionato.id,
                name="Elite",
                max_participants=6,
                positions_from=1,
                positions_to=6,
                strategy_type="inventata",
            )

    def test_un_peso_sotto_uno_si_rifiuta(self, db_session):
        from models.campionato.services import TournamentService

        campionato = _campionato()
        with pytest.raises(ValueError):
            TournamentService.create_playoff_config(
                campionato_id=campionato.id,
                name="Elite",
                max_participants=6,
                positions_from=1,
                positions_to=6,
                playoff_weight=0,
            )

    def test_una_finale_sommata_con_un_altro_sistema_si_rifiuta(self, db_session):
        """SPECIFICHE.md, «Playoff»: con «Campionato + gara di playoff» la
        finale deve contare la stessa cosa del campionato."""
        from models.campionato.services import TournamentService

        campionato = _campionato(default_classification_system="WINS")
        with pytest.raises(ValidationError):
            TournamentService.create_playoff_config(
                campionato_id=campionato.id,
                name="Elite",
                max_participants=6,
                positions_from=1,
                positions_to=6,
                final_ranking_mode="campionato_plus_playoff",
                classification_system="RACK",
            )


@pytest.mark.unit
class TestDalCampionatoEsistente:
    def test_legge_le_configurazioni_attive_in_ordine(self, db_session):
        campionato = _campionato()
        _playoff(campionato, **ACADEMY)
        _playoff(campionato, **ELITE)
        _playoff(
            campionato,
            name="Spenta",
            max_participants=4,
            positions_from=20,
            positions_to=23,
            is_active=False,
        )
        letti = formato.playoff_del_campionato(campionato)
        assert [c["name"] for c in letti] == ["Playoff Elite", "Playoff Academy"]
        assert letti[0]["final_ranking_mode"] == "playoff_only"
        assert letti[0]["entry_fee"] == 20.0
        assert "location" not in letti[0] and "id" not in letti[0]

    def test_il_servizio_salva_anche_i_playoff(self, db_session):
        campionato = _campionato()
        _playoff(campionato, **ELITE)
        preset = ConfigPresetService.salva_dal_campionato(
            _utente(), "Come il lunedì", campionato
        )
        assert preset.schema_version == 2
        assert preset.dati["playoff"][0]["max_participants"] == 8


@pytest.mark.unit
class TestCopie:
    def test_duplica_e_condividi_portano_i_playoff(self, db_session):
        io, altro = _utente(), _utente()
        preset = ConfigPresetService.salva(
            io, "Con playoff", CAMPIONATO, {}, playoff=[ELITE, ACADEMY]
        )
        copia = ConfigPresetService.duplica(preset.id, io)
        (ricevuto,) = ConfigPresetService.condividi(preset.id, io, [altro.id])
        for p in (copia, ricevuto):
            assert p.dati["playoff"] == [ELITE, ACADEMY]
            assert playoff_del_preset(p) == ["Playoff Elite", "Playoff Academy"]

    def test_un_preset_di_gara_non_dice_niente_dei_playoff(self, db_session):
        preset = ConfigPresetService.salva(
            _utente(), "Serata", TipoPreset.GARA, {"distance": 3}
        )
        assert playoff_del_preset(preset) is None


@pytest.mark.unit
class TestNellaModificaNonSiApplicano:
    def test_lo_dice(self, db_session):
        io = _utente()
        preset = ConfigPresetService.salva(
            io, "Con playoff", CAMPIONATO, {}, playoff=[ELITE, ACADEMY]
        )
        dati = ConfigPresetService.per_il_modulo(preset.id, io, _campionato(io))
        nota = dati["nota_playoff_altrove"]
        assert "Playoff Elite" in nota and "Playoff Academy" in nota
        assert "inviti" not in nota

    def test_a_inviti_partiti_lo_dice(self, db_session):
        io = _utente()
        campionato = _campionato(io)
        config = _playoff(campionato, **ELITE)
        db.session.add(
            PlayoffQualification(
                configuration_id=config.id,
                user_id=_utente(UserRole.PLAYER.value).id,
                qualifying_position=1,
                qualification_reason="1° in classifica",
                status=QualificationStatus.PENDING,
            )
        )
        db.session.flush()
        preset = ConfigPresetService.salva(
            io, "Con playoff", CAMPIONATO, {}, playoff=[ACADEMY]
        )
        dati = ConfigPresetService.per_il_modulo(preset.id, io, campionato)
        assert "inviti sono già partiti" in dati["nota_playoff_altrove"]

    def test_senza_playoff_nessuna_nota(self, db_session):
        io = _utente()
        preset = ConfigPresetService.salva(io, "Senza", CAMPIONATO, {})
        dati = ConfigPresetService.per_il_modulo(preset.id, io, _campionato(io))
        assert "nota_playoff_altrove" not in dati


#: Il passo 2 del wizard, quanto basta per creare il campionato.
PASSO_2 = {
    "default_rounds_count": "4",
    "default_odd_policy": "bye",
    "default_anti_rematch": "on",
}


@pytest.mark.unit
class TestAttraversoLeRoute:
    def _passo_1(self, client, preset_id=None, **campi):
        dati = {
            "name": "Dal preset",
            "planned_gare_count": "6",
            "campionato_type": "amalfi",
            "default_classification_system": "WINS",
            **campi,
        }
        if preset_id:
            dati["preset_id"] = preset_id
        return client.post("/admin/campionato/wizard/step2", data=dati)

    def test_wizard_preset_wizard_con_i_playoff(self, client, db_session):
        io = _utente()
        db.session.commit()
        _login(client, io)
        # Primo campionato: Elite 8 e Academy 6 al passo 1.
        self._passo_1(
            client,
            playoff_elite_enabled="on",
            playoff_elite_participants="8",
            playoff_academy_enabled="on",
            playoff_academy_participants="6",
        )
        risposta = client.post(
            "/admin/preset/campionato/dal-modulo",
            data={**PASSO_2, "preset_nome": "Con playoff", "preset_wizard": "1"},
            headers=AJAX,
        )
        assert risposta.status_code == 200, risposta.get_json()
        preset = ConfigPreset.query.filter_by(owner_id=io.id).one()
        assert [c["max_participants"] for c in preset.dati["playoff"]] == [8, 6]
        assert preset.dati["playoff"][1]["positions_from"] == 9

        # Il passo 1 di un altro campionato riceve gli stessi interruttori.
        valori = client.get(f"/admin/preset/{preset.id}/valori").get_json()["valori"]
        coppie = dict(map(tuple, valori))
        assert coppie["playoff_elite_enabled"] is True
        assert coppie["playoff_elite_participants"] == 8
        assert coppie["playoff_academy_participants"] == 6

    def test_il_campionato_creato_dal_preset_ha_i_playoff_attesi(
        self, client, db_session
    ):
        io = _utente()
        preset = ConfigPresetService.salva(
            io, "Elite e Academy", CAMPIONATO, {}, playoff=[ELITE, ACADEMY]
        )
        db.session.commit()
        _login(client, io)
        self._passo_1(
            client,
            preset_id=preset.id,
            playoff_elite_enabled="on",
            playoff_elite_participants="8",
            playoff_academy_enabled="on",
            playoff_academy_participants="6",
        )
        client.post("/admin/campionato/wizard/create", data=PASSO_2)
        campionato = Campionato.query.filter_by(name="Dal preset").one()
        configurazioni = (
            PlayoffConfiguration.query.filter_by(campionato_id=campionato.id)
            .order_by(PlayoffConfiguration.positions_from)
            .all()
        )
        assert len(configurazioni) == 2
        elite, academy = configurazioni
        assert elite.final_ranking_mode == "playoff_only"
        assert elite.playoff_weight == 2
        assert elite.strategy_type == "direct_elimination"
        assert elite.min_garas_played == 3
        assert (academy.positions_from, academy.positions_to) == (9, 14)
        assert academy.min_garas_played == 2
        # Niente lega il campionato al preset.
        assert elite.scheduled_date is None and elite.response_deadline is None

    def test_un_preset_che_la_finale_rifiuta_non_lascia_un_campionato_a_meta(
        self, client, db_session
    ):
        io = _utente()
        storto = {**ELITE, "final_ranking_mode": "campionato_plus_playoff"}
        storto["classification_system"] = "RACK"
        storto["strategy_type"] = "amalfi"
        preset = ConfigPresetService.salva(
            io, "Storto", CAMPIONATO, {}, playoff=[storto]
        )
        db.session.commit()
        _login(client, io)
        self._passo_1(
            client,
            preset_id=preset.id,
            playoff_elite_enabled="on",
            playoff_elite_participants="8",
        )
        client.post("/admin/campionato/wizard/create", data=PASSO_2)
        assert Campionato.query.filter_by(name="Dal preset").count() == 0

    def test_dalla_modifica_legge_i_playoff_del_campionato(self, client, db_session):
        io = _utente()
        campionato = _campionato(io)
        _playoff(campionato, **ELITE)
        db.session.commit()
        _login(client, io)
        risposta = client.post(
            "/admin/preset/campionato/dal-modulo",
            data={
                **PASSO_2,
                "campionato_type": "amalfi",
                "default_classification_system": "WINS",
                "preset_nome": "Dalla modifica",
                "preset_campionato_id": campionato.id,
            },
            headers=AJAX,
        )
        assert risposta.status_code == 200, risposta.get_json()
        preset = ConfigPreset.query.filter_by(owner_id=io.id).one()
        assert [_senza_vuoti(c) for c in preset.dati["playoff"]] == [ELITE]

    def test_dal_dettaglio_legge_i_playoff_del_campionato(self, client, db_session):
        io = _utente()
        campionato = _campionato(io)
        _playoff(campionato, **ACADEMY)
        db.session.commit()
        _login(client, io)
        risposta = client.post(
            f"/admin/preset/campionato/da/{campionato.id}",
            data={"preset_nome": "Dal dettaglio"},
            headers=AJAX,
        )
        assert risposta.status_code == 200, risposta.get_json()
        preset = ConfigPreset.query.filter_by(owner_id=io.id).one()
        # I campi NULL («come il campionato») restano scritti come NULL.
        assert preset.dati["playoff"][0]["distance"] is None
        assert [_senza_vuoti(c) for c in preset.dati["playoff"]] == [ACADEMY]

    def test_la_modifica_riceve_la_nota_col_campionato(self, client, db_session):
        io = _utente()
        campionato = _campionato(io)
        config = _playoff(campionato, **ELITE)
        db.session.add(
            PlayoffQualification(
                configuration_id=config.id,
                user_id=_utente(UserRole.PLAYER.value).id,
                qualifying_position=1,
                qualification_reason="1°",
                status=QualificationStatus.PENDING,
            )
        )
        preset = ConfigPresetService.salva(
            io, "Con playoff", CAMPIONATO, {}, playoff=[ELITE]
        )
        db.session.commit()
        _login(client, io)
        dati = client.get(
            f"/admin/preset/{preset.id}/valori?campionato_id={campionato.id}"
        ).get_json()
        assert "inviti sono già partiti" in dati["nota_playoff_altrove"]
        # Applicare il preset non ha toccato la configurazione.
        assert db.session.get(PlayoffConfiguration, config.id).max_participants == 8

    def test_i_miei_preset_dicono_i_playoff(self, client, db_session):
        io = _utente()
        ConfigPresetService.salva(
            io, "Con playoff", CAMPIONATO, {}, playoff=[ELITE, ACADEMY]
        )
        ConfigPresetService.salva(io, "Senza", CAMPIONATO, {})
        db.session.commit()
        _login(client, io)
        pagina = client.get("/admin/preset/").get_data(as_text=True)
        assert "con 2 playoff: Playoff Elite, Playoff Academy" in pagina
        assert "senza playoff" in pagina
