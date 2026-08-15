"""Regression per i rilievi del test manuale in produzione del 2026-06-10.

1. Card "In diretta ora" (guest): l'icona accanto a "Ai tavoli adesso" era
   una racchetta da ping pong (fa-table-tennis-paddle-ball) invece della
   biglia da biliardo (fa-8-ball, convenzione UI_CONVENTIONS.md).
2. Tavoli liberati: con i turni pre-generati (strategia random) il pull di
   assign_available_tables avviava match anche 2+ turni avanti, spalmando i
   giocatori su troppi turni e lasciando tavoli inutilizzabili. Regola: si
   attiva solo fino al turno immediatamente successivo a quello corrente.
3. Vista mobile admin/gara: i turni attivi erano in ordine inverso (turno 3
   in alto col turno 2 ancora da refertare). L'azionabile va prima: ordine
   crescente come nella vista desktop (_gara_matches.html).
"""

from datetime import date
from types import SimpleNamespace

import pytest
from flask import render_template

from models import BilliardHall, Gara, Match, User
from models.match.table_assignment_service import TableAssignmentService
from models.status_enum import Discipline, GaraStatus, MatchStatus


@pytest.mark.unit
class TestIndexLiveIconRegression:
    """Rilievo 1: icona biliardo, non ping pong, in 'Ai tavoli adesso'."""

    def _live_card(self):
        gara = SimpleNamespace(
            id=1,
            name="Gara Test",
            discipline="8_ball",
            location="Sala Prova",
        )
        live_match = SimpleNamespace(
            table="Tavolo A",
            is_trio=False,
            player1="Alice",
            player1_score=2,
            player2="Bob",
            player2_score=1,
        )
        return SimpleNamespace(
            gara=gara,
            campionato=None,
            current_round=1,
            rounds_count=3,
            active_count=4,
            live_matches=[live_match],
        )

    def test_ai_tavoli_adesso_non_usa_icone_di_altri_sport(self, app):
        """Il rilievo era la racchetta da ping pong su una card di biliardo.

        Il redesign 7c ha poi tolto le icone decorative dalla card e scrive la
        disciplina a parole, quindi le due `fa-8-ball` di allora non ci sono
        piu'. L'invariante che vale ancora e' quello: mai l'icona di un altro
        sport. La presenza della sezione e' asserita perche' altrimenti un
        template vuoto passerebbe per costruzione.
        """
        with app.test_request_context("/"):
            html = render_template(
                "components/_index_live.html", live_garas=[self._live_card()]
            )
        assert "Ai tavoli adesso" in html
        assert "table-tennis" not in html
        assert "ping-pong" not in html


