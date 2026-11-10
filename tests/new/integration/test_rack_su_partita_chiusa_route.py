"""Il «+1» del giocatore su una partita chiusa: un messaggio, non un 500.

Rilievo della revisione del 2026-11-10. La route
`POST /player/match/<id>/racks/add` passava il triangolo al servizio anche a
partita chiusa sotto la distanza — interrotta a tempo sul 3-2 — e rispondeva
200 col punteggio cambiato. Ora il servizio rifiuta con un `ConflictError`:
qui si presidia il giunto, cioè che il rifiuto arrivi al telefono come un
errore leggibile e che il punteggio resti quello della chiusura.
"""

from __future__ import annotations

import pytest
from flask import g

from models.match.models import Match
from models.status_enum import MatchStatus

from tests.new.unit._partite_di_prova import crea_gara, crea_partita

pytestmark = pytest.mark.integration


def test_il_triangolo_su_partita_chiusa_torna_come_messaggio(
    client, db_session, isolated_players
):
    p = isolated_players
    gara = crea_gara(db_session)
    partita = crea_partita(
        db_session,
        gara,
        p,
        player1_score=3,
        player2_score=2,
        winner_id=p[0].id,
        status=MatchStatus.CLOSED_UNILATERALLY.value,
        closed_on_time=True,
    )
    partita_id = partita.id
    perdente_id = p[1].id

    g.pop("_login_user", None)
    accesso = client.post(
        "/auth/login", data={"username": p[1].username, "password": "player123"}
    )
    assert accesso.status_code in (200, 302)

    risposta = client.post(
        f"/player/match/{partita_id}/racks/add", data={"winner_id": perdente_id}
    )

    assert risposta.status_code == 400
    assert risposta.get_json()["error"]
    db_session.rollback()
    partita = db_session.get(Match, partita_id)
    assert (partita.player1_score, partita.player2_score) == (3, 2)
    assert partita.status == MatchStatus.CLOSED_UNILATERALLY.value
