"""
Module: models/exam/models.py
Purpose: Dominio esame — un esame è una **sequenza ordinata di drill** (ADR-042).
Data Structures: Exam, ExamExaminer, ExamChallenge, ExamAttempt, ExamChallengeResult

Tre scelte reggono tutto il modulo, e conviene averle in testa leggendo il resto:

1. **L'esito è booleano.** Superato / non superato, e basta: niente griglia di
   valutazione, niente voto A–F, nessuna nota. Sono quindi spariti
   ``grading_criteria``, ``calculate_grade()`` e ``final_grade``. Il punteggio
   resta (serve a *mostrare* come è andata), ma non produce più un giudizio.
2. **Solo la sessione di persona certifica.** ``mode`` distingue il tentativo in
   autonomia — allenamento, non certificabile mai — da quello certificato,
   condotto davanti a un esaminatore.
3. **Il punteggio massimo è per-esame**, su ``ExamChallenge.max_score``, non su
   ``Challenge``: lo stesso drill può valere 10 in un esame e 15 in un altro.
   ``Challenge`` **non ha** ``max_score`` (né ``name``): leggerlo era il bug che
   rendeva questo dominio non funzionante.

Non c'è più il ``weight``: pesava i drill nel calcolo del voto, e senza voto non
ha scopo. Per dare più rilievo a un drill gli si assegna un ``max_score`` più
alto.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from ..base import db, BaseModel, utc_now
from ..status_enum import ExamAttemptMode, ExamAttemptStatus


class Exam(BaseModel):
    """Un esame: una sequenza ordinata di drill, somministrata da esaminatori."""

    __tablename__ = "exam"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Creatore dell'esame. È esaminatore implicito: non compare in
    # ``exam_examiner``, che elenca solo i co-esaminatori che ha aggiunto.
    examiner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    time_limit_minutes = db.Column(db.Integer, nullable=True)

    challenges = db.relationship(
        "ExamChallenge",
        back_populates="exam",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="ExamChallenge.order",
    )

    attempts = db.relationship(
        "ExamAttempt",
        back_populates="exam",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    examiners = db.relationship(
        "ExamExaminer",
        back_populates="exam",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    examiner = db.relationship("User", foreign_keys=[examiner_id])

    @property
    def examiner_ids(self) -> Set[int]:
        """Chi può somministrare l'esame: il creatore più i co-esaminatori."""
        return {self.examiner_id} | {e.user_id for e in self.examiners}

    def is_examined_by(self, user_id: Optional[int]) -> bool:
        """True se ``user_id`` è il creatore o un co-esaminatore dell'esame."""
        return user_id is not None and user_id in self.examiner_ids

    def get_statistics(self) -> Dict[str, Any]:
        """Statistiche dell'esame (US-E8): sostenuti, superati, candidati.

        Contano i soli tentativi **certificati e conclusi**: l'allenamento in
        autonomia è riportato a parte e gli abbandoni non sono bocciature.
        """
        # ``attempts`` è lazy="dynamic": una sola SELECT, poi tutto in memoria.
        attempts = self.attempts.filter(
            ExamAttempt.status == ExamAttemptStatus.COMPLETED.value
        ).all()

        certified = [a for a in attempts if a.mode == ExamAttemptMode.CERTIFIED.value]
        self_practice = len(attempts) - len(certified)
        passed = sum(1 for a in certified if a.passed)

        return {
            "certified_attempts": len(certified),
            "passed": passed,
            "failed": len(certified) - passed,
            "pass_rate": (
                round(passed / len(certified) * 100, 1) if certified else None
            ),
            "unique_candidates": len({a.user_id for a in certified}),
            "self_practice_attempts": self_practice,
        }

    def __repr__(self) -> str:  # pragma: no cover - banale
        return f"<Exam {self.name}>"


