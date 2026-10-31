"""Un campionato con i playoff disattivati non resta in attesa dei playoff.

Rilievo del 2026-10-31 (domanda di un direttore sulla issue #732): dopo
«Passa alla fase playoff» il direttore può togliere la configurazione con la
✕ (`deactivate_configuration`). `has_playoff_configurations` contava anche le
configurazioni disattivate, mentre `compute_campionato_status` cercava fra le
attive una finale conclusa: senza attive ricadeva su AWAITING_PLAYOFF, e il
campionato restava «In attesa dei playoff» per sempre, con una linguetta
Playoff vuota. Una configurazione disattivata non è un playoff.
"""

import uuid

import pytest

from models import Campionato
from models.base import db, utc_now
from models.playoff.fase import fase_playoff
from models.playoff.models import PlayoffConfiguration, PlayoffType
from models.playoff.services import PlayoffService
from models.status_enum import TournamentStatus

pytestmark = pytest.mark.unit


def _campionato_terminato_con_playoff(db_session):
    c = Campionato(
        name=f"Camp {uuid.uuid4().hex[:8]}", campionato_type="amalfi", is_active=True
    )
    db_session.add(c)
    db_session.flush()
    c.terminated_at = utc_now()
    cfg = PlayoffConfiguration(
        campionato_id=c.id,
        name="Elite",
        playoff_type=PlayoffType.TOP_N,
        max_participants=8,
        positions_from=1,
        positions_to=8,
        is_active=True,
    )
    db_session.add(cfg)
    db_session.commit()
    return c, cfg


def test_prima_di_disattivare_il_campionato_aspetta_i_playoff(db_session):
    c, _cfg = _campionato_terminato_con_playoff(db_session)
    assert c.get_status() == TournamentStatus.AWAITING_PLAYOFF.value


def test_tolti_i_playoff_il_campionato_e_completato(db_session):
    c, cfg = _campionato_terminato_con_playoff(db_session)

    PlayoffService.deactivate_configuration(cfg.id)

    campionato = db.session.get(Campionato, c.id)
    assert campionato.has_playoff_configurations() is False
    assert campionato.get_status() == TournamentStatus.COMPLETED.value
    assert fase_playoff(campionato) is None
