"""Le catene degli spareggi configurabili (ADR-078).

Cinque colonne nuove, liste JSON di voci (`ordinamento.testo_della_catena`):

* `gara.catena_turno` e `gara.catena_gara` — come si ordinano i pari merito
  nella classifica di turno e in quella di gara. NULL = come il campionato
  (su una gara singola: il default dell'app);
* `campionato.default_catena_turno` e `campionato.default_catena_gara` — le
  catene che il campionato propone alle sue gare (ADR-075);
* `campionato.catena_generale` — la catena della classifica generale.

Il riempimento riproduce **esattamente** il comportamento di prima:

* la catena di gara di ogni gara nasce dalle due colonne dello spareggio:
  `tiebreaker_enabled` acceso → `ssr:N` con `N = tiebreaker_until_position or
  3`, spento → senza spareggio. Vittorie: differenza, poi lo spareggio;
  triangoli: solo lo spareggio;
* la catena di turno di ogni gara, e le tre del campionato, sono quelle di
  default del loro sistema. Lasciate a NULL leggerebbero il campionato in
  diretta: una proposta nuova arriverebbe anche alle gare avviate, che la
  proposta salta (la stessa lezione del limite di tempo, PR #617).

Il sistema POSITION non si ordina con la catena (ADR-040): riceve le catene a
vittorie, che nessuno legge.

Le colonne `tiebreaker_enabled`, `tiebreaker_until_position` e
`tiebreaker_mode` restano nel database ma escono dal modello: con i loro
default non intralciano gli INSERT, e toglierle non serve a niente.

Le catene di default sono scritte qui per esteso, senza importare l'app: una
migration deve girare anche quando il codice è cambiato. Il presidio
`test_catene_configurabili.py` le confronta con `catena_di_default`.

Una tabella assente è un no-op dichiarato. Rilanciata, non fa niente: si
riempiono solo le righe ancora a NULL.
"""

import json
import sqlite3

migration_name = "20261007_catene_degli_spareggi"

COLONNE = (
    ("gara", "catena_turno", "TEXT"),
    ("gara", "catena_gara", "TEXT"),
    ("campionato", "default_catena_turno", "TEXT"),
    ("campionato", "default_catena_gara", "TEXT"),
    ("campionato", "catena_generale", "TEXT"),
)

SPAREGGIO_DEFAULT = 3


def _a_triangoli(sistema):
    return (sistema or "").upper() in ("RACK", "RACKS")


def catena_di_turno(sistema):
    voci = ["posizione_precedente", "sorteggio"]
    return voci if _a_triangoli(sistema) else ["differenza_rack"] + voci


def catena_di_gara(sistema, spareggio_fino_al):
    voci = [] if _a_triangoli(sistema) else ["differenza_rack"]
    if spareggio_fino_al is not None:
        voci.append(f"ssr:{spareggio_fino_al}")
    return voci


def catena_generale(sistema):
    voci = ["ssr", "posizione_precedente", "sorteggio"]
    return voci if _a_triangoli(sistema) else ["differenza_rack"] + voci


def _colonne(cursor, tabella):
    return {riga[1] for riga in cursor.execute(f"PRAGMA table_info({tabella})")}


def _riempi_gare(cursor):
    presenti = _colonne(cursor, "gara")
    spareggio = "tiebreaker_enabled" in presenti
    posto = "tiebreaker_until_position" in presenti
    colonne = ["id", "classification_system"]
    colonne += ["tiebreaker_enabled"] if spareggio else []
    colonne += ["tiebreaker_until_position"] if posto else []
    righe = cursor.execute(
        f"SELECT {', '.join(colonne)}, catena_turno, catena_gara FROM gara"
    ).fetchall()
    turno = gara = 0
    for riga in righe:
        valori = dict(zip(colonne + ["catena_turno", "catena_gara"], riga))
        sistema = valori["classification_system"]
        if valori["catena_turno"] is None:
            cursor.execute(
                "UPDATE gara SET catena_turno = ? WHERE id = ?",
                (json.dumps(catena_di_turno(sistema)), valori["id"]),
            )
            turno += 1
        if valori["catena_gara"] is None:
            # Il default del modello era «acceso, fino al 3°».
            acceso = bool(valori.get("tiebreaker_enabled", 1))
            fino_al = valori.get("tiebreaker_until_position") or SPAREGGIO_DEFAULT
            cursor.execute(
                "UPDATE gara SET catena_gara = ? WHERE id = ?",
                (
                    json.dumps(catena_di_gara(sistema, fino_al if acceso else None)),
                    valori["id"],
                ),
            )
            gara += 1
    print(f"  ✓ {turno} gare: catena di turno · {gara} gare: catena di gara")


def _riempi_campionati(cursor):
    righe = cursor.execute(
        "SELECT id, default_classification_system, default_catena_turno, "
        "default_catena_gara, catena_generale FROM campionato"
    ).fetchall()
    toccati = 0
    for cid, sistema, turno, gara, generale in righe:
        nuovi = {}
        if turno is None:
            nuovi["default_catena_turno"] = json.dumps(catena_di_turno(sistema))
        if gara is None:
            nuovi["default_catena_gara"] = json.dumps(
                catena_di_gara(sistema, SPAREGGIO_DEFAULT)
            )
        if generale is None:
            nuovi["catena_generale"] = json.dumps(catena_generale(sistema))
        if not nuovi:
            continue
        assegnazioni = ", ".join(f"{c} = ?" for c in nuovi)
        cursor.execute(
            f"UPDATE campionato SET {assegnazioni} WHERE id = ?",
            (*nuovi.values(), cid),
        )
        toccati += 1
    print(f"  ✓ {toccati} campionati: catene di default")


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
        if {"catena_turno", "catena_gara"} <= _colonne(cursor, "gara"):
            _riempi_gare(cursor)
        if "catena_generale" in _colonne(cursor, "campionato"):
            _riempi_campionati(cursor)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    upgrade_sqlite()
