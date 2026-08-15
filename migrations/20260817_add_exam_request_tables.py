"""Crea le tabelle dell'appuntamento d'esame e aggancia la sessione (ADR-042).

Tabelle nuove: ``exam_request``, ``exam_request_recipient``,
``exam_time_proposal``. In più ``exam_attempt`` viene **ricostruita**, per due
motivi che vengono dallo stesso punto:

1. ``exam_request_id`` era una colonna semplice perché in Fase 2 la tabella
   referente non esisteva ancora. Ora esiste, e la colonna diventa una vera
   ``REFERENCES exam_request(id)``: il DB applica ``PRAGMA foreign_keys=ON``
   (``models/base.py``), quindi una FK dichiarata è una FK **applicata**, non
   documentazione.
2. L'indice su quella colonna passa da semplice a **UNIQUE parziale**: da uno
   stesso appuntamento non può nascere più di una sessione.

⚠️ Attenzione a cosa presidia quell'indice: **non** la corsa «due esaminatori
accettano insieme». Quella si gioca molto prima, sull'accettazione, e la vince
l'indice UNIQUE parziale ``(request_id) WHERE status='accepted'`` su
``exam_request_recipient`` — creato qui sotto — insieme all'UPDATE condizionato
in ``ExamRequestService.accept``. Al momento dell'accettazione nessun
``ExamAttempt`` esiste ancora: un indice su ``exam_attempt`` non potrebbe
fermare nulla.

**Perché ricostruire e non un ALTER.** SQLite non sa aggiungere una FK a una
tabella esistente: servirebbe comunque un rebuild. E come in
``20260816_exam_schema_rework``, le tabelle esame sono **vuote per
costruzione** — il dominio non ha ancora né route né template, quindi nessuno
ci ha mai scritto. L'ipotesi è verificata, non assunta: se ``exam_attempt`` o
``exam_challenge_result`` contengono righe la migration si ferma senza toccare
nulla, perché ricostruire le farebbe sparire.

``exam_challenge_result`` rientra nel giro solo perché ha una FK verso
``exam_attempt``: va droppata prima e ricreata identica dopo.

Il DDL è generato dal metadata SQLAlchemy dei modelli
(``models/exam/models.py``, ``models/exam/request_models.py``), così lo schema
creato qui e quello di ``db.create_all()`` coincidono;
``tests/new/unit/test_exam_schema_migration.py`` lo verifica colonna per
colonna, indice per indice e FK per FK, applicando le migration **in
sequenza**. Se i modelli cambiano, questa migration non va modificata: se ne
scrive una nuova.

⚠️ In produzione va eseguita con la web app su **Disabled** (NFS + SQLite,
incidente 2026-06-10). La CI se ne accorge da sola: ``check-migrations``
rileva il file nuovo e sopprime l'auto-reload post-merge (``ci.yml:70``).
"""

import sqlite3

migration_name = "20260817_add_exam_request_tables"


#: Tabelle da ricostruire, dalla figlia al genitore: è l'ordine del drop.
REBUILT_TABLES = ("exam_challenge_result", "exam_attempt")


