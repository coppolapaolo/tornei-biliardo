"""Regressione issue #66 — il director che gioca non riusciva a segnare.

In una gara standalone di cui non era né creatore né co-direttore, un utente
con ruolo `director` vedeva l'interfaccia giocatore ma il pulsante "+"
puntava all'endpoint admin (`/admin/match/<id>/add_rack`), scelto in base al
*ruolo globale* invece che ai permessi sulla gara: `@match_manager_required`
lo respingeva e la pagina mostrava un flash rosso.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db
from models.competition.services import GaraService
from models.match.models import Match
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _make_user(db_session, role):
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"{role}_{uid}", email=f"{role}_{uid}@test.com", role=role)
    user.set_password("secret123")
    db_session.add(user)
    db_session.commit()
    return user


def _make_playing_match(db_session, owner, player1, player2):
    """Gara standalone di `owner`, con un match in corso fra i due giocatori."""
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Standalone {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=1),
        location="Test Venue",
        rounds_count=1,
        min_participants=2,
        entry_fee=0.0,
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=owner.id,
        matchmaking_strategy="amalfi",
    )
    gara.status = GaraStatus.PLAYING.value
    gara.current_round = 1
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=player1.id,
        player2_id=player2.id,
        status=MatchStatus.PLAYING.value,
        table_assignment="1",
    )
    db.session.add(match)
    db_session.commit()
    return gara, match


@pytest.mark.integration
class TestDirectorPlayingSomeoneElsesGara:

    def test_add_rack_uses_player_endpoint(self, db_session, client):
        """Il director che gioca deve usare il flusso player, come chiunque."""
        owner = _make_user(db_session, UserRole.DIRECTOR.value)
        director_player = _make_user(db_session, UserRole.DIRECTOR.value)
        opponent = _make_user(db_session, UserRole.PLAYER.value)
        _gara, match = _make_playing_match(db_session, owner, director_player, opponent)

        login = client.post(
            "/auth/login",
            data={"username": director_player.username, "password": "secret123"},
            follow_redirects=True,
        )
        assert login.status_code == 200

        response = client.get(f"/admin/match/{match.id}")
        assert response.status_code == 200

        html = response.get_data(as_text=True)
        assert f"/player/match/{match.id}/racks/add" in html
        assert f"/admin/match/{match.id}/add_rack" not in html

    def test_manager_still_uses_admin_endpoint(self, db_session, client):
        """Chi gestisce davvero la gara (e non ci gioca) resta sul flusso admin."""
        owner = _make_user(db_session, UserRole.DIRECTOR.value)
        player1 = _make_user(db_session, UserRole.PLAYER.value)
        player2 = _make_user(db_session, UserRole.PLAYER.value)
        _gara, match = _make_playing_match(db_session, owner, player1, player2)

        login = client.post(
            "/auth/login",
            data={"username": owner.username, "password": "secret123"},
            follow_redirects=True,
        )
        assert login.status_code == 200

        response = client.get(f"/admin/match/{match.id}")
        assert response.status_code == 200

        html = response.get_data(as_text=True)
        assert f"/admin/match/{match.id}/add_rack" in html
