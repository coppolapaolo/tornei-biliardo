"""La data d'iscrizione nel riquadro del giocatore non deve tornare "N/D".

Il template leggeva `user_inscription.inscription_date`, un attributo che sul
modello `Inscription` non e' mai esistito: Jinja lo risolveva a Undefined, il
ramo `else` scattava e la data risultava sempre "N/D". Nessun errore, nessun
log — solo un dato che non compariva mai. Il campo giusto e' `created_at`,
lo stesso che usa `_gara_inscriptions.html`.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from flask import render_template

TEMPLATE = "components/_player_inscription_info.html"


def _inscription(**overrides):
    data = {
        "created_at": datetime(2026, 7, 28, 15, 31),
        "initial_order": 3,
        "is_waitlist": False,
        "waitlist_position": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.unit
def test_mostra_la_data_di_iscrizione(app):
    with app.test_request_context("/"):
        html = render_template(TEMPLATE, user_inscription=_inscription())

    assert "N/D" not in html
    assert "28/07/2026" in html


@pytest.mark.unit
def test_il_campo_letto_e_created_at(app):
    """Senza `created_at` niente data — ma nemmeno un attributo inventato."""
    with app.test_request_context("/"):
        html = render_template(TEMPLATE, user_inscription=_inscription(created_at=None))

    assert "—" in html
    assert "inscription_date" not in html


@pytest.mark.unit
def test_lista_di_attesa_dichiarata(app):
    with app.test_request_context("/"):
        html = render_template(
            TEMPLATE,
            user_inscription=_inscription(is_waitlist=True, waitlist_position=2),
        )

    assert "In lista d&#39;attesa" in html or "In lista d'attesa" in html
    assert "Posizione in lista" in html
