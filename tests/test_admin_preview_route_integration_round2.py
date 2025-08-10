import pytest
from datetime import date

from models import (
    Tournament,
    Prova,
    Inscription,
    Match,
    PlayerEncounter,
    RoundClassification,
    User,
)


@pytest.mark.usefixtures("client")
def test_admin_preview_round2_anti_rematch(client, admin_user, db_session):
    """E2E: /admin/prova/<id>/amalfi/preview_round/2
    - Round 1 completato con accoppiamenti (A-B) e (C-D)
    - PlayerEncounter registrati per A-B e C-D
    - RoundClassification del round 1 presente
    → La preview del round 2 **non** deve riproporre A-B né C-D.
    """
    # Login admin della fixture (stessa sessione di test)
    rv = client.post(
        "/auth/login",
        data={"username": admin_user.username, "password": "password"},
        follow_redirects=True,
    )
    assert rv.status_code in (200, 302)

    # Torneo/Prova (2 round, almeno 4 partecipanti)
    t = Tournament(
        name="T-R2", tournament_type="Amalfi", is_active=True, without_x=False
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    p = Prova(
        tournament_id=t.id,
        number=1,
        name="Prova R2",
        date=date.today(),
        rounds_count=2,
        discipline="9",
        distance=5,
        min_participants=4,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)

    # 4 players + iscrizioni
    a = User(username="A_r2", email="a@x.com", role="player")
    a.set_password("pw")
    b = User(username="B_r2", email="b@x.com", role="player")
    b.set_password("pw")
    c = User(username="C_r2", email="c@x.com", role="player")
    c.set_password("pw")
    d = User(username="D_r2", email="d@x.com", role="player")
    d.set_password("pw")
    db_session.add_all([a, b, c, d])
    db_session.commit()
    db_session.refresh(a)
    db_session.refresh(b)
    db_session.refresh(c)
    db_session.refresh(d)

    db_session.add_all(
        [
            Inscription(prova_id=p.id, user_id=a.id),
            Inscription(prova_id=p.id, user_id=b.id),
            Inscription(prova_id=p.id, user_id=c.id),
            Inscription(prova_id=p.id, user_id=d.id),
        ]
    )
    db_session.commit()

    # Round 1: matches completati A-B e C-D
    m1 = Match(
        prova_id=p.id,
        round_number=1,
        player1_id=a.id,
        player2_id=b.id,
        status="completed",
    )
    m2 = Match(
        prova_id=p.id,
        round_number=1,
        player1_id=c.id,
        player2_id=d.id,
        status="completed",
    )
    db_session.add_all([m1, m2])
    db_session.commit()

    # PlayerEncounter round 1
    # (usiamo direttamente il modello per restare nella stessa sessione)
    enc1 = PlayerEncounter(
        prova_id=p.id,
        player1_id=min(a.id, b.id),
        player2_id=max(a.id, b.id),
        round_number=1,
    )
    enc2 = PlayerEncounter(
        prova_id=p.id,
        player1_id=min(c.id, d.id),
        player2_id=max(c.id, d.id),
        round_number=1,
    )
    db_session.add_all([enc1, enc2])
    db_session.commit()

    # RoundClassification del round 1
    rc = [
        RoundClassification(
            prova_id=p.id,
            round_number=1,
            user_id=a.id,
            position=1,
            matches_won=1,
            rack_difference=2,
            previous_position=None,
        ),
        RoundClassification(
            prova_id=p.id,
            round_number=1,
            user_id=b.id,
            position=2,
            matches_won=0,
            rack_difference=-2,
            previous_position=None,
        ),
        RoundClassification(
            prova_id=p.id,
            round_number=1,
            user_id=c.id,
            position=3,
            matches_won=1,
            rack_difference=1,
            previous_position=None,
        ),
        RoundClassification(
            prova_id=p.id,
            round_number=1,
            user_id=d.id,
            position=4,
            matches_won=0,
            rack_difference=-1,
            previous_position=None,
        ),
    ]
    db_session.add_all(rc)
    db_session.commit()

    m0 = db_session.query(Match).count()
    e0 = db_session.query(PlayerEncounter).count()

    # Preview round 2
    resp = client.get(f"/admin/prova/{p.id}/amalfi/preview_round/2")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    data = resp.get_json()
    assert data["success"] is True

    # Raccogli le coppie (come insiemi) per controllare anti-rematch
    pairs = []
    for m in data["matches"]:
        if m["type"] == "normal":
            p1 = (
                m["player1"]["id"]
                if isinstance(m["player1"], dict)
                else m["player1"]["id"]
            )
            p2 = (
                m["player2"]["id"]
                if isinstance(m["player2"], dict)
                else m["player2"]["id"]
            )
            pairs.append({p1, p2})
    assert {
        a.id,
        b.id,
    } not in pairs, "anti-rematch: A vs B non deve ripetersi al round 2"
    assert {
        c.id,
        d.id,
    } not in pairs, "anti-rematch: C vs D non deve ripetersi al round 2"

    # Nessun side-effect su DB
    assert db_session.query(Match).count() == m0
    assert db_session.query(PlayerEncounter).count() == e0
