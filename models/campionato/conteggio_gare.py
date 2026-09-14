"""Quante gare ha un campionato, con la finale dei playoff tenuta a parte.

SPECIFICHE.md, «Campionati», nota del 2026-09-14: le gare previste
(`Campionato.planned_gare_count`) sono quelle della stagione; la gara di
playoff non è una di queste, è la conclusione. Contarla insieme alle altre
produceva «3 di 2» sulla pagina del direttore e «3 gare» in vetrina.

Chi è una gara di playoff lo dice `Gara.is_playoff` — il collegamento a una
`PlayoffConfiguration` — e nient'altro: né il nome né il numero.

Unica fonte per ogni conteggio mostrato: pagina del direttore, vetrina,
tessere in dashboard, elenchi pubblici.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List


def gare_regolari(gare: Iterable[Any]) -> List[Any]:
    """Le gare della stagione: tutte tranne quelle di playoff."""
    return [g for g in (gare or []) if not g.is_playoff]


def gare_di_playoff(gare: Iterable[Any]) -> List[Any]:
    """Le gare di playoff, cioè le finali."""
    return [g for g in (gare or []) if g.is_playoff]


@dataclass(frozen=True)
class ConteggioGare:
    """Gare regolari e finali, e come dirle a chi legge."""

    regolari: int
    finali: int = 0

    @classmethod
    def da_gare(cls, gare: Iterable[Any]) -> "ConteggioGare":
        elenco = list(gare or [])
        finali = len(gare_di_playoff(elenco))
        return cls(regolari=len(elenco) - finali, finali=finali)

    @property
    def finale_testo(self) -> str:
        """«finale», «2 finali», oppure vuoto se non ce n'è."""
        from flask_babel import gettext as _

        if not self.finali:
            return ""
        if self.finali == 1:
            return _("finale")
        return _("%(n)s finali", n=self.finali)

    @property
    def numero_testo(self) -> str:
        """Il solo numero: «5», oppure «5 + finale»."""
        if not self.finali:
            return str(self.regolari)
        return f"{self.regolari} + {self.finale_testo}"

    @property
    def gare_testo(self) -> str:
        """«5 gare», oppure «5 gare + finale»."""
        from flask_babel import ngettext

        gare = ngettext("%(num)s gara", "%(num)s gare", self.regolari)
        if not self.finali:
            return gare
        return f"{gare} + {self.finale_testo}"
