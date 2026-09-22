"""Le prove fatte in scheda sono prove del catalogo (ADR-072).

Tre colonne, nessuna tabella nuova:

* `training_sheet_item.aggregation` — col punteggio, come le N prove fanno il
  numero della casella: somma, media, mediana, massimo. NULL sulle altre
  misure, e su tutte le voci già scritte;
* `training_entry.aggregation` — la stessa cosa **copiata sulla casella** al
  momento in cui si segna, come misura e «su quanto» (ADR-067 §3);
* `challenge_attempt.training_entry_id` — la casella di cui la prova fa
  parte. NULL su ogni prova fatta da sola, cioè su tutte quelle di prima. Con
  la casella sparisce anche la prova: chi svuota dice che non c'è stata.

`training_entry.value` resta INTEGER: SQLite ci scrive 6,5 dove scriveva 6
(affinità, non tipo), e il modello lo rilegge intero quando lo è.

Nessun backfill: le caselle scritte prima non hanno prove dietro, perché ora e
ordine non si sanno, e si leggono come si leggevano.

Idempotente: SQLite non ha ``ADD COLUMN IF NOT EXISTS``, quindi si guarda
prima il ``PRAGMA``. Una tabella assente è un no-op dichiarato, non un errore:
una migration che solleva non viene marcata applicata e `auto_deploy` la
ritenta ogni notte per niente.
"""

import sqlite3

migration_name = "20260922_prove_in_scheda"

COLONNE = (
    ("training_sheet_item", "aggregation", "VARCHAR(10)"),
    ("training_entry", "aggregation", "VARCHAR(10)"),
    (
        "challenge_attempt",
        "training_entry_id",
        "INTEGER REFERENCES training_entry(id) ON DELETE CASCADE",
    ),
)

INDICI = (
    (
        "ix_challenge_attempt_training_entry_id",
        "challenge_attempt",
        "training_entry_id",
    ),
)


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        for tabella, colonna, tipo in COLONNE:
            presenti = {
                riga[1] for riga in cursor.execute(f"PRAGMA table_info({tabella})")
            }
            if not presenti:
                print(f"  {tabella} non esiste ancora: colonna {colonna} saltata")
                continue
            if colonna in presenti:
                print(f"  {tabella}.{colonna} c'era già: nulla da fare")
                continue
            cursor.execute(f"ALTER TABLE {tabella} ADD COLUMN {colonna} {tipo}")
            print(f"  ✓ {tabella}.{colonna}")
        for nome, tabella, colonna in INDICI:
            presenti = {
                riga[1] for riga in cursor.execute(f"PRAGMA table_info({tabella})")
            }
            if colonna not in presenti:
                continue
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS {nome} ON {tabella} ({colonna})"
            )
            print(f"  ✓ indice {nome}")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover - uso manuale
    upgrade_sqlite()
