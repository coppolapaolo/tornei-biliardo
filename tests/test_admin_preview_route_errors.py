import pytest
from datetime import date

from models import Tournament, Prova, Inscription, Match, User


@pytest.mark.usefixtures("client")
def test_preview_invalid_round_number(client, admin_user, db_session):
    rv = client.post(
        "/auth/login",
        data={"username": admin_user.username, "password": "password"},
        follow_redirects=True,
    )
    assert rv.status_code in (200, 302)

    t = Tournament(name="T-err1", tournament_type="Amalfi", is_active=True)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    p = Prova(
        tournament_id=t.id,
        number=1,
        name="Err1",
        date=date.today(),
        rounds_count=2,
        discipline="9",
        distance=5,
        min_participants=2,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)

    # round 0 non valido
    resp = client.get(f"/admin/prova/{p.id}/amalfi/preview_round/0")
    assert resp.status_code == 400
    assert "non valido" in resp.get_json().get("error", "").lower()

    # round 3 > rounds_count
    resp = client.get(f"/admin/prova/{p.id}/amalfi/preview_round/3")
    assert resp.status_code == 400


@pytest.mark.usefixtures("client")
def test_preview_already_started_round(client, admin_user, db_session):
    rv = client.post(
        "/auth/login",
        data={"username": admin_user.username, "password": "password"},
        follow_redirects=True,
    )
    assert rv.status_code in (200, 302)

    t = Tournament(name="T-err2", tournament_type="Amalfi", is_active=True)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    p = Prova(
        tournament_id=t.id,
        number=1,
        name="Err2",
        date=date.today(),
        rounds_count=2,
        discipline="9",
        distance=5,
        min_participants=2,
        current_round=1,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)

    # round 1 già avviato
    resp = client.get(f"/admin/prova/{p.id}/amalfi/preview_round/1")
    assert resp.status_code == 400
    assert "già" in resp.get_json().get("error", "")


@pytest.mark.usefixtures("client")
def test_preview_previous_round_incomplete(client, admin_user, db_session):
    rv = client.post(
        "/auth/login",
        data={"username": admin_user.username, "password": "password"},
        follow_redirects=True,
    )
    assert rv.status_code in (200, 302)

    t = Tournament(name="T-err3", tournament_type="Amalfi", is_active=True)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    p = Prova(
        tournament_id=t.id,
        number=1,
        name="Err3",
        date=date.today(),
        rounds_count=2,
        discipline="9",
        distance=5,
        min_participants=2,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)

    # round 1 incompleto (un match pending)
    u1 = User(username="e1", email="e1@x.com", role="player")
    u1.set_password("pw")
    u2 = User(username="e2", email="e2@x.com", role="player")
    u2.set_password("pw")
    db_session.add_all([u1, u2])
    db_session.commit()
    db_session.refresh(u1)
    db_session.refresh(u2)

    db_session.add_all(
        [
            Inscription(prova_id=p.id, user_id=u1.id),
            Inscription(prova_id=p.id, user_id=u2.id),
        ]
    )
    db_session.commit()

    m = Match(
        prova_id=p.id,
        round_number=1,
        player1_id=u1.id,
        player2_id=u2.id,
        status="pending",
    )
    db_session.add(m)
    db_session.commit()

    resp = client.get(f"/admin/prova/{p.id}/amalfi/preview_round/2")
    assert resp.status_code == 400
    assert "completa prima il turno 1" in resp.get_json().get("error", "").lower()


@pytest.mark.usefixtures("client")
def test_preview_validation_failure_returns_500(client, admin_user, db_session):
    """Oggi la route cattura le eccezioni e restituisce 500.
    Testiamo il comportamento attuale (in futuro potremmo normalizzare a 400).
    """
    rv = client.post(
        "/auth/login",
        data={"username": admin_user.username, "password": "password"},
        follow_redirects=True,
    )
    assert rv.status_code in (200, 302)

    t = Tournament(name="T-err4", tournament_type="Amalfi", is_active=True)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    # Solo 3 iscritti ma min_participants=4 → valida KO
    p = Prova(
        tournament_id=t.id,
        number=1,
        name="Err4",
        date=date.today(),
        rounds_count=2,
        discipline="9",
        distance=5,
        min_participants=4,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)

    u1 = User(username="v1", email="v1@x.com", role="player")
    u1.set_password("pw")
    u2 = User(username="v2", email="v2@x.com", role="player")
    u2.set_password("pw")
    u3 = User(username="v3", email="v3@x.com", role="player")
    u3.set_password("pw")
    db_session.add_all([u1, u2, u3])
    db_session.commit()
    db_session.refresh(u1)
    db_session.refresh(u2)
    db_session.refresh(u3)

    db_session.add_all(
        [
            Inscription(prova_id=p.id, user_id=u1.id),
            Inscription(prova_id=p.id, user_id=u2.id),
            Inscription(prova_id=p.id, user_id=u3.id),
        ]
    )
    db_session.commit()

    resp = client.get(f"/admin/prova/{p.id}/amalfi/preview_round/1")
    assert resp.status_code == 500
    assert "errore anteprima" in resp.get_json().get("error", "").lower()
