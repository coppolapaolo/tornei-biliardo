"""Dialog modale mostrata all'apertura della pagina successiva.

Stesso meccanismo di trasporto dei toast di gamification: il messaggio viaggia
in un flash con una categoria dedicata, che `base.html` non renderizza come
alert ma consegna al componente `_page_modal.html`.

Serve dove un alert in cima alla pagina non basta: chi arriva sul sito da un
link esterno (locandina, QR code, post) non conosce la pagina e non sa dove
guardare — vedi il link pubblico di iscrizione, issue #61.
"""

from __future__ import annotations

import json
from typing import Optional

from flask import flash

PAGE_MODAL_CATEGORY = "page_modal"


def flash_page_modal(
    *,
    title: str,
    body: str,
    variant: str = "info",
    icon: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    """Programma una dialog modale sulla prossima pagina renderizzata.

    Args:
        title: titolo della modale.
        body: testo principale.
        variant: colore Bootstrap dell'header (`success`, `warning`, `info`,
            `danger`).
        icon: classe Font Awesome (senza `fas`), es. `fa-check-circle`.
        detail: riga secondaria, in piccolo (es. date di iscrizione).
    """
    flash(
        json.dumps(
            {
                "title": title,
                "body": body,
                "variant": variant,
                "icon": icon,
                "detail": detail,
            }
        ),
        category=PAGE_MODAL_CATEGORY,
    )
