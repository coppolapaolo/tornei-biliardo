# tests/test_user_delete_director_reassign.py
import pytest
from models.user.services import UserDeletionService
from models.user.models import TournamentDirector


@pytest.mark.usefixtures("app")
def test_director_reassigned_to_admin(
    admin_user, director_user, tournament, assign_director
):
    # Precondizione: il director_user è l'unico direttore del torneo
    assign_director(director_user, tournament, admin_user)  # <-- UNICA creazione

    # Azione: cancello il director_user
    UserDeletionService.delete_user(director_user)

    # Verifica: il ruolo di direttore è stato riassegnato all'admin_user
    td_admin = TournamentDirector.query.filter_by(
        tournament_id=tournament.id, user_id=admin_user.id
    ).one_or_none()
    assert td_admin is not None

    # Verifica: il director_user non è più direttore di quel torneo
    assert TournamentDirector.query.filter_by(
        tournament_id=tournament.id, user_id=director_user.id
    ).count() == 0
