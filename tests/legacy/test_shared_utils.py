"""
Test module for models/shared/utils.py
"""

from datetime import datetime
from models.shared.utils import (
    parse_date_string,
    format_datetime_for_display,
    validate_email,
    calculate_rack_difference,
    safe_get_attr,
    merge_dicts,
)


class TestSharedUtils:
    """Test cases for shared utilities."""

    def test_parse_date_string_valid_formats(self):
        """Test parse_date_string with valid date formats."""
        # Test ISO format
        result = parse_date_string("2023-01-15")
        assert isinstance(result, datetime)
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 15

        # Test datetime format
        result = parse_date_string("2023-01-15 14:30:00")
        assert isinstance(result, datetime)
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30

        # Test Italian format
        result = parse_date_string("15/01/2023")
        assert isinstance(result, datetime)
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 15

        # Test Italian format with time
        result = parse_date_string("15/01/2023 14:30")
        assert isinstance(result, datetime)
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30

    def test_parse_date_string_invalid_format(self):
        """Test parse_date_string with invalid date format."""
        result = parse_date_string("invalid-date")
        assert result is None

        result = parse_date_string("")
        assert result is None

        # Test with None input (should not crash)
        try:
            result = parse_date_string(None)
            assert result is None
        except TypeError:
            # Expected behavior - function expects a string
            pass

    def test_parse_date_string_custom_formats(self):
        """Test parse_date_string with custom format list."""
        custom_formats = ["%Y%m%d"]
        result = parse_date_string("20230115", custom_formats)
        assert isinstance(result, datetime)
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 15

    def test_format_datetime_for_display(self):
        """Test format_datetime_for_display function."""
        test_date = datetime(2023, 1, 15, 14, 30, 0)
        result = format_datetime_for_display(test_date)
        assert result == "15/01/2023 14:30"

        # Test custom format
        result = format_datetime_for_display(test_date, "%Y-%m-%d")
        assert result == "2023-01-15"

    def test_validate_email_valid(self):
        """Test validate_email with valid email addresses."""
        valid_emails = [
            "test@example.com",
            "user.name@domain.co.uk",
            "user+tag@example.org",
            "123@example.com",
        ]

        for email in valid_emails:
            assert validate_email(email) is True, f"Failed for valid email: {email}"

    def test_validate_email_invalid(self):
        """Test validate_email with invalid email addresses."""
        invalid_emails = [
            "invalid-email",
            "@example.com",
            "test@",
            "test.example.com",
            "",
        ]

        for email in invalid_emails:
            assert validate_email(email) is False, f"Failed for invalid email: {email}"

    def test_calculate_rack_difference(self):
        """Test calculate_rack_difference function."""
        # Test normal case
        result = calculate_rack_difference(5, 3)
        assert result == 2

        # Test reverse case
        result = calculate_rack_difference(3, 5)
        assert result == 2

        # Test equal values
        result = calculate_rack_difference(4, 4)
        assert result == 0

        # Test zero values
        result = calculate_rack_difference(0, 5)
        assert result == 5

    def test_safe_get_attr(self):
        """Test safe_get_attr function."""

        # Create a simple object for testing
        class TestObj:
            def __init__(self):
                self.name = "test"
                self.nested = NestedObj()

        class NestedObj:
            def __init__(self):
                self.value = "nested_value"

        obj = TestObj()

        # Test simple attribute access
        result = safe_get_attr(obj, "name")
        assert result == "test"

        # Test nested attribute access
        result = safe_get_attr(obj, "nested.value")
        assert result == "nested_value"

        # Test non-existent attribute
        result = safe_get_attr(obj, "nonexistent")
        assert result is None

        # Test non-existent nested attribute
        result = safe_get_attr(obj, "nested.nonexistent")
        assert result is None

        # Test with default value
        result = safe_get_attr(obj, "nonexistent", "default")
        assert result == "default"

    def test_merge_dicts(self):
        """Test merge_dicts function."""
        dict1 = {"a": 1, "b": 2}
        dict2 = {"b": 3, "c": 4}

        result = merge_dicts(dict1, dict2)
        assert result == {"a": 1, "b": 3, "c": 4}

        # Test that original dicts are not modified
        assert dict1 == {"a": 1, "b": 2}
        assert dict2 == {"b": 3, "c": 4}

        # Test with empty dicts
        result = merge_dicts({}, {"a": 1})
        assert result == {"a": 1}

        result = merge_dicts({"a": 1}, {})
        assert result == {"a": 1}

        # Test with both empty
        result = merge_dicts({}, {})
        assert result == {}
