"""Sfide a due in attesa di conferma, dalle route (richiesta del 2026-09-14).

La regola sta nel servizio (``test_sfide_in_attesa_di_conferma.py``); qui si
difende quello che vede il giocatore:

* l'elenco delle sfide mostra lo stato «In attesa di conferma»;
* la dashboard non mostra più la partita passato un giorno dalla prima firma;
* chi è bloccato non riceve un errore secco: finisce sulla pagina che gli
  propone di confermare o rifiutare le partite che aspettano lui, e da lì
  torna dov'era.

Stessa impalcatura di ``test_individual_match_quick_routes.py``: app context
aperto e cache utente di Flask-Login azzerata prima di ogni richiesta.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from flask import g

from models import User, db
from models.base import utc_now
from models.individual_match.models import IndividualMatch, MatchProposal
from models.individual_match.proposal_service import ProposalService
from models.status_enum import Discipline, MatchStatus
from models.user.role_enum import UserRole

PAGINA = "/match/matches/da_confermare"


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _player() -> User:
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"pc_{uid}",
        email=f"pc_{uid}@test.com",
        role=UserRole.PLAYER.value,
        gamification_override=True,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _client_for(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True
    return client


def _get(client, url, **kw):
    g.pop("_login_user", None)
    return client.get(url, **kw)


def _post(client, url, **kw):
    g.pop("_login_user", None)
    return client.post(url, **kw)


def _in_attesa(vincitore: User, perdente: User, ore_fa: float) -> IndividualMatch:
    match = IndividualMatch(
        player1_id=vincitore.id,
        player2_id=perdente.id,
        location="Sala Conferme",
        scheduled_at=utc_now() - timedelta(hours=ore_fa + 1),
        status=MatchStatus.IN_PROGRESS,
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        player1_score=3,
        player2_score=1,
        player1_confirmed=True,
        player1_confirmed_at=utc_now() - timedelta(hours=ore_fa),
    )
    db.session.add(match)
    db.session.commit()
    return match


@pytest.mark.integration
class TestElencoEDashboard:
    def test_l_elenco_mostra_lo_stato_in_attesa_di_conferma(self, app):
        vincitore, perdente = _player(), _player()
        _in_attesa(vincitore, perdente, ore_fa=30)

        for user in (vincitore, perdente):
            html = _get(_client_for(app, user), "/match/matches").get_data(as_text=True)
            assert "In attesa di conferma" in html

    def test_l_elenco_propone_di_chiuderle_a_chi_deve_firmare(self, app):
        vincitore, perdente = _player(), _player()
        _in_attesa(vincitore, perdente, ore_fa=30)

        html_perdente = _get(_client_for(app, perdente), "/match/matches").get_data(
            as_text=True
        )
        html_vincitore = _get(_client_for(app, vincitore), "/match/matches").get_data(
            as_text=True
        )

        assert PAGINA in html_perdente
        assert PAGINA not in html_vincitore

    def test_la_dashboard_non_la_mostra_dopo_un_giorno(self, app):
        vincitore, perdente = _player(), _player()
        _in_attesa(vincitore, perdente, ore_fa=30)

        for user in (vincitore, perdente):
            html = _get(_client_for(app, user), "/dashboard").get_data(as_text=True)
            assert "Sala Conferme" not in html

    def test_la_dashboard_la_mostra_prima_di_un_giorno(self, app):
        vincitore, perdente = _player(), _player()
        _in_attesa(vincitore, perdente, ore_fa=3)

        html = _get(_client_for(app, perdente), "/dashboard").get_data(as_text=True)
        assert "Sala Conferme" in html


@pytest.mark.integration
class TestPaginaDaConfermare:
    def test_elenca_le_partite_con_conferma_e_rifiuto(self, app):
        vincitore, perdente = _player(), _player()
        match = _in_attesa(vincitore, perdente, ore_fa=30)

        resp = _get(_client_for(app, perdente), PAGINA)
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert f"/match/matches/{match.id}/confirm" in html
        assert f"/match/matches/{match.id}/reject" in html
        assert 'name="csrf_token"' in html
        assert vincitore.username in html

    def test_senza_pendenti_dice_che_si_puo_ripartire(self, app):
        user = _player()

        resp = _get(_client_for(app, user), f"{PAGINA}?next=/match/quick")
        html = resp.get_data(as_text=True)

        assert resp.status_code == 200
        assert "/match/quick" in html

    def test_next_esterno_ignorato(self, app):
        user = _player()

        html = _get(
            _client_for(app, user), f"{PAGINA}?next=https://evil.example"
        ).get_data(as_text=True)

        # L'indirizzo della richiesta può ricomparire nel guscio della pagina
        # (lingua, login): conta che non diventi il pulsante «Riprendi».
        assert 'href="https://evil.example"' not in html
        assert "Riprendi da dove eri" not in html

    def test_confermare_dalla_pagina_riporta_alla_pagina(self, app):
        vincitore, perdente = _player(), _player()
        match = _in_attesa(vincitore, perdente, ore_fa=30)
        client = _client_for(app, perdente)

        resp = _post(
            client,
            f"/match/matches/{match.id}/confirm",
            data={"next": f"{PAGINA}?next=/match/quick"},
        )

        assert resp.status_code == 302
        assert resp.headers["Location"].endswith(f"{PAGINA}?next=/match/quick")
        assert db.session.get(IndividualMatch, match.id).status == (
            MatchStatus.CONFIRMED_BY_BOTH
        )

    def test_rifiutare_dalla_pagina_riporta_alla_pagina(self, app):
        vincitore, perdente = _player(), _player()
        match = _in_attesa(vincitore, perdente, ore_fa=30)

        resp = _post(
            _client_for(app, perdente),
            f"/match/matches/{match.id}/reject",
            data={"next": PAGINA},
        )

        assert resp.status_code == 302
        assert resp.headers["Location"].endswith(PAGINA)

    def test_confermare_con_next_esterno_torna_alla_partita(self, app):
        vincitore, perdente = _player(), _player()
        match = _in_attesa(vincitore, perdente, ore_fa=30)

        resp = _post(
            _client_for(app, perdente),
            f"/match/matches/{match.id}/confirm",
            data={"next": "//evil.example"},
        )

        assert resp.headers["Location"].endswith(f"/match/matches/{match.id}")


@pytest.mark.integration
class TestBloccoDalleRoute:
    def test_avvio_rapido_porta_alle_partite_da_chiudere(self, app):
        vincitore, perdente = _player(), _player()
        terzo = _player()
        _in_attesa(vincitore, perdente, ore_fa=2)

        resp = _post(
            _client_for(app, perdente),
            "/match/quick",
            data={"opponent_id": terzo.id},
        )

        assert resp.status_code == 302
        assert PAGINA in resp.headers["Location"]
        assert (
            IndividualMatch.query.filter_by(
                player1_id=perdente.id, player2_id=terzo.id
            ).count()
            == 0
        )

    def test_avvio_rapido_in_json_risponde_409_con_le_partite(self, app):
        vincitore, perdente = _player(), _player()
        terzo = _player()
        match = _in_attesa(vincitore, perdente, ore_fa=2)

        resp = _post(
            _client_for(app, perdente),
            "/match/quick",
            json={"opponent_id": terzo.id},
        )
        body = resp.get_json()

        assert resp.status_code == 409
        assert body["success"] is False
        assert body["pending_match_ids"] == [match.id]
        assert PAGINA in body["redirect"]

    def test_accettare_una_proposta_porta_alle_partite_da_chiudere(self, app):
        vincitore, perdente = _player(), _player()
        terzo = _player()
        _in_attesa(vincitore, perdente, ore_fa=2)
        proposta = ProposalService.create_direct_proposal(
            proposer_id=terzo.id,
            invited_user_ids=[perdente.id],
            location="Sala Test",
            scheduled_at=utc_now() + timedelta(days=2),
        )

        resp = _post(
            _client_for(app, perdente),
            f"/match/proposals/{proposta.id}/accept",
        )

        assert resp.status_code == 302
        location = resp.headers["Location"]
        assert PAGINA in location
        # Chiuse le pendenti, si torna alla proposta da accettare.
        assert f"/match/proposals/{proposta.id}" in location.replace("%2F", "/")
        assert db.session.get(MatchProposal, proposta.id).individual_match is None

    def test_proporre_una_sfida_porta_alle_partite_da_chiudere(self, app):
        vincitore, perdente = _player(), _player()
        _in_attesa(vincitore, perdente, ore_fa=2)
        quando = (utc_now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")

        resp = _post(
            _client_for(app, perdente),
            "/match/proposals/create",
            data={
                "scheduled_at": quando,
                "proposal_type": "open",
                "location": "Sala Test",
                "distance": "5",
            },
        )

        assert resp.status_code == 302
        assert PAGINA in resp.headers["Location"]

    def test_chi_aspetta_puo_avviare(self, app):
        vincitore, perdente = _player(), _player()
        terzo = _player()
        _in_attesa(vincitore, perdente, ore_fa=30)

        resp = _post(
            _client_for(app, vincitore),
            "/match/quick",
            data={"opponent_id": terzo.id},
        )

        assert resp.status_code == 302
        assert PAGINA not in resp.headers["Location"]
