"""
Test ProvaService validation with type safety
File: tests/test_prova_service_validation.py
"""

from models.competition.services import ProvaService


class TestProvaServiceValidation:
    """Test ProvaService.validate_prova_data with various input types."""

    def test_validate_with_html_form_strings(self):
        """Test validation with string inputs as from HTML forms."""
        data = {
            "name": "Test Prova",
            "discipline": "palla_8",
            "distance": "9",  # String as from HTML
            "number": "1",
            "min_participants": "4",
            "max_participants": "16",
            "rounds_count": "3",
            "entry_fee": "10.50",
        }

        errors = ProvaService.validate_prova_data(data)
        assert errors == {}, f"Unexpected errors: {errors}"

    def test_validate_with_native_types(self):
        """Test validation with native Python types."""
        data = {
            "name": "Test Prova",
            "discipline": "palla_9",
            "distance": 7,  # Native int
            "number": 2,
            "min_participants": 4,
            "max_participants": 16,
        }

        errors = ProvaService.validate_prova_data(data)
        assert errors == {}

    def test_validate_mixed_types(self):
        """Test validation with mixed string and native types."""
        data = {
            "name": "Mixed Test",
            "discipline": "palla_8",
            "distance": "9",  # String
            "min_participants": 4,  # Int
            "max_participants": "16",  # String
            "entry_fee": 15.5,  # Float
        }

        errors = ProvaService.validate_prova_data(data)
        assert errors == {}

    def test_validate_invalid_distance(self):
        """Test various invalid distance inputs."""
        # Non-numeric string
        data1 = {"name": "Test", "discipline": "palla_8", "distance": "abc"}
        errors = ProvaService.validate_prova_data(data1)
        assert "distance" in errors
        assert "non valida" in errors["distance"]

        # Zero distance
        data2 = {"name": "Test", "discipline": "palla_8", "distance": "0"}
        errors = ProvaService.validate_prova_data(data2)
        assert "distance" in errors
        assert "almeno 1" in errors["distance"]

        # Negative distance
        data3 = {"name": "Test", "discipline": "palla_8", "distance": -5}
        errors = ProvaService.validate_prova_data(data3)
        assert "distance" in errors

    def test_validate_participants_logic(self):
        """Test min/max participants validation logic."""
        # Max less than min
        data1 = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "9",
            "min_participants": "10",
            "max_participants": "5",
        }
        errors = ProvaService.validate_prova_data(data1)
        assert "max_participants" in errors
        assert ">= min" in errors["max_participants"]

        # Min less than 2
        data2 = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "9",
            "min_participants": "1",
        }
        errors = ProvaService.validate_prova_data(data2)
        assert "min_participants" in errors
        assert "Minimo 2" in errors["min_participants"]

    def test_validate_inscription_dates(self):
        """Test inscription date validation."""
        # End before start
        data = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "9",
            "inscription_start": "2025-08-20",
            "inscription_end": "2025-08-10",
        }
        errors = ProvaService.validate_prova_data(data)
        assert "inscription_end" in errors
        assert ">= della data di inizio" in errors["inscription_end"]

        # Invalid date format
        data2 = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "9",
            "inscription_start": "not-a-date",
            "inscription_end": "2025-08-10",
        }
        errors = ProvaService.validate_prova_data(data2)
        assert "inscription_start" in errors

    def test_validate_missing_required_fields(self):
        """Test validation with missing required fields."""
        data = {}
        errors = ProvaService.validate_prova_data(data)

        assert "name" in errors
        assert "discipline" in errors
        assert "distance" in errors
        assert len(errors) == 3  # Only these 3 are required

    def test_validate_entry_fee(self):
        """Test entry fee validation."""
        # Valid string fee
        data1 = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "9",
            "entry_fee": "15.50",
        }
        errors = ProvaService.validate_prova_data(data1)
        assert "entry_fee" not in errors

        # Valid float fee
        data2 = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "9",
            "entry_fee": 20.0,
        }
        errors = ProvaService.validate_prova_data(data2)
        assert "entry_fee" not in errors

        # Negative fee
        data3 = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "9",
            "entry_fee": "-5",
        }
        errors = ProvaService.validate_prova_data(data3)
        assert "entry_fee" in errors
        assert "negativa" in errors["entry_fee"]

        # Invalid fee
        data4 = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "9",
            "entry_fee": "gratis",
        }
        errors = ProvaService.validate_prova_data(data4)
        assert "entry_fee" in errors
        assert "numero valido" in errors["entry_fee"]

    def test_validate_rounds_count(self):
        """Test rounds count validation."""
        # Valid
        data1 = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "9",
            "rounds_count": "5",
        }
        errors = ProvaService.validate_prova_data(data1)
        assert "rounds_count" not in errors

        # Invalid
        data2 = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "9",
            "rounds_count": "0",
        }
        errors = ProvaService.validate_prova_data(data2)
        assert "rounds_count" in errors

    def test_validate_prova_number(self):
        """Test prova number validation."""
        # Valid
        data1 = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "9",
            "number": "3",
        }
        errors = ProvaService.validate_prova_data(data1)
        assert "number" not in errors

        # Invalid
        data2 = {
            "name": "Test",
            "discipline": "palla_8",
            "distance": "9",
            "number": "0",
        }
        errors = ProvaService.validate_prova_data(data2)
        assert "number" in errors
        assert "almeno 1" in errors["number"]

    def test_validate_empty_strings(self):
        """Test that empty strings are handled correctly."""
        data = {
            "name": "",  # Empty string
            "discipline": "   ",  # Whitespace only
            "distance": "",
        }
        errors = ProvaService.validate_prova_data(data)

        assert "name" in errors
        assert "discipline" in errors
        assert "distance" in errors
