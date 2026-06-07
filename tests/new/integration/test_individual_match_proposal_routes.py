"""Integration test delle route proposte/discovery/lifecycle dei match individuali.

Copre la superficie player-facing (prima poco testata): lista/dettaglio/
creazione/accettazione/annullo/rifiuto proposte, dashboard, statistiche,
ricerca giocatori e il ciclo di vita del match (start/rack/confirm/cancel/
forfeit).

App context aperto per tutto il test (fixture ``_ctx``, come
``test_geo_proximity.py``) per evitare il Flask-Login DetachedInstanceError in
parallelo. Poiché Flask-Login **cache l'utente su ``g``** (legato all'app
context), con più attori nello stesso test la cache va azzerata prima di ogni
richiesta del client: per questo si usano i wrapper ``_get``/``_post`` invece di
chiamare ``client.get/post`` direttamente (in produzione ogni richiesta ha il
proprio contesto, quindi il problema non esiste).
"""

import uuid
from datetime import timedelta

import pytest
from flask import g

from models import db, User
from models.base import utc_now
from models.user.role_enum import UserRole
from models.individual_match.models import (
    MatchProposal,
    ProposalType,
    ProposalStatus,
)
from models.individual_match.services import MatchProposalService


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _player(override=True):
    """Player con gamification_override → bypassa i gate feature (can_access)."""
    uid = str(uuid.uuid4())[:8]
    u = User(
        username=f"p_{uid}",
        email=f"p_{uid}@test.com",
        role=UserRole.PLAYER.value,
        gamification_override=override,
    )
    u.set_password("pw123456")
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def _get(client, url, **kw):
    """GET con reset della cache utente di Flask-Login (vedi docstring modulo)."""
    g.pop("_login_user", None)
    return client.get(url, **kw)


def _post(client, url, **kw):
    """POST con reset della cache utente di Flask-Login (vedi docstring modulo)."""
    g.pop("_login_user", None)
    return client.post(url, **kw)


def _client_for(app, user):
    client = app.test_client()
    _login(client, user)
    return client


def _open_proposal(proposer_id, location="Sala Test"):
    return MatchProposalService.create_proposal(
        proposer_id=proposer_id,
        proposal_type=ProposalType.OPEN,
        location=location,
        scheduled_at=utc_now() + timedelta(days=1),
        expires_at=utc_now() + timedelta(hours=23),
        discipline="palla_8",
        distance=5,
    )


def _direct_proposal(proposer_id, invited_ids, location="Sala Test"):
    return MatchProposalService.create_proposal(
        proposer_id=proposer_id,
        proposal_type=ProposalType.DIRECT,
        location=location,
        scheduled_at=utc_now() + timedelta(days=1),
        expires_at=utc_now() + timedelta(hours=23),
        discipline="palla_8",
        distance=5,
        invited_user_ids=invited_ids,
    )


def _accept_via_client(app, proposer, accepter):
    """Crea una proposta aperta e la fa accettare **via route client**.

    L'accettazione va fatta tramite il client (non chiamando il service nel
    corpo del test): un service ``@transactional`` cross-dominio eseguito qui
    dentro l'app_context aperto lascerebbe la ``db.session`` in uno stato che
    rompe le richieste client successive (artefatto di test, non bug di prod).
    """
    prop = _open_proposal(proposer.id)
    resp = _post(
        _client_for(app, accepter), f"/match/proposals/{prop.id}/accept", json={}
    )
    assert resp.status_code == 200
    return resp.get_json()["match_id"]


