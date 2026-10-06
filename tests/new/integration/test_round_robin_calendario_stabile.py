"""Il calendario del girone all'italiana si fissa all'avvio e non si sposta più.

Bug (esplorazione per i gironi multipli, 2026-10-06) —
`models/matchmaking/strategies/round_robin.py`:

La strategia rigenerava l'intero calendario a ogni turno partendo da
`gara.inscriptions`, una relazione **senza ordinamento**, e contando solo gli
iscritti attivi. Due conseguenze:

* il primo turno ignorava il sorteggio: `start_first_round` mescola gli
  iscritti e scrive `initial_order`, ma la strategia non lo leggeva;
* con la regola di ritiro EXCLUDE l'iscrizione di chi si ritira viene
  cancellata, il calendario si ricalcolava su un giocatore in meno e le coppie
  dei turni successivi cambiavano: reincontri, e coppie che non si sarebbero
  incontrate mai.

La correzione: dopo il primo turno l'ordine si ricava dalla classifica di
partenza persistita (`SeedingService`), che contiene anche chi si ritira. Chi
è escluso resta al suo posto nel calendario e il suo avversario di quel turno
riposa, come vuole la gestione del dispari (SPECIFICHE.md, «policy per il
forfait», EXCLUDE: «Se questo cambia la parità dei giocatori, si applica la
gestione dispari configurata»).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from itertools import combinations
from typing import Dict, List, Tuple

import pytest

from models import User
from models.base import db, utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara, Inscription
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.competition.withdraw_policy_service import WithdrawPolicyService
from models.matchmaking.bootstrap import get_registry
from models.status_enum import WithdrawPolicy
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration

Schedule = Dict[int, List[Tuple[int, ...]]]


def _crea_utente(role: str) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"rr_{role}_{uid}", email=f"rr_{role}_{uid}@test.com")
    user.role = role
    user.set_password("x")
    db.session.add(user)
    return user


def _gara_round_robin(n: int, withdraw_policy: str) -> Tuple[Gara, List[User]]:
    director = _crea_utente(UserRole.DIRECTOR.value)
    players = [_crea_utente(UserRole.PLAYER.value) for _ in range(n)]
    db.session.commit()

    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Girone stabile",
        date=date.today() + timedelta(days=7),
        location="Sala",
        description="",
        rounds_count=n if n % 2 else n - 1,
        min_participants=3,
        max_participants=16,
        entry_fee=0.0,
        discipline="8_ball",
        distance=3,
        is_race_to=True,
        director_id=director.id,
        matchmaking_strategy="round_robin",
        first_round_policy="random",
        odd_number_policy="bye",
        anti_rematch_enabled=False,
    )
    gara.withdraw_policy = withdraw_policy
    db.session.commit()

    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)
    return gara, players


def _turno(gara: Gara, round_number: int) -> List[Tuple[int, ...]]:
    """Gli abbinamenti che la strategia produce per il turno, senza salvarli."""
    db.session.expire_all()
    gara = db.session.get(Gara, gara.id)
    strategy = get_registry().get("round_robin")
    return [tuple(p.players) for p in strategy.create_round(gara, round_number)]


def _senza(pairings: List[Tuple[int, ...]], escluso: int) -> List[Tuple[int, ...]]:
    """Gli stessi abbinamenti con `escluso` tolto: il suo avversario riposa."""
    risultato = []
    for pairing in pairings:
        resto = tuple(p for p in pairing if p != escluso)
        if resto:
            risultato.append(resto)
    return risultato


def _coppie(schedule: Schedule) -> List[frozenset]:
    return [
        frozenset(pairing)
        for pairings in schedule.values()
        for pairing in pairings
        if len(pairing) == 2
    ]


class TestPrimoTurnoSegueIlSorteggio:
    def test_primo_turno_usa_initial_order(self, db_session):
        """Il turno 1 nasce dall'ordine del sorteggio, non da quello degli id."""
        gara, players = _gara_round_robin(6, WithdrawPolicy.FORFEIT.value)

        # Un sorteggio che rovescia l'ordine di iscrizione.
        ordine = list(reversed(players))
        for posizione, player in enumerate(ordine, 1):
            iscrizione = (
                db.session.query(Inscription)
                .filter_by(gara_id=gara.id, user_id=player.id)
                .one()
            )
            iscrizione.initial_order = posizione
        db.session.commit()

        ids = [p.id for p in ordine]
        atteso = [(ids[0], ids[5]), (ids[1], ids[4]), (ids[2], ids[3])]
        assert _turno(gara, 1) == atteso


class TestCalendarioStabileAiRitiri:
    @pytest.mark.parametrize("n", [5, 6])
    def test_esclusione_non_sposta_le_coppie(self, db_session, n):
        gara, players = _gara_round_robin(n, WithdrawPolicy.EXCLUDE.value)
        RoundService.start_first_round(gara.id)

        turni = n if n % 2 else n - 1
        previsto: Schedule = {r: _turno(gara, r) for r in range(1, turni + 1)}

        # Il calendario completo, prima di qualunque ritiro, è un girone vero.
        tutti = {p.id for p in players}
        assert sorted(map(sorted, _coppie(previsto))) == sorted(
            map(sorted, (frozenset(c) for c in combinations(tutti, 2)))
        )

        # Si ritira, fra il turno 1 e il 2, un giocatore che non ha la X al 2.
        escluso = next(
            p.id for p in players if any(p.id in c and len(c) == 2 for c in previsto[2])
        )
        WithdrawPolicyService.handle_forfeit(gara_id=gara.id, user_id=escluso)
        db.session.commit()
        assert (
            db.session.query(Inscription)
            .filter_by(gara_id=gara.id, user_id=escluso)
            .first()
            is None
        ), "con EXCLUDE l'iscrizione viene tolta"

        for r in range(2, turni + 1):
            assert _turno(gara, r) == _senza(
                previsto[r], escluso
            ), f"turno {r}: il ritiro ha spostato le coppie"

    def test_forfait_resta_nel_calendario(self, db_session):
        """Con FORFEIT chi si ritira resta negli abbinamenti, al suo posto."""
        gara, players = _gara_round_robin(6, WithdrawPolicy.FORFEIT.value)
        RoundService.start_first_round(gara.id)
        previsto: Schedule = {r: _turno(gara, r) for r in range(1, 6)}

        WithdrawPolicyService.handle_forfeit(gara_id=gara.id, user_id=players[0].id)
        db.session.commit()

        for r in range(2, 6):
            assert _turno(gara, r) == previsto[r]
