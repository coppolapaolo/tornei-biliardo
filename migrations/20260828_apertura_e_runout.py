"""Regola di inizio, regola di apertura, chi ha aperto e il runout (ADR-056).

Tre gruppi di colonne, tre significati diversi — e vale la pena tenerli
distinti, perché è la distinzione su cui poggia tutto l'ADR.

1. **Configurazione**, che si eredita: `campionato.default_start_rule` /
   `default_break_rule` (radice, NOT NULL) e `gara.start_rule` /
   `break_rule` (NULL = eredita). Sui match di gara non c'è nessun override:
   il match eredita sempre dalla gara. Sulle sfide individuali una gara non
   c'è, quindi la radice è il match e `individual_match` prende
   `start_rule` (`break_rule` ce l'aveva già dal 2026-02).

2. **Fatti dell'acchito**, che nessuna regola può ricostruire:
   `lag_winner_id` e `first_break_player_id` su `match` e su
   `individual_match`.

3. **Fatti del triangolo**: `rack.break_player_id` — che sulle sfide e sui
   rack dei set c'era già, e proprio sui match di gara a set singolo, il caso
   normale, mancava — e `is_run_out` su `rack` e `individual_rack`.

I default scelti sono il comportamento storico: apre il primo giocatore, e i
tiri di apertura si alternano. Chi non configura niente non vede cambiare
niente, e le righe già scritte restano vere.

NIENTE FK NELLE COLONNE AGGIUNTE
--------------------------------
`ALTER TABLE ... ADD COLUMN ... REFERENCES user(id)` su SQLite è ammesso solo
col default NULL, ed è quello che serve qui; ma con `PRAGMA foreign_keys=ON`
(models/base.py) una FK dichiarata su una tabella già piena si porta dietro
sorprese all'INSERT che non valgono il beneficio — la relazione la conosce già
l'ORM. Si aggiunge la colonna nuda: `user.id` non si cancella mai davvero
(soft delete), quindi non c'è un vincolo referenziale da far rispettare.

Idempotente: ogni colonna già presente è un no-op dichiarato.
"""

import sqlite3

migration_name = "20260828_apertura_e_runout"

#: (tabella, colonna, DDL del tipo + default). L'ordine è quello del
#: ragionamento sopra, così l'output del runner si legge come l'elenco.
COLONNE = [
    ("campionato", "default_start_rule", "VARCHAR(20) NOT NULL DEFAULT 'first_player'"),
    ("campionato", "default_break_rule", "VARCHAR(20) NOT NULL DEFAULT 'alternate'"),
    ("gara", "start_rule", "VARCHAR(20)"),
    ("gara", "break_rule", "VARCHAR(20)"),
    ("individual_match", "start_rule", "VARCHAR(20) NOT NULL DEFAULT 'first_player'"),
    ("match", "lag_winner_id", "INTEGER"),
    ("match", "first_break_player_id", "INTEGER"),
    ("individual_match", "lag_winner_id", "INTEGER"),
    ("individual_match", "first_break_player_id", "INTEGER"),
    ("rack", "break_player_id", "INTEGER"),
    ("rack", "is_run_out", "BOOLEAN NOT NULL DEFAULT 0"),
    ("individual_rack", "is_run_out", "BOOLEAN NOT NULL DEFAULT 0"),
]


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    aggiunte = 0
    try:
        for tabella, colonna, ddl in COLONNE:
            if not _table_exists(cursor, tabella):
                print(f"  ⏭️  {tabella} non esiste: niente da fare")
                continue
            if _column_exists(cursor, tabella, colonna):
                print(f"  ⏭️  {tabella}.{colonna} c'e' gia'")
                continue
            cursor.execute(f'ALTER TABLE "{tabella}" ADD COLUMN {colonna} {ddl}')
            aggiunte += 1
            print(f"  ✓ {tabella}.{colonna} aggiunta")

        conn.commit()
        print(f"  ✓ {aggiunte} colonne aggiunte")
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
