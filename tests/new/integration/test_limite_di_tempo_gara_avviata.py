"""Il limite di tempo cambiato a gara avviata vale dal turno dopo (ADR-075, ADR-077).

Gara singola, Amalfi: il direttore mette 30 minuti dalla pagina «gara
avviata». Le partite del turno 1 restano senza limite, quelle del turno 2
nascono con 30, e la storia lo scrive «dal turno 2».
"""

from __future__ import annotations

import json

import pytest

from models import Gara, Match
from models.classification.models import RoundClassification
from models.competition.round_service import RoundService
from models.status_enum import MatchStatus
from models.storia.service import StoriaModificheService
from routes.admin.competition.form_parser import GaraFormParser

from .test_modifica_a_gara_avviata import _gara_avviata, _login, direttore  # noqa: F401

pytestmark = pytest.mark.integration


def test_trenta_minuti_dal_turno_dopo(client, db_session, direttore):  # noqa: F811
    gara = _gara_avviata(db_session, direttore)
    primo = Match.query.filter_by(gara_id=gara.id, round_number=1).all()
    assert all(m.time_limit_minutes is None for m in primo)

    _login(client, direttore)
    pagina = client.get(f"/admin/gara/{gara.id}/edit").get_data(as_text=True)
    assert 'name="time_limit_minutes"' in pagina
    client.post(
        f"/admin/gara/{gara.id}/edit",
        data={
            "stato_iniziale": json.dumps(GaraFormParser.valori_attuali(gara)),
            "name": gara.name,
            "date": gara.date.isoformat(),
            "time": "20:00",
            "location": gara.location,
            "entry_fee": "",
            "description": "",
            "distance": "5",
            "discipline": "9_ball",
            "start_rule": "",
            "break_rule": "",
            "has_handicap": "false",
            "time_limit_minutes": "30",
            "odd_number_policy": "bye",
            "x_challenge_id": "",
            "withdraw_policy": gara.withdraw_policy,
            "catena_gara": GaraFormParser.valori_attuali(gara)["catena_gara"],
        },
    )
    gara = db_session.get(Gara, gara.id)
    assert gara.time_limit_minutes == 30
    assert all(db_session.get(Match, m.id).time_limit_minutes is None for m in primo)
    voci = StoriaModificheService.voci_della_gara(gara.id)
    per_turno = {v.from_round: {r.field for r in v.fields} for v in voci}
    assert "time_limit_minutes" in per_turno[2]

    # Chiuso il turno 1, il turno 2 nasce coi 30 minuti.
    for m in primo:
        if not m.is_bye:
            m.player1_score = 5
            m.winner_id = m.player1_id
            m.status = MatchStatus.CLOSED_UNILATERALLY.value
    db_session.commit()
    RoundClassification.calculate_classification_after_round(gara.id, 1)
    db_session.commit()
    RoundService.create_round_with_strategy(gara.id, 2)
    db_session.commit()
    secondo = Match.query.filter_by(gara_id=gara.id, round_number=2, is_bye=False).all()
    assert secondo and all(m.time_limit_minutes == 30 for m in secondo)
