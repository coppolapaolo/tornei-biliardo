"""
Test classification domain functionality with database

Author: Refactoring Phase 2 - Sprint 1
Created: 2025-08-06
"""

import pytest
from datetime import date, timedelta  # AGGIUNGI QUESTO IMPORT
from models import (
    db,
    User,
    Tournament,
    Prova,
    Match,
    Classification,
    RoundClassification,
    PlayerEncounter,
)
from models.classification.services import (
    ClassificationService,
    RoundClassificationService,
    PlayerEncounterService,
)


def test_player_encounter_functionality(app):
    """Test PlayerEncounter recording and querying"""
    with app.app_context():
        # Create test data
        tournament = Tournament(
            name="Test Tournament", tournament_type="Amalfi", is_active=True
        )
        db.session.add(tournament)
        db.session.commit()

        prova = Prova(
            tournament_id=tournament.id,
            name="Test Prova",
            number=1,
            rounds_count=3,
            discipline="palla 8",  # Campo obbligatorio
            distance=5,  # Campo obbligatorio
            date=date.today(),  # Campo obbligatorio (usa date, non datetime)
        )
        db.session.add(prova)

        # Create players
        player1 = User(username="player1", email="p1@test.com", role="player")
        player1.set_password("test123")
        player2 = User(username="player2", email="p2@test.com", role="player")
        player2.set_password("test123")
        player3 = User(username="player3", email="p3@test.com", role="player")
        player3.set_password("test123")

        db.session.add_all([player1, player2, player3])
        db.session.commit()

        # Test encounter recording
        PlayerEncounter.record_encounter(
            prova_id=prova.id,
            player1_id=player1.id,
            player2_id=player2.id,
            round_number=1,
        )

        # Test have_played method
        assert PlayerEncounter.have_played(prova.id, player1.id, player2.id) == True
        assert PlayerEncounter.have_played(prova.id, player1.id, player3.id) == False
        assert PlayerEncounter.have_played(prova.id, player2.id, player3.id) == False

        # Test service methods
        encounters = PlayerEncounterService.get_player_encounters(prova.id, player1.id)
        assert len(encounters) == 1

        available = PlayerEncounterService.get_available_opponents(
            prova.id, player1.id, [player2.id, player3.id]
        )
        assert player3.id in available
        assert player2.id not in available


def test_round_classification_functionality(app):
    """Test RoundClassification calculation and retrieval"""
    with app.app_context():
        # Create test tournament and prova
        tournament = Tournament(
            name="Test Tournament", tournament_type="Amalfi", is_active=True
        )
        db.session.add(tournament)
        db.session.commit()

        prova = Prova(
            tournament_id=tournament.id,
            name="Test Prova",
            number=1,
            current_round=1,
            # Aggiungi campi obbligatori
            date=date.today(),
            discipline="palla 8",
            distance=5,
            rounds_count=3,
        )
        db.session.add(prova)

        # Create 4 players
        players = []
        for i in range(4):
            player = User(username=f"player{i}", email=f"p{i}@test.com", role="player")
            player.set_password("test123")
            players.append(player)
            db.session.add(player)

        db.session.commit()

        # Create matches for round 1
        match1 = Match(
            prova_id=prova.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            player1_score=4,
            player2_score=2,
            status="completed",
        )

        match2 = Match(
            prova_id=prova.id,
            round_number=1,
            player1_id=players[2].id,
            player2_id=players[3].id,
            player1_score=3,
            player2_score=4,
            status="completed",
        )

        db.session.add_all([match1, match2])
        db.session.commit()

        # Calculate round classification
        RoundClassification.calculate_classification_after_round(prova.id, 1)

        # Get standings
        standings = RoundClassificationService.get_round_standings(prova.id, 1)

        assert len(standings) == 4
        assert standings[0].user_id == players[0].id  # Winner of match1
        assert standings[0].matches_won == 1
        assert standings[0].rack_difference == 2
        assert standings[1].user_id == players[3].id  # Winner of match2
        assert standings[1].matches_won == 1
        assert standings[1].rack_difference == 1

        # Test player progression
        progression = RoundClassificationService.get_player_progression(
            prova.id, players[0].id
        )
        assert len(progression) == 1
        assert progression[0].position == 1


