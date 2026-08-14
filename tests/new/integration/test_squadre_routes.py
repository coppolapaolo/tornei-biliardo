"""Le squadre si scelgono e si governano dalle schermate (US-1, 2, 3, 8, 9, 11).

Il servizio ha i suoi unit test; qui si verifica il percorso vero: form →
route → servizio → pagina, con i permessi che decidono chi vede cosa. È il
livello a cui si scoprono gli errori che un test di servizio non vede — un
campo che non compare, una route che non esiste, un permesso applicato solo
nel template.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import List

import pytest

from models import Campionato, Gara, Inscription, Squadra, User
from models.base import utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.squadra.service import SquadraService
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _players(db_session, count: int, squadra_profilo=None) -> List[User]:
    batch = str(uuid.uuid4())[:8]
    users = []
    for index in range(count):
        user = User(
            username=f"sq_{index}_{batch}",
            email=f"sq_{index}_{batch}@test.com",
            role=UserRole.PLAYER.value,
            squadra=squadra_profilo,
            onboarding_completed=True,
        )
        user.set_password("player123")
        users.append(user)
    db_session.add_all(users)
    db_session.commit()
    return users


def _gara(db_session, *, separate_teammates=True, campionato=None) -> Gara:
    batch = str(uuid.uuid4())[:8]
    director = User(
        username=f"dir_{batch}",
        email=f"dir_{batch}@test.com",
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
        separate_teammates=separate_teammates,
    )
    db_session.add(gara)
    db_session.commit()

    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    db_session.commit()
    return gara


def _login(client, user, password="player123"):
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": password},
        follow_redirects=True,
    )


def _inscription_of(gara, user) -> Inscription:
    return Inscription.query.filter_by(gara_id=gara.id, user_id=user.id).one()


class TestSquadraDalProfilo:
    def test_il_testo_del_profilo_precompila_l_iscrizione(self, db_session):
        """US-1: il profilo si legge una volta sola, all'iscrizione."""
        gara = _gara(db_session)
        squadra = SquadraService.create(gara, "Circolo Nord")
        db_session.commit()
        giocatore = _players(db_session, 1, squadra_profilo="circolo nord")[0]

        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()

        assert _inscription_of(gara, giocatore).squadra_id == squadra.id

    def test_senza_corrispondenza_nasce_senza_squadra(self, db_session):
        gara = _gara(db_session)
        SquadraService.create(gara, "Circolo Nord")
        db_session.commit()
        giocatore = _players(db_session, 1, squadra_profilo="Biliardo Sud")[0]

        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()

        assert _inscription_of(gara, giocatore).squadra_id is None

    def test_gara_senza_squadre_ignora_il_profilo(self, db_session):
        gara = _gara(db_session, separate_teammates=False)
        giocatore = _players(db_session, 1, squadra_profilo="Circolo Nord")[0]

        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()

        assert _inscription_of(gara, giocatore).squadra_id is None
        assert SquadraService.list_for_gara(gara) == []


