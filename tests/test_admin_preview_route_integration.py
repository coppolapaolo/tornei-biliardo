import pytest
from datetime import date

from models import Tournament, Prova, Inscription, Match, PlayerEncounter, User


@pytest.mark.usefixtures("client")
def test_admin_preview_round_route_uses_strategy(client, admin_user, db_session):
    """La route di anteprima deve rispondere con JSON coerente e senza side‑effects.
    Verifica end‑to‑end che passi per MatchmakingService.preview()
    (quindi Strategy.preview()).
    Pattern di test: usa *solo* db_session + fixture utenti
    per evitare DetachedInstanceError.
    """
    # Login come admin creato dalla fixture (stessa sessione di test)
    rv = client.post(
        "/auth/login",
        data={"username": admin_user.username, "password": "password"},
        follow_redirects=True,
    )
    assert rv.status_code in (200, 302)

    # Setup torneo e prova con db_session (mai db.session, mai app.app_context())
    t = Tournament(name="T", tournament_type="Amalfi", is_active=True, without_x=True)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    p = Prova(
        tournament_id=t.id,
        number=1,
        name="Prova 1",
        date=date.today(),
        rounds_count=2,
        discipline="9",
        distance=5,
        min_participants=3,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    prova_id = p.id

    # 3 iscritti per forzare disparità → trio/bye a seconda della policy
    u1 = User(username="u1_prev", email="u1@x.com", role="player")
    u1.set_password("pw")
    u2 = User(username="u2_prev", email="u2@x.com", role="player")
    u2.set_password("pw")
    u3 = User(username="u3_prev", email="u3@x.com", role="player")
    u3.set_password("pw")
    db_session.add_all([u1, u2, u3])
    db_session.commit()
    db_session.refresh(u1)
    db_session.refresh(u2)
    db_session.refresh(u3)

    db_session.add_all(
        [
            Inscription(prova_id=prova_id, user_id=u1.id),
            Inscription(prova_id=prova_id, user_id=u2.id),
            Inscription(prova_id=prova_id, user_id=u3.id),
        ]
    )
    db_session.commit()

    m0 = db_session.query(Match).count()
    e0 = db_session.query(PlayerEncounter).count()

    # Call route anteprima (round 1)
    resp = client.get(f"/admin/prova/{prova_id}/amalfi/preview_round/1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["round_number"] == 1
    assert (
        isinstance(data["matches"], list) and data["matches"]
    ), "la route deve restituire almeno un abbinamento"

    # Nessun side‑effect su DB (preview)
    assert db_session.query(Match).count() == m0
    assert db_session.query(PlayerEncounter).count() == e0
