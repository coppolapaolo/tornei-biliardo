"""Giocatori non ancora registrati, creati da direttori e istruttori (ADR-085).

* `user.is_placeholder`: il giocatore esiste per l'app — gioca, entra in
  classifica, ha un ELO — ma nessuno ha ancora l'account per entrare. Nasce
  senza email e con una password che non corrisponde a niente;
* `user.created_by_id`: chi l'ha creato. Servirà al riscatto: è lui che
  conferma che chi si registra è proprio quella persona. `SET NULL` se il
  creatore sparisce davvero (oggi gli utenti si anonimizzano e la riga resta);
* `user.claimed_at`: quando è stato riscattato. Resta NULL finché nessuno lo
  reclama.

I valori nascono falsi o NULL: nessun utente esistente cambia. Una tabella
assente è un no-op dichiarato, non un errore: una migration che solleva non
viene marcata applicata e `auto_deploy` la ritenta ogni notte per niente.
Rilanciata, non fa niente.
"""

import sqlite3

migration_name = "20261017_giocatori_non_registrati"

COLONNE = (
    ("user", "is_placeholder", "BOOLEAN NOT NULL DEFAULT 0"),
    (
        "user",
        "created_by_id",
        'INTEGER REFERENCES "user"(id) ON DELETE SET NULL',
    ),
    ("user", "claimed_at", "DATETIME"),
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
        if _colonne(cursor, "user"):
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS ix_user_is_placeholder "
                'ON "user" (is_placeholder)'
            )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
