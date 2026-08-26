"""Il recupero password, dal «ho dimenticato» fino al login con la nuova.

Questo flusso non aveva **un solo test**: funzionava, ma niente lo difendeva —
e le quattro correzioni del 2026-08-26 (sessioni invalidate, invio dopo il
commit, esito dell'invio riferito, link precedenti disattivati) sono tutte in
punti che un test di comportamento normale non attraversa.

I casi qui sotto sono gli stessi che percorrerebbe una persona vera, piu' i
quattro guasti che erano rimasti scoperti.
"""

from datetime import timedelta

import pytest
from flask import g, url_for

from models.base import db, utc_now
from models.shared.email_service import EmailService
from models.user.models import User
from models.user.profile_service import UserProfileService
from models.user.tokens import UserToken


@pytest.fixture
def utente(db_session):
    u = User(username="mario_rossi", email="mario@example.com", role="player")
    u.set_password("vecchia_password")
    u.is_verified = True
    db_session.add(u)
    db_session.commit()
    return u


def _ultimo_token(user_id):
    return (
        UserToken.query.filter_by(user_id=user_id, token_type="password_reset")
        .order_by(UserToken.id.desc())
        .first()
    )


def _chiedi_reset(client, email="mario@example.com"):
    return client.post("/auth/forgot-password", data={"email": email})


def _simula_richiesta_nuova():
    """Ripulisce l'utente che Flask-Login tiene in cache su `g`.

    Serve perche' in questa suite `g` **non e' per-richiesta**: sopravvive fra
    una `client.get()` e la successiva, quindi Flask-Login trova l'utente gia'
    caricato e non richiama mai `load_user`. Senza questa pulizia, qualunque
    test sulla validita' della sessione passerebbe **sempre** — anche con il
    controllo dell'impronta completamente rimosso — perche' non lo eseguirebbe
    nessuno. Verificato con una spia su `User.from_session_id`: zero chiamate.

    In produzione ogni richiesta parte con un `g` pulito, che e' cio' che qui
    si ricrea a mano.
    """
    if hasattr(g, "_login_user"):
        delattr(g, "_login_user")


# ─────────────────────────── il giro normale ───────────────────────────


def test_giro_completo(client, utente, db_session):
    """Richiesta, link, nuova password: e la vecchia non vale piu'."""
    _chiedi_reset(client)
    token = _ultimo_token(utente.id)
    assert token is not None

    assert client.get(f"/auth/reset-password/{token.token}").status_code == 200

    risposta = client.post(
        f"/auth/reset-password/{token.token}",
        data={"password": "nuova_password", "confirm_password": "nuova_password"},
    )
    assert risposta.status_code == 302

    db_session.refresh(utente)
    assert utente.check_password("nuova_password")
    assert not utente.check_password("vecchia_password")


def test_il_link_vale_una_volta_sola(client, utente, db_session):
    _chiedi_reset(client)
    token = _ultimo_token(utente.id)
    client.post(
        f"/auth/reset-password/{token.token}",
        data={"password": "primo_cambio", "confirm_password": "primo_cambio"},
    )
    client.post(
        f"/auth/reset-password/{token.token}",
        data={"password": "secondo_cambio", "confirm_password": "secondo_cambio"},
    )

    db_session.refresh(utente)
    assert utente.check_password("primo_cambio")
    assert not utente.check_password("secondo_cambio"), "token riutilizzabile"


def test_il_link_scade(client, utente, db_session):
    _chiedi_reset(client)
    token = _ultimo_token(utente.id)
    token.expires_at = utc_now() - timedelta(hours=1)
    db_session.commit()

    assert client.get(f"/auth/reset-password/{token.token}").status_code == 302
    client.post(
        f"/auth/reset-password/{token.token}",
        data={"password": "nuova_password", "confirm_password": "nuova_password"},
    )
    db_session.refresh(utente)
    assert not utente.check_password("nuova_password"), "token scaduto accettato"


def test_email_sconosciuta_indistinguibile(client, utente):
    """Chiedere di un indirizzo che non esiste deve dare la stessa risposta.

    Altrimenti la pagina diventa un modo per sapere chi e' iscritto al sito.
    """
    nota = _chiedi_reset(client, "mario@example.com")
    ignota = _chiedi_reset(client, "nessuno@example.com")
    assert (nota.status_code, nota.location) == (ignota.status_code, ignota.location)


def test_utente_eliminato_non_riceve_niente(client, utente, db_session):
    utente.soft_delete()
    db_session.commit()
    _chiedi_reset(client)
    assert _ultimo_token(utente.id) is None


def test_campo_email_assente(client):
    """Un form senza il campo dava 400 secco: ora lo dice a parole."""
    risposta = client.post("/auth/forgot-password", data={}, follow_redirects=True)
    assert risposta.status_code == 200
    assert "Inserisci l" in risposta.get_data(as_text=True)


