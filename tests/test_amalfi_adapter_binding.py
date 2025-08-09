from datetime import date
import pytest


@pytest.mark.usefixtures("app")
def test_amalfi_adapter_binding_e2e(app):
    """E2E: il Service invoca l'adapter Amalfi e ritorna **Pairing** VO.

    Con 3 giocatori e without_x=True al round 1, accettiamo due esiti:
    - 1 trio (un solo Pairing con 3 id), oppure
    - bye + match 1v1 (due Pairing: uno con len(players)==1 e uno con len(players)==2).
    """
    from models.matchmaking.bootstrap import get_matchmaking_service
    from models import Prova, User, db, Inscription, Tournament

    svc = get_matchmaking_service()

    with app.app_context():
        # Torneo senza X (consente trio nelle impl che lo prevedono)
        t = Tournament(
            name="T",
            tournament_type="Amalfi",
            is_active=True,
            without_x=True,
        )
        db.session.add(t)
        db.session.commit()

        # Per 3 giocatori il validatore consente max 2 turni
        p = Prova(
            tournament_id=t.id,
            number=1,
            name="P",
            date=date.today(),  # NOT NULL nello schema
            rounds_count=2,  # evita "Troppi turni per 3 giocatori"
            distance=5,
            discipline="palla 8",
        )
        db.session.add(p)
        db.session.commit()

        # 3 giocatori iscritti
        a = User(username="a", email="a@test.com", role="player")
        a.set_password("pw")
        b = User(username="b", email="b@test.com", role="player")
        b.set_password("pw")
        c = User(username="c", email="c@test.com", role="player")
        c.set_password("pw")
        db.session.add_all([a, b, c])
        db.session.commit()

        db.session.add_all(
            [
                Inscription(prova_id=p.id, user_id=a.id),
                Inscription(prova_id=p.id, user_id=b.id),
                Inscription(prova_id=p.id, user_id=c.id),
            ]
        )
        db.session.commit()

        pairings = svc.run(strategy_name="Amalfi", prova=p, round_number=1)
        assert pairings, "Nessun pairing generato"

        # pairings è una Sequence di Value Objects Pairing (non tuple)
        trio = [pr for pr in pairings if len(pr.players) == 3]
        byes = [pr for pr in pairings if pr.is_bye or len(pr.players) == 1]
        normal = [pr for pr in pairings if len(pr.players) == 2 and not pr.is_bye]

        if trio:
            assert len(pairings) == 1
            ids = set(trio[0].players)
            assert ids == {a.id, b.id, c.id}
        else:
            # bye + un match 1v1 che coprono tutti gli id
            assert len(byes) == 1, f"atteso 1 bye, ottenuti: {byes}"
            assert len(normal) == 1, f"atteso 1 match 1v1, ottenuti: {normal}"
            used_ids = set(byes[0].players) | set(normal[0].players)
            assert used_ids == {a.id, b.id, c.id}
