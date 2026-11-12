"""Capienza del tabellone e anti-reincontro, percorsi veri (#236, #238).

I test unitari provano le funzioni; qui si invia il modulo come lo invia il
browser. Servono perché le regole possono stare in una funzione che nessuna
route chiama, o in un parser a cui il dato non arriva: al passo 2 del wizard
il tipo di campionato non è nel modulo, è in sessione dal passo 1.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from flask import get_flashed_messages

from models import Gara, User
from models.campionato.models import Campionato
from models.matchmaking.configuration import MatchmakingStrategy
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration

TABELLONI = [
    MatchmakingStrategy.DIRECT_ELIMINATION.value,
    MatchmakingStrategy.DOUBLE_KNOCKOUT.value,
]


@pytest.fixture
def director(db_session):
    user = User(
        username=f"dir_{uuid.uuid4().hex[:8]}",
        email=f"dir_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.DIRECTOR.value,
        onboarding_completed=True,
    )
    user.set_password("director123")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    client.post(
        "/auth/login",
        data={"username": user.username, "password": "director123"},
        follow_redirects=True,
    )


def _gara(**overrides):
    campi = {
        "name": f"Tabellone {uuid.uuid4().hex[:6]}",
        "date": (date.today() + timedelta(days=10)).isoformat(),
        "time": "20:00",
        "discipline": "9_ball",
        "distance": "5",
        "rounds_count": "3",
        "min_participants": "4",
        "max_participants": "16",
        "entry_fee": "0",
        "matchmaking_strategy": MatchmakingStrategy.DIRECT_ELIMINATION.value,
        "first_round_policy": "random",
        "odd_number_policy": "bye",
        "withdraw_policy": "forfeit",
    }
    campi.update(overrides)
    return campi


def _messaggi() -> str:
    return " | ".join(str(m) for m in get_flashed_messages())


@pytest.mark.parametrize("strategia", TABELLONI)
def test_la_gara_a_tabellone_senza_capienza_non_nasce(
    client, db_session, director, strategia
):
    _login(client, director)
    dati = _gara(matchmaking_strategy=strategia, max_participants="")

    with client:
        client.post("/admin/gara/create_standalone", data=dati)
        messaggi = _messaggi()

    assert Gara.query.filter_by(name=dati["name"]).first() is None
    assert "numero massimo di iscritti è obbligatorio" in messaggi
    assert "turni" not in messaggi.lower()


def test_la_gara_non_diventa_tabellone_senza_capienza(client, db_session, director):
    _login(client, director)
    dati = _gara(
        matchmaking_strategy=MatchmakingStrategy.AMALFI.value,
        max_participants="",
        anti_rematch_enabled="on",
    )
    client.post("/admin/gara/create_standalone", data=dati)
    gara = Gara.query.filter_by(name=dati["name"]).one()
    gara_id = gara.id

    dati["matchmaking_strategy"] = MatchmakingStrategy.DIRECT_ELIMINATION.value
    with client:
        client.post(f"/admin/gara/{gara_id}/edit", data=dati)
        messaggi = _messaggi()

    db_session.expire_all()
    gara = db_session.get(Gara, gara_id)
    assert gara.matchmaking_strategy == MatchmakingStrategy.AMALFI.value
    assert "numero massimo di iscritti è obbligatorio" in messaggi


@pytest.mark.parametrize("strategia", TABELLONI)
def test_il_wizard_non_salva_l_anti_reincontro_sul_tabellone(
    client, db_session, director, strategia
):
    """Il modulo del passo 2 è quello vero: il tipo non c'è, la casella sì."""
    _login(client, director)
    nome = f"Camp {uuid.uuid4().hex[:6]}"
    client.post(
        "/admin/campionato/wizard/step2",
        data={
            "name": nome,
            "planned_gare_count": "3",
            "campionato_type": strategia,
            "default_classification_system": "POSITION",
        },
    )

    client.post(
        "/admin/campionato/wizard/create",
        data={"default_anti_rematch": "on", "default_rounds_count": "3"},
    )

    campionato = Campionato.query.filter_by(name=nome).one()
    assert campionato.campionato_type == strategia
    assert campionato.default_anti_rematch is False


def test_il_wizard_tiene_l_anti_reincontro_fuori_dal_tabellone(
    client, db_session, director
):
    _login(client, director)
    nome = f"Camp {uuid.uuid4().hex[:6]}"
    client.post(
        "/admin/campionato/wizard/step2",
        data={
            "name": nome,
            "planned_gare_count": "3",
            "campionato_type": MatchmakingStrategy.AMALFI.value,
            "default_classification_system": "WINS",
        },
    )

    client.post(
        "/admin/campionato/wizard/create",
        data={"default_anti_rematch": "on", "default_rounds_count": "3"},
    )

    campionato = Campionato.query.filter_by(name=nome).one()
    assert campionato.default_anti_rematch is True
