"""La card del direttore con la distanza «esattamente N triangoli».

Regressione del 2026-09-13, trovata dall'utente provando la pagina della gara:
gli stepper salvano a ogni tocco un punteggio parziale, ma la route passava dal
controllo del risultato secco, che in modalità «esattamente N» pretende il
totale finale. Il primo + rispondeva «il totale dei triangoli (1) deve essere
esattamente 5» e sulla card non si riusciva a segnare nemmeno un triangolo.

Il risultato secco del modale resta invece rigoroso: lì un totale diverso da N
è un errore di battitura, e fino alla correzione di `TestExactModeValidation`
un 5-2 lasciava la partita aperta in silenzio.
"""

from models.match.models import Match
from models.match.scoring_service import ScoringService
from models.status_enum import MatchStatus
from models.user.role_enum import UserRole
from tests.new.integration.test_pagina_gara_direttore import _gara_in_gioco, _match

import pytest


@pytest.fixture
def admin_client(client, db_session):
    from models.user.services import UserService

    user = UserService.create_user("esatti_admin", "esatti_admin@test.local", "pw12345")
    user.role = UserRole.ADMIN.value
    db_session.commit()
    resp = client.post(
        "/auth/login", data={"username": "esatti_admin", "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    return client


def _partita_esatta(db_session, distance, suffix):
    gara = _gara_in_gioco(db_session, distance=distance)
    gara.is_race_to = False
    match = _match(db_session, gara, 0, 0, MatchStatus.PLAYING.value, suffix=suffix)
    match.table_assignment = "1"
    db_session.commit()
    return match


def test_la_card_segna_i_triangoli_uno_alla_volta(admin_client, db_session):
    match = _partita_esatta(db_session, 5, "_ex1")
    url = f"/admin/match/{match.id}/punteggio"

    r = admin_client.post(url, data={"player1_score": 1, "player2_score": 0})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["finished"] is False

    r = admin_client.post(url, data={"player1_score": 3, "player2_score": 1})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["finished"] is False
    assert r.get_json()["player1_score"] == 3

    r = admin_client.post(url, data={"player1_score": 3, "player2_score": 2})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["finished"] is True
    riletta = db_session.get(Match, match.id)
    assert MatchStatus.is_finished(riletta.status)
    assert riletta.winner_id == match.player1_id


def test_la_card_rifiuta_un_totale_oltre_la_distanza(admin_client, db_session):
    match = _partita_esatta(db_session, 5, "_ex2")
    r = admin_client.post(
        f"/admin/match/{match.id}/punteggio",
        data={"player1_score": 4, "player2_score": 2},
    )
    assert r.status_code == 400
    assert r.get_json()["success"] is False
    riletta = db_session.get(Match, match.id)
    assert (riletta.player1_score, riletta.player2_score) == (0, 0)


def test_con_distanza_pari_il_pareggio_chiude_senza_vincitore(admin_client, db_session):
    match = _partita_esatta(db_session, 4, "_ex3")
    url = f"/admin/match/{match.id}/punteggio"
    admin_client.post(url, data={"player1_score": 1, "player2_score": 1})
    r = admin_client.post(url, data={"player1_score": 2, "player2_score": 2})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["finished"] is True
    assert db_session.get(Match, match.id).winner_id is None


def test_il_risultato_secco_resta_rigoroso(admin_client, db_session):
    match = _partita_esatta(db_session, 5, "_ex4")
    with pytest.raises(ValueError, match="esatto numero"):
        ScoringService.set_match_result_direct(match.id, 2, 1)
