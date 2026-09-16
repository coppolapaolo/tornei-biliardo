"""La finestra di iscrizione vale per i giocatori, non per il direttore.

`SPECIFICHE.md`, sezione «Gara», nota del 2026-09-16. Chi arriva in sala senza
essersi iscritto in tempo entra lo stesso, iscritto dal direttore, finché la
gara non è avviata; chi avvisa che non viene si toglie. L'iscrizione fatta dal
direttore resta riconoscibile (`inscribed_by_id`), e posti e parità valgono
come per tutti.

Fino a oggi la route del direttore riceveva «Iscrizioni chiuse» come un
giocatore qualsiasi, e il campo «Iscrivi un giocatore» spariva dalla pagina
proprio a scadenza passata.
"""

from __future__ import annotations

import uuid
from datetime import date, time, timedelta

import pytest

from models.base import db, utc_now
from models.competition.inscription_service import InscriptionService
from models.competition.models import Gara, Inscription
from models.exceptions import ConflictError
from models.status_enum import Discipline, GaraStatus
from models.user.models import User
from models.user.role_enum import UserRole


def _utente(db_session, role=UserRole.PLAYER.value):
    s = uuid.uuid4().hex[:8]
    u = User(username=f"{role}_{s}", email=f"{role}_{s}@test.com", role=role)
    u.set_password("password123")
    db_session.add(u)
    db_session.flush()
    return u


def _gara(db_session, direttore, *, finestra, **campi):
    """Una gara in fase iscrizioni; `finestra` è (inizio, fine) relativi a ora."""
    inizio, fine = finestra
    g = Gara(
        name=f"Gara {uuid.uuid4().hex[:6]}",
        number=1,
        date=date.today() + timedelta(days=7),
        time=time(20, 0),
        discipline=Discipline.EIGHT_BALL.value,
        distance=3,
        rounds_count=1,
        min_participants=2,
        director_id=direttore.id,
        status=GaraStatus.INSCRIPTION.value,
        inscription_start=utc_now() + inizio,
        inscription_end=utc_now() + fine,
        **campi,
    )
    db_session.add(g)
    db_session.commit()
    return g


CHIUSA = (timedelta(days=-2), timedelta(hours=-1))
APERTA = (timedelta(hours=-1), timedelta(days=1))
NON_ANCORA = (timedelta(days=1), timedelta(days=2))


def _riga(gara, giocatore) -> Inscription | None:
    return Inscription.query.filter_by(gara_id=gara.id, user_id=giocatore.id).first()


