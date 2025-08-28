"""
Module: models/fields.py
Purpose: Custom SQLAlchemy field types for encrypted data storage
Requirements: SPECIFICHE.md - Personal information encryption
"""

from sqlalchemy import TypeDecorator, String
from utils.encryption import encrypt_data, decrypt_data


class EncryptedString(TypeDecorator):
    """SQLAlchemy field type that automatically encrypts/decrypts string data."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt value before storing in database."""
        if value is not None:
            return encrypt_data(str(value))
        return value

    def process_result_value(self, value, dialect):
        """Decrypt value when retrieving from database."""
        if value is not None:
            return decrypt_data(value)
        return value


class EncryptedText(EncryptedString):
    """Encrypted text field for longer content."""

    impl = String(1000)  # Encrypted data is typically longer
