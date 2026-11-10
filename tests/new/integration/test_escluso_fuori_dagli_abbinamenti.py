"""Chi è stato escluso dalla gara non entra più negli abbinamenti Amalfi.

Difetto trovato il 2026-11-10. In una gara Amalfi con la regola dei ritiri
EXCLUDE, finito il turno 1 il direttore ritira un giocatore: la sua iscrizione
viene cancellata. Al turno 2 la strategia prendeva i giocatori dalle righe
`RoundClassification` del turno precedente, dove l'escluso c'è ancora — ed è
giusto che ci sia, perché resta in classifica — e non le incrociava con le
iscrizioni attive. Nasceva così una partita «escluso contro qualcuno», in
attesa, 0-0, che nessuno poteva giocare.

SPECIFICHE.md, «policy per il forfait», EXCLUDE: «il giocatore viene eliminato
dagli abbinamenti futuri (ma resta in classifica con i punti accumulati). Se
questo cambia la parità dei giocatori, si applica la gestione dispari
configurata».
"""

import uuid
from datetime import date, timedelta

import pytest

from models import Gara, Inscription, Match, User
from models.classification.models import RoundClassification
from models.competition.models import WithdrawPolicy
from models.competition.round_service import RoundService
from models.competition.withdraw_policy_service import WithdrawPolicyService
from models.match.models import TrioMatch
from models.matchmaking.configuration import MatchmakingStrategy, OddNumberPolicy
from models.status_enum import Discipline, GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _utente(db_session, prefisso):
    b = uuid.uuid4().hex[:8]
    utente = User(
        username=f"{prefisso}_{b}",
        email=f"{prefisso}_{b}@t.local",
        role=UserRole.PLAYER.value,
        onboarding_completed=True,
    )
    utente.set_password("pw12345")
    db_session.add(utente)
    db_session.commit()
    return utente


def _gara(db_session, n, dispari=OddNumberPolicy.BYE.value):
    gara = Gara(
        number=1,
        name="Esclusi",
        date=date.today() + timedelta(days=3),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        matchmaking_strategy=MatchmakingStrategy.AMALFI.value,
        status=GaraStatus.INSCRIPTION.value,
        current_round=0,
        rounds_count=3,
        min_participants=2,
        withdraw_policy=WithdrawPolicy.EXCLUDE.value,
        odd_number_policy=dispari,
    )
    db_session.add(gara)
    db_session.commit()
    giocatori = []
    for i in range(n):
        utente = _utente(db_session, f"p{i}")
        db_session.add(Inscription(gara_id=gara.id, user_id=utente.id))
        giocatori.append(utente.id)
    db_session.commit()
    return gara.id, giocatori


def _gioca(db_session, gara_id, turno):
    """Chiude le partite a due del turno 3-1 e ne calcola la classifica."""
    for match in Match.query.filter_by(gara_id=gara_id, round_number=turno).all():
        if MatchStatus.is_finished(match.status):
            continue
        match.player1_score, match.player2_score = 3, 1
        match.winner_id = match.player1_id
        match.status = MatchStatus.CLOSED_UNILATERALLY.value
    db_session.commit()
    RoundClassification.calculate_classification_after_round(gara_id, turno)
    db_session.commit()


def _partite(gara_id, turno):
    return Match.query.filter_by(gara_id=gara_id, round_number=turno).all()


def _coppie(gara_id, turno):
    return {
        frozenset((m.player1_id, m.player2_id))
        for m in _partite(gara_id, turno)
        if not m.is_bye and not m.is_trio
    }


def _in_campo(gara_id, turno):
    """Tutti i giocatori che compaiono in una partita del turno."""
    presenti = []
    for match in _partite(gara_id, turno):
        presenti.extend(p for p in (match.player1_id, match.player2_id) if p)
        if match.is_trio:
            trio = TrioMatch.query.filter_by(match_id=match.id).first()
            presenti.append(trio.player3_id)
    return presenti


