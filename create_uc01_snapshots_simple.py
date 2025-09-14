#!/usr/bin/env python3
"""
Script semplificato per creare snapshot del database per i principali use case di UC01.md
Focus su snapshot funzionanti piuttosto che implementazione completa.
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
from models.competition.services import GaraService, InscriptionService
from models.location.models import BilliardHall
from models.challenge.models import Challenge
from utils.reset_manager import ResetManager


class UC01SnapshotCreatorSimple:
    """Crea snapshot semplificati per i use case principali di UC01.md"""

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
        UC1: Snapshot per guest access - gara pronta per primo turno.
        """
        print("Creating UC1 snapshot: Guest access tournament...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(8)
            billiard_hall = self._create_billiard_hall()

            # Crea gara standalone
            today = date.today()
            gara = GaraService.create_gara(
                number=1,
                name="UC1 - Guest Access Tournament",
                date=today,  # Oggi (in corso)
                discipline="9-ball",
                distance=5,
                campionato_id=None,  # standalone
                director_id=admin.id,
            )

            # Iscrivi 8 giocatori
            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC01_Use_Case_1_Guest_Access_Simple",
                "UC1: Gara standalone pronta per accesso guest - 8 giocatori iscritti",
            )
            print(f"UC1 snapshot: {result['message']}")
            return result

    def create_uc4_table_assignment_snapshot(self):
        """
        UC4: Snapshot per sistema assegnazione tavoli.
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
                number=1,
                name="UC4 - Table Assignment Tournament",
                date=today,
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin.id,
            )

            # Iscrivi esattamente 8 giocatori (come da UC4)
            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC01_Use_Case_4_Table_Assignment_Simple",
                "UC4: Gara con 8 giocatori e billiard hall con 3 tavoli per test assegnazione",
            )
            print(f"UC4 snapshot: {result['message']}")
            return result

    def create_uc6_standalone_challenge_snapshot(self):
        """
        UC6: Snapshot per challenge standalone.
        """
        print("Creating UC6 snapshot: Standalone challenge system...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            directors = self._create_directors()
            players = self._create_players(6)

            # Crea multiple challenge disponibili
            challenges = [
                {
                    "description": "Challenge di precisione per migliorare la mira",
                    "image": "uc6_spot_shot_challenge.jpg",
                },
                {
                    "description": "Challenge per migliorare la spaccata",
                    "image": "uc6_break_challenge.jpg",
                },
                {
                    "description": "Challenge per migliorare il gioco di sicurezza",
                    "image": "uc6_safety_challenge.jpg",
                },
            ]

            for challenge_data in challenges:
                challenge = Challenge(
                    description=challenge_data["description"],
                    image_path=f"/static/challenges/{challenge_data['image']}",
                    is_active=True,
                )
                db.session.add(challenge)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC01_Use_Case_6_Standalone_Challenges_Simple",
                "UC6: Challenge standalone disponibili per i giocatori, sistema pronto per tentativi",
            )
            print(f"UC6 snapshot: {result['message']}")
            return result

    def create_uc7_player_profile_snapshot(self):
        """
        UC7: Snapshot per profilo giocatore con utenti di base.
        """
        print("Creating UC7 snapshot: Player profile system...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(6)
            billiard_hall = self._create_billiard_hall()

            # Crea una gara semplice per storico
            today = date.today()
            gara = GaraService.create_gara(
                number=1,
                name="UC7 - Historical Tournament",
                date=today - timedelta(days=7),
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin.id,
            )

            # Iscrivi alcuni giocatori
            for player in players[:4]:
                InscriptionService.inscribe_user(player.id, gara.id)

            # Crea una challenge per storico
            challenge = Challenge(
                description="Challenge storica per profilo UC7",
                image_path="/static/challenges/uc7_historical_challenge.jpg",
                is_active=True,
            )
            db.session.add(challenge)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC01_Use_Case_7_Player_Profile_Simple",
                "UC7: Giocatori con base per storico e profilo, pronti per test profilo e export",
            )
            print(f"UC7 snapshot: {result['message']}")
            return result

    def create_working_snapshots(self):
        """Crea gli snapshot funzionanti principali"""
        print("Creating working UC01 snapshots...\n")

        snapshots = []
        use_cases = [
            ("UC1", self.create_uc1_guest_access_snapshot),
            ("UC4", self.create_uc4_table_assignment_snapshot),
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

        print(f"\n=== UC01 Working Snapshots Summary ===")
        print(f"Created {len(snapshots)} snapshots:")
        for uc_name, result in snapshots:
            status = "✓" if result["status"] == "success" else "✗"
            print(f"{status} {uc_name}: {result['message']}")

        return snapshots


if __name__ == "__main__":
    creator = UC01SnapshotCreatorSimple()
    creator.create_working_snapshots()
