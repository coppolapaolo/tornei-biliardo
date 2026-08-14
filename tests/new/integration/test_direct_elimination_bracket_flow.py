"""Eliminazione diretta giocata per intero: gli accoppiamenti seguono il tabellone.

Copre US-12 end-to-end, dalla creazione della gara alla finale, passando per i
servizi veri (`InscriptionService`, `RoundService`, `RackService`): il turno 1
estrae il tabellone e lo persiste sui `Match`, i turni successivi lo rileggono.

L'invariante controllata a ogni turno è quella che il vecchio codice violava
sistematicamente: **il nodo `j` accoppia i vincitori dei nodi `2j` e `2j+1` del
turno precedente**. Con i bye il caso è ancora più netto — erano proprio le
teste di serie uscite dai bye a ritrovarsi tutte insieme al turno 2.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Dict, List

import pytest

from models import Gara, Inscription, Match, Squadra, User
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
            username=f"de_{index}_{batch}",
            email=f"de_{index}_{batch}@test.com",
            role=UserRole.PLAYER.value,
        )
        player.set_password("player123")
        players.append(player)
    db_session.add_all(players)
    db_session.commit()
    return players


def _make_gara(
    db_session,
    players: List[User],
    *,
    max_participants: int,
    separate_teammates: bool = False,
) -> Gara:
    """Gara a eliminazione diretta con gli iscritti già dentro.

    Il modello viene costruito a mano invece che via `GaraService`: la
    configurazione dei formati a tabellone dal form è lo Step 10, e qui
    interessa il comportamento del tabellone, non quello del parser.
    """
    batch = str(uuid.uuid4())[:8]
    director = User(
        username=f"dir_{batch}",
        email=f"dir_{batch}@test.com",
        role=UserRole.DIRECTOR.value,
    )
    director.set_password("director123")
    db_session.add(director)
    db_session.flush()

    count = db_session.query(Gara).count()
    gara = Gara(
        director_id=director.id,
        number=count + 1,
        name=f"DE {batch}",
        date=date.today() + timedelta(days=7),
        discipline="9_ball",
        distance=3,
        is_race_to=True,
        # Stima da max_participants: il sorteggio la riscrive sugli iscritti
        # effettivi (Step 4).
        rounds_count=4,
        min_participants=4,
        max_participants=max_participants,
        matchmaking_strategy="direct_elimination",
        first_round_policy="random",
        separate_teammates=separate_teammates,
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


def _round_nodes(gara_id: int, round_number: int) -> Dict[int, Match]:
    """Nodi del winners bracket di un turno, indicizzati per slot."""
    matches = Match.query.filter_by(
        gara_id=gara_id, round_number=round_number, bracket_type="W"
    ).all()
    return {m.bracket_slot: m for m in matches}


def _play_round(db_session, gara_id: int, round_number: int) -> None:
    """Chiude tutti i match del turno: vince sempre `player1`.

    Vincitore deterministico di proposito — l'oggetto del test è *chi incontra
    chi*, non il punteggio, e un esito casuale renderebbe illeggibile un
    fallimento.
    """
    matches = Match.query.filter_by(gara_id=gara_id, round_number=round_number).all()
    for match in matches:
        if match.is_bye or MatchStatus.is_finished(match.status):
            continue
        winner_id = match.player1_id
        for _ in range(match.match_distance):
            RackService.add_rack_with_score_update(
                match_id=match.id,
                winner_id=winner_id,
                reported_by_id=winner_id,
                validated_by_admin=True,
            )
        db_session.refresh(match)
        assert MatchStatus.is_finished(
            match.status
        ), f"match {match.id} non concluso: {match.status}"
    db_session.commit()


def _winner_of(match: Match) -> int:
    return match.winner_id or match.player1_id


def _assert_feeds_from_slots(gara_id: int, round_number: int) -> None:
    """Il nodo `j` accoppia i vincitori dei nodi `2j` e `2j+1`."""
    previous = _round_nodes(gara_id, round_number - 1)
    current = _round_nodes(gara_id, round_number)

    assert current, f"turno {round_number} senza nodi di tabellone"
    assert sorted(current) == list(range(len(previous) // 2))

    for slot, match in current.items():
        expected = {
            _winner_of(previous[2 * slot]),
            _winner_of(previous[2 * slot + 1]),
        }
        assert {match.player1_id, match.player2_id} == expected, (
            f"turno {round_number}, slot {slot}: attesi i vincitori degli slot "
            f"{2 * slot} e {2 * slot + 1}"
        )
        assert match.bracket_round == round_number


class TestTabelloneCompleto:
    def test_otto_giocatori_giocati_fino_in_fondo(self, db_session):
        """Tabellone pieno: 4 + 2 + 1 nodi, senza un solo bye."""
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, players, max_participants=8)

        RoundService.start_first_round(gara.id)
        db_session.refresh(gara)
        assert gara.rounds_count == 3, "8 iscritti = 3 turni"
        assert len(_round_nodes(gara.id, 1)) == 4
        assert not Match.query.filter_by(gara_id=gara.id, is_bye=True).count()

        for round_number in (2, 3):
            _play_round(db_session, gara.id, round_number - 1)
            RoundService.start_next_round(gara.id, round_number)
            _assert_feeds_from_slots(gara.id, round_number)

        _play_round(db_session, gara.id, 3)
        finale = _round_nodes(gara.id, 3)[0]
        assert finale.winner_id is not None

    def test_sedici_posti_sei_iscritti_il_tabellone_si_stringe(self, db_session):
        """Il tabellone si dimensiona sugli iscritti, non sui posti."""
        players = _make_players(db_session, 6)
        gara = _make_gara(db_session, players, max_participants=16)

        RoundService.start_first_round(gara.id)
        db_session.refresh(gara)

        assert gara.rounds_count == 3, "6 iscritti = tabellone da 8, non da 16"
        assert len(_round_nodes(gara.id, 1)) == 4
        assert Match.query.filter_by(gara_id=gara.id, is_bye=True).count() == 2

        for round_number in (2, 3):
            _play_round(db_session, gara.id, round_number - 1)
            RoundService.start_next_round(gara.id, round_number)
            _assert_feeds_from_slots(gara.id, round_number)
            assert not Match.query.filter_by(
                gara_id=gara.id, round_number=round_number, is_bye=True
            ).count(), "nel winners bracket i bye stanno solo al turno 1"


class TestByeCheAvanzano:
    @pytest.mark.parametrize("n_players", [5, 6, 7])
    def test_chi_esce_da_un_bye_incontra_il_vicino_di_tabellone(
        self, db_session, n_players
    ):
        """Il caso che il vecchio codice sbagliava sempre.

        Con `pop(0), pop(0)` sui vincitori i giocatori usciti dai bye —
        inseriti a DB prima delle coppie — si incontravano fra loro al turno 2,
        cioè esattamente le teste di serie che il seeding vuole tenere lontane.
        """
        players = _make_players(db_session, n_players)
        gara = _make_gara(db_session, players, max_participants=8)

        RoundService.start_first_round(gara.id)
        primo_turno = _round_nodes(gara.id, 1)
        byes = {
            slot: _winner_of(match)
            for slot, match in primo_turno.items()
            if match.is_bye
        }
        assert len(byes) == 8 - n_players

        _play_round(db_session, gara.id, 1)
        RoundService.start_next_round(gara.id, 2)
        _assert_feeds_from_slots(gara.id, 2)

        # Chi ha avuto il bye al nodo 0 incontra il vincitore del nodo 1, che
        # e' un match vero: e' il caso concreto del journey ("il seed 1 non
        # incontra un altro giocatore uscito da un bye"). Che poi due bye
        # possano incontrarsi piu' in basso nel tabellone — succede a n=5, dove
        # i seed 2 e 3 hanno entrambi il bye — e' il tabellone canonico, non un
        # difetto: sono gli stessi due che si incontrerebbero in semifinale.
        nodo_alto = _round_nodes(gara.id, 2)[0]
        assert byes[0] in (nodo_alto.player1_id, nodo_alto.player2_id)
        assert 1 not in byes, "il nodo 1 e' un match vero con 5, 6 o 7 iscritti"

        assert not Match.query.filter_by(
            gara_id=gara.id, round_number=2, is_bye=True
        ).count(), "nel winners bracket i bye stanno solo al turno 1"


class TestSeparazioneSquadre:
    """US-6 attraverso il flusso vero: elenco squadre, iscrizioni, sorteggio."""

    def _iscrivi_con_squadre(self, db_session, gara: Gara, players: List[User], nomi):
        """Crea l'elenco squadre della gara e lo assegna alle iscrizioni."""
        squadre = []
        for nome in nomi:
            squadra = Squadra(name=nome, gara_id=gara.id)
            db_session.add(squadra)
            squadre.append(squadra)
        db_session.flush()

        for index, player in enumerate(players):
            inscription = Inscription.query.filter_by(
                gara_id=gara.id, user_id=player.id
            ).one()
            inscription.squadra_id = squadre[index % len(squadre)].id
        db_session.commit()
        return squadre

    def test_niente_derby_al_primo_turno(self, db_session):
        """Due squadre da 4 su tabellone da 8: nessun compagno contro l'altro."""
        players = _make_players(db_session, 8)
        gara = _make_gara(
            db_session, players, max_participants=8, separate_teammates=True
        )
        self._iscrivi_con_squadre(db_session, gara, players, ["Circolo A", "Circolo B"])

        RoundService.start_first_round(gara.id)

        squadra_di = {
            i.user_id: i.squadra_id
            for i in Inscription.query.filter_by(gara_id=gara.id).all()
        }
        for match in _round_nodes(gara.id, 1).values():
            assert (
                squadra_di[match.player1_id] != squadra_di[match.player2_id]
            ), "compagni di squadra accoppiati al primo turno"

    def test_il_profilo_non_conta_dopo_l_iscrizione(self, db_session):
        """`user.squadra` precompila l'iscrizione e poi esce di scena.

        Il tabellone è persistito: cambiare la squadra a sorteggio fatto — sul
        profilo o sull'iscrizione — non sposta nessuno. È la proprietà che
        rende sensato congelare le squadre all'avvio del primo turno (US-11).
        """
        players = _make_players(db_session, 8)
        gara = _make_gara(
            db_session, players, max_participants=8, separate_teammates=True
        )
        self._iscrivi_con_squadre(db_session, gara, players, ["Circolo A", "Circolo B"])

        RoundService.start_first_round(gara.id)
        prima = {
            slot: (m.player1_id, m.player2_id)
            for slot, m in _round_nodes(gara.id, 1).items()
        }

        for player in players:
            player.squadra = "Circolo Inventato"
        db_session.commit()

        dopo = {
            slot: (m.player1_id, m.player2_id)
            for slot, m in _round_nodes(gara.id, 1).items()
        }
        assert dopo == prima

    def test_opzione_spenta_nessun_vincolo(self, db_session):
        """Il default non guarda nemmeno le squadre."""
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, players, max_participants=8)
        self._iscrivi_con_squadre(db_session, gara, players, ["Circolo A", "Circolo B"])

        RoundService.start_first_round(gara.id)

        nodi = _round_nodes(gara.id, 1)
        assert len(nodi) == 4
        assert sorted(nodi) == [0, 1, 2, 3]


