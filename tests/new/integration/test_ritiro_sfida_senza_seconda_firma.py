"""Chi ha firmato può ritirare una sfida rimasta senza seconda firma (2026-10-17).

Regola decisa dall'utente (``SPECIFICHE.md``, nota del 2026-10-17; UC10 di
``docs/usecases/sfide-e-certificazione.md``): una sfida in corso con la sola
firma di chi chiede, e quella dell'avversario assente, si può **ritirare**.
Finisce annullata ed esce da ogni vista e dall'ELO. Lo può fare solo chi ha
firmato — l'avversario ha già «rifiuta» — e dopo la doppia firma non si tocca
più.

Qui si difende anche quello che il giocatore vede:

* il pulsante «Ritira la sfida» nel dettaglio, solo per chi ha firmato;
* la pagina ``/match/`` che non propone «Continua» su una partita che aspetta
  solo una firma;
* le due notifiche all'avversario: alla prima firma e al ritiro.

Stessa impalcatura di ``test_sfide_in_attesa_di_conferma_routes.py``.
"""

from __future__ import annotations

import uuid

import pytest
from flask import g

from models import User, db
from models.base import utc_now
from models.certificazione import Vista, sfide_della_vista
from models.exceptions import ConflictError, PermissionDeniedError
from models.individual_match.match_lifecycle_service import MatchLifecycleService
from models.individual_match.models import IndividualMatch
from models.notification.models import Notification, NotificationType
from models.rating.models import MatchRatingHistory, RatingSystem
from models.status_enum import Discipline, MatchStatus
from models.user.role_enum import UserRole


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _player() -> User:
    uid = str(uuid.uuid4())[:8]
    user = User(
        username=f"rt_{uid}",
        email=f"rt_{uid}@test.com",
        role=UserRole.PLAYER.value,
        gamification_override=True,
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


def _get(client, url, **kw):
    g.pop("_login_user", None)
    return client.get(url, **kw)


def _post(client, url, **kw):
    g.pop("_login_user", None)
    return client.post(url, **kw)


def _finita(p1: User, p2: User) -> IndividualMatch:
    """Una sfida «al 3» finita 3-1 che nessuno ha ancora firmato."""
    match = IndividualMatch(
        player1_id=p1.id,
        player2_id=p2.id,
        location="Sala Ritiri",
        scheduled_at=utc_now(),
        status=MatchStatus.IN_PROGRESS,
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        is_race_to=True,
        player1_score=3,
        player2_score=1,
    )
    db.session.add(match)
    db.session.commit()
    return match


def _firmata_da(p1: User, p2: User) -> IndividualMatch:
    """Finita e firmata da ``p1``: aspetta solo la firma di ``p2``."""
    match = _finita(p1, p2)
    MatchLifecycleService.confirm_match_result(match.id, p1.id)
    return match


def _righe_elo_tutte(match_id: int) -> int:
    return MatchRatingHistory.query.filter_by(
        individual_match_id=match_id, rating_system=RatingSystem.ELO_ALL
    ).count()


def _nella_vista_tutte(match_id: int) -> bool:
    return (
        db.session.query(IndividualMatch.id)
        .filter(IndividualMatch.id == match_id, sfide_della_vista(Vista.TUTTE))
        .first()
        is not None
    )


def _notifiche(user: User, tipo: NotificationType):
    return Notification.query.filter_by(user_id=user.id, notification_type=tipo).all()


@pytest.mark.integration
class TestRitiroDalServizio:
    def test_chi_ha_firmato_la_ritira_ed_esce_da_tutto(self):
        paolo, pietro = _player(), _player()
        sfida = _firmata_da(paolo, pietro)
        assert _nella_vista_tutte(sfida.id)
        assert _righe_elo_tutte(sfida.id) == 2

        MatchLifecycleService.withdraw_match(sfida.id, paolo.id)

        sfida = db.session.get(IndividualMatch, sfida.id)
        assert sfida.status == MatchStatus.CANCELLED
        assert not _nella_vista_tutte(sfida.id)
        assert _righe_elo_tutte(sfida.id) == 0

    def test_l_avversario_non_la_ritira(self):
        """Chi deve ancora firmare ha già «rifiuta»: il ritiro non è suo."""
        paolo, pietro = _player(), _player()
        sfida = _firmata_da(paolo, pietro)

        with pytest.raises(PermissionDeniedError):
            MatchLifecycleService.withdraw_match(sfida.id, pietro.id)
        assert db.session.get(IndividualMatch, sfida.id).status == (
            MatchStatus.IN_PROGRESS
        )

    def test_chi_non_gioca_non_la_ritira(self):
        paolo, pietro, gianni = _player(), _player(), _player()
        sfida = _firmata_da(paolo, pietro)

        with pytest.raises(PermissionDeniedError):
            MatchLifecycleService.withdraw_match(sfida.id, gianni.id)

    def test_senza_firme_non_si_ritira(self):
        paolo, pietro = _player(), _player()
        sfida = _finita(paolo, pietro)

        with pytest.raises(ConflictError):
            MatchLifecycleService.withdraw_match(sfida.id, paolo.id)

    def test_dopo_la_doppia_firma_non_si_tocca(self):
        paolo, pietro = _player(), _player()
        sfida = _firmata_da(paolo, pietro)
        MatchLifecycleService.confirm_match_result(sfida.id, pietro.id)
        assert db.session.get(IndividualMatch, sfida.id).status == (
            MatchStatus.CONFIRMED_BY_BOTH
        )

        with pytest.raises(ConflictError):
            MatchLifecycleService.withdraw_match(sfida.id, paolo.id)

    def test_l_avversario_riceve_la_notizia(self):
        paolo, pietro = _player(), _player()
        sfida = _firmata_da(paolo, pietro)

        MatchLifecycleService.withdraw_match(sfida.id, paolo.id)

        notifiche = _notifiche(pietro, NotificationType.MATCH_CANCELLED)
        assert len(notifiche) == 1
        assert paolo.username in notifiche[0].message
        assert notifiche[0].action_url == f"/match/matches/{sfida.id}"
        assert not _notifiche(paolo, NotificationType.MATCH_CANCELLED)


@pytest.mark.integration
class TestNotificaAllaPrimaFirma:
    def test_alla_prima_firma_l_avversario_e_avvisato(self):
        paolo, pietro = _player(), _player()
        sfida = _firmata_da(paolo, pietro)

        notifiche = _notifiche(pietro, NotificationType.MATCH_RESULT_TO_CONFIRM)
        assert len(notifiche) == 1
        assert notifiche[0].action_url == f"/match/matches/{sfida.id}"
        assert not _notifiche(paolo, NotificationType.MATCH_RESULT_TO_CONFIRM)

    def test_la_firma_d_ufficio_alla_distanza_avvisa_chi_perde(self):
        from models.individual_match.individual_rack_service import (
            IndividualRackService,
        )

        paolo, pietro = _player(), _player()
        sfida = _finita(paolo, pietro)
        sfida.player1_score = 2
        db.session.commit()

        IndividualRackService.add_rack_for_player(sfida.id, paolo.id, paolo.id)

        assert db.session.get(IndividualMatch, sfida.id).player1_confirmed
        assert len(_notifiche(pietro, NotificationType.MATCH_RESULT_TO_CONFIRM)) == 1

    def test_una_firma_ripetuta_non_ripete_l_avviso(self):
        """Rifiuto, correzione, nuova firma: l'avviso ancora da leggere basta."""
        paolo, pietro = _player(), _player()
        sfida = _firmata_da(paolo, pietro)
        sfida = db.session.get(IndividualMatch, sfida.id)
        sfida.player1_confirmed = False
        sfida.player1_confirmed_at = None
        db.session.commit()

        MatchLifecycleService.confirm_match_result(sfida.id, paolo.id)

        assert len(_notifiche(pietro, NotificationType.MATCH_RESULT_TO_CONFIRM)) == 1

    def test_la_seconda_firma_non_avvisa_nessuno(self):
        paolo, pietro = _player(), _player()
        sfida = _firmata_da(paolo, pietro)

        MatchLifecycleService.confirm_match_result(sfida.id, pietro.id)

        assert not _notifiche(paolo, NotificationType.MATCH_RESULT_TO_CONFIRM)


@pytest.mark.integration
class TestRitiroDallaPagina:
    def test_il_pulsante_lo_vede_solo_chi_ha_firmato(self, app):
        paolo, pietro = _player(), _player()
        sfida = _firmata_da(paolo, pietro)
        url = f"/match/matches/{sfida.id}"
        azione = f"/match/matches/{sfida.id}/withdraw"

        html_paolo = _get(_client_for(app, paolo), url).get_data(as_text=True)
        html_pietro = _get(_client_for(app, pietro), url).get_data(as_text=True)

        assert azione in html_paolo
        assert "Ritira la sfida" in html_paolo
        assert azione not in html_pietro

    def test_il_pulsante_chiede_conferma_senza_il_dialogo_del_browser(self, app):
        paolo, pietro = _player(), _player()
        sfida = _firmata_da(paolo, pietro)

        html = _get(_client_for(app, paolo), f"/match/matches/{sfida.id}").get_data(
            as_text=True
        )
        inizio = html.index(f"/match/matches/{sfida.id}/withdraw")
        modulo = html[inizio : html.index("</form>", inizio)]
        assert "csrf_token" in modulo
        assert "confirmSubmit(" in modulo
        assert "confirmText" in modulo

    def test_la_route_la_ritira(self, app):
        paolo, pietro = _player(), _player()
        sfida = _firmata_da(paolo, pietro)

        risposta = _post(_client_for(app, paolo), f"/match/matches/{sfida.id}/withdraw")

        assert risposta.status_code == 302
        assert db.session.get(IndividualMatch, sfida.id).status == (
            MatchStatus.CANCELLED
        )

    def test_la_route_rifiuta_l_avversario(self, app):
        paolo, pietro = _player(), _player()
        sfida = _firmata_da(paolo, pietro)

        risposta = _post(
            _client_for(app, pietro), f"/match/matches/{sfida.id}/withdraw"
        )

        assert risposta.status_code == 302
        assert db.session.get(IndividualMatch, sfida.id).status == (
            MatchStatus.IN_PROGRESS
        )


@pytest.mark.integration
class TestPaginaDelleSfide:
    def test_una_sfida_firmata_non_propone_continua(self, app):
        paolo, pietro = _player(), _player()
        sfida = _firmata_da(paolo, pietro)

        for user in (paolo, pietro):
            html = _get(_client_for(app, user), "/match/").get_data(as_text=True)
            assert f"/match/matches/{sfida.id}" in html
            assert "In attesa di conferma" in html
            assert "Continua" not in html
            assert "Apri la sfida" in html

    def test_una_sfida_in_corso_resta_da_giocare(self, app):
        paolo, pietro = _player(), _player()
        sfida = _finita(paolo, pietro)
        sfida.player1_score = 1
        db.session.commit()

        html = _get(_client_for(app, paolo), "/match/").get_data(as_text=True)

        assert "Continua" in html
        assert "In attesa di conferma" not in html
