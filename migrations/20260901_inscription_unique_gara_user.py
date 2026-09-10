"""Un giocatore, un'iscrizione per gara — anche per il database.

In produzione, gara 39: un giocatore iscritto dal direttore con la categoria B
si è ricreato un account e si è riscritto da solo, senza categoria. L'admin ha
unito i due account e nella gara sono rimasti **due** iscritti con lo stesso
nome, uno con categoria e uno senza.

La causa è che l'unicità di `(gara_id, user_id)` non era mai stata dichiarata:
viveva in `InscriptionService.inscribe_user`, che prima di creare controlla se
l'iscrizione c'è già. `UserMergeService` non passa di lì — riassegna le chiavi
esterne in SQL — e per decidere se una colonna vada spostata riga per riga o in
blocco guarda proprio i vincoli dello schema. Nessun vincolo, `UPDATE` di
massa, doppione.

Questa migration fa due cose, in quest'ordine:

1. **fonde i doppioni già scritti**, con la regola di
   `models/competition/inscription_dedup.py`: sopravvive la riga più vecchia,
   i campi vuoti si riempiono con quelli dell'altra, lo stato si prende in
   blocco dalla riga più avanzata (attivo > lista d'attesa > ritirato);
2. **crea l'indice unico**, senza il quale il punto 1 riparerebbe il passato e
   lascerebbe aperto il futuro.

La regola è scritta due volte — qui in SQL e là in Python — perché una
migration deve saper girare da sola, senza importare modelli che nel frattempo
cambiano forma. Che le due dicano la stessa cosa non è affidato alla buona
volontà: `tests/new/unit/test_migration_inscription_unique.py` esegue *questa*
migration su un database temporaneo e ne confronta l'esito con
`piano_di_fusione`.

Dove i doppioni non ci sono — sviluppo, ogni installazione nuova, e la
produzione se `scripts/fix_iscrizioni_duplicate.py` è già passato — il punto 1
è un no-op che lo dichiara, e resta solo l'indice.
"""

import sqlite3

migration_name = "20260901_inscription_unique_gara_user"

INDICE = "uq_inscription_gara_user"

#: Si prendono tutti dalla riga più avanzata: mescolarli produce stati
#: incoerenti (una `waitlist_position` senza `is_waitlist` non vuol dire nulla).
CAMPI_STATO = (
    "is_waitlist",
    "waitlist_position",
    "waitlist_reason",
    "is_withdrawn",
    "withdrawn_at",
    "is_forfeit",
    "forfeit_at",
)

#: Dati indipendenti fra loro: si riempiono buco per buco.
CAMPI_DATO = ("categoria_id", "squadra_id", "initial_order")


def _colonne(cursor: sqlite3.Cursor, tabella: str) -> set:
    cursor.execute(f"PRAGMA table_info({tabella})")
    return {row[1] for row in cursor.fetchall()}


def _tabella_esiste(cursor: sqlite3.Cursor, tabella: str) -> bool:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabella,)
    )
    return cursor.fetchone() is not None


def _rango_stato(riga: sqlite3.Row) -> int:
    if riga["is_withdrawn"]:
        return 0
    return 1 if riga["is_waitlist"] else 2


def _anzianita(riga: sqlite3.Row):
    # `created_at` è nullable: i NULL vanno in coda, non a confronto con una data.
    return (riga["created_at"] is None, riga["created_at"] or "", riga["id"])


def _fondi_gruppo(cursor: sqlite3.Cursor, righe: list, campi_dato: tuple) -> None:
    """Riduce a una le iscrizioni di ``righe`` (stessa gara, stesso giocatore)."""
    per_anzianita = sorted(righe, key=_anzianita)
    sopravvissuta = per_anzianita[0]
    valori = {}

    for campo in campi_dato:
        if sopravvissuta[campo] is not None:
            continue
        for altra in per_anzianita[1:]:
            if altra[campo] is not None:
                valori[campo] = altra[campo]
                break

    piu_avanzata = max(per_anzianita, key=_rango_stato)
    if piu_avanzata["id"] != sopravvissuta["id"]:
        for campo in CAMPI_STATO:
            if piu_avanzata[campo] != sopravvissuta[campo]:
                valori[campo] = piu_avanzata[campo]

    if valori:
        assegnazioni = ", ".join(f"{campo} = ?" for campo in valori)
        cursor.execute(
            f"UPDATE inscription SET {assegnazioni} WHERE id = ?",
            (*valori.values(), sopravvissuta["id"]),
        )

    da_cancellare = [riga["id"] for riga in per_anzianita[1:]]

    # Le righe nascoste dal profilo puntano all'id dell'iscrizione: si
    # ripuntano sulla sopravvissuta, altrimenti il CASCADE se le porta via e
    # chi aveva nascosto quella gara se la ritrova pubblica.
    if _tabella_esiste(cursor, "hidden_inscription"):
        for vecchio_id in da_cancellare:
            cursor.execute(
                "DELETE FROM hidden_inscription WHERE inscription_id = ? "
                "AND user_id IN (SELECT user_id FROM hidden_inscription "
                "                WHERE inscription_id = ?)",
                (vecchio_id, sopravvissuta["id"]),
            )
            cursor.execute(
                "UPDATE hidden_inscription SET inscription_id = ? "
                "WHERE inscription_id = ?",
                (sopravvissuta["id"], vecchio_id),
            )

    segnaposto = ", ".join("?" for _ in da_cancellare)
    cursor.execute(
        f"DELETE FROM inscription WHERE id IN ({segnaposto})", tuple(da_cancellare)
    )


def upgrade_sqlite(db_path: str = "instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        if not _tabella_esiste(cursor, "inscription"):
            print("  ⏭️  inscription non esiste: nascerà già col vincolo")
            return

        # Su un DB storico qualche colonna può mancare: si chiede allo schema
        # invece di darlo per scontato, così la migration non muore su
        # un'installazione vecchia.
        presenti = _colonne(cursor, "inscription")
        campi_dato = tuple(c for c in CAMPI_DATO if c in presenti)

        cursor.execute(
            "SELECT gara_id, user_id FROM inscription "
            "GROUP BY gara_id, user_id HAVING COUNT(id) > 1"
        )
        gruppi = cursor.fetchall()

        for gara_id, user_id in gruppi:
            cursor.execute(
                "SELECT * FROM inscription WHERE gara_id = ? AND user_id = ?",
                (gara_id, user_id),
            )
            righe = cursor.fetchall()
            _fondi_gruppo(cursor, righe, campi_dato)
            print(
                f"  ✓ gara {gara_id}, giocatore {user_id}: "
                f"{len(righe)} iscrizioni → 1"
            )

        if not gruppi:
            print("  ⏭️  nessuna iscrizione doppia da fondere")

        cursor.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {INDICE} "
            "ON inscription (gara_id, user_id)"
        )
        print(f"  ✓ indice {INDICE} presente")

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
