"""Ciclo di vita della classifica di partenza (turno 0) tra annullamenti e reset.

La classifica di partenza risolve i parimerito dei turni successivi, quindi deve
sopravvivere agli undo che non riportano la gara alle iscrizioni:

- annullare l'avvio del turno N (N > 1)  → il seeding resta
- resettare un match di un turno passato → il seeding resta e viene riusato
- tornare in stato `inscription`         → il seeding sparisce, perché al
  riavvio gli iscritti possono essere cambiati

Copre anche le strategie senza `first_round_policy` (random, round robin), dove
l'ordine di partenza si deriva dagli accoppiamenti del primo turno.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import List

import pytest

from models import Gara, Inscription, Match, User
from models.base import utc_now
from models.classification.models import RoundClassification
from models.classification.seeding_service import SEEDING_ROUND, SeedingService
from models.competition.inscription_service import InscriptionService
from models.competition.round_manager import AdvancedRoundManager
from models.competition.round_service import RoundService
from models.competition.services import GaraService
from models.status_enum import GaraStatus, MatchStatus
from models.user.role_enum import UserRole


def _seeding_order(gara_id: int) -> List[int]:
    return [rc.user_id for rc in SeedingService.get_seeding(gara_id)]


def _complete_round(gara_id: int, round_number: int, db_session) -> None:
    """Chiude tutti i match del turno con un risultato deterministico."""
    matches = Match.query.filter_by(gara_id=gara_id, round_number=round_number).all()
    for match in matches:
        if match.is_bye:
            continue
        match.player1_score = 5
        match.player2_score = 3
        match.winner_id = match.player1_id
        match.status = MatchStatus.COMPLETED.value
        db_session.add(match)
    db_session.flush()


@pytest.mark.integration
class TestSeedingLifecycle:
    """Il turno 0 esiste esattamente finché la gara è avviata."""

    @pytest.fixture
    def director_user(self, db_session) -> User:
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()
        return director

    @pytest.fixture
    def players_8(self, db_session) -> List[User]:
        batch_id = str(uuid.uuid4())[:8]
        players = []
        for i in range(8):
            player = User(
                username=f"player_{i}_{batch_id}",
                email=f"player_{i}_{batch_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            players.append(player)
        db_session.add_all(players)
        db_session.commit()
        return players

    def _started_gara(
        self,
        director_user: User,
        players: List[User],
        matchmaking_strategy: str = "amalfi",
        classification_system: str = "WINS",
    ) -> Gara:
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name=f"Seeding {uuid.uuid4().hex[:6]}",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Seeding lifecycle",
            rounds_count=3,
            min_participants=6,
            max_participants=10,
            entry_fee=0.0,
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy=matchmaking_strategy,
            classification_system=classification_system,
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )
        InscriptionService.open_inscriptions(
            gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
        )
        for player in players:
            InscriptionService.inscribe_user(player.id, gara.id)
        RoundService.start_first_round(gara.id)
        return gara

    def test_first_round_start_persists_seeding(
        self, director_user, players_8, db_session
    ):
        """Avviare il primo turno salva la classifica di partenza."""
        gara = self._started_gara(director_user, players_8)

        seeding = SeedingService.get_seeding(gara.id)

        assert len(seeding) == 8
        assert {rc.user_id for rc in seeding} == {p.id for p in players_8}
        assert [rc.position for rc in seeding] == list(range(1, 9))
        assert all(rc.round_number == SEEDING_ROUND for rc in seeding)

    def test_initial_order_matches_seeding(self, director_user, players_8, db_session):
        """L'"Ordine sorteggio" mostrato al giocatore è la posizione di partenza reale.

        Prima veniva assegnato da uno shuffle indipendente in
        `start_first_round`, scorrelato dal seeding usato per accoppiare.
        """
        gara = self._started_gara(director_user, players_8)

        positions = SeedingService.get_seeding_positions(gara.id)
        inscriptions = Inscription.query.filter_by(gara_id=gara.id).all()

        assert inscriptions
        for inscription in inscriptions:
            assert inscription.initial_order == positions[inscription.user_id]

    def test_cancel_round_2_keeps_seeding(self, director_user, players_8, db_session):
        """Annullare l'avvio del turno 2 non tocca la classifica di partenza."""
        gara = self._started_gara(director_user, players_8)
        original = _seeding_order(gara.id)

        _complete_round(gara.id, 1, db_session)
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        RoundService.create_round_with_strategy(gara.id, 2)
        gara.current_round = 2
        db_session.flush()

        RoundService.cancel_current_round_startup(gara.id)
        db_session.flush()

        assert Match.query.filter_by(gara_id=gara.id, round_number=2).count() == 0
        assert _seeding_order(gara.id) == original

    def test_reset_match_after_undo_keeps_and_uses_seeding(
        self, director_user, players_8, db_session
    ):
        """Il ciclo completo: turno 2 annullato, match del turno 1 resettato.

        È lo scenario segnalato: si torna indietro, si cambia un risultato, e
        la classifica deve continuare a risolvere i parimerito col sorteggio
        iniziale invece di ricadere sull'ordine di registrazione.
        """
        gara = self._started_gara(director_user, players_8)
        original = _seeding_order(gara.id)

        _complete_round(gara.id, 1, db_session)
        RoundClassification.calculate_classification_after_round(gara.id, 1)
        RoundService.create_round_with_strategy(gara.id, 2)
        gara.current_round = 2
        db_session.flush()

        RoundService.cancel_current_round_startup(gara.id)
        db_session.flush()

        target = Match.query.filter_by(
            gara_id=gara.id, round_number=1, is_bye=False
        ).first()
        assert target is not None
        success, message = AdvancedRoundManager.reset_match_with_validation(target.id)
        assert success, message
        db_session.flush()

        # Il seeding è intatto...
        assert _seeding_order(gara.id) == original

        # ...ed è ancora la sorgente di `previous_position` del turno 1,
        # ricostruito da zero dal ricalcolo post-reset.
        seeding_positions = SeedingService.get_seeding_positions(gara.id)
        round1 = RoundClassification.query.filter_by(
            gara_id=gara.id, round_number=1
        ).all()
        assert round1, "il ricalcolo deve aver riscritto la classifica del turno 1"
        for rc in round1:
            assert rc.previous_position == seeding_positions[rc.user_id]

    def test_back_to_inscription_clears_seeding(
        self, director_user, players_8, db_session
    ):
        """Tornare alle iscrizioni cancella il seeding: gli iscritti cambiano."""
        gara = self._started_gara(director_user, players_8)
        assert SeedingService.get_seeding(gara.id)

        RoundService.cancel_current_round_startup(gara.id)
        db_session.flush()

        assert gara.status == GaraStatus.INSCRIPTION.value
        assert SeedingService.get_seeding(gara.id) == []

    def test_back_to_inscription_clears_initial_order(
        self, director_user, players_8, db_session
    ):
        """Anche l'"Ordine sorteggio" mostrato al giocatore sparisce.

        Lasciarlo valorizzato esibirebbe in pagina un ordine che non
        corrisponde più ad alcun seeding fino al riavvio della gara.
        """
        gara = self._started_gara(director_user, players_8)
        assert all(
            i.initial_order is not None
            for i in Inscription.query.filter_by(gara_id=gara.id).all()
        )

        RoundService.cancel_current_round_startup(gara.id)
        db_session.flush()

        assert all(
            i.initial_order is None
            for i in Inscription.query.filter_by(gara_id=gara.id).all()
        )

    def test_cancel_first_round_startup_clears_initial_order(
        self, director_user, players_8, db_session
    ):
        """Stessa pulizia anche dall'annullamento avvio gara."""
        gara = self._started_gara(director_user, players_8)

        RoundService.cancel_first_round_startup(gara.id)
        db_session.flush()

        assert all(
            i.initial_order is None
            for i in Inscription.query.filter_by(gara_id=gara.id).all()
        )

    def test_restart_after_inscription_draws_again(
        self, director_user, players_8, db_session
    ):
        """Dopo il ritorno alle iscrizioni il riavvio rigenera un seeding valido."""
        gara = self._started_gara(director_user, players_8)

        RoundService.cancel_current_round_startup(gara.id)
        db_session.flush()

        RoundService.start_first_round(gara.id)
        db_session.flush()

        seeding = SeedingService.get_seeding(gara.id)
        assert len(seeding) == 8
        assert [rc.position for rc in seeding] == list(range(1, 9))

    def test_cancel_first_round_startup_clears_seeding(
        self, director_user, players_8, db_session
    ):
        """Anche l'annullamento dell'avvio gara ripulisce il turno 0."""
        gara = self._started_gara(director_user, players_8)
        assert SeedingService.get_seeding(gara.id)

        RoundService.cancel_first_round_startup(gara.id)
        db_session.flush()

        assert SeedingService.get_seeding(gara.id) == []


