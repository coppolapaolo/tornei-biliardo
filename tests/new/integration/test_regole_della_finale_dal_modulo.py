"""Le regole della finale, dal modulo della gara singola alle partite.

Decisione dell'utente del 2026-10-12: le regole dei turni del tabellone dopo
i gironi si impostano **per fase** nel modulo, prima dell'avvio — la finale
«senza limite» e «al 7», la fase finale «al 4» — perché prima dell'avvio non
si sa quale numero di turno sarà la finale. Qui il passaggio intero:
modulo → avvio → gironi → semifinali → finale, con le regole fissate sulle
partite (ADR-075), e la tessera in dashboard che dice «Semifinale».
"""

from __future__ import annotations


import pytest

from models import Gara, User
from models.base import db
from models.competition.round_service import RoundService
from models.match.models import Match
from models.matchmaking.bracket import BRACKET_THIRD_PLACE, BRACKET_WINNERS
from tests.new.integration.test_fase_finale_dal_modulo import (  # noqa: F401
    _crea,
    _gioca,
    _iscrivi,
    _login,
    direttore,
)

pytestmark = pytest.mark.integration


def test_il_modulo_porta_le_regole_della_finale(client, direttore):  # noqa: F811
    _login(client, direttore)
    pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)
    for nome in (
        "final_phase_distance_mode",
        "final_phase_distance",
        "final_time_limit",
        "final_time_limit_minutes",
        "final_distance_mode",
        "final_distance",
    ):
        assert f'name="{nome}"' in pagina
    assert "La finale" in pagina


def test_finale_senza_limite_e_al_7(client, db_session, direttore):  # noqa: F811
    gara = _crea(
        client,
        direttore,
        time_limit_minutes="30",
        final_phase_time_limit="minuti",
        final_phase_time_limit_minutes="45",
        final_phase_distance_mode="altra",
        final_phase_distance="4",
        final_time_limit="nessuno",
        final_time_limit_minutes="",
        final_distance_mode="altra",
        final_distance="7",
    )
    assert gara.final_phase_distance == 4
    assert gara.final_time_limit_minutes == 0
    assert gara.final_distance == 7

    elo = _iscrivi(db_session, gara, 8)
    pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert "la finale al 7, senza limite di tempo" in pagina

    RoundService.start_first_round(gara.id, groups_count=2)
    db.session.commit()
    gara = db.session.get(Gara, gara.id)
    assert gara.rounds_count == 5
    for r in range(1, 5):
        if r > 1:
            RoundService.start_next_round(gara.id, r)
            db.session.commit()
        _gioca(gara.id, r, elo)

    # La tessera di un semifinalista dice il nome del turno.
    semifinale = Match.query.filter_by(gara_id=gara.id, round_number=4).first()
    assert semifinale.effective_distance == 4

    RoundService.start_next_round(gara.id, 5)
    db.session.commit()
    finale = Match.query.filter_by(
        gara_id=gara.id, round_number=5, bracket_type=BRACKET_WINNERS
    ).one()
    finalina = Match.query.filter_by(
        gara_id=gara.id, round_number=5, bracket_type=BRACKET_THIRD_PLACE
    ).one()
    assert finale.effective_distance == 7
    assert finale.time_limit_minutes is None
    assert finalina.effective_distance == 4
    assert finalina.time_limit_minutes == 45
    # Le pagine reggono la finale.
    assert client.get(f"/admin/gara/{gara.id}").status_code == 200

    # La tessera del finalista: «La tua partita · Finale».
    finalista = db.session.get(User, finale.player1_id)
    finalista.set_password("x")
    finalista.onboarding_completed = True
    db.session.commit()
    giocatore = client.application.test_client()
    giocatore.post(
        "/auth/login",
        data={"username": finalista.username, "password": "x"},
        follow_redirects=True,
    )
    dashboard = giocatore.get("/dashboard", follow_redirects=True).get_data(
        as_text=True
    )
    assert "La tua partita" in dashboard
    blocco = dashboard[dashboard.index("La tua partita") :][:400]
    assert "Finale" in blocco
    assert "Turno" not in blocco


def test_la_tessera_nei_gironi_dice_il_turno(
    client, db_session, direttore  # noqa: F811
):
    gara = _crea(client, direttore)
    _iscrivi(db_session, gara, 8)
    RoundService.start_first_round(gara.id, groups_count=2)
    db.session.commit()
    partita = Match.query.filter(
        Match.gara_id == gara.id, Match.round_number == 1, Match.player2_id.isnot(None)
    ).first()
    giocatore_db = db.session.get(User, partita.player1_id)
    giocatore_db.set_password("x")
    giocatore_db.onboarding_completed = True
    db.session.commit()
    giocatore = client.application.test_client()
    giocatore.post(
        "/auth/login",
        data={"username": giocatore_db.username, "password": "x"},
        follow_redirects=True,
    )
    dashboard = giocatore.get("/dashboard", follow_redirects=True).get_data(
        as_text=True
    )
    blocco = dashboard[dashboard.index("La tua partita") :][:400]
    assert "Turno" in blocco
