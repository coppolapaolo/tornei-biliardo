"""Le sfide che il riscatto ha portato (ADR-086, emendamento del 2026-10-18).

Tabella ``claim_request_match``: per ogni richiesta di riscatto approvata, le
sfide individuali che erano del giocatore non registrato — le *registrate da
uno* e le partite di altri due — scritte da ``ClaimService.approve`` **prima**
dell'unione. Dopo, ``UserMergeService`` le ha spostate sull'account di chi ha
riscattato, e niente sulla sfida dice più da dove venisse: la pagina della
revisione mostrava allora tutte le partite di altri due che aspettavano una
decisione dell'utente, anche quelle in cui lui era un giocatore dall'inizio.

Il DDL ricalca il metadata di ``models/user/claim_request.py``, compresi
``created_at``/``updated_at`` di ``BaseModel`` (presidio
``tests/new/unit/test_migrations_timestamps.py``).

Nessun riempimento: per i riscatti approvati prima di questa migration la
traccia non si ricostruisce, perché l'unione l'ha già cancellata. Lì valgono le
sole sfide registrate da uno, che si riconoscono da ``recorded_by_id``; le
partite di altri due non compaiono nella revisione e si decidono dalla pagina
di ciascuna (``RevisioneService.da_rivedere``).

Idempotente: ``IF NOT EXISTS`` ovunque. Rilanciata, non fa niente.
"""

import sqlite3

migration_name = "20261018_partite_del_riscatto"


DDL = [
    """
    CREATE TABLE IF NOT EXISTS claim_request_match (
        id INTEGER NOT NULL,
        request_id INTEGER NOT NULL,
        individual_match_id INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_claim_request_match UNIQUE (request_id, individual_match_id),
        FOREIGN KEY(request_id) REFERENCES claim_request (id),
        FOREIGN KEY(individual_match_id) REFERENCES individual_match (id)
            ON DELETE CASCADE
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_claim_request_match_request_id "
        "ON claim_request_match (request_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_claim_request_match_individual_match_id "
        "ON claim_request_match (individual_match_id)"
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
    print("  ✓ Tabella claim_request_match")


if __name__ == "__main__":
    upgrade_sqlite()
