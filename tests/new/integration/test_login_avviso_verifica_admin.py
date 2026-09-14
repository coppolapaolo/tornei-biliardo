"""L'avviso «account non verificato» al login non riguarda l'admin.

L'avviso dice che senza email confermata non si recupera la password, e manda
al profilo per verificarla. Per l'admin sono false entrambe: la sua password
arriva dalla variabile d'ambiente, non dal recupero via email, e il suo profilo
non è modificabile. L'admin nato dal bootstrap ha un'email finta
(`admin@campionato.local`) e `is_verified` falso, quindi lo vedeva a ogni login.

Il flash si legge dalla sessione, prima del redirect: contare testo nell'HTML
della pagina di arrivo conterebbe anche il pannello di debug.
"""

from models.user.models import User
from models.user.role_enum import UserRole

AVVISO = "non è ancora verificato"
PASSWORD = "p@ss123"


def _crea_utente(db_session, username: str, role: str) -> User:
    utente = User(username=username, email=f"{username}@test.local", role=role)
    utente.set_password(PASSWORD)
    utente.is_verified = False
    db_session.add(utente)
    db_session.commit()
    return utente


def _messaggi_dopo_il_login(client, username: str) -> list:
    resp = client.post("/auth/login", data={"username": username, "password": PASSWORD})
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        return [str(messaggio) for _categoria, messaggio in sess.get("_flashes", [])]


def test_admin_non_verificato_non_riceve_l_avviso(client, db_session):
    _crea_utente(db_session, "amministratore_avviso", UserRole.ADMIN.value)

    messaggi = _messaggi_dopo_il_login(client, "amministratore_avviso")

    assert not any(AVVISO in m for m in messaggi), messaggi


def test_giocatore_non_verificato_riceve_ancora_l_avviso(client, db_session):
    _crea_utente(db_session, "giocatore_avviso", UserRole.PLAYER.value)

    messaggi = _messaggi_dopo_il_login(client, "giocatore_avviso")

    assert any(AVVISO in m for m in messaggi), messaggi
