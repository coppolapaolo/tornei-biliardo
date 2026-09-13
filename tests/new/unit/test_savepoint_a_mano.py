"""I savepoint scritti a mano passano da `savepoint()` del gestore.

Lo schema di ADR-025 apre un savepoint per far emergere al flush un
`IntegrityError` e tradurlo. Con `with db.session.begin_nested():` nudo, su
SQLite c'era un difetto: il driver `sqlite3` apre la transazione solo davanti
a una scrittura, quindi se prima c'erano state soltanto letture il `SAVEPOINT`
era il primo comando della transazione e il suo `RELEASE` valeva un commit. Il
chiamante che poi falliva non trovava più niente da annullare (ADR-061).

Come in `test_transazioni_annidate.py`, la verità è il database: si annulla la
sessione e si rilegge.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import models.transaction.manager as gestore
from models.base import db
from models.kpi.models import KpiDailySnapshot
from models.transaction.manager import savepoint, transactional

TABELLA = "prova_savepoint_a_mano"
RADICE = Path(__file__).resolve().parents[3]


@pytest.fixture
def tabella(db_session):
    db.session.execute(text(f"CREATE TABLE IF NOT EXISTS {TABELLA} (v TEXT UNIQUE)"))
    db.session.execute(text(f"DELETE FROM {TABELLA}"))
    db.session.commit()
    yield
    db.session.rollback()
    db.session.execute(text(f"DROP TABLE IF EXISTS {TABELLA}"))
    db.session.commit()


def _scrivi(valore: str) -> None:
    db.session.execute(text(f"INSERT INTO {TABELLA} (v) VALUES (:v)"), {"v": valore})


def _salvati() -> list[str]:
    db.session.rollback()
    righe = db.session.execute(text(f"SELECT v FROM {TABELLA} ORDER BY rowid"))
    return [r[0] for r in righe]


class Guasto(RuntimeError):
    pass


def test_premessa_il_begin_nested_nudo_dopo_letture_salva_da_solo(tabella):
    """Il motivo per cui esiste `savepoint()`.

    Fuori da un `@transactional` — una route, un servizio non decorato — la
    sessione ha solo letto, e il `SAVEPOINT` è il primo comando della
    transazione per SQLite. Dentro un `@transactional` il difetto non si vede:
    il decoratore più esterno apre subito il proprio savepoint, e quello
    interno non è più il primo.

    Se questo test diventa rosso, il driver ha smesso di comportarsi così — per
    esempio con una configurazione del motore diversa — e l'apertura esplicita
    della transazione in `_apri_transazione_sqlite` va rivalutata.
    """
    db.session.execute(text(f"SELECT COUNT(*) FROM {TABELLA}")).scalar()
    with db.session.begin_nested():
        _scrivi("salvato-per-sbaglio")
    db.session.rollback()

    assert _salvati() == ["salvato-per-sbaglio"]


def test_dopo_sole_letture_si_annulla_con_la_sessione(tabella):
    db.session.execute(text(f"SELECT COUNT(*) FROM {TABELLA}")).scalar()
    with savepoint():
        _scrivi("interna")
    db.session.rollback()

    assert _salvati() == []


def test_dopo_sole_letture_si_annulla_con_il_chiamante_decorato(tabella):
    @transactional()
    def esterna():
        db.session.execute(text(f"SELECT COUNT(*) FROM {TABELLA}")).scalar()
        with savepoint():
            _scrivi("interna")
        raise Guasto("guasto dopo il savepoint")

    with pytest.raises(Guasto):
        esterna()
    assert _salvati() == []


def test_il_conflitto_catturato_non_tocca_il_lavoro_del_chiamante(tabella):
    """Lo schema di ADR-025 per intero: il conflitto si traduce, il resto resta."""

    @transactional()
    def esterna():
        _scrivi("prima")
        try:
            with savepoint():
                _scrivi("prima")  # UNIQUE: il conflitto emerge qui
        except IntegrityError:
            pass
        _scrivi("dopo")

    esterna()
    assert _salvati() == ["prima", "dopo"]


def test_riuscito_salva_con_il_chiamante(tabella):
    @transactional()
    def esterna():
        db.session.execute(text(f"SELECT COUNT(*) FROM {TABELLA}")).scalar()
        with savepoint():
            _scrivi("interna")
        _scrivi("esterna")

    esterna()
    assert _salvati() == ["interna", "esterna"]


def _get_or_create_poi_annullato(giorno: date) -> None:
    """Un chiamante non decorato che crea e poi rinuncia."""
    db.session.commit()
    KpiDailySnapshot.get_or_create(giorno)  # legge, poi crea nel savepoint
    db.session.rollback()


def test_un_uso_vero_get_or_create_si_annulla_con_il_chiamante(db_session):
    giorno = date(2026, 9, 13)
    _get_or_create_poi_annullato(giorno)

    assert KpiDailySnapshot.query.filter_by(date=giorno).count() == 0


def test_un_uso_vero_senza_l_apertura_salverebbe(db_session, monkeypatch):
    """Lo stesso uso con il `savepoint()` di prima: prova che il test sopra morde."""

    @contextmanager
    def nudo():
        with db.session.begin_nested() as transazione:
            yield transazione

    monkeypatch.setattr(gestore, "savepoint", nudo)
    giorno = date(2026, 9, 14)
    _get_or_create_poi_annullato(giorno)

    assert KpiDailySnapshot.query.filter_by(date=giorno).count() == 1


def test_nessun_begin_nested_scritto_a_mano_fuori_dal_gestore():
    """Presidio: un `begin_nested()` nudo rimette il difetto, in silenzio."""
    ammesso = RADICE / "models" / "transaction" / "manager.py"
    trovati = []
    for cartella in ("models", "routes", "utils", "scripts"):
        for percorso in (RADICE / cartella).rglob("*.py"):
            if percorso == ammesso:
                continue
            for numero, riga in enumerate(percorso.read_text().splitlines(), 1):
                if "begin_nested(" in riga:
                    trovati.append(f"{percorso.relative_to(RADICE)}:{numero}")
    assert trovati == [], (
        "Usa `savepoint()` da models.transaction.manager al posto di "
        f"`db.session.begin_nested()`: {trovati}"
    )
