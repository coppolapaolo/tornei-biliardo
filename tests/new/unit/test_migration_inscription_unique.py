"""La migration delle iscrizioni doppie dice la stessa cosa del codice.

`migrations/20260901_inscription_unique_gara_user.py` riscrive in SQL la regola
di fusione che in `models/competition/inscription_dedup.py` sta in Python: una
migration deve saper girare da sola, senza importare modelli che nel frattempo
cambiano forma. Il prezzo è che le due possano divergere — e una divergenza
qui non dà errore, dà un'iscrizione con la categoria sbagliata.

Questi test non leggono le due implementazioni per confrontarle a occhio:
**eseguono** la migration su un database temporaneo e confrontano il risultato
con quello che `piano_di_fusione` avrebbe deciso.
"""

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from models.competition.inscription_dedup import (
    CAMPI_DATO,
    CAMPI_STATO,
    piano_di_fusione,
)
from models.competition.models import Inscription

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "migrations"
    / "20260901_inscription_unique_gara_user.py"
)

#: Lo schema del test è scritto a mano perché il modello vero ormai porta il
#: vincolo, e con quello addosso i doppioni non si riescono nemmeno a inserire.
#: `test_lo_schema_del_test_esiste_davvero` lo tiene ancorato al modello.
SCHEMA = """
CREATE TABLE inscription (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    gara_id INTEGER NOT NULL,
    created_at DATETIME,
    initial_order INTEGER,
    is_withdrawn BOOLEAN DEFAULT 0,
    withdrawn_at DATETIME,
    is_forfeit BOOLEAN DEFAULT 0,
    forfeit_at DATETIME,
    is_waitlist BOOLEAN DEFAULT 0,
    waitlist_position INTEGER,
    waitlist_reason VARCHAR(20),
    squadra_id INTEGER,
    categoria_id INTEGER
);
CREATE TABLE hidden_inscription (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    inscription_id INTEGER NOT NULL,
    hidden_at DATETIME
);
"""


def _carica_migration():
    spec = importlib.util.spec_from_file_location(MIGRATION.stem, MIGRATION)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


def _db(tmp_path, righe):
    """Crea un database con le ``righe`` date e ne restituisce il percorso."""
    percorso = tmp_path / "test.db"
    conn = sqlite3.connect(percorso)
    conn.executescript(SCHEMA)
    for riga in righe:
        colonne = ", ".join(riga)
        segnaposto = ", ".join("?" for _ in riga)
        conn.execute(
            f"INSERT INTO inscription ({colonne}) VALUES ({segnaposto})",
            tuple(riga.values()),
        )
    conn.commit()
    conn.close()
    return str(percorso)