class ExamExaminer(BaseModel):
    """Co-esaminatore di un esame (US-E2).

    Il creatore aggiunge altri titolari del ruolo, così che i candidati non
    dipendano solo da lui per sostenere l'esame. Modello concettuale:
    ``DirectorAssignment``. Chi si può aggiungere lo decide il servizio: solo
    chi ha il grant ``examiner`` attivo — e se non esiste nessun altro
    titolare, la lista selezionabile è legittimamente vuota (UJ-1).
    """

    __tablename__ = "exam_examiner"

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(
        db.Integer, db.ForeignKey("exam.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    added_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    added_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    exam = db.relationship("Exam", back_populates="examiners")
    user = db.relationship("User", foreign_keys=[user_id])
    added_by = db.relationship("User", foreign_keys=[added_by_id])

    __table_args__ = (
        db.UniqueConstraint("exam_id", "user_id", name="uq_exam_examiner"),
    )

    def __repr__(self) -> str:  # pragma: no cover - banale
        return f"<ExamExaminer exam={self.exam_id} user={self.user_id}>"


class ExamChallenge(BaseModel):
    """Un drill dentro un esame, con la sua posizione e il suo massimo."""

    __tablename__ = "exam_challenge"

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(
        db.Integer, db.ForeignKey("exam.id", ondelete="CASCADE"), nullable=False
    )
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="CASCADE"), nullable=False
    )
    order = db.Column(db.Integer, nullable=False)

    # Punteggio massimo **per questo esame**. NULL = drill pass/fail, che vale
    # 1 punto se superato. Obbligatorio sui drill numerici, vietato sui
    # pass/fail: il servizio lo impone in scrittura.
    max_score = db.Column(db.Integer, nullable=True)

    exam = db.relationship("Exam", back_populates="challenges")
    challenge = db.relationship("Challenge")

    __table_args__ = (
        db.UniqueConstraint("exam_id", "challenge_id", name="uq_exam_challenge"),
        db.UniqueConstraint("exam_id", "order", name="uq_exam_order"),
    )

    @property
    def is_pass_fail(self) -> bool:
        """True se il drill si valuta superato/non superato."""
        return self.max_score is None

    @property
    def effective_max_score(self) -> int:
        """Punti che questo drill può portare: ``max_score``, o 1 se pass/fail."""
        return 1 if self.max_score is None else self.max_score

    def score_of(self, score: Optional[int], passed: Optional[bool]) -> int:
        """Punti effettivamente ottenuti da un risultato su questo drill.

        Somma semplice, nessun moltiplicatore: un drill numerico contribuisce
        con il punteggio ottenuto, un pass/fail con 1 se superato e 0 altrimenti.
        """
        if self.is_pass_fail:
            return 1 if passed else 0
        return score or 0

    def __repr__(self) -> str:  # pragma: no cover - banale
        # get_display_name(), mai challenge.name: Challenge non ha un nome.
        return (
            f"<ExamChallenge exam={self.exam_id} "
            f"{self.challenge.get_display_name()} (#{self.order})>"
        )