@pytest.mark.unit
class TestNextRoundOnlyTableAssignment:
    """Rilievo 2: i tavoli liberi attivano match solo fino al turno corrente+1."""

    @pytest.fixture
    def venue(self, db_session):
        venue = BilliardHall(
            name="Sala Rilievi", number_of_tables=3, is_active=True, verified=True
        )
        venue.set_table_names(["Tavolo A", "Tavolo B", "Tavolo C"])
        db_session.add(venue)
        db_session.commit()
        return venue

    @pytest.fixture
    def gara(self, db_session, venue):
        gara = Gara(
            number=1,
            name="Gara Random Multi-Turno",
            date=date.today(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=5,
            location=venue.name,
            matchmaking_strategy="random",
            status=GaraStatus.PLAYING.value,
            current_round=1,
            rounds_count=3,
            min_participants=6,
        )
        db_session.add(gara)
        db_session.commit()
        return gara

    @pytest.fixture
    def players(self, db_session):
        players = []
        for i in range(6):
            user = User(
                username=f"rilievi_p{i}",
                email=f"rilievi_p{i}@test.com",
                password_hash="test",
            )
            db_session.add(user)
            players.append(user)
        db_session.commit()
        return players

    def _match(self, db_session, gara, round_number, p1, p2, **kwargs):
        match = Match(
            gara_id=gara.id,
            round_number=round_number,
            player1_id=p1.id,
            player2_id=p2.id,
            status=kwargs.pop("status", MatchStatus.PENDING.value),
            **kwargs,
        )
        db_session.add(match)
        db_session.commit()
        return match

    def test_no_activation_beyond_next_round(self, db_session, gara, players):
        """Turno 1 ancora in gioco: un match del turno 3 NON parte, anche se
        i suoi giocatori e un tavolo sono liberi."""
        p = players
        # Turno 1: un match ai tavoli, uno concluso
        self._match(
            db_session,
            gara,
            1,
            p[0],
            p[1],
            status=MatchStatus.PLAYING.value,
            table_assignment="Tavolo A",
        )
        self._match(
            db_session,
            gara,
            1,
            p[2],
            p[3],
            status=MatchStatus.COMPLETED.value,
            winner_id=p[2].id,
        )
        # Turno 2: bloccato (p0 e' ai tavoli nel turno 1)
        blocked = self._match(db_session, gara, 2, p[0], p[4])
        # Turno 3: giocatori liberi — ma e' 2 turni avanti
        too_far = self._match(db_session, gara, 3, p[2], p[3])

        assigned = TableAssignmentService.assign_available_tables(gara.id)

        assert assigned == 0
        assert db_session.get(Match, too_far.id).status == MatchStatus.PENDING.value
        assert db_session.get(Match, too_far.id).table_assignment is None
        assert db_session.get(Match, blocked.id).status == MatchStatus.PENDING.value

    def test_next_round_match_can_start(self, db_session, gara, players):
        """Il turno immediatamente successivo invece puo' partire subito."""
        p = players
        self._match(
            db_session,
            gara,
            1,
            p[0],
            p[1],
            status=MatchStatus.PLAYING.value,
            table_assignment="Tavolo A",
        )
        next_round = self._match(db_session, gara, 2, p[2], p[3])
        too_far = self._match(db_session, gara, 3, p[4], p[5])

        assigned = TableAssignmentService.assign_available_tables(gara.id)

        assert assigned == 1
        assert db_session.get(Match, next_round.id).status == MatchStatus.PLAYING.value
        assert db_session.get(Match, next_round.id).table_assignment is not None
        assert db_session.get(Match, too_far.id).status == MatchStatus.PENDING.value

    def test_cap_advances_when_round_finishes(self, db_session, gara, players):
        """Chiuso il turno 1, il turno corrente diventa il 2: il turno 3
        torna eleggibile (corrente+1)."""
        p = players
        self._match(
            db_session,
            gara,
            1,
            p[0],
            p[1],
            status=MatchStatus.COMPLETED.value,
            winner_id=p[0].id,
        )
        # Turno 2: uno ai tavoli, uno bloccato (p0 occupato)
        self._match(
            db_session,
            gara,
            2,
            p[0],
            p[5],
            status=MatchStatus.PLAYING.value,
            table_assignment="Tavolo A",
        )
        self._match(db_session, gara, 2, p[0], p[4])
        eligible = self._match(db_session, gara, 3, p[2], p[3])

        assigned = TableAssignmentService.assign_available_tables(gara.id)

        assert assigned == 1
        assert db_session.get(Match, eligible.id).status == MatchStatus.PLAYING.value


@pytest.mark.unit
class TestMobileRoundOrderingRegression:
    """Rilievo 3: in mobile i turni attivi vanno in ordine crescente
    (azionabile prima), come nella vista desktop."""

    def test_active_rounds_ascending_in_mobile_cards(self, db_session, app):
        p = []
        for i in range(4):
            user = User(
                username=f"mobile_p{i}",
                email=f"mobile_p{i}@test.com",
                password_hash="test",
            )
            db_session.add(user)
            p.append(user)
        gara = Gara(
            number=1,
            name="Gara Ordine Mobile",
            date=date.today(),
            discipline=Discipline.EIGHT_BALL.value,
            distance=5,
            matchmaking_strategy="random",
            status=GaraStatus.PLAYING.value,
            current_round=2,
            rounds_count=3,
            min_participants=4,
        )
        db_session.add(gara)
        db_session.commit()

        matches = []
        # Turno 1 concluso; turno 2 con risultati da inserire; turno 3 ai tavoli
        for round_number, status in (
            (1, MatchStatus.COMPLETED.value),
            (2, MatchStatus.PLAYING.value),
            (3, MatchStatus.PLAYING.value),
        ):
            match = Match(
                gara_id=gara.id,
                round_number=round_number,
                player1_id=p[0].id,
                player2_id=p[1].id,
                status=status,
            )
            db_session.add(match)
            matches.append(match)
        db_session.commit()

        with app.test_request_context("/"):
            html = render_template(
                "components/_match_cards_mobile.html",
                gara=gara,
                matches=matches,
                all_matches=matches,
                user_can_manage=False,
                user_inscription=None,
            )

        turno2 = html.index("Turno 2")
        turno3 = html.index("Turno 3")
        assert turno2 < turno3, "il turno azionabile piu' basso va mostrato prima"
