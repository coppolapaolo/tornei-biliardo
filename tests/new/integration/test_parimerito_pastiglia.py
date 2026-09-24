"""La lista «Parimerito» prima dello spareggio mostra la pastiglia, non il suo HTML.

Regressione del 2026-09-13, trovata dall'utente sulla pagina della gara: a
destra di ogni parimerito compariva il testo
`<span class="c7-state c7-state--warn">pari</span>` invece della pastiglia.
Il template la componeva concatenando stringhe con `_('pari')`, che con
l'autoescape è gia' `Markup`: la concatenazione protegge l'altra meta' e il
`|safe` finale non la riporta indietro.
"""

from __future__ import annotations

import pytest

from models.status_enum import GaraStatus
from models.user.role_enum import UserRole
from tests.new.integration.test_chiusura_gara_direttore import _gara_a_un_turno

pytestmark = pytest.mark.integration


@pytest.fixture
def admin_client(client, db_session):
    from models.user.services import UserService

    user = UserService.create_user("pari_admin", "pari_admin@test.local", "pw12345")
    user.role = UserRole.ADMIN.value
    db_session.commit()
    resp = client.post(
        "/auth/login", data={"username": "pari_admin", "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    return client


def test_i_parimerito_hanno_la_pastiglia_pari(admin_client, db_session):
    gara = _gara_a_un_turno(db_session, GaraStatus.PLAYING.value, spareggio=True)
    html = admin_client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

    assert "Serve uno spareggio" in html
    sezione = html.split("Parimerito")[1].split("</section>")[0]
    assert "&lt;span" not in sezione
    # Una pastiglia per gruppo, non per giocatore: i posti in palio sono del
    # gruppo (2026-09-24). Qui due gruppi da due.
    assert sezione.count('<span class="c7-state c7-state--warn">pari</span>') == 2
    assert "Spareggio per il 1° e il 2° posto" in sezione
    assert "Spareggio per il 3° posto" in sezione


def test_nessun_template_incolla_html_a_una_stringa_tradotta():
    """Presidio statico della stessa classe di difetto.

    Una riga che concatena con `~` un pezzo di HTML e una stringa tradotta, e
    poi passa il risultato a `|safe`, mostra l'HTML come testo: `_()` con
    l'autoescape restituisce Markup, che protegge l'altra meta'. Il rimedio e'
    un blocco `{% set %}...{% endset %}`.
    """
    import re
    from pathlib import Path

    radice = Path(__file__).resolve().parents[3] / "templates"
    sospetta = re.compile(
        r"""['"]\s*<[a-zA-Z/][^'"]*['"]\s*~\s*_\(|_\([^)]*\)\s*~\s*['"]\s*</"""
    )
    trovate = [
        f"{percorso.relative_to(radice)}:{numero}"
        for percorso in radice.rglob("*.html")
        for numero, riga in enumerate(
            percorso.read_text(encoding="utf-8").splitlines(), 1
        )
        if sospetta.search(riga)
    ]
    assert trovate == []