NEW_TABLES_DDL = [
    # ── exam_request ────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS exam_request (
        id INTEGER NOT NULL,
        exam_id INTEGER NOT NULL,
        requester_id INTEGER NOT NULL,
        status VARCHAR(20) NOT NULL,
        billiard_hall_id INTEGER NOT NULL,
        scheduled_at DATETIME NOT NULL,
        expires_at DATETIME NOT NULL,
        last_proposed_by_id INTEGER NOT NULL,
        negotiating_with_id INTEGER,
        accepted_by_id INTEGER,
        accepted_at DATETIME,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(exam_id) REFERENCES exam (id) ON DELETE CASCADE,
        FOREIGN KEY(requester_id) REFERENCES user (id),
        FOREIGN KEY(billiard_hall_id) REFERENCES billiard_hall (id),
        FOREIGN KEY(last_proposed_by_id) REFERENCES user (id),
        FOREIGN KEY(negotiating_with_id) REFERENCES user (id),
        FOREIGN KEY(accepted_by_id) REFERENCES user (id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_exam_request_exam_id ON exam_request (exam_id)",
    (
        "CREATE INDEX IF NOT EXISTS ix_exam_request_requester_id "
        "ON exam_request (requester_id)"
    ),
    # ── exam_request_recipient ──────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS exam_request_recipient (
        id INTEGER NOT NULL,
        request_id INTEGER NOT NULL,
        examiner_id INTEGER NOT NULL,
        status VARCHAR(20) NOT NULL,
        responded_at DATETIME,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_exam_request_recipient UNIQUE (request_id, examiner_id),
        FOREIGN KEY(request_id) REFERENCES exam_request (id) ON DELETE CASCADE,
        FOREIGN KEY(examiner_id) REFERENCES user (id)
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_exam_request_recipient_request_id "
        "ON exam_request_recipient (request_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_exam_request_recipient_examiner_id "
        "ON exam_request_recipient (examiner_id)"
    ),
    # Il presidio della corsa «due esaminatori accettano insieme»: un solo
    # accettante per richiesta. Parziale, perché gli altri destinatari devono
    # poter restare in `pending`, `rejected` o `closed` quanti sono.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_exam_request_accepted
    ON exam_request_recipient (request_id)
    WHERE status = 'accepted'
    """,
    # ── exam_time_proposal ──────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS exam_time_proposal (
        id INTEGER NOT NULL,
        request_id INTEGER NOT NULL,
        proposed_by_id INTEGER NOT NULL,
        scheduled_at DATETIME NOT NULL,
        billiard_hall_id INTEGER NOT NULL,
        superseded_at DATETIME,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(request_id) REFERENCES exam_request (id) ON DELETE CASCADE,
        FOREIGN KEY(proposed_by_id) REFERENCES user (id),
        FOREIGN KEY(billiard_hall_id) REFERENCES billiard_hall (id)
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_exam_time_proposal_request_id "
        "ON exam_time_proposal (request_id)"
    ),
]


REBUILD_DDL = [
    # ── exam_attempt (ora con la FK verso exam_request) ─────────────────
    """
    CREATE TABLE IF NOT EXISTS exam_attempt (
        id INTEGER NOT NULL,
        exam_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        mode VARCHAR(20) NOT NULL,
        status VARCHAR(30) NOT NULL,
        started_at DATETIME NOT NULL,
        completed_at DATETIME,
        passed BOOLEAN,
        total_score INTEGER,
        max_possible_score INTEGER,
        examiner_id INTEGER,
        certified_at DATETIME,
        billiard_hall_id INTEGER,
        exam_request_id INTEGER,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(exam_id) REFERENCES exam (id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE,
        FOREIGN KEY(examiner_id) REFERENCES user (id),
        FOREIGN KEY(billiard_hall_id) REFERENCES billiard_hall (id),
        FOREIGN KEY(exam_request_id) REFERENCES exam_request (id)
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_exam_attempt_open_self_practice
    ON exam_attempt (user_id, exam_id)
    WHERE status = 'in_progress' AND mode = 'self_practice'
    """,
    # Una sola sessione per appuntamento. Parziale sul NOT NULL: i tentativi in
    # autonomia hanno tutti ``exam_request_id`` a NULL e devono convivere.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_exam_attempt_request
    ON exam_attempt (exam_request_id)
    WHERE exam_request_id IS NOT NULL
    """,
    # ── exam_challenge_result (identica: si ricrea perché figlia) ───────
    """
    CREATE TABLE IF NOT EXISTS exam_challenge_result (
        id INTEGER NOT NULL,
        exam_attempt_id INTEGER NOT NULL,
        exam_challenge_id INTEGER NOT NULL,
        score INTEGER,
        passed BOOLEAN,
        attempted_at DATETIME,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_exam_challenge_result
            UNIQUE (exam_attempt_id, exam_challenge_id),
        FOREIGN KEY(exam_attempt_id) REFERENCES exam_attempt (id) ON DELETE CASCADE,
        FOREIGN KEY(exam_challenge_id) REFERENCES exam_challenge (id) ON DELETE CASCADE
    )
    """,
]


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _non_empty_tables(cursor: sqlite3.Cursor) -> dict:
    """Fra le tabelle da ricostruire, quelle che contengono righe."""
    populated = {}
    for table in REBUILT_TABLES:
        if not _table_exists(cursor, table):
            continue
        count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if count:
            populated[table] = count
    return populated


def upgrade_sqlite(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        populated = _non_empty_tables(cursor)
        if populated:
            detail = ", ".join(f"{t}={n}" for t, n in sorted(populated.items()))
            raise RuntimeError(
                "Le tabelle dei tentativi d'esame non sono vuote come previsto "
                f"({detail}). La migration le ricostruisce per aggiungere la "
                "FK verso exam_request e l'indice UNIQUE su exam_request_id, e "
                "quei dati andrebbero persi: esportarli, applicarli a mano al "
                "nuovo schema (identico salvo la FK) e rieseguire."
            )

        for statement in NEW_TABLES_DDL:
            cursor.execute(statement)

        for table in REBUILT_TABLES:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        # Gli indici dei tentativi seguono la loro tabella nel DROP, tranne
        # quello vecchio non-UNIQUE se fosse rimasto orfano da un create_all.
        cursor.execute("DROP INDEX IF EXISTS ix_exam_attempt_exam_request_id")
        for statement in REBUILD_DDL:
            cursor.execute(statement)

        conn.commit()
    finally:
        conn.close()

    print(
        "  Created tables: exam_request, exam_request_recipient, "
        "exam_time_proposal (+ 1 partial UNIQUE index); rebuilt exam_attempt "
        "and exam_challenge_result (FK to exam_request + partial UNIQUE index)"
    )
