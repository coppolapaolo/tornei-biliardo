"""La partita deve appartenere alla gara scritta nell'indirizzo (2026-11-10).

Le route `/admin/gara/<gara_id>/match/<match_id>/…` controllavano il permesso
sulla sola gara dell'indirizzo e poi lavoravano sulla partita indicata, senza
verificare che fosse di quella gara: chi dirigeva una gara poteva agire sulle
partite di una gara che non dirigeva. Ora la partita che non appartiene alla
gara dell'indirizzo è «non trovata» (404), e il controllo sta nel servizio.

Nello stesso file `modification_check` dichiarava il parametro `_gara_id`
mentre Flask passa `gara_id`: rispondeva sempre con un errore interno.
"""

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Match, User
from models.campionato.models import Campionato
from models.competition.round_manager import AdvancedRoundManager
from models.exceptions import NotFoundError
from models.match.break_rules import StartRule
from models.match.models import Rack
from models.match.scoring_service import ScoringService
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import DirectorAssignment
from models.user.role_enum import UserRole


def _giocatori(db_session, quanti=2):
    sigla = uuid.uuid4().hex[:8]
    utenti = []
    for i in range(quanti):
        utente = User(
            username=f"pg{i}_{sigla}",
            email=f"pg{i}_{sigla}@test.com",
            role=UserRole.PLAYER.value,
        )
        utente.set_password("test123")
        utenti.append(utente)
    db_session.add_all(utenti)
    db_session.commit()
    return utenti


def _gara_in_corso(db_session):
    campionato = Campionato(
        name=f"C{uuid.uuid4().hex[:6]}",
        default_start_rule=StartRule.FIRST_PLAYER.value,
    )
    db_session.add(campionato)
    db_session.flush()
    gara = Gara(
        campionato_id=campionato.id,
        number=1,
        date=date.today() + timedelta(days=1),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=True,
        status=GaraStatus.PLAYING.value,
        current_round=1,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def _partita_con_tre_rack(db_session, gara):
    a, b = _giocatori(db_session)
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=a.id,
        player2_id=b.id,
        status=MatchStatus.PLAYING.value,
        table_assignment="1",
        match_distance=5,
        is_race_to=True,
    )
    db_session.add(match)
    db_session.commit()
    for _ in range(3):
        ScoringService.add_rack_for_player(
            match_id=match.id, user_id=a.id, winner_id=a.id
        )
    db_session.commit()
    assert Rack.query.filter_by(match_id=match.id).count() == 3
    return match


def _direttore_di(db_session, logged_in_client, gara):
    client, direttore = logged_in_client(role="director", username_prefix="dir")
    db_session.add(
        DirectorAssignment(
            user_id=direttore.id,
            entity_type="gara",
            entity_id=gara.id,
            assigned_by_id=direttore.id,
        )
    )
    db_session.commit()
    return client, direttore


def test_reset_avanzato_rifiuta_la_partita_di_un_altra_gara(
    db_session, logged_in_client
):
    altrui = _gara_in_corso(db_session)
    match = _partita_con_tre_rack(db_session, altrui)
    mia = _gara_in_corso(db_session)
    client, direttore = _direttore_di(db_session, logged_in_client, mia)
    assert not direttore.can_manage_competition(altrui.id)

    risposta = client.post(f"/admin/gara/{mia.id}/match/{match.id}/reset_advanced")

    assert risposta.status_code == 404
    db_session.expire_all()
    assert Rack.query.filter_by(match_id=match.id).count() == 3
    assert db_session.get(Match, match.id).player1_score == 3


def test_reset_avanzato_resta_a_chi_dirige_la_gara_della_partita(
    db_session, logged_in_client
):
    mia = _gara_in_corso(db_session)
    match = _partita_con_tre_rack(db_session, mia)
    client, _direttore = _direttore_di(db_session, logged_in_client, mia)

    risposta = client.post(f"/admin/gara/{mia.id}/match/{match.id}/reset_advanced")

    assert risposta.status_code == 302
    db_session.expire_all()
    assert Rack.query.filter_by(match_id=match.id).count() == 0
    assert db_session.get(Match, match.id).player1_score == 0


def test_il_servizio_rifiuta_la_partita_fuori_dalla_gara_indicata(db_session):
    altrui = _gara_in_corso(db_session)
    match = _partita_con_tre_rack(db_session, altrui)
    mia = _gara_in_corso(db_session)

    with pytest.raises(NotFoundError):
        AdvancedRoundManager.reset_match_with_validation(match.id, gara_id=mia.id)

    db_session.expire_all()
    assert Rack.query.filter_by(match_id=match.id).count() == 3


def test_modification_check_risponde_per_la_partita_della_gara(
    db_session, logged_in_client
):
    mia = _gara_in_corso(db_session)
    match = _partita_con_tre_rack(db_session, mia)
    client, _direttore = _direttore_di(db_session, logged_in_client, mia)

    risposta = client.get(f"/admin/gara/{mia.id}/match/{match.id}/modification_check")

    assert risposta.status_code == 200
    assert risposta.get_json()["match_id"] == match.id
    assert risposta.get_json()["can_modify"] is True


def test_modification_check_non_parla_delle_partite_di_un_altra_gara(
    db_session, logged_in_client
):
    altrui = _gara_in_corso(db_session)
    match = _partita_con_tre_rack(db_session, altrui)
    mia = _gara_in_corso(db_session)
    client, _direttore = _direttore_di(db_session, logged_in_client, mia)

    risposta = client.get(f"/admin/gara/{mia.id}/match/{match.id}/modification_check")

    assert risposta.status_code == 404
