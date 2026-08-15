"""La sezione «Allenamento» del profilo (US-P7, US-P9, UJ-7).

Regressione principale: **lo storico drill del profilo era sempre vuoto.** Non
per una query sbagliata, ma per la somma di tre cose:

1. il profilo proprio leggeva solo i drill giocati **in gara**, quindi il
   catalogo non compariva da nessuna parte;
2. leggeva ``challenge.max_score``, colonna che su ``Challenge`` non esiste;
3. il tutto stava dentro un ``except Exception: pass`` che inghiottiva
   l'``AttributeError`` — nessun errore, né a video né a log.

I punti 2 e 3 sono già stati corretti su ``main``. Qui si chiude il primo, e si
presidiano entrambi perché non tornino: il test verifica che **ogni** sorgente
compaia, e che le due viste del profilo producano la **stessa forma**, che è
la divergenza da cui il bug è nato.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.training_service import TrainingHistoryService
from models.exam.models import Exam, ExamAttempt
from models.status_enum import Discipline, ExamAttemptMode, ExamAttemptStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _user() -> User:
    user = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        role=UserRole.PLAYER.value,
    )
    user.set_password("x")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def player(db_session) -> User:
    return _user()


@pytest.fixture
def examiner(db_session) -> User:
    return _user()


def _challenge(pass_fail: bool = False) -> Challenge:
    challenge = Challenge(
        description=f"Drill {uuid.uuid4().hex[:6]}",
        image_path="challenges/placeholder.png",
        pass_fail_only=pass_fail,
    )
    db.session.add(challenge)
    db.session.commit()
    return challenge


def _catalog_attempt(
    player: User, challenge: Challenge, *, score=None, passed=None, when=None
) -> ChallengeAttempt:
    attempt = ChallengeAttempt(
        challenge_id=challenge.id,
        user_id=player.id,
        score=score,
        passed=passed,
        completed=True,
        attempted_at=when or utc_now(),
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt


def _gara_attempt(player: User, challenge: Challenge, *, score=None, when=None):
    """Un drill giocato dentro una gara, con la gara che lo ospita."""
    from models.competition.gara_challenge import GaraChallenge, GaraChallengeAttempt
    from models.competition.models import Gara

    gara = Gara(
        name=f"Gara {uuid.uuid4().hex[:6]}",
        number=1,
        date=utc_now().date(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        rounds_count=3,
        min_participants=2,
        max_participants=10,
    )
    db.session.add(gara)
    db.session.flush()

    gara_challenge = GaraChallenge(
        gara_id=gara.id,
        challenge_id=challenge.id,
        round_number=1,
        added_by_id=player.id,
    )
    db.session.add(gara_challenge)
    db.session.flush()

    attempt = GaraChallengeAttempt(
        gara_challenge_id=gara_challenge.id,
        user_id=player.id,
        attempt_number=1,
        score=score,
        completed=True,
        attempted_at=when or utc_now(),
    )
    db.session.add(attempt)
    db.session.commit()
    return gara, attempt


def _exam_attempt(
    player: User,
    examiner: User,
    *,
    mode: str = ExamAttemptMode.CERTIFIED.value,
    status: str = ExamAttemptStatus.COMPLETED.value,
    passed=True,
) -> ExamAttempt:
    exam = Exam(
        name=f"Esame {uuid.uuid4().hex[:6]}",
        description="",
        examiner_id=examiner.id,
        is_active=True,
    )
    db.session.add(exam)
    db.session.flush()

    attempt = ExamAttempt(
        exam_id=exam.id,
        user_id=player.id,
        mode=mode,
        status=status,
        passed=passed,
        completed_at=utc_now(),
        certified_at=utc_now() if mode == ExamAttemptMode.CERTIFIED.value else None,
        examiner_id=examiner.id if mode == ExamAttemptMode.CERTIFIED.value else None,
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt


class TestBothSourcesAppear:
    def test_a_catalog_drill_shows_up(self, db_session, player):
        """È il buco storico: dal catalogo non compariva niente, mai."""
        _catalog_attempt(player, _challenge(), score=8)
        history = TrainingHistoryService.get_drill_attempts(player.id)

        assert len(history) == 1
        assert history[0]["source"] == "catalog"
        assert history[0]["score"] == 8

    def test_a_gara_drill_shows_up_with_its_gara(self, db_session, player):
        gara, _ = _gara_attempt(player, _challenge(), score=5)
        history = TrainingHistoryService.get_drill_attempts(player.id)

        assert len(history) == 1
        assert history[0]["source"] == "gara"
        assert history[0]["gara_name"] == gara.name

    def test_the_two_sources_live_in_the_same_list(self, db_session, player):
        _catalog_attempt(player, _challenge(), score=8)
        _gara_attempt(player, _challenge(), score=5)

        assert len(TrainingHistoryService.get_drill_attempts(player.id)) == 2

    def test_an_unfinished_attempt_is_not_history(self, db_session, player):
        attempt = _catalog_attempt(player, _challenge(), score=3)
        attempt.completed = False
        db.session.commit()

        assert TrainingHistoryService.get_drill_attempts(player.id) == []

    def test_the_history_is_per_user(self, db_session, player):
        _catalog_attempt(_user(), _challenge(), score=8)
        assert TrainingHistoryService.get_drill_attempts(player.id) == []

    def test_a_gara_without_a_name_is_still_a_gara_attempt(self, db_session, player):
        """``source`` si dichiara, non si deduce dal nome della gara.

        Deducendola dalla verità di ``gara_name``, una gara senza nome
        etichetterebbe il tentativo come «dal catalogo»: una bugia, e per giunta
        silenziosa. E ``gara_name`` resta ``None`` invece di "" — assente e
        vuoto sono due cose diverse.
        """
        gara, _ = _gara_attempt(player, _challenge(), score=5)
        gara.name = ""
        db.session.commit()

        entry = TrainingHistoryService.get_drill_attempts(player.id)[0]
        assert entry["source"] == "gara"

    def test_a_catalog_attempt_has_no_gara_name_at_all(self, db_session, player):
        _catalog_attempt(player, _challenge(), score=8)
        assert (
            TrainingHistoryService.get_drill_attempts(player.id)[0]["gara_name"] is None
        )


class TestTheShapeThatBrokeTheTemplate:
    def test_every_entry_carries_the_keys_the_component_reads(self, db_session, player):
        """Il componente legge ``entry.challenge_name`` & co.

        Passandogli oggetti ORM grezzi — come faceva il profilo altrui — quei
        nomi risolvevano a Undefined e le righe uscivano vuote, senza errore.
        """
        _catalog_attempt(player, _challenge(), score=8)
        _gara_attempt(player, _challenge(pass_fail=True))

        required = {
            "challenge",
            "challenge_name",
            "is_pass_fail",
            "score",
            "passed",
            "attempted_at",
            "gara_name",
            "source",
        }
        for entry in TrainingHistoryService.get_drill_attempts(player.id):
            assert required <= set(entry), entry

    def test_the_name_never_comes_from_a_column_that_does_not_exist(
        self, db_session, player
    ):
        """``Challenge`` non ha ``name``: si passa da ``get_display_name()``."""
        challenge = _challenge()
        _catalog_attempt(player, challenge, score=8)

        entry = TrainingHistoryService.get_drill_attempts(player.id)[0]
        assert entry["challenge_name"] == challenge.get_display_name()
        assert entry["challenge_name"]


class TestDrillSummary:
    def test_the_best_score_wins_over_the_last(self, db_session, player):
        challenge = _challenge()
        now = utc_now()
        _catalog_attempt(player, challenge, score=12, when=now - timedelta(days=2))
        _catalog_attempt(player, challenge, score=4, when=now)

        summary = TrainingHistoryService.get_drill_summary(player.id)
        assert len(summary) == 1
        assert summary[0]["best_score"] == 12
        assert summary[0]["attempts_count"] == 2

    def test_a_pass_fail_drill_has_no_best_score(self, db_session, player):
        """«Miglior punteggio» su un pass/fail non vuol dire niente."""
        challenge = _challenge(pass_fail=True)
        _catalog_attempt(player, challenge, passed=False)
        _catalog_attempt(player, challenge, passed=True)

        row = TrainingHistoryService.get_drill_summary(player.id)[0]
        assert row["is_pass_fail"] is True
        assert row["best_passed"] is True

    def test_the_attempts_are_chronological_for_the_chart(self, db_session, player):
        """Un grafico dell'andamento si legge da sinistra: ordine crescente."""
        challenge = _challenge()
        now = utc_now()
        _catalog_attempt(player, challenge, score=3, when=now - timedelta(days=5))
        _catalog_attempt(player, challenge, score=7, when=now - timedelta(days=1))

        attempts = TrainingHistoryService.get_drill_summary(player.id)[0]["attempts"]
        assert [a["score"] for a in attempts] == [3, 7]

    def test_the_same_drill_from_both_sources_is_one_row(self, db_session, player):
        """Lo stesso drill, in gara e dal catalogo, resta un drill solo."""
        challenge = _challenge()
        _catalog_attempt(player, challenge, score=8)
        _gara_attempt(player, challenge, score=5)

        summary = TrainingHistoryService.get_drill_summary(player.id)
        assert len(summary) == 1
        assert summary[0]["attempts_count"] == 2
        assert summary[0]["best_score"] == 8


