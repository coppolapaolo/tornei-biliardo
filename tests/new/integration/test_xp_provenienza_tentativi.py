"""L'XP restituito si riconosce dalla provenienza del tentativo.

I tentativi dell'allenamento (`challenge_attempt`) e quelli degli esercizi di
gara (`gara_challenge_attempt`) stanno in due tabelle, e i loro id si
sovrappongono: il primo tentativo di ognuna ha id 1. I movimenti XP li
ricordano entrambi come `challenge_attempt_id`, quindi chi cerca «il movimento
di questo tentativo» con il solo id trova anche quello dell'altra tabella.

Il guasto che questo file presidia, provato sul codice del 2026-09-13 prima
della correzione: un giocatore si allena (tentativo 1, XP pagato), gioca un
esercizio in gara (tentativo di gara 1, XP pagato), il direttore glielo toglie
(movimento compensativo). Poi il giocatore annulla il suo allenamento:
`ChallengeService._refund_xp_for_attempt` trovava per primo il movimento
compensativo della gara, lo leggeva come «gia' restituito» e non restituiva
niente. L'XP dell'allenamento annullato restava al giocatore.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.challenge.services import ChallengeService
from models.competition.gara_challenge import GaraChallenge
from models.competition.gara_challenge_service import GaraChallengeService
from models.competition.models import Gara, Inscription
from models.gamification.models import XPTransaction, XPTransactionType
from models.match.models import Match
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.models import User
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _utente(db_session, prefisso, ruolo=UserRole.PLAYER.value):
    s = uuid.uuid4().hex[:8]
    u = User(
        username=f"{prefisso}_{s}",
        email=f"{prefisso}_{s}@test.com",
        role=ruolo,
        onboarding_completed=True,
    )
    u.set_password("test1234")
    db_session.add(u)
    db_session.commit()
    return u


def _xp(user_id):
    return sum(
        m.xp_amount
        for m in XPTransaction.query.filter_by(
            user_id=user_id, transaction_type=XPTransactionType.CHALLENGE_COMPLETION
        )
    )


def _esercizio_di_gara(db_session, direttore, giocatore, avversario):
    gara = Gara(
        number=1,
        name=f"Gara provenienza {uuid.uuid4().hex[:6]}",
        date=date.today(),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        is_race_to=True,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
        current_round=1,
        rounds_count=3,
        min_participants=2,
        director_id=direttore.id,
    )
    db_session.add(gara)
    db_session.commit()
    for u in (giocatore, avversario):
        db_session.add(Inscription(user_id=u.id, gara_id=gara.id, is_waitlist=False))
    db_session.add(
        Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=giocatore.id,
            player2_id=avversario.id,
            player1_score=5,
            player2_score=2,
            winner_id=giocatore.id,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
        )
    )
    sfida = Challenge(
        description="Esercizio di gara",
        image_path="/x.png",
        is_active=True,
        created_by_id=direttore.id,
    )
    db_session.add(sfida)
    db_session.commit()
    gc = GaraChallenge(
        gara_id=gara.id,
        challenge_id=sfida.id,
        round_number=1,
        max_attempts=1,
        added_by_id=direttore.id,
    )
    db_session.add(gc)
    db_session.commit()
    return gc


def test_annullare_l_allenamento_dopo_un_tentativo_di_gara_tolto(db_session):
    direttore = _utente(db_session, "dir", UserRole.DIRECTOR.value)
    giocatore = _utente(db_session, "gio")
    avversario = _utente(db_session, "avv")

    allenamento = Challenge(
        description="Allenamento",
        image_path="/a.png",
        is_active=True,
        pass_fail_only=True,
        created_by_id=direttore.id,
    )
    db_session.add(allenamento)
    db_session.commit()
    prova = ChallengeService.record_attempt(
        user_id=giocatore.id, challenge_id=allenamento.id, passed=True
    )
    db_session.commit()
    assert _xp(giocatore.id) > 0, "l'allenamento deve pagare XP"
    tariffa = _xp(giocatore.id)

    gc = _esercizio_di_gara(db_session, direttore, giocatore, avversario)
    di_gara = GaraChallengeService.record_challenge_attempt(
        gc.id, giocatore.id, score=3
    )
    db_session.commit()
    # Il presupposto del guasto: due tentativi, due tabelle, lo stesso id.
    assert di_gara.id == prova.id

    GaraChallengeService.remove_challenge_attempt(di_gara.id)
    db_session.commit()
    assert _xp(giocatore.id) == tariffa

    ChallengeService.delete_attempt(attempt_id=prova.id, actor_id=giocatore.id)
    db_session.commit()
    db.session.expire_all()

    assert _xp(giocatore.id) == 0


def test_togliere_il_tentativo_di_gara_non_tocca_l_allenamento(db_session):
    """Il verso opposto: l'allenamento annullato prima, poi il tentativo di
    gara tolto. Ognuno restituisce il suo, e alla fine il saldo e' zero."""
    direttore = _utente(db_session, "dir", UserRole.DIRECTOR.value)
    giocatore = _utente(db_session, "gio")
    avversario = _utente(db_session, "avv")

    allenamento = Challenge(
        description="Allenamento",
        image_path="/a.png",
        is_active=True,
        pass_fail_only=True,
        created_by_id=direttore.id,
    )
    db_session.add(allenamento)
    db_session.commit()
    prova = ChallengeService.record_attempt(
        user_id=giocatore.id, challenge_id=allenamento.id, passed=True
    )
    gc = _esercizio_di_gara(db_session, direttore, giocatore, avversario)
    di_gara = GaraChallengeService.record_challenge_attempt(
        gc.id, giocatore.id, score=3
    )
    db_session.commit()
    assert di_gara.id == prova.id
    tariffa = _xp(giocatore.id) // 2

    ChallengeService.delete_attempt(attempt_id=prova.id, actor_id=giocatore.id)
    db_session.commit()
    assert _xp(giocatore.id) == tariffa

    GaraChallengeService.remove_challenge_attempt(di_gara.id)
    db_session.commit()
    assert _xp(giocatore.id) == 0
