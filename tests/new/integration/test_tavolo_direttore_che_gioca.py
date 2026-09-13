"""Il direttore che gioca chiude la sua partita dal segnapunti: il tavolo passa.

La strada vera dell'utente, attraverso la route del giocatore: chi dirige la
gara segna con `authoritative`, quindi al triangolo decisivo la partita si
chiude da sola. Regressione del 2026-09-13, vedi
`tests/new/unit/test_tavolo_riassegnato_a_ogni_chiusura.py`.
"""

from datetime import date

import pytest

from models.competition.models import Gara
from models.match.models import Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def test_il_direttore_che_gioca_passa_il_tavolo_alla_partita_in_attesa(
    client, db_session
):
    from models.user.models import DirectorAssignment
    from models.user.services import UserService

    direttore = UserService.create_user(
        "tav_direttore", "tav_direttore@test.local", "pw12345"
    )
    direttore.role = UserRole.DIRECTOR.value
    altri = [
        UserService.create_user(f"tav_g{n}", f"tav_g{n}@test.local", "pw12345")
        for n in range(5)
    ]
    gara = Gara(
        number=1,
        name="Gara del direttore che gioca",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
        current_round=1,
        rounds_count=3,
        min_participants=4,
    )
    gara.available_tables = '["1", "2"]'
    db_session.add(gara)
    db_session.commit()
    db_session.add(
        DirectorAssignment(
            user_id=direttore.id,
            entity_type="gara",
            entity_id=gara.id,
            assigned_by_id=direttore.id,
        )
    )

    def partita(p1, p2, tavolo):
        m = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=p1.id,
            player2_id=p2.id,
            table_assignment=tavolo,
            status=(MatchStatus.PLAYING.value if tavolo else MatchStatus.PENDING.value),
            player1_score=0,
            player2_score=0,
        )
        db_session.add(m)
        return m

    sua = partita(direttore, altri[0], "1")
    partita(altri[1], altri[2], "2")
    attesa = partita(altri[3], altri[4], None)
    db_session.commit()
    sua_id, attesa_id = sua.id, attesa.id

    resp = client.post(
        "/auth/login", data={"username": "tav_direttore", "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    for _ in range(3):
        r = client.post(
            f"/player/match/{sua_id}/racks/add", data={"winner_id": direttore.id}
        )
        assert r.status_code == 200, r.get_json()

    db_session.expire_all()
    chiusa = db_session.get(Match, sua_id)
    assert MatchStatus.is_finished(chiusa.status)
    assert chiusa.table_assignment is None
    riletta = db_session.get(Match, attesa_id)
    assert riletta.table_assignment == "1"
    assert riletta.status == MatchStatus.PLAYING.value
