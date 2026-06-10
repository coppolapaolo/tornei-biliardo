"""Regression (review 2026-06, batch 7): bug di correttezza nelle route.

Triage 2026-06-10 della sezione "Da ri-verificare a mano" del report
docs/_archive/2026-06-09-codebase-review-uncovered.md.
"""

import uuid
from datetime import date, time, timedelta

import pytest

from models import Challenge, db
from models.base import utc_now
from models.competition.gara_challenge import GaraChallenge
from models.competition.models import Gara
from models.status_enum import GaraStatus
from models.user.models import User


def _make_user(db_session, role):
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"b7_{role}_{uid}", email=f"b7_{role}_{uid}@t.com", role=role)
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    return db_session.get(User, user.id)


def _login(client, user):
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=True,
    )


@pytest.fixture
def director_user(db_session):
    return _make_user(db_session, "director")


@pytest.fixture
def player_user(db_session):
    return _make_user(db_session, "player")


@pytest.fixture
def random_gara_with_challenge(db_session, director_user, player_user):
    """Gara Random gestita dal director, con una GaraChallenge attiva."""
    uid = uuid.uuid4().hex[:8]
    gara = Gara(
        name=f"B7 Random {uid}",
        number=1,
        date=date.today() + timedelta(days=7),
        time=time(18, 0),
        discipline="palla_8",
        distance=5,
        rounds_count=3,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="random",
        director_id=director_user.id,
        status=GaraStatus.PLAYING.value,
        inscription_start=utc_now() - timedelta(days=1),
        inscription_end=utc_now() - timedelta(hours=1),
    )
    db_session.add(gara)
    db_session.flush()

    challenge = Challenge(
        description="Challenge batch 7",
        image_path="b7.jpg",
        pass_fail_only=True,
        created_by_id=director_user.id,
        is_active=True,
    )
    db_session.add(challenge)
    db_session.flush()

    gara_challenge = GaraChallenge(
        gara_id=gara.id,
        challenge_id=challenge.id,
        round_number=1,
        max_attempts=3,
        is_active=True,
        added_by_id=director_user.id,
    )
    db_session.add(gara_challenge)
    db_session.commit()
    return gara, gara_challenge


class TestRecordChallengeAttemptRoutes:
    """Bug 1: @match_manager_required su route senza <match_id> → 400 sempre.

    Le route /admin/match/record_challenge_attempt(s) non hanno match_id
    nell'URL: il decorator abortiva ogni richiesta con 400 e la registrazione
    challenge da pannello admin era morta. L'autorizzazione corretta e' sulla
    GARA della challenge.
    """

    def test_director_can_record_attempt(
        self, client, db_session, director_user, player_user, random_gara_with_challenge
    ):
        _, gara_challenge = random_gara_with_challenge
        _login(client, director_user)

        response = client.post(
            "/admin/match/record_challenge_attempt",
            json={
                "gara_challenge_id": gara_challenge.id,
                "user_id": player_user.id,
                "passed": True,
            },
        )

        assert response.status_code == 200
        assert response.get_json()["success"] is True

    def test_director_can_record_attempts_bulk(
        self, client, db_session, director_user, player_user, random_gara_with_challenge
    ):
        _, gara_challenge = random_gara_with_challenge
        _login(client, director_user)

        response = client.post(
            "/admin/match/record_challenge_attempts",
            json={
                "attempts": [
                    {
                        "gara_challenge_id": gara_challenge.id,
                        "user_id": player_user.id,
                        "passed": True,
                    }
                ]
            },
        )

        assert response.status_code == 200
        assert response.get_json()["success"] is True

    def test_unrelated_player_gets_403(
        self, client, db_session, player_user, random_gara_with_challenge
    ):
        """Un player che NON gestisce la gara non puo' registrare tentativi."""
        _, gara_challenge = random_gara_with_challenge
        _login(client, player_user)

        response = client.post(
            "/admin/match/record_challenge_attempt",
            json={
                "gara_challenge_id": gara_challenge.id,
                "user_id": player_user.id,
                "passed": True,
            },
        )

        assert response.status_code == 403


