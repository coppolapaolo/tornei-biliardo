"""Categorie di gioco per competizione, e smantellamento del vecchio impianto.

Feature (ADR-049): in una gara con handicap l'ELO torna ad aggiornarsi fra
giocatori della **stessa categoria**. Servono quindi le categorie come dato:

    categoria              nuova tabella, di proprietà del campionato XOR gara
    inscription.categoria_id   la categoria del giocatore in QUELLA gara

Contestualmente si smantella l'impianto categorie/handicap del 2025, che era
codice morto: `player_category` (categoria globale per utente, enum A/B/C/D
cablato), `handicap_rule` e le sue due tabelle figlie. Zero righe ovunque,
nessuna UI (la cartella `templates/rating/` non è mai esistita, quindi ogni
view del blueprint cadeva nell'except), nessun consumer.

ATTENZIONE — perché `handicap_rule` non si droppa e basta
---------------------------------------------------------
`match.handicap_rule_id` la referenzia con una FK, e `models/base.py` applica
`PRAGMA foreign_keys=ON` a ogni connessione. Con le FK attive, **anche un
INSERT che lascia la FK a NULL fallisce** se la tabella padre non esiste:

    DROP TABLE handicap_rule
    INSERT INTO match (..., handicap_rule_id) VALUES (..., NULL)
    → sqlite3.OperationalError: no such table: main.handicap_rule

Droppare la tabella senza prima togliere la colonna manderebbe quindi in
errore **ogni creazione di partita**, cioè ogni avvio di turno in produzione.
La colonna si toglie solo con `ALTER TABLE ... DROP COLUMN` (SQLite ≥ 3.35);
PythonAnywhere sta alla 3.31.1. Dove non si può, si applica il **no-op
dichiarato** già scelto per il Fargo (20260816): la tabella resta in piedi
vuota e la colonna resta orfana ma non mappata da SQLAlchemy, quindi inerte.

Le DROP delle tabelle sono precedute da un conteggio: se una non fosse vuota
la migration **non** la tocca e lo dice. Non solleva mai su una condizione
dell'ambiente — una migration che solleva non viene marcata applicata, e
`auto_deploy` la ritenterebbe ogni notte disabilitando la web app per niente.

Idempotente: ogni passo è guardato da PRAGMA / IF NOT EXISTS / IF EXISTS.
"""

import json
import sqlite3

migration_name = "20260819_categorie_competizione"

#: Versione minima di SQLite con `ALTER TABLE ... DROP COLUMN`.
DROP_COLUMN_MIN_VERSION = (3, 35, 0)

#: Tabelle del vecchio impianto senza dipendenze in entrata: droppabili subito.
DEAD_TABLES = ("category_handicap_rule", "rating_handicap_rule", "player_category")

#: I due traguardi che promettevano una categoria che nessuno poteva ricevere.
#: Ricablati sulla fascia ELO, che è la scala già usata da
#: PlayerRating.get_category_equivalent (≥1800 → A, ≥1500 → B).
ACHIEVEMENT_REWRITES = {
    "category_climber": (
        json.dumps({"type": "elo_reached", "rating": 1500}),
        "Raggiungi 1500 punti Elo",
    ),
    "elite_player": (
        json.dumps({"type": "elo_reached", "rating": 1800}),
        "Raggiungi 1800 punti Elo",
    ),
}


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def _row_count(cursor: sqlite3.Cursor, table: str) -> int:
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    return cursor.fetchone()[0]


def _supports_drop_column() -> bool:
    return sqlite3.sqlite_version_info >= DROP_COLUMN_MIN_VERSION


