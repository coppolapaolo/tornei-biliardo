"""Comporre un esame da una pagina sola, con un salvataggio solo (fase 3a).

Fino al 19/09/2026 per aggiungere un esercizio a un esame si scriveva il suo
**ID numerico** in un campo, e tre cose che il servizio sapeva fare da sempre —
riordinare, cambiare quanto vale una voce, correggere il nome dell'esame —
avevano la route e nessun comando. La pagina «Componi l'esame» le raccoglie, e
salva **tutto insieme o niente**: chi sposta una voce, ne toglie un'altra e poi
sbaglia un punteggio non deve ritrovarsi con un esame scritto a metà.

Due confini che nascono qui, perché è la prima volta che la composizione si
cambia davvero dopo il primo giorno:

* con una **sessione certificata aperta** la composizione non si tocca: la
  griglia delle prove è nata all'apertura, e cambiarla sotto le mani
  dell'esaminatore vuol dire valutare un candidato su un esame diverso da
  quello che ha accettato;
* un **allenamento in autonomia** lasciato aperto non può invece bloccare
  l'esaminatore per sempre: la sua griglia si riallinea alla composizione
  nuova, senza perdere le prove già registrate.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.exam.models import ExamAttempt, ExamChallengeResult
from models.exam.services import CompositionItem, ExamService
from models.exceptions import ConflictError, PermissionDeniedError, ValidationError
from models.status_enum import ExamAttemptMode, ExamAttemptStatus
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

PASSWORD = "prova123"


def _make_user(role: str = UserRole.PLAYER.value) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        username=f"u_{suffix}",
        email=f"{suffix}@example.com",
        role=role,
        is_verified=True,
        onboarding_completed=True,
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    return user


def _make_challenge(
    title: str, pass_fail: bool = False, max_score: int | None = None
) -> Challenge:
    challenge = Challenge(
        title=title,
        description=f"Istruzioni di {title}",
        image_path="/static/uploads/challenges/x.png",
        pass_fail_only=pass_fail,
        max_score=max_score,
    )
    db.session.add(challenge)
    db.session.flush()
    return challenge


@pytest.fixture
def admin(db_session):
    user = _make_user(UserRole.ADMIN.value)
    db_session.commit()
    return user


@pytest.fixture
def examiner(db_session, admin):
    user = _make_user()
    RoleGrantService.grant(user.id, GrantableRole.EXAMINER, admin)
    db_session.commit()
    return user


@pytest.fixture
def composed(db_session, examiner):
    """Un esame di tre voci: a punteggio, riuscito o no, a punteggio."""
    exam = ExamService.create_exam(examiner, "Fondamentali — livello 1")
    spot = _make_challenge("Spot Shot Rally", max_score=10)
    serie = _make_challenge("Serie da otto", pass_fail=True)
    ferma = _make_challenge("Ferma nel cerchio", max_score=20)
    ExamService.add_challenge_to_exam(
        exam.id, spot.id, examiner, max_score=10, max_attempts=3
    )
    ExamService.add_challenge_to_exam(exam.id, serie.id, examiner)
    ExamService.add_challenge_to_exam(
        exam.id, ferma.id, examiner, max_score=12, max_attempts=2
    )
    db_session.commit()
    return exam, spot, serie, ferma


def _sequence(exam):
    return [
        (ec.challenge_id, ec.max_score, ec.max_attempts) for ec in exam.challenges.all()
    ]


class TestSaveComposition:
    def test_un_salvataggio_solo_riordina_cambia_toglie_e_aggiunge(
        self, db_session, examiner, composed
    ):
        exam, spot, serie, ferma = composed
        nuovo = _make_challenge("Linea tangente", max_score=15)
        db_session.commit()

        ExamService.save_composition(
            exam.id,
            examiner,
            name="Fondamentali — livello 2",
            description="Rivisto",
            time_limit_minutes=45,
            items=[
                CompositionItem(ferma.id, 14, 1),
                CompositionItem(nuovo.id, 15, 2),
                CompositionItem(spot.id, 10, 3),
            ],
        )

        exam = ExamService.get_exam(exam.id)
        assert exam.name == "Fondamentali — livello 2"
        assert exam.description == "Rivisto"
        assert exam.time_limit_minutes == 45
        assert _sequence(exam) == [
            (ferma.id, 14, 1),
            (nuovo.id, 15, 2),
            (spot.id, 10, 3),
        ]
        assert [ec.order for ec in exam.challenges.all()] == [1, 2, 3]

    def test_il_limite_di_tempo_si_puo_togliere(self, db_session, examiner, composed):
        """``update_exam`` legge ``None`` come «non toccare»: da lì non si
        toglie mai. Nel modulo il campo vuoto vuol dire «nessun limite»."""
        exam, spot, serie, ferma = composed
        ExamService.update_exam(exam.id, examiner, time_limit_minutes=30)

        ExamService.save_composition(
            exam.id,
            examiner,
            name=exam.name,
            description=None,
            time_limit_minutes=None,
            items=[
                CompositionItem(spot.id, 10, 3),
                CompositionItem(serie.id, None, 1),
                CompositionItem(ferma.id, 12, 2),
            ],
        )

        assert ExamService.get_exam(exam.id).time_limit_minutes is None

    def test_se_una_voce_e_sbagliata_non_si_salva_niente(
        self, db_session, examiner, composed
    ):
        exam, spot, serie, ferma = composed
        before = _sequence(exam)

        with pytest.raises(ValidationError):
            ExamService.save_composition(
                exam.id,
                examiner,
                name="Nome nuovo",
                description=None,
                time_limit_minutes=None,
                items=[
                    CompositionItem(ferma.id, 14, 1),
                    # Un esercizio a punteggio senza «vale»: rifiutato.
                    CompositionItem(spot.id, None, 3),
                ],
            )

        db.session.rollback()
        exam = ExamService.get_exam(exam.id)
        assert exam.name == "Fondamentali — livello 1"
        assert _sequence(exam) == before

    def test_lo_stesso_esercizio_due_volte_e_rifiutato(
        self, db_session, examiner, composed
    ):
        exam, spot, serie, ferma = composed
        with pytest.raises(ValidationError):
            ExamService.save_composition(
                exam.id,
                examiner,
                name=exam.name,
                description=None,
                time_limit_minutes=None,
                items=[
                    CompositionItem(spot.id, 10, 1),
                    CompositionItem(spot.id, 10, 1),
                ],
            )

    def test_chi_non_somministra_l_esame_non_lo_compone(
        self, db_session, admin, composed
    ):
        exam, spot, serie, ferma = composed
        altro = _make_user()
        RoleGrantService.grant(altro.id, GrantableRole.EXAMINER, admin)
        db_session.commit()

        with pytest.raises(PermissionDeniedError):
            ExamService.save_composition(
                exam.id,
                altro,
                name="Mio",
                description=None,
                time_limit_minutes=None,
                items=[],
            )


class TestCompositionAndOpenAttempts:
    def _open_certified(self, exam, examiner, candidate) -> ExamAttempt:
        attempt = ExamAttempt(
            exam_id=exam.id,
            user_id=candidate.id,
            examiner_id=examiner.id,
            mode=ExamAttemptMode.CERTIFIED.value,
            status=ExamAttemptStatus.AWAITING_PLAYER_START.value,
        )
        db.session.add(attempt)
        db.session.flush()
        attempt.create_placeholder_results()
        db.session.commit()
        return attempt

    def test_con_una_sessione_certificata_aperta_non_si_tocca(
        self, db_session, examiner, composed
    ):
        exam, spot, serie, ferma = composed
        candidate = _make_user()
        self._open_certified(exam, examiner, candidate)

        with pytest.raises(ConflictError):
            ExamService.save_composition(
                exam.id,
                examiner,
                name=exam.name,
                description=None,
                time_limit_minutes=None,
                items=[CompositionItem(spot.id, 10, 3)],
            )

    def test_un_allenamento_aperto_si_riallinea_e_tiene_le_prove_fatte(
        self, db_session, examiner, composed
    ):
        exam, spot, serie, ferma = composed
        player = _make_user()
        db_session.commit()
        attempt = ExamService.start_self_practice(player, exam.id)
        spot_ec = next(ec for ec in exam.challenges.all() if ec.challenge_id == spot.id)
        ExamService.record_challenge_result(attempt.id, spot_ec.id, player, score=8)

        nuovo = _make_challenge("Linea tangente", max_score=15)
        db_session.commit()

        ExamService.save_composition(
            exam.id,
            examiner,
            name=exam.name,
            description=None,
            time_limit_minutes=None,
            items=[
                # Spot: da tre prove a due. «Serie da otto» esce, entra il nuovo.
                CompositionItem(spot.id, 10, 2),
                CompositionItem(ferma.id, 12, 2),
                CompositionItem(nuovo.id, 15, 1),
            ],
        )

        attempt = db.session.get(ExamAttempt, attempt.id)
        grid = sorted(
            (r.exam_challenge.challenge_id, r.attempt_number, r.score)
            for r in ExamChallengeResult.query.filter_by(
                exam_attempt_id=attempt.id
            ).all()
        )
        assert grid == sorted(
            [
                (spot.id, 1, 8),
                (spot.id, 2, None),
                (ferma.id, 1, None),
                (ferma.id, 2, None),
                (nuovo.id, 1, None),
            ]
        )
        assert attempt.total_score == 8
        assert attempt.max_possible_score == 10 + 12 + 15
        progress = attempt.get_progress()
        assert progress["total_attempts"] == 5
        assert progress["completed_attempts"] == 1


def _client_for(app, username: str):
    db.session.commit()
    client = app.test_client()
    client.post(
        "/auth/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=True,
    )
    return client


class TestComposePage:
    def test_la_pagina_propone_gli_esercizi_per_nome(
        self, app, db_session, examiner, composed
    ):
        exam, spot, serie, ferma = composed
        _make_challenge("Linea tangente", max_score=15)
        db_session.commit()

        html = (
            _client_for(app, examiner.username)
            .get(f"/exam/{exam.id}/compose")
            .get_data(as_text=True)
        )

        assert "Linea tangente" in html
        assert "data-seq-editor" in html
        # Le tre voci, nell'ordine dell'esame.
        assert html.index("Spot Shot Rally") < html.index("Serie da otto")
        assert html.index("Serie da otto") < html.index("Ferma nel cerchio")

    def test_il_dettaglio_non_chiede_piu_l_id_a_mano(
        self, app, db_session, examiner, composed
    ):
        exam, *_ = composed
        html = (
            _client_for(app, examiner.username)
            .get(f"/exam/{exam.id}")
            .get_data(as_text=True)
        )

        assert 'name="challenge_id"' not in html
        assert f"/exam/{exam.id}/compose" in html

    def test_un_altro_esaminatore_non_apre_la_pagina(
        self, app, db_session, admin, composed
    ):
        exam, *_ = composed
        altro = _make_user()
        RoleGrantService.grant(altro.id, GrantableRole.EXAMINER, admin)
        db_session.commit()

        response = _client_for(app, altro.username).get(f"/exam/{exam.id}/compose")
        assert response.status_code == 403

    def test_il_modulo_salva_la_sequenza_nell_ordine_in_cui_arriva(
        self, app, db_session, examiner, composed
    ):
        exam, spot, serie, ferma = composed

        response = _client_for(app, examiner.username).post(
            f"/exam/{exam.id}/compose",
            data={
                "name": "Rinominato",
                "description": "",
                "time_limit_minutes": "",
                "challenge_id": [str(serie.id), str(spot.id)],
                # Una riga per voce, anche dove non c'è un punteggio: le liste
                # parallele si leggono per posizione.
                "max_score": ["", "11"],
                "max_attempts": ["1", "4"],
            },
        )

        assert response.status_code == 302
        db.session.expire_all()
        exam = ExamService.get_exam(exam.id)
        assert exam.name == "Rinominato"
        assert _sequence(exam) == [(serie.id, None, 1), (spot.id, 11, 4)]

    def test_un_modulo_con_le_liste_sfasate_e_rifiutato(
        self, app, db_session, examiner, composed
    ):
        exam, spot, serie, ferma = composed
        before = _sequence(exam)

        response = _client_for(app, examiner.username).post(
            f"/exam/{exam.id}/compose",
            data={
                "name": exam.name,
                "challenge_id": [str(serie.id), str(spot.id)],
                "max_score": ["11"],
                "max_attempts": ["1", "4"],
            },
        )

        assert response.status_code == 400
        db.session.expire_all()
        assert _sequence(ExamService.get_exam(exam.id)) == before

    def test_con_una_sessione_aperta_la_pagina_lo_dice_prima(
        self, app, db_session, examiner, composed
    ):
        """Il servizio rifiuta comunque; ma saperlo al salvataggio vuol dire
        aver riordinato per niente."""
        exam, *_ = composed
        candidate = _make_user()
        attempt = ExamAttempt(
            exam_id=exam.id,
            user_id=candidate.id,
            examiner_id=examiner.id,
            mode=ExamAttemptMode.CERTIFIED.value,
            status=ExamAttemptStatus.IN_PROGRESS.value,
        )
        db.session.add(attempt)
        db_session.commit()

        html = (
            _client_for(app, examiner.username)
            .get(f"/exam/{exam.id}/compose")
            .get_data(as_text=True)
        )

        assert "esame aperta" in html
        save_button = html.split('type="submit" class="btn btn-success"')[1][:40]
        assert "disabled" in save_button
