"""Lo storico d'allenamento di un giocatore: drill ed esami (US-P7, US-P9).

**Perché un servizio e non due blocchi nelle route.** Prima di questo modulo le
due viste del profilo leggevano sorgenti diverse e producevano forme diverse
per lo *stesso* template:

- ``player.profile`` (profilo proprio) leggeva solo ``GaraChallengeAttempt``, i
  drill giocati **in gara**, e costruiva dizionari;
- ``player.view_profile`` (profilo altrui) leggeva solo ``ChallengeAttempt``, i
  drill del **catalogo**, e passava gli oggetti ORM grezzi.

Risultato: dal catalogo non compariva niente da nessuna parte, e sul profilo
altrui la lista dei tentativi renderizzava righe vuote, perché il componente
cerca ``entry.challenge_name`` su oggetti che non ce l'hanno. Nessuno dei due
sbagliava da solo: sbagliavano insieme, ed è esattamente il tipo di divergenza
che una fonte unica impedisce.

Le due sorgenti restano due tabelle — non è questo il posto per unificarle — ma
escono di qui con la stessa forma, e la gara di provenienza resta visibile
perché è informazione, non rumore.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import joinedload


def _entry(
    *,
    challenge,
    score: Optional[int],
    passed: Optional[bool],
    attempted_at,
    source: str,
    gara_name: Optional[str] = None,
    attempt_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Forma comune alle due sorgenti.

    ``challenge_name`` passa da ``get_display_name()``: ``Challenge`` **non ha**
    un campo ``name``, e leggerlo è il bug storico che svuotava questa sezione
    in silenzio. (``max_score`` oggi c'è: allora mancava anche quello.)

    ``source`` è **dichiarata dal chiamante**, non dedotta dalla presenza del
    nome della gara: un tentativo giocato in una gara senza nome verrebbe
    altrimenti etichettato come «dal catalogo», che è falso. Per lo stesso
    motivo ``gara_name`` resta ``None`` quando manca invece di diventare "":
    assente e vuoto sono due cose diverse.
    """
    return {
        "challenge": challenge,
        "challenge_id": challenge.id,
        "challenge_name": challenge.get_display_name(),
        # Serve allo storico per cancellare la prova sbagliata. `None` sulle
        # prove di gara: quelle non si cancellano dal profilo, hanno
        # conseguenze in classifica e le tocca chi dirige.
        "attempt_id": attempt_id,
        "max_score": challenge.max_score,
        "is_pass_fail": bool(challenge.pass_fail_only),
        "score": score,
        "passed": passed,
        "attempted_at": attempted_at,
        "gara_name": gara_name,
        "source": source,
    }


