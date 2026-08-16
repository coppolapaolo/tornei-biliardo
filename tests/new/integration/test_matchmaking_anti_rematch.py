"""Test specifico per il bug anti-rematch nell'algoritmo Amalfi.

Questi test verificano che l'algoritmo Amalfi eviti correttamente i rematch
tra giocatori che si sono già incontrati in turni precedenti.
"""

import pytest
from datetime import date, timedelta
from typing import Set, Tuple

from models import User, Match
from models.competition.services import GaraService, RoundService, InscriptionService
from models.match.services import MatchService, RackService
from models.classification.models import RoundClassification
from models.base import utc_now


@pytest.mark.integration
class TestAntiRematchBug:
    """Test per verificare il bug anti-rematch nell'algoritmo Amalfi.

    Usa i fixture globali isolated_* per evitare problemi di sessione SQLAlchemy.
    Segue il pattern di completare i match nello stesso ciclo in cui vengono letti.
    """

    def _complete_match_simple(
        self, match: Match, winner_racks: int, loser_racks: int, db_session
    ) -> None:
        """Completa un match con risultati semplici.

        Pattern copiato da test_specifications_alignment.py che funziona
        correttamente senza problemi di sessione.
        """
        if match.is_bye:
            return

        winner_id = match.player1_id
        loser_id = match.player2_id

        # Aggiungi rack per il vincitore
        for rack_num in range(1, winner_racks + 1):
            RackService.add_rack_result(
                match_id=match.id,
                rack_number=rack_num,
                winner_id=winner_id,
                reported_by_id=winner_id,
                confirmed_by_player=True,
                validated_by_admin=True,
                bypass_validation=True,  # Necessario per match in stato PENDING
            )

        # Aggiungi rack per il perdente
        for rack_num in range(winner_racks + 1, winner_racks + loser_racks + 1):
            RackService.add_rack_result(
                match_id=match.id,
                rack_number=rack_num,
                winner_id=loser_id,
                reported_by_id=loser_id,
                confirmed_by_player=True,
                validated_by_admin=True,
                bypass_validation=True,  # Necessario per match in stato PENDING
            )

        MatchService.to_completed(match.id)

    def test_anti_rematch_should_prevent_immediate_rematches(
        self, isolated_admin_user: User, isolated_players, db_session
    ):
        """Test che verifica che l'anti-rematch prevenga i reincontri immediati.

        Scenario:
        - 6 giocatori, 3 turni Amalfi
        - Anti-rematch abilitato
        - Nessuna coppia dovrebbe giocare più di una volta
        """
        admin_user = isolated_admin_user
        players_6 = isolated_players[:6]

        # Crea gara con anti-rematch abilitato e distance=5 (race to 5)
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
            discipline="9_ball",
            distance=5,  # Race to 5
            is_race_to=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
            time=utc_now().time(),
        )

        # Iscrivi 6 giocatori
        for player in players_6:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Apri iscrizioni e avvia primo turno
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )
        RoundService.start_first_round(gara.id)

        # Traccia tutti i pairing attraverso i turni
        all_pairings: Set[Tuple[int, int]] = set()

        # Pattern che funziona: completa i match nello stesso ciclo in cui vengono letti
        for round_num in range(1, 4):  # 3 turni
            if round_num > 1:
                # Prima calcola classificazione del turno precedente
                RoundClassification.calculate_classification_after_round(
                    gara.id, round_num - 1
                )
                # Poi crea il turno successivo
                RoundService.create_round_with_strategy(gara.id, round_num)
                gara.current_round = round_num
                db_session.add(gara)
                db_session.commit()

            # Ottieni match del turno corrente
            matches = Match.query.filter_by(
                gara_id=gara.id, round_number=round_num
            ).all()

            round_pairings: Set[Tuple[int, int]] = set()

            for match in matches:
                if not match.is_bye and not match.is_trio:
                    # Normalizza la coppia (ID più piccolo prima)
                    pairing = tuple(sorted([match.player1_id, match.player2_id]))
                    round_pairings.add(pairing)

                    # Completa il match NELLO STESSO CICLO
                    self._complete_match_simple(match, 3, 1, db_session)

            # Verifica: nessun rematch con turni precedenti
            rematches = all_pairings.intersection(round_pairings)
            assert (
                len(rematches) == 0
            ), f"Trovati rematches nel turno {round_num}: {rematches}"

            # Aggiungi i pairing di questo turno al set totale
            all_pairings.update(round_pairings)

        print("\n✅ Anti-rematch test PASSATO!")
        print(f"   - Tutti i {len(all_pairings)} abbinamenti sono unici")
        print("   - Nessun reincontro rilevato nei 3 turni")

    def test_anti_rematch_with_limited_options(
        self, isolated_admin_user: User, isolated_players, db_session
    ):
        """Test edge case: anti-rematch quando le opzioni sono limitate.

        Con 4 giocatori e 2 turni, matematicamente è impossibile evitare tutti i
        rematches
        dopo il secondo turno, ma con solo 2 turni non dovrebbero esserci rematches.
        """
        admin_user = isolated_admin_user
        players_4 = isolated_players[:4]

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
            discipline="9_ball",
            distance=5,  # Race to 5
            is_race_to=True,
            director_id=admin_user.id,
            matchmaking_strategy="amalfi",
            first_round_policy="random",
            odd_number_policy="bye",
            anti_rematch_enabled=True,
            time=utc_now().time(),
        )

        # Iscrivi 4 giocatori
        for player in players_4:
            InscriptionService.inscribe_user(player.id, gara.id)

        # Avvia la gara
        inscription_start = utc_now() - timedelta(hours=1)
        inscription_end = utc_now() + timedelta(hours=1)
        InscriptionService.open_inscriptions(
            gara.id, inscription_start, inscription_end
        )
        RoundService.start_first_round(gara.id)

        # Con 4 giocatori e 2 turni:
        # - Turno 1: 2 match (4 giocatori)
        # - Turno 2: 2 match diversi (possibile con 4 giocatori)
        pairings_by_round = []

        for round_num in range(1, 3):  # 2 turni
            if round_num > 1:
                # Calcola classificazione del turno precedente
                RoundClassification.calculate_classification_after_round(
                    gara.id, round_num - 1
                )
                # Crea turno successivo
                RoundService.create_round_with_strategy(gara.id, round_num)
                gara.current_round = round_num
                db_session.add(gara)
                db_session.commit()

            # Ottieni match del turno corrente
            matches = Match.query.filter_by(
                gara_id=gara.id, round_number=round_num
            ).all()

            round_pairings: Set[Tuple[int, int]] = set()
            for match in matches:
                if not match.is_bye and not match.is_trio:
                    pairing = tuple(sorted([match.player1_id, match.player2_id]))
                    round_pairings.add(pairing)

                    # Completa il match NELLO STESSO CICLO
                    self._complete_match_simple(match, 3, 1, db_session)

            pairings_by_round.append(round_pairings)
            print(f"Turno {round_num}: {len(round_pairings)} match")

        # Verifica: nessun rematch immediato (turni consecutivi)
        for i in range(len(pairings_by_round) - 1):
            current_round_pairings = pairings_by_round[i]
            next_round_pairings = pairings_by_round[i + 1]

            immediate_rematches = current_round_pairings.intersection(
                next_round_pairings
            )

            assert len(immediate_rematches) == 0, (
                f"Trovati {len(immediate_rematches)} rematches immediati "
                f"tra Turno {i+1} e {i+2}: {immediate_rematches}"
            )

        print("✅ Test edge case PASSATO: nessun rematch immediato rilevato!")
