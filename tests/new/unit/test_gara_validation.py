"""
Test per la validazione delle configurazioni gara.

Regole da docs/CLASSIFICATION_SYSTEM.md sezione 9.
"""

import pytest
from models.competition.validators import (
    validate_gara_configuration,
    validate_gara,
    ClassificationSystem,
    DistanceType,
    OddHandling,
    ForfeitPolicy,
    MatchmakingStrategy,
)


class TestRackSystemValidation:
    """Test validazione sistema RACK."""

    def test_rack_with_exactly_n_is_valid(self):
        """RACK + Exactly N = valido."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.RACK,
            distance_type=DistanceType.EXACTLY,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert errors == []

    def test_rack_with_race_to_has_warning(self):
        """RACK + Race to N = warning (distorce la classifica)."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.RACK,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert errors == []
        assert len(warnings) == 1
        assert "race to" in warnings[0].lower() or "distorce" in warnings[0].lower()

    def test_rack_with_multi_set_is_error(self):
        """RACK + multi-set = errore."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.RACK,
            distance_type=DistanceType.EXACTLY,
            distance=5,
            multi_set=True,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert len(errors) == 1
        assert "multi-set" in errors[0].lower() or "multiset" in errors[0].lower()

    def test_rack_with_bye_simple_is_error(self):
        """RACK + Bye semplice = errore (0 rack = penalizzato)."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.RACK,
            distance_type=DistanceType.EXACTLY,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.BYE,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert len(errors) == 1
        assert "bye" in errors[0].lower()

    def test_rack_with_elimination_is_error(self):
        """RACK + Eliminazione = errore."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.RACK,
            distance_type=DistanceType.EXACTLY,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.ELIMINATION,
        )
        assert len(errors) == 1
        assert "eliminazione" in errors[0].lower() or "elimination" in errors[0].lower()

    def test_rack_with_double_ko_is_error(self):
        """RACK + Doppio KO = errore."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.RACK,
            distance_type=DistanceType.EXACTLY,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.DOUBLE_KO,
        )
        assert len(errors) == 1
        assert "doppio" in errors[0].lower() or "double" in errors[0].lower()

    @pytest.mark.parametrize(
        "odd_handling",
        [OddHandling.NO, OddHandling.TRIO, OddHandling.BYE_CHALLENGE, OddHandling.BYE_N_RACK],
    )
    def test_rack_valid_odd_handling(self, odd_handling):
        """RACK + gestione dispari valida."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.RACK,
            distance_type=DistanceType.EXACTLY,
            distance=5,
            multi_set=False,
            odd_handling=odd_handling,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert errors == []

    @pytest.mark.parametrize("matchmaking", [MatchmakingStrategy.RANDOM, MatchmakingStrategy.AMALFI, MatchmakingStrategy.ROUND_ROBIN])
    def test_rack_valid_matchmaking(self, matchmaking):
        """RACK + matchmaking valido (Random/Amalfi/RR)."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.RACK,
            distance_type=DistanceType.EXACTLY,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=matchmaking,
        )
        assert errors == []


class TestWinsSystemValidation:
    """Test validazione sistema WINS."""

    def test_wins_with_race_to_is_valid(self):
        """WINS + Race to N = valido."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.WINS,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert errors == []

    def test_wins_with_exactly_odd_is_valid(self):
        """WINS + Exactly N (dispari) = valido."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.WINS,
            distance_type=DistanceType.EXACTLY,
            distance=5,  # dispari
            multi_set=False,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert errors == []

    def test_wins_with_exactly_even_is_valid_with_warning(self):
        """WINS + Exactly N (pari) = valido con warning (pareggi possibili)."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.WINS,
            distance_type=DistanceType.EXACTLY,
            distance=4,  # pari
            multi_set=False,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert errors == []
        # Warning opzionale per pareggi, ma non errore

    def test_wins_with_multi_set_is_valid(self):
        """WINS + multi-set = valido."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.WINS,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=True,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert errors == []

    def test_wins_with_bye_simple_is_valid(self):
        """WINS + Bye semplice = valido."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.WINS,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.BYE,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert errors == []

    def test_wins_with_elimination_is_error(self):
        """WINS + Eliminazione = errore."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.WINS,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.ELIMINATION,
        )
        assert len(errors) == 1

    @pytest.mark.parametrize(
        "odd_handling",
        [OddHandling.NO, OddHandling.TRIO, OddHandling.BYE, OddHandling.BYE_CHALLENGE],
    )
    def test_wins_valid_odd_handling(self, odd_handling):
        """WINS + gestione dispari valida (NO/Trio/Bye/Bye+Challenge)."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.WINS,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=False,
            odd_handling=odd_handling,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert errors == []

    def test_wins_with_bye_n_rack_is_error(self):
        """WINS + Bye+N rack = errore (N/A per WINS)."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.WINS,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.BYE_N_RACK,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert len(errors) == 1


