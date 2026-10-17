"""Riscatto dei giocatori non ancora registrati (ADR-086).

Tabelle: ``claim_request`` (chi dice di essere quale giocatore, e com'è
finita) e ``claim_request_recipient`` (chi può decidere: il creatore del
giocatore, o l'amministratore).

Il DDL ricalca il metadata di ``models/user/claim_request.py``, compresi
``created_at``/``updated_at`` di ``BaseModel``: senza, l'ORM fallirebbe con «no
such column» in produzione, dove lo schema non nasce da ``db.create_all()``
(presidio ``tests/new/unit/test_migrations_timestamps.py``).

L'indice ``uq_claim_request_pending (placeholder_id) WHERE status = 'pending'``
è UNIQUE **parziale**: una sola richiesta in attesa per giocatore, mentre le
richieste chiuse restano come storia.

Idempotente: ``IF NOT EXISTS`` ovunque. Rilanciata, non fa niente.
"""

import sqlite3

migration_name = "20261018_riscatto_giocatori"


DDL = [
    """
    CREATE TABLE IF NOT EXISTS claim_request (
        id INTEGER NOT NULL,
        placeholder_id INTEGER NOT NULL,
        claimant_id INTEGER NOT NULL,
        status VARCHAR(20) NOT NULL,
        decided_by_id INTEGER,
        decided_at DATETIME,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(placeholder_id) REFERENCES user (id),
        FOREIGN KEY(claimant_id) REFERENCES user (id),
        FOREIGN KEY(decided_by_id) REFERENCES user (id)
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_claim_request_placeholder_id "
        "ON claim_request (placeholder_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_claim_request_claimant_id "
        "ON claim_request (claimant_id)"
    ),
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_claim_request_pending
    ON claim_request (placeholder_id)
    WHERE status = 'pending'
    """,
    """
    CREATE TABLE IF NOT EXISTS claim_request_recipient (
        id INTEGER NOT NULL,
        request_id INTEGER NOT NULL,
        recipient_id INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_claim_request_recipient UNIQUE (request_id, recipient_id),
        FOREIGN KEY(request_id) REFERENCES claim_request (id),
        FOREIGN KEY(recipient_id) REFERENCES user (id)
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_claim_request_recipient_request_id "
        "ON claim_request_recipient (request_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_claim_request_recipient_recipient_id "
        "ON claim_request_recipient (recipient_id)"
    ),
]


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        for statement in DDL:
            cursor.execute(statement)
        conn.commit()
    finally:
        conn.close()
    print("  ✓ Tabelle claim_request e claim_request_recipient (+ indice parziale)")


if __name__ == "__main__":
    upgrade_sqlite()
