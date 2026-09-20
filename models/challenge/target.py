"""Il bersaglio di un esercizio, come dato (D14, ADR-066).

Vive **dentro la scena** del disegnatore, come una voce `{"type": "target"}`:
il disegno è l'unica fonte di ciò che sta sul tavolo, e un bersaglio tenuto in
una colonna a parte si potrebbe spostare senza che il disegno lo sappia.

Le coordinate sono quelle del disegnatore: **1 diamante = 100 unità**, il panno
è 800 × 400 con l'origine nell'angolo in alto a sinistra del tavolo disteso in
orizzontale. L'orientamento della scena è solo un modo di mostrarla.

Gli anelli hanno tutti lo stesso spessore, `step`, in multipli di un quarto di
diamante — le stesse frazioni della griglia. `values` va dal centro verso
l'esterno.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from models.exceptions import ValidationError

TABLE_LENGTH = 800
TABLE_WIDTH = 400
#: Un quarto di diamante: la frazione più fine che il disegnatore sa agganciare.
QUARTER = 25
MAX_RINGS = 5
MAX_RING_VALUE = 99
TARGET_TYPE = "target"


@dataclass(frozen=True)
class Target:
    x: float
    y: float
    step: int
    values: Tuple[int, ...]

    @property
    def outer_radius(self) -> int:
        return self.step * len(self.values)

    @property
    def max_points(self) -> int:
        return max(self.values)

    def distance(self, x: float, y: float) -> float:
        return math.hypot(x - self.x, y - self.y)

    def points_at(self, x: float, y: float) -> int:
        """I punti dell'anello in cui cade il punto; zero fuori dall'ultimo.

        Sul confine fra due anelli vale quello **esterno**: `floor` manda la
        distanza esatta di un anello nell'anello dopo. La battente che tocca la
        riga non è dentro.
        """
        anello = int(self.distance(x, y) // self.step)
        return self.values[anello] if anello < len(self.values) else 0

    def closeness(self, x: float, y: float) -> float:
        """Quanto vicino al centro, da 1 (sul centro) a 0 (sull'orlo o fuori)."""
        return max(0.0, 1 - self.distance(x, y) / self.outer_radius)


def on_cloth(x: Any, y: Any) -> bool:
    """Il punto sta sul panno? Vale per il bersaglio e per dove si ferma la bianca."""
    return (
        _is_number(x)
        and _is_number(y)
        and 0 <= x <= TABLE_LENGTH
        and 0 <= y <= TABLE_WIDTH
    )


def _is_number(valore: Any) -> bool:
    return isinstance(valore, (int, float)) and not isinstance(valore, bool)


def validate_targets(items: list) -> None:
    """Chiamata da ``parse_scene``: una scena con un bersaglio storto non si salva.

    Un bersaglio solo per scena: la «Posizione» di una prova è la distanza da
    **un** centro. Più bersagli vorrebbero dire sapere a quale mirava ogni
    colpo, che è un'altra domanda.
    """
    bersagli = [
        voce
        for voce in items
        if isinstance(voce, dict) and voce.get("type") == TARGET_TYPE
    ]
    if len(bersagli) > 1:
        raise ValidationError("Il disegno può avere un bersaglio solo")
    for voce in bersagli:
        _build(voce)


def _build(voce: dict) -> Target:
    x, y, step, values = (voce.get(k) for k in ("x", "y", "step", "values"))
    if not on_cloth(x, y):
        raise ValidationError("Il centro del bersaglio deve stare sul panno")
    if not isinstance(step, int) or isinstance(step, bool) or step < QUARTER:
        raise ValidationError("Lo spessore degli anelli parte da un quarto di diamante")
    if step % QUARTER:
        raise ValidationError(
            "Lo spessore degli anelli si misura in quarti di diamante"
        )
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_RINGS:
        raise ValidationError(f"Il bersaglio ha da uno a {MAX_RINGS} anelli")
    for valore in values:
        if (
            not isinstance(valore, int)
            or isinstance(valore, bool)
            or not 0 <= valore <= MAX_RING_VALUE
        ):
            raise ValidationError(
                f"Ogni anello vale un numero intero da 0 a {MAX_RING_VALUE}"
            )
    if max(values) == 0:
        raise ValidationError("Almeno un anello deve valere dei punti")
    return Target(x=x, y=y, step=step, values=tuple(values))


def target_from_scene(raw_scene: Optional[str]) -> Optional[Target]:
    """Il bersaglio dell'esercizio, o ``None`` se il disegno non ne ha.

    Tollerante in lettura: una scena illeggibile o un bersaglio storto danno
    ``None``, non un'eccezione. Il rifiuto sta al salvataggio
    (``validate_targets``); qui si legge ciò che c'è, e chi esegue un esercizio
    non deve trovarsi un 500 per un dato scritto male mesi prima.
    """
    if not raw_scene:
        return None
    try:
        scena = json.loads(raw_scene)
        voci = scena.get("items") if isinstance(scena, dict) else None
        for voce in voci or []:
            if isinstance(voce, dict) and voce.get("type") == TARGET_TYPE:
                return _build(voce)
    except (ValueError, TypeError, ValidationError):
        return None
    return None


__all__ = [
    "Target",
    "target_from_scene",
    "validate_targets",
    "on_cloth",
    "TABLE_LENGTH",
    "TABLE_WIDTH",
    "QUARTER",
    "MAX_RINGS",
]
