"""La seduta in corso: che cosa si vede mentre si segna (ADR-067).

Sola lettura, come `models/exam/session_view.py`, di cui questa è la sorella:
una voce per volta, la striscia di dove siamo, e in basso i comandi. Chi
registra è `TrainingSessionService`.

La sola decisione vera di questo modulo è **quali comandi servono a una voce**,
e discende dalla misura e dal «quanto farne»:

* fino a dieci, una fila di tasti: «quanti su 5?» si risponde con un tocco, ed
  è il gesto del foglio di carta;
* oltre dieci, tiro per tiro — trenta tiri non si contano a mente — con la
  possibilità di scrivere il totale se si è contato da sé;
* col punteggio, il tastierino meno · cifra · più e «Registra la prova»,
  tante volte quante prove dice la voce (ADR-072): la casella è
  l'aggregazione. Se l'esercizio si registra colpo per colpo, si va nella
  schermata del catalogo e la prova torna qui;
* coi minuti, il tastierino e basta;
* con «fatto», due tasti.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from flask_babel import gettext as _

from .measure import SheetMeasure, amount_label, value_label
from .models import TrainingEntry, TrainingSession, TrainingSheet, TrainingSheetItem

#: Fin dove una fila di tasti resta una fila di tasti. Oltre, i bersagli
#: diventano troppo piccoli per un dito e si conta tiro per tiro.
MAX_BUTTONS = 10


@dataclass(frozen=True)
class Cell:
    """Una casella da segnare: la voce, il lato, e com'è adesso."""

    item: TrainingSheetItem
    variant_id: Optional[int]
    side: str
    entry: Optional[TrainingEntry]
    last_time: Optional[int]

    @property
    def value(self) -> Optional[int]:
        return self.entry.value if self.entry else None

    @property
    def done(self) -> Optional[bool]:
        return self.entry.done if self.entry else None

    @property
    def marks(self) -> str:
        return (self.entry.marks or "") if self.entry else ""

    @property
    def shots_done(self) -> int:
        return len(self.marks)

    @property
    def is_filled(self) -> bool:
        return bool(self.entry and self.entry.is_filled)

    @property
    def value_label(self) -> str:
        return value_label(self.value)

    @property
    def last_time_label(self) -> str:
        return value_label(self.last_time)

    # ── Le prove dietro la casella (ADR-072) ──
    @property
    def attempts(self) -> List:
        """Le prove chiuse, in ordine: sono le «prove di stasera» della voce."""
        return self.entry.completed_attempts if self.entry else []

    @property
    def attempts_done(self) -> int:
        return len(self.attempts)

    @property
    def is_full(self) -> bool:
        """Se le prove sono tutte fatte: tante quante ne dice la voce."""
        tetto = self.item.amount
        return tetto is not None and self.attempts_done >= tetto


@dataclass(frozen=True)
class Step:
    """Una voce nella striscia: dove siamo, e cosa c'è già scritto."""

    item: TrainingSheetItem
    index: int
    done: bool
    label: str


@dataclass(frozen=True)
class SessionView:
    session: TrainingSession
    sheet: TrainingSheet
    steps: List[Step]
    item: Optional[TrainingSheetItem]
    index: int
    cells: List[Cell]
    dock: str
    total: int
    max_total: int
    threshold: Optional[int]

    @property
    def is_first(self) -> bool:
        return self.index <= 0

    @property
    def is_last(self) -> bool:
        return self.index >= len(self.steps) - 1

    @property
    def measure(self) -> SheetMeasure:
        return self.item.measure_kind if self.item else SheetMeasure.MADE

    @property
    def dose(self) -> str:
        """«5 tiri», «10 minuti» — o niente col punteggio."""
        if self.item is None or self.item.amount is None:
            return ""
        return amount_label(self.measure, self.item.amount)

    @property
    def buttons(self) -> Sequence[int]:
        """I numeri della fila di tasti, zero compreso."""
        if self.dock != "buttons" or self.item is None or self.item.amount is None:
            return ()
        return range(0, self.item.amount + 1)

    @property
    def aggregation_label(self) -> str:
        """«media», «massimo»: come le prove fanno il numero, col punteggio."""
        kind = self.item.aggregation_kind if self.item else None
        return str(kind.label).lower() if kind else ""

    @property
    def max_score(self) -> Optional[int]:
        """Il massimo di ogni prova a punteggio: lo dice l'esercizio."""
        if self.item is None or self.item.challenge is None:
            return None
        return self.item.challenge.max_score

    @property
    def progress_pct(self) -> int:
        """Quanto della scheda è già fatto, per la barra. Zero se non fa totale."""
        if not self.max_total:
            return 0
        return min(100, round(self.total * 100 / self.max_total))

    @property
    def threshold_label(self) -> str:
        if self.threshold is None:
            return ""
        return _("soglia %(n)s su %(tot)s", n=self.threshold, tot=self.max_total)


