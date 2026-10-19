"""
Module: models/user/attivazione.py
Purpose: Chi ha l'email di un giocatore non registrato lo attiva (ADR-086,
emendamento del 2026-10-19).

Un giocatore non registrato (ADR-085) può avere un'email vera: quella che
aveva quando lo script degli storici lo ha segnato, o quella che l'admin gli
ha scritto. Fino al 2026-10-19 quella persona restava chiusa fuori due volte:

* la registrazione con quell'email rispondeva «email già in uso» — che per
  giunta diceva a chiunque quali indirizzi stanno sul sito;
* il recupero password le mandava un link valido, ma il login rifiutava i non
  registrati anche con la password nuova.

Qui vive la strada che la fa entrare. La **prova** è aver ricevuto l'email:
un link mandato a quella casella e aperto da chi la legge dimostra la stessa
cosa che dimostra il recupero password, e non serve la conferma del creatore.
Il link porta a una pagina in cui la persona sceglie username e password; il
giocatore diventa un account normale — ``is_placeholder`` falso,
``claimed_at`` valorizzato, email verificata — con tutte le sue partite, senza
nessuna unione: l'account è già il suo.

E vive qui l'avviso che sostituisce «email già in uso»: la registrazione
risponde sempre allo stesso modo, e all'indirizzo arriva un'email diversa
secondo chi lo possiede.

Come per il recupero password, il token si crea in una transazione e l'email
parte **dopo** il commit: ``EmailService`` spedisce in un thread, e un link
spedito prima del commit potrebbe non valere ancora (o mai).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from flask import has_request_context, request
from flask_babel import gettext as _
from markupsafe import escape

from models.base import db, utc_now
from models.exceptions import NotFoundError, ValidationError
from models.status_enum import ClaimRequestStatus
from models.transaction.manager import transactional

from .models import User
from .role_enum import UserRole
from .tokens import UserToken

logger = logging.getLogger(__name__)

#: Il tipo del token di attivazione. La colonna è ``String(20)``: il nome lungo
#: ``placeholder_activation`` non ci starebbe.
TOKEN_ATTIVAZIONE = "activation"

#: Quanto vale il link: come quelli di verifica e di recupero.
ORE_DI_VALIDITA = 24

#: L'avviso che parte quando l'indirizzo è di un account normale.
AVVISO = "avviso"
#: Il link di attivazione, per un non registrato ancora da riscattare.
ATTIVAZIONE = "attivazione"


def _base_url() -> str:
    """L'indirizzo del sito da mettere nei link: quello della richiesta."""
    return request.host_url.rstrip("/") if has_request_context() else ""


@dataclass(frozen=True)
class EmailDaSpedire:
    """Cosa spedire dopo il commit: a chi, quale email, con quale link."""

    tipo: str
    user_id: int
    base_url: str
    token: Optional[str] = None


