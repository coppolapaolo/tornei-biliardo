"""I gironi con le finali per piazzamento, sul database (piano gironi, PR 6).

Gare singole, dal servizio: avvio, turni dei gironi, il turno delle finali,
la classifica della serata. Il p-esimo del girone A contro il p-esimo del
girone B; con 5 + 4 l'ultimo del girone da cinque si classifica direttamente
(SPECIFICHE.md, «Fase finale dopo i gironi»).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import pytest

from models import User
from models.base import db, utc_now
from models.classification.models import GaraClassification, RoundClassification
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara, Inscription
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.competition.spareggio_service import SpareggioService
from models.competition.state_service import StateService
from models.match.models import Match
from models.match.services import RackService
from models.matchmaking.bracket import BRACKET_PLACEMENT
from models.status_enum import MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _utente(role: str, elo: Optional[int] = None) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"fp_{role}_{uid}", email=f"fp_{role}_{uid}@test.com")
    user.role = role
    user.set_password("x")
    user.elo_rating = elo
    db.session.add(user)
    return user


def _gara(n: int, *, max_groups: int = 2, **extra) -> Tuple[Gara, List[User]]:
    director = _utente(UserRole.DIRECTOR.value)
    players = [_utente(UserRole.PLAYER.value, elo=2000 - 10 * i) for i in range(n)]
    db.session.commit()
    valori = dict(
        campionato_id=None,
        number=1,
        name="Gironi e finali per piazzamento",
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
        max_groups=max_groups,
        group_seeding="elo",
        final_phase_mode="piazzamento",
    )
    valori.update(extra)
    gara = GaraService.create_gara(**valori)
    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)
    return gara, players


def _vince_il_piu_forte(elo: Dict[int, int]) -> Callable[[Match], int]:
    return lambda m: max((m.player1_id, m.player2_id), key=lambda p: elo[p])


def _gioca(gara_id: int, r: int, chi_vince: Callable[[Match], int]) -> None:
    for match in Match.query.filter_by(gara_id=gara_id, round_number=r).all():
        if match.is_bye or MatchStatus.is_finished(match.status):
            continue
        vince = chi_vince(match)
        for _ in range(match.match_distance):
            RackService.add_rack_with_score_update(
                match_id=match.id,
                winner_id=vince,
                reported_by_id=vince,
                validated_by_admin=True,
            )
    db.session.commit()
    RoundService.update_round_progression(gara_id)
    db.session.commit()


def _gioca_i_gironi(gara: Gara, chi_vince: Callable[[Match], int]) -> Gara:
    RoundService.start_first_round(gara.id, groups_count=2)
    gara = db.session.get(Gara, gara.id)
    for r in range(1, gara.rounds_count):
        if r > 1:
            RoundService.start_next_round(gara.id, r)
        _gioca(gara.id, r, chi_vince)
    return db.session.get(Gara, gara.id)


def _gironi(gara: Gara) -> Dict[int, List[int]]:
    per: Dict[int, List[int]] = {}
    for i in Inscription.query.filter_by(gara_id=gara.id).all():
        per.setdefault(i.group_index, []).append(i.user_id)
    return per


def _posizioni(gara: Gara) -> Dict[int, Tuple[int, Optional[int]]]:
    return {
        gc.user_id: (gc.position, gc.shown_position)
        for gc in GaraClassification.query.filter_by(gara_id=gara.id).all()
    }


class TestAvvio:
    def test_due_gironi_da_quattro_piu_un_turno(self, db_session):
        gara, _ = _gara(8)
        RoundService.start_first_round(gara.id, groups_count=2)
        assert db.session.get(Gara, gara.id).rounds_count == 3 + 1

    def test_cinque_e_quattro(self, db_session):
        gara, _ = _gara(9)
        RoundService.start_first_round(gara.id, groups_count=2)
        assert db.session.get(Gara, gara.id).rounds_count == 5 + 1

    def test_col_girone_unico_la_gara_finisce_col_girone(self, db_session):
        gara, p = _gara(5)
        elo = {u.id: u.elo_rating for u in p}
        RoundService.start_first_round(gara.id, groups_count=1)
        gara = db.session.get(Gara, gara.id)
        assert gara.rounds_count == 5
        for r in range(1, 6):
            if r > 1:
                RoundService.start_next_round(gara.id, r)
            _gioca(gara.id, r, _vince_il_piu_forte(elo))
        assert not Match.query.filter(
            Match.gara_id == gara.id, Match.bracket_type.isnot(None)
        ).count()


class TestNonSiPuo:
    def test_con_tre_gironi_e_rifiutata(self, db_session):
        with pytest.raises(ValueError):
            _gara(9, max_groups=3)

    def test_col_girone_unico_e_rifiutata(self, db_session):
        with pytest.raises(ValueError):
            _gara(6, max_groups=1)

    def test_esattamente_n_e_rifiutata(self, db_session):
        with pytest.raises(ValueError):
            _gara(8, is_race_to=False)

    def test_il_tetto_portato_a_tre_dopo_e_rifiutato(self, db_session):
        gara, _ = _gara(8)
        with pytest.raises(ValueError):
            GaraService.update_gara(gara.id, max_groups=3)


class TestLeFinali:
    def test_il_p_esimo_di_a_contro_il_p_esimo_di_b(self, db_session):
        gara, p = _gara(8)
        elo = {u.id: u.elo_rating for u in p}
        gara = _gioca_i_gironi(gara, _vince_il_piu_forte(elo))
        RoundService.start_next_round(gara.id, 4)
        gironi = _gironi(gara)
        per_posto = {g: sorted(ids, key=lambda i: -elo[i]) for g, ids in gironi.items()}
        finali = Match.query.filter_by(gara_id=gara.id, round_number=4).all()
        assert len(finali) == 4
        assert {m.bracket_type for m in finali} == {BRACKET_PLACEMENT}
        assert all(m.bracket_group is None for m in finali)
        coppia = {
            m.bracket_slot: frozenset((m.player1_id, m.player2_id)) for m in finali
        }
        assert coppia == {
            s: frozenset((per_posto[0][s], per_posto[1][s])) for s in range(4)
        }

    def test_classifica_della_serata_quattro_e_quattro(self, db_session):
        gara, p = _gara(8)
        elo = {u.id: u.elo_rating for u in p}
        gara = _gioca_i_gironi(gara, _vince_il_piu_forte(elo))
        RoundService.start_next_round(gara.id, 4)
        _gioca(gara.id, 4, _vince_il_piu_forte(elo))
        gara = db.session.get(Gara, gara.id)
        StateService.complete(gara)
        db.session.commit()
        pos = _posizioni(gara)
        ordine = sorted(p, key=lambda u: -elo[u.id])
        # Vince il più forte: gli ELO sono distribuiti nei gironi andata e
        # ritorno, quindi ogni finale la vince il più forte dei due.
        assert [pos[u.id] for u in ordine] == [(i, i) for i in range(1, 9)]
        assert not SpareggioService.detect_tiebreakers(gara.id)

    def test_cinque_e_quattro_l_ultimo_diretto_al_nono(self, db_session):
        gara, p = _gara(9)
        elo = {u.id: u.elo_rating for u in p}
        gara = _gioca_i_gironi(gara, _vince_il_piu_forte(elo))
        RoundService.start_next_round(gara.id, gara.rounds_count)
        finali = Match.query.filter_by(
            gara_id=gara.id, round_number=gara.rounds_count
        ).all()
        assert len(finali) == 4
        _gioca(gara.id, gara.rounds_count, _vince_il_piu_forte(elo))
        gara = db.session.get(Gara, gara.id)
        StateService.complete(gara)
        db.session.commit()
        pos = _posizioni(gara)
        in_finale = {pid for m in finali for pid in (m.player1_id, m.player2_id)}
        diretto = next(u for u in p if u.id not in in_finale)
        assert pos[diretto.id] == (9, 9)
        assert sorted(v[0] for v in pos.values()) == list(range(1, 10))

    def test_vince_il_peggiore_e_sale(self, db_session):
        """La finale conta più dei gironi: chi la vince prende il posto."""
        gara, p = _gara(8)
        elo = {u.id: u.elo_rating for u in p}
        gara = _gioca_i_gironi(gara, _vince_il_piu_forte(elo))
        RoundService.start_next_round(gara.id, 4)
        _gioca(
            gara.id,
            4,
            lambda m: min((m.player1_id, m.player2_id), key=lambda x: elo[x]),
        )
        gara = db.session.get(Gara, gara.id)
        StateService.complete(gara)
        db.session.commit()
        pos = _posizioni(gara)
        ordine = sorted(p, key=lambda u: -elo[u.id])
        assert pos[ordine[1].id][0] == 1 and pos[ordine[0].id][0] == 2

    def test_classifica_del_turno_mentre_si_giocano(self, db_session):
        gara, p = _gara(8)
        elo = {u.id: u.elo_rating for u in p}
        gara = _gioca_i_gironi(gara, _vince_il_piu_forte(elo))
        RoundService.start_next_round(gara.id, 4)
        _gioca(gara.id, 4, _vince_il_piu_forte(elo))
        righe = {
            rc.user_id: rc
            for rc in RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=4
            ).all()
        }
        ordine = sorted(p, key=lambda u: -elo[u.id])
        assert [righe[u.id].position for u in ordine] == list(range(1, 9))
        # I numeri restano quelli dei gironi: tre partite, non quattro.
        assert righe[ordine[0].id].matches_won == 3
        assert righe[ordine[0].id].group_position == 1


class TestRegole:
    def test_la_finale_e_quella_del_primo_posto(self, db_session):
        gara, p = _gara(
            8,
            time_limit_minutes=30,
            final_phase_time_limit_minutes=45,
            final_phase_distance=4,
            final_time_limit_minutes=0,
            final_distance=7,
        )
        elo = {u.id: u.elo_rating for u in p}
        gara = _gioca_i_gironi(gara, _vince_il_piu_forte(elo))
        RoundService.start_next_round(gara.id, 4)
        finali = {
            m.bracket_slot: m
            for m in Match.query.filter_by(gara_id=gara.id, round_number=4).all()
        }
        assert (finali[0].effective_distance, finali[0].time_limit_minutes) == (
            7,
            None,
        )
        assert {
            (m.effective_distance, m.time_limit_minutes) for s, m in finali.items() if s
        } == {(4, 45)}

    def test_niente_pareggio(self, db_session):
        from models.match.chiusura import pareggio_ammesso

        gara, p = _gara(8)
        elo = {u.id: u.elo_rating for u in p}
        gara = _gioca_i_gironi(gara, _vince_il_piu_forte(elo))
        RoundService.start_next_round(gara.id, 4)
        finale = Match.query.filter_by(gara_id=gara.id, round_number=4).first()
        dei_gironi = Match.query.filter_by(gara_id=gara.id, round_number=1).first()
        assert not pareggio_ammesso(finale)
        assert pareggio_ammesso(dei_gironi)

    def test_i_nomi_delle_finali(self, db_session):
        from models.competition.tabellone_della_gara import (
            nomi_delle_partite,
            tabellone_della_gara,
        )

        gara, p = _gara(8)
        elo = {u.id: u.elo_rating for u in p}
        gara = _gioca_i_gironi(gara, _vince_il_piu_forte(elo))
        assert nomi_delle_partite(gara, gara.matches) == {}
        RoundService.start_next_round(gara.id, 4)
        gara = db.session.get(Gara, gara.id)
        nomi = nomi_delle_partite(gara, gara.matches)
        finali = [m for m in gara.matches if m.round_number == 4]
        assert {
            m.bracket_slot: (nomi[m.id].chiave, nomi[m.id].numero) for m in finali
        } == {s: ("piazzamento", s + 1) for s in range(4)}
        # Non è un tabellone: le pagine non disegnano un albero.
        assert not tabellone_della_gara(gara, gara.matches).da_mostrare


class TestRitiri:
    def test_chi_si_ritira_perde_a_tavolino(self, db_session):
        gara, p = _gara(8)
        elo = {u.id: u.elo_rating for u in p}
        gara = _gioca_i_gironi(gara, _vince_il_piu_forte(elo))
        ordine = sorted(p, key=lambda u: -elo[u.id])
        ritirato = ordine[0]
        iscrizione = Inscription.query.filter_by(
            gara_id=gara.id, user_id=ritirato.id
        ).one()
        iscrizione.is_withdrawn = True
        db.session.commit()
        RoundService.start_next_round(gara.id, 4)
        finale = Match.query.filter_by(
            gara_id=gara.id, round_number=4, bracket_slot=0
        ).one()
        assert {finale.player1_id, finale.player2_id} == {
            ordine[0].id,
            ordine[1].id,
        }
        assert finale.winner_id == ordine[1].id
        assert MatchStatus.is_finished(finale.status)


class TestAnteprima:
    def test_il_foglio_di_avvio_conta_il_turno_delle_finali(self, db_session):
        from models.competition.gironi_service import GironiService

        gara, _ = _gara(9)
        anteprima = GironiService.anteprima(gara)
        assert anteprima is not None
        # Un girone da nove: nove turni, niente finali. Due gironi da 5 e 4:
        # cinque turni più quello delle finali.
        assert anteprima.turni == {1: 9, 2: 6}
