"""Competizione di prova (ADR-058): chi la vede, dal client HTTP.

Il filtro di visibilità è un listener di sessione che legge `current_user`:
si prova **dalle route**, non dal servizio, perché è lì che ricorsione e
cache per richiesta possono rompersi. Deny-by-default: chi non dirige la
prova riceve 404, non 403 — per lui la prova non esiste.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from flask import url_for

from models.base import db
from models.competition.models import Gara, Inscription
from models.competition.services import GaraService
from models.prova.service import LIMITE_PROVE_ATTIVE, ProvaService
from models.prova.visibility import prova_visibili
from models.status_enum import Discipline, GaraStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _prova(direttore: User, *, minimo=4, massimo=8) -> Gara:
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Prova segreta {uuid.uuid4().hex[:4]}",
        date=date.today() + timedelta(days=1),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        director_id=direttore.id,
        min_participants=minimo,
        max_participants=massimo,
        status=GaraStatus.INSCRIPTION.value,
        **ProvaService.campi_di_creazione(),
    )
    db.session.commit()
    return gara


def _url(endpoint: str, **valori) -> str:
    return url_for(endpoint, **valori)


def _pulisci_stato_fra_richieste() -> None:
    """Rimette il test nelle condizioni di una richiesta vera.

    La fixture `db_session` tiene aperto un request context per tutto il
    test, e Flask-Login ci parcheggia `g._login_user`: creare una gara vera
    fuori da una richiesta passa dalla gamification, che legge `current_user`
    e lo fissa ad **anonimo** per il resto del test (vedi
    `project_test_flask_login_state_leak`). Una prova non ci cade solo
    perché il guard ADR-058 salta quel handler. E la sessione SQLAlchemy è
    una sola: l'identity map servirebbe un fittizio gia' caricato senza
    passare dal filtro, cosa che in produzione — una sessione per
    richiesta — non succede.
    """
    from flask import g

    g.pop("_login_user", None)
    db.session.expunge_all()


@pytest.fixture
def scenario(logged_in_client):
    """Un direttore con una prova, e gli altri che non devono vederla."""
    client_dir, direttore = logged_in_client(
        role=UserRole.DIRECTOR, username_prefix="dir"
    )
    prova = _prova(direttore)
    return {
        "client": client_dir,
        "direttore": direttore,
        "prova_id": prova.id,
        "nome": prova.name,
        "token": prova.public_token,
    }


class TestChiVedeLaProva:
    def test_il_direttore_la_vede_col_banner(self, scenario):
        pagina = scenario["client"].get(
            _url("admin.competition.gara_detail", gara_id=scenario["prova_id"])
        )
        assert pagina.status_code == 200
        html = pagina.get_data(as_text=True)
        assert scenario["nome"] in html
        assert "Competizione di prova" in html
        assert "Elimina la prova" in html
        assert "Iscrivi il minimo" in html
        # Niente link pubblico: al suo posto la spiegazione.
        assert "da fuori non esiste" in html

    def test_l_anonimo_riceve_404(self, scenario, client):
        assert (
            client.get(
                _url("admin.competition.gara_detail", gara_id=scenario["prova_id"])
            ).status_code
            == 404
        )
        assert (
            client.get(_url("main.gara_invite", token=scenario["token"])).status_code
            == 404
        )
        elenco = client.get(_url("main.public_garas_list")).get_data(as_text=True)
        assert scenario["nome"] not in elenco
        home = client.get(_url("main.index")).get_data(as_text=True)
        assert scenario["nome"] not in home

    def test_un_giocatore_riceve_404(self, scenario, logged_in_client):
        client_pl, _ = logged_in_client(role=UserRole.PLAYER, username_prefix="pl")
        assert (
            client_pl.get(
                _url("admin.competition.gara_detail", gara_id=scenario["prova_id"])
            ).status_code
            == 404
        )
        elenco = client_pl.get(_url("main.public_garas_list")).get_data(as_text=True)
        assert scenario["nome"] not in elenco

    def test_un_altro_direttore_riceve_404(self, scenario, logged_in_client):
        client_altro, _ = logged_in_client(
            role=UserRole.DIRECTOR, username_prefix="altro"
        )
        assert (
            client_altro.get(
                _url("admin.competition.gara_detail", gara_id=scenario["prova_id"])
            ).status_code
            == 404
        )

    def test_l_admin_la_vede(self, scenario, logged_in_client):
        client_adm, _ = logged_in_client(role=UserRole.ADMIN, username_prefix="adm")
        pagina = client_adm.get(
            _url("admin.competition.gara_detail", gara_id=scenario["prova_id"])
        )
        assert pagina.status_code == 200
        assert "Competizione di prova" in pagina.get_data(as_text=True)

    def test_la_home_del_direttore_la_marca_come_prova(self, scenario):
        home = scenario["client"].get(_url("dashboard.dashboard"))
        assert home.status_code == 200
        html = home.get_data(as_text=True)
        assert scenario["nome"] in html
        assert "fa-flask" in html

    def test_i_fittizi_non_hanno_un_profilo_per_gli_altri(
        self, scenario, logged_in_client
    ):
        scenario["client"].post(
            _url(
                "admin.competition.prova_iscrivi_fittizi",
                gara_id=scenario["prova_id"],
                modalita="uno",
            ),
            follow_redirects=True,
        )
        with prova_visibili():
            fittizio_id = ProvaService.fittizi_della_radice(
                gara_id=scenario["prova_id"]
            )[0].id
        client_pl, _ = logged_in_client(role=UserRole.PLAYER, username_prefix="pl")
        _pulisci_stato_fra_richieste()
        assert (
            client_pl.get(_url("player.view_profile", user_id=fittizio_id)).status_code
            == 404
        )
        # Il direttore, invece, lo vede.
        _pulisci_stato_fra_richieste()
        assert (
            scenario["client"]
            .get(_url("player.view_profile", user_id=fittizio_id))
            .status_code
            == 200
        )


class TestLeAzioniDelDirettore:
    def test_i_tre_pulsanti_iscrivono_i_fittizi(self, scenario):
        client = scenario["client"]
        gara_id = scenario["prova_id"]

        pagina = client.post(
            _url(
                "admin.competition.prova_iscrivi_fittizi",
                gara_id=gara_id,
                modalita="minimo",
            ),
            follow_redirects=True,
        )
        assert pagina.status_code == 200
        html = pagina.get_data(as_text=True)
        assert "Iscritti 4 giocatori fittizi" in html
        assert "Maria Rossi" in html
        with prova_visibili():
            assert (
                Inscription.query.filter_by(gara_id=gara_id, is_waitlist=False).count()
                == 4
            )

        client.post(
            _url(
                "admin.competition.prova_iscrivi_fittizi",
                gara_id=gara_id,
                modalita="uno",
            ),
            follow_redirects=True,
        )
        client.post(
            _url(
                "admin.competition.prova_iscrivi_fittizi",
                gara_id=gara_id,
                modalita="massimo",
            ),
            follow_redirects=True,
        )
        with prova_visibili():
            assert (
                Inscription.query.filter_by(gara_id=gara_id, is_waitlist=False).count()
                == 8
            )

        di_nuovo = client.post(
            _url(
                "admin.competition.prova_iscrivi_fittizi",
                gara_id=gara_id,
                modalita="uno",
            ),
            follow_redirects=True,
        )
        assert "Niente da aggiungere" in di_nuovo.get_data(as_text=True)

    def test_una_modalita_inventata_e_404(self, scenario):
        risposta = scenario["client"].post(
            _url(
                "admin.competition.prova_iscrivi_fittizi",
                gara_id=scenario["prova_id"],
                modalita="tutti",
            )
        )
        assert risposta.status_code == 404

    def test_un_utente_vero_non_si_iscrive_a_una_prova(
        self, scenario, logged_in_client
    ):
        _, giocatore = logged_in_client(role=UserRole.PLAYER, username_prefix="pl")
        risposta = scenario["client"].post(
            _url("admin.competition.admin_inscribe_user", gara_id=scenario["prova_id"]),
            data={"user_id": giocatore.id},
            follow_redirects=True,
        )
        assert "solo i giocatori fittizi" in risposta.get_data(as_text=True)
        with prova_visibili():
            assert (
                Inscription.query.filter_by(gara_id=scenario["prova_id"]).count() == 0
            )

    def test_elimina_la_prova_e_torna_in_home(self, scenario):
        gara_id = scenario["prova_id"]
        scenario["client"].post(
            _url(
                "admin.competition.prova_iscrivi_fittizi",
                gara_id=gara_id,
                modalita="minimo",
            ),
        )
        risposta = scenario["client"].post(
            _url("admin.competition.prova_elimina", gara_id=gara_id),
            follow_redirects=False,
        )
        assert risposta.status_code == 302
        assert risposta.headers["Location"].endswith(_url("dashboard.dashboard"))
        with prova_visibili():
            assert db.session.get(Gara, gara_id) is None
            assert (
                User.query.filter_by(is_fittizio=True, prova_gara_id=gara_id).count()
                == 0
            )

    def test_eliminare_una_gara_vera_da_qui_e_404(self, scenario):
        vera = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Vera",
            date=date.today() + timedelta(days=1),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            director_id=scenario["direttore"].id,
        )
        db.session.commit()
        vera_id = vera.id
        _pulisci_stato_fra_richieste()
        assert (
            scenario["client"]
            .post(_url("admin.competition.prova_elimina", gara_id=vera_id))
            .status_code
            == 404
        )
        assert db.session.get(Gara, vera_id) is not None

    def test_la_vetrina_rimanda_alla_gara(self, scenario):
        risposta = scenario["client"].get(
            _url("admin.competition.gara_vetrina", gara_id=scenario["prova_id"]),
            follow_redirects=True,
        )
        assert "non ha vetrina" in risposta.get_data(as_text=True)


class TestCreazioneDalModulo:
    def _dati(self, nome: str) -> dict:
        return {
            "name": nome,
            "date": (date.today() + timedelta(days=2)).isoformat(),
            "time": "20:00",
            "discipline": Discipline.NINE_BALL.value,
            "distance": "5",
            "rounds_count": "3",
            "min_participants": "4",
            "max_participants": "8",
            "location": "Sala di prova",
            "available_tables": "1,2",
            "anti_rematch_enabled": "on",
            "is_prova": "on",
        }

    def test_la_spunta_crea_una_prova(self, logged_in_client):
        client, direttore = logged_in_client(
            role=UserRole.DIRECTOR, username_prefix="dir"
        )
        risposta = client.post(
            _url("admin.competition.create_gara_standalone"),
            data=self._dati("Prova dal modulo"),
            follow_redirects=True,
        )
        assert risposta.status_code == 200
        assert "creata: solo tu la vedi" in risposta.get_data(as_text=True)
        prove = ProvaService.prove_attive(direttore.id)
        assert [p.name for p in prove] == ["Prova dal modulo"]
        assert prove[0].prova_expires_at is not None

    def test_la_quarta_viene_rifiutata(self, logged_in_client):
        client, direttore = logged_in_client(
            role=UserRole.DIRECTOR, username_prefix="dir"
        )
        for _ in range(LIMITE_PROVE_ATTIVE):
            _prova(direttore)

        modulo = client.get(_url("admin.competition.create_gara_standalone")).get_data(
            as_text=True
        )
        assert "eliminane una" in modulo

        risposta = client.post(
            _url("admin.competition.create_gara_standalone"),
            data=self._dati("Quarta"),
            follow_redirects=True,
        )
        assert "prove aperte" in risposta.get_data(as_text=True)
        assert len(ProvaService.prove_attive(direttore.id)) == LIMITE_PROVE_ATTIVE
