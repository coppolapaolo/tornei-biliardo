"""Due difetti piccoli trovati cercando nel codice le tracce delle istruzioni
sbagliate (audit del 2026-09-30).

- La revoca di un gestore di sala mandava come «motivo» una frase italiana
  fissa, che ripeteva il titolo e non si traduceva: chi usa l'app in inglese
  riceveva un messaggio a metà in italiano.
- La pagina delle statistiche delle sfide, in caso d'errore, mostrava il testo
  tecnico dell'eccezione, in inglese, con uno status 400 come se la richiesta
  fosse sbagliata.
"""

import uuid

import pytest

from models.location.models import BilliardHall
from models.notification.models import Notification
from models.user.models import User, VenueManagement
from models.user.role_enum import UserRole


def _utente(db_session, role: UserRole) -> User:
    uid = uuid.uuid4().hex[:8]
    u = User(username=f"u_{uid}", email=f"u_{uid}@test.local", role=role.value)
    u.set_password("pw123456")
    db_session.add(u)
    db_session.commit()
    return u


@pytest.mark.unit
def test_la_revoca_non_aggiunge_un_motivo_scritto_a_mano(db_session):
    from models.user.venue_manager_service import VenueManagerService

    admin = _utente(db_session, UserRole.ADMIN)
    gestore = _utente(db_session, UserRole.PLAYER)
    sala = BilliardHall(name=f"Sala {uuid.uuid4().hex[:6]}", is_active=True)
    db_session.add(sala)
    db_session.commit()
    incarico = VenueManagement(
        user_id=gestore.id, venue_id=sala.id, assigned_by_id=admin.id, is_active=True
    )
    db_session.add(incarico)
    db_session.commit()

    VenueManagerService.revoke_venue_manager(incarico.id, revoked_by=admin)

    avviso = (
        Notification.query.filter_by(user_id=gestore.id)
        .order_by(Notification.id.desc())
        .first()
    )
    assert avviso is not None
    assert "revocata" in avviso.message
    assert "Motivo" not in avviso.message


@pytest.mark.unit
def test_le_statistiche_non_mostrano_l_errore_interno(logged_in_client, monkeypatch):
    from models.individual_match.services import IndividualMatchService

    def guasto(_user_id):
        raise RuntimeError("dettaglio interno da non mostrare")

    monkeypatch.setattr(IndividualMatchService, "get_user_statistics", guasto)
    client, _user = logged_in_client(role="player")

    risposta = client.get(
        "/match/statistics", headers={"Accept": "application/json"}, json={}
    )

    assert risposta.status_code == 500
    corpo = risposta.get_json()
    assert corpo["success"] is False
    assert "dettaglio interno" not in corpo["error"]
    assert "Error loading" not in corpo["error"]


@pytest.mark.unit
def test_il_messaggio_d_errore_generico_si_traduce(app):
    """Era una costante italiana: chi usa l'app in inglese la leggeva in
    italiano. Ora si compone nella lingua di chi legge."""
    from flask_babel import force_locale

    from utils.route_helpers import handle_ajax_service_action

    def guasto():
        raise RuntimeError("dettaglio interno")

    with app.test_request_context("/", headers={"X-Requested-With": "XMLHttpRequest"}):
        with force_locale("en"):
            risposta, status = handle_ajax_service_action(
                action=guasto, redirect_url="/", success_message="ok"
            )

    assert status == 500
    assert risposta.get_json()["error"] == "Internal server error"
