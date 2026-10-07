"""La classifica a punti (ADR-078, emendamento «la classifica a punti»).

Otto colonne nuove, nessun riempimento:

* `campionato.default_points_win/draw/loss` — i punti di vittoria, pareggio e
  sconfitta proposti alle gare. NOT NULL con i default dell'app 3, 1 e 0:
  sono i valori che si copiano sulla gara quando nasce (ADR-075);
* `gara.points_win/draw/loss` — NULL = come il campionato, e su una gara
  singola il default dell'app;
* `round_classification.points` e `gara_classification.points` — i punti
  della classifica, NULL nelle gare con un altro sistema.

Nessuna gara esistente cambia: il sistema a punti è nuovo, e nessuna lo usa.
Le colonne della classifica generale non cambiano: i punti finiscono in
`classification.total_position_points`, come quelli per piazzamento.

Una tabella assente è un no-op dichiarato, non un errore: una migration che
solleva non viene marcata applicata e `auto_deploy` la ritenta ogni notte per
niente. Rilanciata, non fa niente.
"""

import sqlite3

migration_name = "20261007_classifica_a_punti"

COLONNE = (
    ("campionato", "default_points_win", "INTEGER NOT NULL DEFAULT 3"),
    ("campionato", "default_points_draw", "INTEGER NOT NULL DEFAULT 1"),
    ("campionato", "default_points_loss", "INTEGER NOT NULL DEFAULT 0"),
    ("gara", "points_win", "INTEGER"),
    ("gara", "points_draw", "INTEGER"),
    ("gara", "points_loss", "INTEGER"),
    ("round_classification", "points", "INTEGER"),
    ("gara_classification", "points", "INTEGER"),
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
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
