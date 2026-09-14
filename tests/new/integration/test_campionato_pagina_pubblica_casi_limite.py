"""La pagina pubblica di un campionato: chi non deve trovarla riceve 404.

`/campionato/<id>/public` e la vetrina `/c/<identificatore>` mostrano lo
stesso campionato a chi non lo dirige, e devono rifiutare gli stessi casi.

**Campionato eliminato.** Su `Campionato` il filtro dei soft-eliminati non è
automatico: la vetrina lo scrive in `resolve_public_identifier_campionato`, la
pagina pubblica no. Fino al 2026-09-14 un campionato eliminato rispondeva qui
200, mostrando una stagione che per l'applicazione non esiste più — e gli id
si enumerano.

**Competizione di prova (ADR-058).** Qui il rifiuto non si scrive: lo applica
il filtro di sessione, che vale anche per `db.get_or_404`. Il test lo fissa,
perché finora era una deduzione dal codice e non un fatto verificato.

Prima di ogni richiesta si svuota l'identity map: nei test la sessione
SQLAlchemy è una sola, e un campionato già caricato verrebbe servito senza
passare dal filtro — in produzione, una sessione per richiesta, non succede.
"""

from __future__ import annotations

import uuid

import pytest
from flask import url_for

from models.base import db
from models.campionato.models import Campionato
from models.campionato.tournament_service import TournamentService
from models.prova.service import ProvaService
from models.prova.visibility import prova_visibili
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _pulisci_stato_fra_richieste() -> None:
    """Vedi `test_prova_visibilita.py`: `g` e l'identity map sopravvivono."""
    from flask import g

    g.pop("_login_user", None)
    db.session.expunge_all()


def _campionato(**overrides) -> int:
    params = dict(name=f"Sociale {uuid.uuid4().hex[:6]}")
    params.update(overrides)
    campionato = Campionato(**params)
    db.session.add(campionato)
    db.session.commit()
    return campionato.id


def _url(campionato_id: int) -> str:
    return url_for("main.campionato_detail_public", campionato_id=campionato_id)


class TestCampionatoEliminato:
    def test_un_campionato_vivo_risponde_200(self, client, db_session):
        """Il controllo: senza, un 404 per qualunque motivo farebbe passare
        anche il test qui sotto."""
        campionato_id = _campionato()
        _pulisci_stato_fra_richieste()

        assert client.get(_url(campionato_id)).status_code == 200

    def test_un_campionato_eliminato_risponde_404(self, client, db_session):
        campionato_id = _campionato(is_deleted=True)
        _pulisci_stato_fra_richieste()

        assert client.get(_url(campionato_id)).status_code == 404

    def test_anche_per_chi_e_autenticato(self, logged_in_client):
        client_pl, _ = logged_in_client(role=UserRole.PLAYER, username_prefix="pl")
        campionato_id = _campionato(is_deleted=True)
        _pulisci_stato_fra_richieste()

        assert client_pl.get(_url(campionato_id)).status_code == 404


class TestCampionatoDiProva:
    @pytest.fixture
    def prova(self, logged_in_client):
        client_dir, direttore = logged_in_client(
            role=UserRole.DIRECTOR, username_prefix="dir"
        )
        with prova_visibili():
            campionato = TournamentService().create_campionato_with_director(
                name=f"Campionato di prova {uuid.uuid4().hex[:4]}",
                creator_user_id=direttore.id,
                **ProvaService.campi_di_creazione(),
            )
            db.session.commit()
            campionato_id = campionato.id
        return {"client": client_dir, "campionato_id": campionato_id}

    def test_l_anonimo_riceve_404(self, prova, client):
        _pulisci_stato_fra_richieste()

        assert client.get(_url(prova["campionato_id"])).status_code == 404

    def test_un_giocatore_riceve_404(self, prova, logged_in_client):
        client_pl, _ = logged_in_client(role=UserRole.PLAYER, username_prefix="pl")
        _pulisci_stato_fra_richieste()

        assert client_pl.get(_url(prova["campionato_id"])).status_code == 404

    def test_il_suo_direttore_la_vede(self, prova):
        """Come per la vetrina e per ogni altra pagina: la prova esiste per
        chi la dirige, e solo per lui."""
        _pulisci_stato_fra_richieste()

        assert prova["client"].get(_url(prova["campionato_id"])).status_code == 200