class TrainingHistoryService:
    """Fonte unica dello storico d'allenamento mostrato nel profilo."""

    # ────────────────────────────────────────────────────────────────────
    # Drill
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def get_drill_attempts(user_id: int) -> List[Dict[str, Any]]:
        """Tutti i tentativi di drill completati, dal più recente.

        Unisce le due sorgenti: il catalogo (``ChallengeAttempt``) e le gare
        (``GaraChallengeAttempt``).
        """
        from ..competition.gara_challenge import GaraChallenge, GaraChallengeAttempt
        from .models import ChallengeAttempt

        entries: List[Dict[str, Any]] = []

        catalog = (
            ChallengeAttempt.query.options(joinedload(ChallengeAttempt.challenge))
            .filter(
                ChallengeAttempt.user_id == user_id,
                ChallengeAttempt.completed.is_(True),
            )
            .all()
        )
        for attempt in catalog:
            if attempt.challenge is None:
                continue
            entries.append(
                _entry(
                    challenge=attempt.challenge,
                    score=attempt.score,
                    passed=attempt.passed,
                    attempted_at=attempt.attempted_at,
                    source="catalog",
                    attempt_id=attempt.id,
                )
            )

        in_gara = (
            GaraChallengeAttempt.query.options(
                joinedload(GaraChallengeAttempt.gara_challenge).joinedload(
                    GaraChallenge.challenge
                ),
                joinedload(GaraChallengeAttempt.gara_challenge).joinedload(
                    GaraChallenge.gara
                ),
            )
            .filter(
                GaraChallengeAttempt.user_id == user_id,
                GaraChallengeAttempt.completed.is_(True),
            )
            .all()
        )
        for attempt in in_gara:
            gara_challenge = attempt.gara_challenge
            challenge = getattr(gara_challenge, "challenge", None)
            if challenge is None:
                continue
            gara = getattr(gara_challenge, "gara", None)
            entries.append(
                _entry(
                    challenge=challenge,
                    score=attempt.score,
                    passed=attempt.passed,
                    attempted_at=attempt.attempted_at,
                    source="gara",
                    gara_name=getattr(gara, "name", None),
                )
            )

        # Un tentativo senza data finirebbe in fondo invece di far esplodere
        # l'ordinamento con un confronto fra ``None`` e ``datetime``.
        entries.sort(key=lambda e: (e["attempted_at"] is not None, e["attempted_at"]))
        entries.reverse()
        return entries

    @staticmethod
    def get_drill_summary(user_id: int) -> List[Dict[str, Any]]:
        """Un drill per riga, col **miglior punteggio** e i tentativi (US-P9).

        ``attempts`` è in ordine cronologico **crescente**, perché serve a
        disegnare l'andamento nel tempo: un grafico si legge da sinistra.

        Per un drill pass/fail il concetto di «miglior punteggio» non esiste:
        al suo posto ``best_passed``, che dice se almeno una volta è riuscito.
        """
        by_challenge: Dict[int, Dict[str, Any]] = {}

        for entry in TrainingHistoryService.get_drill_attempts(user_id):
            row = by_challenge.setdefault(
                entry["challenge_id"],
                {
                    "challenge": entry["challenge"],
                    "challenge_id": entry["challenge_id"],
                    "challenge_name": entry["challenge_name"],
                    "is_pass_fail": entry["is_pass_fail"],
                    "attempts": [],
                    "best_score": None,
                    "best_passed": False,
                    "last_attempt_at": None,
                },
            )
            row["attempts"].append(entry)

            if entry["passed"]:
                row["best_passed"] = True
            if entry["score"] is not None:
                current = row["best_score"]
                row["best_score"] = (
                    entry["score"] if current is None else max(current, entry["score"])
                )
            if entry["attempted_at"] is not None and (
                row["last_attempt_at"] is None
                or entry["attempted_at"] > row["last_attempt_at"]
            ):
                row["last_attempt_at"] = entry["attempted_at"]

        summary = list(by_challenge.values())
        for row in summary:
            row["attempts"].reverse()  # cronologico crescente, per il grafico
            row["attempts_count"] = len(row["attempts"])

        summary.sort(
            key=lambda r: (r["last_attempt_at"] is not None, r["last_attempt_at"]),
            reverse=True,
        )
        return summary

    # ────────────────────────────────────────────────────────────────────
    # Esami
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def get_exam_history(user_id: int) -> List[Dict[str, Any]]:
        """Esami sostenuti, dal più recente, con la distinzione che conta.

        Solo i tentativi **conclusi**: uno abbandonato non è un esame sostenuto
        — il candidato non si è presentato — e comparirebbe come una bocciatura
        che non c'è stata.

        ``is_certified`` è ciò che il profilo traduce nel badge «certificato
        da …»; un tentativo in autonomia non lo porta mai.
        """
        from ..exam.models import Exam, ExamAttempt
        from ..status_enum import ExamAttemptMode, ExamAttemptStatus

        attempts = (
            ExamAttempt.query.options(
                joinedload(ExamAttempt.exam).joinedload(Exam.examiner),
                joinedload(ExamAttempt.examiner),
                joinedload(ExamAttempt.billiard_hall),
            )
            .filter(
                ExamAttempt.user_id == user_id,
                ExamAttempt.status == ExamAttemptStatus.COMPLETED.value,
            )
            .order_by(ExamAttempt.completed_at.desc())
            .all()
        )

        history: List[Dict[str, Any]] = []
        for attempt in attempts:
            certified = attempt.mode == ExamAttemptMode.CERTIFIED.value
            history.append(
                {
                    "attempt_id": attempt.id,
                    "exam": attempt.exam,
                    "exam_name": attempt.exam.name if attempt.exam else "",
                    "is_certified": certified,
                    "passed": attempt.passed,
                    "completed_at": attempt.completed_at,
                    "certified_at": attempt.certified_at if certified else None,
                    "examiner_name": (
                        attempt.examiner.username
                        if certified and attempt.examiner
                        else None
                    ),
                    "hall_name": (
                        attempt.billiard_hall.name if attempt.billiard_hall else None
                    ),
                    "total_score": attempt.total_score or 0,
                    "max_possible_score": attempt.max_possible_score or 0,
                }
            )
        return history

    # ────────────────────────────────────────────────────────────────────
    # Riepilogo
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def get_statistics(
        drill_attempts: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Le quattro cifre in cima alla sezione, o ``None`` se non c'è nulla.

        La media si calcola sui soli drill numerici: mediare un pass/fail con un
        punteggio su 15 darebbe un numero che non vuol dire niente.
        """
        if not drill_attempts:
            return None

        numeric = [
            e
            for e in drill_attempts
            if not e["is_pass_fail"] and e["score"] is not None
        ]
        pass_fail = [e for e in drill_attempts if e["is_pass_fail"]]

        avg_score = sum(e["score"] for e in numeric) / len(numeric) if numeric else 0
        pass_rate = (
            sum(1 for e in pass_fail if e["passed"]) / len(pass_fail) * 100
            if pass_fail
            else 0
        )

        return {
            "total_attempts": len(drill_attempts),
            "unique_challenges": len({e["challenge_id"] for e in drill_attempts}),
            "unique_garas": len(
                {e["gara_name"] for e in drill_attempts if e["gara_name"]}
            ),
            "avg_score": round(avg_score, 1),
            "pass_rate": round(pass_rate, 1),
        }

    @staticmethod
    def get_training_overview(user_id: int) -> Dict[str, Any]:
        """Tutto ciò che serve alla sezione «Allenamento» del profilo."""
        attempts = TrainingHistoryService.get_drill_attempts(user_id)
        return {
            "stats": TrainingHistoryService.get_statistics(attempts),
            "history": attempts,
            "drills": TrainingHistoryService.get_drill_summary(user_id),
            "exams": TrainingHistoryService.get_exam_history(user_id),
        }


__all__ = ["TrainingHistoryService"]