# ──────────────────── i quattro guasti che erano scoperti ────────────────────


def test_il_reset_butta_fuori_le_sessioni_aperte(client, utente, db_session):
    """Chi era dentro con la vecchia password non deve restarci.

    E' il caso per cui esiste il recupero password quando c'e' di mezzo un
    accesso altrui: se la sessione dell'intruso sopravvive al cambio, cambiare
    la password non serve a niente.
    """
    client.post(
        "/auth/login",
        data={"username": "mario_rossi", "password": "vecchia_password"},
        follow_redirects=True,
    )
    _simula_richiesta_nuova()
    assert client.get("/dashboard").status_code == 200, "il login non ha funzionato"

    token = UserToken.create_token(utente.id, "password_reset")
    db_session.commit()
    UserProfileService.reset_password_with_token(token.token, "nuova_password")
    db_session.commit()

    _simula_richiesta_nuova()
    assert (
        client.get("/dashboard").status_code == 302
    ), "la sessione aperta con la vecchia password e' sopravvissuta al reset"


def test_invio_fallito_lo_dice(client, utente, monkeypatch):
    """Se l'email non parte, chi ha chiesto il reset non va rassicurato.

    Prima l'esito veniva scartato: con la posta rotta — o non configurata — il
    recupero password era morto e nessuno poteva accorgersene, perche' il sito
    rispondeva «riceverai un link» esattamente come quando funzionava.
    """
    monkeypatch.setattr(
        EmailService, "send_password_reset_email", lambda *a, **k: False
    )

    risposta = _chiedi_reset(client)
    testo = risposta.get_data(as_text=True) if risposta.status_code == 200 else ""
    if risposta.status_code == 302:
        testo = client.get(risposta.location).get_data(as_text=True)

    assert "riceverai un link" not in testo
    assert "Non siamo riusciti a inviare" in testo


def test_una_nuova_richiesta_disattiva_la_precedente(client, utente):
    """Tre richieste non devono lasciare tre link buoni per 24 ore."""
    for _ in range(3):
        _chiedi_reset(client)

    tutti = UserToken.query.filter_by(
        user_id=utente.id, token_type="password_reset"
    ).all()
    validi = [t for t in tutti if t.is_valid()]
    assert len(tutti) == 3
    assert len(validi) == 1, "i link precedenti sono rimasti validi"


def test_email_inviata_dopo_il_commit(client, utente, monkeypatch):
    """Il token deve esistere sul database *prima* che parta l'email.

    `EmailService` invia in un thread: se la spedizione parte da dentro la
    transazione, un commit fallito lascia in mano all'utente un link che non
    funzionera' mai, e un commit lento glielo fa trovare «non valido» per
    qualche istante.
    """
    stato = {}

    def finto_invio(user, token, base_url):
        token_str = token if isinstance(token, str) else token.token
        stato["persistito"] = (
            UserToken.query.filter_by(token=token_str).first() is not None
        )
        stato["pendenti"] = len(db.session.new)
        return True

    monkeypatch.setattr(EmailService, "send_password_reset_email", finto_invio)
    _chiedi_reset(client)

    assert stato.get("persistito"), "l'email parte con un token non ancora scritto"
    assert stato.get("pendenti") == 0, (
        "ci sono oggetti non ancora scritti: l'invio e' tornato dentro la "
        "transazione"
    )


# ───────────────────────────── i due minori ─────────────────────────────


def test_il_reset_verifica_anche_email(client, db_session):
    """Chi ha letto il link ha dimostrato di controllare quella casella."""
    u = User(username="anna_neri", email="anna@example.com", role="player")
    u.set_password("vecchia_password")
    u.is_verified = False
    db_session.add(u)
    db_session.commit()

    client.post("/auth/forgot-password", data={"email": "anna@example.com"})
    token = _ultimo_token(u.id)
    client.post(
        f"/auth/reset-password/{token.token}",
        data={"password": "nuova_password", "confirm_password": "nuova_password"},
    )

    db_session.refresh(u)
    assert u.check_password("nuova_password")
    assert u.is_verified, "l'email non e' stata considerata verificata"


def test_cambiare_la_propria_password_non_slogga(app, client, utente):
    """Effetto collaterale da tenere a bada.

    Legare la sessione alla credenziale sloggherebbe anche chi cambia la
    password dal proprio profilo, un istante dopo averla cambiata: la route
    rinnova il cookie apposta.
    """
    client.post(
        "/auth/login",
        data={"username": "mario_rossi", "password": "vecchia_password"},
        follow_redirects=True,
    )
    with app.test_request_context():
        url = url_for("player.change_password")

    client.post(
        url,
        data={
            "current_password": "vecchia_password",
            "new_password": "nuova_password",
            "confirm_password": "nuova_password",
        },
    )

    _simula_richiesta_nuova()
    assert (
        client.get("/dashboard").status_code == 200
    ), "chi cambia la propria password si e' ritrovato fuori"
