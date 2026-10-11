"""Le finali per piazzamento, dal modulo della gara singola alla classifica.

Il passaggio interfaccia↔server (ADR-081, emendamento «le finali per
piazzamento»): il modulo le offre con «Gironi: fino a 2», il foglio di avvio
conta il loro turno e dice che col girone unico non si giocano, la pagina del
direttore le annuncia («Finali pronte», «Avvia le finali»), la tessera e lo
schermo in sala nominano le partite («Finale 1°/2° posto»), e giocarle porta
alla classifica della serata. Le regole hanno i loro unit test
(`test_gironi_finali_per_piazzamento.py`, `test_finali_per_piazzamento_moduli.py`).
"""

from __future__ import annotations

import uuid
from typing import Dict

import pytest

from models import Gara, User
from models.base import db
from models.classification.models import GaraClassification
from models.competition.round_service import RoundService
from models.competition.state_service import StateService
from models.match.models import Match
from models.matchmaking.bracket import BRACKET_PLACEMENT
from tests.new.integration.test_fase_finale_dal_modulo import (  # noqa: F401
    _crea,
    _gioca,
    _iscrivi,
    _login,
    direttore,
)

pytestmark = pytest.mark.integration

PIAZZAMENTO = {"final_phase_mode": "piazzamento", "group_seeding": "elo"}


def _gioca_i_gironi(client, gara: Gara, elo: Dict[int, int]) -> Gara:
    gara = db.session.get(Gara, gara.id)
    for r in range(1, gara.rounds_count):
        if r > 1:
            RoundService.start_next_round(gara.id, r)
            db.session.commit()
        _gioca(gara.id, r, elo)
    return db.session.get(Gara, gara.id)


def _posizioni(gara: Gara) -> Dict[int, int]:
    return {
        gc.user_id: gc.position
        for gc in GaraClassification.query.filter_by(gara_id=gara.id).all()
    }


def _per_elo(elo: Dict[int, int]) -> Dict[int, int]:
    """Il posto atteso di ognuno: vince sempre il più forte."""
    return {
        pid: i + 1
        for i, pid in enumerate(sorted(elo, key=lambda p: elo[p], reverse=True))
    }


def test_il_modulo_offre_le_finali(client, direttore):  # noqa: F811
    _login(client, direttore)
    pagina = client.get("/admin/gara/create_standalone").get_data(as_text=True)
    assert 'value="piazzamento"' in pagina
    assert "Finali per piazzamento" in pagina
    assert "data-fase-se-due" in pagina


def test_con_tre_gironi_il_modulo_le_rifiuta(client, direttore):  # noqa: F811
    nome = f"Tre gironi {uuid.uuid4().hex[:6]}"
    with pytest.raises(Exception):
        _crea(client, direttore, name=nome, max_groups="3", **PIAZZAMENTO)
    assert Gara.query.filter_by(name=nome).count() == 0


