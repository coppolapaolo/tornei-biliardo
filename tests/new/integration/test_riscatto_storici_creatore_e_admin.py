"""Gli storici, chi li ha creati, e l'admin come ripiego (ADR-086, emendamento
del 2026-10-19).

Quattro richieste dell'utente in un file:

1. lo script dei non registrati lavora anche su **un utente solo**
   (``--user-id``), e dice quale criterio manca a chi non si segna;
2. il **creatore** di uno storico si ricostruisce dalla prima gara: chi l'ha
   iscritto, oppure l'unico direttore; con più direttori confermano tutti;
3. l'**admin** decide qualunque riscatto in attesa, ma la notifica gli arriva
   solo quando non c'è nessun altro;
4. il direttore crea il non registrato **dalla ricerca** dell'iscrizione.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, time as ora, timedelta

import pytest
from flask import g

from models import User, db
from models.base import utc_now
from models.campionato.models import Campionato
from models.competition.models import Gara, Inscription
from models.exceptions import PermissionDeniedError
from models.matchmaking.configuration import MatchmakingStrategy
from models.notification.models import (
    Notification,
    NotificationStatus,
    NotificationType,
)
from models.status_enum import ClaimRequestStatus, Discipline, GaraStatus
from models.user.claim_request import ClaimRequest
from models.user.claim_service import ClaimService
from models.user.placeholder_storici import (
    ModoRicostruzione,
    criteri_mancanti,
    candidati_storici,
    prima_iscrizione,
    ricostruisci_creatore,
    storici_da_completare,
)
from models.user.role_enum import UserRole
from models.user.services import UserService
from models.user.session_models import UserSession
from scripts.mark_placeholder_users import elabora


@pytest.fixture(autouse=True)
def _ctx(app, db_session):
    with app.app_context():
        yield


def _user(role: str = UserRole.PLAYER.value, **campi) -> User:
    uid = uuid.uuid4().hex[:8]
    campi.setdefault("onboarding_completed", True)
    user = User(
        username=f"st_{uid}",
        email=f"st_{uid}@test.com",
        role=role,
        gamification_override=True,
        **campi,
    )
    user.set_password("pw123456")
    db.session.add(user)
    db.session.commit()
    return user


def _admin() -> User:
    esistente = User.query.filter_by(role=UserRole.ADMIN.value).first()
    return esistente or _user(UserRole.ADMIN.value)


def _mai_entrato() -> User:
    """Un utente storico: ha un account mai usato."""
    return _user(onboarding_completed=False)


def _gara(
    titolare: User, giorni: int = 7, codirettori=(), campionato=None, **campi
) -> Gara:
    gara = Gara(
        campionato_id=campionato.id if campionato else None,
        name=f"Gara {uuid.uuid4().hex[:6]}",
        number=1,
        date=date.today() + timedelta(days=giorni),
        time=ora(20, 0),
        discipline=Discipline.NINE_BALL.value,
        distance=5,
        rounds_count=3,
        min_participants=2,
        max_participants=16,
        matchmaking_strategy=MatchmakingStrategy.RANDOM.value,
        director_id=titolare.id,
        status=GaraStatus.INSCRIPTION.value,
        inscription_start=utc_now() - timedelta(days=1),
        inscription_end=utc_now() + timedelta(days=3),
        **campi,
    )
    db.session.add(gara)
    db.session.commit()
    from models.competition.services import GaraService

    for codirettore in codirettori:
        GaraService.add_director(gara.id, codirettore.id, titolare.id)
    db.session.commit()
    return gara


def _eliminata(gara: Gara) -> Gara:
    gara.soft_delete("prova dello script")
    db.session.commit()
    return gara


def _campionato_eliminato() -> Campionato:
    """Un campionato eliminato che ha lasciato viva la sua gara.

    ``Campionato.soft_delete`` elimina anche le gare; qui il campionato se ne
    va da solo, come per i dati scritti prima di quella cascata.
    """
    campionato = Campionato(name=f"Camp {uuid.uuid4().hex[:6]}", planned_gare_count=1)
    db.session.add(campionato)
    db.session.commit()
    campionato.deleted_at = utc_now()
    db.session.commit()
    return campionato


def _iscrivi(gara: Gara, user: User, da: User | None = None) -> Inscription:
    iscrizione = Inscription(
        gara_id=gara.id, user_id=user.id, inscribed_by_id=da.id if da else None
    )
    db.session.add(iscrizione)
    db.session.commit()
    return iscrizione


def _storico_segnato(gara: Gara) -> User:
    """Uno storico già segnato da una versione precedente dello script."""
    giocatore = _mai_entrato()
    _iscrivi(gara, giocatore)
    giocatore.is_placeholder = True
    db.session.commit()
    return giocatore


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


def _avvisi(user_id: int):
    return Notification.query.filter_by(
        user_id=user_id, notification_type=NotificationType.CLAIM_REQUEST_RECEIVED
    ).all()


# ─────────────────────────────────────────────────────── 1. un utente alla volta


class TestScriptSuUnUtente:
    def test_segna_solo_l_utente_dato(self):
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        scelto, altro = _mai_entrato(), _mai_entrato()
        _iscrivi(gara, scelto)
        _iscrivi(gara, altro)

        esito = elabora(commit=True, user_ids=[scelto.id])

        assert esito.segnati == [scelto.id]
        assert db.session.get(User, scelto.id).is_placeholder
        assert not db.session.get(User, altro.id).is_placeholder

    def test_la_prova_generale_su_un_utente_non_scrive(self):
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        scelto = _mai_entrato()
        _iscrivi(gara, scelto)

        esito = elabora(commit=False, user_ids=[scelto.id])

        assert esito.segnati == [scelto.id]
        assert esito.con_creatore == [scelto.id]
        rivisto = db.session.get(User, scelto.id)
        assert not rivisto.is_placeholder and rivisto.created_by_id is None

    def test_chi_non_rispetta_i_criteri_non_si_segna_e_si_dice_perche(self, caplog):
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        entrato = _user(onboarding_completed=True)
        _iscrivi(gara, entrato)
        db.session.add(UserSession(user_id=entrato.id, last_seen_at=utc_now()))
        db.session.commit()

        with caplog.at_level(logging.INFO, logger="scripts.mark_placeholder_users"):
            esito = elabora(commit=True, user_ids=[entrato.id, 999_999])

        assert esito.segnati == [] and esito.scartati == [entrato.id, 999_999]
        assert not db.session.get(User, entrato.id).is_placeholder
        assert "ha completato l'onboarding" in caplog.text
        assert "ha aperto almeno una sessione" in caplog.text
        assert "#999999: non esiste" in caplog.text

    def test_i_criteri_spiegati_coincidono_con_quelli_dello_script(self):
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        buono, senza_gare = _mai_entrato(), _mai_entrato()
        attivo = _user(onboarding_completed=False, last_active_at=utc_now())
        _iscrivi(gara, buono)
        _iscrivi(gara, attivo)

        assert criteri_mancanti(buono) == []
        assert criteri_mancanti(senza_gare) == ["non è iscritto a nessuna gara"]
        assert criteri_mancanti(attivo) == [
            "ha un'attività registrata (last_active_at non è vuoto)"
        ]
        assert criteri_mancanti(_admin()) and criteri_mancanti(direttore)

        # Le gare che non si vedono più non contano, nella query come qui.
        solo_eliminate, mista = _mai_entrato(), _mai_entrato()
        del_campionato_eliminato, solo_prova = _mai_entrato(), _mai_entrato()
        eliminata = _eliminata(_gara(direttore))
        _iscrivi(eliminata, solo_eliminate)
        _iscrivi(eliminata, mista)
        _iscrivi(gara, mista)
        _iscrivi(
            _gara(direttore, campionato=_campionato_eliminato()),
            del_campionato_eliminato,
        )
        _iscrivi(_gara(direttore, is_prova=True), solo_prova)
        assert criteri_mancanti(mista) == []
        for utente in (solo_eliminate, del_campionato_eliminato, solo_prova):
            assert criteri_mancanti(utente) == [SOLO_GARE_ELIMINATE]

        candidati = {u.id for u in candidati_storici()}
        for utente in (
            buono,
            senza_gare,
            attivo,
            direttore,
            solo_eliminate,
            mista,
            del_campionato_eliminato,
            solo_prova,
        ):
            assert (utente.id in candidati) == (criteri_mancanti(utente) == [])


# ──────────────────────────────────────────────────── 2. chi l'ha creato


class TestRicostruzioneDelCreatore:
    def test_vale_chi_l_ha_iscritto_se_e_un_direttore(self):
        titolare = _user(UserRole.DIRECTOR.value)
        chi_iscrive = _user(UserRole.DIRECTOR.value)
        gara = _gara(titolare)
        giocatore = _mai_entrato()
        _iscrivi(gara, giocatore, da=chi_iscrive)

        elabora(commit=True, user_ids=[giocatore.id])

        rivisto = db.session.get(User, giocatore.id)
        assert rivisto.is_placeholder and rivisto.created_by_id == chi_iscrive.id
        assert ricostruisci_creatore(rivisto).modo is ModoRicostruzione.ISCRIZIONE
        assert [u.id for u in ClaimService.destinatari(rivisto)] == [chi_iscrive.id]

    def test_chi_l_ha_iscritto_ma_non_dirige_non_conta(self):
        titolare = _user(UserRole.DIRECTOR.value)
        gara = _gara(titolare)
        giocatore = _mai_entrato()
        _iscrivi(gara, giocatore, da=_user())

        ricostruzione = ricostruisci_creatore(giocatore)

        assert ricostruzione.modo is ModoRicostruzione.DIRETTORE_UNICO
        assert ricostruzione.creatore.id == titolare.id

    def test_un_solo_direttore_e_il_creatore(self):
        titolare = _user(UserRole.DIRECTOR.value)
        giocatore = _mai_entrato()
        _iscrivi(_gara(titolare), giocatore)

        elabora(commit=True)

        rivisto = db.session.get(User, giocatore.id)
        assert rivisto.created_by_id == titolare.id
        assert [u.id for u in ClaimService.destinatari(rivisto)] == [titolare.id]

    def test_conta_la_prima_gara_per_data(self):
        primo, secondo = _user(UserRole.DIRECTOR.value), _user(UserRole.DIRECTOR.value)
        giocatore = _mai_entrato()
        _iscrivi(_gara(secondo, giorni=30), giocatore)
        _iscrivi(_gara(primo, giorni=2), giocatore)

        assert ricostruisci_creatore(giocatore).creatore.id == primo.id

    def test_con_piu_direttori_confermano_tutti_e_non_si_scrive_niente(self):
        titolare = _user(UserRole.DIRECTOR.value)
        codirettore = _user(UserRole.DIRECTOR.value)
        giocatore = _mai_entrato()
        _iscrivi(_gara(titolare, codirettori=[codirettore]), giocatore)

        esito = elabora(commit=True, user_ids=[giocatore.id])

        rivisto = db.session.get(User, giocatore.id)
        assert rivisto.is_placeholder and rivisto.created_by_id is None
        assert esito.con_creatore == []
        assert {u.id for u in ClaimService.destinatari(rivisto)} == {
            titolare.id,
            codirettore.id,
        }

    def test_senza_dati_conferma_l_admin(self):
        admin = _admin()
        giocatore = _user(onboarding_completed=False)
        giocatore.is_placeholder = True
        db.session.commit()

        assert ricostruisci_creatore(giocatore).modo is ModoRicostruzione.NESSUNO
        assert [u.id for u in ClaimService.destinatari(giocatore)] == [admin.id]

    def test_rilanciato_completa_chi_era_stato_segnato_senza_creatore(self):
        titolare = _user(UserRole.DIRECTOR.value)
        giocatore = _storico_segnato(_gara(titolare))

        prima = elabora(commit=True)
        seconda = elabora(commit=True)

        assert giocatore.id not in prima.segnati
        assert prima.con_creatore == [giocatore.id]
        assert db.session.get(User, giocatore.id).created_by_id == titolare.id
        assert seconda.segnati == [] and seconda.con_creatore == []

    def test_su_un_utente_gia_segnato_lo_completa(self):
        titolare = _user(UserRole.DIRECTOR.value)
        giocatore = _storico_segnato(_gara(titolare))

        esito = elabora(commit=True, user_ids=[giocatore.id])

        assert esito.scartati == [] and esito.con_creatore == [giocatore.id]
        assert db.session.get(User, giocatore.id).created_by_id == titolare.id


# ─────────────────────────────────── solo le gare che si vedono ancora


SOLO_GARE_ELIMINATE = (
    "è iscritto solo a gare eliminate (o di un campionato eliminato, o di prova)"
)


class TestSoloGareNonEliminate:
    """«Ha giocato» vuol dire una gara che l'app mostra ancora.

    In produzione, il 25/10/2026, la prova generale elencava otto account di
    prova iscritti **solo** a gare eliminate: segnati, sarebbero diventati
    riscattabili senza niente da riscattare.
    """

    def test_iscritto_solo_a_gare_eliminate_non_si_segna_e_si_dice_perche(self, caplog):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _mai_entrato()
        _iscrivi(_eliminata(_gara(direttore)), giocatore)
        _iscrivi(_eliminata(_gara(direttore, giorni=9)), giocatore)

        assert giocatore.id not in {u.id for u in candidati_storici()}
        assert elabora(commit=True).segnati == []
        with caplog.at_level(logging.INFO, logger="scripts.mark_placeholder_users"):
            esito = elabora(commit=True, user_ids=[giocatore.id])

        assert esito.segnati == [] and esito.scartati == [giocatore.id]
        assert not db.session.get(User, giocatore.id).is_placeholder
        assert SOLO_GARE_ELIMINATE in caplog.text

    def test_con_una_gara_eliminata_e_una_viva_si_segna_dalla_viva(self):
        chi_ha_eliminato = _user(UserRole.DIRECTOR.value)
        titolare = _user(UserRole.DIRECTOR.value)
        giocatore = _mai_entrato()
        # L'eliminata viene prima: se contasse, il creatore sarebbe l'altro.
        _iscrivi(_eliminata(_gara(chi_ha_eliminato, giorni=2)), giocatore)
        viva = _gara(titolare, giorni=20)
        _iscrivi(viva, giocatore)

        esito = elabora(commit=True)

        assert giocatore.id in esito.segnati and giocatore.id in esito.con_creatore
        rivisto = db.session.get(User, giocatore.id)
        assert rivisto.is_placeholder and rivisto.created_by_id == titolare.id
        ricostruzione = ricostruisci_creatore(rivisto)
        assert ricostruzione.modo is ModoRicostruzione.DIRETTORE_UNICO
        assert ricostruzione.gara.id == viva.id

    def test_la_gara_di_un_campionato_eliminato_non_conta(self):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _mai_entrato()
        gara = _gara(direttore, campionato=_campionato_eliminato())
        _iscrivi(gara, giocatore)

        assert gara.deleted_at is None
        assert giocatore.id not in {u.id for u in candidati_storici()}
        assert criteri_mancanti(giocatore) == [SOLO_GARE_ELIMINATE]
        assert prima_iscrizione(giocatore) is None
        assert ricostruisci_creatore(giocatore).modo is ModoRicostruzione.NESSUNO

    def test_lo_storico_gia_segnato_non_si_completa_da_una_gara_eliminata(self):
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = _storico_segnato(_eliminata(_gara(direttore)))

        assert giocatore.id not in {u.id for u in storici_da_completare()}
        assert giocatore.id not in elabora(commit=True).con_creatore


# ──────────────────────────────────────────── destinatari della richiesta


class TestDestinatariDegliStorici:
    def test_la_richiesta_arriva_a_tutti_i_direttori_e_non_all_admin(self):
        admin = _admin()
        titolare = _user(UserRole.DIRECTOR.value)
        codirettore = _user(UserRole.DIRECTOR.value)
        giocatore = _storico_segnato(_gara(titolare, codirettori=[codirettore]))

        richiesta = ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()

        assert richiesta.recipient_ids == {titolare.id, codirettore.id}
        assert len(_avvisi(titolare.id)) == 1 and len(_avvisi(codirettore.id)) == 1
        assert _avvisi(admin.id) == []

    def test_uno_dei_direttori_decide_e_l_avviso_dell_altro_si_risolve(self):
        titolare = _user(UserRole.DIRECTOR.value)
        codirettore = _user(UserRole.DIRECTOR.value)
        giocatore = _storico_segnato(_gara(titolare, codirettori=[codirettore]))
        richiesta = ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()

        ClaimService.reject(richiesta.id, codirettore)
        db.session.commit()

        assert all(a.status == NotificationStatus.READ for a in _avvisi(titolare.id))

    def test_l_attivazione_dall_email_spegne_l_avviso_di_tutti_i_direttori(self):
        """Con la PR #719 lo storico con l'email si attiva da solo, e la
        richiesta di un altro si chiude rifiutata: gli avvisi «Decidi» si
        spengono anche con più direttori destinatari."""
        from models.user.attivazione import AttivazioneService

        titolare = _user(UserRole.DIRECTOR.value)
        codirettore = _user(UserRole.DIRECTOR.value)
        giocatore = _storico_segnato(_gara(titolare, codirettori=[codirettore]))
        richiesta = ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()

        da_spedire = AttivazioneService.prepara_attivazione(giocatore)
        db.session.commit()
        AttivazioneService.attiva(
            da_spedire.token, f"att_{uuid.uuid4().hex[:6]}", "Password123!"
        )
        db.session.commit()

        rivista = db.session.get(ClaimRequest, richiesta.id)
        assert rivista.status == ClaimRequestStatus.REJECTED.value
        for direttore in (titolare, codirettore):
            assert _avvisi(direttore.id)
            assert all(
                a.status == NotificationStatus.READ for a in _avvisi(direttore.id)
            )

    def test_il_direttore_che_chiede_non_decide_la_sua_richiesta(self):
        titolare = _user(UserRole.DIRECTOR.value)
        codirettore = _user(UserRole.DIRECTOR.value)
        giocatore = _storico_segnato(_gara(titolare, codirettori=[codirettore]))

        richiesta = ClaimService.richiedi(giocatore.id, codirettore)
        db.session.commit()

        assert richiesta.recipient_ids == {titolare.id}
        assert not ClaimService.puo_decidere(richiesta, codirettore)


# ──────────────────────────────────────────────── 3. l'admin come ripiego


class TestAdminDecideSempre:
    def test_l_admin_decide_la_richiesta_di_un_direttore(self):
        admin = _admin()
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = UserService.create_placeholder(
            "Mario", f"Bianchi{uuid.uuid4().hex[:5]}", direttore
        )
        db.session.commit()
        richiesta = ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()
        assert admin.id not in richiesta.recipient_ids

        ClaimService.approve(richiesta.id, admin)
        db.session.commit()

        rivista = db.session.get(ClaimRequest, richiesta.id)
        assert rivista.status == ClaimRequestStatus.APPROVED.value
        assert rivista.decided_by_id == admin.id
        # L'avviso del direttore non chiede più niente.
        assert all(a.status == NotificationStatus.READ for a in _avvisi(direttore.id))

    def test_un_altro_direttore_resta_fuori(self):
        giocatore = UserService.create_placeholder(
            "Mario", f"Verdi{uuid.uuid4().hex[:5]}", _user(UserRole.DIRECTOR.value)
        )
        db.session.commit()
        richiesta = ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()
        with pytest.raises(PermissionDeniedError):
            ClaimService.reject(richiesta.id, _user(UserRole.DIRECTOR.value))

    def test_la_notifica_all_admin_arriva_solo_come_ripiego(self):
        admin = _admin()
        con_creatore = UserService.create_placeholder(
            "Anna", f"Neri{uuid.uuid4().hex[:5]}", _user(UserRole.DIRECTOR.value)
        )
        senza_nessuno = _user(onboarding_completed=False)
        senza_nessuno.is_placeholder = True
        db.session.commit()

        ClaimService.richiedi(con_creatore.id, _user())
        db.session.commit()
        assert _avvisi(admin.id) == []

        ClaimService.richiedi(senza_nessuno.id, _user())
        db.session.commit()
        assert len(_avvisi(admin.id)) == 1

    def test_in_riscatti_l_admin_vede_anche_quelle_degli_altri(self, app):
        admin = _admin()
        direttore = _user(UserRole.DIRECTOR.value)
        giocatore = UserService.create_placeholder(
            "Luca", f"Gialli{uuid.uuid4().hex[:5]}", direttore
        )
        db.session.commit()
        richiesta = ClaimService.richiedi(giocatore.id, _user())
        db.session.commit()

        pagina = _get(_client_for(app, admin), "/riscatti").get_data(as_text=True)

        assert "In attesa di altri" in pagina
        assert f"/riscatti/{richiesta.id}" in pagina
        assert direttore.username in pagina
        # Non gli accende il contatore: non tocca a lui.
        assert ClaimService.conta_da_decidere(admin) == 0
        dettaglio = _get(_client_for(app, admin), f"/riscatti/{richiesta.id}").get_data(
            as_text=True
        )
        assert "Conferma il riscatto" in dettaglio
        assert "Come amministratore puoi decidere tu" in dettaglio


# ─────────────────────────────────────────── 4. creazione dalla ricerca


class TestCreazioneDallaRicerca:
    def test_la_proposta_sta_dentro_la_ricerca_anche_senza_iscrivibili(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)

        pagina = _get(_client_for(app, direttore), f"/admin/gara/{gara.id}").get_data(
            as_text=True
        )

        inizio = pagina.index("data-iscrivibili")
        blocco = pagina[
            inizio : pagina.index("</form>", pagina.index("js-iscritti-crea"))
        ]
        assert "js-iscritti-cerca" in blocco
        assert f"/admin/gara/{gara.id}/admin_inscribe_placeholder" in blocco
        assert 'name="first_name"' in blocco and 'name="last_name"' in blocco
        assert "csrf_token" in blocco
        assert "Crea «{nome}» come non registrato e iscrivilo" in blocco
        # Il vecchio modulo a parte non c'è più.
        assert '<details class="c7-nonreg-crea">' not in pagina

    def test_dalla_ricerca_si_crea_e_si_iscrive(self, app):
        direttore = _user(UserRole.DIRECTOR.value)
        gara = _gara(direttore)
        cognome = f"Ricerca{uuid.uuid4().hex[:5]}"

        risposta = _post(
            _client_for(app, direttore),
            f"/admin/gara/{gara.id}/admin_inscribe_placeholder",
            data={"first_name": "Gianni", "last_name": cognome},
        )

        assert risposta.status_code == 302
        giocatore = User.query.filter_by(username=f"Gianni {cognome}").one()
        assert giocatore.is_placeholder and giocatore.created_by_id == direttore.id
        assert Inscription.query.filter_by(gara_id=gara.id, user_id=giocatore.id).one()
