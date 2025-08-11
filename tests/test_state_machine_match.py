"""
Contract tests – Match state machine (Sprint 4)
Allineato: 2 iscritti alla Prova prima di avviare PLAYING.
"""
from datetime import datetime

from models import db, Tournament, User
from models.competition.services import ProvaService, InscriptionService
from models.match.services import MatchService
from models.status_enum import MatchStatus
from werkzeug.security import generate_password_hash


def _make_user(username: str) -> User:
    u = User(username=username, email=f"{username}@example.com")
    if hasattr(u, "set_password"):
        u.set_password("pwd-12345")
    else:
        u.password_hash = generate_password_hash("pwd-12345")
    db.session.add(u)
    db.session.commit()
    return u


def test_match_transitions(app):
    with app.app_context():
        # Tournament + Prova (che porteremo in playing)
        t = Tournament(name="T1")
        db.session.add(t)
        db.session.commit()

        p = ProvaService.create_prova(
            number=1,
            name="P1",
            date=datetime.now().date(),
            discipline="palla_9",
            distance=3,
            tournament_id=t.id,
        )

        # 2 utenti + iscrizioni (requisito per start_playing)
        u1 = _make_user("u1")
        u2 = _make_user("u2")
        InscriptionService.inscribe_user(u1.id, p.id)
        InscriptionService.inscribe_user(u2.id, p.id)

        ProvaService.to_inscription(p.id)
        ProvaService.start_playing(p.id)

        # Crea match (pending)
        m = MatchService.create_match(
            prova_id=p.id,
            round_number=1,
            player1_id=u1.id,
            player2_id=u2.id,
        )
        assert m.status == MatchStatus.PENDING.value

        # pending → playing
        m = MatchService.to_playing(m.id)
        assert m.status == MatchStatus.PLAYING.value

        # playing → completed
        m = MatchService.to_completed(m.id)
        assert m.status == MatchStatus.COMPLETED.value

        # completed → playing (riapertura dopo rimozione rack, ecc.)
        m = MatchService.to_playing(m.id)
        assert m.status == MatchStatus.PLAYING.value

        # qualsiasi → pending (reset)
        m = MatchService.reset_to_pending(m.id)
        assert m.status == MatchStatus.PENDING.value
