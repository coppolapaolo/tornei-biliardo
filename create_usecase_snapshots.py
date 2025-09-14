#!/usr/bin/env python3
"""
Script per creare snapshot del database per tutti gli 8 use case documentati.
Ogni snapshot rappresenta un momento specifico nel flusso di un use case.
"""

import os
import sys
from datetime import datetime, date, timedelta

# Aggiungi la directory del progetto al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models.base import db
from models import User
from models.campionato.models import Campionato
from models.user.services import UserService
from models.user.role_enum import UserRole
from models.competition.services import GaraService, InscriptionService
from models.location.models import BilliardHall
from utils.reset_manager import ResetManager


class UseCaseSnapshotCreator:
    """Crea snapshot per tutti gli use case documentati"""

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
        """Crea giocatori player01, player02, etc."""
        players = []
        for i in range(count):
            num = start_num + i
            username = f"player{num:02d}"
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
        """Crea direttori mario e pino"""
        directors = []
        names = ["mario", "pino"]
        for i in range(min(count, len(names))):
            name = names[i]
            # Verifica se esiste già
            existing = User.query.filter_by(username=name).first()
            if existing:
                directors.append(existing)
            else:
                director = UserService.create_user(
                    name, f"{name}@directors.com", f"{name}123", role="director"
                )
                directors.append(director)
        return directors

    def create_uc1_amalfi_tournament(self):
        """UC1: Amalfi tournament standalone con 8 giocatori, 3 turni"""
        print("Creating UC1 snapshot: Amalfi tournament...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            # Rileggi admin dal database per evitare problemi di sessione
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(8)

            # Crea gara standalone Amalfi
            today = date.today()
            gara = GaraService.create_gara(
                name="UC1 - Amalfi Tournament",
                number=1,
                date=today + timedelta(days=1),
                discipline="9-ball",
                distance=9,
                campionato_id=None,  # standalone
                director_id=admin.id,
                min_participants=6,
                rounds_count=3,
            )

            # Apri iscrizioni
            GaraService.to_inscription(
                gara.id, datetime.now(), datetime.now() + timedelta(hours=24)
            )

            # Iscrivi 8 giocatori
            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC1_Amalfi_Tournament",
                "Use Case 1: Gara Amalfi standalone con 8 giocatori iscritti, pronta per avvio primo turno",
            )
            print(f"UC1 snapshot: {result['message']}")
            return result

    def create_uc2_random_tournament(self):
        """UC2: Random tournament con challenge e cambio disciplina"""
        print("Creating UC2 snapshot: Random tournament with challenges...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(8)

            # Crea gara standalone Random
            today = date.today()
            gara = GaraService.create_gara(
                name="UC2 - Random Tournament",
                number=1,
                date=today + timedelta(days=1),
                discipline="8-ball",
                distance=9,
                campionato_id=None,  # standalone
                director_id=admin.id,
                min_participants=6,
                rounds_count=3,
            )

            # Apri iscrizioni
            GaraService.to_inscription(
                gara.id, datetime.now(), datetime.now() + timedelta(hours=24)
            )

            # Iscrivi 8 giocatori
            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC2_Random_Tournament",
                "Use Case 2: Gara Random con challenge e cambio disciplina, 8 giocatori iscritti",
            )
            print(f"UC2 snapshot: {result['message']}")
            return result

    def create_uc3_round_robin(self):
        """UC3: Round Robin con multi-set matches"""
        print("Creating UC3 snapshot: Round Robin tournament...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(8)

            # Crea gara Round Robin con multi-set
            today = date.today()
            gara = GaraService.create_gara(
                name="UC3 - Round Robin Multi-Set",
                number=1,
                date=today + timedelta(days=1),
                discipline="8-ball",
                distance=5,
                campionato_id=None,  # standalone
                director_id=admin.id,
                min_participants=6,
                rounds_count=1,
            )

            # Apri iscrizioni
            GaraService.to_inscription(
                gara.id, datetime.now(), datetime.now() + timedelta(hours=24)
            )

            # Iscrivi 8 giocatori
            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC3_Round_Robin_MultiSet",
                "Use Case 3: Gara Round Robin con multi-set (2 set da 5), 8 giocatori iscritti",
            )
            print(f"UC3 snapshot: {result['message']}")
            return result

    def create_uc4_championship(self):
        """UC4: Campionato con 3 gare multiple"""
        print("Creating UC4 snapshot: Championship with multiple competitions...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(10)

            # Crea campionato
            campionato = Campionato(
                name="UC4 - Championship Series", campionato_type="Amalfi"
            )
            db.session.add(campionato)
            db.session.flush()

            # Crea 3 gare del campionato
            for i in range(1, 4):
                today = date.today()
                gara = GaraService.create_gara(
                    name=f"UC4 - Gara {i}",
                    number=i,
                    date=today + timedelta(days=i * 7),  # Una gara a settimana
                    discipline="9-ball",
                    distance=7,
                    campionato_id=campionato.id,
                    director_id=admin.id,
                    min_participants=6,
                    rounds_count=3,
                )

                # Apri iscrizioni solo per la prima gara
                if i == 1:
                    GaraService.to_inscription(
                        gara.id, datetime.now(), datetime.now() + timedelta(days=6)
                    )

                    # Iscrivi alcuni giocatori alla prima gara
                    for player in players[:8]:
                        InscriptionService.inscribe_user(player.id, gara.id)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC4_Championship_Series",
                "Use Case 4: Campionato con 3 gare, prima gara con 8 iscritti",
            )
            print(f"UC4 snapshot: {result['message']}")
            return result

    def create_uc5_guest_access(self):
        """UC5: Guest access system con tornei pubblici"""
        print("Creating UC5 snapshot: Guest access system...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(6)

            # Crea gara pubblica in corso
            today = date.today()
            gara = GaraService.create_gara(
                name="UC5 - Public Tournament",
                number=1,
                date=today,  # Oggi, quindi in corso
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin.id,
                min_participants=4,
                rounds_count=3,
                # Gara pubblica per guest access
            )

            # Chiudi iscrizioni (scadute)
            GaraService.to_inscription(
                gara.id,
                datetime.now() - timedelta(days=2),
                datetime.now() - timedelta(hours=1),
            )

            # Iscrivi 6 giocatori
            for player in players:
                InscriptionService.inscribe_user(player.id, gara.id)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC5_Guest_Access_Public",
                "Use Case 5: Gara pubblica in corso, accessibile ai guest per visualizzazione",
            )
            print(f"UC5 snapshot: {result['message']}")
            return result

    def create_uc6_individual_match(self):
        """UC6: Individual match tra giocatori (semplificato)"""
        print("Creating UC6 snapshot: Individual match system...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            directors = self._create_directors()
            players = self._create_players(6)

            # Crea billiard hall per i match
            location = BilliardHall(
                name="UC6 - Billiard Hall",
                address="Via Test 123",
                city="TestCity",
                is_active=True,
            )
            db.session.add(location)
            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC6_Individual_Matches_Basic",
                "Use Case 6: Base per sistema match individuali con billiard hall e giocatori",
            )
            print(f"UC6 snapshot: {result['message']}")
            return result

    def create_uc7_availability_system(self):
        """UC7: Player availability system (semplificato)"""
        print("Creating UC7 snapshot: Player availability system...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            directors = self._create_directors()
            players = self._create_players(4)

            # Crea billiard hall
            location = BilliardHall(
                name="UC7 - Pool Hall",
                address="Via Availability 456",
                city="AvailabilityCity",
                is_active=True,
            )
            db.session.add(location)
            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC7_Availability_System_Basic",
                "Use Case 7: Base per sistema disponibilità giocatori con location",
            )
            print(f"UC7 snapshot: {result['message']}")
            return result

    def create_uc8_advanced_modification(self):
        """UC8: Advanced match modification workflow"""
        print("Creating UC8 snapshot: Advanced match modification...")

        with self.app.app_context():
            admin = self._reset_db_clean()
            admin = User.query.filter_by(username="admin").first()
            directors = self._create_directors()
            players = self._create_players(8)

            # Crea gara con 4 turni per le modifiche avanzate
            today = date.today()
            gara = GaraService.create_gara(
                name="UC8 - Advanced Modifications",
                number=1,
                date=today - timedelta(days=1),  # Ieri (già iniziata)
                discipline="9-ball",
                distance=5,
                campionato_id=None,
                director_id=admin.id,
                min_participants=6,
                rounds_count=4,
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

            # La gara è pronta per essere avviata (primo turno)

            db.session.commit()

            # Salva snapshot
            result = self.reset_manager.save_current_state(
                "UC8_Advanced_Modifications",
                "Use Case 8: Gara con 4 turni per testare workflow modifiche avanzate",
            )
            print(f"UC8 snapshot: {result['message']}")
            return result

    def create_all_snapshots(self):
        """Crea tutti gli snapshot per tutti i use case"""
        print("Creating all use case snapshots...\n")

        snapshots = []

        # UC1: Amalfi Tournament
        try:
            result = self.create_uc1_amalfi_tournament()
            snapshots.append(("UC1", result))
        except Exception as e:
            print(f"Error creating UC1: {e}")

        # UC2: Random Tournament
        try:
            result = self.create_uc2_random_tournament()
            snapshots.append(("UC2", result))
        except Exception as e:
            print(f"Error creating UC2: {e}")

        # UC3: Round Robin
        try:
            result = self.create_uc3_round_robin()
            snapshots.append(("UC3", result))
        except Exception as e:
            print(f"Error creating UC3: {e}")

        # UC4: Championship
        try:
            result = self.create_uc4_championship()
            snapshots.append(("UC4", result))
        except Exception as e:
            print(f"Error creating UC4: {e}")

        # UC5: Guest Access
        try:
            result = self.create_uc5_guest_access()
            snapshots.append(("UC5", result))
        except Exception as e:
            print(f"Error creating UC5: {e}")

        # UC6: Individual Matches
        try:
            result = self.create_uc6_individual_match()
            snapshots.append(("UC6", result))
        except Exception as e:
            print(f"Error creating UC6: {e}")

        # UC7: Availability System
        try:
            result = self.create_uc7_availability_system()
            snapshots.append(("UC7", result))
        except Exception as e:
            print(f"Error creating UC7: {e}")

        # UC8: Advanced Modifications
        try:
            result = self.create_uc8_advanced_modification()
            snapshots.append(("UC8", result))
        except Exception as e:
            print(f"Error creating UC8: {e}")

        print(f"\n=== Summary ===")
        print(f"Created {len(snapshots)} snapshots:")
        for uc_name, result in snapshots:
            status = "✓" if result["status"] == "success" else "✗"
            print(f"{status} {uc_name}: {result['message']}")

        return snapshots


if __name__ == "__main__":
    creator = UseCaseSnapshotCreator()
    creator.create_all_snapshots()
