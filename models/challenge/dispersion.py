"""Dove si sbaglia, non quanto: la lettura della nuvola dei punti (fase 5d).

A fine prova il tavolo mostra **tutti** i punti d'arrivo insieme. È
l'informazione che nessun punteggio riassume: si vede a colpo d'occhio se si
sbaglia *sempre dallo stesso lato*, che è una correzione tecnica — mentre «vai
un po' meglio» non è una correzione di niente (#183).

Qui quella figura diventa una frase. Due assi, e vogliono dire due cose
diverse:

* **lungo / corto** — la battente si ferma oltre o prima del centro: è
  **forza**, cioè quanto si è tirato;
* **destra / sinistra** — si ferma di lato: è **mira** (o effetto), cioè dove
  si è tirato.

La frase si dice solo quando lo scarto medio supera una soglia: sotto, la
nuvola è dispersa attorno al centro, e inventarle una direzione sarebbe dare
una correzione a chi non ne ha bisogno.

Il tavolo è quello del disegnatore, disteso in orizzontale: **x** cresce verso
la sponda corta di destra, **y** verso il basso. Le parole del giocatore
(«lungo», «corto») valgono rispetto al **bersaglio**, non al tavolo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from flask_babel import gettext as _

from .target import Target

#: Quanto deve valere lo scarto medio, in frazione del raggio del bersaglio,
#: perché si possa chiamare tendenza. Sotto, è dispersione.
SOGLIA = 0.25


@dataclass(frozen=True)
class Dispersion:
    """La nuvola dei punti d'arrivo, letta."""

    points: List[Tuple[float, float]]
    #: Scarto medio dal centro, in unità del disegnatore. Positivo = verso la
    #: sponda di destra (x) e verso il basso (y).
    bias_x: float
    bias_y: float
    headline: str
    detail: str

    @property
    def count(self) -> int:
        return len(self.points)


def read_dispersion(shots: Iterable, target: Optional[Target]) -> Optional[Dispersion]:
    """La lettura della nuvola, o ``None`` se non c'è niente da leggere.

    Solo i colpi **imbucati** hanno un punto d'arrivo: gli altri non entrano,
    ed è il motivo per cui questa figura non si legge da sola — accanto ci
    vogliono le Imbucate, o mostrerebbe solo i colpi riusciti spacciandoli per
    tutti.
    """
    if target is None:
        return None
    punti = [
        (s.x, s.y) for s in shots if s.made and s.x is not None and s.y is not None
    ]
    if not punti:
        return None

    scarto_x = sum(x for x, _y in punti) / len(punti) - target.x
    scarto_y = sum(y for _x, y in punti) / len(punti) - target.y
    # Due misure, non una: un riquadro lungo e basso è largo il doppio di
    # quanto è alto, e normalizzare entrambi gli scarti sullo stesso numero
    # direbbe «corto» a chi in larghezza è centratissimo. Nei cerchi le due
    # coincidono, quindi per loro non cambia niente.
    lungo = scarto_x / (target.scale_x or 1)
    lato = scarto_y / (target.scale_y or 1)
    titolo, dettaglio = _frase(punti, target, lungo, lato)
    return Dispersion(
        points=punti,
        bias_x=round(scarto_x, 1),
        bias_y=round(scarto_y, 1),
        headline=titolo,
        detail=dettaglio,
    )


def _frase(punti, target: Target, lungo: float, lato: float):
    verso_x = _("lungo") if lungo > 0 else _("corto")
    verso_y = _("a destra") if lato > 0 else _("a sinistra")
    forte_x = abs(lungo) >= SOGLIA
    forte_y = abs(lato) >= SOGLIA

    if not forte_x and not forte_y:
        return (
            _("Sparse attorno al centro"),
            _(
                "Nessuna direzione ricorrente: gli arrivi si distribuiscono "
                "attorno al bersaglio."
            ),
        )

    # Quanti colpi vanno **dalla stessa parte**: è il numero che rende la frase
    # una misura invece di un'impressione.
    if forte_x:
        stessi = sum(1 for x, _y in punti if (x - target.x > 0) == (lungo > 0))
    else:
        stessi = sum(1 for _x, y in punti if (y - target.y > 0) == (lato > 0))

    if forte_x and forte_y:
        titolo = _("Arrivi %(lungo)s, e %(lato)s", lungo=verso_x, lato=verso_y)
        coda = _("è forza e mira insieme.")
    elif forte_x:
        titolo = _("Arrivi %(lungo)s", lungo=verso_x)
        coda = _("è forza, non mira.")
    else:
        titolo = _("Arrivi %(lato)s", lato=verso_y)
        coda = _("è mira, non forza.")

    return titolo, _(
        "%(quanti)s battenti su %(totale)s si sono fermate dalla stessa parte "
        "rispetto al centro: %(coda)s",
        quanti=stessi,
        totale=len(punti),
        coda=coda,
    )


__all__ = ["Dispersion", "read_dispersion", "SOGLIA"]
