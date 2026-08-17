"""Il profilo si modifica dalla route, e un campo assente non è un campo svuotato.

Il difetto che questi test presidiano si vede **solo** passando dall'HTTP: la
route leggeva tutti i campi con `request.form.get(...) or ""` e li passava
sempre al service, che normalizza la stringa vuota a `None`. Una richiesta
parziale — un form ridotto, una chiamata che tocca il solo telefono, un campo
tolto dal template — azzerava quindi username ed email.

Il danno non è cosmetico: senza username non si entra più, senza email non si
recupera la password. E non è nemmeno rumoroso — `request_password_reset`
risponde `True` anche a utente non trovato, per non esporre l'enumerazione
degli account, quindi l'utente vedrebbe solo una casella che non riceve mai
niente.

Il driver delle gare serve qui solo per creare l'utente e fare il login veri
(`crea_utente`, `entra`): il resto è client HTTP diretto, perché il profilo
non è una gara e non ha senso allargare `GaraDriver` per questo.
"""

from __future__ import annotations

import pytest

from gara_driver import GaraDriver
from models import db
from models.user.models import User
from models.user.role_enum import UserRole


@pytest.fixture
def giocatore(driver: GaraDriver):
    """Un giocatore autenticato, con tutti i campi del profilo valorizzati."""
    utente = driver.crea_utente(UserRole.PLAYER.value)

    riga = db.session.get(User, utente.id)
    assert riga is not None
    riga.phone = "3330000000"
    riga.home_city = "Udine"
    riga.squadra = "Biliardo Club"
    db.session.commit()

    driver.entra(utente)
    return utente


def _profilo(utente_id: int) -> User:
    """Rilegge l'utente dal DB, senza fidarsi dell'istanza in sessione."""
    db.session.expire_all()
    riga = db.session.get(User, utente_id)
    assert riga is not None
    return riga


@pytest.mark.e2e
class TestModificaParzialeDelProfilo:

    def test_un_form_che_manda_solo_il_telefono_non_azzera_il_resto(
        self, client, giocatore
    ):
        """Il difetto, nella sua forma più pura.

        Nessun campo `username`, nessun campo `email` nella richiesta: il
        service non deve nemmeno vederli. Prima li riceveva vuoti e li
        scriveva a `None`.
        """
        prima = _profilo(giocatore.id)
        nome, indirizzo = prima.username, prima.email

        risposta = client.post(
            "/player/profile/edit",
            data={"phone": "3339999999"},
            follow_redirects=True,
        )
        assert risposta.status_code == 200

        dopo = _profilo(giocatore.id)
        assert dopo.username == nome
        assert dopo.email == indirizzo
        assert dopo.phone == "3339999999"

    def test_un_form_con_username_ma_senza_email_non_azzera_l_email(
        self, client, giocatore
    ):
        """La variante che perdeva davvero un dato, e in silenzio.

        `user.username` è `nullable=False`: quando il form parziale ometteva
        *anche* lo username, il flush violava il NOT NULL, `@transactional`
        annullava tutto e l'utente vedeva un errore generico — brutto, ma
        senza danni. Se invece il form conteneva lo username e ometteva la
        sola email, non c'era nessun vincolo a fermare la scrittura:
        `user.email` (nullable) finiva a `None`, `is_verified` veniva revocata
        e partiva un token di verifica verso un indirizzo che non esiste più.

        Da lì in poi il recupero password è muto: `request_password_reset`
        risponde `True` anche a utente non trovato, per non esporre
        l'enumerazione degli account.
        """
        prima = _profilo(giocatore.id)
        indirizzo = prima.email
        prima.is_verified = True
        db.session.commit()

        client.post(
            "/player/profile/edit",
            data={"username": prima.username, "phone": "3335555555"},
            follow_redirects=True,
        )

        dopo = _profilo(giocatore.id)
        assert dopo.email == indirizzo
        assert dopo.is_verified is True
        assert dopo.phone == "3335555555"

    def test_i_campi_non_mandati_restano_quelli_di_prima(self, client, giocatore):
        """Vale per tutti i facoltativi, non solo per i due obbligatori: una
        modifica parziale è parziale, non una riscrittura con i buchi."""
        prima = _profilo(giocatore.id)
        client.post(
            "/player/profile/edit",
            data={"username": prima.username, "phone": "3331111111"},
            follow_redirects=True,
        )

        dopo = _profilo(giocatore.id)
        assert dopo.home_city == "Udine"
        assert dopo.squadra == "Biliardo Club"


@pytest.mark.e2e
class TestCampoPresenteMaVuoto:
    """Presente-e-vuoto è un gesto: significa «togli». Ma non su tutto."""

    def test_il_telefono_si_puo_cancellare(self, client, giocatore):
        client.post(
            "/player/profile/edit",
            data={"phone": "", "home_city": ""},
            follow_redirects=True,
        )

        dopo = _profilo(giocatore.id)
        assert dopo.phone is None
        assert dopo.home_city is None

    def test_lo_username_vuoto_viene_rifiutato(self, client, giocatore):
        """Qui il vuoto non è mai un gesto sensato: senza username non si entra.

        Chi volesse davvero sparire passa dall'anonimizzazione, che è
        un'altra operazione e ha le sue conseguenze.
        """
        prima = _profilo(giocatore.id).username

        risposta = client.post(
            "/player/profile/edit",
            data={"username": "", "email": "resta@example.test"},
            follow_redirects=True,
        )

        assert risposta.status_code == 200
        assert _profilo(giocatore.id).username == prima

    def test_l_email_vuota_viene_rifiutata(self, client, giocatore):
        prima = _profilo(giocatore.id).email

        client.post(
            "/player/profile/edit",
            data={"username": "nuovo_nome_valido", "email": ""},
            follow_redirects=True,
        )

        dopo = _profilo(giocatore.id)
        assert dopo.email == prima
        # Il rifiuto è dell'intera richiesta: nessun campo passa a metà.
        assert dopo.username != "nuovo_nome_valido"


@pytest.mark.e2e
class TestModificaCompleta:
    """La strada normale non deve essersi rotta nel frattempo."""

    def test_il_form_intero_aggiorna_tutto(self, client, giocatore):
        client.post(
            "/player/profile/edit",
            data={
                "username": "nome_nuovo",
                "email": _profilo(giocatore.id).email,
                "phone": "3334444444",
                "home_city": "Trieste",
                "squadra": "Nuova Squadra",
            },
            follow_redirects=True,
        )

        dopo = _profilo(giocatore.id)
        assert dopo.username == "nome_nuovo"
        assert dopo.phone == "3334444444"
        assert dopo.home_city == "Trieste"
        assert dopo.squadra == "Nuova Squadra"

    def test_cambiare_email_revoca_la_verifica(self, client, giocatore):
        """Il comportamento voluto, da non confondere col difetto: qui l'email
        cambia davvero, quindi la verifica decade ed è giusto."""
        riga = _profilo(giocatore.id)
        riga.is_verified = True
        db.session.commit()

        client.post(
            "/player/profile/edit",
            data={
                "username": riga.username,
                "email": "indirizzo.nuovo@example.test",
                "phone": "3330000000",
            },
            follow_redirects=True,
        )

        dopo = _profilo(giocatore.id)
        assert dopo.email == "indirizzo.nuovo@example.test"
        assert dopo.is_verified is False
