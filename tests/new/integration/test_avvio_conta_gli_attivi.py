"""L'avvio della gara conta gli iscritti attivi, non i ritirati.

Rilievo della revisione automatica sulla PR #347: il foglio «Avvia la gara»
dice «tutti gli attivi entrano in gara», ma `RoundService.start_first_round`
filtrava solo la lista d'attesa. Un ritirato soddisfaceva il minimo e
finiva nell'ordine di partenza.
"""

from __future__ import annotations

from datetime import date

import pytest

from models import Gara, Inscription, Match
from models.competition.round_service import RoundService
from models.status_enum import Discipline, GaraStatus

pytestmark = pytest.mark.integration


def _gara(db_session, minimo):
    gara = Gara(
        number=1,
        name="Gara con ritirati",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        matchmaking_strategy="amalfi",
        status=GaraStatus.INSCRIPTION.value,
        current_round=0,
        rounds_count=2,
        min_participants=minimo,
    )
    db_session.add(gara)
    db_session.commit()
    return gara


def _iscrivi(db_session, gara, quanti, ritirati=0):
    from models.user.services import UserService

    utenti = []
    for i in range(quanti):
        u = UserService.create_user(f"rit_{i}", f"rit_{i}@test.local", "pw12345")
        db_session.add(
            Inscription(
                user_id=u.id,
                gara_id=gara.id,
                is_waitlist=False,
                is_withdrawn=i < ritirati,
            )
        )
        utenti.append(u)
    db_session.commit()
    return utenti


def test_un_ritirato_non_conta_per_il_minimo(db_session):
    gara = _gara(db_session, minimo=4)
    _iscrivi(db_session, gara, 4, ritirati=1)
    with pytest.raises(ValueError, match="Servono almeno"):
        RoundService.start_first_round(gara.id)


def test_un_ritirato_non_entra_nel_sorteggio(db_session):
    gara = _gara(db_session, minimo=4)
    utenti = _iscrivi(db_session, gara, 5, ritirati=1)
    RoundService.start_first_round(gara.id)
    ritirato = utenti[0]
    partite = Match.query.filter_by(gara_id=gara.id).all()
    assert partite
    assert all(
        ritirato.id not in (m.player1_id, m.player2_id) for m in partite
    ), "il ritirato non deve avere partite"
