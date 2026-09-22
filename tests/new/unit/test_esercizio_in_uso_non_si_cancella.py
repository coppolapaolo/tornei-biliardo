"""Un esercizio usato da qualcuno non si cancella davvero: si disattiva.

`ChallengeService.delete_challenge` sceglie fra cancellazione fisica e
disattivazione guardando **dove l'esercizio compare**. L'elenco è cresciuto una
volta per volta, e due posti mancavano:

* l'**esame**. Il danno non era la voce persa: le prove d'esame stanno in
  `exam_challenge_result`, non fra i `ChallengeAttempt` che quel controllo
  contava, quindi un esercizio già sostenuto da dei candidati risultava «mai
  utilizzato» — e `exam_challenge.challenge_id` è `ON DELETE CASCADE`, così la
  cancellazione si portava via la voce e con lei i risultati;
* la **scheda di allenamento** (ADR-067), che nasce oggi e sarebbe entrata
  nello stesso buco.

È la stessa forma del difetto dell'esercizio della X (#267), già raccontato nel
codice: ogni posto nuovo in cui un esercizio compare va aggiunto a quel conto.
"""

from __future__ import annotations

import uuid

from models.challenge.models import Challenge
from models.challenge.services import ChallengeService
from models.exam.models import Exam, ExamChallenge
from models.training_sheet import SheetItemSpec, SheetMeasure, TrainingSheetService
from models.user.models import User
from models.user.role_enum import UserRole


def _user(db_session, role=UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"del_{uid}", email=f"del_{uid}@test.local", role=role)
    user.set_password("p")
    db_session.add(user)
    db_session.flush()
    return user


def _challenge(db_session) -> Challenge:
    challenge = Challenge(
        title=f"Esercizio {uuid.uuid4().hex[:6]}",
        description="istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=True,  # «riusciti» vuole un esito netto (ADR-072)
    )
    db_session.add(challenge)
    db_session.flush()
    return challenge


def test_un_esercizio_mai_usato_si_cancella(db_session):
    """Il caso di controllo: senza usi, la cancellazione resta fisica."""
    challenge = _challenge(db_session)
    challenge_id = challenge.id

    ChallengeService.delete_challenge(challenge_id)
    assert db_session.get(Challenge, challenge_id) is None


def test_un_esercizio_dentro_un_esame_si_disattiva(db_session):
    """Cancellarlo porterebbe via la voce dell'esame, e i risultati con lei."""
    esaminatore = _user(db_session, UserRole.DIRECTOR.value)
    challenge = _challenge(db_session)
    exam = Exam(name="Certificazione", examiner_id=esaminatore.id)
    db_session.add(exam)
    db_session.flush()
    db_session.add(
        ExamChallenge(exam_id=exam.id, challenge_id=challenge.id, order=1, max_score=10)
    )
    db_session.flush()

    ChallengeService.delete_challenge(challenge.id)

    assert db_session.get(Challenge, challenge.id) is not None
    assert challenge.is_active is False
    assert (
        ExamChallenge.query.filter_by(exam_id=exam.id).count() == 1
    ), "la composizione dell'esame resta intera"


def test_un_esercizio_dentro_una_scheda_si_disattiva(db_session):
    giocatore = _user(db_session)
    challenge = _challenge(db_session)
    sheet = TrainingSheetService.create_sheet(giocatore, "Tecnica di base")
    TrainingSheetService.save_composition(
        sheet.id,
        giocatore,
        name="Tecnica di base",
        items=[
            SheetItemSpec(
                challenge_id=challenge.id, measure=SheetMeasure.MADE, amount=5
            )
        ],
    )

    ChallengeService.delete_challenge(challenge.id)

    assert db_session.get(Challenge, challenge.id) is not None
    assert challenge.is_active is False
    assert len(sheet.active_items) == 1, "la scheda di qualcuno resta intera"
