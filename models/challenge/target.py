"""Il bersaglio di un esercizio, come dato (D14, ADR-066).

Vive **dentro la scena** del disegnatore: il disegno è l'unica fonte di ciò che
sta sul tavolo, e un bersaglio tenuto in una colonna a parte si potrebbe
spostare senza che il disegno lo sappia.

Le coordinate sono quelle del disegnatore: **1 diamante = 100 unità**, il panno
è 800 × 400 con l'origine nell'angolo in alto a sinistra del tavolo disteso in
orizzontale. L'orientamento della scena è solo un modo di mostrarla.

**Due forme, una sola domanda a testa** (fase 9b):

* i **cerchi** — voce `{"type": "target"}` — chiedono *quanto vicino*: anelli
  di uguale spessore `step`, in multipli di un quarto di diamante (le stesse
  frazioni della griglia), con `values` dal centro verso l'esterno;
* il **riquadro** — voce `{"type": "zone"}` con un `value` — chiede *dentro o
  fuori*: centro, larghezza e altezza in quarti di diamante, e i punti che vale
  fermarsi dentro.

I riquadri nel disegno possono essere tanti (gli schemi di Billiard University
ne hanno quattro): è **il `value`** a fare di uno di loro il bersaglio, e ce ne
può essere uno solo in tutta la scena — la «Posizione» di una prova è la
distanza da *un* centro. Il riquadro ruotato non ha un campo suo: ruotare di
90° è scambiare larghezza e altezza, e un dato in meno è un dato che non può
contraddire il disegno.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from models.exceptions import ValidationError

TABLE_LENGTH = 800
TABLE_WIDTH = 400
#: Un quarto di diamante: la frazione più fine che il disegnatore sa agganciare.
QUARTER = 25
MAX_RINGS = 5
MAX_RING_VALUE = 99
TARGET_TYPE = "target"
ZONE_TYPE = "zone"

#: Le due forme del bersaglio.
RINGS = "rings"
ZONE = "zone"


@dataclass(frozen=True)
class Target:
    """Il bersaglio, nell'una o nell'altra forma.

    Una classe sola e non due: chi lo usa — il punteggio di un colpo, le due
    percentuali, la lettura della nuvola, il panno che si tocca — fa sempre le
    stesse domande, e con due classi le farebbe due volte. I campi dell'altra
    forma restano a zero, e `shape` dice quale leggere.
    """

    x: float
    y: float
    step: int = 0
    values: Tuple[int, ...] = ()
    shape: str = RINGS
    #: Riquadro: larghezza e altezza intere, in unità del disegnatore.
    w: int = 0
    h: int = 0
    #: Riquadro: quanto vale fermarsi dentro.
    value: int = 0

    @property
    def is_zone(self) -> bool:
        return self.shape == ZONE

    @property
    def graded(self) -> bool:
        """I cerchi misurano *quanto* vicino; il riquadro dice dentro o fuori.

        Serve a chi scrive la parola sopra la percentuale: con un riquadro
        «Posizione» vuol dire «quante volte dentro», ed è un'altra frase.
        """
        return not self.is_zone

    @property
    def outer_radius(self) -> int:
        """Il raggio dei cerchi, o il mezzo lato più lungo del riquadro."""
        if self.is_zone:
            return max(self.w, self.h) // 2
        return self.step * len(self.values)

    @property
    def scale_x(self) -> float:
        """Di quanto si è «fuori» lungo il tavolo, per normalizzare lo scarto.

        Nei cerchi le due misure coincidono; in un riquadro lungo e basso no, e
        usare una misura sola direbbe «corto» a chi è centratissimo in
        larghezza.
        """
        return (self.w / 2) if self.is_zone else float(self.outer_radius)

    @property
    def scale_y(self) -> float:
        return (self.h / 2) if self.is_zone else float(self.outer_radius)

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        """Il rettangolo che lo contiene: serve a inquadrare l'ingrandimento."""
        if self.is_zone:
            return (
                self.x - self.w / 2,
                self.y - self.h / 2,
                self.x + self.w / 2,
                self.y + self.h / 2,
            )
        r = self.outer_radius
        return (self.x - r, self.y - r, self.x + r, self.y + r)

    @property
    def max_points(self) -> int:
        return self.value if self.is_zone else max(self.values)

    def distance(self, x: float, y: float) -> float:
        return math.hypot(x - self.x, y - self.y)

    def contains(self, x: float, y: float) -> bool:
        """Dentro il riquadro? Sul bordo **non** è dentro, come per gli anelli."""
        x0, y0, x1, y1 = self.bounds
        return x0 < x < x1 and y0 < y < y1

    def points_at(self, x: float, y: float) -> int:
        """I punti dell'anello in cui cade il punto; zero fuori dall'ultimo.

        Sul confine fra due anelli vale quello **esterno**: `floor` manda la
        distanza esatta di un anello nell'anello dopo. La battente che tocca la
        riga non è dentro. Nel riquadro la stessa regola, senza gradazione.
        """
        if self.is_zone:
            return self.value if self.contains(x, y) else 0
        anello = int(self.distance(x, y) // self.step)
        return self.values[anello] if anello < len(self.values) else 0

    def closeness(self, x: float, y: float) -> float:
        """Quanto vicino al centro, da 1 (sul centro) a 0 (sull'orlo o fuori).

        Col riquadro non c'è un «quanto»: o dentro o fuori, uno o zero.
        Inventare una gradazione su un rettangolo vorrebbe dire misurare una
        cosa che l'esercizio non chiede.
        """
        if self.is_zone:
            return 1.0 if self.contains(x, y) else 0.0
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


def _scoring_items(items: list) -> List[dict]:
    """Le voci della scena che valgono punti, in una forma o nell'altra.

    Un riquadro **senza** ``value`` è disegno, e il server non lo guarda: gli
    schemi di riferimento ne hanno quattro sul tavolo e uno solo, se tanto,
    conta. Quello che conta è la **presenza** della chiave, non che il valore
    sia buono: togliere i punti a un riquadro vuol dire togliere la chiave, e
    un `value` scritto storto è un bersaglio dichiarato male — si rifiuta, non
    si declassa a disegno in silenzio.
    """
    trovate = []
    for voce in items:
        if not isinstance(voce, dict):
            continue
        if voce.get("type") == TARGET_TYPE:
            trovate.append(voce)
        elif voce.get("type") == ZONE_TYPE and voce.get("value") is not None:
            trovate.append(voce)
    return trovate


def _is_positive_int(valore: Any) -> bool:
    return isinstance(valore, int) and not isinstance(valore, bool) and valore > 0


def validate_targets(items: list) -> None:
    """Chiamata da ``parse_scene``: una scena con un bersaglio storto non si salva.

    Un bersaglio solo per scena: la «Posizione» di una prova è la distanza da
    **un** centro. Più bersagli vorrebbero dire sapere a quale mirava ogni
    colpo, che è un'altra domanda. Vale fra le due forme, non dentro una sola:
    cerchi *e* un riquadro che vale punti sono comunque due bersagli.
    """
    bersagli = _scoring_items(items)
    if len(bersagli) > 1:
        raise ValidationError("Il disegno può avere un bersaglio solo")
    for voce in bersagli:
        _build(voce)


def _build(voce: dict) -> Target:
    if voce.get("type") == ZONE_TYPE:
        return _build_zone(voce)
    return _build_rings(voce)


def _build_rings(voce: dict) -> Target:
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


def _build_zone(voce: dict) -> Target:
    x, y, w, h, value = (voce.get(k) for k in ("x", "y", "w", "h", "value"))
    if not on_cloth(x, y):
        raise ValidationError("Il centro del bersaglio deve stare sul panno")
    for misura, nome in ((w, "larghezza"), (h, "altezza")):
        if not isinstance(misura, int) or isinstance(misura, bool) or misura < QUARTER:
            raise ValidationError(
                f"La {nome} del riquadro parte da un quarto di diamante"
            )
        if misura % QUARTER:
            raise ValidationError(
                f"La {nome} del riquadro si misura in quarti di diamante"
            )
    if w > TABLE_LENGTH or h > TABLE_WIDTH:
        raise ValidationError("Il riquadro non può essere più grande del tavolo")
    if not _is_positive_int(value) or value > MAX_RING_VALUE:
        raise ValidationError(
            f"Il riquadro vale un numero intero da 1 a {MAX_RING_VALUE}"
        )
    return Target(x=x, y=y, shape=ZONE, w=w, h=h, value=value)


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
        for voce in _scoring_items(voci or []):
            return _build(voce)
    except (ValueError, TypeError, ValidationError, AttributeError):
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
    "RINGS",
    "ZONE",
    "TARGET_TYPE",
    "ZONE_TYPE",
]
