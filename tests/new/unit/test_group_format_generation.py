"""Formula FISBB: generazione dei gironi e del tabellone finale (Step 12b).

La gara ha due fasi dentro di sé, e i test seguono quella struttura:

1. **turno 1** — un tabellone per girone, giocati in parallelo, ciascuno coi
   propri bye e col proprio `bracket_group`;
2. **turni 2..2w-1** — il doppio KO del girone, *troncato*: l'ultimo round di
   winners non si gioca (i due imbattuti sono già qualificati) e i round di
   recupero si fermano a `L_{2w-2}`;
3. **turno 2w** — il sorteggio del tabellone finale fra i `4g` qualificati,
   2 diretti e 2 ripescati per girone;
4. **da lì in poi** — eliminazione diretta pura, che la strategia delega al
   codice che già la sa leggere.

Il caso di riferimento è quello del regolamento: `w = 2`, gironi da 8. Con 20
iscritti fa 3 gironi (7 · 7 · 6), 12 qualificati e un tabellone finale da 16
con 4 bye — cioè il caso della verifica del piano.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence

import pytest

from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.matchmaking.bracket import (
    group_format_total_rounds,
    meet_round,
    standard_bracket_order,
)
from models.matchmaking.strategies.base import Pairing
from models.matchmaking.strategies.double_knockout import DoubleKnockoutStrategy
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.unit

FISBB_ROUNDS = 2  # `w` del regolamento: gironi da 8


# ── Impianto ──────────────────────────────────────────────────────────────


def _players(db_session, count: int) -> List:
    """`count` giocatori nuovi: la fixture condivisa ne offre solo 12."""
    from models import User

    base = db_session.query(User).count()
    users = []
    for index in range(count):
        user = User(
            username=f"fisbb_{base + index}",
            email=f"fisbb_{base + index}@test.com",
            role=UserRole.PLAYER.value,
        )
        user.set_password("player123")
        users.append(user)
    db_session.add_all(users)
    db_session.flush()
    return users


def _make_gara(db_session, players: Sequence, *, group_rounds=FISBB_ROUNDS) -> Gara:
    count = db_session.query(Gara).count()
    gara = Gara(
        name=f"FISBB {count + 1}",
        number=count + 1,
        date=date.today(),
        distance=5,
        discipline="9_ball",
        matchmaking_strategy="double_knockout",
        status=GaraStatus.PLAYING.value,
        is_race_to=True,
        rounds_count=99,  # stima larga: il sorteggio la riscrive
        max_participants=64,
        draw_seed=7,
        double_ko_rounds=group_rounds,
    )
    db_session.add(gara)
    db_session.flush()
    for player in players:
        db_session.add(Inscription(gara_id=gara.id, user_id=player.id))
    db_session.flush()
    db_session.refresh(gara)
    return gara


def _squadre(db_session, gara: Gara, count: int) -> List[int]:
    """`count` squadre nell'elenco della gara, e i loro id."""
    from models.squadra.models import Squadra, normalize_squadra_name

    rows = []
    for index in range(count):
        name = f"Circolo {gara.id}-{index}"
        rows.append(
            Squadra(
                name=name,
                normalized_name=normalize_squadra_name(name),
                gara_id=gara.id,
            )
        )
    db_session.add_all(rows)
    db_session.flush()
    return [row.id for row in rows]


def _persist(db_session, gara: Gara, pairings: Sequence[Pairing]) -> List[Match]:
    """Materializza i pairing come nodi conclusi: vince sempre il primo.

    "Vince il primo" è arbitrario ma deterministico, ed è tutto ciò che serve:
    questi test verificano *chi incontra chi*, non chi vince.
    """
    matches = []
    for pairing in pairings:
        winner = pairing.players[0]
        loser = pairing.players[1] if len(pairing.players) > 1 else None
        match = Match(
            gara_id=gara.id,
            player1_id=winner,
            player2_id=loser,
            round_number=pairing.round_number,
            is_bye=pairing.is_bye,
            status=MatchStatus.CONFIRMED_BY_BOTH.value,
            winner_id=winner,
            player1_score=5,
            player2_score=0 if loser is None else 3,
            match_distance=5,
            bracket_type=pairing.bracket_type,
            bracket_round=pairing.bracket_round,
            bracket_slot=pairing.bracket_slot,
            bracket_group=pairing.bracket_group,
        )
        db_session.add(match)
        matches.append(match)
    db_session.flush()
    return matches


