"""Le categorie si assegnano dalla schermata della gara (ADR-049).

Il servizio ha i suoi unit test; qui si verifica il percorso vero — richiesta →
route → servizio → risposta — e i permessi, che sono il punto delicato: la
categoria decide se le partite di un giocatore muovono l'Elo, quindi
autoassegnarsela sarebbe un pulsante «fammi contare».
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import List

import pytest

from models import Campionato, Categoria, Gara, Inscription, User
from models.base import utc_now
from models.categoria.service import CategoriaService
from models.competition.inscription_service import InscriptionService
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _players(db_session, count: int) -> List[User]:
    batch = str(uuid.uuid4())[:8]
    users = []
    for index in range(count):
        user = User(
            username=f"ct_{index}_{batch}",
            email=f"ct_{index}_{batch}@test.com",
            role=UserRole.PLAYER.value,
            onboarding_completed=True,
        )
        user.set_password("player123")
        users.append(user)
    db_session.add_all(users)
    db_session.commit()
    return users


def _gara(db_session, *, has_handicap=True, campionato=None):
    batch = str(uuid.uuid4())[:8]
    director = User(
        username=f"dirc_{batch}",
        email=f"dirc_{batch}@test.com",
        role=UserRole.DIRECTOR.value,
        onboarding_completed=True,
    )
    director.set_password("director123")
    db_session.add(director)
    db_session.flush()

    gara = Gara(
        campionato_id=campionato.id if campionato else None,
        director_id=director.id,
        number=db_session.query(Gara).count() + 1,
        name=f"Gara {batch}",
        date=date.today() + timedelta(days=7),
        discipline="9_ball",
        distance=3,
        is_race_to=True,
        rounds_count=3,
        min_participants=4,
        max_participants=8,
        matchmaking_strategy="direct_elimination",
        first_round_policy="random",
        has_handicap=has_handicap,
    )
    db_session.add(gara)
    db_session.commit()

    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    db_session.commit()
    return gara, director


def _login(client, user, password="player123"):
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": password},
        follow_redirects=True,
    )


def _inscription_of(gara, user) -> Inscription:
    return Inscription.query.filter_by(gara_id=gara.id, user_id=user.id).one()


def _assegna(client, gara, inscription, nome):
    return client.post(
        f"/admin/gara/{gara.id}/inscription/{inscription.id}/categoria",
        json={"name": nome},
    )


class TestCreaAssegnando:
    def test_un_nome_nuovo_crea_la_categoria_e_la_assegna(self, db_session, client):
        gara, director = _gara(db_session)
        giocatore = _players(db_session, 1)[0]
        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()
        _login(client, director, "director123")

        resp = _assegna(client, gara, _inscription_of(gara, giocatore), "B")

        assert resp.status_code == 200
        dati = resp.get_json()
        assert dati["success"] is True
        assert dati["categoria"]["name"] == "B"
        assert dati["elenco"] == ["B"]
        assert dati["senza_categoria"] == 0
        assert _inscription_of(gara, giocatore).categoria.name == "B"

    def test_l_elenco_torna_aggiornato_per_le_altre_righe(self, db_session, client):
        """Il combo delle altre righe deve trovare la voce nuova senza ricarica."""
        gara, director = _gara(db_session)
        uno, due = _players(db_session, 2)
        for giocatore in (uno, due):
            InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()
        _login(client, director, "director123")

        _assegna(client, gara, _inscription_of(gara, uno), "B")
        resp = _assegna(client, gara, _inscription_of(gara, due), "A")

        assert resp.get_json()["elenco"] == ["A", "B"]

    def test_il_nome_vuoto_toglie_la_categoria(self, db_session, client):
        gara, director = _gara(db_session)
        giocatore = _players(db_session, 1)[0]
        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()
        _login(client, director, "director123")
        ins = _inscription_of(gara, giocatore)
        _assegna(client, gara, ins, "B")

        resp = _assegna(client, gara, _inscription_of(gara, giocatore), "")

        assert resp.get_json()["categoria"] is None
        assert _inscription_of(gara, giocatore).categoria_id is None
        assert resp.get_json()["senza_categoria"] == 1


class TestPermessi:
    def test_il_giocatore_non_si_assegna_la_categoria(self, db_session, client):
        """È il vincolo che protegge l'Elo, non una formalità."""
        gara, _director = _gara(db_session)
        giocatore = _players(db_session, 1)[0]
        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()
        _login(client, giocatore)

        resp = _assegna(client, gara, _inscription_of(gara, giocatore), "N")

        assert resp.status_code == 403
        assert _inscription_of(gara, giocatore).categoria_id is None

    def test_un_direttore_estraneo_non_entra(self, db_session, client):
        gara, _director = _gara(db_session)
        altra_gara, altro_direttore = _gara(db_session)
        giocatore = _players(db_session, 1)[0]
        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()
        _login(client, altro_direttore, "director123")

        resp = _assegna(client, gara, _inscription_of(gara, giocatore), "B")

        assert resp.status_code == 403


