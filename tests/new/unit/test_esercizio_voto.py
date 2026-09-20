"""Il voto degli esercizi: chi, quanto, quante volte (ADR-065, D6)."""

from __future__ import annotations

import uuid

import pytest

from models.challenge.models import Challenge, ChallengeAttempt, ChallengeRating
from models.challenge.rating_service import ChallengeRatingService
from models.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from models.user.models import User
from models.user.role_enum import UserRole


def _utente(db_session):
    u = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@test.com",
        role=UserRole.PLAYER.value,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.flush()
    return u


def _esercizio(db_session):
    c = Challenge(
        title=f"Voto {uuid.uuid4().hex[:6]}",
        description="x",
        image_path="t.jpg",
        pass_fail_only=False,
        is_active=True,
    )
    db_session.add(c)
    db_session.flush()
    return c


def _ha_provato(db_session, user, challenge, completed=True):
    db_session.add(
        ChallengeAttempt(
            user_id=user.id, challenge_id=challenge.id, score=3, completed=completed
        )
    )
    db_session.flush()


def test_chi_non_ha_provato_non_vota(db_session):
    c, u = _esercizio(db_session), _utente(db_session)
    assert not ChallengeRatingService.can_rate(u.id, c.id)
    with pytest.raises(PermissionDeniedError):
        ChallengeRatingService.rate(u.id, c.id, 5)


def test_una_prova_lasciata_a_meta_non_basta(db_session):
    c, u = _esercizio(db_session), _utente(db_session)
    _ha_provato(db_session, u, c, completed=False)
    assert not ChallengeRatingService.can_rate(u.id, c.id)


def test_chi_ha_provato_vota_e_i_numeri_tornano_aggiornati(db_session):
    c, a, b = _esercizio(db_session), _utente(db_session), _utente(db_session)
    _ha_provato(db_session, a, c)
    _ha_provato(db_session, b, c)
    ChallengeRatingService.rate(a.id, c.id, 5)
    numeri = ChallengeRatingService.rate(b.id, c.id, 2)
    assert numeri.rating_count == 2
    assert numeri.rating_average == pytest.approx(3.5)
    assert numeri.players == 2
    assert ChallengeRatingService.get(a.id, c.id) == 5


def test_rivotare_sostituisce(db_session):
    c, u = _esercizio(db_session), _utente(db_session)
    _ha_provato(db_session, u, c)
    ChallengeRatingService.rate(u.id, c.id, 2)
    numeri = ChallengeRatingService.rate(u.id, c.id, 4)
    assert numeri.rating_count == 1
    assert numeri.rating_average == pytest.approx(4.0)
    assert db_session.query(ChallengeRating).filter_by(challenge_id=c.id).count() == 1


@pytest.mark.parametrize("voto", [0, 6, -1, "tanto", None, 3.7, True])
def test_fuori_da_uno_cinque_si_rifiuta(db_session, voto):
    c, u = _esercizio(db_session), _utente(db_session)
    _ha_provato(db_session, u, c)
    with pytest.raises(ValidationError):
        ChallengeRatingService.rate(u.id, c.id, voto)


def test_il_voto_si_puo_togliere(db_session):
    c, u = _esercizio(db_session), _utente(db_session)
    _ha_provato(db_session, u, c)
    ChallengeRatingService.rate(u.id, c.id, 4)
    numeri = ChallengeRatingService.clear(u.id, c.id)
    assert numeri.rating_count == 0 and numeri.rating_average is None
    assert ChallengeRatingService.get(u.id, c.id) is None
    # toglierlo due volte non è un errore
    ChallengeRatingService.clear(u.id, c.id)


def test_esercizio_inesistente(db_session):
    with pytest.raises(NotFoundError):
        ChallengeRatingService.rate(_utente(db_session).id, 999_999, 3)
