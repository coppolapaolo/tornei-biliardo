"""Un rollback per un rifiuto di dominio non è un allarme nel log.

Ogni `@transactional` che annulla scriveva un WARNING, qualunque fosse la
causa. Ma un `DomainError` — un dato non valido, un permesso che manca, una
partita già chiusa — è il sistema che funziona: l'utente ha chiesto una cosa
che non si può fare e gli è stato detto. In produzione l'error log tiene da
WARNING in su, quindi quei rifiuti lo riempivano e i guasti veri ci si
perdevano in mezzo (#257, punto 4).

Dal 2026-11-10: `DomainError` → INFO; ogni altra eccezione → WARNING con il
traceback, perché quella è un guasto e va trovata.
"""

import logging

import pytest

from models.exceptions import ValidationError
from models.transaction.manager import transactional

pytestmark = pytest.mark.unit

MODULO = "models.transaction.manager"


@transactional(domain="test")
def _rifiuta():
    raise ValidationError("dato non valido")


@transactional(domain="test")
def _si_rompe():
    raise RuntimeError("guasto vero")


def _righe(caplog):
    return [r for r in caplog.records if r.name == MODULO and "rolled back" in r.msg]


def test_il_rifiuto_di_dominio_si_scrive_a_info(db_session, caplog):
    with caplog.at_level(logging.DEBUG, logger=MODULO):
        with pytest.raises(ValidationError):
            _rifiuta()

    righe = _righe(caplog)
    assert righe, "il rollback deve restare tracciato, a un livello più basso"
    assert all(r.levelno == logging.INFO for r in righe)
    assert all(not r.exc_info for r in righe)


def test_il_guasto_resta_un_warning_e_porta_il_traceback(db_session, caplog):
    with caplog.at_level(logging.DEBUG, logger=MODULO):
        with pytest.raises(RuntimeError):
            _si_rompe()

    righe = _righe(caplog)
    assert righe
    assert all(r.levelno == logging.WARNING for r in righe)
    assert all(r.exc_info for r in righe)