def _drop_if_empty(cursor: sqlite3.Cursor, table: str) -> None:
    """Droppa la tabella solo se è vuota; altrimenti lo dice e prosegue."""
    if not _table_exists(cursor, table):
        print(f"  ⏭️  {table} già assente")
        return
    righe = _row_count(cursor, table)
    if righe:
        print(
            f"  ⚠️  {table} contiene {righe} righe: NON la elimino. "
            "Nessun codice ha mai potuto scriverla — vanno guardate prima."
        )
        return
    cursor.execute(f"DROP TABLE {table}")
    print(f"  ✓ {table} eliminata (era vuota)")


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # ── 1. La tabella nuova ──────────────────────────────────────────
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categoria (
                id INTEGER PRIMARY KEY,
                name VARCHAR(50) NOT NULL,
                normalized_name VARCHAR(50) NOT NULL,
                campionato_id INTEGER REFERENCES campionato (id) ON DELETE CASCADE,
                gara_id INTEGER REFERENCES gara (id) ON DELETE CASCADE,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                CONSTRAINT ck_categoria_owner_exclusive CHECK (
                    (campionato_id IS NOT NULL AND gara_id IS NULL)
                    OR (campionato_id IS NULL AND gara_id IS NOT NULL)
                )
            )
            """)
        print("  ✓ Tabella categoria pronta")

        # Unicità **parziali**: in SQLite un UNIQUE su (campionato_id, nome)
        # non vincola le righe con campionato_id NULL, che sono proprio quelle
        # delle gare standalone. Stessa ragione della migration delle squadre.
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_categoria_campionato_name "
            "ON categoria (campionato_id, normalized_name) "
            "WHERE campionato_id IS NOT NULL"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_categoria_gara_name "
            "ON categoria (gara_id, normalized_name) WHERE gara_id IS NOT NULL"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_categoria_campionato "
            "ON categoria (campionato_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_categoria_gara ON categoria (gara_id)"
        )
        print("  ✓ Indici di categoria pronti")

        # ── 2. La categoria dell'iscritto ────────────────────────────────
        if _column_exists(cursor, "inscription", "categoria_id"):
            print("  ⏭️  inscription.categoria_id già presente")
        else:
            cursor.execute(
                "ALTER TABLE inscription ADD COLUMN categoria_id INTEGER "
                "REFERENCES categoria (id) ON DELETE SET NULL"
            )
            print("  ✓ Colonna inscription.categoria_id aggiunta")

        # ── 3. I due traguardi ricablati ─────────────────────────────────
        # `seed_achievements` salta le righe già presenti, quindi sui DB
        # popolati il solo cambio nei seed non arriverebbe mai: serve l'UPDATE.
        if _table_exists(cursor, "achievement"):
            for slug, (requirements, description) in ACHIEVEMENT_REWRITES.items():
                cursor.execute(
                    "UPDATE achievement SET requirements = ?, description = ?, "
                    "is_active = 1 WHERE slug = ?",
                    (requirements, description, slug),
                )
                if cursor.rowcount:
                    print(f"  ✓ Traguardo «{slug}» ricablato sulla fascia Elo")

        # ── 4. Le tabelle morte senza dipendenze ─────────────────────────
        for table in DEAD_TABLES:
            _drop_if_empty(cursor, table)

        # ── 5. handicap_rule, il passo delicato (vedi docstring) ─────────
        _drop_handicap_rule(cursor)

        # Un commit solo, in fondo: se un passo intermedio fallisse, non si
        # resterebbe con metà lavoro scritto e la migration non marcata.
        conn.commit()
    finally:
        conn.close()


def _drop_handicap_rule(cursor: sqlite3.Cursor) -> None:
    if not _table_exists(cursor, "handicap_rule"):
        print("  ⏭️  handicap_rule già assente")
        return

    righe = _row_count(cursor, "handicap_rule")
    if righe:
        print(
            f"  ⚠️  handicap_rule contiene {righe} righe: NON la elimino. "
            "Nessun codice ha mai potuto scriverla — vanno guardate prima."
        )
        return

    if not _column_exists(cursor, "match", "handicap_rule_id"):
        cursor.execute("DROP TABLE handicap_rule")
        print("  ✓ handicap_rule eliminata (nessuna FK la referenzia più)")
        return

    if _supports_drop_column():
        cursor.execute("ALTER TABLE match DROP COLUMN handicap_rule_id")
        cursor.execute("DROP TABLE handicap_rule")
        print("  ✓ match.handicap_rule_id e handicap_rule eliminate")
        return

    print(
        f"  ⏭️  SQLite {sqlite3.sqlite_version} non ha ALTER TABLE DROP COLUMN "
        f"(serve la {'.'.join(str(n) for n in DROP_COLUMN_MIN_VERSION)}): "
        "match.handicap_rule_id resta, e con essa handicap_rule — vuota. "
        "Eliminare la tabella lasciando la FK farebbe fallire OGNI insert su "
        "match, cioè ogni avvio di turno. La colonna non è più mappata da "
        "SQLAlchemy, quindi è inerte."
    )


if __name__ == "__main__":
    upgrade_sqlite()
