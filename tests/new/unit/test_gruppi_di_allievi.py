"""I gruppi di allievi dell'istruttore, con il loro storico (D12, fase 8c).

La frase che questi test difendono è una sola, ed è dell'ADR-069: **un gruppo
non è un modo per ottenere l'accesso, è un modo per ordinare chi te l'ha già
dato**. Da lì discende tutto il resto:

* ci si mette solo chi ti ha aperto una scheda, e il controllo sta nel
  servizio — non nell'elenco da cui si sceglie;
* un allievo sta in un gruppo solo per volta, e «sposta» è la stessa mossa di
  «aggiungi»;
* chiudere un corso fa uscire chi c'era, con la data: senza, l'indice unico
  impedirebbe di iscriverlo al corso dell'anno dopo;
* se l'allievo ti richiude la scheda, la **riga del gruppo resta** (è storia)
  ma non vedi più niente di nuovo. Le due cose non si parlano mai.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge
from models.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from models.istruttore import GruppoService, allievi_di
from models.istruttore.models import TrainingGroupMember
from models.training_sheet import SheetItemSpec, SheetMeasure, TrainingSheetService
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

ISTRUTTORE = GrantableRole.INSTRUCTOR


# ── allestimento ────────────────────────────────────────────────────────────


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"grp_{uid}", email=f"grp_{uid}@test.local", role=role)
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.flush()
    return user


def _istruttore(admin: User) -> User:
    user = _user()
    RoleGrantService.grant(user.id, ISTRUTTORE, admin)
    return user


def _challenge() -> Challenge:
    challenge = Challenge(
        title=f"Esercizio {uuid.uuid4().hex[:6]}",
        description="istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=True,  # «riusciti» vuole un esito netto (ADR-072)
    )
    db.session.add(challenge)
    db.session.flush()
    return challenge


def _scheda_aperta_a(allievo: User, istruttore: User, nome: str = "Tecnica"):
    """Una scheda dell'allievo, con l'istruttore fra i lettori."""
    scheda = TrainingSheetService.create_sheet(allievo, nome)
    TrainingSheetService.save_composition(
        scheda.id,
        allievo,
        name=nome,
        items=[
            SheetItemSpec(
                challenge_id=_challenge().id, measure=SheetMeasure.MADE, amount=5
            )
        ],
    )
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    return scheda


@pytest.fixture
def admin(db_session):
    return _user(UserRole.ADMIN.value)


@pytest.fixture
def luca(db_session, admin):
    """L'istruttore."""
    return _istruttore(admin)


@pytest.fixture
def paolo(db_session):
    """Un allievo che ha aperto una scheda."""
    return _user()


# ── chi può fare un gruppo ──────────────────────────────────────────────────


def test_solo_un_istruttore_crea_un_gruppo(db_session, admin):
    chiunque = _user()
    with pytest.raises(PermissionDeniedError):
        GruppoService.crea(chiunque, "Base 1")


def test_nemmeno_l_amministratore(db_session, admin):
    """`is_instructor` non è vero d'ufficio per l'admin (ADR-069 §1)."""
    with pytest.raises(PermissionDeniedError):
        GruppoService.crea(admin, "Base 1")


def test_un_gruppo_nasce_in_corso(db_session, luca):
    gruppo = GruppoService.crea(luca, "Base 1 · autunno 2026")
    assert gruppo.is_open
    assert gruppo.closed_at is None


def test_un_corso_col_calendario_fino_a_dicembre_e_in_corso(db_session, luca, paolo):
    """La data di fine è una previsione, non lo stato: «dal 15/09 al 15/12»."""
    _scheda_aperta_a(paolo, luca)
    oggi = utc_now().date()
    gruppo = GruppoService.crea(
        luca, "Base 1 · autunno", oggi - timedelta(days=5), oggi + timedelta(days=86)
    )

    assert gruppo.is_open
    assert GruppoService.gruppi_di(luca.id, aperti=True) == [gruppo]
    # E ci si possono mettere allievi: il caso che il primo modello sbagliava.
    GruppoService.aggiungi(gruppo.id, luca, paolo.id)
    assert [m.user_id for m in gruppo.active_members] == [paolo.id]


def test_cambiare_il_calendario_non_chiude_niente(db_session, luca):
    gruppo = GruppoService.crea(luca, "Base 1")
    oggi = utc_now().date()

    GruppoService.aggiorna(
        gruppo.id, luca, nome="Base 1", dal=oggi, al=oggi + timedelta(days=90)
    )

    assert gruppo.is_open


def test_chiudere_prima_del_tempo_sposta_la_data_a_oggi(db_session, luca):
    """Nello storico non deve comparire una fine che non è mai avvenuta."""
    oggi = utc_now().date()
    gruppo = GruppoService.crea(luca, "Base 1", oggi, oggi + timedelta(days=90))

    GruppoService.chiudi(gruppo.id, luca)

    assert gruppo.ended_on == oggi


