"""Rifà da zero lo schema del dominio esame (ADR-042).

Tabelle: ``exam``, ``exam_challenge``, ``exam_attempt``, ``exam_challenge_result``
riscritte, più la nuova ``exam_examiner``.

**Perché drop-and-recreate e non una sequenza di ALTER.** Le quattro tabelle
preesistenti ci sono, in sviluppo e in produzione, perché le ha create
``db.create_all()``, ma sono **vuote per costruzione**: il dominio era codice
orfano — nessuna
route, nessun template, nessun chiamante di ``ExamService`` fuori dai test
legacy — quindi nessuno ci ha mai scritto. Il rework richiederebbe un
``RENAME COLUMN`` (``director_id`` → ``examiner_id``) e tre ``DROP COLUMN``
(``grading_criteria``, ``final_grade``, ``completed``): il repo evita
``DROP COLUMN`` per prassi consolidata e la versione di SQLite in produzione
non è verificabile da qui (``DROP COLUMN`` richiede ≥ 3.35). Su tabelle vuote
il drop-and-recreate è più semplice, più sicuro, e lascia lo schema pulito
invece di trascinarsi tre colonne morte.

**Se una tabella contiene righe la migration si ferma**, rumorosamente e senza
toccare nulla — stesso contegno di ``20260405_unique_constraints_toctou.py``.
L'ipotesi «sono vuote» è verificata, non assunta: se è falsa, chi la esegue
deve saperlo prima che i dati spariscano.

Il DDL è generato dal metadata SQLAlchemy dei modelli in ``models/exam/models.py``,
così lo schema creato qui e quello di ``db.create_all()`` coincidono
esattamente; ``tests/new/unit/test_exam_schema_migration.py`` lo verifica
colonna per colonna e indice per indice. Se i modelli cambiano, questa
migration **non** va modificata: se ne scrive una nuova.

Nota su ``exam_attempt.exam_request_id``: è una colonna semplice, senza FK. La
tabella ``exam_request`` arriva in Fase 3 con l'appuntamento, e una
``REFERENCES`` verso una tabella inesistente non avrebbe referente.

⚠️ In produzione va eseguita con la web app su **Disabled** (NFS + SQLite,
incidente 2026-06-10). La CI se ne accorge da sola: ``check-migrations``
rileva il file nuovo e sopprime l'auto-reload post-merge (``ci.yml:70``).
"""

import sqlite3

migration_name = "20260816_exam_schema_rework"


#: Tabelle del dominio, dalla figlia al genitore: è l'ordine in cui si droppano.
#: ``exam_examiner`` è nuova in produzione, ma su una macchina di sviluppo
#: ``db.create_all()`` può averla già creata: sta nell'elenco perché anche lì
#: valga la stessa regola — si ricostruisce se è vuota, ci si ferma se non lo è.
EXAM_TABLES = (
    "exam_challenge_result",
    "exam_attempt",
    "exam_challenge",
    "exam_examiner",
    "exam",
)


DDL = [
    # ── exam ────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS exam (
        id INTEGER NOT NULL,
        name VARCHAR(100) NOT NULL,
        description TEXT,
        examiner_id INTEGER NOT NULL,
        is_active BOOLEAN NOT NULL,
        time_limit_minutes INTEGER,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(examiner_id) REFERENCES user (id)
    )
    """,
    # ── exam_examiner (nuova: i co-esaminatori, US-E2) ──────────────────
    """
    CREATE TABLE IF NOT EXISTS exam_examiner (
        id INTEGER NOT NULL,
        exam_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        added_by_id INTEGER NOT NULL,
        added_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_exam_examiner UNIQUE (exam_id, user_id),
        FOREIGN KEY(exam_id) REFERENCES exam (id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES user (id),
        FOREIGN KEY(added_by_id) REFERENCES user (id)
    )
    """,
    # ── exam_challenge (max_score per-esame, niente weight) ─────────────
    """
    CREATE TABLE IF NOT EXISTS exam_challenge (
        id INTEGER NOT NULL,
        exam_id INTEGER NOT NULL,
        challenge_id INTEGER NOT NULL,
        "order" INTEGER NOT NULL,
        max_score INTEGER,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_exam_challenge UNIQUE (exam_id, challenge_id),
        CONSTRAINT uq_exam_order UNIQUE (exam_id, "order"),
        FOREIGN KEY(exam_id) REFERENCES exam (id) ON DELETE CASCADE,
        FOREIGN KEY(challenge_id) REFERENCES challenge (id) ON DELETE CASCADE
    )
    """,
    # ── exam_attempt (mode/status/passed, niente final_grade) ───────────
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
        FOREIGN KEY(billiard_hall_id) REFERENCES billiard_hall (id)
    )
    """,
    # Indice UNIQUE **parziale**: un solo allenamento aperto per (utente,
    # esame). Parziale perché i tentativi conclusi devono poter essere quanti
    # si vuole — un UNIQUE pieno impedirebbe di rifare l'esame.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_exam_attempt_open_self_practice
    ON exam_attempt (user_id, exam_id)
    WHERE status = 'in_progress' AND mode = 'self_practice'
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_exam_attempt_exam_request_id "
        "ON exam_attempt (exam_request_id)"
    ),
    # ── exam_challenge_result ───────────────────────────────────────────
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
    """Tabelle esame che contengono righe, con il conteggio."""
    populated = {}
    for table in EXAM_TABLES:
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
                "Le tabelle esame non sono vuote come previsto "
                f"({detail}). La migration ricrea lo schema da zero e "
                "perderebbe quei dati: esportarli e decidere a mano come "
                "riportarli sul nuovo schema (director_id → examiner_id, "
                "grading_criteria/final_grade rimossi, weight rimosso), "
                "poi rieseguire."
            )

        for table in EXAM_TABLES:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")

        for statement in DDL:
            cursor.execute(statement)

        conn.commit()
    finally:
        conn.close()

    print(
        "  Rebuilt exam schema: exam, exam_examiner, exam_challenge, "
        "exam_attempt, exam_challenge_result (+ 1 partial UNIQUE index)"
    )