def test_tournament_classification_functionality(app):
    """Test Tournament Classification updates"""
    with app.app_context():
        # Create tournament
        tournament = Tournament(
            name="Test Tournament", tournament_type="Amalfi", is_active=True
        )
        db.session.add(tournament)
        db.session.commit()

        # Create players
        players = []
        for i in range(3):
            player = User(username=f"player{i}", email=f"p{i}@test.com", role="player")
            player.set_password("test123")
            players.append(player)
            db.session.add(player)

        db.session.commit()

        # Create 2 provas with matches
        for prova_num in range(2):
            prova = Prova(
                tournament_id=tournament.id,
                name=f"Prova {prova_num+1}",
                number=prova_num + 1,
                # Aggiungi campi obbligatori
                date=date.today() + timedelta(days=prova_num * 7),
                discipline="palla 8",
                distance=5,
                rounds_count=3,
            )
            db.session.add(prova)
            db.session.commit()

            # Player0 wins against player1
            match1 = Match(
                prova_id=prova.id,
                round_number=1,
                player1_id=players[0].id,
                player2_id=players[1].id,
                player1_score=4,
                player2_score=2,
                status="completed",
            )

            # Player2 has BYE
            match2 = Match(
                prova_id=prova.id,
                round_number=1,
                player1_id=players[2].id,
                player2_id=None,
                is_bye=True,
                status="completed",
            )

            db.session.add_all([match1, match2])

        db.session.commit()

        # Update tournament classification
        classifications = ClassificationService.update_tournament_classification(
            tournament.id
        )

        assert len(classifications) == 2  # Only players who played

        # Get standings
        standings = ClassificationService.get_tournament_standings(tournament.id)

        assert standings[0].user_id == players[0].id
        assert standings[0].total_matches_won == 2
        assert standings[0].total_point_difference == 4
        assert standings[0].provas_played == 2

        # Get specific player ranking
        player_rank = ClassificationService.get_player_ranking(
            tournament.id, players[0].id
        )
        assert player_rank.position == 1

        # Player without matches should not have classification
        no_rank = ClassificationService.get_player_ranking(tournament.id, players[2].id)
        assert no_rank is None


def test_classification_with_ties(app):
    """Test classification handling with tied players"""
    with app.app_context():
        # Create tournament and prova
        tournament = Tournament(
            name="Test Tournament", tournament_type="Amalfi", is_active=True
        )
        db.session.add(tournament)
        db.session.commit()

        prova = Prova(
            tournament_id=tournament.id,
            name="Test Prova",
            number=1,
            # Aggiungi campi obbligatori
            date=date.today(),
            discipline="palla 9",
            distance=7,
            rounds_count=3,
        )
        db.session.add(prova)

        # Create 4 players
        players = []
        for i in range(4):
            player = User(username=f"player{i}", email=f"p{i}@test.com", role="player")
            player.set_password("test123")
            players.append(player)
            db.session.add(player)

        db.session.commit()

        # Create matches with tied results
        # Both matches end 4-2
        match1 = Match(
            prova_id=prova.id,
            round_number=1,
            player1_id=players[0].id,
            player2_id=players[1].id,
            player1_score=4,
            player2_score=2,
            status="completed",
        )

        match2 = Match(
            prova_id=prova.id,
            round_number=1,
            player1_id=players[2].id,
            player2_id=players[3].id,
            player1_score=4,
            player2_score=2,
            status="completed",
        )

        db.session.add_all([match1, match2])
        db.session.commit()

        # Calculate classification
        RoundClassification.calculate_classification_after_round(prova.id, 1)

        standings = RoundClassificationService.get_round_standings(prova.id, 1)

        # Winners should be tied (both 1 win, +2 rack difference)
        # Order determined by player ID
        assert standings[0].matches_won == 1
        assert standings[0].rack_difference == 2
        assert standings[1].matches_won == 1
        assert standings[1].rack_difference == 2

        # Losers should also be tied
        assert standings[2].matches_won == 0
        assert standings[2].rack_difference == -2
        assert standings[3].matches_won == 0
        assert standings[3].rack_difference == -2
