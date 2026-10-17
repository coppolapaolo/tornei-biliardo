"""Link al video della partita e descrizione della sfida (2026-10-17).

* `match.video_url` e `individual_match.video_url`: il video della partita su
  YouTube, in forma canonica (`utils/video_link.py`);
* `individual_match.description`: che partita è, scritta da chi la gioca;
* `match_proposal.match_description`: la stessa descrizione scritta nella
  proposta, che passa alla sfida quando viene accettata. È una colonna a sé
  perché `match_proposal.description` è il messaggio all'invitato.

Tutte nascono NULL: nessuna partita cambia. Una tabella assente è un no-op
dichiarato, non un errore: una migration che solleva non viene marcata
applicata e `auto_deploy` la ritenta ogni notte per niente. Rilanciata, non
fa niente.
"""

import sqlite3

migration_name = "20261017_video_e_descrizione_partita"

COLONNE = (
    ("match", "video_url", "VARCHAR(300)"),
    ("individual_match", "video_url", "VARCHAR(300)"),
    ("individual_match", "description", "TEXT"),
    ("match_proposal", "match_description", "TEXT"),
)


def _colonne(cursor, tabella):
    return {riga[1] for riga in cursor.execute(f'PRAGMA table_info("{tabella}")')}


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
