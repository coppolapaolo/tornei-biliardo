"""Test specifico per il bug anti-rematch nell'algoritmo Amalfi."""

import pytest
from datetime import date, datetime, timedelta
from typing import List, Set, Tuple

from models import User, Gara, Match
from models.user.role_enum import UserRole
from models.status_enum import MatchStatus
from models.competition.services import GaraService, InscriptionService
from models.match.services import MatchService, RackService
from models.classification.models import RoundClassification
from models.classification.services import ClassificationService, PlayerEncounterService
from models.classification.models import PlayerEncounter


@pytest.mark.integration
class TestAntiRematchBug:
    """Test per verificare il bug anti-rematch nell'algoritmo Amalfi."""

    @pytest.fixture
    def admin_user(self, db_session):
        """Create admin user for test."""
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        admin = User(
            username=f"admin_{unique_id}",
            email=f"admin_{unique_id}@test.com",
            role=UserRole.ADMIN.value,
        )
        admin.set_password("admin123")
        db_session.add(admin)
        db_session.commit()
        return admin

    @pytest.fixture
    def test_players(self, db_session):
        """Create 6 test players for controlled testing."""
        import uuid

        batch_id = str(uuid.uuid4())[:8]
        players = []

        # Create players with specific names for easier debugging
        player_names = ["pino", "player1", "player2", "player3", "player4", "player5"]

        for i, name in enumerate(player_names):
            player = User(
                username=f"{name}_{batch_id}",
                email=f"{name}_{batch_id}@test.com",
                role=UserRole.PLAYER.value,
            )
            player.set_password("player123")
            players.append(player)

        db_session.add_all(players)
        db_session.commit()
        return players

    def test_anti_rematch_should_prevent_immediate_rematches(
        self, admin_user, test_players, db_session
    ):
        """Test che verifica che l'anti-rematch prevenga i reincontri immediati.

        Scenario:
        - 6 giocatori, 3 turni Amalfi
        - Anti-rematch abilitato
        - Nessuna coppia dovrebbe giocare più di una volta
        """
        # Crea gara con anti-rematch abilitato
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Test Anti-Rematch Bug",
            date=date.today() + timedelta(days=1),
            location="Test Location",
            description="Test per verificare anti-rematch",
            rounds_count=3,
            min_participants=4,
            max_participants=8,
            entry_fee=10.0,
            discipline="palla_9",
            distance=9,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,  # IMPORTANTE: anti-rematch abilitato!
            rating_type=None,
        )

        # Iscrivi 6 giocatori
        for player in test_players:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Apri iscrizioni e avvia primo turno
        inscription_start = datetime.now()
        inscription_end = datetime.now() + timedelta(hours=2)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        GaraService.start_first_round(gara.id)

        # Traccia tutti i pairing attraverso i turni
        all_pairings: Set[Tuple[int, int]] = set()

        for round_num in range(1, 4):  # 3 turni
            if round_num > 1:
                # Completa il turno precedente
                prev_matches = Match.query.filter_by(
                    gara_id=gara.id, round_number=round_num - 1
                ).all()
                self._complete_all_matches_controlled(prev_matches, db_session)
                RoundClassification.calculate_classification_after_round(
                    gara.id, round_num - 1
                )

                # Crea il turno successivo
                GaraService.create_amalfi_round(gara.id, round_num)
                # Aggiorna current_round manualmente
                gara.current_round = round_num
                db_session.add(gara)
                db_session.commit()

            # Ottieni match del turno corrente
            current_matches = Match.query.filter_by(
                gara_id=gara.id, round_number=round_num
            ).all()

            print(f"\n=== TURNO {round_num} ===")

            # Debug: mostra tutti gli encounter esistenti
            all_encounters = (
                db_session.query(PlayerEncounter).filter_by(gara_id=gara.id).all()
            )
            print(f"Tutti gli encounter nella gara: {len(all_encounters)}")
            for enc in all_encounters:
                p1_name = self._get_player_name(enc.player1_id, test_players)
                p2_name = self._get_player_name(enc.player2_id, test_players)
                print(f"  - {p1_name} vs {p2_name} (Round {enc.round_number})")

            # Controlla ogni match del turno corrente
            for match in current_matches:
                if not match.is_bye and not match.is_trio:
                    # Normalizza la coppia (ID più piccolo prima)
                    pairing = tuple(sorted([match.player1_id, match.player2_id]))

                    # Ottieni i nomi per debug
                    p1_name = self._get_player_name(match.player1_id, test_players)
                    p2_name = self._get_player_name(match.player2_id, test_players)

                    print(f"Match: {p1_name} vs {p2_name} (IDs: {pairing})")

                    # CONTROLLO CRITICO: Questo pairing è già stato usato?
                    if pairing in all_pairings:
                        # Trova in quale turno precedente si sono incontrati
                        previous_round = self._find_previous_encounter(
                            gara.id, match.player1_id, match.player2_id, round_num
                        )

                        pytest.fail(
                            f"❌ ANTI-REMATCH BUG RILEVATO!\n"
                            f"   - {p1_name} vs {p2_name} si sono già incontrati nel Turno {previous_round}\n"
                            f"   - Ora si incontrano di nuovo nel Turno {round_num}\n"
                            f"   - L'algoritmo Amalfi doveva evitare questo reincontro!"
                        )

                    # Aggiungi il pairing al set
                    all_pairings.add(pairing)

        # Se arriviamo qui, l'anti-rematch ha funzionato correttamente!
        print(f"\n✅ Anti-rematch test PASSATO!")
        print(f"   - Tutti i {len(all_pairings)} abbinamenti sono unici")
        print(f"   - Nessun reincontro rilevato nei 3 turni")

    def _complete_all_matches_controlled(self, matches: List[Match], db_session):
        """Completa tutti i match con risultati controllati per creare classifiche realistiche."""
        for i, match in enumerate(matches):
            if match.is_bye or match.is_trio:
                continue

            # Simula risultati alternati per creare variazioni di classifica
            # Questo aiuta a testare diverse situazioni di abbinamento
            if i % 2 == 0:
                # Il primo giocatore vince 5-2
                winner_id = match.player1_id
                winner_racks = 5
                loser_racks = 2
            else:
                # Il secondo giocatore vince 5-3
                winner_id = match.player2_id
                winner_racks = 5
                loser_racks = 3

            # Aggiungi rack per il vincitore
            for rack_num in range(1, winner_racks + 1):
                RackService.add_rack_result(
                    match_id=match.id,
                    rack_number=rack_num,
                    winner_id=winner_id,
                    reported_by_id=winner_id,
                    confirmed_by_player=True,
                    validated_by_admin=True,
                )

            # Aggiungi rack per il perdente
            other_player_id = (
                match.player2_id if winner_id == match.player1_id else match.player1_id
            )
            for rack_num in range(winner_racks + 1, winner_racks + loser_racks + 1):
                RackService.add_rack_result(
                    match_id=match.id,
                    rack_number=rack_num,
                    winner_id=other_player_id,
                    reported_by_id=other_player_id,
                    confirmed_by_player=True,
                    validated_by_admin=True,
                )

            # Completa il match
            MatchService.to_completed(match.id)
            db_session.refresh(match)

            # NOTA: Gli encounter sono già registrati dall'Amalfi engine durante la creazione dei match

    def _get_player_name(self, player_id: int, players: List[User]) -> str:
        """Ottieni il nome del giocatore per debug."""
        player = next((p for p in players if p.id == player_id), None)
        if player:
            # Rimuovi il suffixe UUID per leggibilità
            return player.username.split("_")[0]
        return f"Player_{player_id}"

    def _find_previous_encounter(
        self, gara_id: int, p1_id: int, p2_id: int, current_round: int
    ) -> int:
        """Trova il turno precedente in cui due giocatori si sono incontrati."""
        for round_num in range(1, current_round):
            match = (
                Match.query.filter_by(gara_id=gara_id, round_number=round_num)
                .filter(
                    ((Match.player1_id == p1_id) & (Match.player2_id == p2_id))
                    | ((Match.player1_id == p2_id) & (Match.player2_id == p1_id))
                )
                .first()
            )

            if match:
                return round_num

        return -1  # Non dovrebbe mai accadere se viene chiamato correttamente

    def test_anti_rematch_with_limited_options(
        self, admin_user, test_players, db_session
    ):
        """Test edge case: anti-rematch quando le opzioni sono limitate.

        Con 4 giocatori e 3 turni, matematicamente è impossibile evitare tutti i rematches,
        ma l'algoritmo dovrebbe minimizzarli il più possibile.
        """
        # Usa solo 4 giocatori per forzare situazioni critiche
        limited_players = test_players[:4]

        # Crea gara con anti-rematch abilitato
        gara = GaraService.create_gara(
            campionato_id=None,
            number=1,
            name="Test Anti-Rematch Limited Options",
            date=date.today() + timedelta(days=1),
            location="Test Location",
            description="Test anti-rematch con opzioni limitate",
            rounds_count=2,
            min_participants=4,
            max_participants=6,
            entry_fee=10.0,
            discipline="palla_9",
            distance=7,
            best_of=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
            rating_type=None,
        )

        # Iscrivi 4 giocatori
        for player in limited_players:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Avvia la gara
        inscription_start = datetime.now()
        inscription_end = datetime.now() + timedelta(hours=2)
        GaraService.open_inscriptions(gara.id, inscription_start, inscription_end)
        GaraService.start_first_round(gara.id)

        # Con 4 giocatori e 2 turni, dovremmo avere:
        # - Turno 1: 2 match (4 giocatori)
        # - Turno 2: 2 match (ma potrebbero esserci rematches)

        # L'importante è che NON ci siano rematches immediati (turno consecutivo)
        pairings_by_round = []

        for round_num in range(1, 3):
            if round_num > 1:
                # Completa turno precedente
                prev_matches = Match.query.filter_by(
                    gara_id=gara.id, round_number=round_num - 1
                ).all()
                self._complete_all_matches_controlled(prev_matches, db_session)
                RoundClassification.calculate_classification_after_round(
                    gara.id, round_num - 1
                )

                # Crea turno successivo
                GaraService.create_amalfi_round(gara.id, round_num)
                gara.current_round = round_num
                db_session.add(gara)
                db_session.commit()

            # Raccogli pairings del turno corrente
            current_matches = Match.query.filter_by(
                gara_id=gara.id, round_number=round_num
            ).all()

            round_pairings = set()
            for match in current_matches:
                if not match.is_bye and not match.is_trio:
                    pairing = tuple(sorted([match.player1_id, match.player2_id]))
                    round_pairings.add(pairing)

            pairings_by_round.append(round_pairings)
            print(f"Turno {round_num}: {len(round_pairings)} match")

        # Verifica: nessun rematch immediato (turni consecutivi)
        for i in range(len(pairings_by_round) - 1):
            current_round_pairings = pairings_by_round[i]
            next_round_pairings = pairings_by_round[i + 1]

            immediate_rematches = current_round_pairings.intersection(
                next_round_pairings
            )

            assert (
                len(immediate_rematches) == 0
            ), f"Trovati {len(immediate_rematches)} rematches immediati tra Turno {i+1} e {i+2}: {immediate_rematches}"

        print(f"✅ Test edge case PASSATO: nessun rematch immediato rilevato!")