def _iscrizioni(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    righe = [dict(r) for r in conn.execute("SELECT * FROM inscription")]
    conn.close()
    return righe


def test_lo_schema_del_test_esiste_davvero():
    """Le colonne su cui gira la migration sono quelle del modello.

    Senza questo controllo il test resterebbe verde su uno schema inventato: la
    migration passerebbe qui e in produzione lavorerebbe su altre colonne.
    """
    reali = {c.name for c in Inscription.__table__.columns}
    usate = set(CAMPI_STATO) | set(CAMPI_DATO) | {"id", "user_id", "gara_id"}
    assert usate <= reali, f"colonne che il modello non ha: {usate - reali}"

    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    finte = {r[1] for r in conn.execute("PRAGMA table_info(inscription)")}
    conn.close()
    assert reali == finte, (
        "lo schema di questo test non è più quello di Inscription: "
        f"mancano {reali - finte}, in più {finte - reali}"
    )


@pytest.mark.parametrize(
    "righe",
    [
        # Il caso di produzione: la vecchia ha la categoria, la nuova no.
        [
            {
                "id": 1,
                "user_id": 7,
                "gara_id": 39,
                "created_at": "2026-08-01 10:00:00",
                "categoria_id": 3,
                "initial_order": 5,
            },
            {
                "id": 2,
                "user_id": 7,
                "gara_id": 39,
                "created_at": "2026-08-20 10:00:00",
            },
        ],
        # La più vecchia è in lista d'attesa, la nuova è attiva: vince attivo.
        [
            {
                "id": 1,
                "user_id": 7,
                "gara_id": 39,
                "created_at": "2026-08-01 10:00:00",
                "is_waitlist": 1,
                "waitlist_position": 2,
                "waitlist_reason": "capacity",
            },
            {
                "id": 2,
                "user_id": 7,
                "gara_id": 39,
                "created_at": "2026-08-20 10:00:00",
                "categoria_id": 4,
            },
        ],
        # La più recente è ritirata: lo stato della più vecchia (attiva) resta.
        [
            {
                "id": 1,
                "user_id": 7,
                "gara_id": 39,
                "created_at": "2026-08-01 10:00:00",
            },
            {
                "id": 2,
                "user_id": 7,
                "gara_id": 39,
                "created_at": "2026-08-20 10:00:00",
                "is_withdrawn": 1,
                "withdrawn_at": "2026-08-21 10:00:00",
                "squadra_id": 9,
            },
        ],
        # Tre righe, e una senza `created_at` (dati antichi): va in coda.
        [
            {"id": 1, "user_id": 7, "gara_id": 39, "categoria_id": 2},
            {
                "id": 2,
                "user_id": 7,
                "gara_id": 39,
                "created_at": "2026-08-01 10:00:00",
            },
            {
                "id": 3,
                "user_id": 7,
                "gara_id": 39,
                "created_at": "2026-08-20 10:00:00",
                "initial_order": 4,
            },
        ],
    ],
)
def test_la_migration_fonde_come_il_codice(tmp_path, righe):
    """L'esito della migration coincide con quello di `piano_di_fusione`."""
    db_path = _db(tmp_path, righe)
    prima = _iscrizioni(db_path)
    piano = piano_di_fusione(prima)
    assert piano is not None

    _carica_migration().upgrade_sqlite(db_path)

    dopo = _iscrizioni(db_path)
    assert len(dopo) == 1, "la migration deve lasciare una sola iscrizione"
    sopravvissuta = dopo[0]
    assert sopravvissuta["id"] == piano.sopravvissuta_id

    atteso = dict(next(r for r in prima if r["id"] == piano.sopravvissuta_id))
    atteso.update(piano.valori)
    for campo in CAMPI_STATO + CAMPI_DATO:
        # I booleani tornano da SQLite come 0/1: si confrontano per verità.
        if campo.startswith("is_"):
            assert bool(sopravvissuta[campo]) == bool(atteso[campo]), campo
        else:
            assert sopravvissuta[campo] == atteso[campo], campo


def test_la_migration_crea_l_indice_unico(tmp_path):
    """Riparato il passato, il database rifiuta il futuro."""
    db_path = _db(
        tmp_path,
        [{"id": 1, "user_id": 7, "gara_id": 39, "created_at": "2026-08-01 10:00:00"}],
    )
    _carica_migration().upgrade_sqlite(db_path)

    conn = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO inscription (user_id, gara_id) VALUES (7, 39)")
    finally:
        conn.close()


def test_la_migration_e_idempotente(tmp_path):
    """Rigirarla non cambia niente: il runner può ripassarci sopra."""
    db_path = _db(
        tmp_path,
        [
            {
                "id": 1,
                "user_id": 7,
                "gara_id": 39,
                "created_at": "2026-08-01 10:00:00",
                "categoria_id": 3,
            },
            {
                "id": 2,
                "user_id": 7,
                "gara_id": 39,
                "created_at": "2026-08-20 10:00:00",
            },
        ],
    )
    migration = _carica_migration()
    migration.upgrade_sqlite(db_path)
    primo_giro = _iscrizioni(db_path)
    migration.upgrade_sqlite(db_path)
    assert _iscrizioni(db_path) == primo_giro


def test_le_righe_nascoste_seguono_la_sopravvissuta(tmp_path):
    """`hidden_inscription` punta all'id: senza ripuntarlo, il CASCADE lo perde."""
    db_path = _db(
        tmp_path,
        [
            {
                "id": 1,
                "user_id": 7,
                "gara_id": 39,
                "created_at": "2026-08-01 10:00:00",
            },
            {
                "id": 2,
                "user_id": 7,
                "gara_id": 39,
                "created_at": "2026-08-20 10:00:00",
            },
        ],
    )
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO hidden_inscription (user_id, inscription_id) VALUES (7, 2)"
    )
    conn.commit()
    conn.close()

    _carica_migration().upgrade_sqlite(db_path)

    conn = sqlite3.connect(db_path)
    nascoste = conn.execute("SELECT inscription_id FROM hidden_inscription").fetchall()
    conn.close()
    assert nascoste == [(1,)], "la riga nascosta deve seguire la sopravvissuta"
