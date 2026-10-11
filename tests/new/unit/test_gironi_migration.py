"""La migration dei gironi produce lo schema che l'ORM si aspetta (ADR-076).

Stesso presidio di ``test_proposte_migration.py``: i test di comportamento
costruiscono lo schema con ``db.create_all()``, quindi una migration sbagliata
la vedrebbe solo la produzione. Qui si **esegue**, due volte, su un database
«di ieri» con una gara e un campionato già esistenti.

Le gare esistenti devono restare a girone unico e sorteggio: lasciate a NULL
leggerebbero in diretta il tetto del campionato.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from models.matchmaking.gironi import ComposizioneGironi

MIGRATION = "migrations.20261011_gironi"


def _colonne(conn: sqlite3.Connection, tabella: str) -> set[str]:
    return {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}


@pytest.fixture
def db_di_ieri(tmp_path):
    percorso = tmp_path / "ieri.db"
    conn = sqlite3.connect(percorso)
    conn.executescript("""
        CREATE TABLE campionato (id INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO campionato VALUES (1, 'Lunedì al 74');
        CREATE TABLE gara (id INTEGER PRIMARY KEY, campionato_id INTEGER);
        INSERT INTO gara VALUES (1, 1);
        INSERT INTO gara VALUES (2, NULL);
        CREATE TABLE inscription (id INTEGER PRIMARY KEY, gara_id INTEGER);
        INSERT INTO inscription VALUES (1, 1);
        CREATE TABLE round_classification (id INTEGER PRIMARY KEY);
        CREATE TABLE gara_classification (id INTEGER PRIMARY KEY);
        """)
    conn.commit()
    conn.close()
    return str(percorso)


def _esegui(percorso: str) -> None:
    importlib.import_module(MIGRATION).upgrade_sqlite(percorso)


def test_aggiunge_le_colonne_del_modello(db_di_ieri):
    from models.campionato.models import Campionato
    from models.classification.models import GaraClassification, RoundClassification
    from models.competition.models import Gara, Inscription

    _esegui(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    attese = {
        Campionato: {"default_max_groups", "default_group_seeding"},
        Gara: {"max_groups", "group_seeding"},
        Inscription: {"group_index"},
        RoundClassification: {"group_index", "group_position"},
        GaraClassification: {"group_index", "group_position"},
    }
    for modello, colonne in attese.items():
        nel_modello = {c.name for c in modello.__table__.columns}
        assert colonne <= nel_modello, modello.__tablename__
        assert colonne <= _colonne(conn, modello.__tablename__)
    conn.close()


def test_le_gare_esistenti_restano_a_girone_unico(db_di_ieri):
    _esegui(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    assert conn.execute(
        "SELECT id, max_groups, group_seeding FROM gara"
    ).fetchall() == [
        (1, 1, ComposizioneGironi.SORTEGGIO.value),
        (2, 1, ComposizioneGironi.SORTEGGIO.value),
    ]
    assert conn.execute(
        "SELECT default_max_groups, default_group_seeding FROM campionato"
    ).fetchall() == [(1, ComposizioneGironi.SORTEGGIO.value)]
    assert conn.execute("SELECT group_index FROM inscription").fetchall() == [(None,)]
    conn.close()


def test_si_puo_rieseguire(db_di_ieri):
    _esegui(db_di_ieri)
    _esegui(db_di_ieri)
    conn = sqlite3.connect(db_di_ieri)
    assert conn.execute(
        "SELECT COUNT(*) FROM gara WHERE max_groups = 1"
    ).fetchone() == (2,)
    conn.close()


def test_una_tabella_assente_non_e_un_errore(tmp_path):
    """Sollevare la lascerebbe non applicata, e `auto_deploy` la ritenterebbe."""
    percorso = str(tmp_path / "vuoto.db")
    sqlite3.connect(percorso).close()
    _esegui(percorso)
