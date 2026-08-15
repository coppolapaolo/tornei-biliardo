"""Regression lock-in: Random strategy + OddNumberPolicy.NO (parity waitlist).

Documented in _bmad-output/implementation-artifacts/spec-random-odd-policy-no.md (G2).

Context: `OddNumberPolicy.NO` semantics live in `InscriptionService` (not in
the matchmaking strategy). All strategies receive a pool filtered via
`is_waitlist=False`. These tests prove that Random behaves identically to
Amalfi for policy=NO — a regression guard for future refactors of
`_demote_last_to_parity_waitlist` / `_promote_from_parity_waitlist`.

Mirrors `tests/new/unit/test_parity_waitlist.py` at integration level with
`matchmaking_strategy="random"` and exercises `start_first_round` end-to-end
(Random creates all rounds at startup — a peculiarity this lock-in protects).
"""

import uuid
from datetime import date, timedelta
from typing import List

import pytest

from models import Gara, Match, User
from models.base import utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.models import Inscription, WaitlistReason
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.user.role_enum import UserRole


@pytest.mark.integration
class TestRandomPolicyNoInscription:
    """Inscription flow: Random + NO policy behaves like Amalfi + NO."""

    @pytest.fixture
    def director_user(self, db_session) -> User:
        unique_id = uuid.uuid4().hex[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()
        return director

    @pytest.fixture
    def players(self, db_session) -> List[User]:
        batch_id = uuid.uuid4().hex[:8]
        players = []
        for i in range(6):
            p = User(
                username=f"player_{i}_{batch_id}",
                email=f"player_{i}_{batch_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            p.set_password("player123")
            players.append(p)
        db_session.add_all(players)
        db_session.commit()
        return players

    def _create_random_no_gara(
        self, director: User, max_participants: int = 10
    ) -> Gara:
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Random NO Policy Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Random + NO parity waitlist",
            rounds_count=3,
            min_participants=2,
            max_participants=max_participants,
            entry_fee=0.0,
            discipline="8_ball",
            distance=5,
            is_race_to=True,
            director_id=director.id,
            matchmaking_strategy="random",
            first_round_policy="random",
            odd_number_policy="no",
            anti_rematch_enabled=True,
        )
        InscriptionService.open_inscriptions(
            gara.id,
            utc_now() - timedelta(hours=1),
            utc_now() + timedelta(hours=1),
        )
        return gara

    def test_first_player_accepted_despite_odd(
        self, director_user, players, db_session
    ):
        """Scenario #1: 0→1 dispari ma il primo è sempre accettato."""
        gara = self._create_random_no_gara(director_user)

        ins = InscriptionService.inscribe_user(players[0].id, gara.id)

        assert ins is not None
        assert ins.is_waitlist is False

    def test_second_player_accepted_pair(self, director_user, players, db_session):
        """Scenario #2: 1→2 pari, accettato normalmente."""
        gara = self._create_random_no_gara(director_user)
        InscriptionService.inscribe_user(players[0].id, gara.id)

        ins = InscriptionService.inscribe_user(players[1].id, gara.id)

        assert ins.is_waitlist is False

    def test_third_player_goes_to_parity_waitlist(
        self, director_user, players, db_session
    ):
        """Scenario #3: 2→3 dispari, va in PARITY waitlist posizione 1."""
        gara = self._create_random_no_gara(director_user)
        InscriptionService.inscribe_user(players[0].id, gara.id)
        InscriptionService.inscribe_user(players[1].id, gara.id)

        ins = InscriptionService.inscribe_user(players[2].id, gara.id)

        assert ins.is_waitlist is True
        assert ins.waitlist_reason == WaitlistReason.PARITY.value
        assert ins.waitlist_position == 1

    def test_fourth_player_promotes_parity_waitlist(
        self, director_user, players, db_session
    ):
        """Scenario #4: 3→4 pari, il parity waitlist viene promosso."""
        gara = self._create_random_no_gara(director_user)
        InscriptionService.inscribe_user(players[0].id, gara.id)
        InscriptionService.inscribe_user(players[1].id, gara.id)
        third = InscriptionService.inscribe_user(players[2].id, gara.id)
        third_id = third.id

        fourth = InscriptionService.inscribe_user(players[3].id, gara.id)

        db_session.expire_all()
        third_after = db_session.get(Inscription, third_id)
        assert fourth.is_waitlist is False
        assert third_after is not None
        assert third_after.is_waitlist is False
        assert third_after.waitlist_position is None

    def test_fifth_player_goes_to_parity_waitlist(
        self, director_user, players, db_session
    ):
        """Scenario #5: 4→5 dispari, va di nuovo in PARITY waitlist."""
        gara = self._create_random_no_gara(director_user)
        for i in range(4):
            InscriptionService.inscribe_user(players[i].id, gara.id)

        ins = InscriptionService.inscribe_user(players[4].id, gara.id)

        assert ins.is_waitlist is True
        assert ins.waitlist_reason == WaitlistReason.PARITY.value

    def test_uninscribe_making_odd_demotes_last(
        self, director_user, players, db_session
    ):
        """Scenario #6: 4→3 dispari, ultimo iscritto va in PARITY waitlist."""
        gara = self._create_random_no_gara(director_user)
        for i in range(4):
            InscriptionService.inscribe_user(players[i].id, gara.id)

        InscriptionService.uninscribe_user(players[0].id, gara.id)

        remaining = db_session.query(Inscription).filter_by(gara_id=gara.id).all()
        active = [r for r in remaining if not r.is_waitlist]
        parity = [
            r
            for r in remaining
            if r.is_waitlist and r.waitlist_reason == WaitlistReason.PARITY.value
        ]
        assert len(active) == 2
        assert len(parity) == 1


@pytest.mark.integration
class TestRandomPolicyNoRoundCreation:
    """Round creation: start_first_round respects parity waitlist filter."""

    @pytest.fixture
    def director_user(self, db_session) -> User:
        unique_id = uuid.uuid4().hex[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()
        return director

    @pytest.fixture
    def players_5(self, db_session) -> List[User]:
        batch_id = uuid.uuid4().hex[:8]
        players = []
        for i in range(5):
            p = User(
                username=f"player_{i}_{batch_id}",
                email=f"player_{i}_{batch_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            p.set_password("player123")
            players.append(p)
        db_session.add_all(players)
        db_session.commit()
        return players

    def _create_gara(self, director: User, **overrides) -> Gara:
        kwargs = dict(
            campionato_id=None,
            number=1,
            name="Random NO Round Test",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Random + NO round creation",
            rounds_count=3,
            min_participants=2,
            max_participants=10,
            entry_fee=0.0,
            discipline="8_ball",
            distance=5,
            is_race_to=True,
            director_id=director.id,
            matchmaking_strategy="random",
            first_round_policy="random",
            odd_number_policy="no",
            anti_rematch_enabled=True,
        )
        kwargs.update(overrides)
        gara = GaraService.create_gara(**kwargs)
        InscriptionService.open_inscriptions(
            gara.id,
            utc_now() - timedelta(hours=1),
            utc_now() + timedelta(hours=1),
        )
        return gara

    def test_start_round_with_parity_waitlist_excludes_waiting_player(
        self, director_user, players_5, db_session
    ):
        """Scenario #7: 5 iscritti (4 attivi + 1 parity) → round con 4 attivi."""
        gara = self._create_gara(director_user)
        for p in players_5:
            InscriptionService.inscribe_user(p.id, gara.id)

        parity_inscriptions = (
            db_session.query(Inscription)
            .filter_by(
                gara_id=gara.id,
                is_waitlist=True,
                waitlist_reason=WaitlistReason.PARITY.value,
            )
            .all()
        )
        assert len(parity_inscriptions) == 1
        parity_user_id = parity_inscriptions[0].user_id

        RoundService.start_first_round(gara.id)

        round1_matches = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        assert len(round1_matches) == 2

        participants_in_round = set()
        for m in round1_matches:
            if m.player1_id is not None:
                participants_in_round.add(m.player1_id)
            if m.player2_id is not None:
                participants_in_round.add(m.player2_id)

        assert parity_user_id not in participants_in_round
        assert len(participants_in_round) == 4

    def test_start_round_with_even_pool_creates_all_rounds(
        self, director_user, players_5, db_session
    ):
        """Scenario #8: baseline 4 iscritti pari → round creati normalmente."""
        gara = self._create_gara(director_user)
        for p in players_5[:4]:
            InscriptionService.inscribe_user(p.id, gara.id)

        waitlist_count = (
            db_session.query(Inscription)
            .filter_by(gara_id=gara.id, is_waitlist=True)
            .count()
        )
        assert waitlist_count == 0

        RoundService.start_first_round(gara.id)

        for round_num in range(1, 4):
            matches = Match.query.filter_by(
                gara_id=gara.id, round_number=round_num
            ).all()
            assert (
                len(matches) == 2
            ), f"Round {round_num}: expected 2 matches, got {len(matches)}"

    def test_capacity_waitlist_trumps_parity_when_max_reached(
        self, director_user, players_5, db_session
    ):
        """Scenario #9: max=4 + 5° iscritto → reason=CAPACITY (non PARITY).

        Mirror di test_parity_waitlist.py::test_parity_check_before_capacity_check
        ma con matchmaking_strategy="random". Quando il max è raggiunto, la
        ragione waitlist è CAPACITY anche se la parità spingerebbe in PARITY.
        """
        gara = self._create_gara(director_user, max_participants=4)
        for p in players_5[:4]:
            InscriptionService.inscribe_user(p.id, gara.id)

        fifth = InscriptionService.inscribe_user(players_5[4].id, gara.id)

        assert fifth.is_waitlist is True
        assert fifth.waitlist_reason == WaitlistReason.CAPACITY.value
