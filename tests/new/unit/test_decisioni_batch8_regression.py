"""Regression (review 2026-06, batch 8): decisioni co-direttori e decrypt.

- Decisione 1: co-direttore solo con role=director (il service accettava
  qualsiasi non-admin, la UI offriva solo director — allineati).
- Decisione 2: decrypt fallita logga ERROR (evento GlitchTip), non warning.
"""

import base64
import logging
import uuid

import pytest

from models.user.models import User


def _make_user(db_session, role):
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"b8_{role}_{uid}", email=f"b8_{role}_{uid}@t.com", role=role)
    user.set_password("x")
    db_session.add(user)
    db_session.commit()
    return user


def _make_gara(db_session, director):
    from datetime import date, time, timedelta

    from models.competition.models import Gara

    gara = Gara(
        name=f"B8 {uuid.uuid4().hex[:6]}",
        number=1,
        date=date.today() + timedelta(days=7),
        time=time(18, 0),
        discipline="8_ball",
        distance=5,
        rounds_count=3,
        min_participants=2,
        max_participants=10,
        director_id=director.id,
        status="setup",
    )
    db_session.add(gara)
    db_session.commit()
    return gara


@pytest.mark.unit
class TestCoDirectorRoleValidation:
    def test_gara_add_director_rejects_player(self, db_session):
        from models.competition.services import GaraService

        director = _make_user(db_session, "director")
        player = _make_user(db_session, "player")
        gara = _make_gara(db_session, director)

        with pytest.raises(ValueError):
            GaraService.add_director(
                gara_id=gara.id, user_id=player.id, assigned_by_id=director.id
            )

    def test_gara_add_director_accepts_director(self, db_session):
        from models.competition.services import GaraService
        from models.user.models import DirectorAssignment

        director = _make_user(db_session, "director")
        other_director = _make_user(db_session, "director")
        gara = _make_gara(db_session, director)

        assert (
            GaraService.add_director(
                gara_id=gara.id, user_id=other_director.id, assigned_by_id=director.id
            )
            is True
        )
        assert (
            DirectorAssignment.query.filter_by(
                entity_type="gara", entity_id=gara.id, user_id=other_director.id
            ).first()
            is not None
        )

    def test_campionato_add_director_rejects_player(self, db_session):
        from models.campionato.models import Campionato
        from models.campionato.tournament_service import TournamentService

        director = _make_user(db_session, "director")
        player = _make_user(db_session, "player")
        campionato = Campionato(
            name=f"B8 Camp {uuid.uuid4().hex[:6]}",
            campionato_type="amalfi",
            is_active=True,
        )
        db_session.add(campionato)
        db_session.commit()

        with pytest.raises(ValueError):
            TournamentService().add_director(
                campionato_id=campionato.id,
                user_id=player.id,
                assigned_by_id=director.id,
            )


@pytest.mark.unit
def test_decrypt_failure_logs_error(caplog):
    """Decifratura fallita → log ERROR (catturato da GlitchTip), non warning."""
    from utils.encryption import encryption_manager

    garbage = base64.urlsafe_b64encode(b"non-un-token-fernet").decode()
    with caplog.at_level(logging.WARNING, logger="utils.encryption"):
        result = encryption_manager.decrypt(garbage)

    assert result == ""  # degrado garbato: il sito resta su
    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "atteso un log ERROR per la decifratura fallita"
