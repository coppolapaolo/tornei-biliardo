"""Il cipher dei PII si deriva al primo uso, non all'import del modulo.

Nel log dello scheduled task orario la riga

    Using default encryption key. Set ENCRYPTION_KEY environment variable...

compariva **prima** di

    Env di produzione lette da /var/www/..._wsgi.py: ... ENCRYPTION_KEY ...

Non è un avviso spurio: è il resoconto esatto di quello che succedeva.
`utils.encryption` istanziava l'`EncryptionManager` all'import e derivava
subito il cipher; l'import avveniva lungo la catena di `import app`, in cima
allo script, cioè prima che le env del file WSGI fossero caricate. Risultato:
cipher costruito sulla chiave di sviluppo, email e telefoni decifrati a
stringa vuota, nessun errore da nessuna parte. Per i promemoria significava
non spedire niente — e non dirlo.

È la stessa famiglia dell'incidente del 2026-06-25, dove una migration sui PII
girò con la chiave sbagliata e scrisse 0 hash su 37 utenti restando marcata
come applicata.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def encryption_module():
    """Il modulo ricaricato da zero, con lo stato del singleton azzerato.

    Il cipher è un attributo *di classe*: senza questa pulizia un test che
    l'ha già derivato renderebbe i successivi ciechi.
    """
    module = importlib.import_module("utils.encryption")
    manager = module.EncryptionManager
    salvati = (manager._instance, manager._cipher_suite, manager._initialized)
    manager._instance = None
    manager._cipher_suite = None
    manager._initialized = False
    yield module
    manager._instance, manager._cipher_suite, manager._initialized = salvati


@pytest.mark.unit
def test_costruire_il_manager_non_deriva_il_cipher(encryption_module):
    """Il cuore della correzione: `EncryptionManager()` non tocca l'ambiente.

    All'import del modulo succede esattamente questo, e prima bastava a
    inchiodare la chiave sbagliata per tutta la vita del processo.
    """
    encryption_module.EncryptionManager()

    assert encryption_module.EncryptionManager._cipher_suite is None


@pytest.mark.unit
def test_la_chiave_impostata_dopo_l_import_viene_usata(encryption_module, monkeypatch):
    """La sequenza del guasto: manager costruito prima, chiave dopo.

    Si verifica per differenza: un token cifrato con la chiave arrivata tardi
    deve essere decifrabile da un cipher derivato *da quella* chiave, e non da
    quello di sviluppo.
    """
    manager = encryption_module.EncryptionManager()  # come all'import

    monkeypatch.setenv("ENCRYPTION_KEY", "chiave-dal-file-wsgi")
    monkeypatch.delenv("ENCRYPTION_SALT", raising=False)

    token = manager.encrypt("mario@example.test")

    atteso = encryption_module.derive_cipher("chiave-dal-file-wsgi")
    import base64

    assert atteso.decrypt(base64.urlsafe_b64decode(token.encode())) == (
        b"mario@example.test"
    )
    assert manager.decrypt(token) == "mario@example.test"


@pytest.mark.unit
def test_con_la_chiave_di_sviluppo_il_token_non_si_decifra(
    encryption_module, monkeypatch
):
    """La controprova del test precedente.

    Se il cipher nascesse ancora all'import (chiave di sviluppo), il token
    prodotto sarebbe questo — e la chiave vera non lo aprirebbe. È il degrado
    silenzioso che si stava subendo in produzione.
    """
    monkeypatch.delenv("ENCRYPTION_SALT", raising=False)
    con_chiave_sviluppo = encryption_module.derive_cipher(
        encryption_module._DEV_KEY_STRING
    )
    token = con_chiave_sviluppo.encrypt(b"mario@example.test")

    con_chiave_vera = encryption_module.derive_cipher("chiave-dal-file-wsgi")
    with pytest.raises(Exception):
        con_chiave_vera.decrypt(token)


@pytest.mark.unit
def test_il_fail_fast_in_produzione_scatta_al_primo_uso(encryption_module, monkeypatch):
    """Rimandare la derivazione non deve annacquare il fail-fast.

    Cifrare un PII con una chiave pubblica nota equivale a non proteggerlo:
    in produzione senza ENCRYPTION_KEY si solleva, e ora lo si fa nel momento
    in cui il dato viene davvero toccato.
    """
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

    manager = encryption_module.EncryptionManager()  # non solleva

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        manager.encrypt("mario@example.test")


@pytest.mark.unit
def test_il_cipher_si_deriva_una_volta_sola(encryption_module, monkeypatch):
    """La derivazione è PBKDF2 a 100k iterazioni: rifarla a ogni campo
    cifrato costerebbe caro su una pagina che mostra cento email."""
    monkeypatch.setenv("ENCRYPTION_KEY", "chiave")
    manager = encryption_module.EncryptionManager()

    manager.encrypt("uno@example.test")
    primo = encryption_module.EncryptionManager._cipher_suite
    manager.encrypt("due@example.test")

    assert encryption_module.EncryptionManager._cipher_suite is primo
