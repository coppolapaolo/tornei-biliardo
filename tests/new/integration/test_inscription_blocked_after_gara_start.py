"""Regression: la route POST /player/gara/<id>/inscribe deve rifiutare
le iscrizioni quando la gara è già stata avviata (status != INSCRIPTION).

Garantisce che il guard in routes/player/competitions.py:50 non venga
rimosso involontariamente in futuri refactor. Il guard è critico perché
permettere iscrizioni dopo l'avvio rompe l'integrità dello schedule
pre-generato (Bug 1 della PR #3) e della classifica.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Inscription, User
from models.base import db, utc_now
from models.status_enum import GaraStatus
from models.user.role_enum import UserRole


def _make_director(db_session) -> User:
    uid = str(uuid.uuid4())[:8]
    director = User(
        username=f"director_{uid}",
        email=f"director_{uid}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("x")
    db_session.add(director)
    db_session.commit()
    return director


def _make_gara_in_status(db_session, status: str) -> Gara:
    """Crea una gara nel `status` richiesto con finestra di iscrizione
    ancora valida — così l'eventuale fallimento NON può essere attribuito
    a inscription_start/inscription_end fuori range.
    """
    director = _make_director(db_session)
    gara = Gara(
        number=1,
        name=f"Gara test {status}",
        date=date.today() + timedelta(days=7),
        discipline="9_ball",
        distance=5,
        is_race_to=True,
        director_id=director.id,
        rounds_count=2,
        min_participants=2,
        status=status,
        inscription_start=utc_now() - timedelta(hours=1),
        inscription_end=utc_now() + timedelta(hours=24),
    )
    db_session.add(gara)
    db_session.commit()
    return gara


@pytest.mark.integration
class TestInscriptionBlockedAfterGaraStart:
    """Regression suite per il guard di status nella route iscrizione."""

    def test_route_blocks_inscription_when_gara_is_playing(
        self, logged_in_client, db_session
    ):
        """status=PLAYING: route deve rifiutare anche se le date di
        iscrizione sono ancora aperte. Nessuna Inscription creata.
        """
        gara = _make_gara_in_status(db_session, GaraStatus.PLAYING.value)
        client, user = logged_in_client(role="player")

        resp = client.post(f"/player/gara/{gara.id}/inscribe", follow_redirects=False)

        # Route fa redirect (302) verso index/dashboard quando rifiuta.
        assert resp.status_code in (302, 303)

        inscription = Inscription.query.filter_by(
            user_id=user.id, gara_id=gara.id
        ).first()
        assert (
            inscription is None
        ), "Nessuna iscrizione deve essere creata quando la gara è PLAYING"

    def test_route_blocks_inscription_when_gara_is_completed(
        self, logged_in_client, db_session
    ):
        """status=COMPLETED: stesso comportamento di PLAYING — nessuna
        iscrizione ammessa dopo la conclusione.
        """
        gara = _make_gara_in_status(db_session, GaraStatus.COMPLETED.value)
        client, user = logged_in_client(role="player")

        resp = client.post(f"/player/gara/{gara.id}/inscribe", follow_redirects=False)

        assert resp.status_code in (302, 303)
        assert (
            Inscription.query.filter_by(user_id=user.id, gara_id=gara.id).first()
            is None
        )

    def test_route_blocks_inscription_when_gara_is_setup(
        self, logged_in_client, db_session
    ):
        """status=SETUP: il direttore non ha ancora aperto le iscrizioni.
        Anche se le date sono nel range, la route deve rifiutare perché
        lo status non è INSCRIPTION.
        """
        gara = _make_gara_in_status(db_session, GaraStatus.SETUP.value)
        client, user = logged_in_client(role="player")

        resp = client.post(f"/player/gara/{gara.id}/inscribe", follow_redirects=False)

        assert resp.status_code in (302, 303)
        assert (
            Inscription.query.filter_by(user_id=user.id, gara_id=gara.id).first()
            is None
        )

    # Nota: il path positivo (status=INSCRIPTION → iscrizione creata) NON è
    # coperto qui perché soffre di flakiness in parallel test execution
    # (-n 4); è ampiamente coperto da test_gare_usecase_*, test_parity_waitlist
    # e test_participant_limits_waitlist_tdd. Qui ci interessa solo blindare
    # i tre stati che DEVONO rifiutare.
