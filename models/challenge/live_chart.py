"""Il grafico dal vivo della cornice di esecuzione: solo geometria.

Due disegni, uno per ciascun modo di contare:

* **a barre** — una barra per prova, i posti ancora vuoti, e una linea
  tratteggiata di confronto con se stessi (la propria media). È il disegno
  della modalità a punteggio, dove ogni prova è un numero a sé;
* **a corsa** — la somma che sale colpo dopo colpo contro il proprio passo
  solito. È il disegno delle prove fatte di colpi (fase 5b e 5c).

Qui non c'è né HTML né colore: escono coordinate in un viewBox fisso, e il
template (``challenge/_run_chart.html``) le veste coi token 7c. Il viewBox
**non** è stirato — a differenza di ``PlayerHistoryService.trend_chart`` — perché
qui dentro ci sono cerchi e barre arrotondate, e un ``preserveAspectRatio="none"``
li deformerebbe: l'SVG si allarga tutto insieme, proporzioni comprese.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

#: Il viewBox, in unità sue. Le stesse misure del disegno sul canvas.
WIDTH = 330
HEIGHT = 74
_X0, _X1 = 8, WIDTH - 8
_TOP = 8
#: Mai meno di sei posti, e sempre due oltre l'ultima prova: i posti vuoti
#: dicono che la serata non è finita.
MIN_SLOTS = 6
SPARE_SLOTS = 2
#: Una prova da zero punti lascia comunque un segno: senza, sembra un posto vuoto.
_STUB = 3


@dataclass(frozen=True)
class Slot:
    """Un posto del grafico a barre: pieno (una prova) o ancora da fare."""

    x: float
    y: float
    width: float
    height: float
    filled: bool
    now: bool
    value: Optional[int] = None


@dataclass(frozen=True)
class BarsChart:
    slots: List[Slot]
    baseline: float
    plot_height: float
    reference_y: Optional[float] = None
    reference_label: Optional[str] = None
    width: int = WIDTH
    height: int = HEIGHT
    x0: int = _X0
    x1: int = _X1


def bars_chart(
    values: Sequence[int],
    *,
    top: Optional[int],
    reference: Optional[float] = None,
    reference_label: Optional[str] = None,
    height: int = HEIGHT,
) -> BarsChart:
    """Una barra per prova, in ordine di tempo, l'ultima accesa.

    ``top`` è il fondoscala: il massimo dell'esercizio quando c'è. Senza, vale
    il più alto fra ciò che si disegna — confronto compreso, o la linea della
    media uscirebbe dal riquadro.
    """
    baseline = height - 12
    plot_height = baseline - _TOP
    fondo = top or max([*values, reference or 0, 1])

    def _quota(valore: float) -> float:
        return min(max(valore / fondo, 0), 1) * plot_height

    totale = max(MIN_SLOTS, len(values) + SPARE_SLOTS)
    passo = (_X1 - _X0) / totale
    larghezza = round(passo * 0.62, 2)

    slots: List[Slot] = []
    for indice in range(totale):
        x = round(_X0 + passo * indice + (passo - larghezza) / 2, 2)
        if indice < len(values):
            alta = max(round(_quota(values[indice]), 2), _STUB)
            slots.append(
                Slot(
                    x=x,
                    y=round(baseline - alta, 2),
                    width=larghezza,
                    height=alta,
                    filled=True,
                    now=indice == len(values) - 1,
                    value=values[indice],
                )
            )
        else:
            slots.append(
                Slot(
                    x=x,
                    y=baseline - _STUB,
                    width=larghezza,
                    height=_STUB,
                    filled=False,
                    now=False,
                )
            )

    return BarsChart(
        slots=slots,
        baseline=baseline,
        plot_height=plot_height,
        reference_y=(
            None if reference is None else round(baseline - _quota(reference), 2)
        ),
        reference_label=reference_label,
        height=height,
    )


__all__ = ["BarsChart", "Slot", "bars_chart", "WIDTH", "HEIGHT"]