class ExamAttempt(BaseModel):
    """Un tentativo d'esame: allenamento in autonomia oppure sessione certificata."""

    __tablename__ = "exam_attempt"

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(
        db.Integer, db.ForeignKey("exam.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    mode = db.Column(
        db.String(20), nullable=False, default=ExamAttemptMode.SELF_PRACTICE.value
    )
    status = db.Column(
        db.String(30), nullable=False, default=ExamAttemptStatus.IN_PROGRESS.value
    )

    started_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Esito: valorizzato **solo** in modalità certificata e solo a sessione
    # conclusa. NULL su un tentativo in autonomia e su uno abbandonato — che
    # non è una bocciatura.
    passed = db.Column(db.Boolean, nullable=True)

    # Punteggio: serve a mostrare com'è andata, non a calcolare un voto.
    total_score = db.Column(db.Integer, nullable=True)
    max_possible_score = db.Column(db.Integer, nullable=True)

    # Contesto della certificazione (NULL in autonomia).
    examiner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    certified_at = db.Column(db.DateTime, nullable=True)
    billiard_hall_id = db.Column(
        db.Integer, db.ForeignKey("billiard_hall.id"), nullable=True
    )
    # Appuntamento che ha generato la sessione (NULL in autonomia).
    exam_request_id = db.Column(
        db.Integer, db.ForeignKey("exam_request.id"), nullable=True
    )

    exam = db.relationship("Exam", back_populates="attempts")
    user = db.relationship("User", foreign_keys=[user_id])
    examiner = db.relationship("User", foreign_keys=[examiner_id])
    billiard_hall = db.relationship("BilliardHall")
    exam_request = db.relationship("ExamRequest", back_populates="attempt")

    challenge_results = db.relationship(
        "ExamChallengeResult",
        back_populates="exam_attempt",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    # Un solo tentativo in autonomia aperto per (utente, esame): riprendere
    # significa riaprire quello, non affiancargliene un secondo. Parziale, così
    # i tentativi conclusi possono essere quanti si vuole.
    __table_args__ = (
        db.Index(
            "uq_exam_attempt_open_self_practice",
            "user_id",
            "exam_id",
            unique=True,
            sqlite_where=db.text("status = 'in_progress' AND mode = 'self_practice'"),
        ),
        # Una sola sessione per appuntamento. Attenzione: **non** è il presidio
        # della corsa «due esaminatori accettano insieme» — quella si gioca
        # molto prima, su ``exam_request_recipient``, e la vince l'indice
        # parziale dichiarato lì. Questo protegge la sua corsa: due aperture di
        # sessione sullo stesso appuntamento. Parziale sul NOT NULL perché i
        # tentativi in autonomia hanno tutti ``exam_request_id`` a NULL.
        db.Index(
            "uq_exam_attempt_request",
            "exam_request_id",
            unique=True,
            sqlite_where=db.text("exam_request_id IS NOT NULL"),
        ),
    )

    @property
    def is_certified(self) -> bool:
        """True se questo tentativo è una certificazione conclusa.

        È il predicato che il profilo usa per il badge «certificato da …»: né
        l'allenamento né una sessione interrotta lo soddisfano.
        """
        return (
            self.mode == ExamAttemptMode.CERTIFIED.value
            and self.status == ExamAttemptStatus.COMPLETED.value
            and self.passed is not None
        )

    def create_placeholder_results(self) -> List["ExamChallengeResult"]:
        """Crea un risultato vuoto per ogni drill dell'esame."""
        results = []
        for exam_challenge in self.exam.challenges.all():
            result = ExamChallengeResult(
                exam_attempt_id=self.id, exam_challenge_id=exam_challenge.id
            )
            db.session.add(result)
            results.append(result)
        return results

    def recompute_scores(self) -> None:
        """Ricalcola punteggio ottenuto e massimo come **somme semplici**."""
        total = 0
        max_total = 0
        for result in self.challenge_results.all():
            exam_challenge = result.exam_challenge
            total += exam_challenge.score_of(result.score, result.passed)
            max_total += exam_challenge.effective_max_score

        self.total_score = total
        self.max_possible_score = max_total

    def get_progress(self) -> Dict[str, Any]:
        """Avanzamento del tentativo, drill per drill.

        Un drill è svolto se ha un punteggio **oppure** un esito pass/fail: la
        versione precedente contava il solo ``score``, quindi un esame di soli
        drill pass/fail restava eternamente allo 0%.
        """
        total_challenges = self.exam.challenges.count()
        completed_challenges = self.challenge_results.filter(
            db.or_(
                ExamChallengeResult.score.isnot(None),
                ExamChallengeResult.passed.isnot(None),
            )
        ).count()

        return {
            "total_challenges": total_challenges,
            "completed_challenges": completed_challenges,
            "progress_percentage": (
                (completed_challenges / total_challenges * 100)
                if total_challenges > 0
                else 0
            ),
            "is_complete": (
                total_challenges > 0 and completed_challenges == total_challenges
            ),
        }

    def __repr__(self) -> str:  # pragma: no cover - banale
        return (
            f"<ExamAttempt user={self.user_id} exam={self.exam_id} "
            f"{self.mode}/{self.status}>"
        )


class ExamChallengeResult(BaseModel):
    """Il risultato di un drill dentro un tentativo d'esame."""

    __tablename__ = "exam_challenge_result"

    id = db.Column(db.Integer, primary_key=True)
    exam_attempt_id = db.Column(
        db.Integer, db.ForeignKey("exam_attempt.id", ondelete="CASCADE"), nullable=False
    )
    exam_challenge_id = db.Column(
        db.Integer,
        db.ForeignKey("exam_challenge.id", ondelete="CASCADE"),
        nullable=False,
    )

    score = db.Column(db.Integer, nullable=True)
    passed = db.Column(db.Boolean, nullable=True)
    attempted_at = db.Column(db.DateTime, nullable=True)

    exam_attempt = db.relationship("ExamAttempt", back_populates="challenge_results")
    exam_challenge = db.relationship("ExamChallenge")

    __table_args__ = (
        db.UniqueConstraint(
            "exam_attempt_id", "exam_challenge_id", name="uq_exam_challenge_result"
        ),
    )

    def record(
        self, score: Optional[int] = None, passed: Optional[bool] = None
    ) -> None:
        """Registra il risultato di questo drill. La validazione sta nel service."""
        self.score = score
        self.passed = passed
        self.attempted_at = utc_now()

    def __repr__(self) -> str:  # pragma: no cover - banale
        return (
            f"<ExamChallengeResult attempt={self.exam_attempt_id} "
            f"challenge={self.exam_challenge_id}: {self.score}/{self.passed}>"
        )
