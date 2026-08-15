"""Route POST /admin/gara/<id>/cancel_ssr — annullamento della fase spareggio.

Copre il percorso che l'utente tocca davvero: il director preme "Annulla
Spareggio (SSR)" e la gara deve tornare in gioco con i punteggi azzerati.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models.classification.models import GaraClassification
from models.competition.models import Gara
from models.status_enum import GaraStatus


def _uid() -> str:
    return str(uuid.uuid4())[:8]


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "test123"},
        follow_redirects=True,
    )


def _make_gara(db_session, director, status: str) -> Gara:
    existing = db_session.query(Gara).count()
    gara = Gara(
        name=f"Cancel-SSR route {_uid()}",
        number=existing + 1,
        date=date.today(),
        distance=5,
        discipline="9_ball",
        matchmaking_strategy="random",
        status=status,
        is_race_to=True,
        director_id=director.id,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


@pytest.mark.integration
class TestCancelSsrRoute:
    def test_cancel_ssr_returns_gara_to_playing(
        self, client, db_session, isolated_director_user
    ):
        director = isolated_director_user
        director.set_password("test123")
        gara = _make_gara(db_session, director, GaraStatus.AWAITING_SSR.value)
        gc = GaraClassification(
            gara_id=gara.id,
            user_id=director.id,
            position=1,
            matches_won=2,
            racks_won=10,
            rack_difference=4,
            spot_shot_wins=6,
            tiebreaker_resolved=True,
        )
        db_session.add(gc)
        db_session.commit()

        _login(client, director)
        response = client.post(
            f"/admin/gara/{gara.id}/cancel_ssr", follow_redirects=True
        )

        assert response.status_code == 200

        refreshed = db_session.get(Gara, gara.id)
        assert refreshed.status == GaraStatus.PLAYING.value

        db_session.refresh(gc)
        assert gc.spot_shot_wins == 0
        assert gc.tiebreaker_resolved is False

    def test_cancel_ssr_rejected_when_not_in_ssr(
        self, client, db_session, isolated_director_user
    ):
        """La gara resta com'è: niente transizione da uno stato non previsto."""
        director = isolated_director_user
        director.set_password("test123")
        gara = _make_gara(db_session, director, GaraStatus.PLAYING.value)
        db_session.commit()

        _login(client, director)
        response = client.post(
            f"/admin/gara/{gara.id}/cancel_ssr", follow_redirects=True
        )

        assert response.status_code == 200
        refreshed = db_session.get(Gara, gara.id)
        assert refreshed.status == GaraStatus.PLAYING.value