class TestSceltaDelGiocatore:
    def test_sceglie_una_voce_esistente(self, client, db_session):
        gara = _gara(db_session)
        squadra = SquadraService.create(gara, "Circolo Nord")
        db_session.commit()
        giocatore = _players(db_session, 1)[0]
        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()
        iscrizione = _inscription_of(gara, giocatore)

        _login(client, giocatore)
        client.post(
            f"/admin/gara/{gara.id}/inscription/{iscrizione.id}/squadra",
            data={"squadra_id": str(squadra.id)},
            follow_redirects=True,
        )

        assert _inscription_of(gara, giocatore).squadra_id == squadra.id

    def test_nomi_simili_mostrati_prima_di_crearne_una_nuova(self, client, db_session):
        """US-2: il doppione si fa notare prima di nascere."""
        gara = _gara(db_session)
        SquadraService.create(gara, "Circolo Nord")
        db_session.commit()
        giocatore = _players(db_session, 1)[0]
        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()
        iscrizione = _inscription_of(gara, giocatore)

        _login(client, giocatore)
        pagina = client.post(
            f"/admin/gara/{gara.id}/inscription/{iscrizione.id}/squadra",
            data={"squadra_id": "__new__", "new_name": "Circolo Nord Udine"},
            follow_redirects=True,
        ).get_data(as_text=True)

        assert "Circolo Nord" in pagina
        assert len(SquadraService.list_for_gara(gara)) == 1, "creata comunque"

        # Confermando, la voce nuova nasce e viene assegnata.
        client.post(
            f"/admin/gara/{gara.id}/inscription/{iscrizione.id}/squadra",
            data={
                "squadra_id": "__new__",
                "new_name": "Circolo Nord Udine",
                "confirm_new": "on",
            },
            follow_redirects=True,
        )
        assert len(SquadraService.list_for_gara(gara)) == 2
        assert _inscription_of(gara, giocatore).squadra.name == "Circolo Nord Udine"

    def test_senza_squadra_e_una_scelta(self, client, db_session):
        gara = _gara(db_session)
        squadra = SquadraService.create(gara, "Circolo Nord")
        db_session.commit()
        giocatore = _players(db_session, 1)[0]
        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()
        iscrizione = _inscription_of(gara, giocatore)
        iscrizione.squadra_id = squadra.id
        db_session.commit()

        _login(client, giocatore)
        client.post(
            f"/admin/gara/{gara.id}/inscription/{iscrizione.id}/squadra",
            data={"squadra_id": ""},
            follow_redirects=True,
        )

        assert _inscription_of(gara, giocatore).squadra_id is None

    def test_non_puo_toccare_l_iscrizione_di_un_altro(self, client, db_session):
        gara = _gara(db_session)
        squadra = SquadraService.create(gara, "Circolo Nord")
        db_session.commit()
        mio, altrui = _players(db_session, 2)
        for player in (mio, altrui):
            InscriptionService.inscribe_user(player.id, gara.id)
        db_session.commit()
        iscrizione_altrui = _inscription_of(gara, altrui)

        _login(client, mio)
        client.post(
            f"/admin/gara/{gara.id}/inscription/{iscrizione_altrui.id}/squadra",
            data={"squadra_id": str(squadra.id)},
            follow_redirects=True,
        )

        assert _inscription_of(gara, altrui).squadra_id is None

    def test_dopo_il_sorteggio_e_rifiutata(self, client, db_session):
        """US-11: rifiutata con un messaggio, non accettata e ignorata."""
        gara = _gara(db_session)
        squadra = SquadraService.create(gara, "Circolo Nord")
        db_session.commit()
        giocatori = _players(db_session, 4)
        for player in giocatori:
            InscriptionService.inscribe_user(player.id, gara.id)
        db_session.commit()
        iscrizione = _inscription_of(gara, giocatori[0])
        RoundService.start_first_round(gara.id)
        db_session.commit()

        _login(client, giocatori[0])
        pagina = client.post(
            f"/admin/gara/{gara.id}/inscription/{iscrizione.id}/squadra",
            data={"squadra_id": str(squadra.id)},
            follow_redirects=True,
        ).get_data(as_text=True)

        assert _inscription_of(gara, giocatori[0]).squadra_id is None
        assert "primo turno" in pagina


