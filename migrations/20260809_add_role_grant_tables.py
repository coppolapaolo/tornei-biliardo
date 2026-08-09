"""Crea le tabelle dei ruoli concedibili e della loro delega (ADR-038).

Tabelle: ``role_grant``, ``role_request``, ``role_request_recipient``.

Il DDL è stato generato dal metadata SQLAlchemy dei modelli in
``models/user/role_grant.py``, così lo schema creato qui in produzione e
quello prodotto da ``db.create_all()`` in sviluppo e nei test coincidono
esattamente. Se i modelli cambiano, questa migration **non** va modificata: se
ne scrive una nuova.

Due indici sono UNIQUE **parziali**, e la parzialità è la sostanza:

- ``uq_role_grant_active (user_id, role) WHERE revoked_at IS NULL`` — un solo
  grant attivo per utente/ruolo, ma quante revoche si vuole. Un UNIQUE pieno
  su una colonna di stato booleana (come fa ``venue_management``) ammetterebbe
  una sola riga revocata e renderebbe impossibile la seconda revoca.
- ``uq_role_request_pending (user_id, role) WHERE status = 'pending'`` — una
  sola richiesta in attesa per utente/ruolo, senza impedire lo storico.

Idempotente: ``IF NOT EXISTS`` ovunque, quindi rieseguirla è innocua e su un
DB dove ``db.create_all()`` ha già creato le tabelle (sviluppo) non fa nulla.

⚠️ In produzione va eseguita con la web app su **Disabled** (NFS + SQLite,
incidente 2026-06-10). La CI se ne accorge da sola: ``check-migrations``
rileva il file nuovo e sopprime l'auto-reload post-merge (``ci.yml:70``).
"""

import sqlite3

migration_name = "20260809_add_role_grant_tables"


DDL = [
    # ── role_grant ──────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS role_grant (
        id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role VARCHAR(30) NOT NULL,
        granted_by_id INTEGER NOT NULL,
        granted_at DATETIME NOT NULL,
        revoked_at DATETIME,
        revoked_by_id INTEGER,
        notes TEXT,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES user (id),
        FOREIGN KEY(granted_by_id) REFERENCES user (id),
        FOREIGN KEY(revoked_by_id) REFERENCES user (id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_role_grant_user_id ON role_grant (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_role_grant_role ON role_grant (role)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_role_grant_active
    ON role_grant (user_id, role)
    WHERE revoked_at IS NULL
    """,
    # ── role_request ────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS role_request (
        id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        role VARCHAR(30) NOT NULL,
        status VARCHAR(20) NOT NULL,
        requested_at DATETIME NOT NULL,
        notes TEXT,
        processed_at DATETIME,
        processed_by_id INTEGER,
        decision_notes TEXT,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES user (id),
        FOREIGN KEY(processed_by_id) REFERENCES user (id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_role_request_user_id ON role_request (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_role_request_role ON role_request (role)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_role_request_pending
    ON role_request (user_id, role)
    WHERE status = 'pending'
    """,
    # ── role_request_recipient ──────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS role_request_recipient (
        id INTEGER NOT NULL,
        request_id INTEGER NOT NULL,
        recipient_id INTEGER NOT NULL,
        status VARCHAR(20) NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_role_request_recipient UNIQUE (request_id, recipient_id),
        FOREIGN KEY(request_id) REFERENCES role_request (id),
        FOREIGN KEY(recipient_id) REFERENCES user (id)
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_role_request_recipient_request_id "
        "ON role_request_recipient (request_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_role_request_recipient_recipient_id "
        "ON role_request_recipient (recipient_id)"
    ),
]


def upgrade_sqlite(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        for statement in DDL:
            cursor.execute(statement)
        conn.commit()
    finally:
        conn.close()

    print(
        "  Created tables: role_grant, role_request, role_request_recipient "
        "(+ 2 partial UNIQUE indexes)"
    )
