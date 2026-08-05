"""Regression infra (review 2026-06-09): commit fallito NON deve essere
spacciato per successo.

Bug — models/transaction/manager.py:257/282: nei tre rami di commit del
context manager (nested / pseudo-nested / non-nested) un fallimento di
db.session.commit() (IntegrityError, "database is locked", …) veniva catturato
e loggato SOLO come warning, senza re-raise. Il chiamante riceveva il valore di
ritorno della funzione come se tutto fosse andato bene, mentre il DB aveva
annullato i dati → perdita dati silenziosa riportata come successo.

Fix: ogni ramo ri-solleva l'eccezione, che raggiunge l'except esterno (rollback
+ status ROLLED_BACK) e propaga al chiamante.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from models.base import db
from models.transaction.manager import transactional


@transactional()
def _op_that_returns_ok():
    # Operazione fittizia: il corpo va a buon fine, è il COMMIT a fallire.
    return "ok"


@pytest.mark.unit
def test_failed_commit_propagates_not_silent_success(db_session):
    boom = RuntimeError("commit boom (es. IntegrityError / database locked)")

    # Forza il fallimento del commit interno al context manager.
    with patch.object(db.session, "commit", side_effect=boom):
        with pytest.raises(RuntimeError, match="commit boom"):
            _op_that_returns_ok()


@pytest.mark.unit
def test_successful_commit_still_returns_value(db_session):
    # Sanity: senza fallimenti il decoratore continua a funzionare.
    assert _op_that_returns_ok() == "ok"
