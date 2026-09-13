"""Una notifica si scrive nella lingua di chi la riceve (ADR-062).

Il difetto che questi test tengono chiuso: il testo di una notifica veniva
tradotto nella lingua di **chi premeva il pulsante**. Un giocatore inglese
ritirato da un direttore italiano leggeva la notifica in italiano, e un
promemoria composto da uno scheduled task usciva nella lingua di ripiego per
chiunque. Come per il fuso (ADR-043): il testo è per qualcun altro, quindi si
compone nella sua lingua.

Le frasi usate hanno una traduzione inglese già nel catalogo: il test verifica
la lingua, non la traduzione.
"""

import threading
import uuid

from flask_babel import force_locale, gettext as _, lazy_gettext as _l

from models.base import db
from models.notification.factory import NotificationFactory
from models.notification.models import Notification, NotificationType
from models.notification.services import NotificationService
from models.user.models import User
from models.user.role_enum import UserRole


def _utente(db_session, lingua):
    codice = uuid.uuid4().hex[:8]
    utente = User(
        username=f"u_{codice}",
        email=f"{codice}@test.local",
        role=UserRole.PLAYER.value,
    )
    utente.set_password("password-di-prova")
    utente.language = lingua
    db_session.add(utente)
    db_session.commit()
    return utente


def _ultima(user_id):
    return (
        Notification.query.filter_by(user_id=user_id)
        .order_by(Notification.id.desc())
        .first()
    )


def test_un_direttore_in_italiano_scrive_a_un_giocatore_inglese(db_session):
    giocatore = _utente(db_session, "en")

    with force_locale("it"):
        NotificationFactory.create_gara_inscription_notification(
            user_id=giocatore.id,
            gara_id=1,
            gara_name="Coppa di primavera",
            gara_date="15/03/2026",
            enrolled_by="Paolo",
        )

    notifica = _ultima(giocatore.id)
    assert notifica.title == "Competition Enrollment"
    assert "Paolo" in notifica.message
    assert "Coppa di primavera" in notifica.message
    assert "ti ha iscritto" not in notifica.message


def test_un_testo_per_due_destinatari_esce_in_due_lingue(db_session):
    italiano = _utente(db_session, "it")
    inglese = _utente(db_session, "en")

    with force_locale("it"):
        NotificationFactory.create_bulk_notification(
            user_ids=[italiano.id, inglese.id],
            notification_type=NotificationType.MATCH_DECLINED,
            title=_l("Proposta rifiutata"),
            message=_l("Promemoria sfida"),
        )

    assert _ultima(italiano.id).title == "Proposta rifiutata"
    assert _ultima(inglese.id).title == "Proposal declined"
    assert _ultima(inglese.id).message == "Match reminder"


def test_un_testo_composto_da_una_funzione_segue_il_destinatario(db_session):
    inglese = _utente(db_session, "en")

    with force_locale("it"):
        NotificationService.create_notification(
            user_id=inglese.id,
            notification_type=NotificationType.EXAM_CERTIFIED,
            title=lambda: _("Esame certificato"),
            message=lambda: "«%s» — %s" % ("Esame", _("Promemoria sfida")),
        )

    notifica = _ultima(inglese.id)
    assert notifica.title == "Exam certified"
    assert notifica.message == "«Esame» — Match reminder"


def test_chi_non_ha_una_lingua_legge_in_italiano(db_session):
    senza_lingua = _utente(db_session, None)

    with force_locale("en"):
        NotificationService.create_notification(
            user_id=senza_lingua.id,
            notification_type=NotificationType.MATCH_DECLINED,
            title=_l("Proposta rifiutata"),
            message=_l("Promemoria sfida"),
        )

    assert _ultima(senza_lingua.id).title == "Proposta rifiutata"


def test_la_lingua_di_chi_preme_torna_com_era(db_session):
    inglese = _utente(db_session, "en")

    with force_locale("it"):
        NotificationService.create_notification(
            user_id=inglese.id,
            notification_type=NotificationType.EXAM_CERTIFIED,
            title=_l("Esame certificato"),
            message=_l("Promemoria sfida"),
        )
        assert _("Esame certificato") == "Esame certificato"


def test_fuori_da_una_richiesta_vale_lo_stesso(app, db_session):
    """Un thread con il solo contesto dell'app: come uno scheduled task."""
    inglese = _utente(db_session, "en")
    user_id = inglese.id
    errori = []

    def lavoro():
        with app.app_context():
            try:
                NotificationService.create_notification(
                    user_id=user_id,
                    notification_type=NotificationType.EXAM_CERTIFIED,
                    title=_l("Esame certificato"),
                    message=_l("Promemoria sfida"),
                )
            except Exception as errore:  # pragma: no cover - lo dice l'assert
                errori.append(errore)
            finally:
                db.session.remove()

    filo = threading.Thread(target=lavoro)
    filo.start()
    filo.join()

    assert not errori
    db.session.expire_all()
    assert _ultima(user_id).title == "Exam certified"
