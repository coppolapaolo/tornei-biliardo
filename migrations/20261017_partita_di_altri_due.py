"""La partita di altri due, tenuta da un istruttore o da un direttore (ADR-084).

* `individual_match.scorer_id`: chi tiene il referto quando non è uno dei due
  giocatori. NULL vuol dire «sfida normale»;
* `individual_match.player1_rejected_at` e `player2_rejected_at`: il rifiuto
  **per giocatore** della partita di un terzo («non la riconosco»), che non
  tocca triangoli né l'altro giocatore.

Tutte nascono NULL: nessuna partita esistente cambia. Una tabella assente è un
no-op dichiarato, non un errore: una migration che solleva non viene marcata
applicata e `auto_deploy` la ritenta ogni notte per niente. Rilanciata, non
fa niente.
"""

import sqlite3

migration_name = "20261017_partita_di_altri_due"

COLONNE = (
    ("individual_match", "scorer_id", 'INTEGER REFERENCES "user"(id)'),
    ("individual_match", "player1_rejected_at", "DATETIME"),
    ("individual_match", "player2_rejected_at", "DATETIME"),
)


def _colonne(cursor, tabella):
    return {riga[1] for riga in cursor.execute(f'PRAGMA table_info("{tabella}")')}


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        for tabella, colonna, tipo in COLONNE:
            presenti = _colonne(cursor, tabella)
            if not presenti:
                print(f"  ⏭️  tabella {tabella} assente")
                continue
            if colonna in presenti:
                print(f"  ⏭️  {tabella}.{colonna} già esistente")
                continue
            cursor.execute(f'ALTER TABLE "{tabella}" ADD COLUMN {colonna} {tipo}')
            print(f"  ✓ Aggiunta colonna {tabella}.{colonna}")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_individual_match_scorer_id "
            "ON individual_match (scorer_id)"
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
