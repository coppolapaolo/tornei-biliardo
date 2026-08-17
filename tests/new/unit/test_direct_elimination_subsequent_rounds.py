"""Turni >= 2 dell'eliminazione diretta: si legge il tabellone (Step 5).

Il bug da cui è partita tutta l'analisi stava qui: i vincitori venivano
riaccoppiati nell'ordine di ritorno della query (`pop(0), pop(0)`). Non era un
ordine casuale ma uno **sistematicamente sbagliato**, perché i match del turno 1
vengono inseriti prima i bye e poi le coppie: al turno 2 tutti i giocatori
usciti dai bye — cioè le teste di serie — si incontravano fra loro.

Quello che deve valere ora:

1. il vincitore dello slot `2j` incontra quello dello slot `2j+1`, qualunque sia
   l'ordine di inserimento dei match a DB;
2. i bye del turno 1 sono nodi pieni e alimentano il turno 2 come tutti gli altri;
3. i pairing generati portano le coordinate del nodo che occuperanno;
4. le gare senza coordinate (iniziate prima di questa modifica) continuano a
   comportarsi come prima, con un warning;
5. un tabellone incoerente è un errore, non un turno silenziosamente storto.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest

from models.competition.models import Gara
from models.match.models import Match
from models.matchmaking.strategies.direct_elimination import (
    DirectEliminationStrategy,
)
from models.status_enum import GaraStatus, MatchStatus

pytestmark = pytest.mark.unit


def _make_gara(db_session, rounds_count: int = 3) -> Gara:
    count = db_session.query(Gara).count()
    gara = Gara(
        name=f"DE bracket {count + 1}",
        number=count + 1,
        date=date.today(),
        distance=5,
        discipline="9_ball",
        matchmaking_strategy="direct_elimination",
        status=GaraStatus.PLAYING.value,
        is_race_to=True,
        rounds_count=rounds_count,
    )
    db_session.add(gara)
    db_session.flush()
    return gara


def _node(
    db_session,
    gara: Gara,
    *,
    round_number: int,
    slot: int,
    winner,
    loser=None,
    bracket_round=None,
    bracket_type: str | None = "W",
    status: str = MatchStatus.CLOSED_UNILATERALLY.value,
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
        bracket_round=round_number if bracket_round is None else bracket_round,
        bracket_slot=slot,
    )
    db_session.add(match)
    db_session.flush()
    return match


def _pairs(pairings):
    return [tuple(p.players) for p in pairings]


class TestAccoppiamentoPerSlot:
    def test_i_vincitori_seguono_gli_slot_non_l_ordine_di_query(
        self, db_session, isolated_players
    ):
        """Il caso che il vecchio codice sbagliava sempre.

        Tabellone da 8 con 3 bye: i bye vengono inseriti per primi, come fa
        `create_matches_from_pairings`. Con `pop(0), pop(0)` i tre teste di
        serie uscite dai bye si sarebbero incontrate fra loro al turno 2.
        """
        gara = _make_gara(db_session)
        p = isolated_players[:8]

        # Ordine di inserimento deliberatamente "sbagliato": prima i bye
        # (slot 0, 2, 3), poi l'unico match vero (slot 1).
        _node(db_session, gara, round_number=1, slot=0, winner=p[0])
        _node(db_session, gara, round_number=1, slot=2, winner=p[1])
        _node(db_session, gara, round_number=1, slot=3, winner=p[2])
        _node(db_session, gara, round_number=1, slot=1, winner=p[3], loser=p[4])

        strategy = DirectEliminationStrategy()
        pairings = strategy._generate_round_pairings(gara, 2)

        # slot 0 vs slot 1, slot 2 vs slot 3 — non "i tre bye fra loro".
        assert _pairs(pairings) == [(p[0].id, p[3].id), (p[1].id, p[2].id)]

    def test_bye_e_vincitori_si_mescolano_correttamente(
        self, db_session, isolated_players
    ):
        """Chi esce da un bye avanza come chiunque altro."""
        gara = _make_gara(db_session)
        p = isolated_players[:8]

        _node(db_session, gara, round_number=1, slot=0, winner=p[0])  # bye
        _node(db_session, gara, round_number=1, slot=1, winner=p[1], loser=p[2])
        _node(db_session, gara, round_number=1, slot=2, winner=p[3], loser=p[4])
        _node(db_session, gara, round_number=1, slot=3, winner=p[5], loser=p[6])

        strategy = DirectEliminationStrategy()
        pairings = strategy._generate_round_pairings(gara, 2)

        assert _pairs(pairings) == [(p[0].id, p[1].id), (p[3].id, p[5].id)]

    def test_coordinate_propagate_al_turno_successivo(
        self, db_session, isolated_players
    ):
        gara = _make_gara(db_session)
        p = isolated_players[:8]
        for slot in range(4):
            _node(
                db_session,
                gara,
                round_number=1,
                slot=slot,
                winner=p[2 * slot],
                loser=p[2 * slot + 1],
            )

        strategy = DirectEliminationStrategy()
        pairings = strategy._generate_round_pairings(gara, 2)

        assert [p_.bracket_type for p_ in pairings] == ["W", "W"]
        assert [p_.bracket_round for p_ in pairings] == [2, 2]
        assert [p_.bracket_slot for p_ in pairings] == [0, 1]
        assert all(p_.round_number == 2 for p_ in pairings)

    def test_semifinali_verso_finale(self, db_session, isolated_players):
        """Un turno di due nodi ne produce uno solo, con slot 0."""
        gara = _make_gara(db_session)
        p = isolated_players[:8]
        for slot in range(4):
            _node(
                db_session,
                gara,
                round_number=1,
                slot=slot,
                winner=p[2 * slot],
                loser=p[2 * slot + 1],
            )
        _node(db_session, gara, round_number=2, slot=0, winner=p[0], loser=p[2])
        _node(db_session, gara, round_number=2, slot=1, winner=p[4], loser=p[6])

        strategy = DirectEliminationStrategy()
        pairings = strategy._generate_round_pairings(gara, 3)

        assert _pairs(pairings) == [(p[0].id, p[4].id)]
        assert pairings[0].bracket_slot == 0
        assert pairings[0].bracket_round == 3

    def test_nessun_bye_oltre_il_primo_turno(self, db_session, isolated_players):
        """Invariante: nel winners bracket i bye stanno solo al turno 1.

        Discende dal dimensionamento (Step 4): `S` è la potenza di 2
        *immediatamente* superiore agli iscritti, quindi i buchi sono meno
        della metà degli slot e ogni nodo del turno 1 produce un vincitore.
        """
        gara = _make_gara(db_session)
        p = isolated_players[:8]
        _node(db_session, gara, round_number=1, slot=0, winner=p[0])
        _node(db_session, gara, round_number=1, slot=1, winner=p[1])
        _node(db_session, gara, round_number=1, slot=2, winner=p[2], loser=p[3])
        _node(db_session, gara, round_number=1, slot=3, winner=p[4], loser=p[5])

        strategy = DirectEliminationStrategy()
        pairings = strategy._generate_round_pairings(gara, 2)

        assert not any(p_.is_bye for p_ in pairings)


class TestFineDelTabellone:
    def test_dopo_la_finale_nessun_accoppiamento(self, db_session, isolated_players):
        """Turno vuoto significa "tabellone esaurito", non errore."""
        gara = _make_gara(db_session, rounds_count=2)
        p = isolated_players[:4]
        _node(db_session, gara, round_number=1, slot=0, winner=p[0], loser=p[1])
        _node(db_session, gara, round_number=1, slot=1, winner=p[2], loser=p[3])
        _node(db_session, gara, round_number=2, slot=0, winner=p[0], loser=p[2])

        strategy = DirectEliminationStrategy()
        assert strategy._generate_round_pairings(gara, 3) == []

    def test_turno_precedente_inesistente(self, db_session, isolated_players):
        gara = _make_gara(db_session)
        strategy = DirectEliminationStrategy()
        assert strategy._generate_round_pairings(gara, 2) == []


class TestGateDiCompletezza:
    def test_turno_incompleto_non_genera_nulla(self, db_session, isolated_players):
        gara = _make_gara(db_session)
        p = isolated_players[:4]
        _node(db_session, gara, round_number=1, slot=0, winner=p[0], loser=p[1])
        pending = Match(
            gara_id=gara.id,
            player1_id=p[2].id,
            player2_id=p[3].id,
            round_number=1,
            is_bye=False,
            status=MatchStatus.PLAYING.value,
            match_distance=5,
            bracket_type="W",
            bracket_round=1,
            bracket_slot=1,
        )
        db_session.add(pending)
        db_session.flush()

        strategy = DirectEliminationStrategy()
        assert strategy._generate_round_pairings(gara, 2) == []

    def test_validated_conta_come_concluso(self, db_session, isolated_players):
        gara = _make_gara(db_session)
        p = isolated_players[:4]
        _node(
            db_session,
            gara,
            round_number=1,
            slot=0,
            winner=p[0],
            loser=p[1],
            status=MatchStatus.CONFIRMED_BY_BOTH.value,
        )
        _node(db_session, gara, round_number=1, slot=1, winner=p[2], loser=p[3])

        strategy = DirectEliminationStrategy()
        assert _pairs(strategy._generate_round_pairings(gara, 2)) == [
            (p[0].id, p[2].id)
        ]


class TestRamoLegacy:
    """Gare iniziate prima della persistenza del tabellone."""

    def test_senza_coordinate_si_torna_al_comportamento_vecchio(
        self, db_session, isolated_players, caplog
    ):
        gara = _make_gara(db_session)
        p = isolated_players[:8]
        for index, (winner, loser) in enumerate(
            [(p[0], p[1]), (p[2], p[3]), (p[4], p[5]), (p[6], p[7])]
        ):
            _node(
                db_session,
                gara,
                round_number=1,
                slot=None,  # type: ignore[arg-type]
                winner=winner,
                loser=loser,
                bracket_type=None,
            )

        strategy = DirectEliminationStrategy()
        with caplog.at_level(logging.WARNING):
            pairings = strategy._generate_round_pairings(gara, 2)

        # Ordine di query: accoppiamento a coppie consecutive, come prima.
        assert _pairs(pairings) == [(p[0].id, p[2].id), (p[4].id, p[6].id)]
        # Nessuna coordinata inventata a metà gara: il tabellone non c'è mai
        # stato e dichiararlo adesso sarebbe una bugia.
        assert all(p_.bracket_slot is None for p_ in pairings)
        assert any("legacy" in record.message for record in caplog.records)

    def test_coordinate_parziali_contano_come_assenti(
        self, db_session, isolated_players
    ):
        """Basta un nodo senza slot perché il turno non sia un alimentatore."""
        gara = _make_gara(db_session)
        p = isolated_players[:8]
        _node(db_session, gara, round_number=1, slot=0, winner=p[0], loser=p[1])
        _node(
            db_session,
            gara,
            round_number=1,
            slot=None,  # type: ignore[arg-type]
            winner=p[2],
            loser=p[3],
            bracket_type=None,
        )

        strategy = DirectEliminationStrategy()
        pairings = strategy._generate_round_pairings(gara, 2)

        assert _pairs(pairings) == [(p[0].id, p[2].id)]
        assert pairings[0].bracket_slot is None

    def test_legacy_dispari_produce_un_bye(self, db_session, isolated_players):
        """Il vecchio comportamento includeva il bye di parità: resta."""
        gara = _make_gara(db_session)
        p = isolated_players[:6]
        for winner, loser in [(p[0], p[1]), (p[2], p[3]), (p[4], p[5])]:
            _node(
                db_session,
                gara,
                round_number=1,
                slot=None,  # type: ignore[arg-type]
                winner=winner,
                loser=loser,
                bracket_type=None,
            )

        strategy = DirectEliminationStrategy()
        pairings = strategy._generate_round_pairings(gara, 2)

        assert len(pairings) == 2
        assert pairings[-1].is_bye
        assert pairings[-1].players == (p[4].id,)


class TestTabelloneIncoerente:
    def test_slot_mancante_e_un_errore(self, db_session, isolated_players):
        """Un buco negli alimentatori non deve produrre un turno storto."""
        gara = _make_gara(db_session)
        p = isolated_players[:8]
        # Tabellone da 8 (4 nodi al turno 1) ma il turno 2 ne ha uno solo.
        for slot in range(4):
            _node(
                db_session,
                gara,
                round_number=1,
                slot=slot,
                winner=p[2 * slot],
                loser=p[2 * slot + 1],
            )
        _node(db_session, gara, round_number=2, slot=0, winner=p[0], loser=p[2])

        strategy = DirectEliminationStrategy()
        with pytest.raises(ValueError, match="Tabellone incoerente"):
            strategy._generate_round_pairings(gara, 3)

    def test_match_concluso_senza_vincitore(self, db_session, isolated_players):
        gara = _make_gara(db_session)
        p = isolated_players[:4]
        _node(db_session, gara, round_number=1, slot=0, winner=p[0], loser=p[1])
        orphan = Match(
            gara_id=gara.id,
            player1_id=p[2].id,
            player2_id=p[3].id,
            round_number=1,
            is_bye=False,
            status=MatchStatus.CLOSED_UNILATERALLY.value,
            match_distance=5,
            bracket_type="W",
            bracket_round=1,
            bracket_slot=1,
        )
        db_session.add(orphan)
        db_session.flush()

        strategy = DirectEliminationStrategy()
        with pytest.raises(ValueError, match="senza vincitore"):
            strategy._generate_round_pairings(gara, 2)
