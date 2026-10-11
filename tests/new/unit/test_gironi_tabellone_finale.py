"""I gironi col tabellone finale, sul database (piano gironi, PR 5).

Gare singole, perché ogni opzione vale prima di tutto sulla gara. Si gioca
dal servizio: avvio, turni dei gironi, tabellone, classifica finale.
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
from models.exceptions import ValidationError
from models.match.models import Match
from models.match.services import RackService
from models.matchmaking.bracket import BRACKET_THIRD_PLACE, BRACKET_WINNERS
from models.status_enum import MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _utente(role: str, elo: Optional[int] = None) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"tf_{role}_{uid}", email=f"tf_{role}_{uid}@test.com")
    user.role = role
    user.set_password("x")
    user.elo_rating = elo
    db.session.add(user)
    return user


def _gara(
    n: int,
    *,
    max_groups: int = 2,
    k: int = 2,
    finalina: bool = True,
    **extra,
) -> Tuple[Gara, List[User]]:
    director = _utente(UserRole.DIRECTOR.value)
    players = [_utente(UserRole.PLAYER.value, elo=2000 - 10 * i) for i in range(n)]
    db.session.commit()
    valori = dict(
        campionato_id=None,
        number=1,
        name="Gironi e tabellone",
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
        final_phase_mode="tabellone",
        qualifiers_per_group=k,
        third_place_match=finalina,
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


def _gioca_tutto(
    gara: Gara, chi_vince: Callable[[Match], int], groups_count: int = 2
) -> Gara:
    RoundService.start_first_round(gara.id, groups_count=groups_count)
    gara = db.session.get(Gara, gara.id)
    for r in range(1, gara.rounds_count + 1):
        if r > 1:
            RoundService.start_next_round(gara.id, r)
        _gioca(gara.id, r, chi_vince)
    return db.session.get(Gara, gara.id)


def _gironi(gara: Gara) -> Dict[int, List[int]]:
    per: Dict[int, List[int]] = {}
    for i in Inscription.query.filter_by(gara_id=gara.id).all():
        per.setdefault(i.group_index, []).append(i.user_id)
    return per


def _posizioni(gara: Gara) -> Dict[int, int]:
    return {
        gc.user_id: gc.position
        for gc in GaraClassification.query.filter_by(gara_id=gara.id).all()
    }


class TestAvvio:
    def test_due_gironi_da_quattro_semifinali_e_finale(self, db_session):
        gara, _ = _gara(8)
        RoundService.start_first_round(gara.id, groups_count=2)
        # Tre turni di gironi, poi semifinali e finale (la finalina sta nel
        # turno della finale).
        assert db.session.get(Gara, gara.id).rounds_count == 3 + 2

    def test_tre_gironi_e_due_qualificati_tabellone_da_otto(self, db_session):
        gara, _ = _gara(9, max_groups=3)
        RoundService.start_first_round(gara.id, groups_count=3)
        assert db.session.get(Gara, gara.id).rounds_count == 3 + 3

    def test_k_oltre_il_girone_piu_piccolo_ferma_l_avvio(self, db_session):
        gara, _ = _gara(7, k=4)
        with pytest.raises(ValidationError):
            RoundService.start_first_round(gara.id, groups_count=2)

    def test_esattamente_n_non_e_ammesso(self, db_session):
        with pytest.raises(ValueError):
            _gara(8, is_race_to=False)


class TestTabellone:
    def test_incroci_1a_2b_e_1b_2a(self, db_session):
        gara, p = _gara(8)
        elo = {u.id: u.elo_rating for u in p}
        RoundService.start_first_round(gara.id, groups_count=2)
        gara = db.session.get(Gara, gara.id)
        for r in range(1, 4):
            if r > 1:
                RoundService.start_next_round(gara.id, r)
            _gioca(gara.id, r, _vince_il_piu_forte(elo))
        RoundService.start_next_round(gara.id, 4)
        gironi = _gironi(gara)
        girone_di = {pid: g for g, ids in gironi.items() for pid in ids}
        primo = {g: max(ids, key=lambda i: elo[i]) for g, ids in gironi.items()}
        secondo = {
            g: sorted(ids, key=lambda i: -elo[i])[1] for g, ids in gironi.items()
        }
        semifinali = Match.query.filter_by(gara_id=gara.id, round_number=4).all()
        assert len(semifinali) == 2
        assert all(m.bracket_type == BRACKET_WINNERS for m in semifinali)
        assert all(m.bracket_group is None for m in semifinali)
        coppie = {frozenset((m.player1_id, m.player2_id)) for m in semifinali}
        assert coppie == {
            frozenset((primo[0], secondo[1])),
            frozenset((primo[1], secondo[0])),
        }
        for m in semifinali:
            assert girone_di[m.player1_id] != girone_di[m.player2_id]

    def test_classifica_finale_con_finalina(self, db_session):
        gara, p = _gara(8)
        elo = {u.id: u.elo_rating for u in p}
        gara = _gioca_tutto(gara, _vince_il_piu_forte(elo))
        finale = Match.query.filter_by(gara_id=gara.id, round_number=5).all()
        assert {m.bracket_type for m in finale} == {
            BRACKET_WINNERS,
            BRACKET_THIRD_PLACE,
        }
        StateService.complete(gara)
        db.session.commit()
        pos = _posizioni(gara)
        # Il più forte vince tutto: l'ordine finale è quello dell'ELO per i
        # primi quattro, poi i non qualificati nell'ordine dei gironi.
        ordine = sorted(p, key=lambda u: -u.elo_rating)
        assert [pos[u.id] for u in ordine[:4]] == [1, 2, 3, 4]
        # I terzi dei due gironi sono pari per partita: condividono il posto.
        assert sorted(pos[u.id] for u in ordine[4:]) == [5, 5, 7, 7]
        gc = GaraClassification.query.filter_by(
            gara_id=gara.id, user_id=ordine[0].id
        ).one()
        assert gc.group_position == 1

    def test_senza_finalina_due_terzi(self, db_session):
        gara, p = _gara(8, finalina=False)
        elo = {u.id: u.elo_rating for u in p}
        gara = _gioca_tutto(gara, _vince_il_piu_forte(elo))
        StateService.complete(gara)
        db.session.commit()
        pos = _posizioni(gara)
        ordine = sorted(p, key=lambda u: -u.elo_rating)
        assert [pos[u.id] for u in ordine[:4]] == [1, 2, 3, 3]
        assert not SpareggioService.detect_tiebreakers(gara.id)

    def test_tre_gironi_bye_ai_migliori_primi(self, db_session):
        gara, p = _gara(9, max_groups=3)
        elo = {u.id: u.elo_rating for u in p}
        RoundService.start_first_round(gara.id, groups_count=3)
        gara = db.session.get(Gara, gara.id)
        for r in range(1, 4):
            if r > 1:
                RoundService.start_next_round(gara.id, r)
            _gioca(gara.id, r, _vince_il_piu_forte(elo))
        RoundService.start_next_round(gara.id, 4)
        quarti = Match.query.filter_by(gara_id=gara.id, round_number=4).all()
        bye = [m.player1_id for m in quarti if m.is_bye]
        assert len(quarti) == 4 and len(bye) == 2
        gironi = _gironi(gara)
        primi = [max(ids, key=lambda i: elo[i]) for ids in gironi.values()]
        # A parità di partite giocate e di risultati (tutti a punteggio
        # pieno), i due bye vanno a due primi.
        assert set(bye) <= set(primi)

    def test_classifica_del_turno_durante_il_tabellone(self, db_session):
        gara, p = _gara(8)
        elo = {u.id: u.elo_rating for u in p}
        RoundService.start_first_round(gara.id, groups_count=2)
        for r in range(1, 5):
            if r > 1:
                RoundService.start_next_round(gara.id, r)
            _gioca(gara.id, r, _vince_il_piu_forte(elo))
        righe = {
            rc.user_id: rc
            for rc in RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=4
            ).all()
        }
        ordine = sorted(p, key=lambda u: -u.elo_rating)
        # I due finalisti in cima; i numeri restano quelli dei gironi (3
        # partite, non 4).
        assert {righe[ordine[0].id].position, righe[ordine[1].id].position} == {1, 2}
        assert righe[ordine[0].id].matches_won == 3
        assert righe[ordine[0].id].group_position == 1


class TestSoloConPiuGironi:
    def test_col_girone_unico_il_tabellone_e_rifiutato(self, db_session):
        with pytest.raises(ValueError):
            _gara(6, max_groups=1)

    def test_partita_con_un_girone_la_gara_finisce_col_girone(self, db_session):
        """Fino a 2 gironi, ma 5 iscritti in un girone solo: niente tabellone."""
        gara, p = _gara(5)
        elo = {u.id: u.elo_rating for u in p}
        gara = _gioca_tutto(gara, _vince_il_piu_forte(elo), groups_count=1)
        assert gara.rounds_count == 5
        assert not Match.query.filter(
            Match.gara_id == gara.id, Match.bracket_type.isnot(None)
        ).count()
        StateService.complete(gara)
        db.session.commit()
        pos = _posizioni(gara)
        ordine = sorted(p, key=lambda u: -u.elo_rating)
        assert [pos[u.id] for u in ordine] == [1, 2, 3, 4, 5]


class TestTaglio:
    def test_i_pari_al_taglio_li_decide_la_catena_di_turno(self, db_session):
        """Tre pari al 2º posto del girone A, per vittorie e differenza: la
        catena di gara li lascerebbe pari, quella di turno no — passa chi è
        2º nella classifica dell'ultimo turno dei gironi."""
        gara, p = _gara(8)
        elo = {u.id: u.elo_rating for u in p}
        # Girone A per ELO: p0, p3, p4, p7. p0 batte tutti; fra gli altri tre
        # un giro: p3 batte p4, p4 batte p7, p7 batte p3.
        giro = {(p[3].id, p[4].id), (p[4].id, p[7].id), (p[7].id, p[3].id)}

        def chi_vince(m: Match) -> int:
            a, b = m.player1_id, m.player2_id
            if (a, b) in giro:
                return a
            if (b, a) in giro:
                return b
            return max((a, b), key=lambda x: elo[x])

        RoundService.start_first_round(gara.id, groups_count=2)
        for r in range(1, 4):
            if r > 1:
                RoundService.start_next_round(gara.id, r)
            _gioca(gara.id, r, chi_vince)
        righe = {
            rc.user_id: rc
            for rc in RoundClassification.query.filter_by(
                gara_id=gara.id, round_number=3
            ).all()
        }
        pari = [p[3].id, p[4].id, p[7].id]
        assert (
            len({(righe[i].matches_won, righe[i].rack_difference) for i in pari}) == 1
        )
        secondo_a = next(i for i in pari if righe[i].group_position == 2)
        RoundService.start_next_round(gara.id, 4)
        in_semifinale = {
            pid
            for m in Match.query.filter_by(gara_id=gara.id, round_number=4).all()
            for pid in (m.player1_id, m.player2_id)
        }
        assert secondo_a in in_semifinale
        assert not (set(pari) - {secondo_a}) & in_semifinale


