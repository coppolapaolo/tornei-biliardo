"""Regression rilievo test manuale 2026-06-10 (vista mobile admin/gara).

Principio: l'interfaccia mobile mostra prima le cose azionabili in quel
momento e sposta dopo tutto il resto. In fase di gioco l'azionabile sono le
partite (risultati da inserire), non Gestione/Direttori: l'ordine visivo
mobile e' Partite -> Gestione Turni -> Gestione (collassata) -> Direttori,
ottenuto con classi flex order-* (DOM unico, desktop invariato via order-lg:
il guscio 7c cambia impaginazione a 992px, non a 768px).
"""

import re
from datetime import date

import pytest

from models import Gara, Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

# Testata "Gestione" nel design 7c: h3 a tutta riga, senza l'icona a
# ingranaggio di prima. Conta le occorrenze per scoprire i duplicati.
GESTIONE_HEADING = 'flex-fill">Gestione</h3>'


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


def test_playing_phase_console_before_matches(admin_client, db_session):
    """In gioco l'azionabile viene prima: dal 2026-09-12 la pagina del
    direttore e' quella a fasi, e la card della console (o la fascia col
    comando) sta sopra le partite, per mobile e desktop insieme."""
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

    assert "c7-console" in html
    assert html.index("c7-console") < html.index('id="sezioneIscritti"')
    assert 'id="sectionGestioneMobile"' not in html


def test_inscription_phase_fascia_first(admin_client, db_session):
    gara = _make_gara(db_session, GaraStatus.INSCRIPTION.value)

    resp = admin_client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    # Fuori dalla fase di gioco l'azionabile e' avviare la gara: sta nella
    # fascia, prima dell'elenco degli iscritti.
    assert "Iscrizioni aperte" in html
    assert html.index("c7-fascia") < html.index("Nessun iscritto")
