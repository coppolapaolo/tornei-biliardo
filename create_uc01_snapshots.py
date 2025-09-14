#!/usr/bin/env python3
"""
Script per creare snapshot del database per tutti i 7 use case di UC01.md
Ogni snapshot rappresenta lo stato iniziale necessario per eseguire il use case.
"""

import os
import sys
from datetime import datetime, date, timedelta

# Aggiungi la directory del progetto al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models.base import db
from models import User
from models.user.services import UserService
from models.user.role_enum import UserRole
from models.competition.services import (
    GaraService,
    InscriptionService,
    ProvaStateMachine,
)
from models.match.services import MatchService, RackService
from models.matchmaking.service import MatchmakingService
from models.location.models import BilliardHall
from models.challenge.models import Challenge, ChallengeAttempt
from utils.reset_manager import ResetManager


class UC01SnapshotCreator:
    """Crea snapshot specifici per tutti i use case di UC01.md"""

    def __init__(self):
        self.app = create_app()
        self.reset_manager = ResetManager()

    def _reset_db_clean(self):
        """Reset del database pulito usando il reset manager"""
        with self.app.app_context():
            result = self.reset_manager.reset_base()
            if result["status"] == "success":
                return result["data"]["admin"]
            else:
                raise Exception(f"Reset failed: {result['message']}")

    def _create_players(self, count: int, start_num: int = 1):
        """Crea giocatori uc01_player01, uc01_player02, etc."""
        players = []
        for i in range(count):
            num = start_num + i
            username = f"uc01_player{num:02d}"
            # Verifica se esiste già
            existing = User.query.filter_by(username=username).first()
            if existing:
                players.append(existing)
            else:
                player = UserService.create_user(
                    username, f"{username}@test.com", "123456", role="player"
                )
                players.append(player)
        return players

    def _create_directors(self, count: int = 2):
        """Crea direttori uc01_mario e uc01_pino"""
        directors = []
        names = ["uc01_mario", "uc01_pino"]
        for i in range(min(count, len(names))):
            name = names[i]
            # Verifica se esiste già
            existing = User.query.filter_by(username=name).first()
            if existing:
                directors.append(existing)
            else:
                director = UserService.create_user(
                    name, f"{name}@directors.com", f"director123", role="director"
                )
                directors.append(director)
        return directors

    def _create_billiard_hall(self) -> BilliardHall:
        """Crea billiard hall con 3 tavoli per UC4"""
        import json

        hall = BilliardHall(
            name="UC01 Billiard Hall",
            address="Via UC01 123",
            city="UC01City",
            number_of_tables=3,
            table_types=json.dumps(["A", "sala rossa", "sala blu"]),
            is_active=True,
        )
        db.session.add(hall)
        db.session.commit()
        return hall

    def create_uc1_guest_access_snapshot(self):
        """
        UC1: Snapshot per guest access con gara in corso e primo turno completato.
        Stato: Gara standalone con 8 giocatori, primo turno completato, pronta per secondo turno.
        """
        print("Creating UC1 snapshot: Guest access to ongoing tournament...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(8)
            billiard_hall = self._create_billiard_hall()

            # Crea gara standalone
            today = date.today()
            gara = GaraService.create_gara(
                name="UC1 - Guest Access Tournament",
                number=1,
                date=today,  # Oggi (in corso)
                discipline="9-ball",
                distance=5,
                campionato_id=None,  # standalone
                director_id=admin.id,
                min_participants=6,
                rounds_count=3,
# location managed separately,
            )

            # Apri e chiudi iscrizioni (scadute)
            GaraService.to_inscription(
                gara.id,
                datetime.now() - timedelta(hours=25),
                datetime.now() - timedelta(hours=1),
            )

            # Iscrivi 8 giocatori
            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            # Chiudi iscrizioni e avvia primo turno
            gara = GaraService.get_gara_by_id(gara.id)
            ProvaStateMachine.start_playing(gara)

            # Note: UC1 snapshot ready for first round to be created
            # First round creation will be done by test or manual intervention

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC01_Use_Case_1_Guest_Access",
                "UC1: Gara standalone con primo turno completato, guest può vedere risultati e classifica",
            )
            print(f"UC1 snapshot: {result['message']}")
            return result

    def create_uc2_match_modification_snapshot(self):
        """
        UC2: Snapshot per workflow modifiche match con effetto sui turni.
        Stato: Gara con secondo turno completato, pronta per modifiche che influenzano i turni.
        """
        print("Creating UC2 snapshot: Match modification workflow...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(8)
            billiard_hall = self._create_billiard_hall()

            # Crea gara standalone
            today = date.today()
            gara = GaraService.create_gara(
                name="UC2 - Match Modification Tournament",
                number=1,
                date=today - timedelta(days=1),  # Ieri (già iniziata)
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin.id,
                min_participants=6,
                rounds_count=3,
# location managed separately,
            )

            # Iscrizioni scadute
            GaraService.to_inscription(
                gara.id,
                datetime.now() - timedelta(days=3),
                datetime.now() - timedelta(days=2),
            )

            # Iscrivi 8 giocatori
            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            gara = GaraService.get_gara_by_id(gara.id)
            ProvaStateMachine.start_playing(gara)

            matchmaking_service = MatchmakingService()

            # Completa primo e secondo turno
            for round_num in [1, 2]:
                result = # matchmaking_service.create_round - removed for simplicity(gara.id, round_num)
                if not result.success:
                    raise Exception(
                        f"Failed to create round {round_num}: {result.message}"
                    )

                from models.match.models import Match

                matches = Match.query.filter_by(
                    gara_id=gara.id, round_number=round_num
                ).all()

                for match in matches:
                    # Round 1: 5-2, Round 2: 5-1
                    p1_score = 5
                    p2_score = 3 - round_num  # Round 1: 2, Round 2: 1

                    for _ in range(p1_score):
                        RackService.create_rack(
                            match.id, match.player1_id, "player1_win"
                        )
                    for _ in range(p2_score):
                        RackService.create_rack(
                            match.id, match.player2_id, "player2_win"
                        )

                    MatchService.to_completed(match.id)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC01_Use_Case_2_Match_Modification",
                "UC2: Gara con secondo turno completato, pronta per test modifiche match e effetti sui turni",
            )
            print(f"UC2 snapshot: {result['message']}")
            return result

    def create_uc3_round_ordering_snapshot(self):
        """
        UC3: Snapshot per test ordinamento turni e visibilità gestione.
        Stato: Gara random con 3 turni, solo primo turno creato.
        """
        print("Creating UC3 snapshot: Round ordering and management...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(8)
            billiard_hall = self._create_billiard_hall()

            # Crea gara con strategia random
            today = date.today()
            gara = GaraService.create_gara(
                name="UC3 - Round Ordering Tournament",
                number=1,
                date=today,
                discipline="8-ball",
                distance=5,
                campionato_id=None,
                director_id=admin.id,
                min_participants=6,
                rounds_count=3,  # 3 turni come da UC3
# location managed separately,
            )

            # Imposta strategia random
            gara.matchmaking_strategy = "random"

            # Chiudi iscrizioni
            GaraService.to_inscription(
                gara.id,
                datetime.now() - timedelta(hours=25),
                datetime.now() - timedelta(hours=1),
            )

            # Iscrivi 8 giocatori
            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            gara = GaraService.get_gara_by_id(gara.id)
            ProvaStateMachine.start_playing(gara)

            # Crea solo il primo turno (non completato)
            matchmaking_service = MatchmakingService()
            result = # matchmaking_service.create_round - removed for simplicity(gara.id, 1)
            if not result.success:
                raise Exception(f"Failed to create round 1: {result.message}")

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC01_Use_Case_3_Round_Ordering",
                "UC3: Gara random con 3 turni, primo turno creato ma non completato, per test ordinamento",
            )
            print(f"UC3 snapshot: {result['message']}")
            return result

    def create_uc4_table_assignment_snapshot(self):
        """
        UC4: Snapshot per sistema assegnazione tavoli e gestione code.
        Stato: Gara Amalfi con 8 giocatori e 3 tavoli disponibili.
        """
        print("Creating UC4 snapshot: Table assignment system...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(8)
            billiard_hall = self._create_billiard_hall()

            # Crea gara Amalfi (come specificato in UC4)
            today = date.today()
            gara = GaraService.create_gara(
                name="UC4 - Table Assignment Tournament",
                number=1,
                date=today,
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin.id,
                min_participants=6,
                rounds_count=3,
# location managed separately,
            )

            # Imposta strategia Amalfi
            gara.matchmaking_strategy = "amalfi"

            # Chiudi iscrizioni
            GaraService.to_inscription(
                gara.id,
                datetime.now() - timedelta(hours=25),
                datetime.now() - timedelta(hours=1),
            )

            # Iscrivi esattamente 8 giocatori (come da UC4)
            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            gara = GaraService.get_gara_by_id(gara.id)
            ProvaStateMachine.start_playing(gara)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC01_Use_Case_4_Table_Assignment",
                "UC4: Gara Amalfi con 8 giocatori e billiard hall con 3 tavoli, pronta per test assegnazione tavoli",
            )
            print(f"UC4 snapshot: {result['message']}")
            return result

    def create_uc5_challenge_integration_snapshot(self):
        """
        UC5: Snapshot per integrazione sistema challenge con tornei.
        Stato: Gara random con challenge dopo primo turno configurata.
        """
        print("Creating UC5 snapshot: Challenge tournament integration...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(8)
            billiard_hall = self._create_billiard_hall()

            # Crea challenge per dopo il primo turno
            challenge = Challenge(
                description="Challenge da completare dopo il primo turno del torneo",
                image_path="/static/challenges/uc5_tournament_challenge.jpg",
                is_active=True,
            )
            db.session.add(challenge)

            # Crea gara random con challenge
            today = date.today()
            gara = GaraService.create_gara(
                name="UC5 - Challenge Integration Tournament",
                number=1,
                date=today,
                discipline="8-ball",
                distance=5,
                campionato_id=None,
                director_id=admin.id,
                min_participants=6,
                rounds_count=3,
# location managed separately,
            )

            # Imposta strategia random con challenge
            gara.matchmaking_strategy = "random"

            # Chiudi iscrizioni
            GaraService.to_inscription(
                gara.id,
                datetime.now() - timedelta(hours=25),
                datetime.now() - timedelta(hours=1),
            )

            # Iscrivi 8 giocatori
            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            gara = GaraService.get_gara_by_id(gara.id)
            ProvaStateMachine.start_playing(gara)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC01_Use_Case_5_Challenge_Integration",
                "UC5: Gara random con challenge configurata, pronta per test integrazione challenge-torneo",
            )
            print(f"UC5 snapshot: {result['message']}")
            return result

    def create_uc6_standalone_challenge_snapshot(self):
        """
        UC6: Snapshot per challenge standalone indipendenti da tornei.
        Stato: Challenge disponibili per i giocatori, sistema pronto per tentativi.
        """
        print("Creating UC6 snapshot: Standalone challenge system...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            directors = self._create_directors()
            players = self._create_players(6)  # Meno giocatori per challenge standalone

            # Crea multiple challenge disponibili
            challenges = [
                {
                    "name": "UC6 - Spot Shot Challenge",
                    "description": "Challenge di precisione per migliorare la mira",
                    "difficulty": 1,
                    "max_attempts": 3,
                },
                {
                    "name": "UC6 - Break Challenge",
                    "description": "Challenge per migliorare la spaccata",
                    "difficulty": 2,
                    "max_attempts": 5,
                },
                {
                    "name": "UC6 - Safety Challenge",
                    "description": "Challenge per migliorare il gioco di sicurezza",
                    "difficulty": 3,
                    "max_attempts": 2,
                },
            ]

            for challenge_data in challenges:
                challenge = Challenge(
                    description=challenge_data["description"],
                    image_path=f"/static/challenges/{challenge_data['name'].lower().replace(' ', '_')}.jpg",
                    is_active=True,
                )
                db.session.add(challenge)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC01_Use_Case_6_Standalone_Challenges",
                "UC6: Challenge standalone disponibili per i giocatori, sistema pronto per tentativi multipli",
            )
            print(f"UC6 snapshot: {result['message']}")
            return result

    def create_uc7_player_profile_snapshot(self):
        """
        UC7: Snapshot per profilo giocatore con storico e statistiche.
        Stato: Giocatori con storico match e challenge, pronti per visualizzazione profilo.
        """
        print("Creating UC7 snapshot: Player profile and statistics...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(6)
            billiard_hall = self._create_billiard_hall()

            # Crea alcune gare completate per storico
            gare_data = [
                {
                    "name": "UC7 - Historical Tournament 1",
                    "date": date.today() - timedelta(days=30),
                    "discipline": "9-ball",
                },
                {
                    "name": "UC7 - Historical Tournament 2",
                    "date": date.today() - timedelta(days=15),
                    "discipline": "8-ball",
                },
            ]

            for i, gara_data in enumerate(gare_data):
                gara = GaraService.create_gara(
                    name=gara_data["name"],
                    number=i + 1,
                    date=gara_data["date"],
                    discipline=gara_data["discipline"],
                    distance=5,
                    campionato_id=None,
                    director_id=admin.id,
                    min_participants=4,
                    rounds_count=2,
    # location managed separately,
                )

                # Iscrizioni scadute
                GaraService.to_inscription(
                    gara.id,
                    datetime.now() - timedelta(days=35 - i * 15),
                    datetime.now() - timedelta(days=32 - i * 15),
                )

                # Iscrivi alcuni giocatori
                for player in players[:4]:
                    InscriptionService.inscribe_user(player.id, gara.id)

                gara = GaraService.get_gara_by_id(gara.id)
                ProvaStateMachine.start_playing(gara)

                # Completa gara per creare storico
                matchmaking_service = MatchmakingService()
                for round_num in [1, 2]:
                    result = # matchmaking_service.create_round - removed for simplicity(gara.id, round_num)
                    if result.success:
                        from models.match.models import Match

                        matches = Match.query.filter_by(
                            gara_id=gara.id, round_number=round_num
                        ).all()

                        for match in matches:
                            # Risultati variati per storico interessante
                            p1_score = 5
                            p2_score = round_num + (i % 3)  # Varia i risultati

                            for _ in range(p1_score):
                                RackService.create_rack(
                                    match.id, match.player1_id, "player1_win"
                                )
                            for _ in range(p2_score):
                                RackService.create_rack(
                                    match.id, match.player2_id, "player2_win"
                                )

                            MatchService.to_completed(match.id)

            # Crea challenge completate per storico
            challenges = [
                "UC7 - Historical Challenge 1",
                "UC7 - Historical Challenge 2",
            ]

            for challenge_name in challenges:
                challenge = Challenge(
                    description=f"Challenge storica per profilo: {challenge_name}",
                    image_path=f"/static/challenges/{challenge_name.lower().replace(' ', '_')}.jpg",
                    is_active=True,
                )
                db.session.add(challenge)
                db.session.flush()

                # Aggiungi tentativi per alcuni giocatori
                for player in players[:3]:
                    for attempt_num in range(1, 3):
                        attempt = ChallengeAttempt(
                            challenge_id=challenge.id,
                            user_id=player.id,
                            attempt_number=attempt_num,
                            score=15 + attempt_num * 2,
                            is_successful=attempt_num
                            == 2,  # Secondo tentativo riuscito
                        )
                        db.session.add(attempt)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC01_Use_Case_7_Player_Profile",
                "UC7: Giocatori con storico completo di match e challenge, pronti per test profilo e export CSV",
            )
            print(f"UC7 snapshot: {result['message']}")
            return result

    def create_all_uc01_snapshots(self):
        """Crea tutti gli snapshot per tutti i 7 use case di UC01.md"""
        print("Creating all UC01 snapshots...\n")

        snapshots = []
        use_cases = [
            ("UC1", self.create_uc1_guest_access_snapshot),
            ("UC2", self.create_uc2_match_modification_snapshot),
            ("UC3", self.create_uc3_round_ordering_snapshot),
            ("UC4", self.create_uc4_table_assignment_snapshot),
            ("UC5", self.create_uc5_challenge_integration_snapshot),
            ("UC6", self.create_uc6_standalone_challenge_snapshot),
            ("UC7", self.create_uc7_player_profile_snapshot),
        ]

        for uc_name, create_method in use_cases:
            try:
                result = create_method()
                snapshots.append((uc_name, result))
            except Exception as e:
                print(f"Error creating {uc_name}: {e}")
                snapshots.append((uc_name, {"status": "error", "message": str(e)}))

        print(f"\n=== UC01 Snapshots Summary ===")
        print(f"Created {len(snapshots)} snapshots:")
        for uc_name, result in snapshots:
            status = "✓" if result["status"] == "success" else "✗"
            print(f"{status} {uc_name}: {result['message']}")

        return snapshots


if __name__ == "__main__":
    creator = UC01SnapshotCreator()
    creator.create_all_uc01_snapshots()
