"""Preset di campionato, «I miei preset» e condivisione, attraverso le route.

Le regole hanno i loro unit test (`test_preset_campionato_e_condivisione`);
qui il passaggio interfaccia↔server: i moduli del campionato portano la
barra, il passo 2 del wizard salva anche ciò che si è scelto al passo 1, la
pagina mostra i preset e le loro azioni rispondono, e chi non è il
proprietario non tocca niente (404), un giocatore nemmeno entra (403).
"""

from __future__ import annotations

import uuid

import pytest

from models import Campionato, User
from models.notification.models import Notification
from models.preset.models import ConfigPreset
from models.preset.service import ConfigPresetService
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration

AJAX = {"X-Requested-With": "XMLHttpRequest"}


def _utente(db_session, role=UserRole.DIRECTOR.value):
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"pcr_{uid}",
        email=f"pcr_{uid}@test.com",
        role=role,
        onboarding_completed=True,
    )
    user.set_password("director123")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "director123"},
        follow_redirects=True,
    )


def _campionato(db_session, direttore, **campi):
    campionato = Campionato(name="Lunedì", campionato_type="amalfi", **campi)
    db_session.add(campionato)
    db_session.flush()
    db_session.add(
        DirectorAssignment(
            entity_type="campionato",
            entity_id=campionato.id,
            user_id=direttore.id,
            assigned_by_id=direttore.id,
        )
    )
    db_session.commit()
    return campionato


PASSO_2 = {
    "default_entry_fee": "15",
    "default_rounds_count": "4",
    "default_odd_policy": "bye",
    "default_anti_rematch": "on",
    "default_start_rule": "lag",
    "default_break_rule": "alternate",
    "default_time_limit_minutes": "30",
    "listino_presente": "1",
    "listino_id": "",
    "listino_nome": "Serie A",
    "listino_quota": "30",
}


class TestBarraNeiModuli:
    def test_la_modifica_del_campionato_la_porta(self, client, db_session):
        direttore = _utente(db_session)
        campionato = _campionato(db_session, direttore)
        _login(client, direttore)
        pagina = client.get(f"/admin/campionato/{campionato.id}/edit").get_data(
            as_text=True
        )
        assert "/admin/preset/campionato/dal-modulo" in pagina
        assert "preset_modulo.js" in pagina

    def test_il_dettaglio_salva_dal_campionato(self, client, db_session):
        direttore = _utente(db_session)
        campionato = _campionato(db_session, direttore)
        _login(client, direttore)
        pagina = client.get(f"/admin/campionato/{campionato.id}").get_data(as_text=True)
        assert f"/admin/preset/campionato/da/{campionato.id}" in pagina

    def test_il_passo_1_offre_i_preset_e_li_passa_al_passo_2(self, client, db_session):
        direttore = _utente(db_session)
        preset = ConfigPresetService.salva(
            direttore, "Lunedì", "campionato", {"default_rounds_count": 4}
        )
        db_session.commit()
        _login(client, direttore)
        pagina = client.get("/admin/campionato/wizard").get_data(as_text=True)
        assert "data-preset-scelto" in pagina and "Lunedì" in pagina
        passo_2 = client.post(
            "/admin/campionato/wizard/step2",
            data={"name": "Nuovo", "planned_gare_count": "6", "preset_id": preset.id},
        ).get_data(as_text=True)
        assert f'data-preset-auto="{preset.id}"' in passo_2


