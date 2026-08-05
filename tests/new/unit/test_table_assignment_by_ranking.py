"""Test per l'assegnazione tavoli in base alla classifica (ranked mode).

Feature: gara.assign_tables_by_ranking (effettivo solo con strategia random).
- I tavoli configurati sono elencati in ordine di pregio.
- Dal secondo turno in poi nessun match parte finché TUTTE le partite del
  turno precedente non sono terminate; poi, a classifica provvisoria
  aggiornata, il primo tavolo libero della lista va al match in attesa con
  il giocatore meglio piazzato, e così via.
- Flag spento: comportamento pull invariato (i match del turno successivo
  possono partire in anticipo, fino a current_round + 1).
"""

import uuid
from datetime import date

import pytest

from models import Gara, Match, User
from models.status_enum import GaraStatus, MatchStatus, Discipline
from models.match.table_assignment_service import TableAssignmentService


@pytest.mark.unit
class TestTableAssignmentByRanking:
    """Ranked mode di TableAssignmentService.assign_available_tables."""

    @pytest.fixture
    def players(self, db_session):
        """Sei giocatori (A..F) per due turni da 3 match."""
        batch = str(uuid.uuid4())[:8]
        players = []
        for letter in "abcdef":
            user = User(
                username=f"rk_{letter}_{batch}",
                email=f"rk_{letter}_{batch}@test.com",
                password_hash="test",
            )
            db_session.add(user)
            players.append(user)
        db_session.commit()
        return players

    def _make_gara(self, db_session, ranked=True, tables=("T1", "T2", "T3")):
        gara = Gara(
            number=1,
            name="Gara tavoli per classifica",
            date=date.today(),
            discipline=Discipline.NINE_BALL.value,
            distance=4,
            matchmaking_strategy="random",
            classification_system="RACK",
            status=GaraStatus.PLAYING.value,
            current_round=1,
            rounds_count=2,
            min_participants=6,
            assign_tables_by_ranking=ranked,
        )
        gara.set_available_tables(list(tables))
        db_session.add(gara)
        db_session.commit()
        return gara

    @staticmethod
    def _add_match(
        db_session,
        gara,
        round_number,
        p1,
        p2,
        status=MatchStatus.PENDING.value,
        score=(0, 0),
        table=None,
    ):
        match = Match(
            gara_id=gara.id,
            round_number=round_number,
            player1_id=p1.id,
            player2_id=p2.id,
            status=status,
            player1_score=score[0],
            player2_score=score[1],
            table_assignment=table,
        )
        db_session.add(match)
        db_session.commit()
        return match

    def _round1_completed(self, db_session, gara, players):
        """Turno 1 completato con rack totali distinti (sistema RACK).

        Rack vinti: A=7, C=5, E=4, F=3, D=2, B=0
        → classifica attesa: A(1), C(2), E(3), F(4), D(5), B(6).
        """
        a, b, c, d, e, f = players
        done = MatchStatus.COMPLETED.value
        self._add_match(db_session, gara, 1, a, b, status=done, score=(7, 0))
        self._add_match(db_session, gara, 1, c, d, status=done, score=(5, 2))
        self._add_match(db_session, gara, 1, e, f, status=done, score=(4, 3))

    def _round2_pending(self, db_session, gara, players):
        """Turno 2 in attesa: m4=(B,E), m5=(D,A), m6=(F,C)."""
        a, b, c, d, e, f = players
        m4 = self._add_match(db_session, gara, 2, b, e)
        m5 = self._add_match(db_session, gara, 2, d, a)
        m6 = self._add_match(db_session, gara, 2, f, c)
        return m4, m5, m6

    def test_ranked_mode_waits_for_previous_round_completion(self, db_session, players):
        """Con il flag attivo il turno 2 NON parte finché il turno 1 non
        è completamente terminato, anche se ci sono tavoli liberi."""
        gara = self._make_gara(db_session, ranked=True)
        a, b, c, d, e, f = players
        done = MatchStatus.COMPLETED.value
        self._add_match(db_session, gara, 1, a, b, status=done, score=(7, 0))
        self._add_match(db_session, gara, 1, c, d, status=done, score=(5, 2))
        # m3 ancora in gioco sul T3: T1 e T2 sono liberi
        self._add_match(
            db_session,
            gara,
            1,
            e,
            f,
            status=MatchStatus.PLAYING.value,
            table="T3",
        )
        m4, m5, m6 = self._round2_pending(db_session, gara, players)

        assigned = TableAssignmentService.assign_available_tables(gara.id)

        assert assigned == 0
        for match in (m4, m5, m6):
            refreshed = db_session.get(Match, match.id)
            assert refreshed.table_assignment is None
            assert refreshed.status == MatchStatus.PENDING.value

    def test_flag_off_allows_next_round_early_start(self, db_session, players):
        """Senza flag il comportamento pull resta invariato: un match del
        turno 2 con entrambi i giocatori liberi parte in anticipo."""
        gara = self._make_gara(db_session, ranked=False)
        a, b, c, d, e, f = players
        done = MatchStatus.COMPLETED.value
        self._add_match(db_session, gara, 1, a, b, status=done, score=(7, 0))
        self._add_match(db_session, gara, 1, c, d, status=done, score=(5, 2))
        self._add_match(
            db_session,
            gara,
            1,
            e,
            f,
            status=MatchStatus.PLAYING.value,
            table="T3",
        )
        m4, m5, m6 = self._round2_pending(db_session, gara, players)

        assigned = TableAssignmentService.assign_available_tables(gara.id)

        # m4 (B,E) ed m6 (F,C) hanno un giocatore impegnato in m3;
        # m5 (D,A) è libero e prende il primo tavolo libero della lista.
        assert assigned == 1
        m5_refreshed = db_session.get(Match, m5.id)
        assert m5_refreshed.table_assignment == "T1"
        assert m5_refreshed.status == MatchStatus.PLAYING.value

    def test_ranked_mode_assigns_tables_by_classification_order(
        self, db_session, players
    ):
        """A turno 1 concluso, i tavoli vanno in ordine di lista ai match
        con i giocatori meglio piazzati: T1 al match di A (1°), T2 al match
        di C (2°), T3 al match di E (3°)."""
        gara = self._make_gara(db_session, ranked=True)
        self._round1_completed(db_session, gara, players)
        m4, m5, m6 = self._round2_pending(db_session, gara, players)

        assigned = TableAssignmentService.assign_available_tables(gara.id)

        assert assigned == 3
        assert db_session.get(Match, m5.id).table_assignment == "T1"  # con A
        assert db_session.get(Match, m6.id).table_assignment == "T2"  # con C
        assert db_session.get(Match, m4.id).table_assignment == "T3"  # con E

    def test_ranked_mode_freed_table_goes_to_best_ranked_waiting(
        self, db_session, players
    ):
        """Con più match che tavoli, il tavolo che si libera a metà turno va
        subito al match in attesa col giocatore meglio piazzato."""
        gara = self._make_gara(db_session, ranked=True, tables=("T1", "T2"))
        self._round1_completed(db_session, gara, players)
        m4, m5, m6 = self._round2_pending(db_session, gara, players)

        assert TableAssignmentService.assign_available_tables(gara.id) == 2
        assert db_session.get(Match, m5.id).table_assignment == "T1"
        assert db_session.get(Match, m6.id).table_assignment == "T2"
        assert db_session.get(Match, m4.id).table_assignment is None

        # m6 termina: il T2 liberato va a m4 (unico in attesa)
        m6_refreshed = db_session.get(Match, m6.id)
        m6_refreshed.player1_score = 1
        m6_refreshed.player2_score = 4
        m6_refreshed.status = MatchStatus.COMPLETED.value
        db_session.commit()

        TableAssignmentService.release_and_reassign_table(m6.id)

        m4_refreshed = db_session.get(Match, m4.id)
        assert m4_refreshed.table_assignment == "T2"
        assert m4_refreshed.status == MatchStatus.PLAYING.value

    def test_ranked_mode_round_one_assigns_in_match_order(self, db_session, players):
        """Al turno 1 non esiste classifica: l'assegnazione segue l'ordine
        dei match come oggi."""
        gara = self._make_gara(db_session, ranked=True)
        a, b, c, d, e, f = players
        m1 = self._add_match(db_session, gara, 1, a, b)
        m2 = self._add_match(db_session, gara, 1, c, d)
        m3 = self._add_match(db_session, gara, 1, e, f)

        assigned = TableAssignmentService.assign_available_tables(gara.id)

        assert assigned == 3
        assert db_session.get(Match, m1.id).table_assignment == "T1"
        assert db_session.get(Match, m2.id).table_assignment == "T2"
        assert db_session.get(Match, m3.id).table_assignment == "T3"
