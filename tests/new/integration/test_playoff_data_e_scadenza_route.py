"""Data dei playoff e scadenza degli inviti, dalla pagina del campionato.

Le regole stanno in `tests/new/unit/test_playoff_data_e_scadenza.py`; qui si
guarda il giunto con l'interfaccia: il foglio «Avvia i playoff» chiede i due
valori, l'avvio li salva, e dalla pagina si possono cambiare dopo.
"""

from datetime import timedelta

from models import db
from models.base import utc_now
from models.playoff.models import PlayoffConfiguration
from tests.new.integration.test_avvio_playoff_route import (  # noqa: F401
    _login,
    admin_user,
    terminated_campionato_with_playoff,
)


def _campo(quando) -> str:
    """Il valore di un ``<input type="datetime-local">``."""
    return quando.strftime("%Y-%m-%dT%H:%M")


def _vicini(a, b) -> bool:
    """Il campo è nel fuso di chi scrive: fra ora locale e UTC corrono al più
    un paio d'ore, e qui interessa che il valore arrivi, non il fuso."""
    return abs(a - b) <= timedelta(hours=3)


def test_il_foglio_di_avvio_chiede_data_e_scadenza(
    client, db_session, admin_user, terminated_campionato_with_playoff  # noqa: F811
):
    campionato, _cfg, _giocatori, _gara = terminated_campionato_with_playoff
    _login(client, admin_user)

    html = client.get(f"/admin/campionato/{campionato.id}").get_data(as_text=True)

    assert f'action="/admin/campionato/{campionato.id}/start-playoff"' in html
    assert 'name="scheduled_date"' in html
    assert 'name="response_deadline"' in html


def test_l_avvio_salva_data_e_scadenza(
    client, db_session, admin_user, terminated_campionato_with_playoff  # noqa: F811
):
    campionato, cfg, _giocatori, _gara = terminated_campionato_with_playoff
    _login(client, admin_user)
    quando = utc_now() + timedelta(days=15)
    scadenza = utc_now() + timedelta(days=4)

    client.post(
        f"/admin/campionato/{campionato.id}/start-playoff",
        data={"scheduled_date": _campo(quando), "response_deadline": _campo(scadenza)},
        follow_redirects=True,
    )

    config = db.session.get(PlayoffConfiguration, cfg.id)
    assert config.scheduled_date is not None and _vicini(config.scheduled_date, quando)
    assert config.response_deadline is not None
    assert _vicini(config.response_deadline, scadenza)


def test_data_e_scadenza_si_cambiano_dalla_pagina_del_campionato(
    client, db_session, admin_user, terminated_campionato_with_playoff  # noqa: F811
):
    campionato, cfg, _giocatori, _gara = terminated_campionato_with_playoff
    _login(client, admin_user)
    client.post(
        f"/admin/campionato/{campionato.id}/start-playoff", follow_redirects=True
    )
    html = client.get(f"/admin/campionato/{campionato.id}").get_data(as_text=True)
    assert f"/admin/campionato/{campionato.id}/playoff/{cfg.id}/calendario" in html

    quando = utc_now() + timedelta(days=21)
    scadenza = utc_now() + timedelta(days=9)
    client.post(
        f"/admin/campionato/{campionato.id}/playoff/{cfg.id}/calendario",
        data={"scheduled_date": _campo(quando), "response_deadline": _campo(scadenza)},
        follow_redirects=True,
    )

    config = db.session.get(PlayoffConfiguration, cfg.id)
    assert config.scheduled_date is not None and _vicini(config.scheduled_date, quando)
    assert config.response_deadline is not None
    assert _vicini(config.response_deadline, scadenza)
