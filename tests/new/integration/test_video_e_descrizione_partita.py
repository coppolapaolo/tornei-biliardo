"""Link al video della partita e descrizione della sfida (2026-10-17).

Il video arriva spesso giorni dopo la partita, quindi si scrive **in ogni
stato**, anche a partita chiusa. Chi lo scrive:

* nella **sfida individuale**: i due giocatori (con la PR 3 anche chi tiene
  il referto: il punto unico è ``IndividualMatch.can_edit_info``);
* nella **partita di gara**: i due giocatori e i direttori di quella gara.

La descrizione dice che partita è («Finale della prima giornata…»): esiste
solo sulla sfida, si scrive alla creazione (avvio rapido, proposta) e si
corregge insieme al video, dallo stesso servizio e dalla stessa route.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from flask import g

from models import Gara, Match, User, db
from models.base import utc_now
from models.exceptions import PermissionDeniedError, ValidationError
from models.individual_match.models import IndividualMatch
from models.match.match_info_service import (
    DESCRIPTION_MAX_LENGTH,
    MatchInfoService,
)
from models.status_enum import Discipline, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration

VIDEO = "https://youtu.be/dQw4w9WgXcQ?t=90"
CANONICO = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=90s"


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _user(role=UserRole.PLAYER.value) -> User:
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"vd_{uid}",
        email=f"vd_{uid}@test.com",
        role=role,
        gamification_override=True,
        onboarding_completed=True,
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


def _post(client, url, **kw):
    g.pop("_login_user", None)
    return client.post(url, **kw)


def _get(client, url, **kw):
    g.pop("_login_user", None)
    return client.get(url, **kw)


def _sfida(p1: User, p2: User, status=MatchStatus.CONFIRMED_BY_BOTH):
    match = IndividualMatch(
        player1_id=p1.id,
        player2_id=p2.id,
        location="Sala Video",
        scheduled_at=utc_now() - timedelta(days=3),
        status=status,
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        player1_score=3,
        player2_score=1,
    )
    db.session.add(match)
    db.session.commit()
    return match


def _partita_di_gara(p1: User, p2: User):
    director = _user(UserRole.DIRECTOR.value)
    gara = Gara(
        director_id=director.id,
        number=db.session.query(Gara).count() + 1,
        name=f"Gara video {uuid.uuid4().hex[:6]}",
        date=date.today(),
        discipline="9_ball",
        distance=3,
        is_race_to=True,
        rounds_count=3,
        min_participants=2,
        max_participants=8,
        matchmaking_strategy="direct_elimination",
        first_round_policy="random",
    )
    db.session.add(gara)
    db.session.flush()
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
        player1_score=3,
        player2_score=0,
    )
    db.session.add(match)
    db.session.commit()
    return match, director


# --------------------------------------------------------------------------
# Sfida individuale: servizio
# --------------------------------------------------------------------------


def test_un_giocatore_scrive_video_e_descrizione_a_sfida_chiusa():
    p1, p2 = _user(), _user()
    match = _sfida(p1, p2)

    MatchInfoService.update_individual_match_info(
        match.id, p2, video_url=VIDEO, description="  Finale serie C FVG  "
    )

    saved = db.session.get(IndividualMatch, match.id)
    assert saved.video_url == CANONICO
    assert saved.description == "Finale serie C FVG"


def test_campi_vuoti_tolgono_video_e_descrizione():
    p1, p2 = _user(), _user()
    match = _sfida(p1, p2)
    match.video_url, match.description = CANONICO, "Vecchia"
    db.session.commit()

    MatchInfoService.update_individual_match_info(
        match.id, p1, video_url="", description="   "
    )

    saved = db.session.get(IndividualMatch, match.id)
    assert saved.video_url is None
    assert saved.description is None


def test_chi_non_gioca_la_sfida_non_la_tocca():
    p1, p2, estraneo = _user(), _user(), _user()
    match = _sfida(p1, p2)

    with pytest.raises(PermissionDeniedError):
        MatchInfoService.update_individual_match_info(
            match.id, estraneo, video_url=VIDEO, description=None
        )


def test_nemmeno_il_direttore_tocca_una_sfida_non_sua():
    p1, p2 = _user(), _user()
    match = _sfida(p1, p2)
    direttore = _user(UserRole.DIRECTOR.value)

    with pytest.raises(PermissionDeniedError):
        MatchInfoService.update_individual_match_info(
            match.id, direttore, video_url=VIDEO, description=None
        )


def test_una_descrizione_troppo_lunga_si_rifiuta():
    p1, p2 = _user(), _user()
    match = _sfida(p1, p2)

    with pytest.raises(ValidationError):
        MatchInfoService.update_individual_match_info(
            match.id, p1, video_url=None, description="x" * (DESCRIPTION_MAX_LENGTH + 1)
        )
    assert db.session.get(IndividualMatch, match.id).description is None


def test_un_link_non_youtube_si_rifiuta():
    p1, p2 = _user(), _user()
    match = _sfida(p1, p2)

    with pytest.raises(ValidationError):
        MatchInfoService.update_individual_match_info(
            match.id, p1, video_url="https://vimeo.com/1", description=None
        )


def test_anche_una_sfida_annullata_si_corregge():
    """«In ogni stato»: la regola non ha eccezioni da ricordare."""
    p1, p2 = _user(), _user()
    match = _sfida(p1, p2, status=MatchStatus.CANCELLED)

    MatchInfoService.update_individual_match_info(
        match.id, p1, video_url=VIDEO, description=None
    )
    assert db.session.get(IndividualMatch, match.id).video_url == CANONICO


# --------------------------------------------------------------------------
# Sfida individuale: route e pagina
# --------------------------------------------------------------------------


def test_la_route_salva_e_la_pagina_mostra_il_link(app):
    p1, p2 = _user(), _user()
    match = _sfida(p1, p2)
    client = _client_for(app, p1)

    resp = _post(
        client,
        f"/match/matches/{match.id}/info",
        data={"video_url": VIDEO, "description": "Finale <b>serie C</b>"},
    )
    assert resp.status_code == 302

    html = _get(client, f"/match/matches/{match.id}").get_data(as_text=True)
    assert CANONICO.replace("&", "&amp;") in html
    assert 'rel="noopener' in html
    # Testo dell'utente: si stampa con l'escape, mai come HTML.
    assert "Finale &lt;b&gt;serie C&lt;/b&gt;" in html
    assert "Finale <b>serie C</b>" not in html


def test_la_route_rifiuta_un_estraneo(app):
    p1, p2, estraneo = _user(), _user(), _user()
    match = _sfida(p1, p2)

    resp = _post(
        _client_for(app, estraneo),
        f"/match/matches/{match.id}/info",
        data={"video_url": VIDEO},
    )
    assert resp.status_code in (302, 403)
    assert db.session.get(IndividualMatch, match.id).video_url is None


def test_un_link_sbagliato_non_cancella_quello_buono(app):
    p1, p2 = _user(), _user()
    match = _sfida(p1, p2)
    match.video_url = CANONICO
    db.session.commit()

    _post(
        _client_for(app, p1),
        f"/match/matches/{match.id}/info",
        data={"video_url": "https://example.com/video", "description": ""},
    )
    assert db.session.get(IndividualMatch, match.id).video_url == CANONICO


# --------------------------------------------------------------------------
# Partita di gara
# --------------------------------------------------------------------------


def test_il_giocatore_della_partita_di_gara_scrive_il_video():
    p1, p2 = _user(), _user()
    match, _director = _partita_di_gara(p1, p2)

    MatchInfoService.update_gara_match_video(match.id, p2, video_url=VIDEO)
    assert db.session.get(Match, match.id).video_url == CANONICO


def test_il_direttore_della_gara_scrive_il_video():
    p1, p2 = _user(), _user()
    match, director = _partita_di_gara(p1, p2)

    MatchInfoService.update_gara_match_video(match.id, director, video_url=VIDEO)
    assert db.session.get(Match, match.id).video_url == CANONICO


def test_un_altro_direttore_no():
    p1, p2 = _user(), _user()
    match, _director = _partita_di_gara(p1, p2)
    altro = _user(UserRole.DIRECTOR.value)

    with pytest.raises(PermissionDeniedError):
        MatchInfoService.update_gara_match_video(match.id, altro, video_url=VIDEO)


def test_la_pagina_della_partita_di_gara_mostra_il_link(app):
    p1, p2 = _user(), _user()
    match, director = _partita_di_gara(p1, p2)
    client = _client_for(app, director)

    resp = _post(client, f"/admin/match/{match.id}/video", data={"video_url": VIDEO})
    assert resp.status_code == 302
    assert db.session.get(Match, match.id).video_url == CANONICO

    html = _get(_client_for(app, p1), f"/admin/match/{match.id}").get_data(as_text=True)
    assert CANONICO.replace("&", "&amp;") in html


def test_la_route_di_gara_rifiuta_un_estraneo(app):
    p1, p2, estraneo = _user(), _user(), _user()
    match, _director = _partita_di_gara(p1, p2)

    _post(
        _client_for(app, estraneo),
        f"/admin/match/{match.id}/video",
        data={"video_url": VIDEO},
    )
    assert db.session.get(Match, match.id).video_url is None


# --------------------------------------------------------------------------
# Descrizione alla creazione
# --------------------------------------------------------------------------


def test_l_avvio_rapido_porta_la_descrizione():
    from models.individual_match.quick_match_service import QuickMatchService

    p1, p2 = _user(), _user()
    match = QuickMatchService.start(
        p1.id, p2.id, {"description": "Finale 1ª giornata, serie C FVG"}
    )
    assert (
        db.session.get(IndividualMatch, match.id).description
        == "Finale 1ª giornata, serie C FVG"
    )


def test_l_avvio_rapido_rifiuta_una_descrizione_troppo_lunga():
    from models.individual_match.quick_match_service import QuickMatchService

    p1, p2 = _user(), _user()
    with pytest.raises(ValidationError):
        QuickMatchService.start(
            p1.id, p2.id, {"description": "x" * (DESCRIPTION_MAX_LENGTH + 1)}
        )


def test_la_proposta_accettata_porta_la_descrizione_della_partita():
    from models.individual_match.proposal_service import ProposalService

    p1, p2 = _user(), _user()
    proposal = ProposalService.create_direct_proposal(
        proposer_id=p1.id,
        invited_user_ids=[p2.id],
        location="Sala Video",
        scheduled_at=utc_now() + timedelta(days=1),
        description="Ci vediamo alle nove?",
        match_description="Semifinale del torneo sociale",
    )
    match = ProposalService.accept_proposal(p2.id, proposal.id)

    saved = db.session.get(IndividualMatch, match.id)
    # Il messaggio all'invitato resta sulla proposta: non è la descrizione.
    assert saved.description == "Semifinale del torneo sociale"


# --------------------------------------------------------------------------
# Dove si legge la descrizione
# --------------------------------------------------------------------------


def test_la_descrizione_compare_nelle_liste(app):
    p1, p2 = _user(), _user()
    match = _sfida(p1, p2)
    match.description = "Finale della prima giornata"
    db.session.commit()
    client = _client_for(app, p1)

    for url in ("/match/", "/match/matches"):
        html = _get(client, url).get_data(as_text=True)
        assert "Finale della prima giornata" in html, url


def test_la_descrizione_compare_nello_storico():
    from models.player.history_service import HistoryFilters, PlayerHistoryService
    from models.certificazione import Vista

    p1, p2 = _user(), _user()
    match = _sfida(p1, p2)
    match.description = "Semifinale sociale"
    match.player1_confirmed = match.player2_confirmed = True
    db.session.commit()

    pagina, _stats = PlayerHistoryService.get_unified_match_history(
        p1.id, HistoryFilters(), vista=Vista.TUTTE
    )
    assert [v.description for v in pagina.items] == ["Semifinale sociale"]


def test_l_avvio_rapido_dal_modulo_porta_la_descrizione(app):
    p1, p2 = _user(), _user()
    resp = _post(
        _client_for(app, p1),
        "/match/quick",
        data={"opponent_id": p2.id, "description": "Amichevole del giovedì"},
    )
    assert resp.status_code == 302
    match = IndividualMatch.query.filter_by(player1_id=p1.id).one()
    assert match.description == "Amichevole del giovedì"