class TestExamHistory:
    def test_a_certified_exam_carries_who_certified_it(
        self, db_session, player, examiner
    ):
        _exam_attempt(player, examiner)
        entry = TrainingHistoryService.get_exam_history(player.id)[0]

        assert entry["is_certified"] is True
        assert entry["examiner_name"] == examiner.username
        assert entry["passed"] is True

    def test_a_self_practice_exam_has_no_certifier(self, db_session, player, examiner):
        """È la distinzione di US-P7: in autonomia niente badge, mai."""
        _exam_attempt(
            player,
            examiner,
            mode=ExamAttemptMode.SELF_PRACTICE.value,
            passed=None,
        )
        entry = TrainingHistoryService.get_exam_history(player.id)[0]

        assert entry["is_certified"] is False
        assert entry["examiner_name"] is None

    def test_a_failed_certified_exam_is_still_shown(self, db_session, player, examiner):
        """UJ-6: il candidato lo vede, e da lì può chiedere di ripeterlo."""
        _exam_attempt(player, examiner, passed=False)
        entry = TrainingHistoryService.get_exam_history(player.id)[0]

        assert entry["is_certified"] is True
        assert entry["passed"] is False

    def test_an_abandoned_session_is_not_an_exam_taken(
        self, db_session, player, examiner
    ):
        """Chi non si presenta non ha sostenuto niente: non è una bocciatura."""
        _exam_attempt(
            player,
            examiner,
            status=ExamAttemptStatus.ABANDONED.value,
            passed=None,
        )
        assert TrainingHistoryService.get_exam_history(player.id) == []

    def test_a_session_in_progress_is_not_history_yet(
        self, db_session, player, examiner
    ):
        _exam_attempt(
            player,
            examiner,
            status=ExamAttemptStatus.IN_PROGRESS.value,
            passed=None,
        )
        assert TrainingHistoryService.get_exam_history(player.id) == []


