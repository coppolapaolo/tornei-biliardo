"""«Annulla la gara» risponde al pulsante in JSON, anche quando fallisce.

Il pulsante della fase iscrizioni chiama `/admin/gara/<id>/cancel` con `fetch`
e, su risposta non riuscita, mostra «Errore durante la cancellazione:» seguito
dal corpo della risposta. La route non intercettava gli errori imprevisti: il
2026-09-13 l'utente si è visto incollare nel messaggio l'intera pagina di
Werkzeug (`FOREIGN KEY constraint failed` sulla gara di playoff). Il guasto è
corretto nel servizio (`tests/new/unit/test_annullo_gara_playoff.py`); qui si
presidia che un guasto futuro arrivi come frase leggibile.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.competition.models import Gara
from models.competition.services import GaraService
from models.playoff.services import PlayoffService
from models.user.models import User
from models.user.role_enum import UserRole
from tests.new.unit.test_playoff_con_meno_accettazioni import _accetta, _playoff

AJAX = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def admin_user(db_session):
    uid = str(uuid.uuid4())[:8]
    u = User(
        username=f"admin_{uid}", email=f"admin_{uid}@t.com", role=UserRole.ADMIN.value
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.commit()
    return u


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "test1234"},
        follow_redirects=True,
    )


@pytest.fixture
def gara_di_playoff(db_session):
    campionato, cfg, giocatori = _playoff(db_session, posti=4)
    _accetta(cfg, *giocatori)
    gara = PlayoffService.create_playoff_gara(cfg.id)
    return campionato, gara.id


def test_annullare_la_gara_di_playoff_dal_pulsante(
    client, db_session, admin_user, gara_di_playoff
):
    campionato, gara_id = gara_di_playoff
    _login(client, admin_user)

    resp = client.post(f"/admin/gara/{gara_id}/cancel", headers=AJAX)

    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    assert resp.is_json
    assert resp.get_json()["success"] is True
    assert resp.get_json()["redirect"].endswith(f"/admin/campionato/{campionato.id}")
    db.session.expire_all()
    assert db.session.get(Gara, gara_id) is None


def test_un_errore_imprevisto_arriva_come_json_non_come_pagina_html(
    client, db_session, admin_user, gara_di_playoff, monkeypatch
):
    _campionato, gara_id = gara_di_playoff
    _login(client, admin_user)

    def guasto(*_args, **_kwargs):
        raise RuntimeError("FOREIGN KEY constraint failed")

    monkeypatch.setattr(GaraService, "cancel_gara_with_notifications", guasto)

    resp = client.post(f"/admin/gara/{gara_id}/cancel", headers=AJAX)

    assert resp.status_code == 500
    assert resp.is_json
    errore = resp.get_json()["error"]
    assert errore and "<" not in errore
    assert "FOREIGN KEY" not in errore


def test_un_rifiuto_del_servizio_arriva_col_suo_messaggio(
    client, db_session, admin_user, gara_di_playoff, monkeypatch
):
    _campionato, gara_id = gara_di_playoff
    _login(client, admin_user)

    def rifiuto(*_args, **_kwargs):
        raise ValueError("La gara non può essere cancellata in questo stato!")

    monkeypatch.setattr(GaraService, "cancel_gara_with_notifications", rifiuto)

    resp = client.post(f"/admin/gara/{gara_id}/cancel", headers=AJAX)

    assert resp.status_code == 400
    assert resp.get_json()["error"] == (
        "La gara non può essere cancellata in questo stato!"
    )
