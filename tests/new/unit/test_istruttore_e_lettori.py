"""L'istruttore e il legame con l'allievo (ADR-069, fase 8).

Il legame è **allievo–scheda–istruttore** (D11): non esiste «Luca mi segue»,
esiste «questa scheda la legge Luca». Da qui discendono i test di questo file,
che difendono cinque cose:

* il ruolo `INSTRUCTOR` esiste, si chiede come quello di esaminatore, e **non**
  è vero d'ufficio per l'amministratore;
* una scheda si apre **solo a un istruttore**, e il controllo sta nel servizio,
  non nella casella di ricerca;
* il permesso **vale subito** (D18), con una notifica a chi lo riceve, e chi lo
  riceve può **togliersi** da solo;
* togliere un lettore da una scheda non tocca le altre schede dello stesso
  allievo;
* «I miei istruttori» e «I miei allievi» sono **viste derivate** dalle schede:
  senza nessuna scheda aperta il legame non esiste, e non c'è riga da cui
  dedurlo.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.exceptions import PermissionDeniedError, ValidationError
from models.istruttore import allievi_di, istruttori_di
from models.notification.models import Notification, NotificationType
from models.training_sheet import SheetItemSpec, SheetMeasure, TrainingSheetService
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import GRANT_POLICY, RoleGrantService

ISTRUTTORE = GrantableRole.INSTRUCTOR


# ── allestimento ────────────────────────────────────────────────────────────


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"ist_{uid}", email=f"ist_{uid}@test.local", role=role)
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.flush()
    return user


def _istruttore(admin: User) -> User:
    """Un utente con il grant attivo di istruttore."""
    user = _user()
    RoleGrantService.grant(user.id, ISTRUTTORE, admin)
    return user


def _challenge() -> Challenge:
    challenge = Challenge(
        title=f"Esercizio {uuid.uuid4().hex[:6]}",
        description="istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=False,
    )
    db.session.add(challenge)
    db.session.flush()
    return challenge


def _scheda(owner: User, nome: str = "Tecnica di base"):
    scheda = TrainingSheetService.create_sheet(owner, nome)
    TrainingSheetService.save_composition(
        scheda.id,
        owner,
        name=nome,
        items=[
            SheetItemSpec(
                challenge_id=_challenge().id, measure=SheetMeasure.MADE, amount=5
            )
        ],
    )
    return scheda


@pytest.fixture
def admin(db_session):
    return _user(UserRole.ADMIN.value)


@pytest.fixture
def allievo(db_session):
    return _user()


# ────────────────────────────────────────────────────────────────────────────
# Il ruolo
# ────────────────────────────────────────────────────────────────────────────
def test_il_ruolo_istruttore_si_chiede_come_quello_di_esaminatore(app):
    """Stesso meccanismo dell'esaminatore: richiesta, approvazione, grant."""
    with app.app_context():
        policy = RoleGrantService.get_policy(ISTRUTTORE)
        assert policy.request_feature_code == "request_instructor"
        assert ISTRUTTORE in GRANT_POLICY


def test_un_istruttore_puo_nominarne_un_altro(app):
    """La catena è del ruolo (D10): chi insegna sa chi insegna, l'admin no.

    Al contrario del beta tester, il ruolo **non apre niente** da solo: rende
    solo trovabili. Ciò che si vede lo concede un allievo, una scheda per volta.
    """
    with app.app_context():
        assert RoleGrantService.get_policy(ISTRUTTORE).self_propagating is True


def test_l_amministratore_non_e_un_istruttore(db_session, admin):
    """A differenza di `is_examiner`, qui il bypass admin non c'è.

    Questa property decide chi compare nella ricerca di un allievo — spesso
    minorenne — che cerca a chi aprire la sua scheda. Con il bypass ci
    comparirebbero tutti gli amministratori della piattaforma: il consenso si
    dà a una persona, non a chi amministra il sito.
    """
    assert admin.is_instructor is False


def test_chi_ha_il_grant_e_un_istruttore(db_session, admin):
    istruttore = _istruttore(admin)
    assert istruttore.is_instructor is True


# ────────────────────────────────────────────────────────────────────────────
# Aprire una scheda
# ────────────────────────────────────────────────────────────────────────────
def test_una_scheda_si_apre_solo_a_un_istruttore(db_session, admin, allievo):
    """Il controllo sta nel servizio, non nella casella di ricerca.

    Nascondere un nome dall'elenco non è una regola: una POST costruita a mano
    lo aggirerebbe, e le schede di un minorenne non si difendono con l'ordine
    dei risultati.
    """
    scheda = _scheda(allievo)
    estraneo = _user()

    with pytest.raises(ValidationError):
        TrainingSheetService.add_reader(scheda.id, estraneo.id, allievo)

    assert TrainingSheetService.can_read(scheda, estraneo) is False


def test_il_permesso_vale_subito_e_avvisa_chi_lo_riceve(db_session, admin, allievo):
    """D18: nessuno stato «in attesa». Vale, e l'istruttore lo scopre."""
    scheda = _scheda(allievo)
    istruttore = _istruttore(admin)

    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)

    assert TrainingSheetService.can_read(scheda, istruttore) is True
    avvisi = Notification.query.filter_by(
        user_id=istruttore.id, notification_type=NotificationType.SHEET_SHARED
    ).all()
    assert len(avvisi) == 1


def test_chi_legge_non_compone(db_session, admin, allievo):
    """La scheda resta dell'allievo: l'istruttore guarda e dice la sua a voce."""
    scheda = _scheda(allievo)
    istruttore = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)

    assert TrainingSheetService.can_edit(scheda, istruttore) is False
    with pytest.raises(PermissionDeniedError):
        TrainingSheetService.save_composition(
            scheda.id, istruttore, name="Rifatta", items=[]
        )


