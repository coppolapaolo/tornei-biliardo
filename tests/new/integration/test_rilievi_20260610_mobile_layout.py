"""Regression rilievo test manuale 2026-06-10 (vista mobile admin/gara).

Principio: l'interfaccia mobile mostra prima le cose azionabili in quel
momento e sposta dopo tutto il resto. In fase di gioco l'azionabile sono le
partite (risultati da inserire), non Gestione/Direttori: l'ordine visivo
mobile e' Partite -> Gestione Turni -> Gestione (collassata) -> Direttori,
ottenuto con classi flex order-* (DOM unico, desktop invariato via order-md).
"""

import re
from datetime import date

import pytest

from models import Gara, Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _classes_of(html: str, section_id: str) -> str:
    tag = re.search(rf'<div class="([^"]*)" id="{section_id}"', html)
    assert tag, f"sezione {section_id} non trovata"
    return tag.group(1)


@pytest.fixture
def admin_client(client, db_session):
    from models.user.services import UserService

    user = UserService.create_user("mobile_admin", "mobile_admin@test.local", "pw12345")
    user.role = UserRole.ADMIN.value
    db_session.commit()
    resp = client.post(
        "/auth/login", data={"username": "mobile_admin", "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    return client


def _make_gara(db_session, status):
    gara = Gara(
        number=1,
        name="Gara Layout Mobile",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        matchmaking_strategy="random",
        status=status,
        current_round=1,
        rounds_count=3,
        min_participants=4,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def test_playing_phase_mobile_order_actionable_first(admin_client, db_session):
    from models.user.services import UserService

    gara = _make_gara(db_session, GaraStatus.PLAYING.value)
    p1 = UserService.create_user("mobile_pl1", "mobile_pl1@test.local", "pw12345")
    p2 = UserService.create_user("mobile_pl2", "mobile_pl2@test.local", "pw12345")
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        status=MatchStatus.PLAYING.value,
    )
    db_session.add(match)
    db_session.commit()

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Ordine visivo mobile: partite(1) -> turni(2) -> gestione(3) -> direttori(4)
    assert "order-1" in _classes_of(html, "sectionPartite")
    assert "order-2" in _classes_of(html, "sectionTurni")
    gestione = _classes_of(html, "sectionGestioneMobile")
    assert "order-3" in gestione and "d-md-none" in gestione
    assert "order-4" in _classes_of(html, "sectionDirettori")
    # Desktop invariato: ordine ripristinato dalle classi order-md-*
    assert "order-md-1" in _classes_of(html, "sectionDirettori")
    assert "order-md-3" in _classes_of(html, "sectionPartite")


def test_inscription_phase_keeps_default_layout(admin_client, db_session):
    gara = _make_gara(db_session, GaraStatus.INSCRIPTION.value)

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Fuori dalla fase di gioco l'azionabile e' la gestione: niente riordino
    assert 'id="sectionGestioneMobile"' not in html
    assert "order-1" not in _classes_of(html, "sectionPartite")
