"""L'hash della password deve stare nella colonna che lo contiene.

Werkzeug 3.1 ha cambiato il default di `generate_password_hash` da
`pbkdf2:sha256:600000` (102 caratteri) a `scrypt:32768:8:1` (162). La colonna
`user.password_hash` è `String(120)`, e SQLite non fa rispettare la lunghezza:
nessun errore, solo uno schema che dichiara il falso. Allargarla vorrebbe dire
ricostruire la tabella `user`, a cui puntano più di cento chiavi esterne.
Per questo `set_password` fissa l'algoritmo — pbkdf2 — ma non il costo, che
segue Werkzeug.

Il conftest sostituisce `generate_password_hash` con una variante a una sola
iterazione, che ignora il `method` passato: qui si rimette la funzione vera,
altrimenti il test passerebbe anche senza la correzione.
"""

from unittest.mock import patch

from werkzeug.security import generate_password_hash

import models.user.models as user_models
from models.user.models import User


def _hash_di_produzione(password: str) -> str:
    utente = User(username="hash_prova", email="hash_prova@example.com")
    with patch.object(user_models, "generate_password_hash", generate_password_hash):
        utente.set_password(password)
    assert utente.check_password(password)
    return utente.password_hash


def test_l_hash_sta_nella_colonna():
    lunghezza = User.__table__.c.password_hash.type.length
    assert len(_hash_di_produzione("una password lunga e sicura")) <= lunghezza


def test_l_algoritmo_e_pbkdf2_col_costo_di_werkzeug():
    metodo = _hash_di_produzione("prova123").split("$", 1)[0]
    algoritmo, _, iterazioni = metodo.rpartition(":")
    assert algoritmo == "pbkdf2:sha256"
    # Il costo non è fissato: resta quello, crescente, di Werkzeug.
    assert int(iterazioni) >= 600_000