def test_chiudere_in_ritardo_tiene_la_data_vera(db_session, luca):
    oggi = utc_now().date()
    finito = oggi - timedelta(days=10)
    gruppo = GruppoService.crea(luca, "Base 1", oggi - timedelta(days=100), finito)

    GruppoService.chiudi(gruppo.id, luca)

    assert gruppo.ended_on == finito


def test_il_gruppo_vuole_un_nome(db_session, luca):
    with pytest.raises(ConflictError):
        GruppoService.crea(luca, "   ")


def test_il_corso_non_finisce_prima_di_cominciare(db_session, luca):
    with pytest.raises(ConflictError):
        GruppoService.crea(luca, "Base 1", date(2026, 12, 15), date(2026, 9, 15))


def test_i_gruppi_di_un_altro_istruttore_non_esistono(db_session, admin, luca):
    altro = _istruttore(admin)
    gruppo = GruppoService.crea(altro, "Intermedio")
    with pytest.raises(NotFoundError):
        GruppoService.aggiorna(gruppo.id, luca, nome="Mio")


# ── chi ci si può mettere ───────────────────────────────────────────────────


def test_ci_si_mette_solo_chi_ti_ha_aperto_una_scheda(db_session, luca, paolo):
    """Il gruppo ordina chi ti ha già dato accesso, non lo chiede."""
    gruppo = GruppoService.crea(luca, "Base 1")
    with pytest.raises(ConflictError):
        GruppoService.aggiungi(gruppo.id, luca, paolo.id)


def test_chi_ha_aperto_una_scheda_ci_entra(db_session, luca, paolo):
    _scheda_aperta_a(paolo, luca)
    gruppo = GruppoService.crea(luca, "Base 1")

    membro = GruppoService.aggiungi(gruppo.id, luca, paolo.id)

    assert membro.user_id == paolo.id
    assert membro.is_current
    assert [m.user_id for m in gruppo.active_members] == [paolo.id]


def test_mettere_in_un_gruppo_non_apre_nessuna_scheda(db_session, luca, paolo):
    """La prova che le due tabelle non si parlano: il permesso non cambia."""
    scheda = _scheda_aperta_a(paolo, luca)
    gruppo = GruppoService.crea(luca, "Base 1")
    GruppoService.aggiungi(gruppo.id, luca, paolo.id)

    altra = TrainingSheetService.create_sheet(paolo, "Un'altra")
    assert not TrainingSheetService.can_read(altra, luca)
    assert TrainingSheetService.can_read(scheda, luca)


def test_aggiungerlo_due_volte_non_fa_niente(db_session, luca, paolo):
    _scheda_aperta_a(paolo, luca)
    gruppo = GruppoService.crea(luca, "Base 1")

    primo = GruppoService.aggiungi(gruppo.id, luca, paolo.id)
    secondo = GruppoService.aggiungi(gruppo.id, luca, paolo.id)

    assert primo.id == secondo.id
    assert len(gruppo.active_members) == 1


# ── un gruppo solo per volta ────────────────────────────────────────────────


def test_un_allievo_sta_in_un_gruppo_solo(db_session, luca, paolo):
    """«Sposta» non è un comando a parte: aggiungere toglie dall'altro."""
    _scheda_aperta_a(paolo, luca)
    base = GruppoService.crea(luca, "Base 1")
    intermedio = GruppoService.crea(luca, "Intermedio 1")

    GruppoService.aggiungi(base.id, luca, paolo.id)
    GruppoService.aggiungi(intermedio.id, luca, paolo.id)

    assert [m.user_id for m in base.active_members] == []
    assert [m.user_id for m in intermedio.active_members] == [paolo.id]
    # La riga di prima resta, e dice fin quando c'era.
    vecchia = GruppoService.membri_passati(base)
    assert len(vecchia) == 1
    assert vecchia[0].left_at is not None


def test_due_istruttori_diversi_possono_averlo_entrambi(db_session, admin, luca, paolo):
    """Il vincolo è per istruttore: due scuole non si ostacolano."""
    altro = _istruttore(admin)
    _scheda_aperta_a(paolo, luca, "Con Luca")
    _scheda_aperta_a(paolo, altro, "Con l'altro")

    suo = GruppoService.crea(luca, "Base 1")
    altrui = GruppoService.crea(altro, "Corso serale")
    GruppoService.aggiungi(suo.id, luca, paolo.id)
    GruppoService.aggiungi(altrui.id, altro, paolo.id)

    assert [m.user_id for m in suo.active_members] == [paolo.id]
    assert [m.user_id for m in altrui.active_members] == [paolo.id]


def test_toglierlo_lo_fa_uscire_e_la_riga_resta(db_session, luca, paolo):
    _scheda_aperta_a(paolo, luca)
    gruppo = GruppoService.crea(luca, "Base 1")
    GruppoService.aggiungi(gruppo.id, luca, paolo.id)

    GruppoService.togli(gruppo.id, luca, paolo.id)

    assert gruppo.active_members == []
    assert len(gruppo.members) == 1
    assert gruppo.members[0].left_at is not None


