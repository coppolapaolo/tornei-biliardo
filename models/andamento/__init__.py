"""L'andamento dell'allenamento: dove sei forte, dove no, e se stai salendo.

Un pacchetto suo perché legge **due mondi** — le prove del catalogo e le
caselle delle schede — e non può stare dentro nessuno dei due senza importare
l'altro (ADR-068).
"""

from .radar import RadarShape, build_radar
from .view import (
    MIN_OSSERVAZIONI,
    SOGLIA_CRESCITA,
    SOGLIA_SOLIDO,
    Andamento,
    AxisRow,
    Periodo,
    build_andamento,
)

__all__ = [
    "Andamento",
    "AxisRow",
    "Periodo",
    "RadarShape",
    "build_andamento",
    "build_radar",
    "MIN_OSSERVAZIONI",
    "SOGLIA_CRESCITA",
    "SOGLIA_SOLIDO",
]
