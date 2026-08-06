"""Aggiunge `gara.public_token`: il link pubblico di iscrizione (issue #61).

Il direttore deve poter mandare un link a una singola gara — su una locandina,
un post, un QR code — che porti l'utente alla pagina della gara e lo iscriva.
Il link non usa l'id della gara: l'id è sequenziale, quindi `/g/12` rivela
`/g/11` e `/g/13`, e chi riceve il link di una gara ha in mano quello di tutte
le altre. Il token è casuale (6 byte url-safe → 8 caratteri).

Backfill: ogni gara esistente riceve un token, altrimenti le gare già create
resterebbero senza link finché qualcuno non le riapre.

Idempotente: se la colonna esiste già, popola solo le righe rimaste senza
token (caso di una migration interrotta a metà backfill).
"""

import os
import secrets
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260805_add_gara_public_token"

# Deve restare allineato a models.competition.models.PUBLIC_TOKEN_BYTES.
_TOKEN_BYTES = 6


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _column_exists(cursor, "gara", "public_token"):
        # SQLite non accetta UNIQUE in ALTER TABLE ADD COLUMN: il vincolo
        # arriva dall'indice qui sotto (che ammette più NULL, come serve).
        cursor.execute("ALTER TABLE gara ADD COLUMN public_token VARCHAR(32)")
        print("  ✓ gara.public_token aggiunta")
    else:
        print("  ⏭️  gara.public_token già presente")

    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_gara_public_token "
        "ON gara(public_token)"
    )

    # Backfill riga per riga: i token devono essere distinti, quindi non si può
    # fare con una sola UPDATE.
    cursor.execute(
        "SELECT id FROM gara WHERE public_token IS NULL OR public_token = ''"
    )
    ids = [row[0] for row in cursor.fetchall()]

    cursor.execute("SELECT public_token FROM gara WHERE public_token IS NOT NULL")
    used = {row[0] for row in cursor.fetchall()}

    for gara_id in ids:
        token = secrets.token_urlsafe(_TOKEN_BYTES)
        while token in used:  # pragma: no cover - collisione praticamente
            token = secrets.token_urlsafe(_TOKEN_BYTES)  # impossibile
        used.add(token)
        cursor.execute(
            "UPDATE gara SET public_token = ? WHERE id = ?", (token, gara_id)
        )

    conn.commit()
    conn.close()
    print(f"  ✓ token generato per {len(ids)} gare")


if __name__ == "__main__":
    upgrade_sqlite()