class TestConfirmResultBilateral:
    """Bug 2: confirm_result confrontava lo status col letterale "completed".

    Dopo la conferma bilaterale lo status e' VALIDATED: la route rispondeva
    completed=False e "In attesa dell'altro giocatore" anche a match chiuso.
    """

    def test_second_confirmation_reports_completed(self, client, db_session):
        from models.individual_match.models import IndividualMatch
        from models.status_enum import MatchStatus

        p1 = _make_user(db_session, "player")
        p2 = _make_user(db_session, "player")
        match = IndividualMatch(
            player1_id=p1.id,
            player2_id=p2.id,
            location="Test Hall",
            scheduled_at=utc_now() - timedelta(hours=2),
            status=MatchStatus.IN_PROGRESS,  # conferme avvengono a match attivo
            distance=5,
            is_race_to=True,
            player1_score=5,
            player2_score=2,
            player1_confirmed=True,  # p1 ha gia' confermato
        )
        db_session.add(match)
        db_session.commit()

        _login(client, p2)
        response = client.post(f"/match/matches/{match.id}/confirm", json={})

        assert response.status_code == 200
        payload = response.get_json()
        assert payload["success"] is True
        # Seconda conferma = match chiuso: la route deve dirlo.
        assert payload["completed"] is True


class TestAddRackReportedBy:
    """Bug 3: add_rack_result registrava reported_by_id=1 hardcoded."""

    def test_rack_attributed_to_current_user(self, client, db_session):
        from models.match.models import Match, Rack
        from models.status_enum import MatchStatus

        # Il primo utente del DB di test prende id=1: crea prima i player
        # cosi' il director NON ha id=1 e l'hardcoded non passa per caso.
        p1 = _make_user(db_session, "player")
        p2 = _make_user(db_session, "player")
        director = _make_user(db_session, "director")
        assert director.id != 1

        gara = Gara(
            name=f"B7 Rack {uuid.uuid4().hex[:8]}",
            number=1,
            date=date.today() + timedelta(days=7),
            time=time(18, 0),
            discipline="palla_8",
            distance=5,
            rounds_count=3,
            min_participants=2,
            max_participants=10,
            matchmaking_strategy="random",
            director_id=director.id,
            status=GaraStatus.PLAYING.value,
            inscription_start=utc_now() - timedelta(days=1),
            inscription_end=utc_now() - timedelta(hours=1),
        )
        db_session.add(gara)
        db_session.flush()
        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p1.id,
            player2_id=p2.id,
            status=MatchStatus.PLAYING.value,
        )
        db_session.add(match)
        db_session.commit()

        _login(client, director)
        response = client.post(
            f"/admin/match/{match.id}/add_rack", data={"winner_id": p1.id}
        )

        assert response.status_code == 200
        rack = db_session.query(Rack).filter_by(match_id=match.id).one()
        assert rack.reported_by_id == director.id


class TestGamificationAdminFormParsing:
    """Bug 4: parsing form non protetto (int/fromisoformat/Enum[...]) → 500."""

    @pytest.fixture
    def admin_user(self, db_session):
        return _make_user(db_session, "admin")

    def test_create_quest_invalid_type_redirects(self, client, db_session, admin_user):
        _login(client, admin_user)
        response = client.post(
            "/gamification/admin/quests/create",
            data={"name": "Q", "quest_type": "foobar"},
        )
        assert response.status_code == 302  # redirect con flash, non 500

    def test_create_quest_invalid_date_redirects(self, client, db_session, admin_user):
        _login(client, admin_user)
        response = client.post(
            "/gamification/admin/quests/create",
            data={"name": "Q", "start_date": "2026-13-99"},
        )
        assert response.status_code == 302

    def test_grant_freeze_invalid_streak_type_redirects(
        self, client, db_session, admin_user
    ):
        _login(client, admin_user)
        response = client.post(
            "/gamification/admin/streaks/grant_freeze",
            data={"user_id": str(admin_user.id), "streak_type": "BOGUS"},
        )
        assert response.status_code == 302

    def test_grant_xp_non_numeric_redirects(self, client, db_session, admin_user):
        _login(client, admin_user)
        response = client.post(
            "/gamification/admin/xp/grant",
            data={"user_id": str(admin_user.id), "xp_amount": "ten"},
        )
        assert response.status_code == 302


