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
   ``Challenge`` **non ha** ``name``, e quando questo dominio è nato non aveva
   nemmeno ``max_score``: leggerli era il bug che lo rendeva non funzionante.
   Oggi ``Challenge.max_score`` c'è, ma risponde a un'altra domanda (quanto vale
   al massimo la prova, non quanto pesa qui) e fa solo da valore proposto.

Non c'è più il ``weight``: pesava i drill nel calcolo del voto, e senza voto non
ha scopo. Per dare più rilievo a un drill gli si assegna un ``max_score`` più
alto.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

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

    # Quante prove di questo drill prevede l'esame. Il numero lo decide chi
    # compone l'esame, non chi lo sostiene: è parte della prova, come il
    # punteggio massimo. Default 1, che è l'esame di prima parola per parola.
    max_attempts = db.Column(db.Integer, nullable=False, default=1, server_default="1")

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
        """Crea un risultato vuoto per ogni **prova** prevista dall'esame.

        Un drill con tre tentativi nasce con tre righe numerate: la sessione è
        una griglia a caselle fisse, e l'esaminatore le riempie in ordine o le
        corregge. Creare le righe alla bisogna avrebbe reso il conteggio di
        «quanto manca» una sottrazione fra due numeri che nessuno tiene.
        """
        results = []
        for exam_challenge in self.exam.challenges.all():
            for number in range(1, exam_challenge.max_attempts + 1):
                result = ExamChallengeResult(
                    exam_attempt_id=self.id,
                    exam_challenge_id=exam_challenge.id,
                    attempt_number=number,
                )
                db.session.add(result)
                results.append(result)
        return results

    def results_by_challenge(
        self,
    ) -> List[Tuple["ExamChallenge", List["ExamChallengeResult"]]]:
        """I risultati raggruppati per drill: l'ordine dell'esame, poi le prove.

        La sessione si somministra per drill — «ora fai questo, tre volte» — non
        per riga di risultato. Senza il raggruppamento un drill a tre prove
        comparirebbe come tre schede distinte con lo stesso titolo.
        """
        by_challenge: Dict[int, List["ExamChallengeResult"]] = {}
        for result in self.challenge_results.order_by(
            ExamChallengeResult.attempt_number
        ).all():
            by_challenge.setdefault(result.exam_challenge_id, []).append(result)

        return [
            (exam_challenge, by_challenge.get(exam_challenge.id, []))
            for exam_challenge in self.exam.challenges.all()
        ]

    def recompute_scores(self) -> None:
        """Ricalcola punteggio ottenuto e massimo.

        Somma semplice fra drill — niente ``weight``, niente moltiplicatori —
        e, **dentro** ciascun drill, la prova migliore: chi ripete un drill lo
        ripete per migliorare, quindi vale il picco. Sommare le prove farebbe
        pesare un drill a tre tentativi il triplo di uno a tentativo unico,
        cambiando la taratura dell'esame senza che nessuno l'abbia deciso; per
        questo anche il massimo conta il drill **una volta sola**.

        Una prova non ancora registrata non è uno zero: contribuisce 0 al
        massimo fra le prove, e lo zero perde contro qualunque punteggio già
        preso.
        """
        best_by_challenge: Dict[int, int] = {}
        max_by_challenge: Dict[int, int] = {}

        for result in self.challenge_results.all():
            exam_challenge = result.exam_challenge
            scored = exam_challenge.score_of(result.score, result.passed)
            key = exam_challenge.id
            best_by_challenge[key] = max(best_by_challenge.get(key, 0), scored)
            max_by_challenge[key] = exam_challenge.effective_max_score

        self.total_score = sum(best_by_challenge.values())
        self.max_possible_score = sum(max_by_challenge.values())

    def get_progress(self) -> Dict[str, Any]:
        """Avanzamento del tentativo, prova per prova.

        Una prova è svolta se ha un punteggio **oppure** un esito pass/fail: la
        versione precedente contava il solo ``score``, quindi un esame di soli
        drill pass/fail restava eternamente allo 0%.

        Il conto vero è sulle **prove**, non sui drill: un drill da tre
        tentativi non è svolto dopo il primo, e la percentuale calcolata sui
        drill farebbe saltare la barra a un terzo per volta. I due numeri
        restano entrambi esposti — ``completed_challenges`` per «quanti drill
        ho chiuso», ``completed_attempts`` per «quanto manca».
        """
        exam_challenges = self.exam.challenges.all()
        total_challenges = len(exam_challenges)
        total_attempts = sum(ec.max_attempts for ec in exam_challenges)

        # Solo le prove che l'esame prevede **oggi**: se chi lo compone ha
        # ridotto le prove di un esercizio, una terza prova già registrata in un
        # allenamento aperto resta (non si butta un dato), ma non deve far
        # segnare «6 su 5».
        prescribed = {ec.id: ec.max_attempts for ec in exam_challenges}
        recorded = [
            result
            for result in self.challenge_results.filter(
                db.or_(
                    ExamChallengeResult.score.isnot(None),
                    ExamChallengeResult.passed.isnot(None),
                )
            ).all()
            if result.attempt_number <= prescribed.get(result.exam_challenge_id, 0)
        ]
        completed_attempts = len(recorded)

        done_per_challenge: Dict[int, int] = {}
        for result in recorded:
            done_per_challenge[result.exam_challenge_id] = (
                done_per_challenge.get(result.exam_challenge_id, 0) + 1
            )
        completed_challenges = sum(
            1
            for ec in exam_challenges
            if done_per_challenge.get(ec.id, 0) >= ec.max_attempts
        )

        return {
            "total_challenges": total_challenges,
            "completed_challenges": completed_challenges,
            "total_attempts": total_attempts,
            "completed_attempts": completed_attempts,
            "progress_percentage": (
                (completed_attempts / total_attempts * 100) if total_attempts > 0 else 0
            ),
            "is_complete": (
                total_attempts > 0 and completed_attempts == total_attempts
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

    # Quale delle prove previste dal drill è questa: 1..max_attempts. Non è un
    # contatore globale ma la **casella** nella griglia della sessione, per
    # poterla correggere senza ambiguità su quale prova si sta rifacendo.
    attempt_number = db.Column(
        db.Integer, nullable=False, default=1, server_default="1"
    )

    score = db.Column(db.Integer, nullable=True)
    passed = db.Column(db.Boolean, nullable=True)
    attempted_at = db.Column(db.DateTime, nullable=True)

    exam_attempt = db.relationship("ExamAttempt", back_populates="challenge_results")
    exam_challenge = db.relationship("ExamChallenge")

    __table_args__ = (
        db.UniqueConstraint(
            "exam_attempt_id",
            "exam_challenge_id",
            "attempt_number",
            name="uq_exam_challenge_result",
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
