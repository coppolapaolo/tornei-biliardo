"""Doppio KO giocato per intero: winners, losers, ripescaggi e finale (Step 7).

Copre US-14 end-to-end. Quello che interessa non è il punteggio ma la
**topologia**: chi perde una volta ricompare nel losers bracket al turno
giusto, chi perde due volte sparisce, chi ha ricevuto un bye non genera un
perdente fantasma, e la finale mette di fronte i due campioni.

Con i bye il losers bracket si buca, ed è il caso interessante: 9, 11 e 13
iscritti su un tabellone da 16 danno 7, 5 e 3 bye. A 8 esatti non ci sono bye
e quindi nemmeno buchi da propagare.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Dict, List, Tuple

import pytest

from models import Gara, Match, User
from models.base import utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.match.services import RackService
from models.status_enum import MatchStatus
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


def _make_players(db_session, count: int) -> List[User]:
    batch = str(uuid.uuid4())[:8]
    players = []
    for index in range(count):
        player = User(
            username=f"dk_{index}_{batch}",
            email=f"dk_{index}_{batch}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        players.append(player)
    db_session.add_all(players)
    db_session.commit()
    return players


def _make_gara(db_session, players: List[User]) -> Gara:
    batch = str(uuid.uuid4())[:8]
    director = User(
        username=f"dkdir_{batch}",
        email=f"dkdir_{batch}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("director123")
    db_session.add(director)
    db_session.flush()

    count = db_session.query(Gara).count()
    gara = Gara(
        director_id=director.id,
        number=count + 1,
        name=f"DK {batch}",
        date=date.today() + timedelta(days=7),
        discipline="9_ball",
        distance=2,
        is_race_to=True,
        # Stima da max_participants (2k+1 su 16 posti); il sorteggio la
        # riscrive sugli iscritti effettivi.
        rounds_count=9,
        min_participants=8,
        max_participants=16,
        matchmaking_strategy="double_knockout",
        first_round_policy="random",
    )
    db_session.add(gara)
    db_session.commit()

    InscriptionService.open_inscriptions(
        gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
    )
    for player in players:
        InscriptionService.inscribe_user(player.id, gara.id)
    db_session.commit()
    return gara


def _play_round(db_session, gara_id: int, round_number: int, winner=None) -> None:
    """Chiude i match del turno; per default vince `player1`.

    Deterministico di proposito. Con il default, nella finale vince il campione
    del winners bracket (che è `player1` per convenzione di seat) e la gara si
    chiude senza bella; `winner` permette di ribaltarla per far scattare il
    bracket reset.
    """
    pick = winner or (lambda match: match.player1_id)
    matches = Match.query.filter_by(gara_id=gara_id, round_number=round_number).all()
    for match in matches:
        if match.is_bye or MatchStatus.is_finished(match.status):
            continue
        winner_id = pick(match)
        for _ in range(match.match_distance):
            RackService.add_rack_with_score_update(
                match_id=match.id,
                winner_id=winner_id,
                reported_by_id=winner_id,
                validated_by_admin=True,
            )
        db_session.refresh(match)
        assert MatchStatus.is_finished(match.status)
    db_session.commit()


def _nodes(gara_id: int) -> Dict[Tuple, Match]:
    return {
        (m.bracket_type, m.bracket_round, m.bracket_slot): m
        for m in Match.query.filter_by(gara_id=gara_id).all()
    }


def _losses(gara_id: int) -> Dict[int, int]:
    losses: Dict[int, int] = {}
    for match in Match.query.filter_by(gara_id=gara_id).all():
        if match.is_bye or not match.winner_id:
            continue
        loser = (
            match.player1_id
            if match.winner_id == match.player2_id
            else match.player2_id
        )
        if loser:
            losses[loser] = losses.get(loser, 0) + 1
    return losses


def _play_to_the_end(db_session, gara: Gara) -> int:
    """Gioca la gara fino a esaurimento e ritorna l'ultimo turno con match."""
    ultimo = 1
    for round_number in range(2, gara.rounds_count + 1):
        _play_round(db_session, gara.id, round_number - 1)
        _assert_no_zombie(gara.id)
        RoundService.start_next_round(gara.id, round_number)
        if Match.query.filter_by(gara_id=gara.id, round_number=round_number).count():
            ultimo = round_number
        else:
            # Turno vuoto = tabellone esaurito. Non è un errore: la bella si
            # materializza solo se il campione del losers vince la finale.
            break
    _play_round(db_session, gara.id, ultimo)
    return ultimo


