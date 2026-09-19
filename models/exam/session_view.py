"""
Module: models/exam/session_view.py
Purpose: Dove sta guardando chi somministra una sessione d'esame.

Sola lettura. La sessione di prima era l'elenco di **tutti** gli esercizi, ognuno
col suo campo e il suo «Registra»: al tavolo se ne somministra uno per volta, e
il resto è rumore. Qui si decide qual è l'esercizio a fuoco e quale prova si sta
per scrivere; la pagina disegna solo quello, col tastierino agganciato in basso.

**Rinunciare a una prova non si persiste.** «Conta la migliore» rende legittimo
fermarsi alla seconda di tre, e il modello lo regge già: una prova vuota non è
uno zero (`ExamAttempt.recompute_scores`) e la chiusura non pretende tutte le
caselle piene (`ExamService.complete_attempt`). Rinunciare è quindi **andare
avanti**: un indirizzo (`?at=`), non una colonna — e l'ADR-042 resta com'è.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .models import ExamAttempt, ExamChallenge, ExamChallengeResult

#: Il valore di ``?at=`` che porta al riepilogo con i due pulsanti dell'esito.
OUTCOME = "esito"


class StepState(str, Enum):
    DONE = "done"  # ha almeno una prova scritta, e il fuoco è altrove
    NOW = "now"
    TODO = "todo"


def _is_recorded(result: ExamChallengeResult) -> bool:
    return result.score is not None or result.passed is not None


@dataclass
class SessionStep:
    """Un esercizio della sequenza, con le sue prove in ordine."""

    exam_challenge: ExamChallenge
    slots: List[ExamChallengeResult]
    state: StepState = StepState.TODO

    @property
    def recorded(self) -> List[ExamChallengeResult]:
        return [slot for slot in self.slots if _is_recorded(slot)]

    @property
    def first_empty(self) -> Optional[ExamChallengeResult]:
        return next((slot for slot in self.slots if not _is_recorded(slot)), None)

    @property
    def best(self) -> Optional[ExamChallengeResult]:
        """La prova che conta: la migliore fra quelle scritte."""
        recorded = self.recorded
        if not recorded:
            return None
        ec = self.exam_challenge
        return max(recorded, key=lambda slot: ec.score_of(slot.score, slot.passed))


@dataclass
class SessionFocus:
    steps: List[SessionStep] = field(default_factory=list)
    #: L'esercizio a fuoco; ``None`` = si guarda il riepilogo con l'esito.
    step: Optional[SessionStep] = None
    #: La prova che il tastierino sta per scrivere (o riscrivere).
    slot: Optional[ExamChallengeResult] = None
    #: True se ``slot`` ha già un risultato: lo si sta correggendo.
    correcting: bool = False

    @property
    def next_at(self) -> str:
        """Dove porta «vai avanti» dall'esercizio a fuoco."""
        if self.step is None:
            return OUTCOME
        index = self.steps.index(self.step)
        if index + 1 < len(self.steps):
            return str(self.steps[index + 1].exam_challenge.id)
        return OUTCOME

    @property
    def last_recorded(self) -> Optional[ExamChallengeResult]:
        """L'ultima prova scritta dell'esercizio a fuoco: quella da correggere."""
        if self.step is None:
            return None
        recorded = self.step.recorded
        return recorded[-1] if recorded else None


def build_focus(
    attempt: ExamAttempt,
    at: Optional[str] = None,
    attempt_number: Optional[int] = None,
) -> SessionFocus:
    """L'esercizio a fuoco e la prova da scrivere.

    ``at`` è l'id di un ``ExamChallenge`` oppure ``"esito"``; assente o ignoto,
    si riparte dall'**ultimo esercizio che ha un risultato**: se ha ancora
    prove libere è lui, altrimenti il successivo, e finiti gli esercizi resta il
    riepilogo. Partire dal primo con una casella vuota riporterebbe indietro,
    a ogni ricarica, su una prova a cui si è rinunciato.

    ``attempt_number`` sceglie una prova precisa dell'esercizio a fuoco, per
    correggerla.
    """
    steps = [
        SessionStep(exam_challenge=ec, slots=slots)
        for ec, slots in attempt.results_by_challenge()
    ]
    focus = SessionFocus(steps=steps)
    if not steps:
        return focus

    current: Optional[SessionStep] = None
    if at == OUTCOME:
        current = None
    else:
        by_id = {str(step.exam_challenge.id): step for step in steps}
        current = by_id.get(at or "")
        if current is None:
            touched = [i for i, step in enumerate(steps) if step.recorded]
            start = touched[-1] if touched else 0
            current = next(
                (step for step in steps[start:] if step.first_empty is not None),
                None,
            )

    for step in steps:
        if step is current:
            step.state = StepState.NOW
        elif step.recorded:
            step.state = StepState.DONE

    focus.step = current
    if current is None:
        return focus

    chosen = next(
        (slot for slot in current.slots if slot.attempt_number == attempt_number),
        None,
    )
    if chosen is not None:
        focus.slot = chosen
    else:
        # Niente prove libere: si è tornati su un esercizio finito, e l'unica
        # cosa sensata da offrire è correggere l'ultima.
        focus.slot = current.first_empty or current.slots[-1]
    focus.correcting = _is_recorded(focus.slot)
    return focus
