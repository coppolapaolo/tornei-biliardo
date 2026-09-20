"""Il passaggio di livello: chi lo sancisce, e quando (D8, ADR-071).

Quattro colonne, nessuna tabella nuova.

Su ``training_sheet``:

* ``level_up`` — chi sancisce il gradino: `none`, `auto` (la soglia stessa),
  `instructor` (chi legge la scheda). Default **`auto`**, che è ciò che la
  scheda faceva già prima di questa colonna: la fine seduta diceva «gradino
  raggiunto» e nessuno lo timbrava. Alle schede che esistono già tocca lo
  stesso default, ed è la risposta giusta — nessuna di loro ha mai chiesto la
  conferma di qualcuno;
* ``passed_at`` / ``passed_by_id`` — quando il livello è stato superato, e da
  chi. NULL su `passed_by_id` vuol dire che a sancirlo è stata la soglia, e
  sono due frasi diverse da leggere. **Niente backfill**: una scheda superata
  è un fatto avvenuto in un giorno, e inventarne la data per le schede vecchie
  scriverebbe nello storico qualcosa che non è successo.

Su ``training_assignment``:

* ``promotes_sheet_id`` — la scheda che questa proposta **promuove**, quando è
  «dagli il livello successivo». È il secondo gesto del passaggio, quello
  facoltativo: il timbro dice che è superata, la proposta dà il gradino dopo.

**Il nome non è un vezzo.** Il runner esegue le migration in ordine
alfabetico, e questa tocca una tabella che ne crea un'altra dello stesso
giorno: `20260920_passaggio_…` sarebbe girata **prima** di
`20260920_proposte_di_scheda`, cioè su una `training_assignment` che ancora
non esiste — e una migration che solleva non viene marcata applicata, quindi
`auto_deploy` la ritenterebbe ogni notte disabilitando la web app per niente.
`superato_…` viene dopo `proposte_…`. La guardia sulla tabella mancante resta
lo stesso, e dichiara il no-op invece di sollevare.

Idempotente: SQLite non ha ``ADD COLUMN IF NOT EXISTS``, quindi si guarda
prima il ``PRAGMA``.
"""

import sqlite3

migration_name = "20260920_superato_il_livello"

COLONNE = (
    ("training_sheet", "level_up", "VARCHAR(12) NOT NULL DEFAULT 'auto'"),
    ("training_sheet", "passed_at", "DATETIME"),
    (
        "training_sheet",
        "passed_by_id",
        "INTEGER REFERENCES user(id) ON DELETE SET NULL",
    ),
    (
        "training_assignment",
        "promotes_sheet_id",
        "INTEGER REFERENCES training_sheet(id) ON DELETE SET NULL",
    ),
)


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        for tabella, colonna, tipo in COLONNE:
            presenti = {
                riga[1] for riga in cursor.execute(f"PRAGMA table_info({tabella})")
            }
            if not presenti:
                # Tabella assente: no-op **dichiarato**, non un errore. Con
                # l'ordine alfabetico non capita in produzione; capita su un
                # database di prova fermo a prima di questa fase.
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
