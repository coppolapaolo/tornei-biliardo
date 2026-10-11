"""La migration del sistema delle serate produce lo schema dell'ORM (ADR-080).

Stesso presidio di ``test_gironi_migration.py``: i test di comportamento
costruiscono lo schema con ``db.create_all()``, quindi una migration sbagliata
la vedrebbe solo la produzione. Qui si **esegue**, due volte, su un database
«di ieri»: la colonna nasce NULL (= vittorie) e nessun campionato cambia.
"""

from __future__ import annotations

import importlib
import sqlite3

MIGRATION = "migrations.20261011_sistema_delle_gare_a_piazzamenti"


def _esegui(percorso: str) -> None:
    importlib.import_module(MIGRATION).upgrade_sqlite(percorso)


def test_aggiunge_la_colonna_e_non_tocca_i_campionati(tmp_path):
    from models.campionato.models import Campionato

    percorso = str(tmp_path / "ieri.db")
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE campionato (
            id INTEGER PRIMARY KEY, name TEXT,
            default_classification_system VARCHAR(10)
        );
        INSERT INTO campionato VALUES (1, 'A tabellone', 'POSITION');
        INSERT INTO campionato VALUES (2, 'A vittorie', 'WINS');
        """)
    conn.commit()
    conn.close()

    _esegui(percorso)
    _esegui(percorso)  # idempotente

    conn = sqlite3.connect(percorso)
    colonne = {r[1] for r in conn.execute("PRAGMA table_info(campionato)")}
    assert "default_gara_classification_system" in colonne
    assert "default_gara_classification_system" in Campionato.__table__.columns
    righe = conn.execute(
        "SELECT default_classification_system, default_gara_classification_system "
        "FROM campionato ORDER BY id"
    ).fetchall()
    assert righe == [("POSITION", None), ("WINS", None)]
    conn.close()


def test_senza_tabella_non_solleva(tmp_path):
    percorso = str(tmp_path / "vuoto.db")
    sqlite3.connect(percorso).close()
    _esegui(percorso)
