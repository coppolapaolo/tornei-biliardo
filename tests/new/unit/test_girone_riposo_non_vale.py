"""Nel girone all'italiana il riposo non vale, e l'escluso dà la vittoria a tavolino.

Decisione dell'utente del 2026-10-11 (SPECIFICHE.md, «Strategia di
abbinamento», nota del 2026-10-11), nata dal piano dei gironi multipli: fra
gironi di taglia diversa la X regalava una vittoria a chi stava nel girone
dispari.

* **Riposo da calendario.** Col round robin e un numero dispari di giocatori,
  a ogni turno uno riposa. Il riposo resta visibile — una partita `is_bye`
  col solo giocatore che riposa — ma nasce **senza vincitore**: zero vittorie,
  zero punti, zero triangoli, nessuna partita giocata. Vale con ogni sistema
  di classifica ammesso dal girone (WINS, RACK, POINTS).
* **Avversario escluso.** Chi viene escluso a girone in corso (policy
  EXCLUDE) resta al suo posto nel calendario: il suo avversario dei turni
  successivi vince **a tavolino**, come contro un forfait, con i triangoli
  pieni alla distanza effettiva del turno (ADR-027). Se l'escluso era chi
  riposava, o se sono esclusi tutti e due, quel posto non produce partite.
* **La X con prova non c'è più nel girone**: il dispari si gestisce solo col
  riposo semplice. Per questo il divieto della X semplice col sistema RACK
  («chi riposa avrebbe zero triangoli») non vale per il girone: lì ognuno
  riposa esattamente una volta, e lo zero tocca tutti allo stesso modo.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import List, Tuple

import pytest

from models import User
from models.base import db, utc_now
from models.classification.score_aggregator import ScoreAggregator
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara
from models.competition.round_configuration import RoundConfiguration
from models.competition.round_creation import RoundCreationService
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.competition.withdraw_policy_service import WithdrawPolicyService
from models.match.models import Match
from models.matchmaking.bootstrap import get_registry
from models.matchmaking.configuration import MatchmakingStrategy, OddNumberPolicy
from models.status_enum import MatchStatus, WithdrawPolicy
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit


def _utente(role: str = UserRole.PLAYER.value) -> User:
    sigla = uuid.uuid4().hex[:8]
    user = User(username=f"gir_{sigla}", email=f"gir_{sigla}@test.local")
    user.role = role
    user.set_password("x")
    db.session.add(user)
    return user


def _girone(
    n: int,
    *,
    sistema: str = "WINS",
    withdraw_policy: str = WithdrawPolicy.FORFEIT.value,
    distanza: int = 5,
) -> Tuple[Gara, List[User]]:
    direttore = _utente(UserRole.DIRECTOR.value)
    giocatori = [_utente() for _ in range(n)]
    db.session.commit()

    gara = GaraService.create_gara(
        campionato_id=None,
        number=1,
        name=f"Girone {uuid.uuid4().hex[:6]}",
        date=date.today() + timedelta(days=7),
        location="Sala",
        description="",
        rounds_count=n if n % 2 else n - 1,
        min_participants=3,
        max_participants=16,
        entry_fee=0.0,
        discipline="8_ball",
        distance=distanza,
        # «Esattamente N» col sistema RACK, «al N» altrove: è la combinazione
        # che i validatori ammettono senza avvisi.
        is_race_to=sistema != "RACK",
        director_id=direttore.id,
        matchmaking_strategy=MatchmakingStrategy.ROUND_ROBIN.value,
        first_round_policy="random",
        odd_number_policy=OddNumberPolicy.BYE.value,
        anti_rematch_enabled=False,
        classification_system=sistema,
    )
    gara.withdraw_policy = withdraw_policy
    db.session.commit()

    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for giocatore in giocatori:
        InscriptionService.inscribe_user(giocatore.id, gara.id)
    return gara, giocatori


def _partite(gara_id: int, turno: int) -> List[Match]:
    return (
        db.session.query(Match)
        .filter_by(gara_id=gara_id, round_number=turno)
        .order_by(Match.id)
        .all()
    )


def _chiudi_turno(gara_id: int, turno: int) -> None:
    """Chiude 3-1 per il primo giocatore le partite ancora aperte del turno."""
    for match in _partite(gara_id, turno):
        if MatchStatus.is_finished(match.status):
            continue
        match.player1_score = 3
        match.player2_score = 1
        match.winner_id = match.player1_id
        match.status = MatchStatus.CLOSED_UNILATERALLY.value
    db.session.commit()


def _turno_previsto(gara: Gara, turno: int) -> List[Tuple[int, ...]]:
    db.session.expire_all()
    gara = db.session.get(Gara, gara.id)
    strategia = get_registry().get(MatchmakingStrategy.ROUND_ROBIN.value)
    return [tuple(p.players) for p in strategia.create_round(gara, turno)]


# ══ Il riposo da calendario ═══════════════════════════════════════════════


class TestIlRiposoNonVale:
    @pytest.mark.parametrize("sistema", ["WINS", "RACK", "POINTS"])
    def test_il_riposo_nasce_senza_vincitore_e_vale_zero(self, db_session, sistema):
        gara, _ = _girone(5, sistema=sistema)
        RoundService.start_first_round(gara.id)

        riposi = [m for m in _partite(gara.id, 1) if m.is_bye]
        assert len(riposi) == 1
        riposo = riposi[0]
        assert riposo.winner_id is None
        assert riposo.player1_score == 0
        assert riposo.is_riposo
        assert MatchStatus.is_finished(riposo.status)

        voce = {
            v.player_id: v for v in ScoreAggregator().aggregate_round_scores(gara.id, 1)
        }[riposo.player1_id]
        assert voce.matches_won == 0
        assert voce.matches_lost == 0
        assert voce.matches_drawn == 0
        assert voce.points == 0
        assert voce.racks_won == 0
        assert voce.racks_lost == 0

    def test_chi_riposa_resta_in_classifica(self, db_session):
        """Il riposo non vale niente, ma chi riposa non sparisce dalla classifica."""
        gara, giocatori = _girone(5)
        RoundService.start_first_round(gara.id)
        _chiudi_turno(gara.id, 1)

        presenti = {
            v.player_id for v in ScoreAggregator().aggregate_round_scores(gara.id, 1)
        }
        assert presenti == {g.id for g in giocatori}

    def test_la_x_delle_altre_strategie_vale_ancora_una_vittoria(self, db_session):
        """La regola nuova è del girone: la X di amalfi e casuale non cambia."""
        from models.competition.round_creation import create_matches_from_pairings
        from models.matchmaking.strategies.base import Pairing

        gara, giocatori = _girone(5)
        gara.matchmaking_strategy = MatchmakingStrategy.AMALFI.value
        db.session.commit()
        create_matches_from_pairings(
            gara=gara,
            pairings=[Pairing(players=(giocatori[0].id,), is_bye=True)],
            round_number=1,
            round_distance=5,
        )
        db.session.commit()
        x = _partite(gara.id, 1)[0]
        assert x.winner_id == giocatori[0].id
        assert not x.is_riposo


# ══ L'avversario escluso ══════════════════════════════════════════════════


class TestLAvversarioDellEsclusoVinceATavolino:
    def _escludi_fra_turno_1_e_2(self, n: int):
        gara, giocatori = _girone(n, withdraw_policy=WithdrawPolicy.EXCLUDE.value)
        RoundService.start_first_round(gara.id)
        _chiudi_turno(gara.id, 1)
        previsto = _turno_previsto(gara, 2)
        return gara, giocatori, previsto

    @pytest.mark.parametrize("n", [5, 6])
    def test_vittoria_a_tavolino_alla_distanza_del_turno(self, db_session, n):
        gara, giocatori, previsto = self._escludi_fra_turno_1_e_2(n)
        coppia = next(p for p in previsto if len(p) == 2)
        escluso, avversario = coppia[0], coppia[1]

        # Il turno 2 si gioca «al 3» in una gara «al 5»: il tavolino vale 3.
        RoundConfiguration.create_or_update(gara.id, 2, distance=3)
        db.session.commit()
        WithdrawPolicyService.handle_forfeit(gara_id=gara.id, user_id=escluso)
        db.session.commit()

        RoundCreationService.create_round_with_strategy(gara.id, 2)
        partita = next(
            m
            for m in _partite(gara.id, 2)
            if {m.player1_id, m.player2_id} == {escluso, avversario}
        )
        assert not partita.is_bye
        assert partita.winner_id == avversario
        assert MatchStatus.is_finished(partita.status)
        punteggio = {
            partita.player1_id: partita.player1_score,
            partita.player2_id: partita.player2_score,
        }
        assert punteggio == {avversario: 3, escluso: 0}

        voce = {
            v.player_id: v for v in ScoreAggregator().aggregate_round_scores(gara.id, 2)
        }[avversario]
        assert voce.matches_won >= 1

    def test_l_escluso_che_riposava_non_produce_partite(self, db_session):
        gara, giocatori, previsto = self._escludi_fra_turno_1_e_2(5)
        chi_riposa = next(p[0] for p in previsto if len(p) == 1)

        WithdrawPolicyService.handle_forfeit(gara_id=gara.id, user_id=chi_riposa)
        db.session.commit()

        turno = _turno_previsto(gara, 2)
        assert all(chi_riposa not in p for p in turno)
        assert all(len(p) == 2 for p in turno), "nessun altro riposa al suo posto"

    def test_due_esclusi_della_stessa_coppia_non_producono_partite(self, db_session):
        gara, giocatori, previsto = self._escludi_fra_turno_1_e_2(6)
        a, b = next(p for p in previsto if len(p) == 2)

        for escluso in (a, b):
            WithdrawPolicyService.handle_forfeit(gara_id=gara.id, user_id=escluso)
        db.session.commit()

        turno = _turno_previsto(gara, 2)
        assert all(a not in p and b not in p for p in turno)
        assert len(turno) == len(previsto) - 1

    def test_il_tavolino_dell_escluso_non_da_xp_all_escluso(self, db_session):
        """Chi è uscito dalla gara non prende i punti esperienza della sconfitta."""
        from models.gamification.models import XPTransaction

        gara, giocatori, previsto = self._escludi_fra_turno_1_e_2(6)
        escluso, avversario = next(p for p in previsto if len(p) == 2)
        WithdrawPolicyService.handle_forfeit(gara_id=gara.id, user_id=escluso)
        db.session.commit()
        prima = db.session.query(XPTransaction).filter_by(user_id=escluso).count()

        RoundCreationService.create_round_with_strategy(gara.id, 2)
        db.session.commit()

        dopo = db.session.query(XPTransaction).filter_by(user_id=escluso).count()
        assert dopo == prima


# ══ Le formule dei dispari ammesse col girone ═════════════════════════════


class TestDispariNelGirone:
    def test_col_girone_solo_il_riposo_semplice(self):
        from models.matchmaking.configuration import STRATEGY_CONSTRAINTS

        assert STRATEGY_CONSTRAINTS[MatchmakingStrategy.ROUND_ROBIN][
            "odd_policies"
        ] == [OddNumberPolicy.BYE.value]

    def test_rack_ammette_il_riposo_semplice_solo_col_girone(self):
        from models.competition import validators as v

        def errori(matchmaking):
            return v.validate_gara_configuration(
                classification_system=v.ClassificationSystem.RACK,
                distance_type=v.DistanceType.EXACTLY,
                distance=4,
                multi_set=False,
                odd_handling=v.OddHandling.BYE,
                forfeit_policy=v.ForfeitPolicy.FORFEIT,
                matchmaking=matchmaking,
            )[0]

        assert errori(v.MatchmakingStrategy.ROUND_ROBIN) == []
        assert any("Bye" in e for e in errori(v.MatchmakingStrategy.AMALFI))

    def test_la_gara_singola_con_la_x_con_prova_ripiega_sul_riposo(self, db_session):
        direttore = _utente(UserRole.DIRECTOR.value)
        db.session.commit()
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name=f"Girone {uuid.uuid4().hex[:6]}",
            date=date.today() + timedelta(days=7),
            location="Sala",
            description="",
            rounds_count=5,
            min_participants=3,
            max_participants=16,
            entry_fee=0.0,
            discipline="8_ball",
            distance=5,
            is_race_to=True,
            director_id=direttore.id,
            matchmaking_strategy=MatchmakingStrategy.ROUND_ROBIN.value,
            first_round_policy="random",
            odd_number_policy=OddNumberPolicy.BYE_WITH_CHALLENGE.value,
            anti_rematch_enabled=False,
        )
        assert gara.odd_number_policy == OddNumberPolicy.BYE.value
        assert gara.x_challenge_id is None

    def test_la_modifica_ripiega_sul_riposo(self, db_session):
        gara, _ = _girone(5)
        GaraService.update_gara(
            gara.id, odd_number_policy=OddNumberPolicy.BYE_WITH_CHALLENGE.value
        )
        assert gara.odd_number_policy == OddNumberPolicy.BYE.value

    def test_le_opzioni_dei_moduli_del_girone(self, app):
        from utils.jinja import opzioni_dispari

        with app.test_request_context():
            valori = [
                v
                for v, _ in opzioni_dispari(
                    "RACK", strategy=MatchmakingStrategy.ROUND_ROBIN.value
                )
            ]
            assert valori == [OddNumberPolicy.BYE.value]
            assert OddNumberPolicy.BYE.value not in [
                v for v, _ in opzioni_dispari("RACK")
            ]


# ══ Il riposo si vede, e si chiama riposo ═════════════════════════════════


class TestIlRiposoSiVede:
    def test_la_pagina_della_gara_mostra_chi_riposa(self, db_session, client):
        gara, giocatori = _girone(5)
        RoundService.start_first_round(gara.id)
        riposo = next(m for m in _partite(gara.id, 1) if m.is_bye)
        direttore = gara.director
        with client.session_transaction() as sess:
            sess["_user_id"] = direttore.get_id()
            sess["_fresh"] = True

        pagina = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

        assert riposo.player1.username in pagina
        # La partita di chi riposa si chiama «Riposo», non «X a tavolino», e
        # la formula della gara dice che non vale punti.
        assert ">Riposo<" in pagina
        assert "X a tavolino" not in pagina
        assert "Riposo, non vale punti" in pagina
