"""Le regole della fase finale e della sola finale (ADR-081, emendamento).

Il tabellone dopo i gironi ha già il suo limite di tempo
(`gara.final_phase_time_limit_minutes`, migration 20261011). Prima dell'avvio
non si sa quale numero di turno sarà la finale — dipende da quanti gironi
sceglie il direttore nel foglio di avvio — quindi le altre regole del
tabellone si scrivono **per fase**, non per turno (decisione dell'utente del
2026-10-12):

* `gara.final_phase_distance` — la distanza delle partite del tabellone:
  NULL = come i gironi, N = «al N»;
* `gara.final_time_limit_minutes` — il limite di tempo della sola finale:
  NULL = come la fase finale, 0 = senza limite, N minuti;
* `gara.final_distance` — la distanza della sola finale: NULL = come la fase
  finale, N = «al N».

Le stesse tre sul campionato, con il prefisso `default_`: le propone alle sue
gare (ADR-075). Tutte nascono NULL, cioè «come prima»: nessuna gara cambia.

Una tabella assente è un no-op dichiarato, non un errore: una migration che
solleva non viene marcata applicata e `auto_deploy` la ritenta ogni notte per
niente. Rilanciata, non fa niente.
"""

import sqlite3

migration_name = "20261012_regole_della_finale"

COLONNE = (
    ("gara", "final_phase_distance", "INTEGER"),
    ("gara", "final_time_limit_minutes", "INTEGER"),
    ("gara", "final_distance", "INTEGER"),
    ("campionato", "default_final_phase_distance", "INTEGER"),
    ("campionato", "default_final_time_limit_minutes", "INTEGER"),
    ("campionato", "default_final_distance", "INTEGER"),
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
