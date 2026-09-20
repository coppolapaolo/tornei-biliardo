"""La scena del builder: cosa si accetta come «disegno di un drill».

Il builder serializza il tavolo in JSON — ``{v, title, orient, cloth,
ballScale, items}`` — e quel JSON arriva dal browser, cioe' da un posto dove
chiunque puo' scrivere qualunque cosa. Senza un filtro finirebbe in colonna
tale e quale: un blob da megabyte, o un oggetto che al momento di riaprire il
builder lo fa esplodere sull'utente successivo, che magari non e' nemmeno chi
l'ha caricato.

Qui non si valida il **disegno** (dove stanno le bilie, se il tiro ha senso):
quello e' mestiere del builder, e sindacarlo da server vorrebbe dire
riscriverne le regole in un secondo posto destinato a divergere. Si valida che
sia una scena: JSON, oggetto, di una versione che sappiamo leggere, con una
lista di elementi, di dimensione ragionevole.

Le chiavi sconosciute **si tengono**. Il builder e' un file che cambia, e
scartare cio' che oggi non riconosciamo significherebbe che un drill salvato
domani perde pezzi riaprendolo — silenziosamente, che e' il modo peggiore.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..exceptions import ValidationError

#: Le versioni di scena che sappiamo riaprire. Il builder allegato emette la 4;
#: le precedenti non sono mai arrivate in produzione, quindi non c'e' niente da
#: convertire — se un giorno servira', il posto e' questo.
SUPPORTED_VERSIONS = (4,)

#: Tetto alla dimensione della scena. Un drill fitto di bilie e traiettorie sta
#: sotto le poche decine di KB: mezzo megabyte e' larghissimo per l'uso vero e
#: stretto abbastanza da non far diventare la colonna un deposito.
MAX_SCENE_BYTES = 512 * 1024


def parse_scene(raw: Optional[str]) -> Optional[str]:
    """Convalida la scena e la restituisce normalizzata, o ``None``.

    ``None`` e stringa vuota passano senza errore e significano «questo drill
    non ha un disegno»: e' il caso di ogni drill nato da una foto, cioe' la
    maggioranza. Non e' un dato mancante da segnalare.

    Raises:
        ValidationError: la scena c'e' ma non e' leggibile come tale.
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None

    if len(raw.encode("utf-8")) > MAX_SCENE_BYTES:
        raise ValidationError("Il disegno del drill è troppo grande")

    try:
        scene: Any = json.loads(raw)
    except (ValueError, TypeError):
        raise ValidationError("Il disegno del drill non è leggibile")

    if not isinstance(scene, dict):
        raise ValidationError("Il disegno del drill non è una scena valida")

    version = scene.get("v")
    if version not in SUPPORTED_VERSIONS:
        raise ValidationError(
            "Questo disegno viene da una versione del builder che non so leggere"
        )

    if not isinstance(scene.get("items"), list):
        raise ValidationError("Il disegno del drill non contiene elementi")

    # Il bersaglio è l'unica voce della scena che il server legge come dato
    # (ADR-066): tutto il resto è disegno, e resta affare del disegnatore.
    from .target import validate_targets

    validate_targets(scene["items"])

    # Riserializzata compatta: la colonna non deve pagare l'indentazione che il
    # builder usa nel file scaricato, e cosi' due salvataggi identici danno la
    # stessa stringa invece di due che differiscono per spazi.
    return json.dumps(scene, separators=(",", ":"), ensure_ascii=False)


__all__ = ["parse_scene", "SUPPORTED_VERSIONS", "MAX_SCENE_BYTES"]