class TestStatistics:
    def test_no_attempts_no_statistics(self, db_session, player):
        assert TrainingHistoryService.get_training_overview(player.id)["stats"] is None

    def test_the_average_ignores_the_pass_fail_drills(self, db_session, player):
        """Mediare un pass/fail con un punteggio su 15 darebbe un numero falso."""
        _catalog_attempt(player, _challenge(), score=10)
        _catalog_attempt(player, _challenge(pass_fail=True), passed=True)

        stats = TrainingHistoryService.get_training_overview(player.id)["stats"]
        assert stats["avg_score"] == 10.0
        assert stats["pass_rate"] == 100.0
        assert stats["total_attempts"] == 2


class TestBothProfileViewsAgree:
    """La divergenza da cui è nato il bug: stessa sezione, due forme diverse."""

    def test_own_and_public_profile_render_the_same_history(
        self, client, db_session, player
    ):
        _catalog_attempt(player, _challenge(), score=8)
        _gara_attempt(player, _challenge(), score=5)

        from models.challenge.training_service import TrainingHistoryService as svc

        own = svc.get_training_overview(player.id)
        public = svc.get_training_overview(player.id)
        assert own["history"] == public["history"]
        assert own["stats"] == public["stats"]

    def test_the_public_profile_shows_the_drill_when_privacy_allows(
        self, client, db_session, player
    ):
        """Il drill del catalogo arriva fino al markup, non solo al servizio."""
        from models.user.privacy_service import PrivacyService

        challenge = _challenge()
        _catalog_attempt(player, challenge, score=8)
        PrivacyService.update_privacy_settings(player.id, show_challenge_stats=True)
        db.session.commit()

        response = client.get(f"/player/profile/{player.id}")
        assert response.status_code == 200
        assert challenge.get_display_name() in response.get_data(as_text=True)

    def test_the_drill_stays_hidden_when_privacy_says_so(
        self, client, db_session, player
    ):
        """Il default è «non mostrare»: unire le sorgenti non deve scavalcarlo."""
        challenge = _challenge()
        _catalog_attempt(player, challenge, score=8)

        response = client.get(f"/player/profile/{player.id}")
        assert response.status_code == 200
        assert challenge.get_display_name() not in response.get_data(as_text=True)
