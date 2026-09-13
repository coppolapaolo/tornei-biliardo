"""Lo schermo in sala dal client HTTP (canvas 3.10).

La pagina `/g/<indirizzo>/sala` e il suo poll sono pubblici: li apre un
computer della sala senza login. Qui si difendono le quattro cose che non
devono cambiare in silenzio: l'anonimo la vede, una prova (ADR-058) no, una
gara a tabellone dice che non e' ancora disponibile (issue #352), e la
pagina non scrive sul database.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta

import pytest
from flask import g

from models import Gara, Match
from models.base import db
from models.classification.models import RoundClassification
from models.competition.services import GaraService
from models.prova.service import ProvaService
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _utente(prefisso: str, role: str = UserRole.PLAYER.value) -> User:
    unico = uuid.uuid4().hex[:6]
    u = User(
        username=f"{prefisso}_{unico}",
        email=f"{prefisso}_{unico}@test.local",
        role=role,
    )
    u.set_password("secret123")
    db.session.add(u)
    db.session.commit()
    return u


def _gara(*, strategy="amalfi", status=GaraStatus.PLAYING.value, token=None) -> Gara:
    gara = Gara(
        number=1,
        name="Gara in sala",
        date=date.today(),
        location="Sala Test",
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
        matchmaking_strategy=strategy,
        status=status,
        current_round=1,
        rounds_count=3,
        min_participants=2,
        available_tables=json.dumps(["1", "2"]),
        public_token=token or uuid.uuid4().hex[:10],
    )
    db.session.add(gara)
    db.session.commit()
    return gara


def _partita(
    gara, p1, p2, s1, s2, *, status=MatchStatus.PLAYING.value, tavolo=None, turno=1
):
    m = Match(
        gara_id=gara.id,
        round_number=turno,
        player1_id=p1.id,
        player2_id=p2.id,
        player1_score=s1,
        player2_score=s2,
        status=status,
        table_assignment=tavolo,
    )
    db.session.add(m)
    db.session.commit()
    return m


def test_l_anonimo_vede_i_tavoli_senza_menu(client, db_session):
    gara = _gara()
    rossi, verdi = _utente("rossi"), _utente("verdi")
    _partita(gara, rossi, verdi, 4, 2, tavolo="1")

    r = client.get(f"/g/{gara.public_token}/sala")

    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="schermoSala"' in html
    assert rossi.username in html and verdi.username in html
    assert 'class="c7-sala__punti c7-num">4<' in html
    # Il tavolo 2 e' libero.
    assert "Libero" in html
    # Niente guscio dell'app: ne' colonna laterale ne' comando per richiuderla.
    assert "c7-sidetoggle" not in html
    assert 'name="robots" content="noindex"' in html
    assert f"/sse/poll/sala/{gara.public_token}" in html


def test_la_classifica_gia_calcolata_ha_le_medaglie(client, db_session):
    gara = _gara()
    rossi, verdi = _utente("rossi"), _utente("verdi")
    _partita(gara, rossi, verdi, 5, 2, status=MatchStatus.CLOSED_UNILATERALLY.value)
    for pos, u in ((1, rossi), (2, verdi)):
        db.session.add(
            RoundClassification(
                gara_id=gara.id,
                round_number=1,
                user_id=u.id,
                position=pos,
                matches_won=2 - pos,
                rack_difference=3 if pos == 1 else -3,
            )
        )
    db.session.commit()

    html = client.get(f"/g/{gara.public_token}/sala").get_data(as_text=True)

    assert "Classifica dopo il turno 1" in html
    assert "c7-pos--1" in html and "c7-pos--2" in html
    assert "+3" in html


def test_la_pagina_non_ricalcola_la_classifica(client, db_session, monkeypatch):
    """Anonima e ricaricata a ogni evento: non deve scrivere sul database."""
    gara = _gara()
    rossi, verdi = _utente("rossi"), _utente("verdi")
    _partita(gara, rossi, verdi, 5, 2, status=MatchStatus.CLOSED_UNILATERALLY.value)

    def vietato(*args, **kwargs):
        raise AssertionError("lo schermo in sala non ricalcola la classifica")

    monkeypatch.setattr(
        RoundClassification, "calculate_classification_after_round", vietato
    )

    assert client.get(f"/g/{gara.public_token}/sala").status_code == 200


def test_una_gara_a_tabellone_dice_che_non_e_ancora_disponibile(client, db_session):
    gara = _gara(strategy="direct_elimination")

    html = client.get(f"/g/{gara.public_token}/sala").get_data(as_text=True)

    assert "non è ancora disponibile" in html
    assert 'class="c7-sala__tavoli' not in html


def test_un_indirizzo_sconosciuto_e_404(client, db_session):
    assert client.get("/g/nessuna-gara-cosi/sala").status_code == 404
    assert client.get("/sse/poll/sala/nessuna-gara-cosi").status_code == 404


def test_il_poll_pubblico_risponde_all_anonimo(client, db_session):
    gara = _gara()

    r = client.get(f"/sse/poll/sala/{gara.public_token}")

    assert r.status_code == 200
    corpo = r.get_json()
    assert "cursor" in corpo and corpo["events"] == []


def test_una_prova_non_ha_schermo_in_sala(client, db_session):
    """ADR-058: da fuori una prova non esiste, e lo schermo passa dallo stesso
    indirizzo della vetrina."""
    direttore = _utente("dir", role=UserRole.DIRECTOR.value)
    prova = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Prova segreta {uuid.uuid4().hex[:4]}",
        date=date.today() + timedelta(days=1),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        director_id=direttore.id,
        min_participants=4,
        max_participants=8,
        status=GaraStatus.INSCRIPTION.value,
        **ProvaService.campi_di_creazione(),
    )
    db.session.commit()
    token = prova.public_token
    # Come in `test_prova_visibilita`: la sessione del test non e' quella di
    # una richiesta vera, e l'identity map servirebbe la prova senza filtro.
    g.pop("_login_user", None)
    db.session.expunge_all()

    assert client.get(f"/g/{token}/sala").status_code == 404
    assert client.get(f"/sse/poll/sala/{token}").status_code == 404
