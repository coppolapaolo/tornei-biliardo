"""Se la notifica non parte, l'errore deve arrivare dove qualcuno lo guarda.

Il presidio statico (`test_no_print_in_application_code.py`) vieta `print()` nel
codice applicativo, ma da solo non basta: un `logger.debug(...)` al posto del
`print` lo soddisferebbe e lascerebbe l'errore altrettanto invisibile. Il
livello e lo stack sono la sostanza della issue #256, non il fatto che si usi
`logging`.

Quello che si verifica qui è il contratto dei rami `except` di
`InscriptionService`: la promozione dalla lista d'attesa **avviene comunque**
— il posto è del giocatore anche se l'avviso non parte, ed è per questo che
l'eccezione resta catturata — ma finisce a livello ERROR con `exc_info`, cioè
diventa una issue su GlitchTip con lo stack invece di una riga di server log
che nessuno legge.
"""

from __future__ import annotations

import logging
from datetime import date, time

import pytest

from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara, Inscription
from models.status_enum import Discipline, GaraStatus
from models.user.role_enum import UserRole


@pytest.fixture
def gara_con_iscritto_in_attesa(db_session):
    """Una gara con un giocatore in lista d'attesa, pronto a essere promosso."""
    from models import User

    gara = Gara(
        number=1,
        name="Gara con lista d'attesa",
        date=date(2026, 3, 1),
        time=time(20, 0),
        discipline=Discipline.EIGHT_BALL.value,
        distance=5,
        rounds_count=3,
        min_participants=2,
        max_participants=4,
        matchmaking_strategy="amalfi",
        status=GaraStatus.INSCRIPTION.value,
    )
    db_session.add(gara)
    db_session.flush()

    giocatore = User(
        username="in_attesa_256",
        email="in_attesa_256@test.com",
        role=UserRole.PLAYER.value,
    )
    giocatore.set_password("player123")
    db_session.add(giocatore)
    db_session.flush()

    iscrizione = Inscription(
        gara_id=gara.id,
        user_id=giocatore.id,
        is_waitlist=True,
        waitlist_position=1,
    )
    db_session.add(iscrizione)
    db_session.commit()

    return gara, iscrizione


@pytest.mark.unit
def test_la_notifica_fallita_finisce_a_livello_error_con_lo_stack(
    app, db_session, gara_con_iscritto_in_attesa, monkeypatch, caplog
):
    """Notifica in errore → ERROR con `exc_info`, non una riga stampata."""
    gara, iscrizione = gara_con_iscritto_in_attesa

    def esplode(*_args, **_kwargs):
        raise RuntimeError("il servizio di notifica non risponde")

    from models.notification import factory

    monkeypatch.setattr(
        factory.NotificationFactory,
        "create_account_update_notification",
        staticmethod(esplode),
    )

    with caplog.at_level(logging.DEBUG):
        InscriptionService._promote_and_notify(iscrizione, gara)

    errori = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errori, (
        "L'eccezione della notifica è stata catturata e nessuno l'ha "
        "registrata a livello ERROR: su GlitchTip non arriva niente."
    )
    assert any(
        r.exc_info for r in errori
    ), "L'errore è registrato senza `exc_info`: la issue arriva senza stack."


@pytest.mark.unit
def test_la_promozione_avviene_lo_stesso(
    app, db_session, gara_con_iscritto_in_attesa, monkeypatch
):
    """L'avviso mancato non toglie il posto a chi è stato promosso.

    È la ragione per cui l'eccezione resta catturata invece di risalire: la
    promozione è già scritta quando si tenta la notifica, e propagare farebbe
    perdere il lavoro appena fatto.
    """
    gara, iscrizione = gara_con_iscritto_in_attesa

    def esplode(*_args, **_kwargs):
        raise RuntimeError("il servizio di notifica non risponde")

    from models.notification import factory

    monkeypatch.setattr(
        factory.NotificationFactory,
        "create_account_update_notification",
        staticmethod(esplode),
    )

    InscriptionService._promote_and_notify(iscrizione, gara)

    assert iscrizione.is_waitlist is False
    assert iscrizione.waitlist_position is None
