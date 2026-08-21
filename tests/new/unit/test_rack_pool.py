"""Il pool a rack si popola davvero, e non disturba quelli storici (ADR-052).

Il motore puro è verificato in `test_rack_engine.py`. Qui si guarda l'innesto:
che il pool venga scritto, che conti i rack e non le partite, e soprattutto che
i due pool storici e `User.elo_rating` restino dove sono — perché il pool a
rack nasce **affiancato e non mostrato**, e un effetto collaterale su quelli
visibili sarebbe l'unico modo in cui questa aggiunta può fare danni.
"""

from __future__ import annotations

import uuid
from datetime import date, time

import pytest

from models.base import db
from models.competition.models import Gara
from models.match.models import Match
from models.rating import rack_engine
from models.rating.calculation_service import RatingCalculationService
from models.rating.models import PlayerRating, RatingSystem
from models.status_enum import GaraStatus, MatchStatus
from models.user.models import User


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


def _partita(rack1, rack2, **overrides):
    """Una partita conclusa col punteggio dato, e i suoi due giocatori."""
    gara = _gara()
    p1, p2 = _user(), _user()
    base = dict(
        gara_id=gara.id,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        player1_score=rack1,
        player2_score=rack2,
        winner_id=p1.id if rack1 > rack2 else (p2.id if rack2 > rack1 else None),
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
    )
    base.update(overrides)
    match = Match(**base)
    db.session.add(match)
    db.session.flush()
    return match, p1, p2


def _partita_fra(p1, p2, rack1, rack2):
    """Un'altra partita fra due giocatori che si sono già affrontati."""
    gara = _gara()
    match = Match(
        gara_id=gara.id,
        round_number=1,
        player1_id=p1.id,
        player2_id=p2.id,
        player1_score=rack1,
        player2_score=rack2,
        winner_id=p1.id if rack1 > rack2 else (p2.id if rack2 > rack1 else None),
        status=MatchStatus.CONFIRMED_BY_BOTH.value,
    )
    db.session.add(match)
    db.session.flush()
    return match


def _rack_rating(user):
    return PlayerRating.get_user_rating(user.id, RatingSystem.RACK)


class TestIlPoolSiPopola:
    def test_una_partita_conclusa_scrive_il_pool(self, db_session):
        match, p1, p2 = _partita(5, 2)
        RatingCalculationService.process_match_result(
            match, systems=[RatingSystem.RACK]
        )
        db_session.flush()

        r1, r2 = _rack_rating(p1), _rack_rating(p2)
        assert r1 is not None and r2 is not None
        assert r1.rating_value > rack_engine.PARTENZA
        assert r2.rating_value < rack_engine.PARTENZA

    def test_il_valore_e_in_virgola_mobile(self, db_session):
        """Con delta di pochi punti l'intero sarebbe dell'ordine del segnale.

        Servono **due** partite: alla prima i due partono uguali, quindi
        l'atteso è mezzo rack tondo e il delta viene intero per caso. È dalla
        seconda in poi — cioè sempre, nella vita vera — che i decimali
        compaiono, e che troncarli farebbe perdere segnale.
        """
        match, p1, p2 = _partita(5, 2)
        RatingCalculationService.process_match_result(
            match, systems=[RatingSystem.RACK]
        )
        db_session.flush()

        RatingCalculationService.process_match_result(
            _partita_fra(p1, p2, 5, 3), systems=[RatingSystem.RACK]
        )
        db_session.flush()

        valore = _rack_rating(p1).rating_value
        assert isinstance(valore, float)
        assert valore != int(valore), "senza decimali il test non prova niente"

    def test_games_played_conta_i_rack_non_le_partite(self, db_session):
        """Nel pool a rack quel campo è la *robustness*, e regola il `k`."""
        match, p1, p2 = _partita(5, 2)
        RatingCalculationService.process_match_result(
            match, systems=[RatingSystem.RACK]
        )
        db_session.flush()

        assert _rack_rating(p1).games_played == 7
        assert _rack_rating(p2).games_played == 7

    def test_il_margine_arriva_fino_al_database(self, db_session):
        """5-0 e 5-4 non possono produrre lo stesso rating."""
        netta, vincitore_netto, _ = _partita(5, 0)
        tirata, vincitore_tirato, _ = _partita(5, 4)
        for match in (netta, tirata):
            RatingCalculationService.process_match_result(
                match, systems=[RatingSystem.RACK]
            )
        db_session.flush()

        assert (
            _rack_rating(vincitore_netto).rating_value
            > _rack_rating(vincitore_tirato).rating_value
        )


