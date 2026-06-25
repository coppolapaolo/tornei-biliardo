"""Aggiunge user.email_hash (HMAC deterministico dell'email) — issue #8.

L'email e' cifrata con Fernet (non deterministico): la stessa email cifrata due
volte produce ciphertext diversi, quindi non e' filtrabile in SQL. La lookup per
email (login / reset password / registrazione) decifrava percio' TUTTI gli
utenti in Python (O(N), anche vettore di resource-exhaustion su endpoint
pubblici).

`user.email_hash` e' l'HMAC-SHA256 dell'email normalizzata (lowercase + strip),
con chiave derivata da ENCRYPTION_KEY: permette un lookup indicizzato O(1) senza
esporre l'email (l'hash non e' reversibile).

Questa migration:
  1. aggiunge la colonna user.email_hash (VARCHAR(64));
  2. popola l'hash per gli utenti esistenti decifrando l'email;
  3. crea l'indice ix_user_email_hash.

Idempotente: ALTER preceduto da PRAGMA table_info, indice con IF NOT EXISTS, e
ri-popolazione delle sole righe con email_hash mancante.

NOTA produzione: richiede ENCRYPTION_KEY nell'ambiente (la console PA non eredita
le env del WSGI). Lanciare con:  ENCRYPTION_KEY='...' python migrations/runner.py
e con la web app su Disabled (SQLite su NFS, vedi CLAUDE.md).
"""

import os
import sqlite3
import sys

# Project root importabile (il runner aggiunge gia' la root, ma rendiamo lo
# script robusto se eseguito direttamente).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260625_add_email_hash"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    from utils.encryption import decrypt_data, compute_email_hash

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _column_exists(cursor, "user", "email_hash"):
        cursor.execute("ALTER TABLE user ADD COLUMN email_hash VARCHAR(64)")
        print("  ✓ Aggiunta colonna user.email_hash")
    else:
        print("  ⏭️  user.email_hash già esistente")

    # Popola l'hash per le righe con email presente ma hash mancante.
    cursor.execute(
        "SELECT id, email FROM user "
        "WHERE email IS NOT NULL AND email != '' "
        "AND (email_hash IS NULL OR email_hash = '')"
    )
    rows = cursor.fetchall()
    updated = 0
    for user_id, encrypted_email in rows:
        plain = decrypt_data(encrypted_email)
        if not plain:
            # Decifratura fallita (chiave errata o dato corrotto): salta, non
            # vogliamo scrivere un hash sbagliato. decrypt_data logga a ERROR.
            continue
        email_hash = compute_email_hash(plain)
        cursor.execute(
            "UPDATE user SET email_hash = ? WHERE id = ?", (email_hash, user_id)
        )
        updated += 1
    print(f"  ✓ Popolato email_hash per {updated}/{len(rows)} utenti")

    cursor.execute("CREATE INDEX IF NOT EXISTS ix_user_email_hash ON user (email_hash)")
    print("  ✓ Indice ix_user_email_hash")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
