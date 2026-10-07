"""Il girone all'italiana a più gironi (ADR-076).

Nove colonne nuove, e un riempimento:

* `campionato.default_max_groups` e `campionato.default_group_seeding` — il
  tetto dei gironi e la loro composizione proposti alle gare. NOT NULL con i
  default dell'app, girone unico e sorteggio: sono i valori che si copiano
  sulla gara quando nasce (ADR-075);
* `gara.max_groups` e `gara.group_seeding` — NULL = come il campionato, e su
  una gara singola il default dell'app;
* `inscription.group_index` — il girone del giocatore, scritto all'avvio;
* `round_classification.group_index/group_position` e
  `gara_classification.group_index/group_position` — il girone e la posizione
  nel girone, NULL nelle gare a girone unico.

Le **gare esistenti** ricevono girone unico e sorteggio, come le gare nuove
che nascono in un campionato: lasciate a NULL leggerebbero in diretta il tetto
del campionato (la lezione del limite di tempo, migration 20261006).

Nessuna gara esistente cambia. Una tabella assente è un no-op dichiarato, non
un errore: una migration che solleva non viene marcata applicata e
`auto_deploy` la ritenta ogni notte per niente. Rilanciata, non fa niente.
"""

import sqlite3

migration_name = "20261007_gironi"

COLONNE = (
    ("campionato", "default_max_groups", "INTEGER NOT NULL DEFAULT 1"),
    (
        "campionato",
        "default_group_seeding",
        "VARCHAR(20) NOT NULL DEFAULT 'sorteggio'",
    ),
    ("gara", "max_groups", "INTEGER"),
    ("gara", "group_seeding", "VARCHAR(20)"),
    ("inscription", "group_index", "INTEGER"),
    ("round_classification", "group_index", "INTEGER"),
    ("round_classification", "group_position", "INTEGER"),
    ("gara_classification", "group_index", "INTEGER"),
    ("gara_classification", "group_position", "INTEGER"),
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
        presenti = _colonne(cursor, "gara")
        if {"max_groups", "group_seeding"} <= presenti:
            cursor.execute("UPDATE gara SET max_groups = 1 WHERE max_groups IS NULL")
            print(f"  ✓ {cursor.rowcount} gare esistenti: girone unico")
            cursor.execute(
                "UPDATE gara SET group_seeding = 'sorteggio' "
                "WHERE group_seeding IS NULL"
            )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