@pytest.mark.integration
class TestProposalPages:
    def test_proposal_list_renders(self, app):
        client = _client_for(app, _player())
        assert _get(client, "/match/proposals").status_code == 200

    def test_create_proposal_form_renders(self, app):
        client = _client_for(app, _player())
        assert _get(client, "/match/proposals/create").status_code == 200

    def test_dashboard_and_statistics_render(self, app):
        client = _client_for(app, _player())
        assert _get(client, "/match/").status_code == 200
        assert _get(client, "/match/statistics").status_code == 200

    def test_proposal_detail_open_accessible_to_others(self, app):
        prop = _open_proposal(_player().id)
        client = _client_for(app, _player())
        assert _get(client, f"/match/proposals/{prop.id}").status_code == 200

    def test_proposal_detail_direct_denied_to_stranger(self, app):
        proposer = _player()
        invited = _player()
        prop = _direct_proposal(proposer.id, [invited.id])
        client = _client_for(app, _player())  # stranger
        resp = _get(client, f"/match/proposals/{prop.id}", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/match/proposals")


@pytest.mark.integration
class TestProposalLifecycleRoutes:
    def test_create_open_proposal_via_post(self, app):
        user = _player()
        uid = user.id
        client = _client_for(app, user)
        resp = _post(
            client,
            "/match/proposals/create",
            json={
                "proposal_type": "open",
                "location": "Sala Test",
                "scheduled_at": (utc_now() + timedelta(days=1)).isoformat(),
                "expires_hours": "1",
                "discipline": "palla_8",
                "match_format": "single",
                "distance": "5",
                "is_race_to": "true",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        prop = db.session.get(MatchProposal, body["proposal_id"])
        assert prop is not None and prop.proposer_id == uid
        assert prop.proposal_type == ProposalType.OPEN

    def test_accept_open_proposal_creates_match(self, app):
        prop = _open_proposal(_player().id)
        client = _client_for(app, _player())
        resp = _post(client, f"/match/proposals/{prop.id}/accept", json={})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True and "match_id" in body
        assert db.session.get(MatchProposal, prop.id).status == ProposalStatus.ACCEPTED

    def test_cancel_proposal_by_proposer(self, app):
        proposer = _player()
        prop = _open_proposal(proposer.id)
        client = _client_for(app, proposer)
        resp = _post(client, f"/match/proposals/{prop.id}/cancel", json={})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert db.session.get(MatchProposal, prop.id).status == ProposalStatus.CANCELLED

    def test_decline_direct_invitation(self, app):
        """Regressione: la route chiamava MatchProposalService.reject_invitation
        (inesistente) → 500 per ogni rifiuto di invito diretto. Ora usa
        reject_proposal(proposal_id, user_id)."""
        from models.individual_match.models import InvitationStatus

        proposer = _player()
        invited = _player()
        prop = _direct_proposal(proposer.id, [invited.id])
        invited_id = invited.id
        client = _client_for(app, invited)
        resp = _post(client, f"/match/proposals/{prop.id}/decline", json={})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        inv = next(
            i
            for i in db.session.get(MatchProposal, prop.id).invitations
            if i.invited_user_id == invited_id
        )
        assert inv.status == InvitationStatus.REJECTED


@pytest.mark.integration
class TestPlayerDiscoveryRoutes:
    def test_search_players_short_query_returns_empty(self, app):
        client = _client_for(app, _player())
        resp = _get(client, "/match/players/search?q=a")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_search_players_finds_eligible(self, app):
        target = _player(override=True)
        target_id, target_name = target.id, target.username
        client = _client_for(app, _player())
        resp = _get(client, f"/match/players/search?q={target_name[:5]}")
        assert resp.status_code == 200
        assert target_id in {p["id"] for p in resp.get_json()}

    def test_get_opponents_returns_json(self, app):
        client = _client_for(app, _player())
        resp = _get(client, "/match/players/opponents")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


@pytest.mark.integration
class TestMatchLifecycleRoutes:
    def test_match_list_and_detail(self, app):
        p1, p2 = _player(), _player()
        mid = _accept_via_client(app, p1, p2)
        client = _client_for(app, p1)
        assert _get(client, "/match/matches").status_code == 200
        assert _get(client, f"/match/matches/{mid}").status_code == 200

    def test_match_detail_denied_to_stranger(self, app):
        p1, p2 = _player(), _player()
        mid = _accept_via_client(app, p1, p2)
        client = _client_for(app, _player())  # stranger
        resp = _get(client, f"/match/matches/{mid}", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/match/matches")

    def test_full_play_flow_start_score_confirm(self, app):
        from models.individual_match.models import IndividualMatch

        p1, p2 = _player(), _player()
        p1id = p1.id
        mid = _accept_via_client(app, p1, p2)
        c1 = _client_for(app, p1)
        c2 = _client_for(app, p2)

        assert _post(c1, f"/match/matches/{mid}/start", json={}).status_code == 200
        for _ in range(5):  # p1 vince 5 rack (race to 5)
            assert (
                _post(
                    c1,
                    f"/match/matches/{mid}/racks/add",
                    json={"winner_id": p1id},
                ).status_code
                == 200
            )
        assert db.session.get(IndividualMatch, mid).is_ready_for_validation() is True

        # 1ª conferma: ancora in attesa dell'altro giocatore.
        r1 = _post(c1, f"/match/matches/{mid}/confirm", json={})
        assert r1.status_code == 200 and r1.get_json()["completed"] is False
        # 2ª conferma: bilaterale → match concluso (VALIDATED). La route ora
        # riporta completed=True (prima diceva False perché controllava solo
        # status=="completed" mentre il flusso produce VALIDATED).
        resp = _post(c2, f"/match/matches/{mid}/confirm", json={})
        assert resp.status_code == 200
        assert resp.get_json()["completed"] is True

        from models.status_enum import MatchStatus

        final = db.session.get(IndividualMatch, mid)
        assert final.player1_confirmed and final.player2_confirmed
        assert final.status == MatchStatus.VALIDATED.value
        assert final.winner_id == p1id

    def test_cancel_match(self, app):
        p1, p2 = _player(), _player()
        mid = _accept_via_client(app, p1, p2)
        client = _client_for(app, p1)
        resp = _post(client, f"/match/matches/{mid}/cancel", json={})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_forfeit_match(self, app):
        from models.individual_match.models import IndividualMatch

        p1, p2 = _player(), _player()
        p2id = p2.id
        mid = _accept_via_client(app, p1, p2)
        client = _client_for(app, p1)
        _post(client, f"/match/matches/{mid}/start", json={})
        resp = _post(client, f"/match/matches/{mid}/forfeit", json={})
        assert resp.status_code == 200
        # chi dichiara forfait perde → vince l'avversario
        assert resp.get_json()["winner_id"] == p2id
        assert db.session.get(IndividualMatch, mid).winner_id == p2id


@pytest.mark.integration
class TestMatchScoringExtraRoutes:
    """Route di scoring/lifecycle non coperte altrove: remove_rack, reject,
    complete (legacy), update-times, rematch."""

    def _started(self, app, p1, p2):
        mid = _accept_via_client(app, p1, p2)
        c1 = _client_for(app, p1)
        c2 = _client_for(app, p2)
        assert _post(c1, f"/match/matches/{mid}/start", json={}).status_code == 200
        return mid, c1, c2

    def test_remove_rack_decrements_score(self, app):
        p1, p2 = _player(), _player()
        p1id = p1.id
        mid, c1, _c2 = self._started(app, p1, p2)
        # 2 rack a p1
        _post(c1, f"/match/matches/{mid}/racks/add", json={"winner_id": p1id})
        r = _post(c1, f"/match/matches/{mid}/racks/add", json={"winner_id": p1id})
        assert r.get_json()["player1_score"] == 2
        # rimuovi un rack di p1
        rem = _post(c1, f"/match/matches/{mid}/racks/remove", json={"player_id": p1id})
        assert rem.status_code == 200
        assert rem.get_json()["player1_score"] == 1

    def test_reject_result_removes_last_rack(self, app):
        from models.individual_match.models import IndividualMatch

        p1, p2 = _player(), _player()
        p1id = p1.id
        mid, c1, _c2 = self._started(app, p1, p2)
        for _ in range(5):  # p1 arriva a 5 → pronto per validazione
            _post(c1, f"/match/matches/{mid}/racks/add", json={"winner_id": p1id})
        assert db.session.get(IndividualMatch, mid).is_ready_for_validation() is True

        resp = _post(c1, f"/match/matches/{mid}/reject", json={})
        assert resp.status_code == 200
        assert resp.get_json()["player1_score"] == 4
        assert db.session.get(IndividualMatch, mid).is_ready_for_validation() is False

    def test_complete_match_legacy(self, app):
        from models.individual_match.models import IndividualMatch

        p1, p2 = _player(), _player()
        p1id = p1.id
        mid, c1, _c2 = self._started(app, p1, p2)
        for _ in range(5):
            _post(c1, f"/match/matches/{mid}/racks/add", json={"winner_id": p1id})

        resp = _post(c1, f"/match/matches/{mid}/complete", json={"winner_id": p1id})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert db.session.get(IndividualMatch, mid).winner_id == p1id

    def test_update_match_times(self, app):
        from datetime import timedelta

        p1, p2 = _player(), _player()
        mid, c1, _c2 = self._started(app, p1, p2)
        started = (utc_now() - timedelta(hours=1)).isoformat()
        resp = _post(
            c1,
            f"/match/matches/{mid}/update-times",
            json={"started_at": started},
        )
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_rematch_redirects_to_create_with_params(self, app):
        # Match portato a VALIDATED, poi rematch → redirect a create_proposal.
        p1, p2 = _player(), _player()
        p1id = p1.id
        mid, c1, c2 = self._started(app, p1, p2)
        for _ in range(5):
            _post(c1, f"/match/matches/{mid}/racks/add", json={"winner_id": p1id})
        _post(c1, f"/match/matches/{mid}/confirm", json={})
        _post(c2, f"/match/matches/{mid}/confirm", json={})

        resp = _get(c1, f"/match/matches/{mid}/rematch", follow_redirects=False)
        assert resp.status_code == 302
        loc = resp.headers["Location"]
        assert "/match/proposals/create" in loc and "rematch=true" in loc

    def test_rematch_blocked_if_not_completed(self, app):
        # Match solo avviato (non concluso) → niente rematch.
        p1, p2 = _player(), _player()
        mid, c1, _c2 = self._started(app, p1, p2)
        resp = _get(c1, f"/match/matches/{mid}/rematch", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith(f"/match/matches/{mid}")
