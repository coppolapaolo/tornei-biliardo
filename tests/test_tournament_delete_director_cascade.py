# tests/test_tournament_delete_director_cascade.py
import pytest
from models import db, Tournament
from models.user.models import TournamentDirector


@pytest.mark.usefixtures("app")
def test_delete_tournament_with_director_cascade(
    admin_user, director_user, tournament, assign_director
):
    # Precondizione: torneo con almeno un direttore assegnato
    assign_director(director_user, tournament, admin_user)
    assert (
        TournamentDirector.query.filter_by(
            tournament_id=tournament.id, user_id=director_user.id
        ).count()
        == 1
    )

    # Azione: cancello il torneo
    db.session.delete(tournament)
    db.session.commit()

    # Verifica: il torneo è stato rimosso e l'associazione director è stata cascata
    assert db.session.get(Tournament, tournament.id) is None
    assert TournamentDirector.query.filter_by(tournament_id=tournament.id).count() == 0
