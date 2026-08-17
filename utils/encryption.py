"""
Module: utils/encryption.py
Purpose: Data encryption/decryption utilities for user privacy compliance
Requirements: SPECIFICHE.md - Personal information must be encrypted with a
              server-side key
"""

import os
import base64
import hmac
import hashlib
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

# Chiave di sviluppo: NON sicura, usata solo se ENCRYPTION_KEY non e' impostata
# in dev/test. In produzione la sua assenza e' fail-fast (vedi _resolve_key_string).
_DEV_KEY_STRING = "default-development-key-change-in-production"

# Domain separation per l'HMAC dell'email: garantisce che la chiave usata per
# l'email_hash sia indipendente da quella del cipher Fernet, pur derivando
# dalla stessa ENCRYPTION_KEY.
_EMAIL_HASH_INFO = b"email-hash-v1"


def _resolve_key_string() -> str:
    """Risolve la key string per cifratura/hash.

    Fail-fast in produzione se ENCRYPTION_KEY non e' impostata (cifrare/hashare
    PII con una chiave nota nel sorgente equivale a non proteggerli). In
    dev/test ripiega su una chiave di sviluppo con warning.
    """
    key_string = os.environ.get("ENCRYPTION_KEY")
    if not key_string:
        if os.environ.get("FLASK_ENV") == "production":
            raise RuntimeError(
                "ENCRYPTION_KEY non impostata in produzione: i dati PII "
                "verrebbero cifrati/hashati con una chiave pubblica nota. "
                "Configura ENCRYPTION_KEY nell'ambiente."
            )
        key_string = _DEV_KEY_STRING
        logger.warning(
            "Using default encryption key. Set ENCRYPTION_KEY environment "
            "variable in production."
        )
    return key_string


def compute_email_hash(email: Optional[str]) -> Optional[str]:
    """HMAC-SHA256 deterministico dell'email normalizzata (lowercase + strip).

    Serve a cercare un utente per email in SQL senza decifrare l'intero
    insieme (l'email cifrata con Fernet non e' filtrabile, vedi issue #8).
    L'hash non e' reversibile: la privacy resta preservata. La chiave HMAC e'
    derivata da ENCRYPTION_KEY con domain separation, quindi indipendente dal
    cipher Fernet.

    Ritorna None per email vuote/None (es. utenti anonimizzati), coerente con
    la colonna nullable.
    """
    if not email:
        return None
    normalized = email.strip().lower()
    if not normalized:
        return None
    key = hashlib.sha256(
        _EMAIL_HASH_INFO + b":" + _resolve_key_string().encode()
    ).digest()
    return hmac.new(key, normalized.encode(), hashlib.sha256).hexdigest()


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
    """Handles encryption/decryption of sensitive user data.

    Il cipher si deriva **al primo uso**, non all'import del modulo.

    Non e' un'ottimizzazione: e' la differenza fra leggere ENCRYPTION_KEY e
    non leggerla. Console e scheduled task non ereditano le variabili del file
    WSGI e se le caricano da soli (`scripts/prod_env.py`) subito prima di
    creare l'app; ma `utils.encryption` viene importato lungo la catena di
    `import app`, che nei due script avveniva *prima* di quel caricamento. Con
    l'inizializzazione all'import il cipher nasceva quindi dalla chiave di
    sviluppo — visibile nel log come "Using default encryption key" stampato
    **prima** della riga "Env di produzione lette da ..." — e ogni email o
    telefono si decifrava a stringa vuota, in silenzio. Per il task orario dei
    promemoria significava non spedire niente e non dirlo a nessuno: stessa
    famiglia dell'incidente del 2026-06-25.

    Rimandare al primo uso non pretende piu' che nessuno importi il modulo
    troppo presto: pretende solo che nessuno *cifri* prima di aver caricato
    l'ambiente, che e' una condizione che si rispetta da se'.
    """

    _instance: Optional["EncryptionManager"] = None
    _cipher_suite: Optional[Fernet] = None
    _initialized: bool = False

    def __new__(cls) -> "EncryptionManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Volutamente vuoto: vedi docstring. Il cipher lo deriva
        # _ensure_cipher(), chiamata da chi lo usa davvero.
        pass

    def _initialize_cipher(self) -> None:
        """Initialize encryption cipher from server configuration."""
        # Get encryption key from environment or config (fail-fast in prod).
        key_string = _resolve_key_string()

        # Salt configurabile (default = valore storico per retro-compatibilita'
        # con i dati gia' cifrati).
        EncryptionManager._cipher_suite = derive_cipher(key_string)
        EncryptionManager._initialized = True

    def _ensure_cipher(self) -> Fernet:
        """Deriva il cipher se non c'e' ancora, e lo restituisce.

        E' qui che scatta il fail-fast in produzione (`_resolve_key_string`):
        al primo PII toccato, non all'avvio del processo.
        """
        if not self._initialized or self._cipher_suite is None:
            self._initialize_cipher()

        cipher = EncryptionManager._cipher_suite
        if cipher is None:  # pragma: no cover - o assegna o solleva
            raise RuntimeError("Encryption manager not properly initialized")
        return cipher

    def encrypt(self, data: str) -> str:
        """Encrypt a string value."""
        if not data:
            return ""

        cipher = self._ensure_cipher()

        encrypted_bytes = cipher.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted_bytes).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt an encrypted string value."""
        if not encrypted_data:
            return ""

        cipher = self._ensure_cipher()

        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_bytes = cipher.decrypt(encrypted_bytes)
            return decrypted_bytes.decode()
        except Exception:
            # Degrado garbato (campo vuoto, il sito resta su) ma allarme vero:
            # a livello ERROR l'evento arriva a GlitchTip via sentry_sdk.
            # Una chiave sbagliata qui significa email/telefoni illeggibili
            # in silenzio (decisione 2026-06-10, batch 8).
            logger.error(
                "Decryption failed (chiave errata o dato corrotto)", exc_info=True
            )
            return ""


# Global instance
encryption_manager = EncryptionManager()


def encrypt_data(data: str) -> str:
    """Convenience function to encrypt data."""
    return encryption_manager.encrypt(data)


def decrypt_data(encrypted_data: str) -> str:
    """Convenience function to decrypt data."""
    return encryption_manager.decrypt(encrypted_data)
