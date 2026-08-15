"""
Module: models/exam/services.py
Purpose: Servizio del dominio esame — authoring, co-esaminatori, allenamento in
         autonomia, statistiche (ADR-042).

Tre differenze rispetto alla versione precedente, tutte volute:

- **Ogni metodo mutante riceve l'actor.** Chi scrive è parte dell'operazione,
  non un dettaglio della route: l'autorizzazione sta qui, in un posto solo.
- **Eccezioni di dominio**, non ``ValueError`` generici né ``first_or_404()``:
  un servizio non deve dipendere da Flask per dire «non l'ho trovato», e la
  route mappa da sola 404/409/403 (``http_status_for_exception``).
- **Statistiche senza N+1**: gli aggregati si calcolano in SQL con un GROUP BY,
  non iterando le relazioni ``lazy="dynamic"`` esame per esame.

La sessione certificata (apertura, accettazione del candidato, punteggi,
certificazione) arriva in Fase 3 insieme all'appuntamento: qui ci sono già gli
invarianti che la riguardano — su un tentativo certificato scrive solo
l'esaminatore, e mai prima che il candidato abbia accettato l'inizio — perché
sono proprietà del tentativo, non della schermata che lo pilota.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import case, distinct, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from ..base import db, utc_now
from ..challenge.models import Challenge
from ..exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from ..status_enum import ExamAttemptMode, ExamAttemptStatus
from ..transaction.manager import transactional
from ..user.models import User
from .models import Exam, ExamAttempt, ExamChallenge, ExamChallengeResult, ExamExaminer

logger = logging.getLogger(__name__)


class ExamService:
    """Composizione, somministrazione e statistiche degli esami."""

    # ────────────────────────────────────────────────────────────────────
    # Lookup e autorizzazione
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def get_exam(exam_id: int) -> Exam:
        """Esame per id, o ``NotFoundError``."""
        exam = db.session.get(Exam, exam_id)
        if exam is None:
            raise NotFoundError("Esame non trovato")
        return exam

    @staticmethod
    def can_edit(exam: Exam, actor: Optional[User]) -> bool:
        """True se ``actor`` può modificare l'esame.

        Il creatore, un co-esaminatore di *quell'*esame, o un admin (UJ-6): un
        esaminatore qualsiasi non tocca gli esami altrui.
        """
        if actor is None or not getattr(actor, "id", None):
            return False
        return bool(actor.is_admin) or exam.is_examined_by(actor.id)

    @staticmethod
    def _require_edit(exam: Exam, actor: Optional[User]) -> None:
        if not ExamService.can_edit(exam, actor):
            raise PermissionDeniedError("Non puoi modificare questo esame")

    @staticmethod
    def _require_examiner(actor: Optional[User]) -> User:
        """L'actor deve essere titolare del ruolo (o admin)."""
        if actor is None or not getattr(actor, "id", None) or not actor.is_examiner:
            raise PermissionDeniedError("Serve il ruolo di esaminatore")
        return actor

    # ────────────────────────────────────────────────────────────────────
    # Authoring dell'esame (US-E1)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="exam")
    def create_exam(
        actor: User,
        name: str,
        description: Optional[str] = None,
        time_limit_minutes: Optional[int] = None,
    ) -> Exam:
        """Crea un esame. Il creatore ne è esaminatore implicito."""
        ExamService._require_examiner(actor)

        clean_name = (name or "").strip()
        if not clean_name:
            raise ValidationError("Il nome dell'esame è obbligatorio")
        if time_limit_minutes is not None and time_limit_minutes <= 0:
            raise ValidationError("Il tempo limite deve essere positivo")

        exam = Exam(
            name=clean_name,
            description=description,
            examiner_id=actor.id,
            time_limit_minutes=time_limit_minutes,
        )
        db.session.add(exam)
        db.session.flush()
        return exam

    @staticmethod
    @transactional(domain="exam")
    def update_exam(
        exam_id: int,
        actor: User,
        name: Optional[str] = None,
        description: Optional[str] = None,
        time_limit_minutes: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> Exam:
        """Aggiorna i dati dell'esame."""
        exam = ExamService.get_exam(exam_id)
        ExamService._require_edit(exam, actor)

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValidationError("Il nome dell'esame è obbligatorio")
            exam.name = clean_name
        if description is not None:
            exam.description = description
        if time_limit_minutes is not None:
            if time_limit_minutes <= 0:
                raise ValidationError("Il tempo limite deve essere positivo")
            exam.time_limit_minutes = time_limit_minutes
        if is_active is not None:
            exam.is_active = is_active

        return exam

    @staticmethod
    @transactional(domain="exam")
    def deactivate_exam(exam_id: int, actor: User) -> Exam:
        """Ritira l'esame dal catalogo senza cancellarlo.

        I tentativi già svolti — e le certificazioni rilasciate — restano.
        """
        exam = ExamService.get_exam(exam_id)
        ExamService._require_edit(exam, actor)
        exam.is_active = False
        return exam

    # ────────────────────────────────────────────────────────────────────
    # Drill dentro l'esame (US-E1)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _validate_max_score(challenge: Challenge, max_score: Optional[int]) -> None:
        """``max_score`` è obbligatorio sui drill numerici, vietato sui pass/fail."""
        if challenge.pass_fail_only:
            if max_score is not None:
                raise ValidationError(
                    "Un drill pass/fail non ha punteggio massimo: vale 1 punto"
                )
            return
        if max_score is None:
            raise ValidationError("Serve un punteggio massimo per un drill numerico")
        if max_score <= 0:
            raise ValidationError("Il punteggio massimo deve essere positivo")

    @staticmethod
    @transactional(domain="exam")
    def add_challenge_to_exam(
        exam_id: int,
        challenge_id: int,
        actor: User,
        max_score: Optional[int] = None,
        order: Optional[int] = None,
    ) -> ExamChallenge:
        """Aggiunge un drill in coda all'esame (o alla posizione richiesta)."""
        exam = ExamService.get_exam(exam_id)
        ExamService._require_edit(exam, actor)

        challenge = db.session.get(Challenge, challenge_id)
        if challenge is None:
            raise NotFoundError("Drill non trovato")
        ExamService._validate_max_score(challenge, max_score)

        existing = ExamChallenge.query.filter_by(
            exam_id=exam_id, challenge_id=challenge_id
        ).first()
        if existing is not None:
            raise ConflictError("Questo drill fa già parte dell'esame")

        if order is None:
            max_order = (
                db.session.query(func.max(ExamChallenge.order))
                .filter_by(exam_id=exam_id)
                .scalar()
            )
            order = (max_order or 0) + 1
        else:
            # Le posizioni partono da 1. Ammettere lo zero o un negativo non
            # sarebbe solo brutto in lista: `reorder_exam_challenges` parcheggia
            # le posizioni sui negativi, e una riga già negativa collide con il
            # parcheggio facendo fallire un riordino altrimenti legittimo.
            if order <= 0:
                raise ValidationError("La posizione parte da 1")
            if (
                ExamChallenge.query.filter_by(exam_id=exam_id, order=order).first()
                is not None
            ):
                raise ConflictError("Posizione già occupata nell'esame")

        exam_challenge = ExamChallenge(
            exam_id=exam_id,
            challenge_id=challenge_id,
            order=order,
            max_score=max_score,
        )
        db.session.add(exam_challenge)
        db.session.flush()
        return exam_challenge

    @staticmethod
    @transactional(domain="exam")
    def update_exam_challenge(
        exam_id: int, challenge_id: int, actor: User, max_score: Optional[int]
    ) -> ExamChallenge:
        """Cambia il punteggio massimo di un drill dentro l'esame."""
        exam = ExamService.get_exam(exam_id)
        ExamService._require_edit(exam, actor)

        exam_challenge = ExamChallenge.query.filter_by(
            exam_id=exam_id, challenge_id=challenge_id
        ).first()
        if exam_challenge is None:
            raise NotFoundError("Drill non presente nell'esame")

        ExamService._validate_max_score(exam_challenge.challenge, max_score)
        exam_challenge.max_score = max_score
        return exam_challenge

    @staticmethod
    @transactional(domain="exam")
    def remove_challenge_from_exam(
        exam_id: int, challenge_id: int, actor: User
    ) -> None:
        """Toglie un drill dall'esame."""
        exam = ExamService.get_exam(exam_id)
        ExamService._require_edit(exam, actor)

        exam_challenge = ExamChallenge.query.filter_by(
            exam_id=exam_id, challenge_id=challenge_id
        ).first()
        if exam_challenge is None:
            raise NotFoundError("Drill non presente nell'esame")

        db.session.delete(exam_challenge)

    @staticmethod
    @transactional(domain="exam")
    def reorder_exam_challenges(
        exam_id: int, actor: User, ordered_challenge_ids: Sequence[int]
    ) -> List[ExamChallenge]:
        """Riordina i drill dell'esame secondo la sequenza data.

        Due passate: ``(exam_id, order)`` è UNIQUE, quindi scrivere le nuove
        posizioni una per una collide con quelle vecchie appena due drill si
        scambiano. Si parcheggiano prima su valori negativi, che nessun ordine
        reale usa.
        """
        exam = ExamService.get_exam(exam_id)
        ExamService._require_edit(exam, actor)

        by_challenge = {ec.challenge_id: ec for ec in exam.challenges.all()}
        requested = list(ordered_challenge_ids)
        # «Esattamente» vuol dire anche una volta sola: deduplicare in silenzio
        # farebbe passare un elenco ambiguo e ne applicherebbe una lettura
        # arbitraria, che non è ciò che il chiamante ha chiesto.
        if len(requested) != len(set(requested)) or set(requested) != set(by_challenge):
            raise ValidationError(
                "Il riordino deve elencare esattamente i drill dell'esame, "
                "ciascuno una volta sola"
            )

        for index, challenge_id in enumerate(requested, start=1):
            by_challenge[challenge_id].order = -index
        db.session.flush()

        for index, challenge_id in enumerate(requested, start=1):
            by_challenge[challenge_id].order = index
        db.session.flush()

        return [by_challenge[cid] for cid in requested]

    # ────────────────────────────────────────────────────────────────────
    # Co-esaminatori (US-E2)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def eligible_examiners(exam_id: int) -> List[User]:
        """Chi può essere aggiunto come co-esaminatore.

        I titolari attivi del ruolo, meno il creatore e chi c'è già. In UJ-1 la
        lista è **vuota** — l'unico esaminatore del sistema è il creatore — e
        la UI deve reggerlo senza inventarsi candidati.
        """
        from ..user.role_enum import GrantableRole
        from ..user.role_grant_service import RoleGrantService

        exam = ExamService.get_exam(exam_id)
        holder_ids = {
            g.user_id for g in RoleGrantService.list_holders(GrantableRole.EXAMINER)
        } - exam.examiner_ids
        if not holder_ids:
            return []
        # Via User.query: il filtro automatico sul soft delete esclude così i
        # titolari anonimizzati.
        return User.query.filter(User.id.in_(holder_ids)).all()

    @staticmethod
    @transactional(domain="exam")
    def add_examiner(exam_id: int, user_id: int, actor: User) -> ExamExaminer:
        """Aggiunge un co-esaminatore all'esame."""
        from ..user.role_enum import GrantableRole
        from ..user.role_grant_service import RoleGrantService

        exam = ExamService.get_exam(exam_id)
        ExamService._require_edit(exam, actor)

        candidate = db.session.get(User, user_id)
        if candidate is None or candidate.is_deleted:
            raise NotFoundError("Utente non trovato")

        # Il grant, non ``is_examiner``: quest'ultimo è True anche per gli
        # admin, e un admin senza grant non è un esaminatore dell'esame.
        if not RoleGrantService.has_role(user_id, GrantableRole.EXAMINER):
            raise ValidationError("L'utente non ha il ruolo di esaminatore")

        if exam.is_examined_by(user_id):
            raise ConflictError("È già esaminatore di questo esame")

        link = ExamExaminer(
            exam_id=exam_id, user_id=user_id, added_by_id=actor.id, added_at=utc_now()
        )
        db.session.add(link)
        db.session.flush()
        return link

    @staticmethod
    @transactional(domain="exam")
    def remove_examiner(exam_id: int, user_id: int, actor: User) -> None:
        """Toglie un co-esaminatore. Il creatore non è rimovibile."""
        exam = ExamService.get_exam(exam_id)
        ExamService._require_edit(exam, actor)

        if user_id == exam.examiner_id:
            raise ValidationError("Il creatore dell'esame non può essere rimosso")

        link = ExamExaminer.query.filter_by(exam_id=exam_id, user_id=user_id).first()
        if link is None:
            raise NotFoundError("Non è esaminatore di questo esame")

        db.session.delete(link)

    # ────────────────────────────────────────────────────────────────────
    # Letture di catalogo
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def get_available_exams() -> List[Exam]:
        """Esami attivi, per il catalogo dei candidati (US-P1)."""
        return (
            Exam.query.options(joinedload(Exam.examiner))
            .filter_by(is_active=True)
            .order_by(Exam.name.asc())
            .all()
        )

    @staticmethod
    def get_exams_for_examiner(
        user_id: int, include_inactive: bool = False
    ) -> List[Exam]:
        """Esami che ``user_id`` somministra: creati da lui o in cui è aggiunto."""
        co_examined = db.session.query(ExamExaminer.exam_id).filter(
            ExamExaminer.user_id == user_id
        )
        query = Exam.query.filter(
            db.or_(Exam.examiner_id == user_id, Exam.id.in_(co_examined))
        )
        if not include_inactive:
            query = query.filter(Exam.is_active.is_(True))
        return query.order_by(Exam.name.asc()).all()

    @staticmethod
    def get_user_exam_attempts(
        user_id: int, certified_only: bool = False
    ) -> List[ExamAttempt]:
        """Tentativi d'esame di un utente, dal più recente.

        ``exam`` ed ``examiner`` in eager loading: il profilo stampa nome
        dell'esame e «certificato da …» per riga (UJ-7).
        """
        query = ExamAttempt.query.options(
            joinedload(ExamAttempt.exam), joinedload(ExamAttempt.examiner)
        ).filter(ExamAttempt.user_id == user_id)
        if certified_only:
            query = query.filter(
                ExamAttempt.mode == ExamAttemptMode.CERTIFIED.value,
                ExamAttempt.status == ExamAttemptStatus.COMPLETED.value,
            )
        return query.order_by(ExamAttempt.started_at.desc()).all()

    @staticmethod
    def get_open_self_practice(user_id: int, exam_id: int) -> Optional[ExamAttempt]:
        """Il tentativo in autonomia ancora aperto, se c'è (UJ-2, ripresa)."""
        return ExamAttempt.query.filter_by(
            user_id=user_id,
            exam_id=exam_id,
            mode=ExamAttemptMode.SELF_PRACTICE.value,
            status=ExamAttemptStatus.IN_PROGRESS.value,
        ).first()

    # ────────────────────────────────────────────────────────────────────
    # Tentativo in autonomia (US-P3)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="exam")
    def start_self_practice(actor: User, exam_id: int) -> ExamAttempt:
        """Apre (o riprende) un tentativo di allenamento.

        Resta allenamento per sempre: nessun percorso lo trasforma in
        certificato, nemmeno a posteriori.
        """
        exam = ExamService.get_exam(exam_id)
        if not exam.is_active:
            raise ConflictError("Questo esame non è più disponibile")
        if exam.challenges.count() == 0:
            raise ValidationError("L'esame non contiene ancora nessun drill")

        existing = ExamService.get_open_self_practice(actor.id, exam_id)
        if existing is not None:
            return existing

        attempt = ExamAttempt(
            exam_id=exam_id,
            user_id=actor.id,
            mode=ExamAttemptMode.SELF_PRACTICE.value,
            status=ExamAttemptStatus.IN_PROGRESS.value,
            started_at=utc_now(),
        )
        db.session.add(attempt)
        db.session.flush()

        attempt.create_placeholder_results()
        db.session.flush()
        return attempt

    # ────────────────────────────────────────────────────────────────────
    # Sessione certificata (US-E6, US-P6)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="exam")
    def open_certified_session(actor: User, request_id: int) -> ExamAttempt:
        """Apre la sessione d'esame dall'appuntamento accettato.

        Nasce in ``awaiting_player_start``: la sessione esiste, ma **nessun
        punteggio è registrabile** finché il candidato non accetta l'inizio
        (US-P6). L'attesa è uno stato del tentativo, non una schermata: una
        POST diretta aggira la UI, non il servizio.
        """
        from .request_models import ExamRequest

        request = db.session.get(ExamRequest, request_id)
        if request is None:
            raise NotFoundError("Richiesta d'esame non trovata")

        actor_id = getattr(actor, "id", None)
        if actor_id is None:
            raise PermissionDeniedError("Non puoi aprire questa sessione")

        if not request.is_accepted or request.accepted_by_id is None:
            raise ConflictError(
                "L'appuntamento non è stato ancora fissato: non c'è nulla da aprire"
            )
        if actor_id != request.accepted_by_id:
            raise PermissionDeniedError(
                "Solo l'esaminatore che ha accettato l'appuntamento apre la sessione"
            )
        if actor_id == request.requester_id:
            raise PermissionDeniedError("Un esaminatore non può esaminare se stesso")

        attempt = ExamAttempt(
            exam_id=request.exam_id,
            user_id=request.requester_id,
            mode=ExamAttemptMode.CERTIFIED.value,
            status=ExamAttemptStatus.AWAITING_PLAYER_START.value,
            started_at=utc_now(),
            examiner_id=actor_id,
            billiard_hall_id=request.billiard_hall_id,
            exam_request_id=request.id,
        )
        db.session.add(attempt)

        # Savepoint: l'indice UNIQUE parziale su ``exam_request_id`` emerge al
        # flush se una sessione per questo appuntamento esiste già, e va
        # tradotto invece di uscire come 500 opaco (ADR-025).
        try:
            with db.session.begin_nested():
                db.session.flush()
        except IntegrityError as exc:
            raise ConflictError(
                "Per questo appuntamento la sessione è già stata aperta"
            ) from exc

        attempt.create_placeholder_results()
        db.session.flush()

        ExamService._notify_session_opened(attempt)
        return attempt

    @staticmethod
    @transactional(domain="exam")
    def accept_session_start(attempt_id: int, actor: User) -> ExamAttempt:
        """Il candidato accetta l'inizio dell'esame (US-P6).

        È l'unico gesto che sblocca la registrazione dei punteggi, e lo fa solo
        il candidato: nessuno viene valutato a sua insaputa.
        """
        attempt = db.session.get(ExamAttempt, attempt_id)
        if attempt is None:
            raise NotFoundError("Tentativo non trovato")

        if getattr(actor, "id", None) != attempt.user_id:
            raise PermissionDeniedError(
                "Solo il candidato può accettare l'inizio dell'esame"
            )
        if attempt.status != ExamAttemptStatus.AWAITING_PLAYER_START.value:
            raise ConflictError("Questa sessione non è in attesa di iniziare")

        attempt.status = ExamAttemptStatus.IN_PROGRESS.value
        attempt.started_at = utc_now()
        db.session.flush()
        return attempt

    # ────────────────────────────────────────────────────────────────────
    # Registrazione dei risultati
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _require_scorer(attempt: ExamAttempt, actor: Optional[User]) -> None:
        """Chi può scrivere i punteggi su questo tentativo.

        In autonomia il candidato stesso; in una sessione certificata solo
        l'esaminatore che la conduce — mai il candidato su di sé.
        """
        actor_id = getattr(actor, "id", None)
        if actor_id is None:
            raise PermissionDeniedError("Non puoi registrare punteggi")

        if attempt.mode == ExamAttemptMode.SELF_PRACTICE.value:
            if actor_id != attempt.user_id:
                raise PermissionDeniedError(
                    "Solo chi si allena registra i propri punteggi"
                )
            return

        if attempt.examiner_id is None or actor_id != attempt.examiner_id:
            raise PermissionDeniedError(
                "Solo l'esaminatore della sessione registra i punteggi"
            )
        if attempt.examiner_id == attempt.user_id:
            raise PermissionDeniedError("Un esaminatore non può esaminare se stesso")

    @staticmethod
    def _require_in_progress(attempt: ExamAttempt) -> None:
        if attempt.status == ExamAttemptStatus.AWAITING_PLAYER_START.value:
            # US-P6: nessuno viene valutato a sua insaputa. Il rifiuto è del
            # servizio, non della UI, perché la UI si aggira con una POST.
            raise ConflictError(
                "Il candidato non ha ancora accettato l'inizio dell'esame"
            )
        if attempt.status != ExamAttemptStatus.IN_PROGRESS.value:
            raise ConflictError("Il tentativo non è in corso")

    @staticmethod
    @transactional(domain="exam")
    def record_challenge_result(
        attempt_id: int,
        exam_challenge_id: int,
        actor: User,
        score: Optional[int] = None,
        passed: Optional[bool] = None,
    ) -> ExamChallengeResult:
        """Registra il risultato di un drill dentro un tentativo."""
        attempt = db.session.get(ExamAttempt, attempt_id)
        if attempt is None:
            raise NotFoundError("Tentativo non trovato")

        ExamService._require_scorer(attempt, actor)
        ExamService._require_in_progress(attempt)

        result = ExamChallengeResult.query.filter_by(
            exam_attempt_id=attempt_id, exam_challenge_id=exam_challenge_id
        ).first()
        if result is None:
            raise NotFoundError("Drill non presente in questo tentativo")

        exam_challenge = result.exam_challenge
        if exam_challenge.is_pass_fail:
            if passed is None:
                raise ValidationError("Serve l'esito per un drill pass/fail")
            result.record(score=1 if passed else 0, passed=bool(passed))
        else:
            if score is None:
                raise ValidationError("Serve il punteggio per un drill numerico")
            if score < 0 or score > exam_challenge.effective_max_score:
                raise ValidationError(
                    "Punteggio fuori scala: " f"0–{exam_challenge.effective_max_score}"
                )
            result.record(score=score, passed=None)

        attempt.recompute_scores()
        db.session.flush()
        return result

    @staticmethod
    @transactional(domain="exam")
    def complete_attempt(
        attempt_id: int, actor: User, passed: Optional[bool] = None
    ) -> ExamAttempt:
        """Chiude un tentativo.

        In autonomia non c'è nulla da certificare: ``passed`` resta NULL e
        passarlo è un errore, non una scorciatoia. La chiusura certificata —
        con l'esito booleano — arriva in Fase 3 insieme alla sessione.
        """
        attempt = db.session.get(ExamAttempt, attempt_id)
        if attempt is None:
            raise NotFoundError("Tentativo non trovato")

        ExamService._require_scorer(attempt, actor)
        ExamService._require_in_progress(attempt)

        certified = attempt.mode == ExamAttemptMode.CERTIFIED.value
        if not certified:
            if passed is not None:
                raise ValidationError(
                    "Un tentativo in autonomia non certifica: non ha un esito"
                )
        else:
            if passed is None:
                raise ValidationError("Serve l'esito: superato o non superato")
            attempt.passed = bool(passed)
            attempt.certified_at = utc_now()

        attempt.recompute_scores()
        attempt.status = ExamAttemptStatus.COMPLETED.value
        attempt.completed_at = utc_now()
        db.session.flush()

        if certified:
            ExamService._notify_certified(attempt)
        ExamService._publish_completed(attempt)
        return attempt

    @staticmethod
    @transactional(domain="exam")
    def abandon_attempt(attempt_id: int, actor: User) -> ExamAttempt:
        """Interrompe un tentativo senza esito.

        Non è una bocciatura: ``passed`` resta NULL e il tentativo non compare
        fra gli esami sostenuti. Serve al caso reale del candidato che non si
        presenta (UJ-3) e a chi lascia a metà un allenamento.
        """
        attempt = db.session.get(ExamAttempt, attempt_id)
        if attempt is None:
            raise NotFoundError("Tentativo non trovato")

        actor_id = getattr(actor, "id", None)
        allowed = {attempt.user_id}
        if attempt.examiner_id is not None:
            allowed.add(attempt.examiner_id)
        if actor_id not in allowed and not getattr(actor, "is_admin", False):
            raise PermissionDeniedError("Non puoi interrompere questo tentativo")

        if not ExamAttemptStatus.is_open(attempt.status):
            raise ConflictError("Il tentativo è già concluso")

        attempt.status = ExamAttemptStatus.ABANDONED.value
        attempt.completed_at = utc_now()
        attempt.passed = None
        db.session.flush()
        return attempt

    # ────────────────────────────────────────────────────────────────────
    # Eventi di dominio
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _publish_completed(attempt: ExamAttempt) -> None:
        """Annuncia la chiusura del tentativo (XP, streak, achievement).

        L'esame non chiama la gamification: pubblica il fatto e chi vuole
        ascolta. Best-effort come le notifiche — un handler che esplode non
        deve far perdere la certificazione appena registrata, che è il dato
        importante.
        """
        from ..events.base import EventBus
        from .events import ExamAttemptCompletedEvent

        try:
            EventBus.publish(
                ExamAttemptCompletedEvent(
                    attempt_id=attempt.id,
                    exam_id=attempt.exam_id,
                    exam_name=attempt.exam.name if attempt.exam else "",
                    user_id=attempt.user_id,
                    mode=attempt.mode,
                    passed=attempt.passed,
                    examiner_id=attempt.examiner_id,
                    total_score=attempt.total_score or 0,
                    max_possible_score=attempt.max_possible_score or 0,
                )
            )
        except Exception:  # pragma: no cover - la gamification non blocca mai
            logger.warning("Evento di chiusura esame non pubblicato", exc_info=True)

    # ────────────────────────────────────────────────────────────────────
    # Notifiche della sessione (best-effort: non bloccano mai l'operazione)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _notify(user_ids: Sequence[int], **kwargs: Any) -> None:
        if not user_ids:
            return
        try:
            from ..notification.factory import NotificationFactory

            NotificationFactory.create_bulk_notification(
                user_ids=list(user_ids), continue_on_error=True, **kwargs
            )
        except Exception:  # pragma: no cover - le notifiche non bloccano mai
            logger.warning("Notifica di sessione d'esame non inviata", exc_info=True)

    @staticmethod
    def _notify_session_opened(attempt: ExamAttempt) -> None:
        from flask_babel import _
        from ..notification.models import NotificationPriority, NotificationType

        ExamService._notify(
            [attempt.user_id],
            notification_type=NotificationType.EXAM_SESSION_OPENED,
            title=_("L'esame sta per iniziare"),
            message=_(
                "L'esaminatore ha aperto la sessione di «%(exam)s»: accetta "
                "l'inizio per far partire la valutazione.",
                exam=attempt.exam.name,
            ),
            priority=NotificationPriority.HIGH,
            # Le route dell'esame arrivano in Fase 5: URL da tenere allineato.
            action_url=f"/exam/sessions/{attempt.id}",
            action_text=_("Accetta l'inizio"),
        )

    @staticmethod
    def _notify_certified(attempt: ExamAttempt) -> None:
        from flask_babel import _
        from ..notification.models import NotificationPriority, NotificationType

        outcome = _("superato") if attempt.passed else _("non superato")
        ExamService._notify(
            [attempt.user_id],
            notification_type=NotificationType.EXAM_CERTIFIED,
            title=_("Esame certificato"),
            message=_(
                "«%(exam)s»: esito %(outcome)s, certificato da %(examiner)s.",
                exam=attempt.exam.name,
                outcome=outcome,
                examiner=(
                    attempt.examiner.username
                    if attempt.examiner
                    else _("l'esaminatore")
                ),
            ),
            priority=NotificationPriority.HIGH,
            action_url=f"/exam/sessions/{attempt.id}",
            action_text=_("Vedi l'esito"),
        )

    # ────────────────────────────────────────────────────────────────────
    # Statistiche (US-E8)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def get_exam_statistics(exam_id: int) -> Dict[str, Any]:
        """Statistiche di un singolo esame."""
        return ExamService.get_exam(exam_id).get_statistics()

    @staticmethod
    def get_examiner_statistics(examiner_id: int) -> Dict[str, Any]:
        """Statistiche di tutti gli esami di un esaminatore (US-E8).

        Tre query in tutto, indipendentemente da quanti esami ci sono: gli
        aggregati escono da un GROUP BY, non da un ``exam.get_statistics()``
        per esame — che con ``attempts`` ``lazy="dynamic"`` era un N+1.
        """
        exams = ExamService.get_exams_for_examiner(examiner_id, include_inactive=True)
        if not exams:
            return {
                "total_exams": 0,
                "certified_attempts": 0,
                "passed": 0,
                "failed": 0,
                "pass_rate": None,
                "unique_candidates": 0,
                "exams": [],
            }

        exam_ids = [exam.id for exam in exams]
        certified_filter = (
            ExamAttempt.exam_id.in_(exam_ids),
            ExamAttempt.mode == ExamAttemptMode.CERTIFIED.value,
            ExamAttempt.status == ExamAttemptStatus.COMPLETED.value,
        )
        passed_sum = func.sum(case((ExamAttempt.passed.is_(True), 1), else_=0))

        rows = (
            db.session.query(
                ExamAttempt.exam_id,
                func.count(ExamAttempt.id),
                passed_sum,
                func.count(distinct(ExamAttempt.user_id)),
            )
            .filter(*certified_filter)
            .group_by(ExamAttempt.exam_id)
            .all()
        )
        by_exam = {
            exam_id: (int(total), int(passed or 0), int(candidates))
            for exam_id, total, passed, candidates in rows
        }

        # I candidati distinti dell'esaminatore non sono la somma di quelli
        # per esame: la stessa persona può aver sostenuto due esami suoi.
        unique_candidates = (
            db.session.query(func.count(distinct(ExamAttempt.user_id)))
            .filter(*certified_filter)
            .scalar()
            or 0
        )

        per_exam = []
        total_attempts = total_passed = 0
        for exam in exams:
            attempts, passed, candidates = by_exam.get(exam.id, (0, 0, 0))
            total_attempts += attempts
            total_passed += passed
            per_exam.append(
                {
                    "exam": exam,
                    "certified_attempts": attempts,
                    "passed": passed,
                    "failed": attempts - passed,
                    "pass_rate": (
                        round(passed / attempts * 100, 1) if attempts else None
                    ),
                    "unique_candidates": candidates,
                }
            )

        return {
            "total_exams": len(exams),
            "certified_attempts": total_attempts,
            "passed": total_passed,
            "failed": total_attempts - total_passed,
            "pass_rate": (
                round(total_passed / total_attempts * 100, 1)
                if total_attempts
                else None
            ),
            "unique_candidates": int(unique_candidates),
            "exams": per_exam,
        }
