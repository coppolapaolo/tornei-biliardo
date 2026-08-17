"""`individual_match.status`: dai nomi dei membri ai valori dell'enum.

La colonna era mappata come `db.Enum(MatchStatus)` senza `values_callable`, e
in quel caso SQLAlchemy persiste il **nome del membro** — sul disco c'era
scritto `VALIDATED`, non `validated`. Finché i nomi non cambiano nessuno se ne
accorge; il giorno in cui cambiano, le righe già scritte diventano illeggibili:

    LookupError: 'VALIDATED' is not among the defined enum values.
                 Enum name: matchstatus.

È successo il 2026-08-17 col rinomino di `COMPLETED`/`VALIDATED` in
`CLOSED_UNILATERALLY`/`CONFIRMED_BY_BOTH` (PR #125). Il rinomino aveva
verificato che i **valori** restassero `"completed"` e `"validated"` — vero per
`match.status`, che è una `db.String`, falso per questa colonna, che i valori
non li salvava affatto. La dashboard rispondeva 500.

Questa migration riscrive i dati nella forma nuova (i valori), e il modello ora
dichiara `values_callable`. Da qui in poi la colonna è indifferente ai nomi
Python: un rinomino non la tocca più.

La mappa parte dai nomi **storici**, quelli che possono trovarsi sul disco, non
da `MatchStatus.__members__`: quest'ultimo oggi contiene i nomi nuovi, che sul
disco non ci sono mai stati, e domani potrebbe contenerne altri ancora.

Idempotente: le righe già in forma di valore non vengono toccate, e girare due
volte non cambia nulla.
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

migration_name = "20260817_individual_match_status_values"

#: nome storico sul disco → valore dell'enum.
#:
#: `COMPLETED` e `VALIDATED` sono i nomi di prima del rinomino: sono quelli che
#: si trovano davvero nelle righe scritte fino al 2026-08-17.
NOMI_STORICI = {
    "PENDING": "pending",
    "PLAYING": "playing",
    "SCHEDULED": "scheduled",
    "IN_PROGRESS": "in_progress",
    "COMPLETED": "completed",
    "VALIDATED": "validated",
    "CANCELLED": "cancelled",
    # I nomi nuovi, se una riga fosse stata scritta dopo il deploy della PR
    # #125 e prima di questa migration: stesso valore di destinazione.
    "CLOSED_UNILATERALLY": "completed",
    "CONFIRMED_BY_BOTH": "validated",
}


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        if not _table_exists(cursor, "individual_match"):
            print("  ⏭️  individual_match assente: niente da convertire")
            return

        convertite = 0
        for nome, valore in NOMI_STORICI.items():
            cursor.execute(
                "UPDATE individual_match SET status = ? WHERE status = ?",
                (valore, nome),
            )
            if cursor.rowcount:
                print(f"  ✓ {nome} → {valore}: {cursor.rowcount} righe")
                convertite += cursor.rowcount

        if not convertite:
            print("  ⏭️  nessuna riga da convertire (già in forma di valore)")

        # Un residuo qui significa un valore che non sappiamo mappare: meglio
        # dirlo forte che lasciarlo diventare un 500 alla prima lettura.
        cursor.execute(
            "SELECT DISTINCT status FROM individual_match WHERE status IS NOT NULL"
        )
        attesi = set(NOMI_STORICI.values())
        residui = [r[0] for r in cursor.fetchall() if r[0] not in attesi]
        if residui:
            raise RuntimeError(
                "individual_match.status contiene valori non riconosciuti "
                f"({', '.join(sorted(residui))}): la lettura via ORM "
                "fallirebbe. Vanno mappati a mano prima di proseguire."
            )

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
