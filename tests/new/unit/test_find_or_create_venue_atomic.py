"""Regression: find_or_create_venue committa il venue in modo atomico.

Bug (code review 2026-06-09, HIGH correttezza) — `models/location/services.py:62`:

`find_or_create_venue` chiamava `create_billiard_hall` (@transactional, che
COMMITTA la riga con i default `is_active=True`) e SOLO DOPO mutava
`is_active=False`/`verified=False`/`set_table_names(...)`. A transaction già
chiusa quelle mutazioni restavano pendenti nella sessione: venivano persistite
solo per side-effect di un commit successivo (es. GaraService.create_gara nella
route). Se tra la creazione del venue e quel commit avveniva un early-return
(es. validate_strategy fallisce), le mutazioni venivano scartate al teardown e
in DB restava un venue ATTIVO e non verificato, visibile subito nelle liste
pubbliche bypassando la verifica admin.

Fix: i valori sono passati a `create_billiard_hall` e committati nello stesso
`@transactional`. Il test simula l'early-return con un `rollback()` dopo la
creazione: lo stato corretto deve sopravvivere (era già committato).
"""

from __future__ import annotations

import pytest

from models.base import db
from models import BilliardHall, User
from models.user.role_enum import UserRole
from models.location.services import LocationService


@pytest.fixture
def director(db_session):
    user = User(
        username="venue_creator",
        email="venue_creator@example.com",
        role=UserRole.DIRECTOR.value,
    )
    user.set_password("pw")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.mark.unit
def test_new_venue_is_inactive_and_unverified_after_rollback(director):
    # Crea un venue nuovo con lista esplicita di tavoli.
    location, hall_id, _msg = LocationService.find_or_create_venue(
        location="Sala Nuova Da Verificare",
        tables_input="Rosso, Verde, Blu",
        added_by_id=director.id,
    )
    assert hall_id is not None

    # Simula l'early-return della route (validate_strategy fallisce): nessun
    # commit successivo, il teardown scarta tutto ciò che è ancora pendente.
    db.session.rollback()
    db.session.expire_all()

    hall = db.session.get(BilliardHall, hall_id)
    assert hall is not None, "Il venue deve essere stato committato"
    # Pre-fix questi due erano True/default perché le mutazioni post-commit
    # venivano scartate dal rollback.
    assert hall.is_active is False
    assert hall.verified is False
    # I nomi tavoli espliciti devono essere persistiti atomicamente.
    assert hall.get_table_names() == ["Rosso", "Verde", "Blu"]


@pytest.mark.unit
def test_single_number_tables_use_default_names(director):
    # Input numerico singolo → niente lista esplicita, nomi di default.
    _location, hall_id, _msg = LocationService.find_or_create_venue(
        location="Sala Tre Tavoli",
        tables_input="3",
        added_by_id=director.id,
    )
    db.session.rollback()
    db.session.expire_all()

    hall = db.session.get(BilliardHall, hall_id)
    assert hall is not None
    assert hall.is_active is False
    assert hall.verified is False
    assert hall.number_of_tables == 3