def test_togliere_chi_non_c_e_non_passa_in_silenzio(db_session, luca, paolo):
    gruppo = GruppoService.crea(luca, "Base 1")
    with pytest.raises(NotFoundError):
        GruppoService.togli(gruppo.id, luca, paolo.id)


# ── chiudere un corso ───────────────────────────────────────────────────────


def test_chiudere_un_corso_fa_uscire_chi_c_era(db_session, luca, paolo):
    """E deve: senza la data d'uscita non lo si potrebbe iscrivere altrove."""
    _scheda_aperta_a(paolo, luca)
    gruppo = GruppoService.crea(luca, "Base 1 · primavera")
    GruppoService.aggiungi(gruppo.id, luca, paolo.id)

    GruppoService.chiudi(gruppo.id, luca)

    assert not gruppo.is_open
    assert gruppo.closed_at is not None
    assert gruppo.active_members == []
    assert len(gruppo.members) == 1  # la riga c'è ancora: chi c'era


def test_dopo_un_corso_chiuso_l_allievo_entra_in_quello_nuovo(db_session, luca, paolo):
    _scheda_aperta_a(paolo, luca)
    vecchio = GruppoService.crea(luca, "Base 1 · primavera")
    GruppoService.aggiungi(vecchio.id, luca, paolo.id)
    GruppoService.chiudi(vecchio.id, luca)

    nuovo = GruppoService.crea(luca, "Base 1 · autunno")
    GruppoService.aggiungi(nuovo.id, luca, paolo.id)

    assert [m.user_id for m in nuovo.active_members] == [paolo.id]


def test_in_un_gruppo_chiuso_non_si_aggiunge_nessuno(db_session, luca, paolo):
    _scheda_aperta_a(paolo, luca)
    gruppo = GruppoService.crea(luca, "Base 1")
    GruppoService.chiudi(gruppo.id, luca)

    with pytest.raises(ConflictError):
        GruppoService.aggiungi(gruppo.id, luca, paolo.id)


def test_un_gruppo_gia_chiuso_non_si_richiude(db_session, luca):
    gruppo = GruppoService.crea(luca, "Base 1")
    GruppoService.chiudi(gruppo.id, luca)
    with pytest.raises(ConflictError):
        GruppoService.chiudi(gruppo.id, luca)


def test_lo_storico_e_i_corsi_in_corso_si_leggono_a_parte(db_session, luca):
    aperto = GruppoService.crea(luca, "Base 1 · autunno", date(2026, 9, 15))
    chiuso = GruppoService.crea(luca, "Base 1 · primavera", date(2026, 3, 2))
    GruppoService.chiudi(chiuso.id, luca)

    assert [g.id for g in GruppoService.gruppi_di(luca.id, aperti=True)] == [aperto.id]
    assert [g.id for g in GruppoService.gruppi_di(luca.id, aperti=False)] == [chiuso.id]
    assert len(GruppoService.gruppi_di(luca.id)) == 2


# ── il legame resta quello delle schede ─────────────────────────────────────


def test_se_richiude_la_scheda_la_riga_del_gruppo_resta(db_session, luca, paolo):
    """La riga è storia; l'accesso no. È la conseguenza voluta dell'ADR-069."""
    scheda = _scheda_aperta_a(paolo, luca)
    gruppo = GruppoService.crea(luca, "Base 1")
    GruppoService.aggiungi(gruppo.id, luca, paolo.id)

    TrainingSheetService.remove_reader(scheda.id, luca.id, paolo)

    assert [m.user_id for m in gruppo.active_members] == [paolo.id]
    assert allievi_di(luca.id) == []
    assert not TrainingSheetService.can_read(scheda, luca)


def test_il_gruppo_non_rende_allievo_chi_non_lo_e_piu(db_session, luca, paolo):
    """Chi è uscito dal legame non si può riaggiungere: il gruppo non apre nulla."""
    scheda = _scheda_aperta_a(paolo, luca)
    gruppo = GruppoService.crea(luca, "Base 1")
    GruppoService.aggiungi(gruppo.id, luca, paolo.id)
    GruppoService.togli(gruppo.id, luca, paolo.id)
    TrainingSheetService.remove_reader(scheda.id, luca.id, paolo)

    with pytest.raises(ConflictError):
        GruppoService.aggiungi(gruppo.id, luca, paolo.id)


def test_l_indice_unico_e_nello_schema_non_in_python(db_session):
    """Un `if` applicativo è invisibile a chi scrive in blocco (UserMergeService)."""
    indici = {i.name for i in TrainingGroupMember.__table__.indexes}
    assert "uq_training_group_member_attivo" in indici
    unico = next(
        i
        for i in TrainingGroupMember.__table__.indexes
        if i.name == "uq_training_group_member_attivo"
    )
    assert unico.unique
    assert [c.name for c in unico.columns] == ["instructor_id", "user_id"]
