"""La fase finale dopo i gironi, proposta dal campionato (ADR-081, ADR-075).

Quattro colonne nuove sul campionato, i valori di partenza delle sue gare a
girone all'italiana:

* `campionato.default_final_phase_mode` — nessuna o tabellone, di norma
  nessuna;
* `campionato.default_qualifiers_per_group` — quanti passano per girone, di
  norma 2;
* `campionato.default_third_place_match` — la finalina, di norma no;
* `campionato.default_final_phase_time_limit_minutes` — il limite di tempo
  della fase finale: NULL = come i gironi, 0 = senza limite, N = N minuti.

I campionati esistenti ricevono i default, che sono «nessuna fase finale»:
nessuna gara cambia, e nessuna proposta parte.

Una tabella assente è un no-op dichiarato, non un errore: una migration che
solleva non viene marcata applicata e `auto_deploy` la ritenta ogni notte per
niente. Rilanciata, non fa niente.
"""

import sqlite3

migration_name = "20261012_fase_finale_proposta"

COLONNE = (
    (
        "default_final_phase_mode",
        "VARCHAR(20) NOT NULL DEFAULT 'nessuna'",
    ),
    ("default_qualifiers_per_group", "INTEGER NOT NULL DEFAULT 2"),
    ("default_third_place_match", "BOOLEAN NOT NULL DEFAULT 0"),
    ("default_final_phase_time_limit_minutes", "INTEGER"),
)


def _colonne(cursor, tabella):
    return {riga[1] for riga in cursor.execute(f"PRAGMA table_info({tabella})")}


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        presenti = _colonne(cursor, "campionato")
        if not presenti:
            print("  ⏭️  tabella campionato assente")
            return
        for colonna, tipo in COLONNE:
            if colonna in presenti:
                print(f"  ⏭️  campionato.{colonna} già esistente")
                continue
            cursor.execute(f'ALTER TABLE "campionato" ADD COLUMN {colonna} {tipo}')
            print(f"  ✓ Aggiunta colonna campionato.{colonna}")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
