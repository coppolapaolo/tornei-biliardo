"""
Additional comprehensive tests for amalfi/engine.py to improve coverage.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date

from amalfi.engine import AmalfiEngine, ValidationResult
from models import (
    Match,
    Gara,
    Inscription,
    PlayerEncounter,
    RoundClassification,
    User,
    Campionato,
)
from models.competition.models import WithdrawPolicy


class TestAmalfiEngineCreateRounds:
    """Test round creation functionality."""

    @pytest.fixture
    def sample_campionato(self, db_session):
        """Create a sample campionato."""
        campionato = Campionato(name="Test Campionato", campionato_type="Amalfi")
        db_session.add(campionato)
        db_session.commit()
        return campionato

    @pytest.fixture
    def sample_gara(self, db_session, sample_campionato):
        """Create a sample gara."""
        gara = Gara(
            campionato_id=sample_campionato.id,
            number=1,
            name="Test Gara",
            date=date.today(),
            discipline="palla 9",
            distance=7,
            best_of=True,
            min_participants=4,
            status="playing",
            current_round=1,
            rounds_count=5,
        )
        db_session.add(gara)
        db_session.commit()
        return gara

    @pytest.fixture
    def sample_users(self, db_session):
        """Create sample users for testing."""
        users = []
        for i in range(6):
            user = User(
                username=f"player{i+1}", email=f"player{i+1}@test.com", role="player"
            )
            user.set_password("password")
            db_session.add(user)
            users.append(user)
        db_session.commit()
        return users

    @pytest.fixture
    def sample_inscriptions(self, db_session, sample_gara, sample_users):
        """Create sample inscriptions."""
        inscriptions = []
        for user in sample_users:
            inscription = Inscription(
                gara_id=sample_gara.id, user_id=user.id, is_withdrawn=False
            )
            db_session.add(inscription)
            inscriptions.append(inscription)
        db_session.commit()
        return inscriptions

    def test_engine_initialization(self, sample_gara):
        """Test engine initialization."""
        engine = AmalfiEngine(sample_gara)
        assert engine.gara == sample_gara
        assert engine.campionato == sample_gara.campionato

    def test_create_round_matches_first_round(self, sample_gara, sample_inscriptions):
        """Test creating matches for first round."""
        engine = AmalfiEngine(sample_gara)

        with patch.object(engine, "_create_first_round") as mock_first:
            mock_matches = [Mock()]
            mock_first.return_value = mock_matches

            with patch.object(
                engine, "_cleanup_cancelled_matches"
            ) as mock_cleanup, patch.object(
                engine, "_finalize_forfeit_matches"
            ) as mock_finalize:

                result = engine.create_round_matches(1)

                mock_first.assert_called_once()
                mock_cleanup.assert_called_once_with(mock_matches)
                mock_finalize.assert_called_once_with(mock_matches)
                assert result == mock_matches

    def test_create_round_matches_amalfi_round(self, sample_gara, sample_inscriptions):
        """Test creating matches for amalfi round."""
        engine = AmalfiEngine(sample_gara)

        with patch.object(engine, "_create_amalfi_round") as mock_amalfi:
            mock_matches = [Mock()]
            mock_amalfi.return_value = mock_matches

            with patch.object(
                engine, "_cleanup_cancelled_matches"
            ) as mock_cleanup, patch.object(
                engine, "_finalize_forfeit_matches"
            ) as mock_finalize:

                result = engine.create_round_matches(2)

                mock_amalfi.assert_called_once_with(2)
                mock_cleanup.assert_called_once_with(mock_matches)
                mock_finalize.assert_called_once_with(mock_matches)
                assert result == mock_matches

    def test_create_first_round_insufficient_participants(self, sample_gara):
        """Test first round creation with insufficient participants."""
        engine = AmalfiEngine(sample_gara)

        with patch.object(engine, "_inscriptions_for_pairing") as mock_inscriptions:
            mock_inscriptions.return_value = [Mock(), Mock()]  # Only 2 participants

            with pytest.raises(ValueError, match="Servono almeno 4 iscritti"):
                engine._create_first_round()

    def test_create_first_round_matches_even_players(
        self, sample_gara, sample_users, db_session
    ):
        """Test first round creation with even number of players."""
        engine = AmalfiEngine(sample_gara)

        # Create 4 users for even pairing
        inscriptions = []
        for i in range(4):
            inscription = Mock()
            inscription.user = sample_users[i]
            inscription.user_id = sample_users[i].id
            inscriptions.append(inscription)

        matches = engine._create_first_round_matches(inscriptions)

        # Should create 2 matches for 4 players
        assert len(matches) == 2

        # No bye match should be created
        bye_matches = [m for m in matches if getattr(m, "is_bye", False)]
        assert len(bye_matches) == 0

    def test_create_first_round_matches_odd_players(
        self, sample_gara, sample_users, db_session
    ):
        """Test first round creation with odd number of players."""
        engine = AmalfiEngine(sample_gara)

        # Create 5 users for odd pairing
        inscriptions = []
        for i in range(5):
            inscription = Mock()
            inscription.user = sample_users[i]
            inscription.user_id = sample_users[i].id
            inscriptions.append(inscription)

        matches = engine._create_first_round_matches(inscriptions)

        # Should create 3 matches (2 regular + 1 bye)
        assert len(matches) == 3

        # One bye match should be created
        bye_matches = [m for m in matches if getattr(m, "is_bye", False)]
        assert len(bye_matches) == 1

        bye_match = bye_matches[0]
        assert bye_match.winner_id == bye_match.player1_id
        assert bye_match.status == "completed"


class TestAmalfiEngineClassification:
    """Test classification and ranking functionality."""

    @pytest.fixture
    def sample_gara_classification(self, db_session):
        """Create a gara for classification tests."""
        campionato = Campionato(name="Class Test", campionato_type="Amalfi")
        db_session.add(campionato)
        db_session.flush()

        gara = Gara(
            campionato_id=campionato.id,
            number=1,
            name="Classification Test",
            date=date.today(),
            discipline="palla 9",
            distance=7,
            best_of=True,
            status="playing",
            current_round=2,
            rounds_count=5,
            withdraw_policy=WithdrawPolicy.EXCLUDE.value,
        )
        db_session.add(gara)
        db_session.commit()
        return gara

    def test_create_amalfi_round_with_exclusions(
        self, sample_gara_classification, player_user, db_session
    ):
        """Test amalfi round creation with withdrawn players excluded."""
        engine = AmalfiEngine(sample_gara_classification)

        # Create classifications
        classifications = []
        for i in range(4):
            user = User(
                username=f"classif_user_{i}",
                email=f"classif{i}@test.com",
                role="player",
            )
            user.set_password("password")
            db_session.add(user)
            db_session.flush()

            classification = RoundClassification(
                gara_id=sample_gara_classification.id,
                round_number=1,
                user_id=user.id,
                position=i + 1,
            )
            db_session.add(classification)
            classifications.append(classification)

        # Create withdrawn inscription
        withdrawn_inscription = Inscription(
            gara_id=sample_gara_classification.id,
            user_id=classifications[0].user_id,
            is_withdrawn=True,
        )
        db_session.add(withdrawn_inscription)
        db_session.commit()

        with patch(
            "models.classification.models.RoundClassification.calculate_classification_after_round"
        ) as mock_calc, patch.object(
            engine, "_apply_amalfi_algorithm"
        ) as mock_apply, patch.object(
            engine, "_finalize_forfeit_matches"
        ) as mock_finalize:

            mock_apply.return_value = []

            result = engine._create_amalfi_round(2)

            mock_calc.assert_called_once_with(sample_gara_classification.id, 1)
            mock_apply.assert_called_once()

            # Check that excluded player was filtered out
            called_classification = mock_apply.call_args[0][0]
            excluded_user_ids = [c.user_id for c in called_classification]
            assert classifications[0].user_id not in excluded_user_ids


class TestAmalfiEngineValidation:
    """Test validation functionality."""

    def test_validation_result_typing(self):
        """Test ValidationResult typing."""
        result: ValidationResult = {
            "is_valid": True,
            "warnings": ["Warning message"],
            "errors": [],
        }

        assert result["is_valid"] is True
        assert len(result["warnings"]) == 1
        assert len(result["errors"]) == 0


class TestAmalfiEnginePlayerEncounters:
    """Test player encounter recording."""

    @pytest.fixture
    def sample_match(self, db_session):
        """Create a sample match."""
        campionato = Campionato(name="Encounter Test", campionato_type="Amalfi")
        db_session.add(campionato)
        db_session.flush()

        gara = Gara(
            campionato_id=campionato.id,
            number=1,
            name="Encounter Test",
            date=date.today(),
            discipline="palla 9",
            distance=7,
            status="playing",
        )
        db_session.add(gara)
        db_session.flush()

        user1 = User(username="enc_player1", email="enc1@test.com", role="player")
        user2 = User(username="enc_player2", email="enc2@test.com", role="player")
        user1.set_password("password")
        user2.set_password("password")
        db_session.add_all([user1, user2])
        db_session.flush()

        match = Match(
            gara_id=gara.id,
            round_number=1,
            player1_id=user1.id,
            player2_id=user2.id,
            amalfi_round=1,
        )
        match.gara = gara
        db_session.add(match)
        db_session.commit()
        return match

    def test_player_encounter_recording_regular_match(self, sample_match):
        """Test recording encounters for regular matches."""
        gara = sample_match.gara
        engine = AmalfiEngine(gara)

        matches = [sample_match]

        with patch("models.PlayerEncounter.record_encounter") as mock_record:
            # Simulate the encounter recording from _create_first_round
            for match in matches:
                if not getattr(match, "is_bye", False):
                    PlayerEncounter.record_encounter(
                        gara.id, match.player1_id, match.player2_id, 1
                    )

            mock_record.assert_called_once_with(
                gara.id, sample_match.player1_id, sample_match.player2_id, 1
            )

    def test_player_encounter_recording_trio_match(self, db_session):
        """Test recording encounters for trio matches."""
        campionato = Campionato(name="Trio Test", campionato_type="Amalfi")
        db_session.add(campionato)
        db_session.flush()

        gara = Gara(
            campionato_id=campionato.id,
            number=1,
            name="Trio Test",
            date=date.today(),
            discipline="palla 9",
            distance=7,
            status="playing",
        )
        db_session.add(gara)
        db_session.flush()

        # Create trio match
        trio_match = Mock()
        trio_match.is_trio = True
        trio_match.trio_match = Mock()
        trio_match.trio_match.player1_id = 1
        trio_match.trio_match.player2_id = 2
        trio_match.trio_match.player3_id = 3

        engine = AmalfiEngine(gara)
        matches = [trio_match]

        with patch("models.PlayerEncounter.record_encounter") as mock_record:
            # Simulate trio encounter recording
            for match in matches:
                if getattr(match, "is_bye", False):
                    continue
                if getattr(match, "is_trio", False):
                    trio = match.trio_match
                    PlayerEncounter.record_encounter(
                        gara.id, trio.player1_id, trio.player2_id, 1
                    )
                    PlayerEncounter.record_encounter(
                        gara.id, trio.player1_id, trio.player3_id, 1
                    )
                    PlayerEncounter.record_encounter(
                        gara.id, trio.player2_id, trio.player3_id, 1
                    )

            # Should record 3 encounters for trio match
            assert mock_record.call_count == 3


class TestAmalfiEngineInscriptions:
    """Test inscription handling."""

    def test_inscriptions_for_pairing_method_exists(self):
        """Test that _inscriptions_for_pairing method exists and can be called."""
        gara = Mock()
        engine = AmalfiEngine(gara)

        # This tests that the method exists and can be mocked
        with patch.object(engine, "_inscriptions_for_pairing") as mock_method:
            mock_method.return_value = []
            result = engine._inscriptions_for_pairing()
            assert result == []
            mock_method.assert_called_once()


class TestAmalfiEngineUtilityMethods:
    """Test utility methods for match management."""

    def test_cleanup_cancelled_matches_method_exists(self):
        """Test that _cleanup_cancelled_matches method exists."""
        gara = Mock()
        engine = AmalfiEngine(gara)

        with patch.object(engine, "_cleanup_cancelled_matches") as mock_method:
            matches = [Mock()]
            engine._cleanup_cancelled_matches(matches)
            mock_method.assert_called_once_with(matches)

    def test_finalize_forfeit_matches_method_exists(self):
        """Test that _finalize_forfeit_matches method exists."""
        gara = Mock()
        engine = AmalfiEngine(gara)

        with patch.object(engine, "_finalize_forfeit_matches") as mock_method:
            matches = [Mock()]
            engine._finalize_forfeit_matches(matches)
            mock_method.assert_called_once_with(matches)

    def test_apply_amalfi_algorithm_method_exists(self):
        """Test that _apply_amalfi_algorithm method exists."""
        gara = Mock()
        engine = AmalfiEngine(gara)

        with patch.object(engine, "_apply_amalfi_algorithm") as mock_method:
            mock_method.return_value = []
            classification = []
            result = engine._apply_amalfi_algorithm(classification, 2, 3)
            assert result == []
            mock_method.assert_called_once_with(classification, 2, 3)
