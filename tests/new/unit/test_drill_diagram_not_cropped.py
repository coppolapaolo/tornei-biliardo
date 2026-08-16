"""L'immagine di un drill è un diagramma, e un diagramma non si taglia.

La foto di un drill non è decorazione: **è** l'esercizio. Dice dove stanno le
bilie, dov'è la battente, quali buche contano. Ritagliarla per riempire un
riquadro toglie proprio i bordi del tavolo, cioè la parte che dà il senso alle
posizioni — e lo fa in silenzio, perché un tavolo tagliato somiglia a un tavolo.

Il problema stava tutto nel CSS: il ridimensionamento lato server è già corretto
(``img.thumbnail`` preserva le proporzioni, ``utils/image_paths.py``). Erano i
cinque riquadri a chiedere ``object-fit: cover``, che riempie ritagliando.

Le foto reali sono ~800×459 (1.74:1): dentro una miniatura quadrata `cover` ne
buttava via il 43% della larghezza.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

#: Dove si mostra l'immagine di un drill. Aggiungerne uno qui quando nasce una
#: superficie nuova è il modo per non ripetere il ritaglio.
SURFACES = (
    "templates/components/_challenge_bits.html",
    "templates/components/_challenge_management_modal.html",
    "templates/challenge/_challenge_detail.html",
    "templates/challenge/_challenge_card.html",
    "templates/player/challenge_attempt_detail.html",
)

#: Chi produce l'indirizzo di quell'immagine: in Jinja e nel JS del modale.
IMAGE_MARKERS = ("challenge_image_url", "challengeThumb")


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("relative", SURFACES)
def test_the_surface_still_shows_a_drill_image(relative):
    """Guardia della guardia: se la superficie sparisce, il test lo dice."""
    source = _source(relative)
    assert any(marker in source for marker in IMAGE_MARKERS), relative


@pytest.mark.parametrize("relative", SURFACES)
def test_no_drill_image_is_cropped_to_fill(relative):
    """Nessun ``object-fit: cover`` dove si mostra un drill.

    Si guarda il file intero e non il singolo elemento: in queste pagine
    l'unica immagine è quella del drill, quindi un ``cover`` qui è comunque il
    bug — e cercarlo per elemento vorrebbe dire parsare l'HTML per niente.
    """
    source = _source(relative)
    cropping = re.findall(r"object-fit:\s*cover", source)
    assert not cropping, (
        f"{relative}: l'immagine del drill viene ritagliata. "
        "Usa .c7-diagram/.c7-diagram__img (object-fit: contain): il diagramma "
        "va mostrato intero, anche a costo di due bande vuote."
    )


def test_the_shared_macro_uses_the_diagram_frame():
    """La miniatura condivisa si propaga a dodici template: conta doppio."""
    source = _source("templates/components/_challenge_bits.html")
    assert "c7-diagram" in source
    assert "c7-diagram__img" in source


def test_the_frame_is_defined_once_in_the_theme():
    """La regola vive nel tema, non ricopiata in cinque ``style=``.

    Era già ricopiata cinque volte, ed è così che quattro sono rimaste indietro
    la prima volta che qualcuno ha provato a sistemarne una.
    """
    theme = _source("static/css/theme-7c.css")
    assert ".c7-diagram {" in theme
    assert ".c7-diagram__img {" in theme
    assert "object-fit: contain" in theme