class TestPositionSystemValidation:
    """Test validazione sistema POSITION."""

    def test_position_with_race_to_is_valid(self):
        """POSITION + Race to N = valido."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.POSITION,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.BRACKET_BYE,
            forfeit_policy=ForfeitPolicy.FORFEIT,
            matchmaking=MatchmakingStrategy.ELIMINATION,
        )
        assert errors == []

    def test_position_with_exactly_odd_is_valid(self):
        """POSITION + Exactly N (dispari) = valido."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.POSITION,
            distance_type=DistanceType.EXACTLY,
            distance=5,  # dispari
            multi_set=False,
            odd_handling=OddHandling.BRACKET_BYE,
            forfeit_policy=ForfeitPolicy.FORFEIT,
            matchmaking=MatchmakingStrategy.ELIMINATION,
        )
        assert errors == []

    def test_position_with_exactly_even_is_error(self):
        """POSITION + Exactly N (pari) = errore (pareggi non ammessi)."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.POSITION,
            distance_type=DistanceType.EXACTLY,
            distance=4,  # pari
            multi_set=False,
            odd_handling=OddHandling.BRACKET_BYE,
            forfeit_policy=ForfeitPolicy.FORFEIT,
            matchmaking=MatchmakingStrategy.ELIMINATION,
        )
        assert len(errors) == 1
        assert "pari" in errors[0].lower() or "even" in errors[0].lower()

    def test_position_with_exclude_is_error(self):
        """POSITION + EXCLUDE = errore (solo FORFEIT)."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.POSITION,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.BRACKET_BYE,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.ELIMINATION,
        )
        assert len(errors) == 1
        assert "exclude" in errors[0].lower() or "forfeit" in errors[0].lower()

    def test_position_with_random_is_error(self):
        """POSITION + Random = errore."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.POSITION,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.BRACKET_BYE,
            forfeit_policy=ForfeitPolicy.FORFEIT,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert len(errors) == 1

    def test_position_with_amalfi_is_error(self):
        """POSITION + Amalfi = errore."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.POSITION,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.BRACKET_BYE,
            forfeit_policy=ForfeitPolicy.FORFEIT,
            matchmaking=MatchmakingStrategy.AMALFI,
        )
        assert len(errors) == 1

    def test_position_with_round_robin_is_error(self):
        """POSITION + Round Robin = errore."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.POSITION,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.BRACKET_BYE,
            forfeit_policy=ForfeitPolicy.FORFEIT,
            matchmaking=MatchmakingStrategy.ROUND_ROBIN,
        )
        assert len(errors) == 1

    @pytest.mark.parametrize("matchmaking", [MatchmakingStrategy.ELIMINATION, MatchmakingStrategy.DOUBLE_KO])
    def test_position_valid_matchmaking(self, matchmaking):
        """POSITION + matchmaking valido (Eliminazione/Doppio KO)."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.POSITION,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=False,
            odd_handling=OddHandling.BRACKET_BYE,
            forfeit_policy=ForfeitPolicy.FORFEIT,
            matchmaking=matchmaking,
        )
        assert errors == []

    def test_position_with_multi_set_is_valid(self):
        """POSITION + multi-set = valido."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.POSITION,
            distance_type=DistanceType.RACE_TO,
            distance=5,
            multi_set=True,
            odd_handling=OddHandling.BRACKET_BYE,
            forfeit_policy=ForfeitPolicy.FORFEIT,
            matchmaking=MatchmakingStrategy.ELIMINATION,
        )
        assert errors == []


class TestTrioValidation:
    """Test validazione Trio."""

    @pytest.mark.parametrize("distance", [2, 3, 4, 5])
    def test_trio_valid_distances(self, distance):
        """Trio con distanza 2-5 = valido."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.RACK,
            distance_type=DistanceType.EXACTLY,
            distance=distance,
            multi_set=False,
            odd_handling=OddHandling.TRIO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert errors == []

    @pytest.mark.parametrize("distance", [1, 6, 7, 8, 9, 10])
    def test_trio_invalid_distances(self, distance):
        """Trio con distanza <2 o >5 = errore."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.RACK,
            distance_type=DistanceType.EXACTLY,
            distance=distance,
            multi_set=False,
            odd_handling=OddHandling.TRIO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert len(errors) == 1
        assert "trio" in errors[0].lower() or "distanza" in errors[0].lower()


class TestMultipleErrors:
    """Test configurazioni con errori multipli."""

    def test_rack_with_multiple_errors(self):
        """RACK + multi-set + Bye semplice + Eliminazione = 3 errori."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.RACK,
            distance_type=DistanceType.EXACTLY,
            distance=5,
            multi_set=True,
            odd_handling=OddHandling.BYE,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.ELIMINATION,
        )
        assert len(errors) == 3

    def test_position_with_multiple_errors(self):
        """POSITION + Exactly N pari + EXCLUDE + Amalfi = 3 errori."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.POSITION,
            distance_type=DistanceType.EXACTLY,
            distance=4,
            multi_set=False,
            odd_handling=OddHandling.BRACKET_BYE,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.AMALFI,
        )
        assert len(errors) == 3


class TestEdgeCases:
    """Test casi limite."""

    def test_minimum_valid_distance(self):
        """Distanza minima valida = 1."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.WINS,
            distance_type=DistanceType.RACE_TO,
            distance=1,
            multi_set=False,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert errors == []

    def test_zero_distance_is_error(self):
        """Distanza 0 = errore."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.WINS,
            distance_type=DistanceType.RACE_TO,
            distance=0,
            multi_set=False,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert len(errors) == 1

    def test_negative_distance_is_error(self):
        """Distanza negativa = errore."""
        errors, warnings = validate_gara_configuration(
            classification_system=ClassificationSystem.WINS,
            distance_type=DistanceType.RACE_TO,
            distance=-1,
            multi_set=False,
            odd_handling=OddHandling.NO,
            forfeit_policy=ForfeitPolicy.EXCLUDE,
            matchmaking=MatchmakingStrategy.RANDOM,
        )
        assert len(errors) == 1


class TestValidateGaraIntegration:
    """Test integrazione validate_gara con oggetti Gara mock."""

    def test_validate_gara_with_amalfi_strategy(self):
        """Gara Amalfi viene validata come WINS."""

        class MockGara:
            matchmaking_strategy = "amalfi"
            odd_number_policy = "bye"
            is_race_to = True
            is_multi_set = False
            distance = 5

        errors, warnings = validate_gara(MockGara())
        assert errors == []

    def test_validate_gara_with_elimination_strategy(self):
        """Gara Eliminazione viene validata come POSITION."""

        class MockGara:
            matchmaking_strategy = "direct_elimination"
            odd_number_policy = "bye"
            is_race_to = True
            is_multi_set = False
            distance = 5

        errors, warnings = validate_gara(MockGara())
        assert errors == []

    def test_validate_gara_elimination_with_even_exactly_is_error(self):
        """Gara Eliminazione + Exactly pari = errore."""

        class MockGara:
            matchmaking_strategy = "direct_elimination"
            odd_number_policy = "bye"
            is_race_to = False  # Exactly
            is_multi_set = False
            distance = 4  # pari

        errors, warnings = validate_gara(MockGara())
        assert len(errors) == 1
        assert "pari" in errors[0].lower()

    def test_validate_gara_rack_system_with_multi_set_is_error(self):
        """Gara RACK + multi-set = errore."""

        class MockGara:
            matchmaking_strategy = "amalfi"
            odd_number_policy = "bye"
            is_race_to = False
            is_multi_set = True
            distance = 5

        errors, warnings = validate_gara(
            MockGara(), classification_system=ClassificationSystem.RACK
        )
        assert len(errors) >= 1
        assert any("multi-set" in e.lower() for e in errors)

    def test_validate_gara_infers_position_from_double_ko(self):
        """Double KO viene mappato a POSITION automaticamente."""

        class MockGara:
            matchmaking_strategy = "double_knockout"
            odd_number_policy = "bye"
            is_race_to = True
            is_multi_set = True  # POSITION supporta multi-set
            distance = 5

        errors, warnings = validate_gara(MockGara())
        # POSITION + Eliminazione è valido
        assert errors == []

    def test_validate_gara_with_trio_valid_distance(self):
        """Trio con distanza 2-5 è valido."""

        class MockGara:
            matchmaking_strategy = "random"
            odd_number_policy = "trio"
            is_race_to = True
            is_multi_set = False
            distance = 3

        errors, warnings = validate_gara(MockGara())
        assert errors == []

    def test_validate_gara_with_trio_invalid_distance(self):
        """Trio con distanza > 5 è errore."""

        class MockGara:
            matchmaking_strategy = "random"
            odd_number_policy = "trio"
            is_race_to = True
            is_multi_set = False
            distance = 7

        errors, warnings = validate_gara(MockGara())
        assert len(errors) == 1
        assert "trio" in errors[0].lower()
