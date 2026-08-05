"""Rimuove la disponibilità "località" a testo libero (ADR-033).

`PlayerAvailability` (tabella `player_availability`, basata su `location: str`)
è sostituita interamente da `UserLocationAvailability` (FK `billiard_hall_id`).

Questa migrazione:
1. Per ogni record `player_availability`, se la stringa `location` corrisponde
   (case-insensitive, trimmed) al `name` di una `billiard_hall`, crea il
   corrispondente record `user_location_availability` (se non già presente),
   mappando `preferred_days`→`available_days` e `preferred_times` ("HH:MM-HH:MM")
   →`preferred_time_start`/`preferred_time_end`.
2. I record senza sala corrispondente vengono scartati (perdita accettata,
   vedi ADR-033: erano luoghi non censiti).
3. `DROP TABLE player_availability`.

Idempotente: se la tabella `player_availability` non esiste, è un no-op.
"""

import sqlite3
from datetime import datetime, timezone

migration_name = "20260606_drop_player_availability"


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cursor.fetchone() is not None


def _parse_times(preferred_times):
    """'HH:MM-HH:MM' -> ('HH:MM:SS', 'HH:MM:SS') or (None, None)."""
    if not preferred_times:
        return None, None
    try:
        start_str, end_str = str(preferred_times).split("-")
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        return f"{sh:02d}:{sm:02d}:00", f"{eh:02d}:{em:02d}:00"
    except (ValueError, AttributeError):
        return None, None


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _table_exists(cursor, "player_availability"):
        print("  ⏭️  tabella player_availability assente, niente da fare")
        conn.close()
        return

    migrated = 0
    skipped = 0

    can_migrate = _table_exists(cursor, "billiard_hall") and _table_exists(
        cursor, "user_location_availability"
    )
    if can_migrate:
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        cursor.execute(
            "SELECT user_id, location, is_available, preferred_days, "
            "preferred_times FROM player_availability"
        )
        for (
            user_id,
            location,
            is_available,
            preferred_days,
            preferred_times,
        ) in cursor.fetchall():
            cursor.execute(
                "SELECT id FROM billiard_hall "
                "WHERE lower(trim(name)) = lower(trim(?)) LIMIT 1",
                (location,),
            )
            hall = cursor.fetchone()
            if not hall:
                skipped += 1
                continue
            hall_id = hall[0]

            cursor.execute(
                "SELECT id FROM user_location_availability "
                "WHERE user_id=? AND billiard_hall_id=?",
                (user_id, hall_id),
            )
            if cursor.fetchone():
                skipped += 1  # già presente come disponibilità sala: non sovrascrivere
                continue

            start, end = _parse_times(preferred_times)
            cursor.execute(
                "INSERT INTO user_location_availability "
                "(user_id, billiard_hall_id, is_available, available_days, "
                " preferred_time_start, preferred_time_end, notify_on_proposals, "
                " notify_on_cancellations, advance_notice_hours, "
                " matches_played_here, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, 1, 24, 0, ?, ?)",
                (
                    user_id,
                    hall_id,
                    1 if is_available else 0,
                    preferred_days,
                    start,
                    end,
                    now,
                    now,
                ),
            )
            migrated += 1
    else:
        print(
            "  ⚠️  billiard_hall/user_location_availability assenti: "
            "salto la migrazione dati"
        )

    cursor.execute("DROP TABLE player_availability")
    conn.commit()
    conn.close()
    print(
        f"  ✓ player_availability rimossa " f"(migrati {migrated}, scartati {skipped})"
    )
