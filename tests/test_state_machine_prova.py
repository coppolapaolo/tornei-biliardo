"""
Contract tests – Prova state machine (Sprint 4)
Allineato alla logica attuale: servono almeno 2 iscritti per passare a PLAYING.
"""
from datetime import datetime

from models import db, Tournament, User
from models.competition.services import ProvaService, InscriptionService
from models.status_enum import ProvaStatus
from werkzeug.security import generate_password_hash


def _make_user(username: str) -> User:
    u = User(username=username, email=f"{username}@example.com")
    # Rispetta il vincolo NOT NULL su password_hash
    if hasattr(u, "set_password"):
        u.set_password("pwd-12345")
    else:
        u.password_hash = generate_password_hash("pwd-12345")
    db.session.add(u)
    db.session.commit()
    return u


def test_prova_transitions(app):
    with app.app_context():
        # Torneo di contesto
        t = Tournament(name="T1")
        db.session.add(t)
        db.session.commit()

        # Crea una Prova
        p = ProvaService.create_prova(
            number=1,
            name="P1",
            date=datetime.now().date(),
            discipline="palla_9",
            distance=7,
            tournament_id=t.id,
        )
        assert p.status == ProvaStatus.SETUP.value

        # 2 utenti + iscrizioni (requisito per start_playing)
        u1 = _make_user("u1")
        u2 = _make_user("u2")
        InscriptionService.inscribe_user(u1.id, p.id)
        InscriptionService.inscribe_user(u2.id, p.id)

        # setup → inscription
        p = ProvaService.to_inscription(p.id)
        assert p.status == ProvaStatus.INSCRIPTION.value

        # inscription → playing (ora consentito)
        p = ProvaService.start_playing(p.id)
        assert p.status == ProvaStatus.PLAYING.value

        # playing → completed
        p = ProvaService.complete(p.id)
        assert p.status == ProvaStatus.COMPLETED.value
