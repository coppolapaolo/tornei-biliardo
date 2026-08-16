"""Dominio Referto TPA (Total Performance Average).

Il referto TPA e' il modo in cui gli statistici di Accu-Stats registrano una
partita di biliardo americano: non solo chi vince i rack, ma **cosa succede a
ogni visita al tavolo** — quante bilie si imbucano e perche' il turno finisce.
Da quelle annotazioni esce un numero solo, il TPA:

    TPA = bilie imbucate / (bilie imbucate + errori)

Il modulo e' diviso in due meta' che non si toccano:

- ``engine``: il motore, Python puro, senza database e senza Flask. E' la
  traduzione fedele dell'app JS di riferimento (TPA-scorekeeper) ed e' l'unico
  posto dove vivono le regole Accu-Stats.
- ``models`` / ``services``: la persistenza sul match individuale e il ciclo di
  vita del referto.

Vedi ``docs/adr/ADR-044-tpa-scoresheet.md``.
"""

from models.tpa.models import TpaComando, TpaReferto  # noqa: F401
from models.tpa.services import FEATURE_CODE, TpaRefertoService  # noqa: F401
from models.tpa.engine import (  # noqa: F401
    ERROR_KINDS,
    TpaAnnotation,
    TpaButton,
    TpaState,
    TurnState,
    PlayerTally,
    tpa_score,
    total_errors,
)

__all__ = [
    "FEATURE_CODE",
    "TpaComando",
    "TpaReferto",
    "TpaRefertoService",
    "ERROR_KINDS",
    "TpaAnnotation",
    "TpaButton",
    "TpaState",
    "TurnState",
    "PlayerTally",
    "tpa_score",
    "total_errors",
]
