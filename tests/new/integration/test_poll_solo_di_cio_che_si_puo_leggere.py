"""Il poll risponde solo a chi può leggere la pagina che aggiorna (2026-11-10).

Il poll delle sfide individuali rispondeva a qualunque utente collegato per
qualunque id, mentre la pagina della sfida la aprono solo i due giocatori e
chi la segna, e non la vede chi ne è stato escluso. Ora il poll segue la
stessa regola di lettura — più chi può guardare il referto, che usa lo stesso
poll (ADR-069).

Il poll delle gare resta aperto a ogni utente collegato, perché le gare sono
pubbliche. Fa eccezione la competizione di prova (ADR-058), che da fuori non
deve esistere: il suo poll rispondeva comunque a chiunque ne indovinasse l'id.
Ora passa dal filtro delle prove.
"""

import json
import uuid
from datetime import date, timedelta

from models import Gara, User
from models.base import db, utc_now
from models.individual_match.match_models import IndividualMatch
from models.match.break_rules import StartRule
from models.prova.visibility import prova_visibili
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole
from routes.sse import emit_gara_event, emit_individual_match_event


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


def _sfida(db_session, a, b, **campi):
    sfida = IndividualMatch(
        player1_id=a.id,
        player2_id=b.id,
        scheduled_at=utc_now(),
        status=MatchStatus.IN_PROGRESS,
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=True,
        start_rule=StartRule.FIRST_PLAYER.value,
        **campi,
    )
    db.session.add(sfida)
    db.session.commit()
    return sfida


def _gara(db_session, is_prova=False):
    gara = Gara(
        name=f"G{uuid.uuid4().hex[:6]}",
        number=1,
        date=date.today() + timedelta(days=1),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        is_race_to=True,
        status=GaraStatus.PLAYING.value,
        is_prova=is_prova,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def test_un_estraneo_non_legge_il_poll_di_una_sfida(db_session, logged_in_client):
    client, _estraneo = logged_in_client(role="player", username_prefix="estraneo")
    sfida = _sfida(db_session, _utente(db_session, "a"), _utente(db_session, "b"))
    emit_individual_match_event(sfida.id, "rack_added", {"punteggio": "1-0"})

    risposta = client.get(f"/sse/poll/individual_match/{sfida.id}?since=0")

    assert risposta.status_code == 403
    assert "1-0" not in risposta.get_data(as_text=True)


def test_un_giocatore_legge_il_poll_della_sua_sfida(db_session, logged_in_client):
    client, io = logged_in_client(role="player", username_prefix="io")
    sfida = _sfida(db_session, io, _utente(db_session, "b"))
    emit_individual_match_event(sfida.id, "rack_added", {"punteggio": "1-0"})

    risposta = client.get(f"/sse/poll/individual_match/{sfida.id}?since=0")

    assert risposta.status_code == 200
    assert [e["type"] for e in risposta.get_json()["events"]] == ["rack_added"]


def test_chi_segna_la_partita_di_altri_due_ne_legge_il_poll(
    db_session, logged_in_client
):
    client, chi_segna = logged_in_client(role="director", username_prefix="segna")
    sfida = _sfida(
        db_session,
        _utente(db_session, "a"),
        _utente(db_session, "b"),
        scorer_id=chi_segna.id,
    )

    risposta = client.get(f"/sse/poll/individual_match/{sfida.id}")

    assert risposta.status_code == 200


def test_la_partita_rifiutata_non_si_legge_piu_dal_poll(db_session, logged_in_client):
    client, io = logged_in_client(role="player", username_prefix="io")
    chi_segna = _utente(db_session, "segna")
    sfida = _sfida(db_session, io, _utente(db_session, "b"), scorer_id=chi_segna.id)
    sfida.status = MatchStatus.REJECTED
    db_session.commit()
    assert db_session.get(IndividualMatch, sfida.id).is_hidden_from(io.id)

    risposta = client.get(f"/sse/poll/individual_match/{sfida.id}")

    assert risposta.status_code == 403


def test_il_poll_di_una_sfida_che_non_esiste_e_404(db_session, logged_in_client):
    client, _io = logged_in_client(role="player", username_prefix="io")

    assert client.get("/sse/poll/individual_match/987654").status_code == 404


def test_il_poll_di_una_gara_resta_di_ogni_utente_collegato(
    db_session, logged_in_client
):
    client, _io = logged_in_client(role="player", username_prefix="io")
    gara = _gara(db_session)
    emit_gara_event(gara.id, "match_updated", {"tavolo": "3"})

    risposta = client.get(f"/sse/poll/gara/{gara.id}?since=0")

    assert risposta.status_code == 200
    assert len(risposta.get_json()["events"]) == 1


def test_il_poll_di_una_prova_non_risponde_a_chi_non_la_dirige(
    db_session, logged_in_client
):
    client, _io = logged_in_client(role="player", username_prefix="io")
    with prova_visibili():
        prova = _gara(db_session, is_prova=True)
        prova_id = prova.id
    emit_gara_event(prova_id, "match_updated", {"tavolo": "segreto"})

    risposta = client.get(f"/sse/poll/gara/{prova_id}?since=0")

    assert risposta.status_code == 404
    assert "segreto" not in risposta.get_data(as_text=True)


def test_il_poll_di_una_prova_risponde_all_admin(db_session, logged_in_client):
    client, _admin = logged_in_client(role="admin", username_prefix="adm")
    with prova_visibili():
        prova = _gara(db_session, is_prova=True)
        prova_id = prova.id
    emit_gara_event(prova_id, "match_updated", {"tavolo": "3"})

    risposta = client.get(f"/sse/poll/gara/{prova_id}?since=0")

    assert risposta.status_code == 200
    assert json.dumps(risposta.get_json()["events"]).count("match_updated") == 1
