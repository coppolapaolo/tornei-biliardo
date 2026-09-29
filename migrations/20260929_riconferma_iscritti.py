"""La riconferma degli iscritti: le condizioni accettate (ADR-075).

Una colonna nuova su `inscription` e su `playoff_qualification`:
`accepted_terms`, in JSON, con data, ora, sala e quota che il giocatore ha
accettato. Se quelle della gara cambiano oltre soglia, gli si chiede se c'è
ancora.

Si riempie con le condizioni di **adesso** per le iscrizioni e gli inviti
accettati che esistono già: nessuno si trova da riconfermare per una modifica
fatta prima che la riconferma esistesse, e le modifiche da qui in avanti si
vedono. Tocca solo le righe con la colonna vuota: idempotente. Tabelle
assenti sono un no-op dichiarato.
"""

import json
import sqlite3

migration_name = "20260929_riconferma_iscritti"


def _colonne(cursor, tabella):
    return {riga[1] for riga in cursor.execute(f"PRAGMA table_info({tabella})")}


def _testo_quota(quota):
    if quota is None:
        return ""
    if isinstance(quota, float) and quota.is_integer():
        return str(int(quota))
    return str(quota)


def _termini(data, ora, sala, quota):
    return json.dumps(
        {
            "date": data or "",
            "time": (ora or "")[:5],
            "location": sala or "",
            "entry_fee": _testo_quota(quota),
        },
        sort_keys=True,
    )


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        tabelle = {r[0] for r in cursor.execute("SELECT name FROM sqlite_master")}
        if "inscription" in tabelle:
            if "accepted_terms" not in _colonne(cursor, "inscription"):
                cursor.execute("ALTER TABLE inscription ADD COLUMN accepted_terms TEXT")
            righe = cursor.execute("""
                SELECT i.id, g.date, g.time, g.location, g.entry_fee
                FROM inscription i JOIN gara g ON g.id = i.gara_id
                WHERE i.accepted_terms IS NULL
                """).fetchall()
            for iid, data, ora, sala, quota in righe:
                cursor.execute(
                    "UPDATE inscription SET accepted_terms = ? WHERE id = ?",
                    (_termini(data, ora, sala, quota), iid),
                )
            print(f"  ✓ inscription.accepted_terms ({len(righe)} righe)")
        if "playoff_qualification" in tabelle:
            if "accepted_terms" not in _colonne(cursor, "playoff_qualification"):
                cursor.execute(
                    "ALTER TABLE playoff_qualification ADD COLUMN accepted_terms TEXT"
                )
            righe = cursor.execute("""
                SELECT q.id, c.scheduled_date, c.location, c.entry_fee
                FROM playoff_qualification q
                JOIN playoff_configuration c ON c.id = q.configuration_id
                WHERE q.accepted_terms IS NULL AND q.status = 'CONFIRMED'
                """).fetchall()
            for qid, quando, sala, quota in righe:
                data, _, ora = (quando or "").partition(" ")
                cursor.execute(
                    "UPDATE playoff_qualification SET accepted_terms = ? WHERE id = ?",
                    (_termini(data, ora, sala, quota), qid),
                )
            print(f"  ✓ playoff_qualification.accepted_terms ({len(righe)} righe)")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
