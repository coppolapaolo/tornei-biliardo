"""Issue #61 — link pubblico alla singola gara per iscriversi.

Il direttore condivide `/g/<token>` su una locandina o un post. Chi lo segue:

1. autenticato → arriva sulla gara e ci si trova già iscritto, con una dialog
   di conferma;
2. non autenticato → passa da login/registrazione e torna sulla gara, dove
   l'iscrizione resta un suo click sul pulsante.

E in ogni altro caso (link inesistente, iscrizioni non ancora aperte o già
chiuse, gara in corso o conclusa) la pagina deve dire cosa sta succedendo:
chi arriva da una locandina non ha altro contesto.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Inscription, User
from models.base import db, utc_now
from models.competition.services import GaraService
from models.status_enum import GaraStatus
from models.user.role_enum import UserRole


def _user(role: str = UserRole.PLAYER.value) -> User:
    unique = str(uuid.uuid4())[:8]
    user = User(
        username=f"{role}_{unique}",
        email=f"{role}_{unique}@test.local",
        role=role,
    )
    user.set_password("secret123")
    db.session.add(user)
    db.session.commit()
    return user


def _gara(director: User, **overrides) -> Gara:
    now = utc_now()
    params = dict(
        campionato_id=None,
        number=1,
        name="Trofeo della Locandina",
        date=date.today() + timedelta(days=10),
        location="Sala Test",
        rounds_count=3,
        min_participants=2,
        discipline="palla_9",
        distance=5,
        is_race_to=True,
        director_id=director.id,
        matchmaking_strategy="random",
        inscription_start=now - timedelta(days=1),
        inscription_end=now + timedelta(days=5),
    )
    params.update(overrides)
    gara = GaraService.create_gara(**params)
    gara.status = GaraStatus.INSCRIPTION.value
    db.session.commit()
    return gara


def _login(client, user: User) -> None:
    response = client.post(
        "/auth/login",
        data={"username": user.username, "password": "secret123"},
        follow_redirects=False,
    )
    assert response.status_code == 302


@pytest.mark.integration
class TestTokenGeneration:
    def test_every_gara_gets_a_token(self, db_session):
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)

        assert gara.public_token
        assert len(gara.public_token) >= 8

    def test_token_is_not_derived_from_the_id(self, db_session):
        """Il link non deve essere indovinabile a partire da quello vicino.

        Con un token derivato dall'id (o dall'id stesso) chi riceve il link di
        una gara ha in mano quello di tutte le altre.
        """
        from models.competition.models import generate_public_token

        director = _user(UserRole.DIRECTOR.value)
        first = _gara(director)
        second = _gara(director, number=2, name="Seconda")

        assert first.public_token != second.public_token
        assert first.public_token != str(first.id)
        assert second.public_token != str(second.id)

        # Casuale, non un contatore: 200 generazioni non devono collidere né
        # ripetersi.
        tokens = {generate_public_token() for _ in range(200)}
        assert len(tokens) == 200


@pytest.mark.integration
class TestAuthenticatedVisitor:
    def test_following_the_link_inscribes_the_player(self, client, db_session):
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)
        player = _user()
        _login(client, player)

        response = client.get(f"/g/{gara.public_token}")

        assert response.status_code == 302
        assert f"/admin/gara/{gara.id}" in response.headers["Location"]
        assert (
            Inscription.query.filter_by(user_id=player.id, gara_id=gara.id).first()
            is not None
        )

    def test_the_landing_page_confirms_with_a_dialog(self, client, db_session):
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)
        player = _user()
        _login(client, player)

        page = client.get(f"/g/{gara.public_token}", follow_redirects=True)

        body = page.get_data(as_text=True)
        assert "Sei iscritto!" in body
        assert "data-page-modal" in body

    def test_visiting_twice_does_not_duplicate_the_inscription(
        self, client, db_session
    ):
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)
        player = _user()
        _login(client, player)

        client.get(f"/g/{gara.public_token}")
        page = client.get(f"/g/{gara.public_token}", follow_redirects=True)

        assert (
            Inscription.query.filter_by(user_id=player.id, gara_id=gara.id).count() == 1
        )
        assert "Sei già iscritto" in page.get_data(as_text=True)

    def test_the_director_of_the_gara_is_not_inscribed_by_their_own_link(
        self, client, db_session
    ):
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)
        _login(client, director)

        client.get(f"/g/{gara.public_token}")

        assert (
            Inscription.query.filter_by(user_id=director.id, gara_id=gara.id).first()
            is None
        )


@pytest.mark.integration
class TestAnonymousVisitor:
    def test_the_link_sends_the_guest_to_login_keeping_the_destination(
        self, client, db_session
    ):
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)

        response = client.get(f"/g/{gara.public_token}")

        assert response.status_code == 302
        location = response.headers["Location"]
        assert "/auth/login" in location
        assert f"%2Fg%2F{gara.public_token}" in location or (
            f"/g/{gara.public_token}" in location
        )

    def test_after_login_the_user_lands_on_the_gara_without_being_inscribed(
        self, client, db_session
    ):
        """Punto 2 dell'issue: l'iscrizione resta un gesto consapevole.

        Un login non deve iscrivere nessuno a niente: l'utente arriva sulla
        gara e trova il pulsante.
        """
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)
        player = _user()

        invite = f"/g/{gara.public_token}"
        redirect_to_login = client.get(invite)
        login_url = redirect_to_login.headers["Location"]

        after_login = client.post(
            login_url,
            data={"username": player.username, "password": "secret123"},
            follow_redirects=False,
        )

        assert after_login.status_code == 302
        assert f"/g/{gara.public_token}" in after_login.headers["Location"]

        landing = client.get(after_login.headers["Location"], follow_redirects=True)

        assert (
            Inscription.query.filter_by(user_id=player.id, gara_id=gara.id).first()
            is None
        ), "il login non deve iscrivere: l'ultimo passo è un click dell'utente"
        body = landing.get_data(as_text=True)
        assert "Puoi iscriverti" in body
        # Il pulsante deve esserci davvero: prima di #61 la pagina della gara
        # non aveva alcun modo di iscriversi, si poteva solo dalle card.
        assert f'action="/player/gara/{gara.id}/inscribe"' in body

    def test_the_inscribe_button_on_the_gara_page_completes_the_flow(
        self, client, db_session
    ):
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)
        player = _user()
        _login(client, player)

        response = client.post(
            f"/player/gara/{gara.id}/inscribe",
            data={"next": f"/admin/gara/{gara.id}"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert f"/admin/gara/{gara.id}" in response.headers["Location"]
        assert (
            Inscription.query.filter_by(user_id=player.id, gara_id=gara.id).first()
            is not None
        )


@pytest.mark.integration
class TestNextIsNotAnOpenRedirect:
    def test_login_ignores_an_external_destination(self, client, db_session):
        """`next` arriva dall'URL, quindi da chiunque: fuori dal sito non va."""
        player = _user()

        response = client.post(
            "/auth/login?next=https://sito-falso.example/login",
            data={"username": player.username, "password": "secret123"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "sito-falso.example" not in response.headers["Location"]
        assert "/dashboard" in response.headers["Location"]


@pytest.mark.integration
class TestUnavailableGara:
    def test_an_unknown_token_gets_a_dedicated_page(self, client, db_session):
        response = client.get("/g/nonesistente")

        assert response.status_code == 404
        assert "non porta a nessuna gara" in response.get_data(as_text=True)

    def test_a_deleted_gara_is_treated_as_unknown(self, client, db_session):
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)
        token = gara.public_token
        gara.soft_delete()
        db.session.commit()

        response = client.get(f"/g/{token}")

        assert response.status_code == 404

    def test_inscriptions_not_open_yet_show_the_dates(self, client, db_session):
        director = _user(UserRole.DIRECTOR.value)
        now = utc_now()
        gara = _gara(
            director,
            inscription_start=now + timedelta(days=3),
            inscription_end=now + timedelta(days=10),
        )
        player = _user()
        _login(client, player)

        page = client.get(f"/g/{gara.public_token}", follow_redirects=True)

        body = page.get_data(as_text=True)
        assert "Iscrizioni non ancora aperte" in body
        assert "Iscrizioni dal" in body
        assert (
            Inscription.query.filter_by(user_id=player.id, gara_id=gara.id).first()
            is None
        )

    def test_closed_inscriptions_say_so(self, client, db_session):
        director = _user(UserRole.DIRECTOR.value)
        now = utc_now()
        gara = _gara(
            director,
            inscription_start=now - timedelta(days=10),
            inscription_end=now - timedelta(days=1),
        )
        player = _user()
        _login(client, player)

        page = client.get(f"/g/{gara.public_token}", follow_redirects=True)

        assert "Iscrizioni chiuse" in page.get_data(as_text=True)
        assert (
            Inscription.query.filter_by(user_id=player.id, gara_id=gara.id).first()
            is None
        )

    def test_a_completed_gara_says_so(self, client, db_session):
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)
        gara.status = GaraStatus.COMPLETED.value
        db.session.commit()
        player = _user()
        _login(client, player)

        page = client.get(f"/g/{gara.public_token}", follow_redirects=True)

        assert "Gara conclusa" in page.get_data(as_text=True)

    def test_a_gara_in_progress_says_so(self, client, db_session):
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)
        gara.status = GaraStatus.PLAYING.value
        db.session.commit()
        player = _user()
        _login(client, player)

        page = client.get(f"/g/{gara.public_token}", follow_redirects=True)

        assert "Gara già iniziata" in page.get_data(as_text=True)


@pytest.mark.integration
class TestDirectorSeesTheLink:
    def test_the_manager_finds_the_link_on_the_gara_page(self, client, db_session):
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)
        _login(client, director)

        page = client.get(f"/admin/gara/{gara.id}")

        body = page.get_data(as_text=True)
        assert "Link pubblico di iscrizione" in body
        assert f"/g/{gara.public_token}" in body

    def test_a_player_does_not_see_the_link(self, client, db_session):
        director = _user(UserRole.DIRECTOR.value)
        gara = _gara(director)
        player = _user()
        _login(client, player)

        page = client.get(f"/admin/gara/{gara.id}")

        assert gara.public_token not in page.get_data(as_text=True)