class AttivazioneService:
    """Attivare un non registrato dalla sua email, e non rivelare gli indirizzi."""

    # -------------------------------------------------------------- chi si attiva

    @staticmethod
    def attivabile(user: Optional[User]) -> bool:
        """Vero per un non registrato ancora da riscattare, con un'email.

        Non i fittizi della prova (ADR-058), non chi è già stato riscattato o
        cancellato: per loro un link di attivazione non ha niente da attivare.
        """
        return bool(
            user is not None
            and user.is_placeholder
            and not user.is_fittizio
            and not user.is_deleted
            and user.claimed_at is None
            and user.email
        )

    @staticmethod
    def _nuovo_token(user_id: int) -> str:
        """Un link nuovo, e quelli chiesti prima smettono di valere.

        Stessa ragione del recupero password: chi ne chiede un altro teme
        spesso che il primo sia finito dove non doveva.
        """
        UserToken.query.filter_by(
            user_id=user_id, token_type=TOKEN_ATTIVAZIONE, is_used=False
        ).update({"is_used": True}, synchronize_session=False)
        token = UserToken.create_token(
            user_id, TOKEN_ATTIVAZIONE, expires_in_hours=ORE_DI_VALIDITA
        )
        return token.token

    @staticmethod
    def prepara_attivazione(user: User) -> EmailDaSpedire:
        """Il token di attivazione, dentro la transazione di chi chiama."""
        return EmailDaSpedire(
            tipo=ATTIVAZIONE,
            user_id=user.id,
            base_url=_base_url(),
            token=AttivazioneService._nuovo_token(user.id),
        )

    # ------------------------------------------------- registrazione con email nota

    @staticmethod
    @transactional(domain="user")
    def _prepara_avviso_di_registrazione(email: str) -> Optional[EmailDaSpedire]:
        from .profile_service import UserProfileService

        proprietario = UserProfileService.get_user_by_email(email)
        if proprietario is None:
            return None
        if AttivazioneService.attivabile(proprietario):
            return AttivazioneService.prepara_attivazione(proprietario)
        if proprietario.is_placeholder or proprietario.is_fittizio:
            # Un non registrato che non si può attivare non ha nessuno a cui
            # scrivere: niente email, e la pagina risponde come sempre.
            return None
        return EmailDaSpedire(
            tipo=AVVISO,
            user_id=proprietario.id,
            base_url=_base_url(),
        )

    @staticmethod
    def avvisa_registrazione_con_email_nota(email: str, password: str) -> None:
        """Qualcuno si è registrato con un indirizzo che il sito conosce già.

        Non nasce nessun account, e la pagina risponde **come a una
        registrazione riuscita**: dire «email già in uso» rivelerebbe a
        chiunque quali indirizzi sono registrati. Chi legge quella casella
        riceve invece l'email giusta: l'avviso con il link al recupero
        password, o — se l'indirizzo è di un non registrato — il link per
        attivarlo.

        La password non serve a niente qui: si calcola il suo hash e lo si
        butta, perché la registrazione vera lo calcola, ed è il passo più
        lento. Senza, il tempo di risposta direbbe ciò che il messaggio tace.

        Non solleva mai: un guasto della posta non deve cambiare la risposta.
        """
        # Lo stesso calcolo di `User.set_password`, dallo stesso modulo: costa
        # quanto quello della registrazione vera.
        from . import models as modello_utente

        modello_utente.generate_password_hash(password or "", method="pbkdf2:sha256")
        try:
            da_spedire = AttivazioneService._prepara_avviso_di_registrazione(email)
            if da_spedire is not None:
                AttivazioneService.spedisci(da_spedire)
        except Exception:
            logger.exception("Avviso di registrazione con email nota non spedito")

    # -------------------------------------------------------------------- email

    @staticmethod
    def spedisci(da_spedire: EmailDaSpedire) -> bool:
        """Compone l'email nella lingua di chi la riceve e la spedisce."""
        from models.shared.email_service import EmailService
        from utils.lingua import nella_lingua_di

        user = db.session.get(User, da_spedire.user_id)
        if user is None or not user.email:
            return False
        with nella_lingua_di(user.id):
            if da_spedire.tipo == ATTIVAZIONE:
                oggetto, corpo = AttivazioneService._email_di_attivazione(
                    user, da_spedire
                )
            else:
                oggetto, corpo = AttivazioneService._email_di_avviso(user, da_spedire)
        return EmailService.send_email(user.email, oggetto, corpo)

    @staticmethod
    def _email_di_attivazione(user: User, da_spedire: EmailDaSpedire) -> tuple:
        from config import Config

        link = f"{da_spedire.base_url}/auth/attiva/{da_spedire.token}"
        app = Config.APP_NAME
        oggetto = _("Attiva il tuo account - %(app)s", app=Config.APP_NAME)
        corpo = f"""
        <h1>{escape(_("Ciao %(nome)s,", nome=user.username))}</h1>
        <p>{escape(_(
            "su %(app)s c'è già un giocatore con questo indirizzo email: "
            "%(nome)s, con le partite che ha giocato in sala.",
            app=app, nome=user.username,
        ))}</p>
        <p>{escape(_(
            "Se sei tu, apri il link qui sotto: scegli nome utente e password "
            "e il giocatore diventa il tuo account, con tutte le sue partite."
        ))}</p>
        <p><a href="{link}">{escape(_("Attiva il mio account"))}</a></p>
        <p>{escape(_(
            "Se non sei stato tu a chiederlo, ignora questa email: senza il "
            "link non cambia niente."
        ))}</p>
        <p>{escape(_("Il link scadrà tra %(ore)s ore.", ore=ORE_DI_VALIDITA))}</p>
        """
        return oggetto, corpo

    @staticmethod
    def _email_di_avviso(user: User, da_spedire: EmailDaSpedire) -> tuple:
        from config import Config

        recupero = f"{da_spedire.base_url}/auth/forgot-password"
        accesso = f"{da_spedire.base_url}/auth/login"
        app = Config.APP_NAME
        oggetto = _(
            "Un tentativo di registrazione con il tuo indirizzo - %(app)s",
            app=Config.APP_NAME,
        )
        corpo = f"""
        <h1>{escape(_("Ciao %(nome)s,", nome=user.username))}</h1>
        <p>{escape(_(
            "qualcuno ha provato a registrarsi su %(app)s con il tuo indirizzo "
            "email. Non abbiamo creato nessun account nuovo: il tuo è al suo "
            "posto.",
            app=app,
        ))}</p>
        <p>{escape(_(
            "Se eri tu, hai già un account: accedi, o recupera la password "
            "se non la ricordi."
        ))}</p>
        <p><a href="{accesso}">{escape(_("Accedi"))}</a>
        · <a href="{recupero}">{escape(_("Recupera la password"))}</a></p>
        <p>{escape(_("Se non eri tu, ignora questa email."))}</p>
        """
        return oggetto, corpo

    # ------------------------------------------------------------- l'attivazione

    @staticmethod
    def token_valido(token_str: str) -> Optional[UserToken]:
        """Il token, se vale ancora e porta a un giocatore da attivare."""
        token = UserToken.query.filter_by(
            token=token_str, token_type=TOKEN_ATTIVAZIONE
        ).first()
        if token is None or not token.is_valid():
            return None
        if not AttivazioneService.attivabile(db.session.get(User, token.user_id)):
            return None
        return token

    @staticmethod
    @transactional(domain="user")
    def attiva(token_str: str, username: str, password: str) -> User:
        """Il non registrato diventa un account normale, con le sue partite.

        Raises:
            NotFoundError: link inesistente, scaduto, già usato, o giocatore già
                riscattato nel frattempo.
            ValidationError: username o password non vanno bene.
        """
        token = AttivazioneService.token_valido(token_str)
        if token is None:
            raise NotFoundError(_("Link di attivazione non valido o scaduto."))
        user = db.session.get(User, token.user_id)
        assert user is not None  # token_valido l'ha appena letto

        nuovo_username = (username or "").strip()
        if not nuovo_username:
            raise ValidationError(_("Scegli un nome utente."))
        if len(nuovo_username) > 80:
            raise ValidationError(_("Il nome utente è troppo lungo."))
        if nuovo_username.lower() == UserRole.ADMIN.value:
            raise ValidationError(
                _("Lo username «admin» (e le sue varianti) è riservato al sistema.")
            )
        # Gli username sono pubblici: dire che uno è preso non rivela niente.
        occupato = User.query.filter(
            User.username == nuovo_username, User.id != user.id
        ).first()
        if occupato is not None:
            raise ValidationError(
                _("Lo username «%(nome)s» è già in uso.", nome=nuovo_username)
            )
        if not password or len(password.strip()) < 6:
            raise ValidationError(_("La password deve avere almeno 6 caratteri."))

        user.username = nuovo_username
        user.set_password(password)
        user.is_placeholder = False
        user.claimed_at = utc_now()
        # Ha aperto un link arrivato a quella casella: è la verifica.
        user.is_verified = True
        token.mark_as_used()

        # Gli altri link ancora in giro — attivazioni chieste due volte,
        # recuperi password chiesti prima di questa correzione — non servono più.
        UserToken.query.filter(
            UserToken.user_id == user.id,
            UserToken.token_type.in_(  # type: ignore[attr-defined]
                [TOKEN_ATTIVAZIONE, "password_reset"]
            ),
            UserToken.is_used.is_(False),
        ).update({"is_used": True}, synchronize_session=False)

        AttivazioneService._chiudi_richiesta_in_attesa(user)
        db.session.flush()
        logger.info("Giocatore non registrato %s attivato dalla sua email", user.id)
        return user

    # ---------------------------------------------- una richiesta di riscatto aperta

    @staticmethod
    def _chiudi_richiesta_in_attesa(user: User) -> None:
        """Una richiesta di riscatto in attesa su di lui si chiude: rifiutata.

        Chi apre il link ha dimostrato di leggere l'email del giocatore, e
        quindi di essere lui: la richiesta di un altro che diceva di esserlo
        non ha più niente da decidere. Si chiude come **rifiutata**, decisa
        dalla persona stessa — la pagina della richiesta dirà «rifiutata,
        decisa da» lei —, perché *ritirata* direbbe che l'ha ritirata chi
        l'aveva fatta, che non è vero. Gli avvisi «Decidi» di chi doveva
        decidere si spengono, e chi aveva chiesto riceve l'esito.
        """
        from .claim_request import ClaimRequest
        from .claim_service import ClaimService

        richiesta = ClaimRequest.query.filter(
            ClaimRequest.placeholder_id == user.id,
            ClaimRequest.status == ClaimRequestStatus.PENDING.value,
        ).first()
        if richiesta is None:
            return
        richiesta.status = ClaimRequestStatus.REJECTED.value
        richiesta.decided_by_id = user.id
        richiesta.decided_at = utc_now()
        db.session.flush()
        ClaimService._risolvi_avvisi_ai_destinatari(richiesta)
        AttivazioneService._avvisa_chi_aveva_chiesto(richiesta, user)

    @staticmethod
    def _avvisa_chi_aveva_chiesto(richiesta: Any, user: User) -> None:
        from flask_babel import lazy_gettext as _l

        from models.notification.models import NotificationPriority, NotificationType

        from .claim_service import ClaimService

        ClaimService._notifica(
            [richiesta.claimant_id],
            notification_type=NotificationType.CLAIM_REQUEST_PROCESSED,
            title=_l("Esito del riscatto"),
            message=_l(
                "%(giocatore)s ha attivato il suo account dall'indirizzo email "
                "con cui era stato registrato: la tua richiesta di riscatto è "
                "chiusa.",
                giocatore=user.username,
            ),
            priority=NotificationPriority.HIGH,
            action_url=f"/riscatti/{richiesta.id}",
            action_text=_l("Vedi la richiesta"),
        )