@pytest.mark.integration
class TestSeedingForNonAmalfiStrategies:
    """Random e round robin derivano il seeding dagli accoppiamenti."""

    @pytest.fixture
    def director_user(self, db_session) -> User:
        unique_id = str(uuid.uuid4())[:8]
        director = User(
            username=f"director_{unique_id}",
            email=f"director_{unique_id}@test.com",
            role=UserRole.DIRECTOR.value,
        )
        director.set_password("director123")
        db_session.add(director)
        db_session.commit()
        return director

    @pytest.fixture
    def players_6(self, db_session) -> List[User]:
        batch_id = str(uuid.uuid4())[:8]
        players = []
        for i in range(6):
            player = User(
                username=f"p{i}_{batch_id}",
                email=f"p{i}_{batch_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            players.append(player)
        db_session.add_all(players)
        db_session.commit()
        return players

    def _start(self, director_user, players, strategy, rounds_count):
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name=f"Seeding {uuid.uuid4().hex[:6]}",
            date=date.today() + timedelta(days=7),
            location="Test Venue",
            description="Seeding non-amalfi",
            rounds_count=rounds_count,
            min_participants=4,
            max_participants=10,
            entry_fee=0.0,
            discipline="9_ball",
            distance=5,
            is_race_to=True,
            director_id=director_user.id,
            matchmaking_strategy=strategy,
            classification_system="WINS",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
        )
        InscriptionService.open_inscriptions(
            gara.id, utc_now() - timedelta(hours=1), utc_now() + timedelta(hours=1)
        )
        for player in players:
            InscriptionService.inscribe_user(player.id, gara.id)
        RoundService.start_first_round(gara.id)
        return gara

    @pytest.mark.parametrize(
        "strategy,rounds_count",
        # round robin con 6 giocatori richiede esattamente 5 turni
        [("random", 3), ("round_robin", 5)],
    )
    def test_seeding_matches_first_round_pairings(
        self, director_user, players_6, db_session, strategy, rounds_count
    ):
        """L'ordine di partenza è quello in cui i giocatori compaiono al turno 1."""
        gara = self._start(director_user, players_6, strategy, rounds_count)

        seeding = SeedingService.get_seeding(gara.id)
        assert len(seeding) == 6
        assert {rc.user_id for rc in seeding} == {p.id for p in players_6}

        expected = SeedingService.order_from_pairings(
            [
                type(
                    "P",
                    (),
                    {"players": tuple(filter(None, (m.player1_id, m.player2_id)))},
                )()
                for m in Match.query.filter_by(gara_id=gara.id, round_number=1)
                .order_by(Match.id)
                .all()
            ]
        )
        assert [rc.user_id for rc in seeding] == expected
