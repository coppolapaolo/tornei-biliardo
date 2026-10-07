"""Il girone all'italiana a più gironi: avvio, turni paralleli, ritiri (ADR-076).

Gare singole, perché ogni opzione vale prima di tutto sulla gara: il
campionato la propone soltanto.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from itertools import combinations
from typing import Dict, List, Optional, Tuple

import pytest

from models import User
from models.base import db, utc_now
from models.competition.gironi_service import GironiService
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara, Inscription
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.competition.withdraw_policy_service import WithdrawPolicyService
from models.exceptions import ValidationError
from models.match.models import Match
from models.matchmaking.bootstrap import get_registry
from models.status_enum import WithdrawPolicy
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _utente(role: str, elo: Optional[int] = None) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"gi_{role}_{uid}", email=f"gi_{role}_{uid}@test.com")
    user.role = role
    user.set_password("x")
    user.elo_rating = elo
    db.session.add(user)
    return user


def _gara(
    n: int,
    max_groups: Optional[int] = 2,
    withdraw_policy: str = WithdrawPolicy.FORFEIT.value,
    group_seeding: Optional[str] = None,
) -> Tuple[Gara, List[User]]:
    director = _utente(UserRole.DIRECTOR.value)
    players = [_utente(UserRole.PLAYER.value, elo=2000 - i) for i in range(n)]
    db.session.commit()
    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name="Serata a gironi",
        date=date.today() + timedelta(days=7),
        location="Sala",
        description="",
        rounds_count=3,
        min_participants=3,
        max_participants=32,
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
    gara.max_groups = max_groups
    gara.group_seeding = group_seeding
    db.session.commit()
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)
    return gara, players


def _turno(gara: Gara, r: int) -> List[Tuple[Tuple[int, ...], Optional[int]]]:
    db.session.expire_all()
    gara = db.session.get(Gara, gara.id)
    strategy = get_registry().get("round_robin")
    return [(tuple(p.players), p.bracket_group) for p in strategy.create_round(gara, r)]


def _gironi(gara: Gara) -> Dict[int, set]:
    per: Dict[int, set] = {}
    for i in db.session.query(Inscription).filter_by(gara_id=gara.id).all():
        per.setdefault(i.group_index, set()).add(i.user_id)
    return per


class TestAvvio:
    def test_undici_iscritti_due_gironi_da_sei_e_cinque(self, db_session):
        gara, _players = _gara(11)
        RoundService.start_first_round(gara.id)
        gara = db.session.get(Gara, gara.id)
        gironi = _gironi(gara)
        assert sorted(len(v) for v in gironi.values()) == [5, 6]
        assert set(gironi) == {0, 1}
        assert gara.rounds_count == 5

        partite = db.session.query(Match).filter_by(gara_id=gara.id).all()
        assert {m.bracket_group for m in partite} == {0, 1}
        for m in partite:
            for pid in (m.player1_id, m.player2_id):
                if pid is not None:
                    assert pid in gironi[m.bracket_group]
        # Il girone da cinque ha la sua X, quello da sei no.
        x = [m for m in partite if m.is_bye]
        assert len(x) == 1 and len(gironi[x[0].bracket_group]) == 5

    def test_il_direttore_sceglie_il_numero(self, db_session):
        gara, _ = _gara(11, max_groups=3)
        RoundService.start_first_round(gara.id, groups_count=3)
        assert sorted(len(v) for v in _gironi(gara).values()) == [3, 4, 4]
        assert db.session.get(Gara, gara.id).rounds_count == 3

    def test_un_girone_e_il_round_robin_di_sempre(self, db_session):
        gara, _ = _gara(5)
        RoundService.start_first_round(gara.id, groups_count=1)
        assert set(_gironi(gara)) == {None}
        partite = db.session.query(Match).filter_by(gara_id=gara.id).all()
        assert {m.bracket_group for m in partite} == {None}
        assert db.session.get(Gara, gara.id).rounds_count == 5

    def test_senza_tetto_si_fissano_i_turni_sugli_iscritti(self, db_session):
        """Il girone unico ora fissa i turni all'avvio (nota della PR 0)."""
        gara, _ = _gara(6, max_groups=None)
        RoundService.start_first_round(gara.id)
        assert db.session.get(Gara, gara.id).rounds_count == 5

    def test_almeno_tre_per_girone(self, db_session):
        gara, _ = _gara(8, max_groups=3)
        with pytest.raises(ValidationError):
            RoundService.start_first_round(gara.id, groups_count=3)
        db.session.rollback()
        assert db.session.get(Gara, gara.id).current_round == 0

    def test_non_oltre_il_tetto(self, db_session):
        gara, _ = _gara(12, max_groups=2)
        with pytest.raises(ValidationError):
            RoundService.start_first_round(gara.id, groups_count=3)

    def test_per_elo_i_due_migliori_in_gironi_diversi(self, db_session):
        gara, players = _gara(8, group_seeding="elo")
        RoundService.start_first_round(gara.id, groups_count=2)
        girone = GironiService.girone_dei_giocatori(db.session.get(Gara, gara.id))
        assert girone[players[0].id] != girone[players[1].id]
        assert girone[players[0].id] == girone[players[3].id]

    def test_annullare_l_avvio_toglie_i_gironi(self, db_session):
        gara, _ = _gara(8)
        RoundService.start_first_round(gara.id, groups_count=2)
        RoundService.cancel_first_round_startup(gara.id)
        assert set(_gironi(gara)) == {None}


