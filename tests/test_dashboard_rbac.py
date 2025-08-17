# tests/test_dashboard_rbac.py
from datetime import date
import pytest


@pytest.mark.usefixtures("app")
def test_admin_dashboard_shows_standalone(client, admin_user):
    # Login come admin
    client.post(
        "/auth/login", data={"username": admin_user.username, "password": "password"}
    )

    # Crea una prova standalone valida
    from models.base import db
    from models.competition.models import Prova

    p = Prova(
        number=1,
        name="Prova Standalone X",
        tournament_id=None,
        director_id=None,
        date=date.today(),
        discipline="palla_8",
        distance=9,
    )
    db.session.add(p)
    db.session.commit()

    # Vai in dashboard admin
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert b"Competizioni Standalone" in resp.data
    assert b"Prova Standalone X" in resp.data
    # Admin non gioca mai
    assert b"Le mie iscrizioni" not in resp.data


@pytest.mark.usefixtures("app")
def test_demote_director_removes_prova_director_id(app, admin_user, director_user):
    from models.base import db
    from models.competition.models import Prova
    from models.user.services import UserService

    # Prova standalone assegnata al director (rispetta NOT NULL)
    prova = Prova(
        number=1,
        name="S1",
        tournament_id=None,
        director_id=director_user.id,
        date=date.today(),
        discipline="palla_8",
        distance=9,
    )
    db.session.add(prova)
    db.session.commit()
    assert prova.director_id == director_user.id

    # Demote con admin valido
    UserService.demote_from_director(director_user.id, admin_user=admin_user)

    # Ricarica e verifica
    db.session.refresh(prova)
    assert prova.director_id is None
