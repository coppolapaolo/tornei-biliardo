"""L'export CSV del profilo contiene tutte le partite finite, non solo una metà.

Filtrava `Match.status == CLOSED_UNILATERALLY`, cioè le sole partite chiuse
dal direttore, a forfait o con la X: quelle chiuse dai due giocatori con la
doppia conferma (`CONFIRMED_BY_BOTH`) sparivano dal file, senza errori. È lo
stesso scambio che teneva monco lo storico dei profili (CLAUDE.md, «partita
giocata»). Anche la X a tavolino ha il suo nome: prima era «Bye».
"""

from __future__ import annotations

import csv
import io
from datetime import date

import pytest

from models import Gara, Match, User
from models.status_enum import GaraStatus, MatchStatus

pytestmark = pytest.mark.integration


def _righe(response):
    testo = response.get_data(as_text=True)
    return list(csv.reader(io.StringIO(testo)))


def test_l_export_contiene_anche_le_partite_confermate_dai_giocatori(
    logged_in_client, db_session
):
    client, giocatore = logged_in_client(role="player", username_prefix="export")
    avversario = User(username="avversario_export", email="avv_export@test.com")
    avversario.set_password("x")
    db_session.add(avversario)
    gara = Gara(
        name="Gara esportata",
        number=1,
        date=date(2026, 9, 1),
        discipline="palla 8",
        status=GaraStatus.COMPLETED.value,
        distance=5,
    )
    db_session.add(gara)
    db_session.flush()
    for turno, stato in (
        (1, MatchStatus.CLOSED_UNILATERALLY.value),
        (2, MatchStatus.CONFIRMED_BY_BOTH.value),
    ):
        db_session.add(
            Match(
                gara_id=gara.id,
                round_number=turno,
                player1_id=giocatore.id,
                player2_id=avversario.id,
                player1_score=5,
                player2_score=3,
                winner_id=giocatore.id,
                status=stato,
            )
        )
    db_session.add(
        Match(
            gara_id=gara.id,
            round_number=3,
            player1_id=giocatore.id,
            player2_id=None,
            player1_score=0,
            player2_score=0,
            winner_id=giocatore.id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
        )
    )
    db_session.commit()

    response = client.get(f"/player/profile/{giocatore.id}/export/csv")

    assert response.status_code == 200
    partite = [r for r in _righe(response)[1:] if r and r[0] == "Tournament Match"]
    assert sorted(int(r[6]) for r in partite) == [1, 2, 3]
    avversari = {int(r[6]): r[3] for r in partite}
    assert avversari[3] == "X a tavolino"
    assert "Bye" not in response.get_data(as_text=True)
