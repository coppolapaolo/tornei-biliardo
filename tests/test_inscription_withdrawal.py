import pytest
from models import db
from models.user.services import UserDeletionService
from models.competition.models import Inscription


@pytest.mark.usefixtures("app")
def test_withdraw_marks_started_prova(player_user, started_prova, admin_user):
    ins = Inscription(user_id=player_user.id, prova_id=started_prova.id)
    db.session.add(ins)
    db.session.commit()

    UserDeletionService.delete_user(player_user)

    db.session.refresh(ins)
    assert ins.is_withdrawn is True
    assert (
        ins.withdrawn_at is not None
    )  # policy ora è a livello Prova, non su Inscription