def _play_through(db_session, gara: Gara, last_round: int) -> Dict[int, List[Pairing]]:
    """Gioca la gara fino a `last_round` incluso, restituendo i pairing."""
    strategy = DoubleKnockoutStrategy()
    history: Dict[int, List[Pairing]] = {}
    for round_number in range(1, last_round + 1):
        pairings = list(strategy._generate_round_pairings(gara, round_number))
        history[round_number] = pairings
        _persist(db_session, gara, pairings)
    return history


def _by_group(pairings: Sequence[Pairing]) -> Dict[Optional[int], List[Pairing]]:
    grouped: Dict[Optional[int], List[Pairing]] = {}
    for pairing in pairings:
        grouped.setdefault(pairing.bracket_group, []).append(pairing)
    return grouped


def _coordinates(pairings: Sequence[Pairing]) -> set:
    return {(p.bracket_type, p.bracket_round, p.bracket_slot) for p in pairings}


def _people(pairings: Sequence[Pairing]) -> set:
    return {player for p in pairings for player in p.players}


# ── 1. Turno 1: un tabellone per girone ───────────────────────────────────


class TestPrimoTurno:
    def test_venti_iscritti_fanno_tre_gironi(self, db_session):
        """20 su gironi da 8: 3 gironi da 7, 7 e 6, e nessuno resta fuori."""
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)

        pairings = DoubleKnockoutStrategy()._generate_round_pairings(gara, 1)
        grouped = _by_group(pairings)

        assert sorted(grouped) == [0, 1, 2]
        assert sorted(len(_people(nodes)) for nodes in grouped.values()) == [6, 7, 7]
        assert _people(pairings) == {p.id for p in players}

    def test_ogni_girone_e_un_tabellone_da_otto(self, db_session):
        """Quattro nodi per girone, slot 0..3, e i bye ai posti dei buchi."""
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)

        grouped = _by_group(DoubleKnockoutStrategy()._generate_round_pairings(gara, 1))

        for group, nodes in grouped.items():
            assert _coordinates(nodes) == {("W", 1, slot) for slot in range(4)}, group
            byes = [node for node in nodes if node.is_bye]
            assert len(byes) == 8 - len(_people(nodes))

    def test_nessuno_gioca_in_due_gironi(self, db_session):
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)

        grouped = _by_group(DoubleKnockoutStrategy()._generate_round_pairings(gara, 1))
        occurrences = [
            player for nodes in grouped.values() for player in _people(nodes)
        ]

        assert len(occurrences) == len(set(occurrences)) == 20

    def test_i_turni_si_fissano_sugli_iscritti(self, db_session):
        """`rounds_count` passa dalla stima larga ai turni veri: 3 + 4 = 7.

        La stima in creazione viene da `max_participants`; qui il dato è certo.
        Nel formato a gironi il conto **non** si può leggere dal numero di nodi
        del turno 1 come nel tabellone unico: i gironi sono più d'uno e hanno
        buchi propri.
        """
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)
        strategy = DoubleKnockoutStrategy()

        pairings = strategy._generate_round_pairings(gara, 1)
        strategy._apply_side_effects(pairings, gara, 1)

        assert gara.rounds_count == group_format_total_rounds(20, FISBB_ROUNDS) == 7

    def test_un_solo_girone_quando_bastano_otto(self, db_session):
        players = _players(db_session, 8)
        gara = _make_gara(db_session, players)

        grouped = _by_group(DoubleKnockoutStrategy()._generate_round_pairings(gara, 1))

        assert list(grouped) == [0]
        assert len(grouped[0]) == 4
        assert not any(node.is_bye for node in grouped[0])


# ── 2. La fase a gironi è un doppio KO troncato ───────────────────────────


