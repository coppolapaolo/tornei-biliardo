"""Il pulsante «Valida Risultato» compare anche sui pareggi.

Bug (esplorazione per i gironi multipli, 2026-10-06) —
`templates/components/_match_admin_controls.html`:

il pulsante chiedeva `match.winner_id and not match.validated_by_admin`. Il
secondo campo su `Match` non esiste (vive su `Rack`): Jinja lo valuta falso
senza protestare, quindi la condizione era il solo vincitore. Con «esattamente
N triangoli» e N pari il pareggio esiste — a 3-3 la partita è alla distanza e
`winner_id` resta vuoto — e il direttore non trovava il pulsante per chiuderla,
mentre la card della pagina della gara la dava «da validare».

La regola è una sola, `Match.is_awaiting_validation`: alla distanza, non
ancora chiusa e senza la doppia conferma dei giocatori.
"""

from __future__ import annotations

import pytest

from models.match.models import Match
from models.status_enum import MatchStatus
from models.user.role_enum import UserRole
from tests.new.integration.test_pagina_gara_direttore import _gara_in_gioco, _match

pytestmark = pytest.mark.integration

PULSANTE = 'onclick="validateMatch('


@pytest.fixture
def admin_client(client, db_session):
    from models.user.services import UserService

    user = UserService.create_user("valida_admin", "valida_admin@test.local", "pw12345")
    user.role = UserRole.ADMIN.value
    db_session.commit()
    resp = client.post(
        "/auth/login", data={"username": "valida_admin", "password": "pw12345"}
    )
    assert resp.status_code in (200, 302)
    return client


def _partita(db_session, p1, p2, *, distance, race_to, suffix) -> Match:
    gara = _gara_in_gioco(db_session, distance=distance)
    gara.is_race_to = race_to
    match = _match(db_session, gara, p1, p2, MatchStatus.PLAYING.value, suffix=suffix)
    match.table_assignment = "1"
    db_session.commit()
    return match


def _pagina(client, match: Match) -> str:
    return client.get(f"/admin/match/{match.id}").get_data(as_text=True)


def test_pareggio_alla_distanza_si_valida(admin_client, db_session):
    match = _partita(db_session, 3, 3, distance=6, race_to=False, suffix="_vp")
    assert match.winner_id is None
    assert PULSANTE in _pagina(admin_client, match)


def test_vittoria_alla_distanza_si_valida(admin_client, db_session):
    match = _partita(db_session, 5, 1, distance=5, race_to=True, suffix="_vv")
    assert PULSANTE in _pagina(admin_client, match)


def test_partita_non_alla_distanza_non_si_valida(admin_client, db_session):
    match = _partita(db_session, 2, 1, distance=5, race_to=True, suffix="_vn")
    assert PULSANTE not in _pagina(admin_client, match)


def test_regola_condivisa_con_la_pagina_della_gara(db_session):
    """La card del direttore e la pagina della partita contano le stesse."""
    from models.competition.direttore_view import _e_da_validare

    pari = _partita(db_session, 3, 3, distance=6, race_to=False, suffix="_vr")
    assert pari.is_awaiting_validation is True
    assert _e_da_validare(pari) is True
    pari.status = MatchStatus.CONFIRMED_BY_BOTH.value
    assert pari.is_awaiting_validation is False
