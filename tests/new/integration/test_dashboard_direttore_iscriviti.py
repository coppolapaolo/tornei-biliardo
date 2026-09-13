"""Il direttore è anche un giocatore: sulla tessera della gara che dirige, a
iscrizioni aperte, trova «Iscriviti» o «Disiscriviti».

Richiesta dell'utente del 2026-09-13. La tessera sapeva già sommare il fatto
da giocatore a quello da direttore, ma solo se la gara non aveva un comando da
annunciare: a iscrizioni aperte il comando c'è sempre, «Avvia la gara», quindi
il pulsante del giocatore non compariva mai.

Le condizioni restano quelle del giocatore: finestra aperta, lista d'attesa a
gara piena, niente per l'admin e niente sul playoff, dove ci si iscrive solo
accettando l'invito.
"""

from datetime import timedelta

import pytest

from models.base import utc_now
from models.competition.models import Inscription
from models.status_enum import GaraStatus
from models.user.models import User
from tests.new.integration.test_dashboard_gare_divise_render import _gara, _login, _uid

pytestmark = pytest.mark.integration


@pytest.fixture
def direttore(db_session):
    user = User(username=f"dir_{_uid()}", email=f"dir_{_uid()}@t.com", role="director")
    user.set_password("test1234")
    db_session.add(user)
    db_session.flush()
    return user


def _aperta(db_session, direttore, nome, **kwargs):
    valori = {
        "name": nome,
        "status": GaraStatus.INSCRIPTION.value,
        "director_id": direttore.id,
        "min_participants": 2,
        "inscription_start": utc_now() - timedelta(days=1),
        "inscription_end": utc_now() + timedelta(days=7),
    }
    valori.update(kwargs)
    return _gara(db_session, **valori)


def _tessera(client, nome):
    html = client.get("/dashboard").get_data(as_text=True)
    assert nome in html
    return html.split(nome, 1)[1].split("</article>", 1)[0]


def test_il_direttore_non_iscritto_vede_iscriviti_accanto_al_comando(
    client, db_session, direttore
):
    gara = _aperta(db_session, direttore, "Gara Mia Aperta")
    db_session.commit()

    _login(client, direttore)
    tessera = _tessera(client, "Gara Mia Aperta")

    assert "Avvia la gara" in tessera
    assert f"inscribeToGara({gara.id})" in tessera
    assert "unsubscribeFromGara" not in tessera


def test_il_direttore_iscritto_vede_disiscriviti(client, db_session, direttore):
    gara = _aperta(db_session, direttore, "Gara Mia Iscritto")
    db_session.add(Inscription(user_id=direttore.id, gara_id=gara.id))
    db_session.commit()

    _login(client, direttore)
    tessera = _tessera(client, "Gara Mia Iscritto")

    assert "Avvia la gara" in tessera
    assert f"unsubscribeFromGara({gara.id})" in tessera
    assert "Disiscriviti" in tessera
    assert "inscribeToGara" not in tessera


def test_a_gara_piena_il_direttore_si_mette_in_lista(client, db_session, direttore):
    gara = _aperta(db_session, direttore, "Gara Mia Piena", max_participants=2)
    for n in range(2):
        altro = User(username=f"g{n}_{_uid()}", email=f"g{n}_{_uid()}@t.com")
        altro.set_password("test1234")
        db_session.add(altro)
        db_session.flush()
        db_session.add(Inscription(user_id=altro.id, gara_id=gara.id))
    db_session.commit()

    _login(client, direttore)
    tessera = _tessera(client, "Gara Mia Piena")

    assert f"inscribeToGara({gara.id})" in tessera
    assert "Mettiti in lista" in tessera


def test_a_iscrizioni_non_aperte_nessuno_dei_due(client, db_session, direttore):
    _gara(
        db_session,
        name="Gara Mia Bozza",
        status=GaraStatus.SETUP.value,
        director_id=direttore.id,
    )
    db_session.commit()

    _login(client, direttore)
    tessera = _tessera(client, "Gara Mia Bozza")

    assert "Apri le iscrizioni" in tessera
    assert "inscribeToGara" not in tessera
    assert "unsubscribeFromGara" not in tessera


def test_sul_playoff_nessuno_dei_due(client, db_session, direttore):
    """Al playoff si entra accettando l'invito: il servizio rifiuta
    l'iscrizione diretta, quindi il pulsante porterebbe a un rifiuto."""
    from tests.new.unit.test_avvio_playoff import _make_campionato, _make_config

    campionato = _make_campionato(db_session)
    config = _make_config(db_session, campionato)
    gara = _aperta(
        db_session,
        direttore,
        "Gara Mia Playoff",
        campionato_id=campionato.id,
        playoff_config_id=config.id,
    )
    db_session.add(Inscription(user_id=direttore.id, gara_id=gara.id))
    db_session.commit()

    _login(client, direttore)
    tessera = _tessera(client, "Gara Mia Playoff")

    assert "inscribeToGara" not in tessera
    assert "unsubscribeFromGara" not in tessera


def test_l_admin_non_ha_pulsanti_da_giocatore(client, db_session, direttore):
    admin = User(username=f"adm_{_uid()}", email=f"adm_{_uid()}@t.com", role="admin")
    admin.set_password("test1234")
    db_session.add(admin)
    gara = _aperta(db_session, direttore, "Gara Vista Da Admin")
    db_session.commit()

    _login(client, admin)
    html = client.get("/dashboard").get_data(as_text=True)

    assert f"inscribeToGara({gara.id})" not in html
    assert f"unsubscribeFromGara({gara.id})" not in html
