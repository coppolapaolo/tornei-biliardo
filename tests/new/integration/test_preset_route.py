"""I preset dei direttori dai moduli al server e ritorno (ADR-082).

Il payload e il servizio hanno i loro unit test (`test_preset_dei_direttori`);
qui il passaggio interfaccia↔server: che i moduli della gara portino la barra,
che «Salva come preset» tenga solo la configurazione, che i valori tornino al
proprietario e a nessun altro, e che la gara creata dal modulo precompilato
non resti legata al preset.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Campionato, Gara, User
from models.preset.models import ConfigPreset
from models.preset.service import ConfigPresetService
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration

AJAX = {"X-Requested-With": "XMLHttpRequest"}


def _utente(db_session, role=UserRole.DIRECTOR.value):
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"prs_{uid}",
        email=f"prs_{uid}@test.com",
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


def _modulo(nome="Lunedì al 74", **extra):
    dati = {
        "name": nome,
        "date": (date.today() + timedelta(days=10)).isoformat(),
        "time": "20:30",
        "location": "Biliardo 74",
        "available_tables": "1,2",
        "description": "note",
        "discipline": "9_ball",
        "distance": "3",
        "rounds_count": "3",
        "min_participants": "4",
        "max_participants": "12",
        "entry_fee": "15",
        "matchmaking_strategy": "round_robin",
        "first_round_policy": "random",
        "odd_number_policy": "bye",
        "withdraw_policy": "Forfeit",
        "classification_system": "POINTS",
        "points_win": "3",
        "points_draw": "1",
        "points_loss": "0",
        "max_groups": "2",
        "group_seeding": "sorteggio",
        "final_phase_mode": "tabellone",
        "qualifiers_per_group": "2",
        "time_limit_minutes": "30",
        "listino_presente": "1",
        "listino_id": "",
        "listino_nome": "Serie A",
        "listino_quota": "30",
    }
    dati.update(extra)
    return dati


class TestSalvaDalModulo:
    def test_il_modulo_della_gara_singola_porta_la_barra(self, client, db_session):
        _login(client, _utente(db_session))
        pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)
        assert "data-preset" in pagina
        assert "preset_modulo.js" in pagina

    def test_salva_solo_la_configurazione(self, client, db_session):
        direttore = _utente(db_session)
        _login(client, direttore)
        risposta = client.post(
            "/admin/preset/gara/dal-modulo",
            data={**_modulo(), "preset_nome": "Lunedì al 74"},
            headers=AJAX,
        )
        assert risposta.status_code == 200, risposta.get_json()
        preset = ConfigPreset.query.filter_by(owner_id=direttore.id).one()
        campi = preset.dati["campi"]
        assert campi["distance"] == 3
        assert campi["max_groups"] == 2
        assert campi["time_limit_minutes"] == 30
        for escluso in ("name", "date", "time", "location", "description"):
            assert escluso not in campi
        assert preset.dati["listino"] == [{"nome": "Serie A", "quota": 30.0}]

    def test_la_data_vuota_non_ferma_il_salvataggio(self, client, db_session):
        _login(client, _utente(db_session))
        risposta = client.post(
            "/admin/preset/gara/dal-modulo",
            data={**_modulo(date=""), "preset_nome": "Senza data"},
            headers=AJAX,
        )
        assert risposta.status_code == 200

    def test_stesso_nome_e_un_conflitto_che_si_puo_sostituire(self, client, db_session):
        _login(client, _utente(db_session))
        url = "/admin/preset/gara/dal-modulo"
        client.post(url, data={**_modulo(), "preset_nome": "Lunedì"}, headers=AJAX)
        doppio = client.post(
            url, data={**_modulo(distance="5"), "preset_nome": "Lunedì"}, headers=AJAX
        )
        assert doppio.status_code == 409
        assert doppio.get_json()["conflitto"] is True
        sostituito = client.post(
            url,
            data={
                **_modulo(distance="5"),
                "preset_nome": "Lunedì",
                "preset_sostituisci": "1",
            },
            headers=AJAX,
        )
        assert sostituito.status_code == 200
        assert ConfigPreset.query.one().dati["campi"]["distance"] == 5

    def test_un_giocatore_non_salva_preset(self, client, db_session):
        _login(client, _utente(db_session, UserRole.PLAYER.value))
        risposta = client.post(
            "/admin/preset/gara/dal-modulo",
            data={**_modulo(), "preset_nome": "Mio"},
            headers=AJAX,
        )
        assert risposta.status_code == 403


class TestValori:
    def _preset(self, db_session, proprietario):
        return ConfigPresetService.salva(
            proprietario, "Lunedì", "gara", {"distance": 3, "is_race_to": True}
        )

    def test_il_proprietario_li_riceve(self, client, db_session):
        direttore = _utente(db_session)
        preset = self._preset(db_session, direttore)
        _login(client, direttore)
        dati = client.get(f"/admin/preset/{preset.id}/valori").get_json()
        assert dati["success"] is True
        assert ["distance", 3] in dati["valori"]
        assert ["exact_number", False] in dati["valori"]

    def test_per_un_altro_direttore_non_esiste(self, client, db_session):
        preset = self._preset(db_session, _utente(db_session))
        _login(client, _utente(db_session))
        assert client.get(f"/admin/preset/{preset.id}/valori").status_code == 404

    def test_un_giocatore_riceve_403(self, client, db_session):
        preset = self._preset(db_session, _utente(db_session))
        _login(client, _utente(db_session, UserRole.PLAYER.value))
        assert client.get(f"/admin/preset/{preset.id}/valori").status_code == 403


class TestDallaGara:
    def _gara(self, db_session, direttore, campionato=None):
        gara = Gara(
            name="Serata",
            number=1,
            date=date.today() + timedelta(days=5),
            discipline="9_ball",
            distance=4,
            is_race_to=True,
            matchmaking_strategy="amalfi",
            classification_system="WINS",
            director_id=direttore.id,
            campionato_id=campionato.id if campionato else None,
        )
        db_session.add(gara)
        db_session.commit()
        return gara

    def test_salva_la_gara_singola(self, client, db_session):
        direttore = _utente(db_session)
        gara = self._gara(db_session, direttore)
        _login(client, direttore)
        risposta = client.post(
            f"/admin/preset/gara/da/{gara.id}",
            data={"preset_nome": "Come la serata"},
            headers=AJAX,
        )
        assert risposta.status_code == 200, risposta.get_json()
        campi = ConfigPreset.query.one().dati["campi"]
        assert campi["distance"] == 4
        assert campi["has_handicap"] is False
        assert "name" not in campi

    def test_la_pagina_delle_impostazioni_la_offre(self, client, db_session):
        direttore = _utente(db_session)
        gara = self._gara(db_session, direttore)
        _login(client, direttore)
        pagina = client.get(f"/admin/gara/{gara.id}/impostazioni").get_data(
            as_text=True
        )
        assert f"/admin/preset/gara/da/{gara.id}" in pagina

    def test_la_gara_di_un_altro_non_si_legge(self, client, db_session):
        gara = self._gara(db_session, _utente(db_session))
        _login(client, _utente(db_session))
        risposta = client.post(
            f"/admin/preset/gara/da/{gara.id}",
            data={"preset_nome": "Rubato"},
            headers=AJAX,
        )
        assert risposta.status_code == 404
        assert ConfigPreset.query.count() == 0

    def test_dentro_un_campionato_l_ereditato_diventa_esplicito(
        self, client, db_session
    ):
        direttore = _utente(db_session)
        campionato = Campionato(
            name="Lunedì",
            campionato_type="amalfi",
            has_handicap=True,
            default_time_limit_minutes=25,
        )
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
        gara = self._gara(db_session, direttore, campionato)
        _login(client, direttore)
        client.post(
            f"/admin/preset/gara/da/{gara.id}",
            data={"preset_nome": "Dal campionato"},
            headers=AJAX,
        )
        campi = ConfigPreset.query.one().dati["campi"]
        assert campi["has_handicap"] is True
        assert campi["time_limit_minutes"] == 25


class TestNessunLegame:
    def test_la_gara_creata_non_cambia_se_il_preset_cambia(self, client, db_session):
        direttore = _utente(db_session)
        _login(client, direttore)
        client.post(
            "/admin/preset/gara/dal-modulo",
            data={**_modulo(), "preset_nome": "Lunedì"},
            headers=AJAX,
        )
        preset = ConfigPreset.query.one()
        valori = dict(
            client.get(f"/admin/preset/{preset.id}/valori").get_json()["valori"]
        )
        modulo = _modulo(nome="Serata del 9")
        modulo.update({k: str(v) for k, v in valori.items() if v not in (True, False)})
        client.post("/admin/gara/create_standalone", data=modulo)
        gara = Gara.query.filter_by(name="Serata del 9").one()
        assert gara.distance == 3 and gara.max_groups == 2

        ConfigPresetService.salva(
            direttore, "Lunedì", "gara", {"distance": 7}, sostituisci=True
        )
        db_session.delete(ConfigPreset.query.one())
        db_session.commit()
        gara = db_session.get(Gara, gara.id)
        assert gara.distance == 3 and gara.max_groups == 2