class TestGareLegacy:
    def test_gara_senza_coordinate_continua_come_prima(self, db_session):
        """R1: cambiare accoppiamento a metà gara sarebbe peggio del bug."""
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, players, max_participants=8)

        RoundService.start_first_round(gara.id)
        # Simula una gara sorteggiata prima della persistenza del tabellone.
        for match in Match.query.filter_by(gara_id=gara.id, round_number=1).all():
            match.bracket_type = None
            match.bracket_round = None
            match.bracket_slot = None
        db_session.commit()

        _play_round(db_session, gara.id, 1)
        RoundService.start_next_round(gara.id, 2)

        secondo_turno = Match.query.filter_by(gara_id=gara.id, round_number=2).all()
        assert len(secondo_turno) == 2
        assert all(m.bracket_slot is None for m in secondo_turno), (
            "nessuna coordinata inventata a metà gara: quei turni non hanno "
            "mai rispettato un tabellone"
        )


class TestFinalinaTerzoQuarto:
    """US-7: la finalina occupa lo stesso turno della finale, non uno in più."""

    def test_due_match_all_ultimo_turno(self, db_session):
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, players, max_participants=8)
        gara.third_place_match = True
        db_session.commit()

        RoundService.start_first_round(gara.id)
        db_session.refresh(gara)
        assert gara.rounds_count == 3, "la finalina non aggiunge turni"

        for round_number in (2, 3):
            _play_round(db_session, gara.id, round_number - 1)
            RoundService.start_next_round(gara.id, round_number)

        ultimo = Match.query.filter_by(gara_id=gara.id, round_number=3).all()
        per_tipo = {m.bracket_type: m for m in ultimo}
        assert set(per_tipo) == {"W", "3P"}

        # I quattro protagonisti dell'ultimo turno sono i due vincitori e i
        # due sconfitti delle semifinali, senza sovrapposizioni.
        semifinali = _round_nodes(gara.id, 2)
        vincitori = {_winner_of(m) for m in semifinali.values()}
        sconfitti = {
            (m.player1_id if m.winner_id == m.player2_id else m.player2_id)
            for m in semifinali.values()
        }
        assert {per_tipo["W"].player1_id, per_tipo["W"].player2_id} == vincitori
        assert {per_tipo["3P"].player1_id, per_tipo["3P"].player2_id} == sconfitti

    def test_spenta_solo_la_finale(self, db_session):
        players = _make_players(db_session, 8)
        gara = _make_gara(db_session, players, max_participants=8)

        RoundService.start_first_round(gara.id)
        for round_number in (2, 3):
            _play_round(db_session, gara.id, round_number - 1)
            RoundService.start_next_round(gara.id, round_number)

        ultimo = Match.query.filter_by(gara_id=gara.id, round_number=3).all()
        assert [m.bracket_type for m in ultimo] == ["W"]