def _assert_no_zombie(gara_id: int) -> None:
    """Chi ha perso due volte non compare più in un match successivo."""
    eliminati_al: Dict[int, int] = {}
    conteggio: Dict[int, int] = {}
    matches = sorted(
        Match.query.filter_by(gara_id=gara_id).all(),
        key=lambda m: (m.round_number, m.id),
    )
    for match in matches:
        for player in (match.player1_id, match.player2_id):
            if player and player in eliminati_al:
                assert eliminati_al[player] >= match.round_number, (
                    f"il giocatore {player} gioca al turno {match.round_number} "
                    f"dopo la seconda sconfitta (turno {eliminati_al[player]})"
                )
        if match.is_bye or not match.winner_id:
            continue
        loser = (
            match.player1_id
            if match.winner_id == match.player2_id
            else match.player2_id
        )
        if loser:
            conteggio[loser] = conteggio.get(loser, 0) + 1
            if conteggio[loser] == 2:
                eliminati_al[loser] = match.round_number


class TestTabellonePieno:
    def test_otto_giocatori_dal_sorteggio_alla_finale(self, db_session):
        """8 iscritti: 7 turni, nessun bye, 6 nodi di losers bracket."""
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, players)

        RoundService.start_first_round(gara.id)
        db_session.refresh(gara)
        assert gara.rounds_count == 7, "2k + 1 con k = 3"

        ultimo = _play_to_the_end(db_session, gara)

        nodi = _nodes(gara.id)
        winners = {k for k in nodi if k[0] == "W"}
        losers = {k for k in nodi if k[0] == "L"}

        assert len(winners) == 7, "S - 1 nodi nel winners bracket"
        assert len(losers) == 6, "S - 2 nodi nel losers bracket"
        assert ("GF", 1, 0) in nodi
        assert ultimo == 6, "la finale è al turno 2k"

        # Il campione del winners bracket vince anche la finale (player1
        # vince sempre): niente bella, e il turno 7 resta vuoto senza errori.
        assert not Match.query.filter_by(gara_id=gara.id, round_number=7).count()

        # Esattamente un giocatore chiude con meno di due sconfitte.
        losses = _losses(gara.id)
        imbattuti = [p.id for p in players if losses.get(p.id, 0) < 2]
        assert imbattuti == [nodi[("GF", 1, 0)].winner_id]

    def test_il_losers_bracket_parte_al_turno_2(self, db_session):
        """Dal turno 2 ogni turno contiene due blocchi affiancati."""
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, players)

        RoundService.start_first_round(gara.id)
        _play_round(db_session, gara.id, 1)
        RoundService.start_next_round(gara.id, 2)

        secondo = Match.query.filter_by(gara_id=gara.id, round_number=2).all()
        tipi = {m.bracket_type for m in secondo}
        assert tipi == {"W", "L"}
        assert sum(1 for m in secondo if m.bracket_type == "W") == 2
        assert sum(1 for m in secondo if m.bracket_type == "L") == 2

        # I quattro perdenti del turno 1 sono esattamente i giocatori di L1.
        perdenti = {
            (m.player1_id if m.winner_id == m.player2_id else m.player2_id)
            for m in Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        }
        in_losers = set()
        for match in secondo:
            if match.bracket_type == "L":
                in_losers |= {match.player1_id, match.player2_id}
        assert in_losers == perdenti


class TestBuchiNelLosersBracket:
    @pytest.mark.parametrize("n_players", [9, 11, 13])
    def test_i_bye_non_generano_perdenti_fantasma(self, db_session, n_players):
        """Tabellone da 16 con 7, 5 e 3 bye: il losers bracket si buca."""
        players = _make_players(db_session, n_players)
        gara = _make_gara(db_session, players)

        RoundService.start_first_round(gara.id)
        db_session.refresh(gara)
        assert gara.rounds_count == 9, "2k + 1 con k = 4"

        byes = Match.query.filter_by(gara_id=gara.id, round_number=1, is_bye=True)
        assert byes.count() == 16 - n_players

        _play_round(db_session, gara.id, 1)
        RoundService.start_next_round(gara.id, 2)

        primo_turno = {
            m.bracket_slot: m
            for m in Match.query.filter_by(gara_id=gara.id, round_number=1).all()
        }
        losers = {
            m.bracket_slot: m
            for m in Match.query.filter_by(
                gara_id=gara.id, round_number=2, bracket_type="L"
            ).all()
        }

        # Il nodo L1 slot s è alimentato dai perdenti dei nodi W1 2s e 2s+1:
        # due match veri → partita, uno solo → bye, nessuno → niente nodo.
        for slot in range(4):
            alimentatori = sum(
                0 if primo_turno[2 * slot + offset].is_bye else 1 for offset in (0, 1)
            )
            if alimentatori == 0:
                assert slot not in losers
            elif alimentatori == 1:
                assert losers[slot].is_bye
            else:
                assert not losers[slot].is_bye

    def test_gara_con_bye_giocata_fino_in_fondo(self, db_session):
        """Il tabellone bucato arriva comunque a una finale sensata."""
        players = _make_players(db_session, 11)
        gara = _make_gara(db_session, players)

        RoundService.start_first_round(gara.id)
        ultimo = _play_to_the_end(db_session, gara)

        nodi = _nodes(gara.id)
        assert ("GF", 1, 0) in nodi, "la finale si materializza anche con i buchi"
        assert ultimo == 8, "finale al turno 2k con k = 4"

        losses = _losses(gara.id)
        imbattuti = [p.id for p in players if losses.get(p.id, 0) < 2]
        assert imbattuti == [nodi[("GF", 1, 0)].winner_id]


