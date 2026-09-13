"""A che punto sono i playoff di un campionato (`models/playoff/fase.py`).

Rilievo del 2026-09-13: a playoff finiti la pagina del campionato mostrava
ancora «Inviti chiusi» con «Vai alla gara playoff», e gli invitati restavano
in pagina anche a finale cominciata. La fase si calcola dai fatti — inviti
partiti, gara di playoff avviata, gara conclusa — e quando è «conclusi»
coincide con lo stato Completato del campionato (SPECIFICHE.md, «Stati di un
campionato»): la pagina constata, non chiede un'altra chiusura.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from models.base import utc_now
from models.campionato.statistics_service import compute_campionato_status
from models.playoff.fase import FasePlayoff, fase_playoff
from models.status_enum import GaraStatus, TournamentStatus

pytestmark = pytest.mark.unit


def _gara(status: str, turno: int = 0, eliminata: bool = False):
    return SimpleNamespace(status=status, current_round=turno, is_deleted=eliminata)


def _config(gara=None, invitati: bool = True, attiva: bool = True):
    inviti = [SimpleNamespace(invited_at=utc_now() if invitati else None)]
    return SimpleNamespace(is_active=attiva, gara=gara, qualifications=inviti)


def _campionato(*configs, terminato: bool = True):
    return SimpleNamespace(
        terminated_at=utc_now() if terminato else None,
        playoff_configurations=list(configs),
        has_playoff_configurations=lambda: bool(configs),
        gare=[],
    )


def test_un_campionato_non_terminato_non_e_in_fase_playoff():
    assert fase_playoff(_campionato(_config(), terminato=False)) is None


def test_senza_playoff_non_c_e_fase():
    assert fase_playoff(_campionato()) is None


def test_prima_degli_inviti_i_playoff_sono_da_avviare():
    assert fase_playoff(_campionato(_config(invitati=False))) == FasePlayoff.DA_AVVIARE


def test_con_gli_inviti_partiti_e_senza_gara_si_e_agli_inviti():
    assert fase_playoff(_campionato(_config())) == FasePlayoff.INVITI


@pytest.mark.parametrize(
    "status", [GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value]
)
def test_con_la_gara_creata_ma_non_avviata_si_e_ancora_agli_inviti(status):
    assert fase_playoff(_campionato(_config(_gara(status)))) == FasePlayoff.INVITI


@pytest.mark.parametrize(
    "status", [GaraStatus.PLAYING.value, GaraStatus.AWAITING_SSR.value]
)
def test_con_la_gara_avviata_i_playoff_sono_in_corso(status):
    campionato = _campionato(_config(_gara(status, turno=1)))
    assert fase_playoff(campionato) == FasePlayoff.IN_CORSO


def test_con_la_gara_conclusa_i_playoff_sono_conclusi():
    campionato = _campionato(_config(_gara(GaraStatus.COMPLETED.value, turno=1)))
    assert fase_playoff(campionato) == FasePlayoff.CONCLUSI


def test_con_due_playoff_basta_uno_ancora_da_giocare_per_non_essere_conclusi():
    campionato = _campionato(
        _config(_gara(GaraStatus.COMPLETED.value, turno=1)),
        _config(_gara(GaraStatus.PLAYING.value, turno=1)),
    )
    assert fase_playoff(campionato) == FasePlayoff.IN_CORSO


def test_una_gara_eliminata_non_conta_come_avviata():
    campionato = _campionato(
        _config(_gara(GaraStatus.PLAYING.value, turno=1, eliminata=True))
    )
    assert fase_playoff(campionato) == FasePlayoff.INVITI


@pytest.mark.parametrize(
    "configs, conclusi",
    [
        ((_config(_gara(GaraStatus.COMPLETED.value, turno=1)),), True),
        ((_config(_gara(GaraStatus.PLAYING.value, turno=1)),), False),
        ((_config(),), False),
        (
            (
                _config(_gara(GaraStatus.COMPLETED.value, turno=1)),
                _config(_gara(GaraStatus.COMPLETED.value, turno=1), attiva=False),
            ),
            True,
        ),
    ],
)
def test_conclusi_coincide_con_il_campionato_completato(configs, conclusi):
    """La pagina non deve dire «concluso» a un campionato che non lo è, né il
    contrario: le due risposte nascono dagli stessi fatti."""
    campionato = _campionato(*configs)
    completato = (
        compute_campionato_status(campionato) == TournamentStatus.COMPLETED.value
    )
    assert (fase_playoff(campionato) == FasePlayoff.CONCLUSI) is conclusi
    assert completato is conclusi
