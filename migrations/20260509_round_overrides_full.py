"""Estende RoundConfiguration e Match per supportare override per turno completi.

Source: ADR-027 (round-level configuration enforcement). La UI in
templates/components/_round_management.html prometteva override di disciplina
e distanza per turno, ma li salvava solo in localStorage del browser. Il modello
RoundConfiguration esisteva ma era dead code (nessun route lo popolava) e i
match venivano creati con il solo `match_distance` impostato dal valore di
gara, mai con `is_race_to`. La conseguenza in produzione: l'utente vedeva la UI
applicare override (per es. "4 rack esatti" sul turno 2) ma il backend ignorava
tutto, lasciando i match validati con la distanza della gara.

Questa migration:
1. Aggiunge `match.is_race_to` (Boolean nullable) — override modalità per match
2. Aggiunge `match.is_race_to_sets` (Boolean nullable) — override per multi-set
3. Aggiunge a `round_configuration`: `is_race_to`, `is_multi_set`,
   `match_distance`, `is_race_to_sets` (tutte nullable, NULL = eredita da gara)
4. Backfill: per i match single-set legacy con `match_distance=1` o NULL, lo
   uniforma a `gara.distance`. Era il valore default schema-level che aveva
   forzato `Distance.from_match` a una orribile heuristic per distinguere
   "non popolato" da "popolato a 1". Dopo questo backfill, la heuristic può
   essere semplificata a `match.match_distance or gara.distance`.

Idempotente: ogni ALTER TABLE è preceduto da PRAGMA table_info check, e il
backfill UPDATE filtra solo le righe ancora a 1/NULL.
"""

import sqlite3

migration_name = "20260509_round_overrides_full"


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ── 1. Match: aggiungi is_race_to e is_race_to_sets ──────────────────
    if not _column_exists(cursor, "match", "is_race_to"):
        cursor.execute("ALTER TABLE match ADD COLUMN is_race_to BOOLEAN")
        print("  ✓ Aggiunta colonna match.is_race_to")
    else:
        print("  ⏭️  match.is_race_to già esistente")

    if not _column_exists(cursor, "match", "is_race_to_sets"):
        cursor.execute("ALTER TABLE match ADD COLUMN is_race_to_sets BOOLEAN")
        print("  ✓ Aggiunta colonna match.is_race_to_sets")
    else:
        print("  ⏭️  match.is_race_to_sets già esistente")

    # ── 2. RoundConfiguration: estendi con tutti i campi override ────────
    rc_cols = [
        ("is_race_to", "BOOLEAN"),
        ("is_multi_set", "BOOLEAN"),
        ("match_distance", "INTEGER"),
        ("is_race_to_sets", "BOOLEAN"),
    ]
    for col_name, col_type in rc_cols:
        if not _column_exists(cursor, "round_configuration", col_name):
            cursor.execute(
                f"ALTER TABLE round_configuration ADD COLUMN {col_name} {col_type}"
            )
            print(f"  ✓ Aggiunta colonna round_configuration.{col_name}")
        else:
            print(f"  ⏭️  round_configuration.{col_name} già esistente")

    # Migra il vecchio campo `best_of` (deprecato) a `is_race_to` se possibile.
    # `best_of` era nullable e mai popolato in produzione (RoundConfiguration
    # era dead code), ma lo gestiamo per completezza.
    if _column_exists(cursor, "round_configuration", "best_of"):
        cursor.execute("""
            UPDATE round_configuration
            SET is_race_to = best_of
            WHERE best_of IS NOT NULL AND is_race_to IS NULL
        """)
        moved = cursor.rowcount
        if moved:
            print(f"  ✓ Migrati {moved} valori da best_of a is_race_to")

    # ── 3. Backfill match.match_distance legacy ──────────────────────────
    # I match creati prima del fix avevano match_distance=1 (default schema)
    # quando la gara era single-set. Questo costringeva Distance.from_match
    # a una heuristic imprecisa. Uniformiamo tutti i match single-set legacy.
    cursor.execute("""
        SELECT COUNT(*)
        FROM match m
        JOIN gara g ON g.id = m.gara_id
        WHERE m.gara_id IS NOT NULL
          AND (m.is_multi_set IS NULL OR m.is_multi_set = 0)
          AND (m.match_distance IS NULL OR m.match_distance = 1)
          AND g.distance > 1
    """)
    legacy_count = cursor.fetchone()[0]

    if legacy_count > 0:
        cursor.execute("""
            UPDATE match
            SET match_distance = (
                SELECT distance FROM gara WHERE gara.id = match.gara_id
            )
            WHERE gara_id IS NOT NULL
              AND (is_multi_set IS NULL OR is_multi_set = 0)
              AND (match_distance IS NULL OR match_distance = 1)
              AND (SELECT distance FROM gara WHERE gara.id = match.gara_id) > 1
        """)
        print(f"  ✓ Backfill match.match_distance per {legacy_count} match legacy")
    else:
        print("  ⏭️  Nessun match legacy da uniformare")

    conn.commit()
    conn.close()
