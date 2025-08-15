# tests/test_tournament_service_delete_hardening.py
import pytest
from models import db, User, Tournament, Prova, Match, Rack, Classification
from models.user.models import TournamentDirector
from models.tournament.services import TournamentService
from datetime import datetime


@pytest.mark.usefixtures("app")
def test_service_delete_cascades_entities(app):
    with app.app_context():
        # Utenti minimi
        u1 = User(username="u_del_1", email="u1@x.com", role="player")
        u1.set_password("pw")
        u2 = User(username="u_del_2", email="u2@x.com", role="player")
        u2.set_password("pw")
        admin = User(username="admin_x", email="admin@x.com", role="admin")
        admin.set_password("pw")
        db.session.add_all([u1, u2, admin])
        db.session.commit()

        # Torneo + Prova (nessuna iscrizione per rispettare la regola can_be_deleted)
        t = Tournament(name="TorneoDel", tournament_type="Amalfi")
        db.session.add(t)
        db.session.flush()
        p = Prova(
            tournament_id=t.id,
            number=1,
            name="ProvaDel",
            date=datetime.utcnow(),
            discipline="palla 9",
            distance=5,
            status="setup",
            current_round=0,
        )
        db.session.add(p)
        db.session.flush()

        # Director association (era la fonte dell'errore iniziale)
        db.session.add(
            TournamentDirector(
                user_id=admin.id, tournament_id=t.id, assigned_by_id=admin.id
            )
        )

        # Match + Rack (ammessi perché la regola blocca solo se ci sono iscrizioni)
        m = Match(
            prova_id=p.id,
            round_number=1,
            player1_id=u1.id,
            player2_id=u2.id,
            status="pending",
        )
        db.session.add(m)
        db.session.flush()
        db.session.add(Rack(match_id=m.id, rack_number=1, winner_id=None))

        # Classification (overall)
        db.session.add(Classification(tournament_id=t.id, user_id=u1.id, position=1))

        db.session.commit()

        # Pre-condizioni
        assert Tournament.query.get(t.id) is not None
        assert Prova.query.filter_by(tournament_id=t.id).count() == 1
        assert Match.query.filter_by(prova_id=p.id).count() == 1
        assert Rack.query.count() == 1
        assert Classification.query.filter_by(tournament_id=t.id).count() == 1
        assert TournamentDirector.query.filter_by(tournament_id=t.id).count() == 1

        # Azione: elimina tramite Service (atomicità + cascade)
        TournamentService.delete_tournament(t.id)

        # Verifiche: tutto sparito
        assert Tournament.query.get(t.id) is None
        assert Prova.query.filter_by(tournament_id=t.id).count() == 0
        assert Match.query.filter_by(prova_id=p.id).count() == 0
        assert Rack.query.count() == 0
        assert Classification.query.filter_by(tournament_id=t.id).count() == 0
        assert TournamentDirector.query.filter_by(tournament_id=t.id).count() == 0
