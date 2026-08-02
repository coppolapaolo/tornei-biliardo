"""Regressione issue #58 — "auto-copia iscritti" non copiava nulla.

Il flag `copy_from_previous` esisteva solo lato client, dove precompilava i
*parametri* della nuova gara (sede, quota, disciplina...). Il server non lo
leggeva mai: il director apriva le iscrizioni e non trovava alcun iscritto,
pur avendo lasciato l'opzione attiva.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara, Inscription
from models.competition.services import GaraService


def _make_campionato(db_session, director_id):
    from models.campionato.services import TournamentService

    return TournamentService().create_campionato_with_director(
        name=f"Camp_{uuid.uuid4().hex[:6]}",
        creator_user_id=director_id,
        campionato_type="amalfi",
        is_active=True,
        planned_gare_count=3,
    )


def _make_gara(campionato_id, number, director_id, max_participants=None):
    return GaraService.create_gara(
        campionato_id=campionato_id,
        number=number,
        name=f"Gara {number}",
        date=date.today() + timedelta(days=number),
        location="Test Venue",
        rounds_count=1,
        min_participants=2,
        max_participants=max_participants,
        entry_fee=0.0,
        discipline="palla_9",
        distance=5,
        is_race_to=True,
        director_id=director_id,
        matchmaking_strategy="amalfi",
    )


@pytest.mark.integration
class TestCopyInscriptionsFromPreviousGara:

    def test_copies_active_inscriptions(
        self, db_session, isolated_director_user, isolated_players
    ):
        campionato = _make_campionato(db_session, isolated_director_user.id)
        gara1 = _make_gara(campionato.id, 1, isolated_director_user.id)
        gara2 = _make_gara(campionato.id, 2, isolated_director_user.id)

        roster = isolated_players[:4]
        for player in roster:
            InscriptionService.inscribe_user(player.id, gara1.id)
        db_session.commit()

        copied = InscriptionService.copy_inscriptions_from_gara(gara1.id, gara2.id)

        assert copied == 4
        assert Inscription.active_count_for_gara(gara2.id) == 4
        copied_ids = {
            i.user_id
            for i in db.session.query(Inscription).filter_by(gara_id=gara2.id).all()
        }
        assert copied_ids == {p.id for p in roster}

    def test_withdrawn_players_are_not_copied(
        self, db_session, isolated_director_user, isolated_players
    ):
        campionato = _make_campionato(db_session, isolated_director_user.id)
        gara1 = _make_gara(campionato.id, 1, isolated_director_user.id)
        gara2 = _make_gara(campionato.id, 2, isolated_director_user.id)

        for player in isolated_players[:3]:
            InscriptionService.inscribe_user(player.id, gara1.id)
        db_session.commit()

        withdrawn = (
            db.session.query(Inscription)
            .filter_by(gara_id=gara1.id, user_id=isolated_players[0].id)
            .one()
        )
        withdrawn.is_withdrawn = True
        db_session.commit()

        copied = InscriptionService.copy_inscriptions_from_gara(gara1.id, gara2.id)

        assert copied == 2
        copied_ids = {
            i.user_id
            for i in db.session.query(Inscription).filter_by(gara_id=gara2.id).all()
        }
        assert isolated_players[0].id not in copied_ids

    def test_is_idempotent(self, db_session, isolated_director_user, isolated_players):
        """Ricopiare non duplica: inscribe_user ritorna l'iscrizione esistente."""
        campionato = _make_campionato(db_session, isolated_director_user.id)
        gara1 = _make_gara(campionato.id, 1, isolated_director_user.id)
        gara2 = _make_gara(campionato.id, 2, isolated_director_user.id)

        for player in isolated_players[:3]:
            InscriptionService.inscribe_user(player.id, gara1.id)
        db_session.commit()

        InscriptionService.copy_inscriptions_from_gara(gara1.id, gara2.id)
        InscriptionService.copy_inscriptions_from_gara(gara1.id, gara2.id)

        assert db.session.query(Inscription).filter_by(gara_id=gara2.id).count() == 3


@pytest.mark.integration
class TestFindPreviousGaraInCampionato:

    def test_returns_gara_with_highest_lower_number(
        self, db_session, isolated_director_user
    ):
        campionato = _make_campionato(db_session, isolated_director_user.id)
        gara1 = _make_gara(campionato.id, 1, isolated_director_user.id)
        gara2 = _make_gara(campionato.id, 2, isolated_director_user.id)
        gara3 = _make_gara(campionato.id, 3, isolated_director_user.id)
        db_session.commit()

        assert InscriptionService.find_previous_gara_in_campionato(gara3).id == gara2.id
        assert InscriptionService.find_previous_gara_in_campionato(gara2).id == gara1.id

    def test_first_gara_has_no_previous(self, db_session, isolated_director_user):
        campionato = _make_campionato(db_session, isolated_director_user.id)
        gara1 = _make_gara(campionato.id, 1, isolated_director_user.id)
        db_session.commit()

        assert InscriptionService.find_previous_gara_in_campionato(gara1) is None

    def test_standalone_gara_has_no_previous(self, db_session, isolated_director_user):
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name=f"Standalone {uuid.uuid4().hex[:6]}",
            date=date.today() + timedelta(days=1),
            location="Test Venue",
            rounds_count=1,
            min_participants=2,
            entry_fee=0.0,
            discipline="palla_9",
            distance=5,
            is_race_to=True,
            director_id=isolated_director_user.id,
            matchmaking_strategy="amalfi",
        )
        db_session.commit()

        assert InscriptionService.find_previous_gara_in_campionato(gara) is None


@pytest.mark.integration
def test_create_gara_route_honours_copy_from_previous(
    db_session, isolated_director_user, isolated_players, client
):
    """Il POST di creazione gara con `copy_from_previous` porta gli iscritti."""
    campionato = _make_campionato(db_session, isolated_director_user.id)
    gara1 = _make_gara(campionato.id, 1, isolated_director_user.id)
    for player in isolated_players[:3]:
        InscriptionService.inscribe_user(player.id, gara1.id)
    db_session.commit()

    login = client.post(
        "/auth/login",
        data={"username": isolated_director_user.username, "password": "director123"},
        follow_redirects=True,
    )
    assert login.status_code == 200

    response = client.post(
        "/admin/gara/create",
        data={
            "campionato_id": str(campionato.id),
            "number": "2",
            "name": "Gara 2",
            "date": (date.today() + timedelta(days=5)).isoformat(),
            "time": "20:00",
            "location": "Test Venue",
            "available_tables": "2",
            "min_participants": "2",
            "entry_fee": "0",
            "discipline": "palla_9",
            "distance": "5",
            "rounds_count": "1",
            "copy_from_previous": "true",
        },
        follow_redirects=False,
    )

    assert response.status_code in (301, 302)

    created = (
        db.session.query(Gara)
        .filter_by(campionato_id=campionato.id, number=2)
        .one_or_none()
    )
    assert created is not None, "la gara 2 non è stata creata"
    assert Inscription.active_count_for_gara(created.id) == 3
