"""La variante specchiata: una colonna sola su ``challenge_variant`` (fase 9c).

Una variante è la stessa prova vista dall'altro lato — destra e sinistra — e
finora l'autore doveva **ridisegnare** il tavolo per farla vedere: due disegni
da tenere allineati a mano, che è il difetto che l'ADR-065 evita per gli
esercizi e che rientrava dalla finestra con le varianti.

``mirrored`` dice che quella variante si mostra col disegno **ribaltato**: non
c'è un secondo disegno da nessuna parte, c'è una riflessione di quello che
esiste. Default ``0``, cioè il comportamento di prima per tutte le varianti già
scritte: nessun backfill da fare, perché nessuna di loro ha mai chiesto lo
specchio.

Idempotente: SQLite non ha ``ADD COLUMN IF NOT EXISTS``, quindi si guarda prima
il ``PRAGMA``.
"""

import sqlite3

migration_name = "20260920_variante_specchiata"

COLONNE = (("challenge_variant", "mirrored", "BOOLEAN NOT NULL DEFAULT 0"),)


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        for tabella, colonna, tipo in COLONNE:
            presenti = {
                riga[1] for riga in cursor.execute(f"PRAGMA table_info({tabella})")
            }
            if not presenti:
                # Tabella assente: no-op **dichiarato**, non un errore. Una
                # migration che solleva non viene marcata applicata, e
                # `auto_deploy` la ritenta ogni notte per niente.
                print(f"  {tabella} non esiste ancora: colonna {colonna} saltata")
                continue
            if colonna in presenti:
                print(f"  {tabella}.{colonna} c'era già: nulla da fare")
                continue
            cursor.execute(f"ALTER TABLE {tabella} ADD COLUMN {colonna} {tipo}")
            print(f"  ✓ {tabella}.{colonna}")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover - uso manuale
    upgrade_sqlite()
