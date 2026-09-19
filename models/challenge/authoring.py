"""Creare, correggere e duplicare un esercizio: un modulo, tre ingressi (#252, #253).

Il modulo è uno e questo servizio è la sua unica porta: scrive **insieme** come
si valuta la prova (``ChallengeService``) e come la si trova
(``ChallengeProfileService``), in una transazione sola — un esercizio salvato a
metà, col titolo nuovo e le categorie vecchie, non deve poter esistere.

**La domanda sulle prove già registrate.** Correggere un esercizio che ha già dei
risultati riscrive il passato: chi guarda uno storico legge un 8 ottenuto su una
scala che non c'è più. Quindi quando il salvataggio cambia il **senso** dei
punteggi — tipo di valutazione, massimo, istruzioni — e di prove ce ne sono,
``update`` non salva: solleva ``EvidenceDecisionRequired``, che dice che cosa è
cambiato e quante prove ci sono. Chi chiama richiama con la decisione:

* ``COPY`` — nasce un esercizio nuovo con le modifiche, l'originale resta com'è;
* ``OVERWRITE`` — si modifica questo, sapendolo.

Titolo, profilo, foto e attivo/non attivo **non** fanno scattare la domanda: un
refuso corretto o un'abilità aggiunta non toccano nessun punteggio.

La decisione sta qui e non nel browser: una POST scritta a mano non deve poterla
saltare.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from flask_babel import gettext as _

from ..base import db
from ..exceptions import ConflictError, NotFoundError, ValidationError
from ..status_enum import _StrEnum
from ..transaction.manager import transactional
from .models import Challenge, ChallengeAttempt
from .profile_service import ChallengeProfileService
from .services import ChallengeService


class OnEvidence(_StrEnum):
    """Che fare quando la modifica cambia il senso di prove già registrate."""

    ASK = "ask"
    COPY = "copy"
    OVERWRITE = "overwrite"

    @classmethod
    def parse(cls, value: object) -> "OnEvidence":
        try:
            return cls(str(value or "").strip().lower())
        except ValueError:
            return cls.ASK


class MeaningChangeKind(_StrEnum):
    SCORING_TYPE = "scoring_type"
    MAX_SCORE = "max_score"
    INSTRUCTIONS = "instructions"


@dataclass(frozen=True)
class MeaningChange:
    """Una modifica che cambia come si leggono i punteggi già registrati."""

    kind: MeaningChangeKind
    before: Optional[str] = None
    after: Optional[str] = None


@dataclass(frozen=True)
class Evidence:
    """Quante prove ha già l'esercizio, e di quanti giocatori."""

    attempts: int = 0
    players: int = 0

    def __bool__(self) -> bool:
        return self.attempts > 0


class EvidenceDecisionRequired(ConflictError):
    """Il salvataggio aspetta una decisione: copia, o modifica comunque."""

    def __init__(self, changes: List[MeaningChange], evidence: Evidence):
        super().__init__(_("Questo esercizio ha già delle prove registrate"))
        self.changes = changes
        self.evidence = evidence


@dataclass(frozen=True)
class ChallengeDraft:
    """Tutto quello che il modulo dice di un esercizio, già ripulito."""

    description: str
    title: str = ""
    pass_fail_only: bool = False
    max_score: Optional[int] = None
    is_active: Optional[bool] = None
    abilita: Sequence[str] = ()
    gesti: Sequence[str] = ()
    declared_level: Optional[int] = None
    family: Optional[str] = None
    family_step: Optional[int] = None
    cue_ball_reset: Optional[bool] = None
    variants: Sequence[Dict[str, Any]] = field(default_factory=tuple)


@dataclass(frozen=True)
class AuthoringResult:
    challenge: Challenge
    # True quando le modifiche sono finite su una copia e l'originale è intatto.
    copied: bool = False