class TestFaseAGironi:
    def test_turno_due_affianca_winners_e_recupero(self, db_session):
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)
        history = _play_through(db_session, gara, 2)

        grouped = _by_group(history[2])
        assert sorted(grouped) == [0, 1, 2]
        for group, nodes in grouped.items():
            coordinates = _coordinates(nodes)
            assert ("W", 2, 0) in coordinates and ("W", 2, 1) in coordinates, group
            assert {c for c in coordinates if c[0] == "L"} <= {
                ("L", 1, 0),
                ("L", 1, 1),
            }, group

    def test_l_ultimo_turno_e_il_recupero(self, db_session):
        """Turno 3: solo `L2`, e **nessun** `W3`.

        È il troncamento: i due imbattuti del girone sono già qualificati e
        farli giocare fra loro non aggiungerebbe informazione.
        """
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)
        history = _play_through(db_session, gara, 3)

        assert all(p.bracket_type == "L" for p in history[3])
        assert {p.bracket_round for p in history[3]} == {2}
        assert not any(
            p.bracket_type == "W" and p.bracket_round == 3
            for pairings in history.values()
            for p in pairings
        )

    def test_i_gironi_non_si_mescolano(self, db_session):
        """Chi gioca nel girone `g` incontra solo gente del girone `g`."""
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)
        history = _play_through(db_session, gara, 3)

        rosters = {
            group: _people(nodes) for group, nodes in _by_group(history[1]).items()
        }
        for round_number in (2, 3):
            for pairing in history[round_number]:
                assert set(pairing.players) <= rosters[pairing.bracket_group]

    def test_un_girone_incompleto_ferma_tutti(self, db_session):
        """I gironi giocano in parallelo: il turno dopo aspetta l'ultimo match."""
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)
        strategy = DoubleKnockoutStrategy()

        pairings = strategy._generate_round_pairings(gara, 1)
        matches = _persist(db_session, gara, pairings)
        matches[-1].status = MatchStatus.PLAYING.value
        db_session.flush()

        assert strategy._generate_round_pairings(gara, 2) == []


# ── 3. I qualificati ──────────────────────────────────────────────────────


class TestQualificati:
    def test_quattro_per_girone_due_imbattuti_e_due_ripescati(self, db_session):
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)
        _play_through(db_session, gara, 3)

        final_round = DoubleKnockoutStrategy()._generate_round_pairings(gara, 4)
        qualified = _people(final_round)

        assert len(qualified) == 12
        # Chi si qualifica ha al massimo una sconfitta; chi esce ne ha due.
        losses = _losses_by_player(db_session, gara)
        assert all(losses.get(player, 0) <= 1 for player in qualified)
        eliminated = set(losses) - qualified
        assert eliminated and all(losses[player] == 2 for player in eliminated)

    def test_i_due_imbattuti_sono_i_primi_seed_del_girone(self, db_session):
        """L'ordine dentro il girone è il merito: prima i diretti, poi i ripescati."""
        players = _players(db_session, 8)
        gara = _make_gara(db_session, players)
        _play_through(db_session, gara, 3)

        strategy = DoubleKnockoutStrategy()
        played = strategy._played_matches(gara, 4)
        assert played is not None
        nodes = strategy._nodes_by_coordinate(gara, played)
        qualified = strategy._group_qualifiers(nodes[0], FISBB_ROUNDS)

        losses = _losses_by_player(db_session, gara)
        assert [losses.get(player, 0) for player in qualified] == [0, 0, 1, 1]


def _losses_by_player(db_session, gara: Gara) -> Dict[int, int]:
    losses: Dict[int, int] = {}
    for match in db_session.query(Match).filter_by(gara_id=gara.id).all():
        if match.is_bye or match.winner_id is None:
            continue
        for player in (match.player1_id, match.player2_id):
            if player is not None and player != match.winner_id:
                losses[player] = losses.get(player, 0) + 1
    return losses


# ── 4. Il tabellone finale ────────────────────────────────────────────────


