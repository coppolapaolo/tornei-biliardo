"""La preparazione della gara, passo per passo (canvas, fase 1).

Le pagine dei passi (turni, tavoli, esercizi, direttori) con avanti e
indietro; la vetrina come ultimo passo; il foglio «Apri le iscrizioni» con
minimo e massimo; gli esercizi fra i turni anche con Amalfi; la descrizione
della gara in testata che segue gli override per turno (rilievo del
12/09/2026); la lista «Da preparare» che porta ai passi.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from models import Gara
from models.competition.round_configuration import RoundConfiguration
from models.status_enum import Discipline, GaraStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def admin_client(client, db_session):
    from models.user.services import UserService

    user = UserService.create_user("prep_admin", "prep_admin@test.local", "pw12345")
    user.role = UserRole.ADMIN.value
    db_session.commit()
    resp = client.post(
        "/auth/login", data={"username": "prep_admin", "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    return client


def _gara(db_session, status=GaraStatus.SETUP.value, *, strategy="amalfi", rounds=3):
    gara = Gara(
        number=1,
        name="Gara in preparazione",
        date=date.today() + timedelta(days=3),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
        matchmaking_strategy=strategy,
        status=status,
        current_round=0,
        rounds_count=rounds,
        min_participants=4,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


# ── I passi ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("passo", ["turni", "tavoli", "esercizi", "direttori"])
def test_ogni_passo_ha_la_sua_pagina_con_avanti_e_indietro(
    admin_client, db_session, passo
):
    gara = _gara(db_session)
    resp = admin_client.get(f"/admin/gara/{gara.id}/preparazione/{passo}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'class="c7-stepnav"' in html
    assert "di 5" in html  # turni, tavoli, esercizi, direttori, vetrina


def test_il_primo_passo_torna_alla_panoramica_e_l_ultimo_e_la_vetrina(
    admin_client, db_session
):
    gara = _gara(db_session)
    html = admin_client.get(f"/admin/gara/{gara.id}/preparazione/turni").get_data(
        as_text=True
    )
    assert "1 di 5" in html
    assert f"/admin/gara/{gara.id}/preparazione/tavoli" in html
    html = admin_client.get(f"/admin/gara/{gara.id}/preparazione/direttori").get_data(
        as_text=True
    )
    assert "4 di 5" in html
    assert f"/admin/gara/{gara.id}/vetrina" in html
    html = admin_client.get(f"/admin/gara/{gara.id}/vetrina").get_data(as_text=True)
    assert "5 di 5" in html
    assert f"/admin/gara/{gara.id}/preparazione/direttori" in html


def test_un_passo_ignoto_e_404_e_fuori_dalla_preparazione_i_passi_non_ci_sono(
    admin_client, db_session
):
    gara = _gara(db_session)
    assert (
        admin_client.get(f"/admin/gara/{gara.id}/preparazione/boh").status_code == 404
    )
    gara_in_gioco = _gara(db_session, GaraStatus.PLAYING.value)
    assert (
        admin_client.get(
            f"/admin/gara/{gara_in_gioco.id}/preparazione/turni"
        ).status_code
        == 404
    )


def test_senza_esercizi_ammessi_il_passo_non_esiste(admin_client, db_session):
    """Sul tabellone i turni sono un ramo dell'albero: niente esercizi fra i
    turni, e la preparazione ha quattro passi."""
    gara = _gara(db_session, strategy="direct_elimination", rounds=3)
    assert (
        admin_client.get(f"/admin/gara/{gara.id}/preparazione/esercizi").status_code
        == 404
    )
    html = admin_client.get(f"/admin/gara/{gara.id}/preparazione/tavoli").get_data(
        as_text=True
    )
    assert "di 4" in html


def test_i_passi_non_sono_per_chi_non_dirige(client, db_session):
    from models.user.services import UserService

    UserService.create_user("prep_player", "prep_player@test.local", "pw12345")
    db_session.commit()
    client.post("/auth/login", data={"username": "prep_player", "password": "pw12345"})
    gara = _gara(db_session)
    assert client.get(f"/admin/gara/{gara.id}/preparazione/turni").status_code in (
        302,
        403,
    )


# ── La panoramica ─────────────────────────────────────────────────────────────


def test_da_preparare_porta_ai_passi(admin_client, db_session):
    gara = _gara(db_session)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert 'id="daPreparare"' in html
    for passo in ("turni", "tavoli", "esercizi", "direttori"):
        assert f"/admin/gara/{gara.id}/preparazione/{passo}" in html
    assert f"/admin/gara/{gara.id}/vetrina" in html
    # Sul desktop le sezioni in linea: direzione, tavoli, vetrina.
    assert 'id="sezioneDirettori"' in html
    assert 'id="sezioneTavoli"' in html
    assert 'id="sezioneVetrina"' in html


def test_la_testata_dice_i_turni_modificati(admin_client, db_session):
    """Rilievo del canvas (12/09): «Al 5 · Palla 8» prendeva sempre i valori
    della creazione. Con un override per turno la descrizione lo dice."""
    gara = _gara(db_session)
    db_session.add(
        RoundConfiguration(
            gara_id=gara.id,
            round_number=2,
            discipline=Discipline.NINE_BALL.value,
            distance=3,
        )
    )
    db_session.commit()
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert "c7-head__override" in html
    assert "turno 2" in html
    assert "Palla 9" in html
    assert "al 3 triangoli" in html


# ── Apri le iscrizioni ────────────────────────────────────────────────────────


def test_apri_le_iscrizioni_con_minimo_e_massimo(admin_client, db_session):
    gara = _gara(db_session)
    inizio = date.today().strftime("%Y-%m-%dT10:00")
    fine = (date.today() + timedelta(days=2)).strftime("%Y-%m-%dT19:30")
    resp = admin_client.post(
        f"/admin/gara/{gara.id}/open_inscriptions",
        data={
            "inscription_start": inizio,
            "inscription_end": fine,
            "min_participants": "8",
            "max_participants": "16",
        },
    )
    assert resp.status_code == 302
    refreshed = db_session.get(Gara, gara.id)
    assert refreshed.status == GaraStatus.INSCRIPTION.value
    assert refreshed.min_participants == 8
    assert refreshed.max_participants == 16


def test_apri_le_iscrizioni_senza_massimo(admin_client, db_session):
    gara = _gara(db_session)
    gara.max_participants = 12
    db_session.commit()
    inizio = date.today().strftime("%Y-%m-%dT10:00")
    fine = (date.today() + timedelta(days=2)).strftime("%Y-%m-%dT19:30")
    admin_client.post(
        f"/admin/gara/{gara.id}/open_inscriptions",
        data={
            "inscription_start": inizio,
            "inscription_end": fine,
            "min_participants": "6",
            "max_participants": "",
        },
    )
    refreshed = db_session.get(Gara, gara.id)
    assert refreshed.status == GaraStatus.INSCRIPTION.value
    assert refreshed.max_participants is None


def test_un_minimo_vuoto_lascia_quello_che_c_e(admin_client, db_session):
    """Rilievo della revisione automatica: un minimo vuoto non e' zero."""
    gara = _gara(db_session)
    inizio = date.today().strftime("%Y-%m-%dT10:00")
    fine = (date.today() + timedelta(days=2)).strftime("%Y-%m-%dT19:30")
    admin_client.post(
        f"/admin/gara/{gara.id}/open_inscriptions",
        data={
            "inscription_start": inizio,
            "inscription_end": fine,
            "min_participants": "",
            "max_participants": "",
        },
    )
    refreshed = db_session.get(Gara, gara.id)
    assert refreshed.status == GaraStatus.INSCRIPTION.value
    assert refreshed.min_participants == 4


