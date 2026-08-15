"""Bella del doppio KO e finalina 3°/4° posto (Step 8, US-7 e US-15).

Due nodi che esistono solo a certe condizioni, ed è la condizione a essere
interessante:

- la **bella** si gioca solo se la finale l'ha vinta chi arrivava dal losers
  bracket. Il doppio KO promette due sconfitte prima dell'eliminazione, quindi
  chi arriva imbattuto non può uscire per una sola partita. Se invece vince
  lui, il turno della bella resta vuoto — e un turno vuoto non è un errore;
- la **finalina** si gioca solo se il director l'ha chiesta, e occupa lo stesso
  turno della finale invece di aggiungerne uno.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

import pytest

from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.matchmaking.strategies.direct_elimination import DirectEliminationStrategy
from models.matchmaking.strategies.double_knockout import DoubleKnockoutStrategy
from models.status_enum import GaraStatus, MatchStatus

pytestmark = pytest.mark.unit


def _make_gara(db_session, strategy: str, **kwargs) -> Gara:
    count = db_session.query(Gara).count()
    gara = Gara(
        name=f"{strategy} {count + 1}",
        number=count + 1,
        date=date.today(),
        distance=5,
        discipline="9_ball",
        matchmaking_strategy=strategy,
        status=GaraStatus.PLAYING.value,
        is_race_to=True,
        rounds_count=kwargs.pop("rounds_count", 7),
        **kwargs,
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
    bracket_type: str,
    bracket_round: int,
    slot: int,
    player1,
    player2: Optional[object] = None,
    winner=None,
) -> Match:
    """Nodo concluso. `player2=None` è un bye; `winner` default: player1."""
    is_bye = player2 is None
    champion = winner if winner is not None else player1
    match = Match(
        gara_id=gara.id,
        player1_id=player1.id,
        player2_id=None if is_bye else player2.id,  # type: ignore[union-attr]
        round_number=round_number,
        is_bye=is_bye,
        status=MatchStatus.VALIDATED.value,
        winner_id=champion.id,
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


def _dk_fino_alla_finale(db_session, gara: Gara, p) -> None:
    """Tabellone da 4 giocato fino alla finale (esclusa): k = 2, GF al turno 4.

    p0 vince il winners bracket, p2 risale dal losers.
    """
    _node(
        db_session,
        gara,
        round_number=1,
        bracket_type="W",
        bracket_round=1,
        slot=0,
        player1=p[0],
        player2=p[3],
    )
    _node(
        db_session,
        gara,
        round_number=1,
        bracket_type="W",
        bracket_round=1,
        slot=1,
        player1=p[1],
        player2=p[2],
    )
    _node(
        db_session,
        gara,
        round_number=2,
        bracket_type="W",
        bracket_round=2,
        slot=0,
        player1=p[0],
        player2=p[1],
    )
    _node(
        db_session,
        gara,
        round_number=2,
        bracket_type="L",
        bracket_round=1,
        slot=0,
        player1=p[2],
        player2=p[3],
    )
    _node(
        db_session,
        gara,
        round_number=3,
        bracket_type="L",
        bracket_round=2,
        slot=0,
        player1=p[2],
        player2=p[1],
    )


class TestBellaDelDoppioKO:
    def test_vince_il_ripescato_si_gioca_la_bella(self, db_session, isolated_players):
        """Chi arrivava imbattuto non può uscire per una sola sconfitta."""
        gara = _make_gara(db_session, "double_knockout")
        p = isolated_players[:4]
        _inscribe(db_session, gara, p)
        _dk_fino_alla_finale(db_session, gara, p)

        # Finale: player1 = campione winners (p0), player2 = campione losers
        # (p2). Vince p2, quindi ora hanno una sconfitta a testa.
        _node(
            db_session,
            gara,
            round_number=4,
            bracket_type="GF",
            bracket_round=1,
            slot=0,
            player1=p[0],
            player2=p[2],
            winner=p[2],
        )

        pairings = DoubleKnockoutStrategy()._generate_round_pairings(gara, 5)

        assert len(pairings) == 1
        bella = pairings[0]
        assert bella.bracket_type == "GFR"
        assert set(bella.players) == {p[0].id, p[2].id}
        assert not bella.is_bye

    def test_vince_l_imbattuto_nessun_turno_aggiuntivo(
        self, db_session, isolated_players
    ):
        """Zero pairing significa "torneo concluso", non errore."""
        gara = _make_gara(db_session, "double_knockout")
        p = isolated_players[:4]
        _inscribe(db_session, gara, p)
        _dk_fino_alla_finale(db_session, gara, p)

        _node(
            db_session,
            gara,
            round_number=4,
            bracket_type="GF",
            bracket_round=1,
            slot=0,
            player1=p[0],
            player2=p[2],
            winner=p[0],
        )

        assert DoubleKnockoutStrategy()._generate_round_pairings(gara, 5) == []

    def test_la_convenzione_di_seat_e_cio_che_decide(
        self, db_session, isolated_players
    ):
        """Invertire i seat della finale invertirebbe l'esito della bella.

        È l'unico punto in cui la correttezza dipende da un ordine di
        costruzione, quindi va detto a voce alta: qui si costruisce una finale
        con i seat scambiati e si verifica che la decisione cambi. Serve a far
        fallire il test se qualcuno "normalizza" l'ordine dei giocatori.
        """
        gara = _make_gara(db_session, "double_knockout")
        p = isolated_players[:4]
        _inscribe(db_session, gara, p)
        _dk_fino_alla_finale(db_session, gara, p)

        # Seat scambiati: il campione del losers come player1.
        _node(
            db_session,
            gara,
            round_number=4,
            bracket_type="GF",
            bracket_round=1,
            slot=0,
            player1=p[2],
            player2=p[0],
            winner=p[2],
        )

        # Stesso vincitore del primo test, esito opposto: la strategia guarda
        # il seat, non lo storico delle sconfitte.
        assert DoubleKnockoutStrategy()._generate_round_pairings(gara, 5) == []

    def test_senza_finale_nessuna_bella(self, db_session, isolated_players):
        gara = _make_gara(db_session, "double_knockout")
        p = isolated_players[:4]
        _inscribe(db_session, gara, p)
        _dk_fino_alla_finale(db_session, gara, p)

        assert DoubleKnockoutStrategy()._generate_round_pairings(gara, 5) == []

    def test_la_finalina_non_si_applica_al_doppio_ko(
        self, db_session, isolated_players
    ):
        """Il terzo posto lo decide già il losers bracket (US-7)."""
        gara = _make_gara(db_session, "double_knockout", third_place_match=True)
        p = isolated_players[:8]
        _inscribe(db_session, gara, p)

        result = DoubleKnockoutStrategy()._validate_strategy_specific(gara)

        assert result["errors"] == []
        assert any("3°/4°" in w for w in result["warnings"])


class TestFinalinaEliminazioneDiretta:
    def _semifinali(self, db_session, gara, p):
        """Tabellone da 4: il turno 1 sono le semifinali."""
        _node(
            db_session,
            gara,
            round_number=1,
            bracket_type="W",
            bracket_round=1,
            slot=0,
            player1=p[0],
            player2=p[1],
        )
        _node(
            db_session,
            gara,
            round_number=1,
            bracket_type="W",
            bracket_round=1,
            slot=1,
            player1=p[2],
            player2=p[3],
        )

    def test_attiva_due_match_all_ultimo_turno(self, db_session, isolated_players):
        """Finale e finalina insieme, senza allungare il tabellone."""
        gara = _make_gara(
            db_session, "direct_elimination", rounds_count=2, third_place_match=True
        )
        p = isolated_players[:4]
        self._semifinali(db_session, gara, p)

        pairings = DirectEliminationStrategy()._generate_round_pairings(gara, 2)

        per_tipo = {pairing.bracket_type: pairing for pairing in pairings}
        assert set(per_tipo) == {"W", "3P"}
        assert per_tipo["W"].players == (p[0].id, p[2].id), "i due vincitori"
        assert per_tipo["3P"].players == (p[1].id, p[3].id), "i due sconfitti"
        # Stesso turno di gara e stesso livello di tabellone della finale.
        assert per_tipo["3P"].round_number == per_tipo["W"].round_number == 2
        assert per_tipo["3P"].bracket_round == per_tipo["W"].bracket_round == 2

    def test_spenta_solo_la_finale(self, db_session, isolated_players):
        """Il default non produce nodi in più."""
        gara = _make_gara(db_session, "direct_elimination", rounds_count=2)
        p = isolated_players[:4]
        self._semifinali(db_session, gara, p)

        pairings = DirectEliminationStrategy()._generate_round_pairings(gara, 2)

        assert [pairing.bracket_type for pairing in pairings] == ["W"]

    def test_solo_all_ultimo_turno(self, db_session, isolated_players):
        """Ai quarti la finalina non c'entra nulla."""
        gara = _make_gara(
            db_session, "direct_elimination", rounds_count=3, third_place_match=True
        )
        p = isolated_players[:8]
        for slot in range(4):
            _node(
                db_session,
                gara,
                round_number=1,
                bracket_type="W",
                bracket_round=1,
                slot=slot,
                player1=p[2 * slot],
                player2=p[2 * slot + 1],
            )

        # Turno 2: sono le semifinali, non la finale.
        pairings = DirectEliminationStrategy()._generate_round_pairings(gara, 2)
        assert [pairing.bracket_type for pairing in pairings] == ["W", "W"]

    def test_semifinale_vinta_senza_giocare(self, db_session, isolated_players, caplog):
        """Un bye non produce uno sconfitto: niente finalina a un giocatore."""
        import logging

        gara = _make_gara(
            db_session, "direct_elimination", rounds_count=2, third_place_match=True
        )
        p = isolated_players[:4]
        _node(
            db_session,
            gara,
            round_number=1,
            bracket_type="W",
            bracket_round=1,
            slot=0,
            player1=p[0],
        )
        _node(
            db_session,
            gara,
            round_number=1,
            bracket_type="W",
            bracket_round=1,
            slot=1,
            player1=p[2],
            player2=p[3],
        )

        with caplog.at_level(logging.WARNING):
            pairings = DirectEliminationStrategy()._generate_round_pairings(gara, 2)

        assert [pairing.bracket_type for pairing in pairings] == ["W"]
        assert any("finalina" in record.message for record in caplog.records)
