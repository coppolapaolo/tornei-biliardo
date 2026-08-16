"""Un drill dentro un esame può prevedere più prove (ADR-042).

``exam_challenge`` guadagna ``max_attempts`` — quante volte l'esame chiede di
eseguire quel drill — e ``exam_challenge_result`` guadagna ``attempt_number``,
cioè **quale** delle prove è quella riga. La UNIQUE della seconda si allarga di
conseguenza: da ``(tentativo, drill)`` a ``(tentativo, drill, prova)``. Non è un
allentamento — due risultati sulla stessa prova restano vietati — ma il vincolo
minimo che regge la ripetizione.

Il punteggio del drill resta uno solo: conta la prova **migliore**. Sommare le
prove avrebbe fatto pesare un drill a tre tentativi il triplo di uno a tentativo
unico, cambiando la taratura degli esami senza dirlo. Il conto sta in
``ExamAttempt.recompute_scores``; qui c'è solo lo spazio dove scriverlo.

**Perché ricostruire e non un ALTER.** Un ``ALTER TABLE ADD COLUMN`` basterebbe
per le due colonne, ma non per la UNIQUE di ``exam_challenge_result``: SQLite
non sa modificare un vincolo di tabella, e servirebbe comunque un rebuild.
Tanto vale farne uno solo, coerente con ``20260816`` e ``20260817``.

Come le due che la precedono, la migration **verifica** invece di assumere: le
tabelle esame sono vuote perché il dominio è entrato in produzione da pochi
giorni e nessun esame è ancora stato composto (confermato dall'esercente). Se
una delle due contiene righe, la migration si ferma senza toccare nulla —
ricostruire le farebbe sparire.

``exam_challenge_result`` è figlia di ``exam_challenge``: va droppata per prima
e ricreata per seconda.

⚠️ In produzione va eseguita con la web app su **Disabled** (NFS + SQLite,
incidente 2026-06-10). La CI se ne accorge da sola: ``check-migrations`` rileva
il file nuovo e sopprime l'auto-reload post-merge (``ci.yml:70``).
"""

import sqlite3

migration_name = "20260819_exam_challenge_max_attempts"


#: Dalla figlia al genitore: è l'ordine del drop.
REBUILT_TABLES = ("exam_challenge_result", "exam_challenge")


REBUILD_DDL = [
    # ── exam_challenge (+ max_attempts) ─────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS exam_challenge (
        id INTEGER NOT NULL,
        exam_id INTEGER NOT NULL,
        challenge_id INTEGER NOT NULL,
        "order" INTEGER NOT NULL,
        max_score INTEGER,
        max_attempts INTEGER DEFAULT '1' NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_exam_challenge UNIQUE (exam_id, challenge_id),
        CONSTRAINT uq_exam_order UNIQUE (exam_id, "order"),
        FOREIGN KEY(exam_id) REFERENCES exam (id) ON DELETE CASCADE,
        FOREIGN KEY(challenge_id) REFERENCES challenge (id) ON DELETE CASCADE
    )
    """,
    # ── exam_challenge_result (+ attempt_number, UNIQUE allargata) ──────
    """
    CREATE TABLE IF NOT EXISTS exam_challenge_result (
        id INTEGER NOT NULL,
        exam_attempt_id INTEGER NOT NULL,
        exam_challenge_id INTEGER NOT NULL,
        attempt_number INTEGER DEFAULT '1' NOT NULL,
        score INTEGER,
        passed BOOLEAN,
        attempted_at DATETIME,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_exam_challenge_result
            UNIQUE (exam_attempt_id, exam_challenge_id, attempt_number),
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


def _already_applied(cursor: sqlite3.Cursor) -> bool:
    """La colonna c'è già: la migration è idempotente e non fa nulla."""
    if not _table_exists(cursor, "exam_challenge"):
        return False
    columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(exam_challenge)").fetchall()
    }
    return "max_attempts" in columns


def upgrade_sqlite(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        if _already_applied(cursor):
            print("  exam_challenge.max_attempts già presente: nulla da fare")
            return

        populated = _non_empty_tables(cursor)
        if populated:
            detail = ", ".join(f"{t}={n}" for t, n in sorted(populated.items()))
            raise RuntimeError(
                "Le tabelle dei drill d'esame non sono vuote come previsto "
                f"({detail}). La migration le ricostruisce per aggiungere "
                "max_attempts/attempt_number e allargare la UNIQUE dei "
                "risultati, e quei dati andrebbero persi: esportarli, "
                "applicarli al nuovo schema (identico salvo le due colonne, "
                "che valgono 1) e rieseguire."
            )

        for table in REBUILT_TABLES:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        for statement in REBUILD_DDL:
            cursor.execute(statement)

        conn.commit()
    finally:
        conn.close()

    print(
        "  Rebuilt exam_challenge (+max_attempts) and exam_challenge_result "
        "(+attempt_number, UNIQUE widened to include the attempt)"
    )
