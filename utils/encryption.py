"""
Module: utils/encryption.py
Purpose: Data encryption/decryption utilities for user privacy compliance
Requirements: SPECIFICHE.md - Personal information must be encrypted with a
              server-side key
"""

import os
import base64
import logging
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Salt di default storico: NON cambiarlo o i dati PII gia' cifrati in
# produzione (email/phone) diventano indecifrabili. Override possibile via
# ENCRYPTION_SALT per nuovi deployment.
_DEFAULT_SALT = b"campionati-biliardo-salt"


def derive_cipher(key_string: str, salt: Optional[bytes] = None) -> Fernet:
    """Deriva il cipher Fernet da una key string (PBKDF2-SHA256, 100k iter).

    Stessa derivazione usata dall'EncryptionManager: serve anche allo script
    di rotazione chiave (scripts/rotate_encryption_key.py), che deve poter
    costruire cipher per chiavi diverse da quella in ENCRYPTION_KEY.
    """
    if salt is None:
        salt_env = os.environ.get("ENCRYPTION_SALT")
        salt = salt_env.encode() if salt_env else _DEFAULT_SALT

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return Fernet(base64.urlsafe_b64encode(kdf.derive(key_string.encode())))


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
            # Fail-fast in produzione: cifrare PII con una chiave nota nel
            # sorgente equivale a non cifrare. In dev/test si usa un default
            # con warning esplicito.
            if os.environ.get("FLASK_ENV") == "production":
                raise RuntimeError(
                    "ENCRYPTION_KEY non impostata in produzione: i dati PII "
                    "verrebbero cifrati con una chiave pubblica nota. "
                    "Configura ENCRYPTION_KEY nell'ambiente."
                )
            key_string = "default-development-key-change-in-production"
            logger.warning(
                "Using default encryption key. Set ENCRYPTION_KEY environment "
                "variable in production."
            )

        # Salt configurabile (default = valore storico per retro-compatibilita'
        # con i dati gia' cifrati).
        EncryptionManager._cipher_suite = derive_cipher(key_string)

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
            # Degrado garbato (campo vuoto, il sito resta su) ma allarme vero:
            # a livello ERROR l'evento arriva a GlitchTip via sentry_sdk.
            # Una chiave sbagliata qui significa email/telefoni illeggibili
            # in silenzio (decisione 2026-06-10, batch 8).
            logger.error("Decryption failed (chiave errata o dato corrotto): %s", e)
            return ""


# Global instance
encryption_manager = EncryptionManager()


def encrypt_data(data: str) -> str:
    """Convenience function to encrypt data."""
    return encryption_manager.encrypt(data)


def decrypt_data(encrypted_data: str) -> str:
    """Convenience function to decrypt data."""
    return encryption_manager.decrypt(encrypted_data)
