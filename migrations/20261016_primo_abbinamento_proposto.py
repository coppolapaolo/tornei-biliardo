"""Il primo abbinamento proposto dal campionato alle sue gare (ADR-075).

`campionato.default_first_round_policy` è il valore di partenza di
`gara.first_round_policy` per le gare che nascono nel campionato: casuale,
basato sul rating, o basato sulla classifica del campionato. Fino a oggi ogni
gara nasceva «casuale» e chi voleva il turno 1 dalla classifica doveva
cambiarlo a mano gara per gara; il preset di campionato non poteva portarlo.

La colonna nasce NULL, che vale «casuale»: nessun campionato e nessuna gara
cambia. Una tabella assente è un no-op dichiarato, non un errore: una
migration che solleva non viene marcata applicata e `auto_deploy` la ritenta
ogni notte per niente. Rilanciata, non fa niente.
"""

import sqlite3

migration_name = "20261016_primo_abbinamento_proposto"

COLONNE = (("campionato", "default_first_round_policy", "VARCHAR(50)"),)


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