class TestIlDirettoreIscriveAFinestraChiusa:
    def test_entra_e_resta_scritto_chi_lo_ha_iscritto(self, db_session):
        direttore = _utente(db_session, UserRole.DIRECTOR.value)
        giocatore = _utente(db_session)
        gara = _gara(db_session, direttore, finestra=CHIUSA)

        InscriptionService.inscribe_user(
            giocatore.id, gara.id, inscribed_by_id=direttore.id
        )

        riga = _riga(gara, giocatore)
        assert riga is not None and not riga.is_waitlist
        assert riga.inscribed_by_id == direttore.id
        assert riga.iscritto_dal_direttore

    def test_anche_prima_dell_apertura(self, db_session):
        direttore = _utente(db_session, UserRole.DIRECTOR.value)
        giocatore = _utente(db_session)
        gara = _gara(db_session, direttore, finestra=NON_ANCORA)

        InscriptionService.inscribe_user(
            giocatore.id, gara.id, inscribed_by_id=direttore.id
        )

        assert _riga(gara, giocatore) is not None

    def test_il_giocatore_da_solo_resta_fuori(self, db_session):
        direttore = _utente(db_session, UserRole.DIRECTOR.value)
        giocatore = _utente(db_session)
        gara = _gara(db_session, direttore, finestra=CHIUSA)

        with pytest.raises(ConflictError, match="Iscrizioni chiuse"):
            InscriptionService.inscribe_user(giocatore.id, gara.id)
        assert _riga(gara, giocatore) is None

    def test_chi_si_iscrive_da_solo_non_risulta_iscritto_da_altri(self, db_session):
        direttore = _utente(db_session, UserRole.DIRECTOR.value)
        giocatore = _utente(db_session)
        gara = _gara(db_session, direttore, finestra=APERTA)

        InscriptionService.inscribe_user(giocatore.id, gara.id)

        riga = _riga(gara, giocatore)
        assert riga is not None
        assert riga.inscribed_by_id is None
        assert not riga.iscritto_dal_direttore

    def test_oltre_i_posti_va_in_lista_d_attesa_come_tutti(self, db_session):
        """La finestra non vale per il direttore; i posti sì."""
        direttore = _utente(db_session, UserRole.DIRECTOR.value)
        gara = _gara(db_session, direttore, finestra=CHIUSA, max_participants=1)
        primo, secondo = _utente(db_session), _utente(db_session)

        InscriptionService.inscribe_user(
            primo.id, gara.id, inscribed_by_id=direttore.id
        )
        InscriptionService.inscribe_user(
            secondo.id, gara.id, inscribed_by_id=direttore.id
        )

        assert not _riga(gara, primo).is_waitlist
        assert _riga(gara, secondo).is_waitlist

    def test_e_lo_toglie_a_finestra_chiusa(self, db_session):
        direttore = _utente(db_session, UserRole.DIRECTOR.value)
        giocatore = _utente(db_session)
        gara = _gara(db_session, direttore, finestra=APERTA)
        InscriptionService.inscribe_user(giocatore.id, gara.id)
        gara.inscription_end = utc_now() - timedelta(hours=1)
        db_session.commit()

        assert InscriptionService.admin_uninscribe_user(
            giocatore.id, gara.id, direttore.id
        )
        assert _riga(gara, giocatore) is None


class TestLaPaginaDelDirettore:
    def _accedi(self, client, utente):
        from flask import g

        with client.session_transaction() as sessione:
            sessione["_user_id"] = utente.get_id()
        g.pop("_login_user", None)

    def test_la_route_iscrive_a_finestra_chiusa_e_firma(self, client, db_session):
        direttore = _utente(db_session, UserRole.DIRECTOR.value)
        giocatore = _utente(db_session)
        gara = _gara(db_session, direttore, finestra=CHIUSA)
        self._accedi(client, direttore)

        risposta = client.post(
            f"/admin/gara/{gara.id}/admin_inscribe",
            data={"user_id": str(giocatore.id)},
            follow_redirects=True,
        )

        assert risposta.status_code == 200
        db.session.expire_all()
        riga = _riga(gara, giocatore)
        assert riga is not None
        assert riga.inscribed_by_id == direttore.id

    def test_il_campo_iscrivi_resta_a_finestra_chiusa_e_l_elenco_dice_chi(
        self, client, db_session
    ):
        direttore = _utente(db_session, UserRole.DIRECTOR.value)
        giocatore = _utente(db_session)
        _utente(db_session)  # un candidato da iscrivere: senza, il campo non compare
        gara = _gara(db_session, direttore, finestra=CHIUSA)
        InscriptionService.inscribe_user(
            giocatore.id, gara.id, inscribed_by_id=direttore.id
        )
        db_session.commit()
        self._accedi(client, direttore)

        html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

        assert "Iscrivi un giocatore" in html
        assert f"iscritto da {direttore.username}" in html

    def test_a_gara_avviata_il_campo_sparisce(self, client, db_session):
        direttore = _utente(db_session, UserRole.DIRECTOR.value)
        gara = _gara(db_session, direttore, finestra=CHIUSA)
        gara.status = GaraStatus.PLAYING.value
        gara.current_round = 1
        db_session.commit()
        self._accedi(client, direttore)

        html = client.get(f"/admin/gara/{gara.id}").get_data(as_text=True)

        assert "Iscrivi un giocatore" not in html
