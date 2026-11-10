"""Acchito e runout di una sfida li registra solo chi la gioca (2026-11-10).

Le due azioni erano le uniche del blueprint delle sfide a non passare al
servizio chi le chiedeva: un utente collegato che non c'entrava poteva
registrare l'acchito o marcare un runout su una sfida fra altri due. Ora
vale la regola del segnapunti: i due giocatori, oppure chi tiene il referto
quando la partita è segnata da un terzo (ADR-084).
"""

import uuid

from models import User
from models.base import db, utc_now
from models.individual_match.individual_rack_service import IndividualRackService
from models.individual_match.match_models import IndividualMatch, IndividualRack
from models.match.break_rules import StartRule
from models.status_enum import Discipline, MatchStatus
from models.user.role_enum import UserRole


def _utente(db_session, prefisso):
    sigla = uuid.uuid4().hex[:8]
    utente = User(
        username=f"{prefisso}_{sigla}",
        email=f"{prefisso}_{sigla}@test.com",
        role=UserRole.PLAYER.value,
    )
    utente.set_password("test123")
    db_session.add(utente)
    db_session.commit()
    return utente


def _sfida(db_session, a, b, regola, scorer_id=None):
    sfida = IndividualMatch(
        player1_id=a.id,
        player2_id=b.id,
        scheduled_at=utc_now(),
        status=MatchStatus.IN_PROGRESS,
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=True,
        start_rule=regola,
        scorer_id=scorer_id,
    )
    db.session.add(sfida)
    db.session.commit()
    return sfida


def _sfida_con_un_triangolo(db_session, a, b):
    sfida = _sfida(db_session, a, b, StartRule.FIRST_PLAYER.value)
    IndividualRackService.add_rack_for_player(
        match_id=sfida.id, user_id=a.id, winner_id=a.id
    )
    db_session.commit()
    rack = IndividualRack.query.filter_by(match_id=sfida.id).first()
    return sfida, rack


def _acchito(client, sfida, vincitore):
    return client.post(
        f"/match/matches/{sfida.id}/lag",
        json={"lag_winner_id": vincitore.id, "first_break_player_id": vincitore.id},
    )


def test_un_estraneo_non_registra_l_acchito(db_session, logged_in_client):
    client, _estraneo = logged_in_client(role="player", username_prefix="estraneo")
    a, b = _utente(db_session, "a"), _utente(db_session, "b")
    sfida = _sfida(db_session, a, b, StartRule.LAG.value)

    risposta = _acchito(client, sfida, b)

    assert risposta.status_code == 403
    db_session.expire_all()
    assert db_session.get(IndividualMatch, sfida.id).lag_winner_id is None


def test_un_giocatore_registra_l_acchito(db_session, logged_in_client):
    client, io = logged_in_client(role="player", username_prefix="io")
    b = _utente(db_session, "b")
    sfida = _sfida(db_session, io, b, StartRule.LAG.value)

    risposta = _acchito(client, sfida, b)

    assert risposta.status_code == 200
    db_session.expire_all()
    assert db_session.get(IndividualMatch, sfida.id).lag_winner_id == b.id


def test_un_estraneo_non_marca_il_runout(db_session, logged_in_client):
    client, _estraneo = logged_in_client(role="player", username_prefix="estraneo")
    a, b = _utente(db_session, "a"), _utente(db_session, "b")
    sfida, rack = _sfida_con_un_triangolo(db_session, a, b)

    risposta = client.post(f"/match/matches/{sfida.id}/racks/{rack.id}/runout", json={})

    assert risposta.status_code == 403
    db_session.expire_all()
    assert not db_session.get(IndividualRack, rack.id).is_run_out


def test_un_giocatore_marca_il_runout(db_session, logged_in_client):
    client, io = logged_in_client(role="player", username_prefix="io")
    b = _utente(db_session, "b")
    sfida, rack = _sfida_con_un_triangolo(db_session, io, b)

    risposta = client.post(f"/match/matches/{sfida.id}/racks/{rack.id}/runout", json={})

    assert risposta.status_code == 200
    db_session.expire_all()
    assert db_session.get(IndividualRack, rack.id).is_run_out


def test_nella_partita_di_altri_due_l_acchito_e_di_chi_segna(
    db_session, logged_in_client
):
    client, giocatore = logged_in_client(role="player", username_prefix="gioca")
    b = _utente(db_session, "b")
    chi_segna = _utente(db_session, "segna")
    sfida = _sfida(
        db_session, giocatore, b, StartRule.LAG.value, scorer_id=chi_segna.id
    )

    assert _acchito(client, sfida, b).status_code == 403

    IndividualRackService.register_lag(sfida.id, chi_segna.id, b.id, b.id)
    db_session.expire_all()
    assert db_session.get(IndividualMatch, sfida.id).lag_winner_id == b.id