class TestAntiIDOR:
    def test_l_iscrizione_di_un_altra_gara_non_si_tocca(self, db_session, client):
        gara, director = _gara(db_session)
        altra, _altro = _gara(db_session)
        giocatore = _players(db_session, 1)[0]
        InscriptionService.inscribe_user(giocatore.id, altra.id)
        db_session.commit()
        _login(client, director, "director123")

        resp = client.post(
            f"/admin/gara/{gara.id}/inscription/"
            f"{_inscription_of(altra, giocatore).id}/categoria",
            json={"name": "B"},
        )

        assert resp.status_code == 404

    def test_una_categoria_di_un_altra_competizione_non_si_rinomina(
        self, db_session, client
    ):
        gara, director = _gara(db_session)
        altra, _altro = _gara(db_session)
        estranea = CategoriaService.create(altra, "B")
        db_session.commit()
        _login(client, director, "director123")

        client.post(
            f"/admin/gara/{gara.id}/categorie/{estranea.id}/rename",
            data={"name": "Rubata"},
            follow_redirects=True,
        )

        assert db_session.get(Categoria, estranea.id).name == "B"


class TestFinestraDiModifica:
    def test_a_gara_avviata_risponde_409(self, db_session, client):
        gara, director = _gara(db_session)
        giocatore = _players(db_session, 1)[0]
        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()
        ins = _inscription_of(gara, giocatore)

        gara.status = "playing"
        gara.current_round = 1
        db_session.commit()
        _login(client, director, "director123")

        resp = _assegna(client, gara, ins, "B")

        assert resp.status_code == 409


class TestElencoCondiviso:
    def test_la_categoria_si_riporta_alla_gara_successiva(self, db_session, client):
        """La proprietà che giustifica l'ambito «competizione»."""
        campionato = Campionato(name=f"Camp {uuid.uuid4().hex[:6]}")
        db_session.add(campionato)
        db_session.commit()
        prima, director = _gara(db_session, campionato=campionato)
        seconda, _altro = _gara(db_session, campionato=campionato)
        giocatore = _players(db_session, 1)[0]

        # Per le gare di un campionato il permesso viene dall'assegnazione sul
        # campionato: `gara.director_id` conta solo per le standalone.
        from models.status_enum import EntityType
        from models.user.models import DirectorAssignment

        db_session.add(
            DirectorAssignment(
                user_id=director.id,
                entity_type=EntityType.CAMPIONATO.value,
                entity_id=campionato.id,
                assigned_by_id=director.id,
            )
        )
        db_session.commit()

        InscriptionService.inscribe_user(giocatore.id, prima.id)
        db_session.commit()
        _login(client, director, "director123")
        resp = _assegna(client, prima, _inscription_of(prima, giocatore), "B")
        assert resp.status_code == 200

        InscriptionService.inscribe_user(giocatore.id, seconda.id)
        db_session.commit()

        assert _inscription_of(seconda, giocatore).categoria.name == "B"
