"""Doppio KO: gli accoppiamenti si leggono dal tabellone persistito (Step 7).

Storia di questo file. Nasce come regressione di un bug del 2026-06-09: la
distinzione winners/losers bracket si basava su `Match.notes`, una colonna che
su `Match` **non esiste** (c'è solo su `Set`), quindi il round 2 sollevava
`AttributeError`; e le query filtravano `status="completed"` ignorando i match
`validated`, cioè quelli confermati bilateralmente. Il fix di allora derivava
il bracket dallo storico delle sconfitte.

Lo Step 7 elimina anche quella derivazione: ogni nodo ha coordinate
(`bracket_type`/`bracket_round`/`bracket_slot`) e ogni giocatore ha una
destinazione calcolata. Le tre verifiche originali restano — sono le stesse
domande, poste a un'implementazione diversa — e si aggiungono le proprietà
nuove: la propagazione dei buchi nel losers bracket, la convenzione di seat
della finale e il rifiuto esplicito delle gare senza tabellone.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

import pytest

from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.matchmaking.strategies.double_knockout import DoubleKnockoutStrategy
from models.status_enum import GaraStatus, MatchStatus

pytestmark = pytest.mark.unit


def _make_dk_gara(db_session) -> Gara:
    count = db_session.query(Gara).count()
    gara = Gara(
        name=f"DK gara {count + 1}",
        number=count + 1,
        date=date.today(),
        distance=5,
        discipline="9_ball",
        matchmaking_strategy="double_knockout",
        status=GaraStatus.PLAYING.value,
        is_race_to=True,
        rounds_count=7,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _inscribe(db_session, gara: Gara, players: List) -> None:
    for p in players:
        db_session.add(Inscription(gara_id=gara.id, user_id=p.id))
    db_session.flush()


def _node(
    db_session,
    gara: Gara,
    *,
    round_number: int,
    bracket_type: Optional[str],
    bracket_round: Optional[int],
    slot: Optional[int],
    winner,
    loser=None,
    status: str = MatchStatus.CONFIRMED_BY_BOTH.value,
) -> Match:
    """Nodo di tabellone già concluso. `loser=None` significa bye."""
    is_bye = loser is None
    match = Match(
        gara_id=gara.id,
        player1_id=winner.id,
        player2_id=None if is_bye else loser.id,
        round_number=round_number,
        is_bye=is_bye,
        status=status,
        winner_id=winner.id,
        player1_score=5,
        player2_score=0 if is_bye else 3,
        match_distance=5,
        bracket_type=bracket_type,
        bracket_round=bracket_round,
        bracket_slot=slot,
    )
    db_session.add(match)
    db_session.flush()
    return match


def _pairs(pairings):
    return {frozenset(p.players) for p in pairings if len(p.players) == 2}


def _by_coordinate(pairings):
    return {(p.bracket_type, p.bracket_round, p.bracket_slot): p for p in pairings}


class TestSchedule:
    """Le tre domande della regressione originale, sul nuovo impianto."""

    def test_round2_separa_winners_e_losers(self, db_session, isolated_players):
        """4 giocatori: al turno 2 si giocano `W2` e `L1` affiancati.

        Prima del fix del 2026-06 questo sollevava `AttributeError` su
        `Match.notes`; con lo Step 7 le coordinate lo rendono un lookup.
        """
        gara = _make_dk_gara(db_session)
        p = isolated_players[:4]
        _inscribe(db_session, gara, p)

        _node(
            db_session,
            gara,
            round_number=1,
            bracket_type="W",
            bracket_round=1,
            slot=0,
            winner=p[0],
            loser=p[3],
        )
        _node(
            db_session,
            gara,
            round_number=1,
            bracket_type="W",
            bracket_round=1,
            slot=1,
            winner=p[1],
            loser=p[2],
        )

        pairings = DoubleKnockoutStrategy()._generate_round_pairings(gara, 2)

        assert _pairs(pairings) == {
            frozenset((p[0].id, p[1].id)),  # W2: i due vincitori
            frozenset((p[2].id, p[3].id)),  # L1: i due perdenti
        }
        coordinate = _by_coordinate(pairings)
        assert set(coordinate) == {("W", 2, 0), ("L", 1, 0)}

    def test_round3_ripesca_il_sopravvissuto_del_losers(
        self, db_session, isolated_players
    ):
        """`L2` accoppia il sopravvissuto con chi è appena sceso dal winners."""
        gara = _make_dk_gara(db_session)
        p = isolated_players[:4]
        _inscribe(db_session, gara, p)

        _node(
            db_session,
            gara,
            round_number=1,
            bracket_type="W",
            bracket_round=1,
            slot=0,
            winner=p[0],
            loser=p[3],
        )
        _node(
            db_session,
            gara,
            round_number=1,
            bracket_type="W",
            bracket_round=1,
            slot=1,
            winner=p[1],
            loser=p[2],
        )
        _node(
            db_session,
            gara,
            round_number=2,
            bracket_type="W",
            bracket_round=2,
            slot=0,
            winner=p[0],
            loser=p[1],
        )
        _node(
            db_session,
            gara,
            round_number=2,
            bracket_type="L",
            bracket_round=1,
            slot=0,
            winner=p[2],
            loser=p[3],
        )

        pairings = DoubleKnockoutStrategy()._generate_round_pairings(gara, 3)

        # p1 scende dal winners, p2 è il sopravvissuto del losers.
        assert _pairs(pairings) == {frozenset((p[1].id, p[2].id))}
        assert list(_by_coordinate(pairings)) == [("L", 2, 0)]

    def test_completed_vale_quanto_validated(self, db_session, isolated_players):
        """Entrambi gli stati finali sbloccano il turno successivo."""
        gara = _make_dk_gara(db_session)
        p = isolated_players[:4]
        _inscribe(db_session, gara, p)

        for slot, (winner, loser) in enumerate([(p[0], p[3]), (p[1], p[2])]):
            _node(
                db_session,
                gara,
                round_number=1,
                bracket_type="W",
                bracket_round=1,
                slot=slot,
                winner=winner,
                loser=loser,
                status=MatchStatus.CLOSED_UNILATERALLY.value,
            )

        pairings = DoubleKnockoutStrategy()._generate_round_pairings(gara, 2)

        assert _pairs(pairings) == {
            frozenset((p[0].id, p[1].id)),
            frozenset((p[2].id, p[3].id)),
        }

    def test_turno_incompleto_non_genera_nulla(self, db_session, isolated_players):
        gara = _make_dk_gara(db_session)
        p = isolated_players[:4]
        _inscribe(db_session, gara, p)

        _node(
            db_session,
            gara,
            round_number=1,
            bracket_type="W",
            bracket_round=1,
            slot=0,
            winner=p[0],
            loser=p[3],
        )
        db_session.add(
            Match(
                gara_id=gara.id,
                player1_id=p[1].id,
                player2_id=p[2].id,
                round_number=1,
                is_bye=False,
                status=MatchStatus.PLAYING.value,
                match_distance=5,
                bracket_type="W",
                bracket_round=1,
                bracket_slot=1,
            )
        )
        db_session.flush()

        assert DoubleKnockoutStrategy()._generate_round_pairings(gara, 2) == []


class TestFinale:
    def test_convenzione_di_seat(self, db_session, isolated_players):
        """`player1` = campione winners, `player2` = campione losers.

        Non è cosmesi: è così che lo Step 8 riconosce il bracket reset. Se
        qualcuno invertisse i due seat, la bella scatterebbe esattamente nei
        casi sbagliati — e nessun altro test se ne accorgerebbe.
        """
        gara = _make_dk_gara(db_session)
        p = isolated_players[:4]
        _inscribe(db_session, gara, p)

        _node(
            db_session,
            gara,
            round_number=1,
            bracket_type="W",
            bracket_round=1,
            slot=0,
            winner=p[0],
            loser=p[3],
        )
        _node(
            db_session,
            gara,
            round_number=1,
            bracket_type="W",
            bracket_round=1,
            slot=1,
            winner=p[1],
            loser=p[2],
        )
        _node(
            db_session,
            gara,
            round_number=2,
            bracket_type="W",
            bracket_round=2,
            slot=0,
            winner=p[0],
            loser=p[1],
        )
        _node(
            db_session,
            gara,
            round_number=2,
            bracket_type="L",
            bracket_round=1,
            slot=0,
            winner=p[2],
            loser=p[3],
        )
        _node(
            db_session,
            gara,
            round_number=3,
            bracket_type="L",
            bracket_round=2,
            slot=0,
            winner=p[2],
            loser=p[1],
        )

        # Tabellone da 4: k = 2, la finale è al turno 2k = 4.
        pairings = DoubleKnockoutStrategy()._generate_round_pairings(gara, 4)

        assert len(pairings) == 1
        finale = pairings[0]
        assert finale.bracket_type == "GF"
        assert finale.players == (p[0].id, p[2].id)


class TestPropagazioneDeiBuchi:
    """Un bye del turno 1 non produce perdenti: lo slot a valle resta vuoto."""

    def _winners_first_round(self, db_session, gara, players, byes):
        """Turno 1 su tabellone da 16: `byes` = slot senza avversario."""
        used = 0
        for slot in range(8):
            if slot in byes:
                _node(
                    db_session,
                    gara,
                    round_number=1,
                    bracket_type="W",
                    bracket_round=1,
                    slot=slot,
                    winner=players[used],
                )
                used += 1
            else:
                _node(
                    db_session,
                    gara,
                    round_number=1,
                    bracket_type="W",
                    bracket_round=1,
                    slot=slot,
                    winner=players[used],
                    loser=players[used + 1],
                )
                used += 2

    def test_due_bye_adiacenti_non_materializzano_il_nodo(
        self, db_session, isolated_players
    ):
        """Zero alimentatori: il nodo `L1` non viene creato affatto."""
        gara = _make_dk_gara(db_session)
        players = isolated_players[:12]
        _inscribe(db_session, gara, players)
        # Slot 0 e 1 entrambi bye → il nodo L1 slot 0 non ha perdenti.
        self._winners_first_round(db_session, gara, players, byes={0, 1, 2, 3})

        pairings = DoubleKnockoutStrategy()._generate_round_pairings(gara, 2)
        losers = {
            p.bracket_slot for p in pairings if p.bracket_type == "L"
        }  # slot materializzati

        assert 0 not in losers, "nessun perdente: il nodo non va materializzato"
        assert 1 not in losers
        assert losers == {2, 3}, "i nodi alimentati da match veri restano"

    def test_un_solo_alimentatore_diventa_un_bye(self, db_session, isolated_players):
        """Un alimentatore su due: il ripescato passa il turno senza giocare."""
        gara = _make_dk_gara(db_session)
        players = isolated_players[:12]
        _inscribe(db_session, gara, players)
        # Slot 0 bye, slot 1 match → il nodo L1 slot 0 ha un solo perdente.
        self._winners_first_round(db_session, gara, players, byes={0, 2, 4, 6})

        pairings = DoubleKnockoutStrategy()._generate_round_pairings(gara, 2)
        losers = {p.bracket_slot: p for p in pairings if p.bracket_type == "L"}

        assert set(losers) == {0, 1, 2, 3}
        assert all(p.is_bye for p in losers.values())
        assert all(len(p.players) == 1 for p in losers.values())


class TestGareSenzaTabellone:
    def test_errore_esplicito(self, db_session, isolated_players):
        """Niente ramo legacy: il vecchio accoppiamento non era deterministico.

        A differenza dell'eliminazione diretta, qui non c'è un "comportamento
        precedente" da preservare — il losers bracket veniva accoppiato da un
        `list(set(...))`, cioè in ordine arbitrario. Ricostruire un tabellone
        su turni giocati così produrrebbe un tabellone falso.
        """
        gara = _make_dk_gara(db_session)
        p = isolated_players[:4]
        _inscribe(db_session, gara, p)

        for winner, loser in [(p[0], p[3]), (p[1], p[2])]:
            _node(
                db_session,
                gara,
                round_number=1,
                bracket_type=None,
                bracket_round=None,
                slot=None,
                winner=winner,
                loser=loser,
            )

        with pytest.raises(ValueError, match="coordinate di tabellone"):
            DoubleKnockoutStrategy()._generate_round_pairings(gara, 2)


class TestConteggioTurni:
    @pytest.mark.parametrize(
        "n_players,expected",
        [(8, 6), (9, 8), (16, 8), (17, 10)],
    )
    def test_i_turni_programmati_sono_due_k(self, n_players, expected):
        """`2k` sul **tabellone**, non sugli iscritti: 9 giocatori danno k=4.

        Diceva `2k + 1`, contando la bella fra i turni certi: la gara ne
        dichiarava uno che meta' delle volte non si gioca, e l'interfaccia lo
        annunciava come "in corso" pur essendo senza partite (issue #239).
        L'induzione che fissa il numero sta in
        `test_doppio_ko_conteggio_turni.py`.
        """
        assert DoubleKnockoutStrategy().get_total_rounds_needed(n_players) == expected

    def test_pavimento_a_otto(self):
        """Sotto gli 8 il tabellone non si stringe: il formato non lo permette."""
        strategy = DoubleKnockoutStrategy()
        assert strategy.get_bracket_size(8) == 8
        assert strategy.min_players == 8