class TestLimiteDiTempo:
    def test_la_fase_finale_ha_il_suo_limite(self, db_session):
        gara, p = _gara(8, time_limit_minutes=30, final_phase_time_limit_minutes=45)
        elo = {u.id: u.elo_rating for u in p}
        RoundService.start_first_round(gara.id, groups_count=2)
        for r in range(1, 4):
            if r > 1:
                RoundService.start_next_round(gara.id, r)
            _gioca(gara.id, r, _vince_il_piu_forte(elo))
        RoundService.start_next_round(gara.id, 4)
        gironi = Match.query.filter(
            Match.gara_id == gara.id, Match.round_number <= 3, Match.is_bye.is_(False)
        ).all()
        semifinali = Match.query.filter_by(gara_id=gara.id, round_number=4).all()
        assert {m.time_limit_minutes for m in gironi} == {30}
        assert {m.time_limit_minutes for m in semifinali} == {45}

    def test_come_i_gironi_e_senza_limite(self, db_session):
        gara, _ = _gara(8, time_limit_minutes=30)
        assert gara.effective_final_phase_time_limit_minutes == 30
        gara.final_phase_time_limit_minutes = 0
        assert gara.effective_final_phase_time_limit_minutes is None

    def test_l_override_del_turno_vince_sulla_fase_finale(self, db_session):
        from models.competition.round_configuration import RoundConfiguration

        gara, p = _gara(8, time_limit_minutes=30, final_phase_time_limit_minutes=45)
        elo = {u.id: u.elo_rating for u in p}
        RoundService.start_first_round(gara.id, groups_count=2)
        # La finale è il turno 5, che prima dell'avvio non si conosceva.
        RoundConfiguration.create_or_update(gara.id, 5, time_limit_minutes=0)
        db.session.commit()
        for r in range(1, 5):
            if r > 1:
                RoundService.start_next_round(gara.id, r)
            _gioca(gara.id, r, _vince_il_piu_forte(elo))
        RoundService.start_next_round(gara.id, 5)
        semifinali = Match.query.filter_by(gara_id=gara.id, round_number=4).all()
        finale = Match.query.filter_by(gara_id=gara.id, round_number=5).all()
        assert {m.time_limit_minutes for m in semifinali} == {45}
        assert {m.time_limit_minutes for m in finale} == {None}
