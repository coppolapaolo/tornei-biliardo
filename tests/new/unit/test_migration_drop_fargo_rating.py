"""Test della migration 20260816_drop_fargo_rating.

Questa migration ha fallito ogni notte in produzione per un motivo che in
locale non si vede: `ALTER TABLE ... DROP COLUMN` esiste solo da SQLite 3.35,
PythonAnywhere sta alla 3.31.1, e la prima stesura in quel caso sollevava. Il
runner registrava allora "Completed: 0/1", **non** marcava la migration come
applicata, e `auto_deploy.py` la ritentava il giorno dopo — disabilitando e
riabilitando la web app a ogni giro.

La versione di SQLite non è configurabile: è compilata nella libreria a cui
l'interprete è linkato (qui una 3.5x, dove la DROP COLUMN funziona). Il ramo
che in produzione si prende sempre, in locale non si prende mai. I test lo
raggiungono quindi sostituendo `sqlite3.sqlite_version_info`, che è il valore
su cui la migration decide.

Cosa questi test dimostrano e cosa no:

* dimostrano che **sotto soglia la migration riesce** invece di sollevare, e
  che le cancellazioni dei passi 1 e 2 arrivano su disco lo stesso (la prima
  stesura chiudeva la connessione senza commit prima di sollevare: anche il
  lavoro riuscito veniva buttato via);
* **non** dimostrano che SQLite 3.31 rifiuti davvero quell'ALTER TABLE. Quello
  è un fatto a monte — la DROP COLUMN è del marzo 2021 — più il traceback
  notturno che l'ha reso visibile.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3] / "migrations" / "20260816_drop_fargo_rating.py"
)

#: Quella di PythonAnywhere: sotto la soglia della DROP COLUMN.
SQLITE_PYTHONANYWHERE = (3, 31, 1)


def _load_migration():
    spec = importlib.util.spec_from_file_location("drop_fargo_rating", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def migration():
    return _load_migration()


@pytest.fixture
def db_path(tmp_path) -> str:
    """Un DB con la colonna Fargo e due righe Fargo da ripulire.

    Le tabelle sono ridotte all'osso: alla migration servono solo la colonna
    da togliere e le due colonne `rating_system` su cui filtra.
    """
    path = tmp_path / "fargo.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE user (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL,
            fargo_rating INTEGER
        );
        CREATE TABLE player_rating (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            rating_system TEXT NOT NULL
        );
        CREATE TABLE rating_handicap_rule (
            id INTEGER PRIMARY KEY,
            rating_system TEXT NOT NULL
        );

        INSERT INTO user (username, fargo_rating) VALUES ('ada', NULL);
        INSERT INTO player_rating (user_id, rating_system)
            VALUES (1, 'fargo'), (1, 'elo');
        INSERT INTO rating_handicap_rule (rating_system)
            VALUES ('fargo'), ('elo');
        """)
    conn.commit()
    conn.close()
    return str(path)


def _fresh(db_path: str) -> sqlite3.Connection:
    """Una connessione nuova: legge solo ciò che è arrivato davvero su disco."""
    return sqlite3.connect(db_path)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _count(conn: sqlite3.Connection, table: str, system: str) -> int:
    return conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE rating_system = ?", (system,)
    ).fetchone()[0]


@pytest.fixture
def sqlite_vecchia(monkeypatch):
    """Fa credere alla migration di girare sulla SQLite di PythonAnywhere."""
    monkeypatch.setattr(sqlite3, "sqlite_version_info", SQLITE_PYTHONANYWHERE)
    monkeypatch.setattr(
        sqlite3, "sqlite_version", ".".join(str(n) for n in SQLITE_PYTHONANYWHERE)
    )


# ══ Sotto soglia: il caso della produzione ═══════════════════════════════════


def test_su_sqlite_vecchia_non_solleva(migration, db_path, sqlite_vecchia):
    """Il punto di tutta la correzione: niente eccezione, quindi il runner
    marca la migration come applicata e il ciclo notturno finisce."""
    migration.upgrade_sqlite(db_path)  # non deve sollevare


def test_su_sqlite_vecchia_la_colonna_resta(migration, db_path, sqlite_vecchia):
    """Il no-op è dichiarato, non simulato: la colonna è ancora lì.

    È l'esito accettato per iscritto (vuota, nullable, nessun codice la
    nomina). Un test che pretendesse la colonna sparita starebbe chiedendo al
    motore una cosa che non sa fare.
    """
    migration.upgrade_sqlite(db_path)

    with _fresh(db_path) as conn:
        assert _has_column(conn, "user", "fargo_rating")


def test_su_sqlite_vecchia_la_pulizia_dei_dati_e_persistita(
    migration, db_path, sqlite_vecchia
):
    """La regressione vera: prima il `raise` arrivava *dopo* le DELETE e
    *prima* del commit, quindi ogni notte si rifaceva un lavoro che veniva
    ogni volta buttato via. Si rilegge da una connessione nuova apposta: sulla
    stessa, le DELETE non committate si vedrebbero lo stesso.
    """
    migration.upgrade_sqlite(db_path)

    with _fresh(db_path) as conn:
        assert _count(conn, "rating_handicap_rule", "fargo") == 0
        assert _count(conn, "player_rating", "fargo") == 0
        # Gli altri sistemi di rating non vengono sfiorati.
        assert _count(conn, "rating_handicap_rule", "elo") == 1
        assert _count(conn, "player_rating", "elo") == 1


def test_su_sqlite_vecchia_e_ripetibile(migration, db_path, sqlite_vecchia):
    """Finché non viene marcata applicata la migration rigira: due passate di
    fila devono restare innocue."""
    migration.upgrade_sqlite(db_path)
    migration.upgrade_sqlite(db_path)

    with _fresh(db_path) as conn:
        assert _count(conn, "player_rating", "fargo") == 0
        assert _has_column(conn, "user", "fargo_rating")


# ══ Sopra soglia: la strada che si percorre in locale ════════════════════════


def test_su_sqlite_recente_la_colonna_sparisce(migration, db_path):
    """Dove il motore lo consente la migration fa ancora il suo mestiere.

    Salta se la SQLite di chi esegue i test è anch'essa sotto soglia: qui non
    si sta verificando il ramo, si sta verificando il motore.
    """
    if sqlite3.sqlite_version_info < migration.DROP_COLUMN_MIN_VERSION:
        pytest.skip(f"SQLite locale {sqlite3.sqlite_version} senza DROP COLUMN")

    migration.upgrade_sqlite(db_path)

    with _fresh(db_path) as conn:
        assert not _has_column(conn, "user", "fargo_rating")
        assert _count(conn, "player_rating", "fargo") == 0


def test_e_ripetibile_anche_a_colonna_gia_tolta(migration, db_path):
    if sqlite3.sqlite_version_info < migration.DROP_COLUMN_MIN_VERSION:
        pytest.skip(f"SQLite locale {sqlite3.sqlite_version} senza DROP COLUMN")

    migration.upgrade_sqlite(db_path)
    migration.upgrade_sqlite(db_path)  # non deve sollevare


# ══ Robustezza ═══════════════════════════════════════════════════════════════


def test_tabelle_di_rating_assenti_non_sono_un_errore(migration, tmp_path):
    """Un DB che non ha mai avuto il sistema di rating: la migration passa."""
    path = tmp_path / "minimo.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE user (id INTEGER PRIMARY KEY, username TEXT)")
    conn.commit()
    conn.close()

    migration.upgrade_sqlite(str(path))  # non deve sollevare
