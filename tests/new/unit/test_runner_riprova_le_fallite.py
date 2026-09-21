"""Due migration in ordine sbagliato devono passare nello stesso giro.

Le migration si eseguono in ordine **alfabetico** (`get_migration_files`), che
non ha niente a che vedere con l'ordine in cui le tabelle nascono. Finché le
date bastano a separarle non si vede, ma dieci migration con la stessa data si
ordinano per l'iniziale della descrizione: il 2026-09-20 in produzione
`20260920_estrazione_e_consegna` ha chiesto una colonna a `challenge_shot`
sei file prima che `20260920_prova_fatta_di_colpi` la creasse, e
`20260920_note_condivise` una a `training_sheet` quattro file prima di
`20260920_scheda_di_allenamento`. Due «no such table», due migration non
marcate, e le pagine delle schede di allenamento in 500: non per una notte, ma
finché qualcuno non se ne fosse accorto, perché senza codice nuovo da portare
lo scheduled task usciva prima di guardare le migration pendenti (l'altra metà
del guasto, in `test_auto_deploy_migration_pendenti.py`).

Il guard di idempotenza non poteva accorgersene: `PRAGMA table_info` su una
tabella che non esiste non solleva, restituisce zero righe, e «la colonna non
c'è» è indistinguibile da «la tabella non c'è».

Qui non si difende l'ordine dei nomi, che nessuno ricorderà: si verifica che il
runner **riprovi** le fallite finché una passata ne salva almeno una. Il
secondo test è quello che tiene in piedi il primo: senza un punto di arresto,
una migration rotta sul serio terrebbe il ciclo — e la web app disabilitata —
per sempre.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from migrations import runner

# Una migration finta: `nome` la identifica, `corpo` è ciò che esegue.
MODELLO = """
import sqlite3

migration_name = "{nome}"


def upgrade_sqlite(db_path="instance/billiard_campionato.db"):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute({sql!r})
        conn.commit()
    finally:
        conn.close()
"""


@pytest.fixture
def finto_ambiente(tmp_path, monkeypatch):
    """Un DB vuoto e una cartella di migration, al posto di quelli veri."""
    db = tmp_path / "prova.db"
    sqlite3.connect(db).close()

    cartella = tmp_path / "migrations"
    cartella.mkdir()

    monkeypatch.setattr(runner, "get_db_path", lambda: str(db))
    monkeypatch.setattr(
        runner, "get_migration_files", lambda: sorted(cartella.glob("*.py"))
    )
    return db, cartella


def _migration(cartella: Path, nome: str, sql: str) -> None:
    (cartella / f"{nome}.py").write_text(MODELLO.format(nome=nome, sql=sql))


def _applicate(db: Path) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return runner.get_applied_migrations(conn)
    finally:
        conn.close()


def _colonne(db: Path, tabella: str) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {riga[1] for riga in conn.execute(f"PRAGMA table_info({tabella})")}
    finally:
        conn.close()


def test_la_colonna_arriva_anche_se_la_tabella_nasce_dopo(finto_ambiente):
    """`a_` aggiunge una colonna alla tabella che `b_` crea: l'ordine è inverso.

    È la forma esatta dell'incidente del 2026-09-20. Alla prima passata `a_`
    fallisce; `b_` crea la tabella; la seconda passata salva `a_`.
    """
    db, cartella = finto_ambiente
    _migration(
        cartella, "29990101_a_colonna", "ALTER TABLE tavolo ADD COLUMN panno TEXT"
    )
    _migration(cartella, "29990101_b_tabella", "CREATE TABLE tavolo (id INTEGER)")

    assert runner.run_pending_migrations() == 2

    assert _applicate(db) == {"29990101_a_colonna.py", "29990101_b_tabella.py"}
    assert "panno" in _colonne(db, "tavolo")


def test_una_migration_rotta_non_manda_il_runner_in_circolo(finto_ambiente):
    """Quando una passata non salva più nessuno, si esce.

    `rotta` non aspetta nessuna tabella: è sbagliata e lo sarà sempre. Il
    runner la lascia non applicata — così il giro successivo la ritenta e chi
    legge il log la vede — senza riprovarla all'infinito.
    """
    db, cartella = finto_ambiente
    _migration(cartella, "29990101_buona", "CREATE TABLE tavolo (id INTEGER)")
    _migration(cartella, "29990101_rotta", "QUESTA NON E' SQL")

    assert runner.run_pending_migrations() == 1

    assert _applicate(db) == {"29990101_buona.py"}


def test_senza_dipendenze_resta_una_passata_sola(finto_ambiente, capsys):
    """Il caso normale non deve pagare niente: nessuna riga di ritentativo."""
    db, cartella = finto_ambiente
    _migration(cartella, "29990101_una", "CREATE TABLE tavolo (id INTEGER)")
    _migration(cartella, "29990102_due", "CREATE TABLE stecca (id INTEGER)")

    assert runner.run_pending_migrations() == 2
    assert "Passata 2" not in capsys.readouterr().out
