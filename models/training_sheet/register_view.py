"""Il registro di una scheda: le sedute fatte, e cosa dicono (ADR-067).

Sul foglio di carta il registro **è** l'andamento: una riga per seduta, e
guardando la colonna si vede se quell'esercizio sta salendo. Qui è la stessa
cosa, detta in tre modi — i tre numeri in cima, la riga di ogni voce con le
ultime volte, e l'elenco delle sedute.

Le poche frasi che accompagnano una voce («in crescita», «a sinistra sei
indietro») sono osservazioni, non diagnosi, e tacciono quando non hanno di che
parlare: sotto tre sedute non si dice niente, e una differenza fra i due lati
si nomina solo quando è grande abbastanza da non essere rumore.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from flask_babel import gettext as _

from .measure import SheetMeasure, value_label
from .models import TrainingSession, TrainingSheet
from .session_service import TrainingSessionService

#: Quante sedute si mostrano nella riga di una voce, e su quante si fa la media.
ULTIME = 3
#: Sotto questo numero di sedute non si dice se una voce sale o scende: due
#: punti sono una retta, e una retta non è una tendenza.
MIN_PER_TENDENZA = 3
#: Di quanto devono discostarsi le medie dei due lati perché valga la pena
#: dirlo. Sotto, è rumore: un tiro di differenza lo fa il caso.
SCARTO_LATI = 1.0


@dataclass(frozen=True)
class ItemRow:
    """Una voce nel registro: le ultime volte, e cosa se ne può dire."""

    label: str
    measure: SheetMeasure
    values: List[Optional[int]]
    note: str
    tone: str

    @property
    def recent_label(self) -> str:
        """«9 · 9 · 10», dalla più vecchia alla più recente."""
        return " · ".join(value_label(v) for v in self.values)


@dataclass(frozen=True)
class SessionRow:
    session: TrainingSession
    filled: int
    slots: int
    minutes: Optional[int]
    total: int
    max_total: int
    above: bool


@dataclass(frozen=True)
class Register:
    sheet: TrainingSheet
    sessions: List[SessionRow]
    items: List[ItemRow]
    last_total: Optional[int]
    last_max: Optional[int]
    average: Optional[float]
    above_count: int

    @property
    def is_empty(self) -> bool:
        return not self.sessions

    @property
    def counts(self) -> bool:
        """Se la scheda ha un totale di cui parlare."""
        return bool(self.sheet.total)

    @property
    def average_label(self) -> str:
        if self.average is None:
            return "–"
        # Una cifra dopo la virgola: la media di tre sedute non merita di più,
        # e nella lingua di chi legge la virgola non è un punto.
        return ("%.1f" % self.average).replace(".", ",")


def build_register(sheet: TrainingSheet, user_id: int, limit: int = 20) -> Register:
    """Il registro della scheda per questo giocatore, dalle sedute chiuse."""
    sedute = TrainingSessionService.closed_sessions(sheet.id, user_id, limit=limit)
    righe_sedute = [_riga_seduta(sheet, seduta) for seduta in sedute]

    ultime = list(reversed(sedute[:ULTIME]))  # dalla più vecchia alla più recente
    totali = [s.total for s in sedute if s.max_total]

    return Register(
        sheet=sheet,
        sessions=righe_sedute,
        items=_righe_voci(sheet, sedute, ultime),
        last_total=sedute[0].total if sedute else None,
        last_max=sedute[0].max_total if sedute else None,
        average=(sum(totali[:ULTIME]) / len(totali[:ULTIME])) if totali else None,
        above_count=(
            sum(
                1
                for s in sedute
                if sheet.threshold is not None and s.total >= sheet.threshold
            )
            if sheet.threshold is not None
            else 0
        ),
    )


def _riga_seduta(sheet: TrainingSheet, seduta: TrainingSession) -> SessionRow:
    compilate = sum(1 for entry in seduta.entries if entry.is_filled)
    caselle = sum(voce.slots for voce in sheet.items_for_day(seduta.day))
    minuti = None
    if seduta.ended_at and seduta.started_at:
        quanti = round((seduta.ended_at - seduta.started_at).total_seconds() / 60)
        minuti = quanti if quanti >= 1 else None
    return SessionRow(
        session=seduta,
        filled=compilate,
        slots=caselle,
        minutes=minuti,
        total=seduta.total,
        max_total=seduta.max_total,
        above=sheet.threshold is not None and seduta.total >= sheet.threshold,
    )


def _righe_voci(
    sheet: TrainingSheet,
    tutte: Sequence[TrainingSession],
    ultime: Sequence[TrainingSession],
) -> List[ItemRow]:
    """Una riga per voce attiva: le ultime volte, e l'osservazione.

    Le voci **ritirate** non compaiono: il registro racconta la scheda di oggi.
    I loro numeri restano nelle sedute in cui erano state segnate.
    """
    righe: List[ItemRow] = []
    for voce in sheet.active_items:
        per_seduta = [_somma_voce(seduta, voce.id) for seduta in ultime]
        medie = _medie_per_lato(tutte, voce)
        nota, tono = _nota_e_tono(voce, per_seduta, medie)
        righe.append(
            ItemRow(
                label=voce.challenge.get_display_name(),
                measure=voce.measure_kind,
                values=per_seduta,
                note=nota,
                tone=tono,
            )
        )
    return righe


def _somma_voce(seduta: TrainingSession, item_id: int) -> Optional[int]:
    """Quanto vale questa voce in questa seduta: i lati sommati.

    ``None`` se in quella seduta non era stata segnata — che è diverso da zero,
    e nella riga si legge «–».
    """
    valori = [
        entry.value
        for entry in seduta.entries
        if entry.item_id == item_id and entry.value is not None
    ]
    return sum(valori) if valori else None


def _medie_per_lato(
    sedute: Sequence[TrainingSession], voce
) -> Dict[Optional[int], Tuple[float, str]]:
    """La media di ogni lato sulle sedute date, con l'etichetta del lato."""
    raccolta: Dict[Optional[int], List[int]] = {}
    etichette: Dict[Optional[int], str] = {}
    for variante in voce.variants:
        etichette[variante.id] = variante.label
    for seduta in sedute:
        for entry in seduta.entries:
            if entry.item_id != voce.id or entry.value is None:
                continue
            raccolta.setdefault(entry.variant_id, []).append(entry.value)
    return {
        variant_id: (sum(valori) / len(valori), etichette.get(variant_id, ""))
        for variant_id, valori in raccolta.items()
        if valori
    }