def test_l_escluso_non_ha_partite_e_il_dispari_passa_dalla_x(db_session):
    """Sei giocatori, uno escluso dopo il turno 1: restano cinque, uno ha la X."""
    gara_id, giocatori = _gara(db_session, 6)
    RoundService.start_first_round(gara_id)
    _gioca(db_session, gara_id, 1)

    escluso = giocatori[0]
    assert WithdrawPolicyService.handle_forfeit(gara_id, escluso) == "excluded"
    db_session.commit()

    RoundService.start_next_round(gara_id, 2)
    db_session.commit()

    presenti = _in_campo(gara_id, 2)
    assert escluso not in presenti
    assert sorted(presenti) == sorted(set(giocatori) - {escluso})
    partite = _partite(gara_id, 2)
    assert sum(1 for m in partite if m.is_bye) == 1
    assert sum(1 for m in partite if not m.is_bye) == 2
    # Nessuna partita nasce già decisa o ingiocabile: le due vere sono da giocare.
    assert all(
        m.status == MatchStatus.PENDING.value and m.winner_id is None
        for m in partite
        if not m.is_bye
    )


def test_l_escluso_resta_in_classifica(db_session):
    """«Resta in classifica con i punti accumulati»: anche nei turni dopo."""
    gara_id, giocatori = _gara(db_session, 6)
    RoundService.start_first_round(gara_id)
    _gioca(db_session, gara_id, 1)
    escluso = giocatori[0]
    prima = RoundClassification.query.filter_by(
        gara_id=gara_id, round_number=1, user_id=escluso
    ).one()
    vittorie_prima = prima.matches_won

    WithdrawPolicyService.handle_forfeit(gara_id, escluso)
    db_session.commit()
    RoundService.start_next_round(gara_id, 2)
    db_session.commit()
    _gioca(db_session, gara_id, 2)

    for turno in (1, 2):
        riga = RoundClassification.query.filter_by(
            gara_id=gara_id, round_number=turno, user_id=escluso
        ).one_or_none()
        assert riga is not None, f"l'escluso è sparito dalla classifica {turno}"
        assert riga.matches_won == vittorie_prima


def test_col_trio_il_dispari_passa_dal_trio(db_session):
    """La gestione dispari configurata è il trio: cinque rimasti, un trio."""
    gara_id, giocatori = _gara(db_session, 6, dispari=OddNumberPolicy.TRIO.value)
    RoundService.start_first_round(gara_id)
    _gioca(db_session, gara_id, 1)
    escluso = giocatori[0]
    WithdrawPolicyService.handle_forfeit(gara_id, escluso)
    db_session.commit()

    RoundService.start_next_round(gara_id, 2)
    db_session.commit()

    presenti = _in_campo(gara_id, 2)
    assert sorted(presenti) == sorted(set(giocatori) - {escluso})
    partite = _partite(gara_id, 2)
    assert sum(1 for m in partite if m.is_trio) == 1
    assert sum(1 for m in partite if m.is_bye) == 0


def test_x_mai_due_volte_e_nessun_reincontro_dopo_le_esclusioni(db_session):
    """Sette giocatori: la X del turno 1, poi due esclusioni.

    Turno 2 in sei: numero pari, quindi nessun reincontro (ADR-029) e nessuna
    X. Turno 3 in cinque: la X va a chi non l'ha già avuta.
    """
    gara_id, giocatori = _gara(db_session, 7)
    RoundService.start_first_round(gara_id)
    con_la_x = [m.player1_id for m in _partite(gara_id, 1) if m.is_bye]
    assert len(con_la_x) == 1
    _gioca(db_session, gara_id, 1)

    primo_escluso = next(g for g in giocatori if g != con_la_x[0])
    WithdrawPolicyService.handle_forfeit(gara_id, primo_escluso)
    db_session.commit()
    RoundService.start_next_round(gara_id, 2)
    db_session.commit()

    assert primo_escluso not in _in_campo(gara_id, 2)
    assert not [m for m in _partite(gara_id, 2) if m.is_bye]
    assert len(_coppie(gara_id, 2)) == 3
    assert not (_coppie(gara_id, 2) & _coppie(gara_id, 1))
    _gioca(db_session, gara_id, 2)

    secondo_escluso = next(
        g for g in giocatori if g not in (con_la_x[0], primo_escluso)
    )
    WithdrawPolicyService.handle_forfeit(gara_id, secondo_escluso)
    db_session.commit()
    RoundService.start_next_round(gara_id, 3)
    db_session.commit()

    presenti = _in_campo(gara_id, 3)
    assert primo_escluso not in presenti and secondo_escluso not in presenti
    x_del_terzo = [m.player1_id for m in _partite(gara_id, 3) if m.is_bye]
    assert len(x_del_terzo) == 1
    assert x_del_terzo[0] != con_la_x[0]
