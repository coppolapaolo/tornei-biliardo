"""Gli esercizi fra i turni si registrano dalla pagina della gara del direttore.

Un esercizio fra i turni (`GaraChallenge`) si gioca «dopo il turno N»: a turno
N concluso la pagina del direttore mostra una riga per giocatore attivo, e il
foglio registra il tentativo con l'endpoint di chi dirige
(`admin.match.record_challenge_attempt`), cioe' con lo stesso servizio e gli
stessi controlli della pagina della partita.

Qui: le righe compaiono dopo il turno giusto e non prima; il limite dei
tentativi e il tetto del punteggio li impone il servizio; chi dirige — anche
senza essere admin — registra per un giocatore, ma solo per chi gioca la
gara; la forma a esito; la competizione di prova si comporta allo stesso modo;
e la pagina della partita manda il direttore all'endpoint giusto.
"""

from __future__ import annotations

from datetime import date

import pytest
from flask import url_for

from models import Gara, Inscription, Match
from models.challenge.models import Challenge
from models.competition.gara_challenge import GaraChallenge, GaraChallengeAttempt
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _login(client, db_session, username, role):
    from models.user.services import UserService

    user = UserService.create_user(username, f"{username}@test.local", "pw12345")
    user.role = role
    db_session.commit()
    resp = client.post(
        "/auth/login", data={"username": username, "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    return user


def _scenario(
    db_session,
    director,
    *,
    turno_chiuso,
    a_esito=False,
    tentativi=2,
    tetto=None,
    is_prova=False,
):
    """Una gara Amalfi al turno 1 con quattro giocatori, un ritirato e un
    esercizio dopo il turno 1."""
    from models.user.services import UserService

    gara = Gara(
        number=1,
        name="Gara con esercizio",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
        current_round=1,
        rounds_count=3,
        min_participants=4,
        director_id=director.id,
        is_prova=is_prova,
    )
    db_session.add(gara)
    db_session.commit()
    nomi = ("eft_anna", "eft_bruno", "eft_carla", "eft_dario", "eft_ritirato")
    giocatori = [UserService.create_user(n, f"{n}@test.local", "pw12345") for n in nomi]
    for u in giocatori:
        db_session.add(
            Inscription(
                user_id=u.id,
                gara_id=gara.id,
                is_waitlist=False,
                is_withdrawn=(u.username == "eft_ritirato"),
            )
        )
    stato = (
        MatchStatus.CLOSED_UNILATERALLY.value
        if turno_chiuso
        else MatchStatus.PLAYING.value
    )
    for a, b in ((giocatori[0], giocatori[1]), (giocatori[2], giocatori[3])):
        m = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=a.id,
            player2_id=b.id,
            player1_score=5 if turno_chiuso else 1,
            player2_score=3 if turno_chiuso else 0,
            status=stato,
        )
        if turno_chiuso:
            m.winner_id = a.id
        db_session.add(m)
    sfida = Challenge(
        title="Spot shot di prova",
        description="Esercizio fra i turni",
        image_path="/x.png",
        pass_fail_only=a_esito,
        max_score=tetto,
        is_active=True,
        created_by_id=director.id,
    )
    db_session.add(sfida)
    db_session.commit()
    gc = GaraChallenge(
        gara_id=gara.id,
        challenge_id=sfida.id,
        round_number=1,
        max_attempts=tentativi,
        added_by_id=director.id,
    )
    db_session.add(gc)
    db_session.commit()
    return gara, gc, giocatori


def _url_tentativo(client):
    with client.application.test_request_context():
        return url_for("admin.match.record_challenge_attempt")


def _pagina(client, gara):
    resp = client.get(f"/admin/gara/{gara.id}")
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def test_prima_che_il_turno_sia_concluso_l_esercizio_e_solo_in_elenco(
    client, db_session
):
    director = _login(client, db_session, "eft_dir1", UserRole.DIRECTOR.value)
    gara, _gc, _g = _scenario(db_session, director, turno_chiuso=False)

    html = _pagina(client, gara)

    assert "Esercizi fra i turni" in html
    assert "dopo il turno 1" in html
    assert "Esercizio dopo il turno 1" not in html
    assert "apriTentativoEsercizio(this)" not in html
    assert "tentativoEsercizioModal" not in html
    # La regola e' «dopo il turno N»: la vecchia lista diceva «dal turno».
    assert "dal turno" not in html


def test_a_turno_concluso_ogni_giocatore_attivo_ha_la_sua_riga(client, db_session):
    director = _login(client, db_session, "eft_dir2", UserRole.DIRECTOR.value)
    gara, gc, giocatori = _scenario(db_session, director, turno_chiuso=True)

    html = _pagina(client, gara)

    assert "Esercizio dopo il turno 1" in html
    assert "4 da registrare" in html
    for g in giocatori[:4]:
        assert f'data-user-id="{g.id}"' in html
    # Chi si e' ritirato non gioca l'esercizio.
    assert f'data-user-id="{giocatori[4].id}"' not in html
    assert "tentativoEsercizioModal" in html
    assert 'data-a-esito="0"' in html
    # Una lista sola: la sezione in sola lettura non si ripete.
    assert html.count("Spot shot di prova") >= 1
    assert "Esercizi fra i turni" not in html


def test_il_direttore_registra_per_un_giocatore(client, db_session):
    director = _login(client, db_session, "eft_dir3", UserRole.DIRECTOR.value)
    gara, gc, giocatori = _scenario(db_session, director, turno_chiuso=True, tetto=15)
    anna = giocatori[0]

    resp = client.post(
        _url_tentativo(client),
        json={
            "gara_challenge_id": gc.id,
            "user_id": anna.id,
            "score": 9,
            "round_when_attempted": 1,
        },
    )
    assert resp.status_code == 200, resp.get_json()

    tentativo = GaraChallengeAttempt.query.filter_by(gara_challenge_id=gc.id).one()
    assert (tentativo.user_id, tentativo.score) == (anna.id, 9)

    html = _pagina(client, gara)
    assert "1 tentativo su 2" in html
    assert "3 da registrare" in html


def test_i_tentativi_si_fermano_al_massimo(client, db_session):
    director = _login(client, db_session, "eft_dir4", UserRole.DIRECTOR.value)
    gara, gc, giocatori = _scenario(
        db_session, director, turno_chiuso=True, tentativi=1
    )
    dati = {"gara_challenge_id": gc.id, "user_id": giocatori[1].id, "score": 3}

    assert client.post(_url_tentativo(client), json=dati).status_code == 200
    secondo = client.post(_url_tentativo(client), json=dati)
    assert secondo.status_code == 400
    assert GaraChallengeAttempt.query.filter_by(gara_challenge_id=gc.id).count() == 1

    # Nuovi tentativi no; la riga si apre ancora, ma solo per togliere quello
    # registrato per sbaglio (dal 2026-09-13, finche' il turno dopo non parte).
    html = _pagina(client, gara)
    inizio = html.index(f'data-user-id="{giocatori[1].id}"')
    riga = html[html.rindex("<button", 0, inizio) : html.index(">", inizio)]
    assert 'data-puo-tentare="0"' in riga
    assert '"id": ' in riga
    assert "finiti" in html


def test_non_si_registra_per_chi_non_gioca_la_gara(client, db_session):
    director = _login(client, db_session, "eft_dir5", UserRole.DIRECTOR.value)
    _gara, gc, giocatori = _scenario(db_session, director, turno_chiuso=True)

    for chi in (director, giocatori[4]):
        resp = client.post(
            _url_tentativo(client),
            json={"gara_challenge_id": gc.id, "user_id": chi.id, "score": 3},
        )
        assert resp.status_code == 400
    assert GaraChallengeAttempt.query.filter_by(gara_challenge_id=gc.id).count() == 0


def test_il_punteggio_non_supera_il_tetto_dell_esercizio(client, db_session):
    director = _login(client, db_session, "eft_dir6", UserRole.DIRECTOR.value)
    _gara, gc, giocatori = _scenario(db_session, director, turno_chiuso=True, tetto=10)

    for punteggio in (11, -1):
        resp = client.post(
            _url_tentativo(client),
            json={
                "gara_challenge_id": gc.id,
                "user_id": giocatori[0].id,
                "score": punteggio,
            },
        )
        assert resp.status_code == 400
    assert GaraChallengeAttempt.query.filter_by(gara_challenge_id=gc.id).count() == 0


def test_chi_non_dirige_la_gara_non_registra(client, db_session):
    from models.user.services import UserService

    padrone = UserService.create_user(
        "eft_padrone", "eft_padrone@test.local", "pw12345"
    )
    padrone.role = UserRole.DIRECTOR.value
    db_session.commit()
    _gara, gc, giocatori = _scenario(db_session, padrone, turno_chiuso=True)
    _login(client, db_session, "eft_altro", UserRole.DIRECTOR.value)

    resp = client.post(
        _url_tentativo(client),
        json={"gara_challenge_id": gc.id, "user_id": giocatori[0].id, "score": 3},
    )
    assert resp.status_code == 403


def test_a_esito_il_foglio_ha_riuscito_e_non_riuscito(client, db_session):
    director = _login(client, db_session, "eft_dir7", UserRole.DIRECTOR.value)
    gara, gc, giocatori = _scenario(
        db_session, director, turno_chiuso=True, a_esito=True
    )

    html = _pagina(client, gara)
    assert 'data-a-esito="1"' in html
    assert 'data-esito="true"' in html and 'data-esito="false"' in html

    senza_esito = client.post(
        _url_tentativo(client),
        json={"gara_challenge_id": gc.id, "user_id": giocatori[2].id, "score": 1},
    )
    assert senza_esito.status_code == 400

    resp = client.post(
        _url_tentativo(client),
        json={"gara_challenge_id": gc.id, "user_id": giocatori[2].id, "passed": True},
    )
    assert resp.status_code == 200
    tentativo = GaraChallengeAttempt.query.filter_by(gara_challenge_id=gc.id).one()
    assert tentativo.passed is True

    html = _pagina(client, gara)
    assert "Riuscito" in html


def test_la_competizione_di_prova_si_comporta_allo_stesso_modo(client, db_session):
    director = _login(client, db_session, "eft_dir8", UserRole.DIRECTOR.value)
    gara, gc, giocatori = _scenario(
        db_session, director, turno_chiuso=True, is_prova=True
    )

    html = _pagina(client, gara)
    assert "Esercizio dopo il turno 1" in html
    for g in giocatori[:4]:
        assert f'data-user-id="{g.id}"' in html

    resp = client.post(
        _url_tentativo(client),
        json={"gara_challenge_id": gc.id, "user_id": giocatori[3].id, "score": 4},
    )
    assert resp.status_code == 200


def test_la_pagina_della_partita_manda_il_direttore_all_endpoint_della_gara(
    client, db_session
):
    """Regressione: un direttore non admin registrava sull'endpoint del
    giocatore, che scrive sempre per chi chiama — 403, o il tentativo
    dell'avversario finito a lui."""
    director = _login(client, db_session, "eft_dir9", UserRole.DIRECTOR.value)
    gara, _gc, _g = _scenario(db_session, director, turno_chiuso=False)
    match = Match.query.filter_by(gara_id=gara.id).first()

    with client.application.test_request_context():
        url_partita = url_for("admin.match.match_detail", match_id=match.id)
    resp = client.get(url_partita)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)

    assert "recordChallengeAttempt(" in html
    assert _url_tentativo(client) in html
    # Il segnaposto dell endpoint del giocatore, che registra per chi chiama.
    assert "987654321" not in html
