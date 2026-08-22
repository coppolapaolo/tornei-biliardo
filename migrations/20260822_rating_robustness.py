"""Rinomina i due campi che contavano partite e ora contano rack.

Col passaggio al motore a rack (ADR-052) `player_rating.games_played` ha
smesso di contare le partite: contiene i **rack**, cioè la *robustness* di
FargoRate, e serve solo a regolare quanto in fretta il rating si muove. Idem
per `match_rating_history.games_increment`, che dice quanti rack quella partita
ha aggiunto.

Un nome rimasto vero fino a ieri e falso da oggi è esattamente la trappola di
`rack_difference`, che conteneva un totale mentre il nome prometteva una
differenza: non dà errori, non fa fallire test, e si scopre il giorno in cui
qualcuno mostra il campo in una schermata — con «40 partite» a chi ne ha
giocate 6.

Si rinomina adesso perché adesso è gratis: nessuno legge quei due campi fuori
da `models/rating/`, verificato su `models/`, `routes/` e `templates/`.

Idempotente: guarda le colonne presenti e non fa niente se il rinomino c'è
già. Su un DB dove esistessero entrambe (non dovrebbe succedere) si ferma
dicendolo, invece di indovinare quale sia buona.
"""

import sqlite3

migration_name = "20260822_rating_robustness"

#: (tabella, nome vecchio, nome nuovo)
RINOMINI = (
    ("player_rating", "games_played", "robustness"),
    ("match_rating_history", "games_increment", "robustness_increment"),
)


def _colonne(cursor: sqlite3.Cursor, tabella: str) -> set:
    cursor.execute(f"PRAGMA table_info({tabella})")
    return {riga[1] for riga in cursor.fetchall()}


def _tabella_esiste(cursor: sqlite3.Cursor, tabella: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabella,)
    )
    return cursor.fetchone() is not None


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db") -> None:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        for tabella, vecchio, nuovo in RINOMINI:
            if not _tabella_esiste(cursor, tabella):
                print(f"  ⏭️  {tabella} non esiste, salto")
                continue

            colonne = _colonne(cursor, tabella)
            if nuovo in colonne and vecchio in colonne:
                # Non è una condizione che ci si aspetta: meglio dirlo che
                # scegliere a caso quale delle due tenere.
                print(
                    f"  ⚠️  {tabella}: esistono sia {vecchio} sia {nuovo}, "
                    f"intervento manuale"
                )
                continue
            if nuovo in colonne:
                print(f"  ⏭️  {tabella}.{nuovo} già rinominata")
                continue
            if vecchio not in colonne:
                print(f"  ⏭️  {tabella}: nessuna colonna {vecchio}, salto")
                continue

            cursor.execute(f"ALTER TABLE {tabella} RENAME COLUMN {vecchio} TO {nuovo}")
            print(f"  ✓ {tabella}: {vecchio} → {nuovo}")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