class TestElencoDelDirector:
    def test_crea_rinomina_unisci(self, client, db_session):
        gara = _gara(db_session)
        giocatore = _players(db_session, 1)[0]
        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()
        director = db_session.get(User, gara.director_id)

        _login(client, director, password="director123")

        client.post(
            f"/admin/gara/{gara.id}/squadre/create",
            data={"name": "Circolo Alfa"},
            follow_redirects=True,
        )
        client.post(
            f"/admin/gara/{gara.id}/squadre/create",
            data={"name": "C. Alfa"},
            follow_redirects=True,
        )
        elenco = SquadraService.list_for_gara(gara)
        assert len(elenco) == 2

        doppione = next(s for s in elenco if s.name == "C. Alfa")
        buona = next(s for s in elenco if s.name == "Circolo Alfa")
        iscrizione = _inscription_of(gara, giocatore)
        iscrizione.squadra_id = doppione.id
        db_session.commit()

        client.post(
            f"/admin/gara/{gara.id}/squadre/{buona.id}/rename",
            data={"name": "Circolo Alfa Udine"},
            follow_redirects=True,
        )
        client.post(
            f"/admin/gara/{gara.id}/squadre/{doppione.id}/merge",
            data={"target_id": str(buona.id)},
            follow_redirects=True,
        )

        rimaste = SquadraService.list_for_gara(gara)
        assert [s.name for s in rimaste] == ["Circolo Alfa Udine"]
        # US-3: l'unione riassegna le iscrizioni, non le perde.
        assert _inscription_of(gara, giocatore).squadra_id == buona.id

    def test_corregge_la_squadra_di_un_iscritto(self, client, db_session):
        """US-9: chi rappresenta chi quella sera lo sa il direttore."""
        gara = _gara(db_session)
        squadra = SquadraService.create(gara, "Circolo Nord")
        db_session.commit()
        giocatore = _players(db_session, 1)[0]
        InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()
        iscrizione = _inscription_of(gara, giocatore)
        director = db_session.get(User, gara.director_id)

        _login(client, director, password="director123")
        client.post(
            f"/admin/gara/{gara.id}/inscription/{iscrizione.id}/squadra",
            data={"squadra_id": str(squadra.id)},
            follow_redirects=True,
        )

        assert _inscription_of(gara, giocatore).squadra_id == squadra.id

    def test_un_estraneo_non_governa_l_elenco(self, client, db_session):
        gara = _gara(db_session)
        estraneo = _players(db_session, 1)[0]

        _login(client, estraneo)
        risposta = client.post(
            f"/admin/gara/{gara.id}/squadre/create", data={"name": "Abusiva"}
        )

        assert risposta.status_code == 403
        assert SquadraService.list_for_gara(gara) == []

    def test_l_elenco_del_campionato_e_condiviso(self, client, db_session):
        """US-2: alla seconda gara le squadre sono già lì."""
        campionato = Campionato(name=f"Camp {uuid.uuid4().hex[:6]}")
        db_session.add(campionato)
        db_session.commit()
        prima = _gara(db_session, campionato=campionato)
        seconda = _gara(db_session, campionato=campionato)
        director = db_session.get(User, prima.director_id)
        # `directors` è una property calcolata: l'assegnazione si scrive sulla
        # tabella, non sulla lista.
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

        _login(client, director, password="director123")
        client.post(
            f"/admin/gara/{prima.id}/squadre/create",
            data={"name": "Circolo Condiviso"},
            follow_redirects=True,
        )

        assert [s.name for s in SquadraService.list_for_gara(seconda)] == [
            "Circolo Condiviso"
        ]
        assert Squadra.query.filter_by(campionato_id=campionato.id).count() == 1


class TestSchermate:
    def test_il_campo_squadra_compare_solo_dove_serve(self, client, db_session):
        con = _gara(db_session)
        senza = _gara(db_session, separate_teammates=False)
        giocatore = _players(db_session, 1)[0]
        for gara in (con, senza):
            InscriptionService.inscribe_user(giocatore.id, gara.id)
        db_session.commit()

        _login(client, giocatore)
        pagina_con = client.get(f"/admin/gara/{con.id}").get_data(as_text=True)
        pagina_senza = client.get(f"/admin/gara/{senza.id}").get_data(as_text=True)

        assert "La tua squadra" in pagina_con
        assert "La tua squadra" not in pagina_senza

    def test_il_giocatore_vede_il_campo_profilo(self, client, db_session):
        giocatore = _players(db_session, 1, squadra_profilo="Circolo Nord")[0]
        _login(client, giocatore)

        pagina = client.get("/player/profile/edit").get_data(as_text=True)
        assert 'name="squadra"' in pagina
        assert "Circolo Nord" in pagina


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
