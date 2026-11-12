"""Nell'avvio rapido si sceglie qualunque giocatore registrato (issue #601).

Segnalazione di un utente: cerca un giocatore che ha fatto molti tornei e non
lo trova. L'avvio rapido mostrava solo chi aveva **sbloccato** le sfide
individuali e i giocatori non registrati: uno senza account si poteva
sfidare, uno con l'account e senza sblocco no.

Decisione del 2026-11-12: lo sblocco serve per **avviare** una sfida, non per
**essere scelto**. Chi viene scelto conferma o rifiuta il risultato come ogni
avversario. La proposta di sfida per una data resta com'era.
"""

import uuid

import pytest
from flask import g

from models import User, db
from models.individual_match.models import IndividualMatch
from models.individual_match.quick_match_service import QuickMatchService
from models.user.role_enum import UserRole

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _utente(sbloccato, role=UserRole.PLAYER.value):
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"avv601_{uid}",
        email=f"avv601_{uid}@test.com",
        role=role,
        gamification_override=sbloccato,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _client_for(app, user):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = user.get_id()
        sess["_fresh"] = True
    return client


def _cerca(app, chi, testo, ambito=None):
    g.pop("_login_user", None)
    url = f"/match/players/search?q={testo}"
    if ambito:
        url += f"&ambito={ambito}"
    risposta = _client_for(app, chi).get(url)
    assert risposta.status_code == 200
    return [riga["id"] for riga in risposta.get_json()]


def test_chi_non_ha_sbloccato_le_sfide_si_puo_scegliere(app):
    avversario = _utente(sbloccato=False)
    assert avversario.can_access("create_match_direct") is False

    assert QuickMatchService.can_be_opponent(avversario) is True


def test_la_ricerca_dell_avvio_rapido_lo_trova(app):
    io, avversario = _utente(sbloccato=True), _utente(sbloccato=False)

    assert avversario.id in _cerca(app, io, avversario.username, ambito="sfida")


def test_la_partita_parte(app):
    io, avversario = _utente(sbloccato=True), _utente(sbloccato=False)

    g.pop("_login_user", None)
    risposta = _client_for(app, io).post(
        "/match/quick", data={"opponent_id": str(avversario.id)}
    )

    assert risposta.status_code == 302
    partita = IndividualMatch.query.one()
    assert {partita.player1_id, partita.player2_id} == {io.id, avversario.id}


def test_la_proposta_per_una_data_resta_a_chi_ha_sbloccato(app):
    """La proposta va accettata dalle sfide: chi non le ha non la vedrebbe."""
    io, avversario = _utente(sbloccato=True), _utente(sbloccato=False)

    assert avversario.id not in _cerca(app, io, avversario.username)


def test_l_admin_non_e_un_avversario(app):
    admin = _utente(sbloccato=True, role=UserRole.ADMIN.value)

    assert QuickMatchService.can_be_opponent(admin) is False
