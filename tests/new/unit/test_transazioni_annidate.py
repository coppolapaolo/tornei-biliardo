"""Un `@transactional` dentro un altro deve restare dentro l'altro.

Fino al 2026-09-13 il ramo annidato del gestore chiudeva il savepoint con
`db.session.commit()` e lo annullava con `db.session.rollback()`. Da SQLAlchemy
1.4 quei due metodi agiscono sulla transazione **più esterna**, non sul
savepoint, quindi:

* se l'operazione esterna falliva dopo quella interna, restavano scritti il
  lavoro interno e quello esterno fatto prima: una gara scritta a metà;
* se falliva quella interna e l'esterna la catturava e proseguiva, si perdeva
  in silenzio il lavoro che l'esterna aveva fatto *prima*.

ADR-048, punto 4, lo aveva trovato e aggirato. Qui la verità è il database:
dopo ogni scenario si annulla la sessione e si rilegge la tabella, quindi
resta solo ciò che è stato davvero salvato.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from models.base import db
from models.transaction.manager import transactional

TABELLA = "prova_transazioni_annidate"


@pytest.fixture
def tabella(db_session):
    db.session.execute(text(f"CREATE TABLE IF NOT EXISTS {TABELLA} (v TEXT)"))
    db.session.execute(text(f"DELETE FROM {TABELLA}"))
    db.session.commit()
    yield
    db.session.rollback()
    db.session.execute(text(f"DROP TABLE IF EXISTS {TABELLA}"))
    db.session.commit()


def _scrivi(valore: str) -> None:
    db.session.execute(text(f"INSERT INTO {TABELLA} (v) VALUES (:v)"), {"v": valore})


def _salvati() -> list[str]:
    """Ciò che sta sul database: la sessione si annulla prima di leggere."""
    db.session.rollback()
    righe = db.session.execute(text(f"SELECT v FROM {TABELLA} ORDER BY rowid"))
    return [r[0] for r in righe]


class Guasto(RuntimeError):
    pass


@transactional()
def _interna(valore: str = "interna") -> None:
    _scrivi(valore)


@transactional()
def _interna_che_fallisce() -> None:
    _scrivi("interna-fallita")
    raise Guasto("guasto interno")


def test_senza_annidamento_salva(tabella):
    _interna("sola")
    assert _salvati() == ["sola"]


def test_senza_annidamento_un_guasto_non_salva(tabella):
    with pytest.raises(Guasto):
        _interna_che_fallisce()
    assert _salvati() == []


def test_l_esterna_che_fallisce_annulla_anche_l_interna(tabella):
    @transactional()
    def esterna():
        _scrivi("esterna-prima")
        _interna()
        _scrivi("esterna-dopo")
        raise Guasto("guasto dopo la chiamata interna")

    with pytest.raises(Guasto):
        esterna()
    assert _salvati() == []


def test_l_interna_che_fallisce_non_cancella_il_lavoro_dell_esterna(tabella):
    @transactional()
    def esterna():
        _scrivi("esterna-A")
        try:
            _interna_che_fallisce()
        except Guasto:
            pass
        _scrivi("esterna-B")

    esterna()
    assert _salvati() == ["esterna-A", "esterna-B"]


def test_l_esterna_che_riesce_salva_tutto(tabella):
    @transactional()
    def esterna():
        _scrivi("esterna-prima")
        _interna()
        _scrivi("esterna-dopo")

    esterna()
    assert _salvati() == ["esterna-prima", "interna", "esterna-dopo"]


def test_tre_livelli_il_guasto_in_mezzo_annulla_solo_il_suo_ramo(tabella):
    @transactional()
    def mezzo():
        _scrivi("mezzo")
        _interna("fondo")
        raise Guasto("guasto nel mezzo")

    @transactional()
    def cima():
        _scrivi("cima-prima")
        try:
            mezzo()
        except Guasto:
            pass
        _interna("fondo-dopo")
        _scrivi("cima-dopo")

    cima()
    assert _salvati() == ["cima-prima", "fondo-dopo", "cima-dopo"]


def test_tre_livelli_il_guasto_in_cima_annulla_tutto(tabella):
    @transactional()
    def mezzo():
        _scrivi("mezzo")
        _interna("fondo")

    @transactional()
    def cima():
        _scrivi("cima")
        mezzo()
        raise Guasto("guasto in cima")

    with pytest.raises(Guasto):
        cima()
    assert _salvati() == []


def test_l_esterna_che_ha_solo_letto_annulla_comunque_l_interna(tabella):
    """Nessuna scrittura dell'esterna prima della chiamata interna.

    Il driver `sqlite3` apre la transazione solo davanti a una scrittura, e un
    `SAVEPOINT` come primo comando renderebbe il suo `RELEASE` un commit. Qui
    non succede: il decoratore esterno apre subito il proprio savepoint. Il
    test resta perché è il caso in cui le due cause si confondono — prima del
    2026-09-13 era rosso per il `db.session.commit()` interno, non per il
    driver. Il caso del driver, fuori da un decoratore, sta in
    `test_savepoint_a_mano.py`.
    """

    @transactional()
    def esterna():
        db.session.execute(text(f"SELECT COUNT(*) FROM {TABELLA}")).scalar()
        _interna()
        raise Guasto("guasto dopo la chiamata interna")

    with pytest.raises(Guasto):
        esterna()
    assert _salvati() == []


def test_sessione_gia_aperta_il_decoratore_salva_davvero(tabella):
    """Il ramo «pseudo-nested»: la sessione ha già letto qualcosa.

    Il decoratore più esterno per il gestore trova una transazione aperta dalla
    sessione stessa, non da un altro decoratore: deve comunque salvare.
    """
    db.session.execute(text(f"SELECT COUNT(*) FROM {TABELLA}")).scalar()
    assert db.session.is_active

    _interna("con-sessione-aperta")
    assert _salvati() == ["con-sessione-aperta"]


def test_sessione_gia_aperta_un_guasto_non_salva(tabella):
    db.session.execute(text(f"SELECT COUNT(*) FROM {TABELLA}")).scalar()

    with pytest.raises(Guasto):
        _interna_che_fallisce()
    assert _salvati() == []