def test_un_massimo_sotto_il_minimo_non_apre(admin_client, db_session):
    gara = _gara(db_session)
    inizio = date.today().strftime("%Y-%m-%dT10:00")
    fine = (date.today() + timedelta(days=2)).strftime("%Y-%m-%dT19:30")
    admin_client.post(
        f"/admin/gara/{gara.id}/open_inscriptions",
        data={
            "inscription_start": inizio,
            "inscription_end": fine,
            "min_participants": "8",
            "max_participants": "6",
        },
    )
    refreshed = db_session.get(Gara, gara.id)
    assert refreshed.status == GaraStatus.SETUP.value
    assert refreshed.min_participants == 4


# ── Esercizi fra i turni con Amalfi ──────────────────────────────────────────


def test_gli_esercizi_fra_i_turni_valgono_anche_con_amalfi(
    admin_client, db_session, app
):
    """Decisione 4 del canvas: il limite al casuale stava nelle route, non
    nel servizio."""
    from models.challenge import Challenge

    gara = _gara(db_session, strategy="amalfi")
    challenge = Challenge(
        title="Stop shot",
        description="Ferma la battente",
        pass_fail_only=False,
        is_active=True,
        image_path="stop.png",
    )
    db_session.add(challenge)
    db_session.commit()

    resp = admin_client.post(
        f"/admin/gara/{gara.id}/add_challenge",
        data={"challenge_id": challenge.id, "round_number": 2, "max_attempts": 2},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["success"] is True

    html = admin_client.get(f"/admin/gara/{gara.id}/preparazione/esercizi").get_data(
        as_text=True
    )
    assert "Stop shot" in html
    assert "dopo il turno 2" in html


def test_sul_tabellone_gli_esercizi_fra_i_turni_sono_negati(admin_client, db_session):
    from models.challenge import Challenge

    gara = _gara(db_session, strategy="direct_elimination")
    challenge = Challenge(
        title="Tiro lungo",
        description="In sponda",
        pass_fail_only=True,
        is_active=True,
        image_path="tiro.png",
    )
    db_session.add(challenge)
    db_session.commit()
    resp = admin_client.post(
        f"/admin/gara/{gara.id}/add_challenge",
        data={"challenge_id": challenge.id, "round_number": 1, "max_attempts": 1},
    )
    assert resp.status_code == 400
