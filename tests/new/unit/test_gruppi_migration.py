"""La migration dei gruppi produce lo schema che l'ORM si aspetta (D12).

Stesso presidio di ``test_scheda_allenamento_migration.py``: i test di
comportamento costruiscono lo schema con ``db.create_all()``, quindi una
migration sbagliata la vedrebbe solo la produzione. Qui si **esegue**, due
volte, e le colonne si confrontano una per una con quelle dei modelli.

L'indice unico **parziale** ha un test suo, ed è il cuore della faccenda: è lì
che vive «un allievo sta in un gruppo solo per volta», e deve essere il
database a dirlo — un `if` in Python è invisibile a chi scrive in blocco, come
`UserMergeService`, che legge lo schema per decidere.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from models.istruttore.models import TrainingGroup, TrainingGroupMember

MIGRATION = "migrations.20260920_gruppi_di_allievi"


def _colonne(conn: sqlite3.Connection, tabella: str) -> set[str]:
    return {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}


def _gruppo(conn: sqlite3.Connection, gruppo_id: int = 1) -> None:
    conn.execute(
        "INSERT INTO training_group (id, instructor_id, name, created_at, updated_at) "
        f"VALUES ({gruppo_id}, 1, 'Base 1', '2026-01-01', '2026-01-01')"
    )


def _iscrizione(gruppo_id: int, uscito: bool) -> str:
    fine = "'2026-06-01'" if uscito else "NULL"
    return (
        "INSERT INTO training_group_member "
        "(group_id, instructor_id, user_id, joined_at, left_at, "
        " created_at, updated_at) "
        f"VALUES ({gruppo_id}, 1, 2, '2026-01-01', {fine}, "
        "'2026-01-01', '2026-01-01')"
    )


@pytest.fixture
def db_di_ieri(tmp_path):
    """Un database senza gruppi: due utenti, e basta."""
    percorso = tmp_path / "ieri.db"
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY);
        INSERT INTO user VALUES (1);
        INSERT INTO user VALUES (2);
        """)
    conn.commit()
    conn.close()
    return str(percorso)


def test_lo_schema_coincide_con_i_modelli(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    for modello in (TrainingGroup, TrainingGroupMember):
        attese = {c.name for c in modello.__table__.columns}
        assert _colonne(conn, modello.__tablename__) == attese, modello.__tablename__
    conn.close()


def test_si_puo_rieseguire(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)


def test_in_due_gruppi_insieme_non_ci_sta(db_di_ieri):
    """Il vincolo è dello schema, e vale anche per un UPDATE scritto a mano."""
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    _gruppo(conn, 1)
    _gruppo(conn, 2)
    conn.execute(_iscrizione(1, uscito=False))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(_iscrizione(2, uscito=False))
    conn.close()


def test_dopo_essere_uscito_ci_rientra_altrove(db_di_ieri):
    """Per questo chiudere un corso data l'uscita: NULL non collide con NULL."""
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    _gruppo(conn, 1)
    _gruppo(conn, 2)
    conn.execute(_iscrizione(1, uscito=True))
    conn.execute(_iscrizione(2, uscito=False))  # non solleva
    conn.close()


def test_due_corsi_passati_possono_averlo_avuto_entrambi(db_di_ieri):
    importlib.import_module(MIGRATION).upgrade_sqlite(db_di_ieri)

    conn = sqlite3.connect(db_di_ieri)
    _gruppo(conn, 1)
    _gruppo(conn, 2)
    conn.execute(_iscrizione(1, uscito=True))
    conn.execute(_iscrizione(2, uscito=True))
    conn.close()