class TestTabelloneFinale:
    def test_dodici_qualificati_su_un_tabellone_da_sedici(self, db_session):
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)
        _play_through(db_session, gara, 3)

        final_round = DoubleKnockoutStrategy()._generate_round_pairings(gara, 4)

        assert _coordinates(final_round) == {("W", 1, slot) for slot in range(8)}
        assert len([p for p in final_round if p.is_bye]) == 4
        assert all(p.bracket_group is None for p in final_round)

    def test_i_compagni_di_girone_non_si_incontrano_subito(self, db_session):
        """Il seeding da solo non basta: con 3 gironi i seed 7 e 10 sono
        complementari in un tabellone da 16. È la separazione applicata sul
        girone di provenienza a rimandare l'incontro."""
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)
        _play_through(db_session, gara, 3)

        strategy = DoubleKnockoutStrategy()
        final_round = strategy._generate_round_pairings(gara, 4)
        origin = _origin_by_player(db_session, gara)

        derby = [
            p
            for p in final_round
            if len(p.players) == 2 and origin[p.players[0]] == origin[p.players[1]]
        ]
        assert not derby, "due qualificati dello stesso girone al primo turno"

    def test_il_tabellone_finale_prosegue_da_solo(self, db_session):
        """Dal turno dopo il sorteggio è eliminazione diretta pura.

        Il vincitore del nodo `2j` incontra quello del nodo `2j+1`, e i nodi
        dei gironi — che pure hanno le stesse coordinate `(W, 1, s)` — non
        vengono scambiati per alimentatori.
        """
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)
        history = _play_through(db_session, gara, 4)

        winners = {
            p.bracket_slot: p.players[0] for p in history[4] if p.bracket_group is None
        }
        pairings = DoubleKnockoutStrategy()._generate_round_pairings(gara, 5)

        assert _coordinates(pairings) == {("W", 2, slot) for slot in range(4)}
        assert all(p.bracket_group is None for p in pairings)
        for pairing in pairings:
            slot = pairing.bracket_slot
            assert pairing.players == (winners[2 * slot], winners[2 * slot + 1])

    def test_si_arriva_alla_finale(self, db_session):
        """Sette turni in tutto, e l'ultimo è un solo match."""
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)
        history = _play_through(db_session, gara, 7)

        assert len(history[7]) == 1
        assert _coordinates(history[7]) == {("W", 4, 0)}
        assert DoubleKnockoutStrategy().total_rounds_for(gara, 20) == 7


def _origin_by_player(db_session, gara: Gara) -> Dict[int, int]:
    """Girone di provenienza di ciascun giocatore, letto dal turno 1."""
    origin: Dict[int, int] = {}
    rows = db_session.query(Match).filter_by(gara_id=gara.id, round_number=1).all()
    for match in rows:
        for player in (match.player1_id, match.player2_id):
            if player is not None:
                origin[player] = match.bracket_group
    return origin


class TestClassifica:
    def test_un_solo_vincitore_e_i_qualificati_davanti(self, db_session):
        """La classifica legge il tabellone e rispetta le due fasi.

        È il punto in cui il formato misto si vede: nel girone servono due
        sconfitte per uscire, nel tabellone finale una. Con una regola sola,
        chi si qualifica imbattuto e perde subito nel tabellone finale
        resterebbe "ancora in gioco" a gara conclusa.
        """
        from models.classification.bracket_standings import bracket_positions

        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)
        history = _play_through(db_session, gara, 7)

        qualified = _people(history[4])
        positions = bracket_positions(gara)

        assert len(positions) == 20
        assert sorted(positions.values()).count(1) == 1, "un vincitore solo"
        eliminati_nei_gironi = {p.id for p in players} - qualified
        assert max(positions[p] for p in qualified) < min(
            positions[p] for p in eliminati_nei_gironi
        )


# ── 5. Il doppio KO classico non cambia ───────────────────────────────────


class TestNonRegressione:
    def test_senza_double_ko_rounds_resta_un_tabellone_solo(self, db_session):
        """`double_ko_rounds` assente = doppio KO classico, nodi senza girone."""
        players = _players(db_session, 8)
        gara = _make_gara(db_session, players, group_rounds=None)

        pairings = DoubleKnockoutStrategy()._generate_round_pairings(gara, 1)

        assert len(pairings) == 4
        assert all(p.bracket_group is None for p in pairings)
        assert _coordinates(pairings) == {("W", 1, slot) for slot in range(4)}

    def test_lo_zero_vale_come_assente(self, db_session):
        """Un campo lasciato a 0 da una form non è un formato a gironi."""
        players = _players(db_session, 8)
        gara = _make_gara(db_session, players, group_rounds=0)

        pairings = DoubleKnockoutStrategy()._generate_round_pairings(gara, 1)

        assert all(p.bracket_group is None for p in pairings)

    def test_il_seeding_del_girone_resta_canonico(self, db_session):
        """Senza squadre né buchi il girone è l'ordine canonico del tabellone.

        Con 16 iscritti i due gironi sono pieni: ogni nodo accoppia seed
        complementari, esattamente come farebbe un tabellone da 8 a sé stante.
        """
        players = _players(db_session, 16)
        gara = _make_gara(db_session, players)
        strategy = DoubleKnockoutStrategy()

        inscriptions = strategy._seeding._active_inscriptions(gara)
        seeded = strategy._seeding._get_seeded_players(gara, inscriptions)
        grouped = _by_group(strategy._generate_round_pairings(gara, 1))

        order = standard_bracket_order(8)
        for group, nodes in grouped.items():
            roster = [player for player in seeded if player in _people(nodes)]
            expected = {
                frozenset((roster[order[2 * j] - 1], roster[order[2 * j + 1] - 1]))
                for j in range(4)
            }
            assert {frozenset(node.players) for node in nodes} == expected, group