class ChallengeAuthoringService:
    """Il modulo dell'esercizio salva tutto da qui."""

    # ── leggere ─────────────────────────────────────────────────────────
    @staticmethod
    def evidence(challenge_id: int) -> Evidence:
        """Le prove che una modifica riscriverebbe: catalogo, gara, esami.

        Più largo di «quanti l'hanno provato» (``popularity``), che guarda solo
        agli allenamenti: qui contano anche le prove d'esame, perché il
        punteggio di una sessione certificata si legge sulla stessa scala.
        """
        from ..competition.gara_challenge import GaraChallenge, GaraChallengeAttempt
        from ..exam.models import ExamAttempt, ExamChallenge, ExamChallengeResult

        dal_catalogo = (
            db.session.query(ChallengeAttempt.user_id)
            .filter(
                ChallengeAttempt.challenge_id == challenge_id,
                ChallengeAttempt.completed.is_(True),
            )
            .all()
        )
        in_gara = (
            db.session.query(GaraChallengeAttempt.user_id)
            .join(
                GaraChallenge,
                GaraChallengeAttempt.gara_challenge_id == GaraChallenge.id,
            )
            .filter(
                GaraChallenge.challenge_id == challenge_id,
                GaraChallengeAttempt.completed.is_(True),
            )
            .all()
        )
        in_esame = (
            db.session.query(ExamAttempt.user_id)
            .join(
                ExamChallengeResult,
                ExamChallengeResult.exam_attempt_id == ExamAttempt.id,
            )
            .join(
                ExamChallenge,
                ExamChallengeResult.exam_challenge_id == ExamChallenge.id,
            )
            .filter(
                ExamChallenge.challenge_id == challenge_id,
                ExamChallengeResult.attempted_at.isnot(None),
            )
            .all()
        )
        righe = [*dal_catalogo, *in_gara, *in_esame]
        return Evidence(attempts=len(righe), players=len({r[0] for r in righe}))

    @staticmethod
    def meaning_changes(
        challenge: Challenge, draft: ChallengeDraft
    ) -> List[MeaningChange]:
        """Che cosa, di questa bozza, cambia il senso dei punteggi già scritti."""
        changes: List[MeaningChange] = []
        if bool(challenge.pass_fail_only) != bool(draft.pass_fail_only):
            changes.append(MeaningChange(MeaningChangeKind.SCORING_TYPE))
        elif not draft.pass_fail_only and challenge.max_score != draft.max_score:
            changes.append(
                MeaningChange(
                    MeaningChangeKind.MAX_SCORE,
                    before=_fmt(challenge.max_score),
                    after=_fmt(draft.max_score),
                )
            )
        if _squash(challenge.description) != _squash(draft.description):
            changes.append(MeaningChange(MeaningChangeKind.INSTRUCTIONS))
        return changes

    # ── scrivere ────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="challenge")
    def create(
        draft: ChallengeDraft,
        *,
        image_path: str,
        created_by_id: Optional[int],
        diagram_scene: Optional[str] = None,
    ) -> Challenge:
        """Un esercizio nuovo, col suo profilo. Vale anche per «Duplica»."""
        _require_description(draft)
        challenge = ChallengeService.create_challenge(
            title=draft.title,
            description=draft.description.strip(),
            image_path=image_path,
            pass_fail_only=draft.pass_fail_only,
            created_by_id=created_by_id,
            diagram_scene=diagram_scene,
            max_score=draft.max_score,
        )
        db.session.flush()
        _write_profile(challenge.id, draft, is_new=True)
        return challenge

    @staticmethod
    @transactional(domain="challenge")
    def update(
        challenge_id: int,
        draft: ChallengeDraft,
        *,
        acting_user_id: Optional[int],
        image_path: Optional[str] = None,
        copy_image_path: Optional[str] = None,
        on_evidence: OnEvidence = OnEvidence.ASK,
    ) -> AuthoringResult:
        """Salva le modifiche — qui, o su una copia se si è scelto così.

        Args:
            image_path: la foto nuova, se ne è stata caricata una
            copy_image_path: il file **già duplicato** dell'immagine
                dell'originale, per la copia. Serve solo con ``COPY`` e senza
                foto nuova: due esercizi che puntano allo stesso file vuol dire
                che ritoccando l'uno si spegne il disegno dell'altro
            on_evidence: la decisione, quando la domanda è già stata fatta

        Raises:
            EvidenceDecisionRequired: la modifica cambia il senso di prove già
                registrate e nessuno ha ancora deciso
        """
        challenge = db.session.get(Challenge, challenge_id)
        if challenge is None:
            raise NotFoundError(_("Esercizio non trovato"))
        _require_description(draft)

        changes = ChallengeAuthoringService.meaning_changes(challenge, draft)
        evidence = (
            ChallengeAuthoringService.evidence(challenge_id) if changes else Evidence()
        )
        if changes and evidence:
            if on_evidence == OnEvidence.ASK:
                raise EvidenceDecisionRequired(changes, evidence)
            if on_evidence == OnEvidence.COPY:
                immagine = image_path or copy_image_path
                if not immagine:
                    raise ValidationError(_("Alla copia manca l'immagine"))
                copia = ChallengeAuthoringService.create(
                    _without_variant_ids(draft),
                    image_path=immagine,
                    created_by_id=acting_user_id,
                    # La scena segue l'immagine: con una foto nuova il disegno
                    # dell'originale non descrive più la copia.
                    diagram_scene=None if image_path else challenge.diagram_scene,
                )
                return AuthoringResult(challenge=copia, copied=True)

        ChallengeService.update_challenge(
            challenge_id=challenge_id,
            title=draft.title,
            description=draft.description.strip(),
            image_path=image_path,
            pass_fail_only=draft.pass_fail_only,
            is_active=draft.is_active,
            max_score=draft.max_score,
            # Il modulo manda sempre il campo: vuoto vuol dire «togli il tetto».
            clear_max_score=draft.max_score is None,
        )
        if image_path:
            # Una foto caricata al posto di un disegno: la scena di prima non
            # descrive più quello che si vede, e «Modifica il disegno»
            # riaprirebbe un tavolo che non è questo.
            challenge.diagram_scene = None
        _write_profile(challenge_id, draft, is_new=False)
        return AuthoringResult(challenge=challenge, copied=False)


# ────────────────────────────────────────────────────────────────────────
# Pezzi
# ────────────────────────────────────────────────────────────────────────
def _write_profile(challenge_id: int, draft: ChallengeDraft, *, is_new: bool) -> None:
    ChallengeProfileService.set_profile(
        challenge_id,
        abilita=list(draft.abilita),
        gesti=list(draft.gesti),
        declared_level=draft.declared_level,
        family=draft.family,
        family_step=draft.family_step,
        cue_ball_reset=draft.cue_ball_reset,
        variants=list(
            _without_variant_ids(draft).variants if is_new else draft.variants
        ),
    )


def _without_variant_ids(draft: ChallengeDraft) -> ChallengeDraft:
    """Le varianti di una copia sono righe nuove: gli id dell'originale via."""
    from dataclasses import replace

    return replace(
        draft, variants=tuple({"label": v.get("label")} for v in draft.variants)
    )


def _require_description(draft: ChallengeDraft) -> None:
    if not (draft.description or "").strip():
        raise ValidationError(_("Servono le istruzioni per chi esegue l'esercizio"))


def _squash(testo: Optional[str]) -> str:
    """Spazi e ritorni a capo non sono una modifica delle istruzioni."""
    return " ".join((testo or "").split())


def _fmt(valore: Optional[int]) -> Optional[str]:
    return None if valore is None else str(valore)