def test_l_istruttore_puo_togliersi_da_solo(db_session, admin, allievo):
    """D18: chi riceve il permesso non è obbligato a tenerlo."""
    scheda = _scheda(allievo)
    istruttore = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)

    TrainingSheetService.leave_sheet(scheda.id, istruttore)

    assert TrainingSheetService.can_read(scheda, istruttore) is False


def test_nessun_altro_puo_togliere_un_lettore(db_session, admin, allievo):
    """Né un altro istruttore, né un estraneo: decide chi possiede la scheda."""
    scheda = _scheda(allievo)
    istruttore = _istruttore(admin)
    altro = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)

    with pytest.raises(PermissionDeniedError):
        TrainingSheetService.remove_reader(scheda.id, istruttore.id, altro)
    with pytest.raises(PermissionDeniedError):
        TrainingSheetService.leave_sheet(scheda.id, altro)


def test_togliere_un_lettore_non_tocca_le_altre_schede(db_session, admin, allievo):
    """«Le altre non cambiano»: il permesso è per scheda, non per persona."""
    prima = _scheda(allievo, "Tecnica di base")
    seconda = _scheda(allievo, "Prima della gara")
    istruttore = _istruttore(admin)
    TrainingSheetService.add_reader(prima.id, istruttore.id, allievo)
    TrainingSheetService.add_reader(seconda.id, istruttore.id, allievo)

    TrainingSheetService.remove_reader(prima.id, istruttore.id, allievo)

    assert TrainingSheetService.can_read(prima, istruttore) is False
    assert TrainingSheetService.can_read(seconda, istruttore) is True


def test_la_riga_resta_e_dice_da_quando_a_quando(db_session, admin, allievo):
    """Il permesso tolto non si cancella: il registro dirà chi c'era."""
    scheda = _scheda(allievo)
    istruttore = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    TrainingSheetService.remove_reader(scheda.id, istruttore.id, allievo)

    righe = [r for r in scheda.readers if r.user_id == istruttore.id]
    assert len(righe) == 1
    assert righe[0].granted_at is not None
    assert righe[0].revoked_at is not None


def test_riaprire_la_scheda_apre_un_secondo_periodo(db_session, admin, allievo):
    """Ripensarci è normale: due periodi, non una riga riscritta."""
    scheda = _scheda(allievo)
    istruttore = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    TrainingSheetService.remove_reader(scheda.id, istruttore.id, allievo)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)

    righe = [r for r in scheda.readers if r.user_id == istruttore.id]
    assert len(righe) == 2
    assert TrainingSheetService.can_read(scheda, istruttore) is True


# ────────────────────────────────────────────────────────────────────────────
# Le due viste derivate (D11)
# ────────────────────────────────────────────────────────────────────────────
def test_senza_schede_aperte_non_esiste_nessun_legame(db_session, admin, allievo):
    """Il ruolo da solo non lega nessuno a nessuno."""
    istruttore = _istruttore(admin)
    _scheda(allievo)

    assert istruttori_di(allievo.id) == []
    assert allievi_di(istruttore.id) == []


def test_i_miei_istruttori_elenca_le_schede_che_ciascuno_legge(
    db_session, admin, allievo
):
    prima = _scheda(allievo, "Tecnica di base")
    seconda = _scheda(allievo, "Prima della gara")
    luca = _istruttore(admin)
    giada = _istruttore(admin)
    TrainingSheetService.add_reader(prima.id, luca.id, allievo)
    TrainingSheetService.add_reader(seconda.id, luca.id, allievo)
    TrainingSheetService.add_reader(prima.id, giada.id, allievo)

    elenco = {riga.persona.id: riga for riga in istruttori_di(allievo.id)}

    assert set(elenco) == {luca.id, giada.id}
    assert [s.name for s in elenco[luca.id].schede] == [
        "Tecnica di base",
        "Prima della gara",
    ]
    assert [s.name for s in elenco[giada.id].schede] == ["Tecnica di base"]


def test_i_miei_allievi_e_la_stessa_tabella_letta_dall_altra_parte(
    db_session, admin, allievo
):
    scheda = _scheda(allievo)
    altro_allievo = _user()
    sua = _scheda(altro_allievo, "Tre giorni a settimana")
    luca = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, luca.id, allievo)
    TrainingSheetService.add_reader(sua.id, luca.id, altro_allievo)

    elenco = {riga.persona.id: riga for riga in allievi_di(luca.id)}

    assert set(elenco) == {allievo.id, altro_allievo.id}
    assert [s.name for s in elenco[altro_allievo.id].schede] == [
        "Tre giorni a settimana"
    ]


def test_un_istruttore_tolto_sparisce_da_entrambe_le_viste(db_session, admin, allievo):
    """Tolto dall'ultima scheda, il legame non c'è più: non è un elenco a parte."""
    scheda = _scheda(allievo)
    luca = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, luca.id, allievo)
    TrainingSheetService.remove_reader(scheda.id, luca.id, allievo)

    assert istruttori_di(allievo.id) == []
    assert allievi_di(luca.id) == []


def test_una_scheda_archiviata_non_lega_piu_nessuno(db_session, admin, allievo):
    """Archiviare toglie la scheda dall'elenco: e con lei il legame che portava."""
    scheda = _scheda(allievo)
    luca = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, luca.id, allievo)

    TrainingSheetService.archive_sheet(scheda.id, allievo)

    assert allievi_di(luca.id) == []
    assert istruttori_di(allievo.id) == []
