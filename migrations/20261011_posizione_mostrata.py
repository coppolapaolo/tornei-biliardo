"""La posizione da mostrare accanto a quella che decide (2026-10-11).

Il pari merito si mostra sempre alla posizione più alta: chi è separato dagli
altri solo dal sorteggio è a pari merito, e due primi sono «1°» entrambi
(SPECIFICHE.md, «Classifica», nota del 2026-10-11). La posizione che decide —
abbinamenti, taglio, inviti, punti — resta `position`; quella da mostrare va
in colonne sue:

- `round_classification`: `shown_position`, `shown_group_position`,
  `shown_previous_position` (per la freccia di tendenza);
- `gara_classification`: `shown_position`, `shown_group_position`;
- `classification`: `shown_position`.

Nessun riempimento: NULL vuol dire «come la posizione», e il prossimo
ricalcolo le scrive. Una tabella assente è un no-op dichiarato, non un
errore. Rilanciata, non fa niente.
"""

import sqlite3

migration_name = "20261011_posizione_mostrata"

COLONNE = {
    "round_classification": (
        "shown_position",
        "shown_group_position",
        "shown_previous_position",
    ),
    "gara_classification": ("shown_position", "shown_group_position"),
    "classification": ("shown_position",),
}


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        for tabella, colonne in COLONNE.items():
            presenti = {
                riga[1] for riga in cursor.execute(f"PRAGMA table_info({tabella})")
            }
            if not presenti:
                print(f"  ⏭️  tabella {tabella} assente")
                continue
            for colonna in colonne:
                if colonna in presenti:
                    print(f"  ⏭️  {tabella}.{colonna} già esistente")
                    continue
                cursor.execute(f'ALTER TABLE "{tabella}" ADD COLUMN {colonna} INTEGER')
                print(f"  ✓ Aggiunta colonna {tabella}.{colonna}")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
