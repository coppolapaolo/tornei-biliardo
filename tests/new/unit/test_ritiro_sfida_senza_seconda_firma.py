"""La regola del ritiro, sul modello (2026-10-17).

Una sfida in corso firmata da chi chiede, e non ancora dall'avversario, si
ritira: finisce annullata. L'avversario non può — ha già «rifiuta» — e dopo la
doppia firma, o senza firme, non si ritira. ``SPECIFICHE.md``, nota del
2026-10-17; il percorso dalle route sta in
``tests/new/integration/test_ritiro_sfida_senza_seconda_firma.py``.
"""

import pytest

from models.certificazione import livello_di_sfida
from models.exceptions import ConflictError, PermissionDeniedError
from models.individual_match.match_models import IndividualMatch
from models.status_enum import MatchStatus


def _sfida(p1=False, p2=False, status=MatchStatus.IN_PROGRESS):
    return IndividualMatch(
        player1_id=1,
        player2_id=2,
        status=status,
        player1_confirmed=p1,
        player2_confirmed=p2,
        player1_score=3,
        player2_score=1,
        distance=3,
        is_race_to=True,
    )


def test_chi_ha_firmato_la_ritira_e_la_sfida_perde_il_livello(app):
    sfida = _sfida(p1=True)

    sfida.withdraw_by_signer(1)

    assert sfida.status == MatchStatus.CANCELLED
    assert livello_di_sfida(sfida) is None
    assert not sfida.signed_and_waiting(1)


def test_l_avversario_non_la_ritira(app):
    sfida = _sfida(p1=True)

    with pytest.raises(PermissionDeniedError):
        sfida.withdraw_by_signer(2)
    assert sfida.status == MatchStatus.IN_PROGRESS


def test_chi_non_gioca_non_la_ritira(app):
    with pytest.raises(PermissionDeniedError):
        _sfida(p1=True).withdraw_by_signer(3)


@pytest.mark.parametrize(
    "p1,p2,status",
    [
        (False, False, MatchStatus.IN_PROGRESS),
        (True, True, MatchStatus.CONFIRMED_BY_BOTH),
        (True, False, MatchStatus.CANCELLED),
    ],
    ids=["senza-firme", "doppia-firma", "gia-annullata"],
)
def test_fuori_dall_attesa_non_si_ritira(app, p1, p2, status):
    sfida = _sfida(p1=p1, p2=p2, status=status)

    with pytest.raises(ConflictError):
        sfida.withdraw_by_signer(1)
    assert sfida.status == status