class TestTurniParalleli:
    @pytest.mark.parametrize("n", [8, 10, 11])
    def test_ognuno_incontra_tutto_il_suo_girone_una_volta(self, db_session, n):
        gara, _ = _gara(n)
        RoundService.start_first_round(gara.id, groups_count=2)
        gara = db.session.get(Gara, gara.id)
        gironi = _gironi(gara)
        coppie = []
        for r in range(1, gara.rounds_count + 1):
            visti = set()
            for players, gruppo in _turno(gara, r):
                assert set(players) <= gironi[gruppo]
                assert not (visti & set(players)), "due partite nello stesso turno"
                visti |= set(players)
                if len(players) == 2:
                    coppie.append(frozenset(players))
        attese = {frozenset(c) for g in gironi.values() for c in combinations(g, 2)}
        assert sorted(map(sorted, coppie)) == sorted(map(sorted, attese))

    def test_quattro_e_tre_giocatori_tre_turni(self, db_session):
        gara, _ = _gara(7)
        RoundService.start_first_round(gara.id, groups_count=2)
        assert db.session.get(Gara, gara.id).rounds_count == 3

    def test_il_girone_piu_piccolo_finisce_prima_e_si_ferma(self, db_session):
        gara, _ = _gara(13)
        RoundService.start_first_round(gara.id, groups_count=2)
        gara = db.session.get(Gara, gara.id)
        gironi = _gironi(gara)
        assert sorted(len(v) for v in gironi.values()) == [6, 7]
        assert gara.rounds_count == 7
        strategy = get_registry().get("round_robin")
        assert strategy.has_round(gara, 7)
        assert not strategy.has_round(gara, 8)
        sei = next(g for g, v in gironi.items() if len(v) == 6)
        for r in (6, 7):
            assert {gruppo for _p, gruppo in _turno(gara, r)} == {1 - sei}

    def test_il_calendario_e_stabile(self, db_session):
        gara, _ = _gara(11)
        RoundService.start_first_round(gara.id)
        primo = {r: _turno(gara, r) for r in range(1, 6)}
        assert {r: _turno(gara, r) for r in range(1, 6)} == primo


class TestRitiri:
    def test_un_ritiro_non_cambia_i_gironi_ne_le_coppie(self, db_session):
        gara, players = _gara(11, withdraw_policy=WithdrawPolicy.EXCLUDE.value)
        RoundService.start_first_round(gara.id)
        previsto = {r: _turno(gara, r) for r in range(1, 6)}
        gironi_prima = GironiService.girone_dei_giocatori(db.session.get(Gara, gara.id))

        escluso = next(
            pid
            for players_, _g in previsto[2]
            if len(players_) == 2
            for pid in players_
        )
        WithdrawPolicyService.handle_forfeit(gara_id=gara.id, user_id=escluso)
        db.session.commit()

        gara = db.session.get(Gara, gara.id)
        assert GironiService.girone_dei_giocatori(gara) == gironi_prima
        for r in range(2, 6):
            atteso = []
            for players_, gruppo in previsto[r]:
                resto = tuple(p for p in players_ if p != escluso)
                if resto:
                    atteso.append((resto, gruppo))
            assert _turno(gara, r) == atteso, f"turno {r}"
