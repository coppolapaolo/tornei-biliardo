"""Competizione di prova (ADR-058), tappa 2: i pulsanti di simulazione dal client.

Il servizio è provato in `tests/new/unit/test_prova_simulazione.py`; qui si
percorre il giunto interfaccia↔server: i tre pulsanti compaiono solo in fase
di gioco e solo in una prova, la route chiude le partite nei due modi, e chi
non dirige la prova non la tocca (404 sulla pagina, 403 sull'azione).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from flask import url_for

from models.base import db
from models.competition.models import Gara
from models.competition.services import GaraService
from models.match.models import Match
from models.prova.service import ProvaService
from models.prova.visibility import prova_visibili
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole
from utils.feature_flags import ENDPOINT_ROLES

pytestmark = pytest.mark.integration


def _prova(direttore: User, *, iscritti: int = 6) -> Gara:
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Prova {uuid.uuid4().hex[:4]}",
        date=date.today() + timedelta(days=1),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        director_id=direttore.id,
        min_participants=iscritti,
        max_participants=iscritti,
        rounds_count=3,
        matchmaking_strategy="amalfi",
        first_round_policy="random",
        odd_number_policy="bye",
        status=GaraStatus.INSCRIPTION.value,
        **ProvaService.campi_di_creazione(),
    )
    db.session.commit()
    return gara


def _pulisci_stato_fra_richieste() -> None:
    """Vedi `test_prova_visibilita.py`: `g` e l'identity map sopravvivono."""
    from flask import g

    g.pop("_login_user", None)
    db.session.expunge_all()


def _simula(client, gara_id: int, azione: str):
    return client.post(
        url_for("admin.competition.prova_simula", gara_id=gara_id, azione=azione),
        follow_redirects=True,
    )


@pytest.fixture
def scenario(logged_in_client):
    """Un direttore con una prova avviata dal client, come farebbe lui."""
    client, direttore = logged_in_client(role=UserRole.DIRECTOR, username_prefix="dir")
    prova = _prova(direttore)
    gara_id = prova.id
    client.post(
        url_for(
            "admin.competition.prova_iscrivi_fittizi",
            gara_id=gara_id,
            modalita="minimo",
        ),
        follow_redirects=True,
    )
    risposta = client.post(
        url_for("admin.competition.start_first_round", gara_id=gara_id),
        follow_redirects=True,
    )
    assert risposta.status_code == 200
    _pulisci_stato_fra_richieste()
    with prova_visibili():
        gara = db.session.get(Gara, gara_id)
        assert gara is not None and gara.status == GaraStatus.PLAYING.value
    return {"client": client, "direttore": direttore, "gara_id": gara_id}


def _partite(gara_id: int) -> list[Match]:
    with prova_visibili():
        return [
            m
            for m in Match.query.filter_by(gara_id=gara_id).order_by(Match.id).all()
            if not m.is_bye
        ]


class TestIPulsanti:
    def test_compaiono_in_fase_di_gioco_e_solo_li(self, scenario, logged_in_client):
        html = (
            scenario["client"]
            .get(url_for("admin.competition.gara_detail", gara_id=scenario["gara_id"]))
            .get_data(as_text=True)
        )
        assert "Simula una partita" in html
        assert "Simula il turno" in html
        assert "Simula tutta la gara" in html

        # A iscrizioni aperte i pulsanti sono quelli dei fittizi, non questi.
        aperta_id = _prova(scenario["direttore"]).id
        _pulisci_stato_fra_richieste()
        html = (
            scenario["client"]
            .get(url_for("admin.competition.gara_detail", gara_id=aperta_id))
            .get_data(as_text=True)
        )
        assert "Simula una partita" not in html
        assert "Iscrivi il minimo" in html

    def test_una_gara_vera_non_li_ha(self, scenario):
        vera = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Vera",
            date=date.today() + timedelta(days=1),
            discipline=Discipline.NINE_BALL.value,
            distance=5,
            director_id=scenario["direttore"].id,
            status=GaraStatus.PLAYING.value,
        )
        db.session.commit()
        vera_id = vera.id
        _pulisci_stato_fra_richieste()
        html = (
            scenario["client"]
            .get(url_for("admin.competition.gara_detail", gara_id=vera_id))
            .get_data(as_text=True)
        )
        assert "Simula una partita" not in html
        assert _simula(scenario["client"], vera_id, "turno").status_code == 404

    def test_la_route_e_riservata_ai_direttori(self):
        assert ENDPOINT_ROLES["admin.competition.prova_simula"] == {"director"}


class TestLaRoute:
    def test_una_partita(self, scenario):
        risposta = _simula(scenario["client"], scenario["gara_id"], "partita")
        assert risposta.status_code == 200
        assert "Simulate 1 partite del turno 1" in risposta.get_data(as_text=True)
        chiuse = [m for m in _partite(scenario["gara_id"]) if m.is_at_distance]
        assert len(chiuse) == 1

    def test_il_turno_nei_due_modi(self, scenario):
        risposta = _simula(scenario["client"], scenario["gara_id"], "turno")
        html = risposta.get_data(as_text=True)
        assert "Simulate 3 partite del turno 1" in html
        assert "aspettano che tu le validi" in html
        stati = {m.status for m in _partite(scenario["gara_id"])}
        assert stati == {MatchStatus.CONFIRMED_BY_BOTH.value, MatchStatus.PLAYING.value}

        # Il direttore valida una partita dal segnapunti vero: chiude d'ufficio.
        in_attesa = next(
            m
            for m in _partite(scenario["gara_id"])
            if m.status == MatchStatus.PLAYING.value
        )
        _pulisci_stato_fra_richieste()
        validata = scenario["client"].post(
            url_for("admin.match.validate_match", match_id=in_attesa.id)
        )
        assert validata.status_code == 200, validata.get_data(as_text=True)
        with prova_visibili():
            db.session.expire_all()
            partita = db.session.get(Match, in_attesa.id)
            assert partita is not None
            assert partita.status == MatchStatus.CLOSED_UNILATERALLY.value

    def test_tutta_la_gara(self, scenario):
        risposta = _simula(scenario["client"], scenario["gara_id"], "gara")
        html = risposta.get_data(as_text=True)
        assert "fino alla fine della gara" in html
        partite = _partite(scenario["gara_id"])
        assert partite and all(MatchStatus.is_finished(m.status) for m in partite)
        assert {m.round_number for m in partite} == {1, 2, 3}

        _pulisci_stato_fra_richieste()
        di_nuovo = _simula(scenario["client"], scenario["gara_id"], "partita")
        assert "Nessuna partita da simulare" in di_nuovo.get_data(as_text=True)

    def test_un_azione_inventata_e_404(self, scenario):
        risposta = scenario["client"].post(
            url_for(
                "admin.competition.prova_simula",
                gara_id=scenario["gara_id"],
                azione="tutto",
            )
        )
        assert risposta.status_code == 404

    def test_un_altro_direttore_non_la_vede(self, scenario, logged_in_client):
        altro, _ = logged_in_client(role=UserRole.DIRECTOR, username_prefix="altro")
        _pulisci_stato_fra_richieste()
        # `gara_manager_required` risponde prima del filtro di visibilità:
        # 403 come per qualunque gara altrui. La pagina, invece, dà 404
        # (`test_prova_visibilita.py`). In entrambi i casi non tocca niente.
        assert _simula(altro, scenario["gara_id"], "turno").status_code == 403
        assert all(not m.is_at_distance for m in _partite(scenario["gara_id"]))
