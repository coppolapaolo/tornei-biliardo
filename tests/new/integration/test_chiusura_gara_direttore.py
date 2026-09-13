"""Spareggio e gara conclusa dalla pagina del direttore (canvas 4.x e 5.x).

Una gara vera a un turno: quattro giocatori, due partite 5–3. I due
vincitori sono pari al primo posto e i due perdenti al terzo, quindi con lo
spareggio acceso ci sono due gruppi da sciogliere.
"""

from __future__ import annotations

from datetime import date

import pytest

from models import Gara, Inscription, Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture
def admin_client(client, db_session):
    from models.user.services import UserService

    user = UserService.create_user(
        "chiusura_admin", "chiusura_admin@test.local", "pw12345"
    )
    user.role = UserRole.ADMIN.value
    db_session.commit()
    resp = client.post(
        "/auth/login", data={"username": "chiusura_admin", "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    return client


def _gara_a_un_turno(db_session, status, *, spareggio):
    from models.user.services import UserService

    gara = Gara(
        number=1,
        name="Gara da chiudere",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
        matchmaking_strategy="amalfi",
        status=status,
        current_round=1,
        rounds_count=1,
        min_participants=4,
        classification_system="WINS",
        tiebreaker_enabled=spareggio,
    )
    db_session.add(gara)
    db_session.commit()
    giocatori = [
        UserService.create_user(f"chiu_{n}", f"chiu_{n}@test.local", "pw12345")
        for n in ("rossi", "verdi", "galli", "neri")
    ]
    for u in giocatori:
        db_session.add(Inscription(user_id=u.id, gara_id=gara.id, is_waitlist=False))
    for vince, perde in ((giocatori[0], giocatori[1]), (giocatori[2], giocatori[3])):
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=1,
                player1_id=vince.id,
                player2_id=perde.id,
                player1_score=5,
                player2_score=3,
                winner_id=vince.id,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )
        )
    db_session.commit()
    return gara


def test_in_spareggio_i_punti_si_segnano_con_gli_stepper(admin_client, db_session):
    gara = _gara_a_un_turno(db_session, GaraStatus.AWAITING_SSR.value, spareggio=True)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

    assert "Inserisci i punti" in html
    assert "Parimerito per il 1° posto" in html
    assert "passoSsr(this, 1)" in html
    assert "ssr-group-input" in html
    # «Termina» resta spento finche' i gruppi non sono sciolti.
    termina = html.split("terminateGara(")[1].split(">")[0]
    assert "disabled" in termina
    # I parimerito aperti hanno la pastiglia in classifica.
    assert "c7-classifica__pill" in html


def test_a_gara_conclusa_la_classifica_ha_il_podio(admin_client, db_session):
    gara = _gara_a_un_turno(db_session, GaraStatus.COMPLETED.value, spareggio=False)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

    assert "Gara conclusa" in html
    assert "c7-podio-finale" in html and "c7-podio-finale__avatar--oro" in html
    assert "Classifica finale" in html
    # Le partite restano in pagina, in righe (5S), turno 1 compreso.
    assert "c7-riga-partita" in html
    assert "Resta bloccato" in html