class TestSalvaDalCampionato:
    def test_dal_modulo_di_modifica(self, client, db_session):
        direttore = _utente(db_session)
        campionato = _campionato(db_session, direttore)
        _login(client, direttore)
        risposta = client.post(
            "/admin/preset/campionato/dal-modulo",
            data={
                **PASSO_2,
                "name": "Non entra",
                "default_venue_id": "3",
                "campionato_type": "round_robin",
                "default_classification_system": "WINS",
                "planned_gare_count": "8",
                "preset_nome": "Lunedì",
                "preset_campionato_id": campionato.id,
            },
            headers=AJAX,
        )
        assert risposta.status_code == 200, risposta.get_json()
        preset = ConfigPreset.query.filter_by(owner_id=direttore.id).one()
        campi = preset.dati["campi"]
        assert preset.kind == "campionato"
        assert campi["campionato_type"] == "round_robin"
        assert campi["default_rounds_count"] == 4
        assert campi["default_time_limit_minutes"] == 30
        assert "name" not in campi and "default_venue_id" not in campi
        assert preset.dati["listino"] == [{"nome": "Serie A", "quota": 30.0}]

    def test_dal_passo_2_del_wizard_prende_il_passo_1_dalla_sessione(
        self, client, db_session
    ):
        _login(client, _utente(db_session))
        client.post(
            "/admin/campionato/wizard/step2",
            data={
                "name": "Nuovo",
                "planned_gare_count": "6",
                "campionato_type": "random",
                "challenge_mode": "on",
            },
        )
        risposta = client.post(
            "/admin/preset/campionato/dal-modulo",
            data={**PASSO_2, "preset_nome": "Dal wizard", "preset_wizard": "1"},
            headers=AJAX,
        )
        assert risposta.status_code == 200, risposta.get_json()
        campi = ConfigPreset.query.one().dati["campi"]
        assert campi["campionato_type"] == "random"
        assert campi["planned_gare_count"] == 6
        assert campi["challenge_mode"] is True

    def test_dal_campionato_esistente(self, client, db_session):
        direttore = _utente(db_session)
        campionato = _campionato(db_session, direttore, default_rounds_count=5)
        _login(client, direttore)
        risposta = client.post(
            f"/admin/preset/campionato/da/{campionato.id}",
            data={"preset_nome": "Come il lunedì"},
            headers=AJAX,
        )
        assert risposta.status_code == 200, risposta.get_json()
        assert ConfigPreset.query.one().dati["campi"]["default_rounds_count"] == 5

    def test_il_campionato_di_un_altro_non_si_legge(self, client, db_session):
        campionato = _campionato(db_session, _utente(db_session))
        _login(client, _utente(db_session))
        risposta = client.post(
            f"/admin/preset/campionato/da/{campionato.id}",
            data={"preset_nome": "Rubato"},
            headers=AJAX,
        )
        assert risposta.status_code == 404
        assert ConfigPreset.query.count() == 0

    def test_il_campionato_creato_non_cambia_se_il_preset_cambia(
        self, client, db_session
    ):
        direttore = _utente(db_session)
        _login(client, direttore)
        preset = ConfigPresetService.salva(
            direttore, "Lunedì", "campionato", {"default_rounds_count": 4}
        )
        db_session.commit()
        client.post(
            "/admin/campionato/wizard/step2",
            data={"name": "Dal preset", "planned_gare_count": "6"},
        )
        # Il JavaScript del passo 2 scrive nei campi i valori del preset.
        valori = client.get(f"/admin/preset/{preset.id}/valori").get_json()["valori"]
        modulo = {**PASSO_2, "default_rounds_count": "3"}
        modulo.update({nome: str(valore) for nome, valore in valori})
        client.post("/admin/campionato/wizard/create", data=modulo)
        campionato = Campionato.query.filter_by(name="Dal preset").one()
        assert campionato.default_rounds_count == 4

        ConfigPresetService.salva(
            direttore,
            "Lunedì",
            "campionato",
            {"default_rounds_count": 2},
            sostituisci=True,
        )
        ConfigPresetService.cancella(preset.id, direttore)
        db_session.commit()
        assert db_session.get(Campionato, campionato.id).default_rounds_count == 4


class TestLaPagina:
    def test_elenca_gara_e_campionato_e_la_provenienza(self, client, db_session):
        io, paolo = _utente(db_session), _utente(db_session)
        ConfigPresetService.salva(io, "Serata", "gara", {})
        mandato = ConfigPresetService.salva(paolo, "Stagione", "campionato", {})
        ConfigPresetService.condividi(mandato.id, paolo, [io.id])
        db_session.commit()
        _login(client, io)
        pagina = client.get("/admin/preset/").get_data(as_text=True)
        assert "Serata" in pagina and "Stagione" in pagina
        assert f"ricevuto da {paolo.username}" in pagina
        assert "confirmSubmit(" in pagina and "confirm(" not in pagina.replace(
            "confirmSubmit(", ""
        )

    def test_il_menu_porta_alla_pagina(self, client, db_session):
        _login(client, _utente(db_session))
        assert "/admin/preset/" in client.get("/admin/preset/").get_data(as_text=True)

    def test_un_giocatore_non_entra(self, client, db_session):
        _login(client, _utente(db_session, UserRole.PLAYER.value))
        assert client.get("/admin/preset/").status_code == 403


