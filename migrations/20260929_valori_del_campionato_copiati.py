"""Chi apre, chi spacca e handicap si copiano sulla gara (ADR-075).

Fino al 2026-09-29 tre valori della gara restavano NULL = «segue il
campionato», e la gara li rileggeva dal campionato a ogni accesso:
`start_rule`, `break_rule` e `has_handicap`. Tutti gli altri valori del
campionato si copiavano già sulla gara quando nasce. Ora vale una regola sola —
il campionato propone, la gara decide — quindi i NULL delle gare di campionato
si riempiono con il valore che la gara usa **oggi**, con le stesse catene di
ripiego di `Gara.effective_*`:

* chi apre: campionato → `first_player` (il comportamento storico);
* chi spacca: campionato → `alternate`;
* handicap: campionato → no.

Nessuna gara cambia comportamento. Le gare fuori da un campionato non si
toccano: lì NULL non ha niente da cui ereditare. Idempotente: tocca solo i NULL.
Tabelle o colonne assenti sono un no-op dichiarato.
"""

import sqlite3

migration_name = "20260929_valori_del_campionato_copiati"

INIZIO = {"first_player", "lag"}
APERTURA = {"alternate", "winner_breaks", "loser_breaks", "alternate_two"}


def _colonne(cursor, tabella):
    return {riga[1] for riga in cursor.execute(f"PRAGMA table_info({tabella})")}


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        gara = _colonne(cursor, "gara")
        camp = _colonne(cursor, "campionato")
        servono_gara = {"start_rule", "break_rule", "has_handicap", "campionato_id"}
        servono_camp = {"default_start_rule", "default_break_rule", "has_handicap"}
        if not servono_gara <= gara or not servono_camp <= camp:
            print("  colonne assenti: niente da fare")
            return

        righe = cursor.execute("""
            SELECT g.id, g.start_rule, g.break_rule, g.has_handicap,
                   c.default_start_rule, c.default_break_rule, c.has_handicap
            FROM gara g JOIN campionato c ON c.id = g.campionato_id
            WHERE g.start_rule IS NULL OR g.break_rule IS NULL
               OR g.has_handicap IS NULL
            """).fetchall()
        for gid, sr, br, hh, c_sr, c_br, c_hh in righe:
            nuovi = {}
            if sr is None:
                nuovi["start_rule"] = c_sr if c_sr in INIZIO else "first_player"
            if br is None:
                nuovi["break_rule"] = c_br if c_br in APERTURA else "alternate"
            if hh is None:
                nuovi["has_handicap"] = 1 if c_hh else 0
            assegnazioni = ", ".join(f"{colonna} = ?" for colonna in nuovi)
            cursor.execute(
                f"UPDATE gara SET {assegnazioni} WHERE id = ?", (*nuovi.values(), gid)
            )
        print(f"  ✓ valori del campionato copiati su {len(righe)} gare")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
