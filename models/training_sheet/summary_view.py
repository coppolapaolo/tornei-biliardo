"""Fine seduta: com'è andata, confrontata con la volta prima (ADR-067).

La stessa forma di `models/challenge/summary_view.py`: una pagina che si
riapre, e che dice tre cose — il totale, voce per voce com'è cambiato, e se il
gradino è superato.

Il confronto è col **prima**: includere la seduta appena chiusa nel record
direbbe «il tuo meglio» a ogni seduta migliore di niente.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from flask_babel import gettext as _

from .measure import SheetMeasure
from .models import TrainingSession, TrainingSheet
from .session_service import TrainingSessionService


@dataclass(frozen=True)
class Row:
    """Una casella nel riepilogo: quanto oggi, quanto la volta prima."""

    label: str
    side: str
    value: Optional[int]
    previous: Optional[int]
    measure: SheetMeasure
    done: Optional[bool]

    @property
    def tone(self) -> str:
        """Verde se è migliorata, rosso se è peggiorata, niente se è uguale."""
        if self.value is None or self.previous is None:
            return ""
        if self.value > self.previous:
            return "ok"
        if self.value < self.previous:
            return "err"
        return ""

    @property
    def value_label(self) -> str:
        if self.measure is SheetMeasure.DONE:
            return _("fatto") if self.done else _("no")
        return "–" if self.value is None else str(self.value)


@dataclass(frozen=True)
class SessionSummary:
    session: TrainingSession
    sheet: TrainingSheet
    rows: List[Row]
    total: int
    max_total: int
    threshold: Optional[int]
    streak: int
    previous_best: Optional[int]
    minutes: Optional[int]

    @property
    def counts(self) -> bool:
        """Se questa seduta ha un totale da confrontare con qualcosa."""
        return self.max_total > 0

    @property
    def above(self) -> bool:
        return self.threshold is not None and self.total >= self.threshold

    @property
    def is_best(self) -> bool:
        return self.counts and (
            self.previous_best is None or self.total > self.previous_best
        )

    @property
    def step_reached(self) -> bool:
        """Se la soglia è stata tenuta per quante sedute la scheda chiede.

        Il passaggio di livello non lo sancisce nessuno, per ora: qui si dice
        che si può chiedere. Chi conferma arriva con gli istruttori.
        """
        return (
            self.above
            and self.sheet.level is not None
            and self.streak >= (self.sheet.threshold_streak or 1)
        )


def build_summary(session: TrainingSession) -> SessionSummary:
    """Il riepilogo di una seduta. Vale anche su una seduta ancora aperta."""
    sheet = session.sheet
    precedente = _precedente(session)
    prima = (
        {(e.item_id, e.variant_id): e for e in precedente.entries} if precedente else {}
    )

    righe: List[Row] = []
    for entry in sorted(
        session.entries,
        key=lambda e: ((e.item.position if e.item else 0), e.variant_id or 0),
    ):
        voce = entry.item
        variante = entry.variant
        vecchia = prima.get((entry.item_id, entry.variant_id))
        righe.append(
            Row(
                label=(
                    voce.challenge.get_display_name()
                    if voce and voce.challenge
                    else _("Voce")
                ),
                side=variante.label if variante else "",
                value=entry.value,
                previous=vecchia.value if vecchia else None,
                measure=entry.measure_kind,
                done=entry.done,
            )
        )

    chiuse = [
        s
        for s in TrainingSessionService.closed_sessions(sheet.id, session.user_id)
        if s.id != session.id
    ]

    return SessionSummary(
        session=session,
        sheet=sheet,
        rows=righe,
        total=session.total,
        max_total=session.max_total or sheet.total_for_day(session.day),
        threshold=sheet.threshold,
        streak=TrainingSessionService.above_threshold_streak(sheet, session.user_id),
        previous_best=max((s.total for s in chiuse), default=None),
        minutes=_minuti(session),
    )


def _precedente(session: TrainingSession) -> Optional[TrainingSession]:
    return (
        TrainingSession.query.filter(
            TrainingSession.sheet_id == session.sheet_id,
            TrainingSession.user_id == session.user_id,
            TrainingSession.id != session.id,
            TrainingSession.ended_at.isnot(None),
        )
        .order_by(TrainingSession.ended_at.desc())
        .first()
    )


def _minuti(session: TrainingSession) -> Optional[int]:
    """Quanto è durata. Niente se è aperta o se è durata meno di un minuto."""
    if session.ended_at is None or session.started_at is None:
        return None
    minuti = round((session.ended_at - session.started_at).total_seconds() / 60)
    return minuti if minuti >= 1 else None


__all__ = ["SessionSummary", "Row", "build_summary"]