# ── 6. Squadre ────────────────────────────────────────────────────────────


class TestSquadre:
    def test_i_compagni_finiscono_in_gironi_diversi(self, db_session):
        """Distribuirli costa zero: dentro una riga di serpentina i seed sono
        adiacenti, quindi permutarli non sposta l'equilibrio fra i gironi."""
        players = _players(db_session, 24)
        gara = _make_gara(db_session, players)
        gara.separate_teammates = True
        db_session.flush()

        # Tre squadre da 3, il resto senza squadra.
        ids = _squadre(db_session, gara, 3)
        squadre = {players[index].id: ids[index % 3] for index in range(9)}
        for inscription in gara.inscriptions:
            inscription.squadra_id = squadre.get(inscription.user_id)
        db_session.flush()

        grouped = _by_group(DoubleKnockoutStrategy()._generate_round_pairings(gara, 1))
        for team in ids:
            members = {uid for uid, value in squadre.items() if value == team}
            groups_touched = [
                group for group, nodes in grouped.items() if members & _people(nodes)
            ]
            assert len(groups_touched) == 3, f"squadra {team} ammassata"

    def test_nel_tabellone_finale_la_squadra_batte_il_girone(self, db_session):
        """Il vincolo forte è sulle squadre: il tabellone finale è a
        eliminazione diretta pura, lì un derby elimina davvero."""
        players = _players(db_session, 20)
        gara = _make_gara(db_session, players)
        gara.separate_teammates = True
        db_session.flush()
        ids = _squadre(db_session, gara, 4)
        for index, inscription in enumerate(gara.inscriptions):
            inscription.squadra_id = ids[index % 4]
        db_session.flush()

        _play_through(db_session, gara, 3)
        final_round = DoubleKnockoutStrategy()._generate_round_pairings(gara, 4)

        teams = {i.user_id: i.squadra_id for i in gara.inscriptions}
        derby = [
            p
            for p in final_round
            if len(p.players) == 2 and teams[p.players[0]] == teams[p.players[1]]
        ]
        assert not derby

    def test_dentro_il_girone_il_derby_e_tollerato(self, db_session):
        """Nel girone c'è il recupero: chi perde non è fuori, e la struttura
        del doppio KO rende l'incontro quasi impossibile da evitare. Il
        sorteggio non deve fallire per questo."""
        players = _players(db_session, 8)
        gara = _make_gara(db_session, players)
        gara.separate_teammates = True
        db_session.flush()
        (unica,) = _squadre(db_session, gara, 1)
        for inscription in gara.inscriptions:
            inscription.squadra_id = unica  # tutti della stessa squadra
        db_session.flush()

        pairings = DoubleKnockoutStrategy()._generate_round_pairings(gara, 1)

        assert len(pairings) == 4
        assert _people(pairings) == {p.id for p in players}


# ── 7. Aritmetica sotto mano ──────────────────────────────────────────────


def test_meet_round_e_coerente_col_tabellone_finale():
    """Promemoria del perché serve la separazione: 7 e 10 si incontrano subito.

    Nel tabellone canonico da 16 lo slot del seed 7 e quello del seed 10 sono
    adiacenti, cioè `meet_round` vale 1. Sono i seed che `qualifier_seeding`
    assegna al primo girone quando i gironi sono 3.
    """
    order = standard_bracket_order(16)
    assert meet_round(order.index(7), order.index(10)) == 1