class TestIndividualMatchMissingFields:
    """Bug 5: data["campo"] con indicizzazione diretta → KeyError → 500."""

    @pytest.fixture
    def in_progress_match(self, db_session):
        from models.individual_match.models import IndividualMatch
        from models.status_enum import MatchStatus

        p1 = _make_user(db_session, "player")
        p2 = _make_user(db_session, "player")
        match = IndividualMatch(
            player1_id=p1.id,
            player2_id=p2.id,
            location="Test Hall",
            scheduled_at=utc_now() - timedelta(hours=1),
            status=MatchStatus.IN_PROGRESS,
            distance=5,
            is_race_to=True,
            player1_score=1,
            player2_score=0,
        )
        db_session.add(match)
        db_session.commit()
        return match, p1, p2

    def test_add_rack_without_winner_id_is_400(
        self, client, db_session, in_progress_match
    ):
        match, p1, _ = in_progress_match
        _login(client, p1)
        response = client.post(f"/match/matches/{match.id}/racks/add", json={})
        assert response.status_code == 400

    def test_remove_rack_without_player_id_is_400(
        self, client, db_session, in_progress_match
    ):
        match, p1, _ = in_progress_match
        _login(client, p1)
        response = client.post(f"/match/matches/{match.id}/racks/remove", json={})
        assert response.status_code == 400

    def test_complete_match_without_winner_id_is_400(
        self, client, db_session, in_progress_match
    ):
        match, p1, _ = in_progress_match
        _login(client, p1)
        response = client.post(f"/match/matches/{match.id}/complete", json={})
        assert response.status_code == 400

    def test_create_proposal_without_scheduled_at_is_400(self, client, db_session):
        p1 = _make_user(db_session, "player")
        _login(client, p1)
        response = client.post("/match/proposals/create", json={"location": "Hall"})
        assert response.status_code == 400


class TestRematchPreservesFormat:
    """Bug 6: rematch non passava match_format → multi-set/free diventava
    sempre single race-to-5."""

    def _completed_match(self, db_session, **extra):
        from models.individual_match.models import IndividualMatch
        from models.status_enum import MatchStatus

        p1 = _make_user(db_session, "player")
        p2 = _make_user(db_session, "player")
        match = IndividualMatch(
            player1_id=p1.id,
            player2_id=p2.id,
            location="Test Hall",
            scheduled_at=utc_now() - timedelta(hours=3),
            status=MatchStatus.VALIDATED,
            winner_id=p1.id,
            **extra,
        )
        db_session.add(match)
        db_session.commit()
        return match, p1

    def test_rematch_multi_set_passes_format(self, client, db_session):
        match, p1 = self._completed_match(
            db_session,
            distance=4,  # rack per set
            is_race_to=True,
            is_multi_set=True,
            match_distance=3,
            player1_score=3,
            player2_score=1,
        )
        _login(client, p1)
        response = client.get(f"/match/matches/{match.id}/rematch")
        assert response.status_code == 302
        assert "match_format=multi" in response.location
        assert "set_distance=4" in response.location

    def test_rematch_free_format_passes_format(self, client, db_session):
        match, p1 = self._completed_match(
            db_session,
            distance=None,  # free format
            is_race_to=True,
            player1_score=3,
            player2_score=2,
        )
        _login(client, p1)
        response = client.get(f"/match/matches/{match.id}/rematch")
        assert response.status_code == 302
        assert "match_format=free" in response.location

    def test_create_proposal_prefills_multi_format(self, client, db_session):
        p1 = _make_user(db_session, "player")
        _login(client, p1)
        response = client.get(
            "/match/proposals/create?rematch=true&match_format=multi"
            "&set_distance=4&match_distance=3"
        )
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        # Il radio multi deve essere preselezionato
        import re

        multi_radio = re.search(r'<input[^>]*id="formatMulti"[^>]*>', html)
        assert multi_radio and "checked" in multi_radio.group(0)


class TestToggleVenueStatusCoercion:
    """Bug 7: value senza coercizione bool — 'false' (stringa truthy)
    ATTIVAVA la sala, None finiva NULL nel campo."""

    @pytest.fixture
    def active_venue(self, db_session):
        from models.location.models import BilliardHall

        hall = BilliardHall(name=f"B7 Sala {uuid.uuid4().hex[:8]}", is_active=True)
        db_session.add(hall)
        db_session.commit()
        return hall

    def test_string_false_deactivates(self, client, db_session, active_venue):
        from models.location.models import BilliardHall

        admin = _make_user(db_session, "admin")
        _login(client, admin)

        response = client.post(
            f"/admin/venues/{active_venue.id}/toggle",
            json={"field": "is_active", "value": "false"},
        )

        assert response.status_code == 200
        db_session.expire_all()
        assert db_session.get(BilliardHall, active_venue.id).is_active is False

    def test_missing_value_is_400(self, client, db_session, active_venue):
        admin = _make_user(db_session, "admin")
        _login(client, admin)
        response = client.post(
            f"/admin/venues/{active_venue.id}/toggle",
            json={"field": "is_active"},
        )
        assert response.status_code == 400


class TestStartFirstRoundMissingGara:
    """Bug 8: start_first_round su gara inesistente flashava successo."""

    def test_nonexistent_gara_is_404(self, client, db_session):
        admin = _make_user(db_session, "admin")
        _login(client, admin)
        response = client.post("/admin/gara/999999/start_first_round")
        assert response.status_code == 404
