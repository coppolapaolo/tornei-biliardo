"""Regression (bug 2 docs/debug20260528.md): le debug action `fill_gara` e
`inscribe_next_player` devono usare i quick-login player e fermarsi al
minimo (fill) o aggiungerne uno alla volta (inscribe), rispettando il
limite massimo.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Inscription, User
from models.base import utc_now
from models.status_enum import GaraStatus
from models.user.role_enum import UserRole


def _make_players(db_session, count: int) -> list[User]:
    """Crea `count` player con username 'playerN_<uid>' (quick-login)."""
    players = []
    uid = str(uuid.uuid4())[:6]
    for i in range(1, count + 1):
        p = User(
            username=f"player{i}_{uid}",
            email=f"p{i}_{uid}@test.local",
            role=UserRole.PLAYER.value,
        )
        p.set_password("x")
        db_session.add(p)
        players.append(p)
    db_session.commit()
    return players


def _make_open_gara(db_session, *, min_p: int, max_p: int) -> Gara:
    gara = Gara(
        number=1,
        name=f"GaraDbg {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=7),
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        rounds_count=2,
        min_participants=min_p,
        max_participants=max_p,
        status=GaraStatus.INSCRIPTION.value,
        inscription_start=utc_now() - timedelta(hours=1),
        inscription_end=utc_now() + timedelta(days=2),
    )
    db_session.add(gara)
    db_session.commit()
    return gara


@pytest.mark.integration
class TestDebugFillGara:
    def test_fill_gara_stops_at_minimum(self, client, db_session):
        players = _make_players(db_session, count=6)
        gara = _make_open_gara(db_session, min_p=4, max_p=10)

        # Iscrivi i primi 2 manualmente: dovrebbe colmare fino a 4
        from models.competition.inscription_service import InscriptionService

        InscriptionService.inscribe_user(players[0].id, gara.id)
        InscriptionService.inscribe_user(players[1].id, gara.id)

        resp = client.get(f"/debug/fill_gara/{gara.id}", follow_redirects=False)

        assert resp.status_code in (302, 303)
        active = Inscription.query.filter_by(
            gara_id=gara.id, is_waitlist=False, is_withdrawn=False
        ).count()
        assert (
            active == 4
        ), f"Atteso 4 (min), trovato {active}. Fill deve fermarsi al minimo."

    def test_fill_gara_no_op_when_min_already_reached(self, client, db_session):
        players = _make_players(db_session, count=5)
        gara = _make_open_gara(db_session, min_p=3, max_p=10)

        from models.competition.inscription_service import InscriptionService

        for p in players[:3]:
            InscriptionService.inscribe_user(p.id, gara.id)

        resp = client.get(f"/debug/fill_gara/{gara.id}", follow_redirects=False)

        assert resp.status_code in (302, 303)
        active = Inscription.query.filter_by(
            gara_id=gara.id, is_waitlist=False, is_withdrawn=False
        ).count()
        assert active == 3, "Min raggiunto: nessuna iscrizione aggiunta"

    def test_inscribe_next_player_adds_one(self, client, db_session):
        _make_players(db_session, count=5)
        gara = _make_open_gara(db_session, min_p=2, max_p=10)

        resp = client.get(
            f"/debug/inscribe_next_player/{gara.id}", follow_redirects=False
        )

        assert resp.status_code in (302, 303)
        active = Inscription.query.filter_by(
            gara_id=gara.id, is_waitlist=False, is_withdrawn=False
        ).count()
        assert active == 1, f"Atteso 1 iscrizione, trovate {active}"

    def test_inscribe_next_player_stops_at_maximum(self, client, db_session):
        players = _make_players(db_session, count=8)
        gara = _make_open_gara(db_session, min_p=2, max_p=3)

        from models.competition.inscription_service import InscriptionService

        for p in players[:3]:
            InscriptionService.inscribe_user(p.id, gara.id)

        resp = client.get(
            f"/debug/inscribe_next_player/{gara.id}", follow_redirects=False
        )

        assert resp.status_code in (302, 303)
        active = Inscription.query.filter_by(
            gara_id=gara.id, is_waitlist=False, is_withdrawn=False
        ).count()
        assert active == 3, "Max raggiunto: nessuna iscrizione aggiunta"
