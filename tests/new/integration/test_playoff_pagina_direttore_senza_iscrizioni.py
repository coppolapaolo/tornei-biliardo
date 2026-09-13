"""La pagina del direttore di una gara di playoff, prima dell'avvio.

Al playoff si entra dall'invito: la pagina non chiede di aprire le iscrizioni,
offre «Avvia la gara» e la striscia non ha la tacca delle iscrizioni. Le
regole stanno in `tests/new/unit/test_playoff_senza_iscrizioni.py`; qui si
guarda cosa legge il direttore.
"""

import pytest

from models.playoff.services import PlayoffService
from models.user.role_enum import UserRole
from tests.new.integration.test_pagina_gara_direttore import _tacche
from tests.new.unit.test_playoff_con_meno_accettazioni import _accetta, _playoff

pytestmark = pytest.mark.integration


@pytest.fixture
def admin_client(client, db_session):
    from models.user.services import UserService

    user = UserService.create_user(
        "playoff_avvio_admin", "playoff_avvio_admin@test.local", "pw12345"
    )
    user.role = UserRole.ADMIN.value
    db_session.commit()
    risposta = client.post(
        "/auth/login",
        data={"username": "playoff_avvio_admin", "password": "pw12345"},
    )
    assert risposta.status_code in (200, 302)
    return client


def test_il_playoff_in_preparazione_si_avvia_senza_aprire_le_iscrizioni(
    admin_client, db_session
):
    _campionato, cfg, giocatori = _playoff(db_session, posti=4)
    _accetta(cfg, *giocatori)
    gara = PlayoffService.create_playoff_gara(cfg.id)

    risposta = admin_client.get(f"/admin/gara/{gara.id}")
    html = risposta.get_data(as_text=True)

    assert risposta.status_code == 200
    # Il comando nella fascia avvia, e nessun pulsante apre le iscrizioni.
    assert f'onclick="startFirstRound({gara.id},' in html
    assert 'data-bs-target="#openInscriptionsModal"' not in html
    # Il pulsante apre il foglio di avvio: senza, `startFirstRound` esce in
    # silenzio e «Avvia la gara» non fa niente (rilievo del 2026-09-13).
    assert 'id="avviaGaraModal"' in html
    # Chi ha accettato l'invito è iscritto, e il direttore lo vede.
    for giocatore in giocatori:
        assert giocatore.username in html
    # La striscia salta la fase delle iscrizioni.
    titoli = [titolo for _stato, titolo in _tacche(html)]
    assert "Iscrizioni" not in titoli
    assert titoli[0] == "Preparazione"