class TestBracketReset:
    """US-15: la bella, quando la finale la vince il ripescato."""

    def _fino_alla_finale(self, db_session, gara: Gara) -> Match:
        """Gioca fino alla finale esclusa e la restituisce."""
        for round_number in range(2, 7):
            _play_round(db_session, gara.id, round_number - 1)
            RoundService.start_next_round(gara.id, round_number)
        return Match.query.filter_by(gara_id=gara.id, bracket_type="GF").one()

    def test_vince_il_ripescato_si_gioca_la_bella(self, db_session):
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, players)
        RoundService.start_first_round(gara.id)

        finale = self._fino_alla_finale(db_session, gara)
        campione_winners, campione_losers = finale.player1_id, finale.player2_id

        # Ribalta la finale: vince chi arrivava dal losers bracket.
        _play_round(db_session, gara.id, 6, winner=lambda m: m.player2_id)
        RoundService.start_next_round(gara.id, 7)

        bella = Match.query.filter_by(gara_id=gara.id, round_number=7).all()
        assert len(bella) == 1
        assert bella[0].bracket_type == "GFR"
        assert {bella[0].player1_id, bella[0].player2_id} == {
            campione_winners,
            campione_losers,
        }

    def test_vince_l_imbattuto_la_gara_finisce(self, db_session):
        """Il turno della bella resta vuoto, e avviarlo non solleva."""
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, players)
        RoundService.start_first_round(gara.id)

        self._fino_alla_finale(db_session, gara)
        _play_round(db_session, gara.id, 6)

        total, *_ = RoundService.start_next_round(gara.id, 7)

        assert total == 0
        assert not Match.query.filter_by(gara_id=gara.id, round_number=7).count()


class TestTurniRimastiIndietro:
    """Il numero di turni non deve impedire il sorteggio che lo corregge.

    Regressione da una segnalazione dal vivo: una gara creata col wizard si
    portava dietro `rounds_count=3` (il default del form, che per il doppio KO
    non vuol dire nulla) e l'avvio del primo turno veniva **rifiutato** con
    "richiede N turni, la gara ne ha 3". Il valore lo riscrive il sorteggio
    stesso sugli iscritti effettivi, quindi la validazione bloccava proprio
    l'azione che l'avrebbe sistemato — e il form non chiede piu' quel campo,
    quindi non c'era nemmeno un modo di correggerlo a mano.
    """

    def test_il_sorteggio_riscrive_i_turni_rimasti_indietro(self, db_session):
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, players)

        gara.rounds_count = 3  # com'era prima che il form smettesse di chiederlo
        db_session.commit()

        RoundService.start_first_round(gara.id)

        db_session.refresh(gara)
        assert gara.rounds_count == 7  # 2*log2(8) + 1
        assert Match.query.filter_by(gara_id=gara.id, round_number=1).count() == 4

    def test_a_tabellone_estratto_resta_un_errore(self, db_session):
        """Dopo il sorteggio i nodi esistono: un valore troppo basso e' un bug.

        Qui non c'e' piu' niente da riscrivere, quindi la validazione torna a
        essere quello che dice di essere.
        """
        from models.matchmaking.bootstrap import get_registry

        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, players)
        RoundService.start_first_round(gara.id)

        gara.rounds_count = 3
        db_session.commit()

        result = get_registry().get("double_knockout").validate(gara)

        assert not result.ok
        assert any("turni" in error for error in result.errors)
