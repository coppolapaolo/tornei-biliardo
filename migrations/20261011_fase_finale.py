"""La fase finale dopo i gironi (piano gironi, PR 5).

Tre colonne nuove sulla gara:

* `gara.final_phase_mode` — nessuna, tabellone, piazzamento. NULL = come il
  campionato, e su una gara singola nessuna fase finale;
* `gara.qualifiers_per_group` — quanti passano al tabellone da ogni girone.
  NULL = come il campionato, poi 2;
* `gara.final_phase_time_limit_minutes` — il limite di tempo delle partite
  della fase finale: NULL = come i gironi, 0 = senza limite, N = N minuti.

Le **gare esistenti** ricevono «nessuna fase finale», scritto: lasciato a NULL
leggerebbe in diretta la proposta del campionato (la lezione del limite di
tempo, migration 20261006). Nessuna gara esistente cambia.

Una tabella assente è un no-op dichiarato, non un errore: una migration che
solleva non viene marcata applicata e `auto_deploy` la ritenta ogni notte per
niente. Rilanciata, non fa niente.
"""

import sqlite3

migration_name = "20261011_fase_finale"

COLONNE = (
    ("gara", "final_phase_mode", "VARCHAR(20)"),
    ("gara", "qualifiers_per_group", "INTEGER"),
    ("gara", "final_phase_time_limit_minutes", "INTEGER"),
)


def _colonne(cursor, tabella):
    return {riga[1] for riga in cursor.execute(f"PRAGMA table_info({tabella})")}


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
        if "final_phase_mode" in _colonne(cursor, "gara"):
            cursor.execute(
                "UPDATE gara SET final_phase_mode = 'nessuna' "
                "WHERE final_phase_mode IS NULL"
            )
            print(f"  ✓ {cursor.rowcount} gare esistenti: nessuna fase finale")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