def _lati_a_confronto(medie) -> Optional[Tuple[str, float, str, float]]:
    """I due lati più distanti, se la distanza vale la pena di essere detta."""
    con_nome = [(nome, media) for media, nome in medie.values() if nome]
    if len(con_nome) < 2:
        return None
    ordinati = sorted(con_nome, key=lambda x: x[1])
    peggiore, migliore = ordinati[0], ordinati[-1]
    if migliore[1] - peggiore[1] < SCARTO_LATI:
        return None
    return peggiore[0], peggiore[1], migliore[0], migliore[1]


def _numero(valore: float) -> str:
    return ("%.1f" % valore).replace(".", ",")


def _nota_e_tono(voce, valori: Sequence[Optional[int]], medie) -> Tuple[str, str]:
    """Una frase sola e il suo colore, e solo quando c'è qualcosa da dire.

    Insieme e non in due funzioni: il colore discende da **quale** osservazione
    si è fatta, e ricavarlo rileggendo la frase vorrebbe dire confrontare del
    testo tradotto — che in inglese non direbbe più quello che dice qui.

    I due lati vengono prima della tendenza: sapere da che parte si sbaglia è
    più utile che sapere che si sta salendo, ed è la ragione per cui il foglio
    di carta ha due colonne.
    """
    lati = _lati_a_confronto(medie)
    if lati is not None:
        peggiore, media_p, migliore, media_m = lati
        return (
            _(
                "%(lato)s %(n)s di media, %(altro)s %(m)s",
                lato=peggiore,
                n=_numero(media_p),
                altro=migliore,
                m=_numero(media_m),
            ),
            "err",
        )

    pieni = [v for v in valori if v is not None]
    if len(pieni) >= MIN_PER_TENDENZA:
        sale = all(dopo >= prima for prima, dopo in zip(pieni, pieni[1:]))
        scende = all(dopo <= prima for prima, dopo in zip(pieni, pieni[1:]))
        if sale and pieni[-1] > pieni[0]:
            return _("in crescita"), "ok"
        if scende and pieni[-1] < pieni[0]:
            return _("in calo"), "err"
    if not voce.measure_kind.counts_toward_threshold:
        return _("fuori dalla soglia: non è a riusciti"), ""
    return "", ""


__all__ = [
    "Register",
    "ItemRow",
    "SessionRow",
    "build_register",
    "ULTIME",
    "MIN_PER_TENDENZA",
    "SCARTO_LATI",
]