class TestLeAzioni:
    def test_rinomina_duplica_cancella(self, client, db_session):
        io = _utente(db_session)
        preset = ConfigPresetService.salva(io, "Serata", "gara", {"distance": 3})
        db_session.commit()
        _login(client, io)
        client.post(f"/admin/preset/{preset.id}/rinomina", data={"nome": "Lunedì"})
        assert db_session.get(ConfigPreset, preset.id).name == "Lunedì"
        client.post(f"/admin/preset/{preset.id}/duplica")
        assert ConfigPreset.query.filter_by(owner_id=io.id).count() == 2
        client.post(f"/admin/preset/{preset.id}/cancella")
        assert db_session.get(ConfigPreset, preset.id) is None
        assert ConfigPreset.query.filter_by(owner_id=io.id).count() == 1

    def test_il_preset_di_un_altro_e_404(self, client, db_session):
        preset = ConfigPresetService.salva(_utente(db_session), "Suo", "gara", {})
        db_session.commit()
        _login(client, _utente(db_session))
        for azione in ("rinomina", "duplica", "cancella", "condividi"):
            risposta = client.post(
                f"/admin/preset/{preset.id}/{azione}", data={"nome": "Mio"}
            )
            assert risposta.status_code == 404, azione
        assert db_session.get(ConfigPreset, preset.id).name == "Suo"

    def test_un_giocatore_riceve_403(self, client, db_session):
        preset = ConfigPresetService.salva(_utente(db_session), "Suo", "gara", {})
        db_session.commit()
        _login(client, _utente(db_session, UserRole.PLAYER.value))
        assert client.post(f"/admin/preset/{preset.id}/cancella").status_code == 403


class TestCondividi:
    def test_manda_una_copia_e_una_notifica(self, client, db_session):
        io, anna = _utente(db_session), _utente(db_session)
        preset = ConfigPresetService.salva(io, "Serata", "gara", {"distance": 3})
        db_session.commit()
        _login(client, io)
        client.post(f"/admin/preset/{preset.id}/condividi", data={"user_id": anna.id})
        copia = ConfigPreset.query.filter_by(owner_id=anna.id).one()
        assert copia.received_from_user_id == io.id
        assert copia.dati == {"campi": {"distance": 3}}
        notifica = Notification.query.filter_by(user_id=anna.id).one()
        assert notifica.action_url == "/admin/preset/"

    def test_con_un_giocatore_si_rifiuta(self, client, db_session):
        io = _utente(db_session)
        giocatore = _utente(db_session, UserRole.PLAYER.value)
        preset = ConfigPresetService.salva(io, "Serata", "gara", {})
        db_session.commit()
        _login(client, io)
        pagina = client.post(
            f"/admin/preset/{preset.id}/condividi",
            data={"user_id": giocatore.id},
            follow_redirects=True,
        ).get_data(as_text=True)
        assert "non è un direttore" in pagina
        assert ConfigPreset.query.filter_by(owner_id=giocatore.id).count() == 0

    def test_la_ricerca_trova_solo_direttori(self, client, db_session):
        io = _utente(db_session)
        altro = _utente(db_session)
        _utente(db_session, UserRole.PLAYER.value)
        _login(client, io)
        dati = client.get("/admin/preset/direttori?q=pcr_", headers=AJAX).get_json()
        ids = {d["id"] for d in dati["direttori"]}
        assert altro.id in ids and io.id not in ids
        assert all(db_session.get(User, i).role == UserRole.DIRECTOR.value for i in ids)


class TestIPlayoffNelPreset:
    """Emendamento del 2026-10-12 all'ADR-082: il preset porta i playoff."""

    def test_wizard_preset_wizard_crea_gli_stessi_playoff(self, client, db_session):
        from models.playoff.models import PlayoffConfiguration

        direttore = _utente(db_session)
        _login(client, direttore)
        passo_1 = {
            "planned_gare_count": "6",
            "playoff_elite_enabled": "on",
            "playoff_elite_participants": "8",
            "playoff_academy_enabled": "on",
            "playoff_academy_participants": "5",
        }
        client.post("/admin/campionato/wizard/step2", data={"name": "Primo", **passo_1})
        risposta = client.post(
            "/admin/preset/campionato/dal-modulo",
            data={**PASSO_2, "preset_nome": "Con playoff", "preset_wizard": "1"},
            headers=AJAX,
        )
        assert risposta.status_code == 200, risposta.get_json()
        preset = ConfigPreset.query.filter_by(owner_id=direttore.id).one()

        # Il passo 1 del secondo campionato riceve i valori del preset, come
        # li scrive il JavaScript: caselle accese mandano «on».
        valori = client.get(f"/admin/preset/{preset.id}/valori").get_json()["valori"]
        modulo = {"name": "Secondo", "planned_gare_count": "6", "preset_id": preset.id}
        for nome, valore in valori:
            if nome.startswith("playoff_") and valore is not False:
                modulo[nome] = "on" if valore is True else str(valore)
        client.post("/admin/campionato/wizard/step2", data=modulo)
        client.post("/admin/campionato/wizard/create", data=PASSO_2)

        secondo = Campionato.query.filter_by(name="Secondo").one()
        configurazioni = (
            PlayoffConfiguration.query.filter_by(campionato_id=secondo.id)
            .order_by(PlayoffConfiguration.positions_from)
            .all()
        )
        assert [
            (c.positions_from, c.positions_to, c.max_participants)
            for c in configurazioni
        ] == [(1, 8, 8), (9, 13, 5)]