class TestNonDisturbaGliAltriPool:
    def test_non_tocca_user_elo_rating(self, db_session):
        """`User.elo_rating` è la fonte del solo pool competitivo."""
        match, p1, _ = _partita(5, 0)
        prima = p1.elo_rating

        RatingCalculationService.process_match_result(
            match, systems=[RatingSystem.RACK]
        )
        db_session.flush()

        assert p1.elo_rating == prima

    def test_non_crea_righe_negli_altri_pool(self, db_session):
        match, p1, _ = _partita(5, 0)
        RatingCalculationService.process_match_result(
            match, systems=[RatingSystem.RACK]
        )
        db_session.flush()

        assert PlayerRating.get_user_rating(p1.id, RatingSystem.ELO) is None
        assert PlayerRating.get_user_rating(p1.id, RatingSystem.ELO_GLOBAL) is None

    def test_processare_due_volte_non_raddoppia(self, db_session):
        """L'idempotenza per pool vale anche per questo (history per match)."""
        match, p1, _ = _partita(5, 0)
        RatingCalculationService.process_match_result(
            match, systems=[RatingSystem.RACK]
        )
        db_session.flush()
        dopo_una = _rack_rating(p1).rating_value

        RatingCalculationService.process_match_result(
            match, systems=[RatingSystem.RACK]
        )
        db_session.flush()

        assert _rack_rating(p1).rating_value == dopo_una


class TestIlTrioRestaFuori:
    def test_un_trio_non_entra_nel_pool(self, db_session):
        """In `TrioMatch` i rack sono per giocatore, non per coppia.

        Non esiste il dato con cui costruire i tre confronti del girone
        interno, e ripartirlo a occhio significherebbe far dire ai numeri
        qualcosa che non hanno visto.
        """
        match, p1, p2 = _partita(5, 2, is_trio=True)
        RatingCalculationService.process_match_result(
            match, systems=[RatingSystem.RACK]
        )
        db_session.flush()

        assert _rack_rating(p1) is None
        assert _rack_rating(p2) is None


class TestRicalcolo:
    def test_il_ricalcolo_ricostruisce_lo_stesso_valore(self, db_session):
        """Il replay deve tornare al punto in cui era: è la sua unica promessa."""
        match, p1, _ = _partita(5, 1)
        RatingCalculationService.process_match_result(
            match, systems=[RatingSystem.RACK]
        )
        db_session.flush()
        atteso = _rack_rating(p1).rating_value

        risultato = RatingCalculationService.recalculate_all_rack()
        db_session.flush()

        assert risultato["processed"] >= 1
        assert _rack_rating(p1).rating_value == pytest.approx(atteso)


class TestIPoolStoriciRestanoInteri:
    """Le colonne sono in virgola mobile, ma l'interfaccia no.

    Passare `rating_value` a `Float` per il pool a rack ha fatto comparire
    «1184.0» dove prima c'era «1184»: i pool storici scrivono interi, ma
    SQLAlchemy li rilegge come float. Il test dell'attività dashboard lo ha
    intercettato; queste due vie non erano coperte da nessuno.
    """

    def _scrivi(self, user, sistema, valore):
        db.session.add(
            PlayerRating(
                user_id=user.id,
                rating_system=sistema,
                rating_value=valore,
                games_played=1,
            )
        )
        db.session.flush()

    def test_elo_globale_del_profilo_non_ha_decimali(self, db_session):
        user = _user()
        self._scrivi(user, RatingSystem.ELO_GLOBAL, 1184.0)

        assert user.elo_global_rating == 1184
        assert str(user.elo_global_rating) == "1184"

    def test_la_classifica_elo_non_ha_decimali(self, db_session):
        from models.gamification.leaderboard_service import LeaderboardService

        user = _user()
        self._scrivi(user, RatingSystem.ELO, 1250.0)

        voci = LeaderboardService._calculate_elo_rating()
        mia = next((v for v in voci if v.user_id == user.id), None)
        assert mia is not None
        assert mia.score == 1250
        assert str(mia.score) == "1250"
