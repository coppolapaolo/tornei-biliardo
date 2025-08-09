from datetime import date
import pytest

from models.matchmaking.strategies.amalfi_adapter import AmalfiStrategy
from models.matchmaking.bindings.amalfi_binding import validate_prova, propose_pairings


@pytest.mark.usefixtures("app")
def test_preview_round1_no_side_effects(app):
    from models import Prova, User, db, Inscription, Tournament, Match, PlayerEncounter

    with app.app_context():
        t = Tournament(name="T", tournament_type="Amalfi", is_active=True, without_x=True)
        db.session.add(t); db.session.commit()

        p = Prova(
            tournament_id=t.id,
            number=1,
            name="P",
            date=date.today(),
            rounds_count=2,
            distance=5,
            discipline="palla 8",
        )
        db.session.add(p); db.session.commit()

        a = User(username="a", email="a@test.com", role="player"); a.set_password("pw")
        b = User(username="b", email="b@test.com", role="player"); b.set_password("pw")
        c = User(username="c", email="c@test.com", role="player"); c.set_password("pw")
        db.session.add_all([a, b, c]); db.session.commit()

        db.session.add_all([
            Inscription(prova_id=p.id, user_id=a.id),
            Inscription(prova_id=p.id, user_id=b.id),
            Inscription(prova_id=p.id, user_id=c.id),
        ]); db.session.commit()

        m0 = Match.query.count(); e0 = PlayerEncounter.query.count()

        # Istanzio la Strategy passando le dipendenze come da design Sprint 1
        strategy = AmalfiStrategy(validate_fn=validate_prova, propose_fn=propose_pairings)
        prs = strategy.preview(p, 1)
        assert prs, "preview deve generare almeno un pairing"

        # Nessun side-effect
        assert Match.query.count() == m0
        assert PlayerEncounter.query.count() == e0
