"""Le due graduatorie Elo si calcolano sui rack (ADR-052).

Il motore puro è verificato in `test_rack_engine.py`. Qui si guarda l'innesto:
che il punteggio esatto arrivi fino al database, che `robustness` conti i
rack, che il trio si scomponga nei suoi confronti veri, e che la colonna
mostrata resti intera.

Non è un calcolo affiancato: **sostituisce** quello binario in entrambe le
graduatorie, quindi è il numero che i giocatori vedono.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models.base import db
from models.competition.models import Gara
from models.match.models import Match, TrioMatch, TrioRack
from models.rating import rack_engine
from models.rating.calculation_service import RatingCalculationService
from models.rating.models import PlayerRating, RatingSystem
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User

SOLO_ELO = [RatingSystem.ELO]


def _user():
    suffix = uuid.uuid4().hex[:8]
    u = User(username=f"rack_{suffix}", email=f"rack_{suffix}@t.com", role="player")
    u.set_password("x")
    db.session.add(u)
    db.session.flush()
    return u


def _gara():
    gara = Gara(
        number=1,
        name=f"Gara {uuid.uuid4().hex[:6]}",
        date=date(2026, 1, 1),
        time=time(18, 0),
        discipline="8_ball",
        distance=5,
        rounds_count=1,
        current_round=1,
        min_participants=2,
        max_participants=10,
        matchmaking_strategy="amalfi",
        status=GaraStatus.PLAYING.value,
    )
    db.session.add(gara)
    db.session.flush()
    return gara


def _match(p1, p2, rack1, rack2, **overrides):
    base = dict(
        gara_id=_gara().id,
        round_number=1,
        player1_id=p1.id if p1 else None,
        player2_id=p2.id if p2 else None,
        player1_score=rack1,
        player2_score=rack2,
        winner_id=(p1.id if rack1 > rack2 else (p2.id if rack2 > rack1 else None)),
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
    )
    base.update(overrides)
    match = Match(**base)
    db.session.add(match)
    db.session.flush()
    return match


def _partita(rack1, rack2, **overrides):
    p1, p2 = _user(), _user()
    return _match(p1, p2, rack1, rack2, **overrides), p1, p2


def _rating(user, sistema=RatingSystem.ELO):
    return PlayerRating.get_user_rating(user.id, sistema)


class TestIlPunteggioArrivaAlDatabase:
    def test_una_partita_conclusa_muove_i_due_rating(self, db_session):
        match, p1, p2 = _partita(5, 2)
        RatingCalculationService.process_match_result(match, systems=SOLO_ELO)
        db_session.flush()

        assert _rating(p1).rating_value > rack_engine.PARTENZA
        assert _rating(p2).rating_value < rack_engine.PARTENZA

    def test_il_margine_conta_fino_in_fondo(self, db_session):
        """5-0 e 5-4 non possono produrre lo stesso rating.

        È la ragione dell'intero cambio: il motore precedente leggeva solo
        `winner_id` e per lui le due partite erano identiche.
        """
        netta, vincitore_netto, _ = _partita(5, 0)
        tirata, vincitore_tirato, _ = _partita(5, 4)
        for match in (netta, tirata):
            RatingCalculationService.process_match_result(match, systems=SOLO_ELO)
        db_session.flush()

        assert (
            _rating(vincitore_netto).rating_value
            > _rating(vincitore_tirato).rating_value
        )

    def test_robustness_conta_i_rack_non_le_partite(self, db_session):
        """È la *robustness*: regola quanto in fretta il rating si muove."""
        match, p1, p2 = _partita(5, 2)
        RatingCalculationService.process_match_result(match, systems=SOLO_ELO)
        db_session.flush()

        assert _rating(p1).robustness == 7
        assert _rating(p2).robustness == 7

    def test_una_partita_senza_rack_non_muove_niente(self, db_session):
        match, p1, _ = _partita(0, 0)
        RatingCalculationService.process_match_result(match, systems=SOLO_ELO)
        db_session.flush()

        assert _rating(p1) is None

    def test_processare_due_volte_non_raddoppia(self, db_session):
        match, p1, _ = _partita(5, 0)
        RatingCalculationService.process_match_result(match, systems=SOLO_ELO)
        db_session.flush()
        dopo_una = _rating(p1).rating_value

        RatingCalculationService.process_match_result(match, systems=SOLO_ELO)
        db_session.flush()

        assert _rating(p1).rating_value == dopo_una


class TestLaColonnaMostrataRestaIntera:
    """`PlayerRating` tiene i decimali, `User.elo_rating` no.

    Il rating vive in virgola mobile perché una partita lo muove di pochi
    punti; la colonna che finisce sotto gli occhi dei giocatori è intera, e
    deve restare tale — altrimenti compare «1204.35» sulla scheda partita.
    """

    def test_elo_rating_e_intero_e_arrotondato(self, db_session):
        match, p1, p2 = _partita(5, 2)
        RatingCalculationService.process_match_result(match, systems=SOLO_ELO)
        db_session.flush()
        # Una seconda partita: alla prima i due partono uguali e i conti
        # vengono tondi per caso.
        RatingCalculationService.process_match_result(
            _match(p1, p2, 5, 3), systems=SOLO_ELO
        )
        db_session.flush()

        preciso = _rating(p1).rating_value
        assert preciso != int(preciso), "senza decimali il test non prova niente"
        assert p1.elo_rating == int(round(preciso))
        assert str(p1.elo_rating) == str(int(p1.elo_rating))


class TestIlTrioSiScompone:
    """Un trio è un girone: tre confronti veri, non una media.

    `TrioRack` registra per ogni rack chi erano i due al tavolo e chi ha vinto,
    quindi la scomposizione sta nei dati. Prima di ADR-052 il trio veniva
    collassato in un 1/0.5/0 confrontato con la media dei rating degli altri
    due — un avversario che non esiste.
    """

    def _trio(self, sequenza):
        """`sequenza`: lista di (indice_al_tavolo_1, indice_2, indice_vincitore)."""
        giocatori = [_user(), _user(), _user()]
        match = _match(giocatori[0], giocatori[1], 0, 0, is_trio=True)
        trio = TrioMatch(
            match_id=match.id,
            player1_id=giocatori[0].id,
            player2_id=giocatori[1].id,
            player3_id=giocatori[2].id,
        )
        db.session.add(trio)
        db.session.flush()

        for numero, (a, b, vincitore) in enumerate(sequenza, 1):
            attesa = ({0, 1, 2} - {a, b}).pop()
            db.session.add(
                TrioRack(
                    trio_match_id=trio.id,
                    rack_number=numero,
                    winner_id=giocatori[vincitore].id,
                    player1_id=giocatori[a].id,
                    player2_id=giocatori[b].id,
                    waiting_player_id=giocatori[attesa].id,
                )
            )
        db.session.flush()
        return match, giocatori

    def test_chi_vince_i_suoi_scontri_sale(self, db_session):
        match, g = self._trio([(0, 1, 0), (0, 1, 0), (0, 2, 0), (0, 2, 0), (1, 2, 1)])
        RatingCalculationService.process_match_result(match, systems=SOLO_ELO)
        db_session.flush()

        assert _rating(g[0]).rating_value > rack_engine.PARTENZA
        assert _rating(g[2]).rating_value < rack_engine.PARTENZA

    def test_il_totale_dei_rating_non_si_muove(self, db_session):
        """Tre confronti a somma zero restano a somma zero."""
        match, g = self._trio([(0, 1, 0), (1, 2, 1), (0, 2, 2)])
        RatingCalculationService.process_match_result(match, systems=SOLO_ELO)
        db_session.flush()

        totale = sum(_rating(x).rating_value for x in g)
        assert totale == pytest.approx(3 * rack_engine.PARTENZA)

    def test_un_trio_senza_righe_di_rack_viene_saltato(self, db_session):
        """Dati vecchi: non scomponibili, e inventarli sarebbe peggio."""
        giocatori = [_user(), _user(), _user()]
        match = _match(giocatori[0], giocatori[1], 3, 2, is_trio=True)
        trio = TrioMatch(
            match_id=match.id,
            player1_id=giocatori[0].id,
            player2_id=giocatori[1].id,
            player3_id=giocatori[2].id,
        )
        db.session.add(trio)
        db.session.flush()

        RatingCalculationService.process_match_result(match, systems=SOLO_ELO)
        db_session.flush()

        assert all(_rating(x) is None for x in giocatori)


class TestRicalcolo:
    def test_il_replay_ricostruisce_lo_stesso_valore(self, db_session):
        match, p1, _ = _partita(5, 1)
        RatingCalculationService.process_match_result(match, systems=SOLO_ELO)
        db_session.flush()
        atteso = _rating(p1).rating_value

        risultato = RatingCalculationService.recalculate_all_elo()
        db_session.flush()

        assert risultato["processed"] >= 1
        assert _rating(p1).rating_value == pytest.approx(atteso)


class TestLeVieDiVisualizzazione:
    """Le colonne sono float, l'interfaccia no.

    Passare `rating_value` a `Float` ha fatto comparire «1184.0» dove c'era
    «1184»: SQLAlchemy rilegge come float anche i valori interi. Il test
    dell'attività dashboard lo ha intercettato; queste due vie non erano
    coperte da nessuno.
    """

    def _scrivi(self, user, sistema, valore):
        db.session.add(
            PlayerRating(
                user_id=user.id,
                rating_system=sistema,
                rating_value=valore,
                robustness=1,
            )
        )
        db.session.flush()

    def test_elo_globale_del_profilo_non_ha_decimali(self, db_session):
        user = _user()
        self._scrivi(user, RatingSystem.ELO_GLOBAL, 1184.4)

        assert user.elo_global_rating == 1184
        assert str(user.elo_global_rating) == "1184"

    def test_la_classifica_elo_non_ha_decimali(self, db_session):
        from models.gamification.leaderboard_service import LeaderboardService

        user = _user()
        self._scrivi(user, RatingSystem.ELO, 1250.6)

        voci = LeaderboardService._calculate_elo_rating()
        mia = next((v for v in voci if v.user_id == user.id), None)
        assert mia is not None
        assert mia.score == 1251