def test_quattro_e_quattro_fino_alla_classifica(
    client, db_session, direttore  # noqa: F811
):
    gara = _crea(client, direttore, **PIAZZAMENTO)
    assert gara.final_phase_mode == "piazzamento"
    assert gara.third_place_match is False
    # I tavoli servono allo schermo in sala: le caselle sono i tavoli.
    gara.available_tables = '["1", "2", "3", "4"]'
    db.session.commit()

    elo = _iscrivi(db_session, gara, 8)
    pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    # Due gironi da 4: tre turni di girone e il turno delle finali.
    assert "2 gironi · 4 turni" in pagina
    assert "Poi le finali per piazzamento" in pagina
    assert "le finali non si giocano: la gara finisce col girone" in pagina
    regolamento = client.get(f"/gara/{gara.id}/regolamento").get_data(as_text=True)
    assert "Poi le finali per piazzamento" in regolamento

    client.post(
        f"/admin/gara/{gara.id}/start_first_round",
        data={"groups_count": "2"},
        follow_redirects=True,
    )
    db_session.expire_all()
    gara = db_session.get(Gara, gara.id)
    assert gara.rounds_count == 4

    gara = _gioca_i_gironi(client, gara, elo)
    pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert "Finali pronte" in pagina
    assert "Avvia le finali" in pagina

    RoundService.start_next_round(gara.id, 4)
    db.session.commit()
    finali = Match.query.filter_by(
        gara_id=gara.id, round_number=4, bracket_type=BRACKET_PLACEMENT
    ).all()
    assert len(finali) == 4
    pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    assert "Finali per piazzamento · Turno 4 di 4" in pagina

    # La tessera del finalista: «La tua partita · Finale 1°/2° posto».
    finale = next(m for m in finali if m.bracket_slot == 0)
    finalista = db.session.get(User, finale.player1_id)
    finalista.set_password("x")
    finalista.onboarding_completed = True
    db.session.commit()
    giocatore = client.application.test_client()
    giocatore.post(
        "/auth/login",
        data={"username": finalista.username, "password": "x"},
        follow_redirects=True,
    )
    dashboard = giocatore.get("/dashboard", follow_redirects=True).get_data(
        as_text=True
    )
    blocco = dashboard[dashboard.index("La tua partita") :][:400]
    assert "Finale 1°/2° posto" in blocco

    # Lo schermo in sala nomina il turno e le partite.
    gara = db.session.get(Gara, gara.id)
    gara.public_token = uuid.uuid4().hex[:10]
    db.session.commit()
    sala = (
        client.application.test_client()
        .get(f"/g/{gara.public_token}/sala")
        .get_data(as_text=True)
    )
    assert "Finali per piazzamento" in sala
    assert "Finale 3°/4° posto" in sala

    _gioca(gara.id, 4, elo)
    StateService.complete(db.session.get(Gara, gara.id))
    db.session.commit()
    assert _posizioni(gara) == _per_elo(elo)


def test_cinque_e_quattro_l_ultimo_e_nono(client, db_session, direttore):  # noqa: F811
    gara = _crea(client, direttore, **PIAZZAMENTO)
    elo = _iscrivi(db_session, gara, 9)
    pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    # Il girone da cinque gioca cinque turni (riposo compreso), poi le finali.
    assert "2 gironi · 6 turni" in pagina

    client.post(
        f"/admin/gara/{gara.id}/start_first_round",
        data={"groups_count": "2"},
        follow_redirects=True,
    )
    db_session.expire_all()
    gara = _gioca_i_gironi(client, db_session.get(Gara, gara.id), elo)
    RoundService.start_next_round(gara.id, 6)
    db.session.commit()
    assert (
        Match.query.filter_by(
            gara_id=gara.id, round_number=6, bracket_type=BRACKET_PLACEMENT
        ).count()
        == 4
    )
    _gioca(gara.id, 6, elo)
    StateService.complete(db.session.get(Gara, gara.id))
    db.session.commit()
    posizioni = _posizioni(gara)
    assert posizioni == _per_elo(elo)
    assert posizioni[min(elo, key=lambda p: elo[p])] == 9


def test_un_girone_solo_finisce_col_girone(client, db_session, direttore):  # noqa: F811
    gara = _crea(client, direttore, **PIAZZAMENTO)
    elo = _iscrivi(db_session, gara, 5)
    pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)
    # Con 5 iscritti non stanno due gironi da 3: si gioca un girone solo.
    assert "le finali non si giocano: la gara finisce col girone" in pagina

    client.post(
        f"/admin/gara/{gara.id}/start_first_round",
        data={"groups_count": "1"},
        follow_redirects=True,
    )
    db_session.expire_all()
    gara = db_session.get(Gara, gara.id)
    assert gara.rounds_count == 5
    for r in range(1, 6):
        if r > 1:
            RoundService.start_next_round(gara.id, r)
            db.session.commit()
            assert "Avvia le finali" not in client.get(
                f"/admin/gara/{gara.id}"
            ).get_data(as_text=True)
        _gioca(gara.id, r, elo)
    StateService.complete(db.session.get(Gara, gara.id))
    db.session.commit()
    assert not Match.query.filter_by(
        gara_id=gara.id, bracket_type=BRACKET_PLACEMENT
    ).count()
    assert _posizioni(gara)[max(elo, key=lambda p: elo[p])] == 1