def build_run(session: TrainingSession, at: Optional[int] = None) -> SessionView:
    """La seduta come si vede adesso. ``at`` è la voce a fuoco, per posizione.

    Senza ``at`` si va alla **prima casella vuota**: chi riapre la seduta
    riprende da dove aveva smesso, e non deve ricordarselo.
    """
    sheet = session.sheet
    voci = sheet.items_for_day(session.day)
    caselle_per_voce = {voce.id: _celle(session, voce, {}) for voce in voci}
    steps = [
        Step(
            item=voce,
            index=posizione,
            done=all(c.is_filled for c in caselle_per_voce[voce.id]),
            label=voce.challenge.get_display_name(),
        )
        for posizione, voce in enumerate(voci)
    ]

    indice = at if at is not None else _prima_vuota(steps)
    if voci:
        indice = max(0, min(indice, len(voci) - 1))
    else:
        indice = 0
    voce = voci[indice] if voci else None

    ultime = _ultima_volta(session, voce) if voce is not None else {}
    celle = _celle(session, voce, ultime) if voce is not None else []

    return SessionView(
        session=session,
        sheet=sheet,
        steps=steps,
        item=voce,
        index=indice,
        cells=celle,
        dock=_dock(voce),
        total=session.total,
        max_total=sheet.total_for_day(session.day),
        threshold=sheet.threshold,
    )


def _prima_vuota(steps: Sequence[Step]) -> int:
    for step in steps:
        if not step.done:
            return step.index
    return len(steps) - 1 if steps else 0


def _dock(item: Optional[TrainingSheetItem]) -> str:
    """Quali comandi servono a questa voce."""
    if item is None:
        return "none"
    from ..challenge.recording import RecordingMode

    misura = item.measure_kind
    if misura is SheetMeasure.DONE:
        return "done"
    if misura is SheetMeasure.SCORE and item.makes_attempts:
        # N prove (ADR-072): il tastierino tante volte, o la schermata del
        # catalogo se l'esercizio si registra colpo per colpo.
        a_colpi = RecordingMode.parse(item.challenge.recording_mode).is_sequence
        return "launch" if a_colpi else "scores"
    if misura is SheetMeasure.SCORE or misura is SheetMeasure.MINUTES:
        return "pad"
    if item.amount is not None and item.amount <= MAX_BUTTONS:
        return "buttons"
    return "counter"


def _celle(
    session: TrainingSession,
    item: Optional[TrainingSheetItem],
    ultime: Dict[Optional[int], Optional[int]],
) -> List[Cell]:
    """Una casella, o una per variante quando la voce le segna separate."""
    if item is None:
        return []
    per_chiave = {
        entry.variant_id: entry for entry in session.entries if entry.item_id == item.id
    }
    varianti: List[Tuple[Optional[int], str]] = [
        (variante.id, variante.label) for variante in item.variants
    ] or [(None, "")]
    return [
        Cell(
            item=item,
            variant_id=variant_id,
            side=etichetta,
            entry=per_chiave.get(variant_id),
            last_time=ultime.get(variant_id),
        )
        for variant_id, etichetta in varianti
    ]


def _ultima_volta(
    session: TrainingSession, item: TrainingSheetItem
) -> Dict[Optional[int], Optional[int]]:
    """Quanto si era fatto su questa voce la volta precedente, per lato.

    Serve a dare un riferimento mentre si tira, ed è il numero che sul foglio
    di carta si legge nella riga sopra. Si guarda la seduta **chiusa** più
    recente: una aperta non è una volta precedente, è questa.
    """
    precedente = (
        TrainingSession.query.filter(
            TrainingSession.sheet_id == session.sheet_id,
            TrainingSession.user_id == session.user_id,
            TrainingSession.id != session.id,
            TrainingSession.ended_at.isnot(None),
        )
        .order_by(TrainingSession.ended_at.desc())
        .first()
    )
    if precedente is None:
        return {}
    return {
        entry.variant_id: entry.value
        for entry in precedente.entries
        if entry.item_id == item.id
    }


__all__ = ["SessionView", "Cell", "Step", "build_run", "MAX_BUTTONS"]
