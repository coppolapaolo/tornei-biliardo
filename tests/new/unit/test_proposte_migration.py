"""La migration delle proposte produce lo schema che l'ORM si aspetta (ADR-071).

Stesso presidio di ``test_gruppi_migration.py``: i test di comportamento
costruiscono lo schema con ``db.create_all()``, quindi una migration sbagliata
la vedrebbe solo la produzione. Qui si **esegue**, due volte, e le colonne si
confrontano una per una con quelle del modello.

L'indice unico **parziale** ha un test suo: è lì che vive «una proposta in
attesa per volta, per coppia», e deve essere il database a dirlo.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from models.istruttore.models import TrainingAssignment

MIGRATION = "migrations.20260920_proposte_di_scheda"

#: Le migration che **aggiungono colonne** a questa tabella dopo la prima. Il
#: confronto con il modello le vuole tutte: l'ORM legge lo schema di oggi, non
#: quello del giorno in cui la tabella è nata.
SUCCESSIVE = ("migrations.20260920_superato_il_livello",)


def _colonne(conn: sqlite3.Connection, tabella: str) -> set[str]:
    return {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}


def _proposta(istruttore: int, allievo: int, chiusa: bool) -> str:
    fine = "'2026-06-01'" if chiusa else "NULL"
    esito = "'declined'" if chiusa else "NULL"
    return (
        "INSERT INTO training_assignment "
        "(instructor_id, user_id, source_sheet_id, proposed_at, closed_at, "
        " outcome, created_at, updated_at) "
        f"VALUES ({istruttore}, {allievo}, 1, '2026-01-01', {fine}, {esito}, "
        "'2026-01-01', '2026-01-01')"
    )


@pytest.fixture
def db_di_ieri(tmp_path):
    """Un database senza proposte: tre utenti, un gruppo, una scheda."""
    percorso = tmp_path / "ieri.db"
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY);
        INSERT INTO user VALUES (1);
        INSERT INTO user VALUES (2);
        INSERT INTO user VALUES (3);
        CREATE TABLE training_sheet (id INTEGER PRIMARY KEY);
        INSERT INTO training_sheet VALUES (1);
        CREATE TABLE training_group (id INTEGER PRIMARY KEY);
        INSERT INTO training_group VALUES (1);
        """)
    conn.commit()
    conn.close()
    return str(percorso)


def _schema_di_oggi(percorso: str) -> None:
    importlib.import_module(MIGRATION).upgrade_sqlite(percorso)
    for nome in SUCCESSIVE:
        importlib.import_module(nome).upgrade_sqlite(percorso)


def test_lo_schema_coincide_col_modello(db_di_ieri):
    _schema_di_oggi(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    attese = {c.name for c in TrainingAssignment.__table__.columns}
    assert _colonne(conn, TrainingAssignment.__tablename__) == attese
    conn.close()


def test_si_puo_rieseguire(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)


def test_due_proposte_in_attesa_allo_stesso_allievo_non_ci_stanno(db_di_ieri):
    """Il vincolo è dello schema, e vale anche per un INSERT scritto a mano."""
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    conn.execute(_proposta(1, 2, chiusa=False))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(_proposta(1, 2, chiusa=False))
    conn.close()


def test_chiusa_quella_se_ne_puo_fare_un_altra(db_di_ieri):
    """NULL non collide con NULL: è il motivo per cui l'indice è parziale."""
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    conn.execute(_proposta(1, 2, chiusa=True))
    conn.execute(_proposta(1, 2, chiusa=True))
    conn.execute(_proposta(1, 2, chiusa=False))  # non solleva
    conn.close()


def test_due_istruttori_possono_proporre_insieme(db_di_ieri):
    """Il limite è per coppia: il mestiere di uno non chiude la porta all'altro."""
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    conn.execute(_proposta(1, 3, chiusa=False))
    conn.execute(_proposta(2, 3, chiusa=False))  # non solleva
    conn.close()
