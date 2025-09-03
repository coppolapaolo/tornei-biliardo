"""
Module: utils/encryption.py
Purpose: Data encryption/decryption utilities for user privacy compliance
Requirements: SPECIFICHE.md - Personal information must be encrypted with server-side key
"""

import os
import base64
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionManager:
    """Handles encryption/decryption of sensitive user data."""

    _instance: Optional["EncryptionManager"] = None
    _cipher_suite: Optional[Fernet] = None
    _initialized: bool = False

    def __new__(cls) -> "EncryptionManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self._initialize_cipher()
            EncryptionManager._initialized = True

    def _initialize_cipher(self) -> None:
        """Initialize encryption cipher from server configuration."""
        # Get encryption key from environment or config
        key_string = os.environ.get("ENCRYPTION_KEY")

        if not key_string:
            # For development, generate a default key
            # In production, this should be set in server configuration
            key_string = "default-development-key-change-in-production"
            print(
                "WARNING: Using default encryption key. Set ENCRYPTION_KEY environment variable in production."
            )

        # Derive encryption key from the key string
        key_bytes = key_string.encode()
        salt = b"campionati-biliardo-salt"  # Should be random in production

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        key = base64.urlsafe_b64encode(kdf.derive(key_bytes))
        EncryptionManager._cipher_suite = Fernet(key)

    def encrypt(self, data: str) -> str:
        """Encrypt a string value."""
        if not data:
            return ""

        if self._cipher_suite is None:
            raise RuntimeError("Encryption manager not properly initialized")

        encrypted_bytes = self._cipher_suite.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted_bytes).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt an encrypted string value."""
        if not encrypted_data:
            return ""

        if self._cipher_suite is None:
            raise RuntimeError("Encryption manager not properly initialized")

        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_bytes = self._cipher_suite.decrypt(encrypted_bytes)
            return decrypted_bytes.decode()
        except Exception as e:
            # Log error and return empty string for corrupted data
            print(f"Decryption failed: {e}")
            return ""


# Global instance
encryption_manager = EncryptionManager()


def encrypt_data(data: str) -> str:
    """Convenience function to encrypt data."""
    return encryption_manager.encrypt(data)


def decrypt_data(encrypted_data: str) -> str:
    """Convenience function to decrypt data."""
    return encryption_manager.decrypt(encrypted_data)
