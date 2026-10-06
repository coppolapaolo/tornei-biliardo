"""Il limite di tempo delle partite (ADR-077).

Quattro colonne nuove, e un solo riempimento:

* `campionato.default_time_limit_minutes` — i minuti proposti alle gare,
  0 = nessun limite. NOT NULL con default 0: è il valore che si copia sulla
  gara quando nasce (ADR-075);
* `gara.time_limit_minutes` — NULL = come il campionato (su una gara singola:
  nessun limite), 0 = senza limite per scelta, N = N minuti;
* `match.time_limit_minutes` — fissato quando la partita nasce, NULL = nessun
  limite;
* `match.timer_started_at` — quando è partito il conto alla rovescia.

Le **gare esistenti** ricevono 0, «senza limite» per scelta. Lasciate a NULL
leggerebbero il limite del campionato in diretta (`Gara.effective_time_limit_minutes`):
un campionato portato da 0 a 30 minuti lo darebbe subito a ogni gara vecchia,
anche a quelle avviate che la proposta alle gare salta (rilievo della revisione
automatica sulla PR #617). Le partite restano NULL: senza limite.

Nessuna partita esistente cambia. Una tabella
assente è un no-op dichiarato, non un errore: una migration che solleva non
viene marcata applicata e `auto_deploy` la ritenta ogni notte per niente.
Rilanciata, non fa niente.
"""

import sqlite3

migration_name = "20261006_limite_di_tempo"

COLONNE = (
    ("campionato", "default_time_limit_minutes", "INTEGER NOT NULL DEFAULT 0"),
    ("gara", "time_limit_minutes", "INTEGER"),
    ("match", "time_limit_minutes", "INTEGER"),
    ("match", "timer_started_at", "DATETIME"),
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
        if "time_limit_minutes" in _colonne(cursor, "gara"):
            cursor.execute(
                "UPDATE gara SET time_limit_minutes = 0 "
                "WHERE time_limit_minutes IS NULL"
            )
            print(f"  ✓ {cursor.rowcount} gare esistenti: senza limite di tempo")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
