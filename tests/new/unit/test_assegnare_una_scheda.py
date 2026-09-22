"""Proporre una scheda a un allievo, e prenderla (fase 8d).

La frase che questi test difendono è quella dell'ADR-069 vista dal lato
dell'istruttore: **dare una scheda non è un modo per ottenere l'accesso**. Da
lì discende tutto ciò che c'è qui sotto.

* Si propone **solo a chi ti è già allievo**: la prima mossa resta dell'altro,
  sempre. Un istruttore non può scrivere per primo a un ragazzo di quattordici
  anni che non lo conosce.
* La scheda **nasce quando l'allievo accetta**, e nasce **sua**: proprietario
  lui, e da quel momento la cambia, la archivia, la dà a chi vuole.
* Il permesso di lettura è **un atto suo**, spedito nello stesso modulo ma
  separato: rifiutarlo lascia la scheda e toglie l'istruttore.
* Una proposta in attesa per volta, per coppia (istruttore, allievo), e a
  imporlo è il database — non un `if`.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from models.istruttore import AssegnazioneService
from models.istruttore.models import EsitoProposta, TrainingAssignment
from models.training_sheet import SheetItemSpec, SheetMeasure, TrainingSheetService
from models.training_sheet.models import TrainingSheet
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

ISTRUTTORE = GrantableRole.INSTRUCTOR


# ── allestimento ────────────────────────────────────────────────────────────


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"asg_{uid}", email=f"asg_{uid}@test.local", role=role)
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


def _scheda(proprietario: User, nome: str = "Tecnica", voci: int = 2) -> TrainingSheet:
    """Una scheda composta, con `voci` esercizi «a riusciti» da 5 tiri."""
    scheda = TrainingSheetService.create_sheet(proprietario, nome)
    TrainingSheetService.save_composition(
        scheda.id,
        proprietario,
        name=nome,
        items=[
            SheetItemSpec(
                challenge_id=_challenge().id,
                measure=SheetMeasure.MADE,
                amount=5,
                section="Riscaldamento" if indice == 0 else None,
            )
            for indice in range(voci)
        ],
    )
    return scheda


def _allievo_di(istruttore: User) -> User:
    """Un giocatore che ha aperto una sua scheda a questo istruttore."""
    allievo = _user()
    scheda = _scheda(allievo, "La mia")
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    return allievo


@pytest.fixture
def admin(db_session) -> User:
    return _user(UserRole.ADMIN.value)


# ── chi può proporre, e a chi ───────────────────────────────────────────────


def test_si_propone_solo_a_chi_ti_e_gia_allievo(admin):
    """La prima mossa resta dell'allievo: senza scheda aperta, non si propone."""
    istruttore = _istruttore(admin)
    estraneo = _user()
    modello = _scheda(istruttore, "Tecnica di base")

    with pytest.raises(ConflictError):
        AssegnazioneService.proponi(istruttore, modello.id, [estraneo.id])


def test_chi_non_e_istruttore_non_propone(admin):
    giocatore = _user()
    altro = _user()
    modello = _scheda(giocatore, "Tecnica di base")

    with pytest.raises(PermissionDeniedError):
        AssegnazioneService.proponi(giocatore, modello.id, [altro.id])


def test_si_propone_una_scheda_tua(admin):
    """La scheda di un allievo non si gira a un altro allievo."""
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    sua = _scheda(_user(), "Di qualcun altro")

    with pytest.raises(PermissionDeniedError):
        AssegnazioneService.proponi(istruttore, sua.id, [allievo.id])


def test_una_scheda_senza_voci_non_si_propone(admin):
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    vuota = TrainingSheetService.create_sheet(istruttore, "Ancora niente")

    with pytest.raises(ConflictError):
        AssegnazioneService.proponi(istruttore, vuota.id, [allievo.id])


def test_una_proposta_aperta_per_volta(admin):
    """Il secondo invito non nasce: chi è già in attesa viene saltato."""
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    modello = _scheda(istruttore, "Tecnica di base")

    prime = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])
    seconde = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])

    assert len(prime) == 1
    assert seconde == []


def test_due_istruttori_possono_proporre_insieme(admin):
    """Il limite è per coppia, non per allievo: due maestri, due proposte."""
    uno, due = _istruttore(admin), _istruttore(admin)
    allievo = _user()
    for istruttore in (uno, due):
        scheda = _scheda(allievo, f"Per {istruttore.username}")
        TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)

    assert AssegnazioneService.proponi(uno, _scheda(uno, "A").id, [allievo.id])
    assert AssegnazioneService.proponi(due, _scheda(due, "B").id, [allievo.id])
    assert len(AssegnazioneService.proposte_per(allievo.id)) == 2


# ── prenderla ───────────────────────────────────────────────────────────────


def test_accettare_fa_nascere_una_scheda_dell_allievo(admin):
    """La copia è sua: proprietario lui, e la compone lui."""
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    modello = _scheda(istruttore, "Tecnica di base", voci=3)
    modello.level, modello.threshold, modello.threshold_streak = 3, 10, 2
    db.session.flush()

    proposta = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])[0]
    nata = AssegnazioneService.accetta(proposta.id, allievo, apri_lettura=False)

    assert nata.owner_id == allievo.id
    assert nata.id != modello.id
    assert nata.name == modello.name
    assert (nata.level, nata.threshold, nata.threshold_streak) == (3, 10, 2)
    assert len(nata.active_items) == 3
    assert [v.measure for v in nata.active_items] == [v.measure for v in modello.items]
    assert [v.amount for v in nata.active_items] == [v.amount for v in modello.items]
    assert nata.active_items[0].section == "Riscaldamento"
    assert TrainingSheetService.can_edit(nata, allievo)
    assert not TrainingSheetService.can_edit(nata, istruttore)


def test_la_lettura_e_un_atto_dell_allievo(admin):
    """Spuntata o no, il permesso nasce dal suo gesto — e senza, non c'è."""
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    modello = _scheda(istruttore, "Tecnica di base")

    senza = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])[0]
    nata = AssegnazioneService.accetta(senza.id, allievo, apri_lettura=False)
    assert not TrainingSheetService.can_read(nata, istruttore)

    con = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])[0]
    seconda = AssegnazioneService.accetta(con.id, allievo, apri_lettura=True)
    assert TrainingSheetService.can_read(seconda, istruttore)


def test_le_note_restano_chiuse_anche_nella_copia(admin):
    """La scelta sulle note è di chi la possiede: non si eredita dal modello."""
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    modello = _scheda(istruttore, "Tecnica di base")
    TrainingSheetService.set_notes_shared(modello.id, istruttore, True)

    proposta = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])[0]
    nata = AssegnazioneService.accetta(proposta.id, allievo, apri_lettura=True)

    assert nata.readers_see_notes is False
    assert not TrainingSheetService.can_read_notes(nata, istruttore)


def test_accetta_solo_il_destinatario(admin):
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    passante = _user()
    modello = _scheda(istruttore, "Tecnica di base")
    proposta = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])[0]

    with pytest.raises(NotFoundError):
        AssegnazioneService.accetta(proposta.id, passante, apri_lettura=False)


def test_una_proposta_si_chiude_una_volta_sola(admin):
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    modello = _scheda(istruttore, "Tecnica di base")
    proposta = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])[0]

    AssegnazioneService.accetta(proposta.id, allievo, apri_lettura=False)
    with pytest.raises(ConflictError):
        AssegnazioneService.rifiuta(proposta.id, allievo)


def test_il_modello_che_cambia_dopo_non_tocca_la_copia(admin):
    """Presa la scheda, è sua: l'istruttore non la riscrive a distanza."""
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    modello = _scheda(istruttore, "Tecnica di base", voci=2)
    proposta = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])[0]
    nata = AssegnazioneService.accetta(proposta.id, allievo, apri_lettura=True)

    TrainingSheetService.save_composition(
        modello.id,
        istruttore,
        name="Tecnica di base v2",
        items=[
            SheetItemSpec(
                challenge_id=_challenge().id, measure=SheetMeasure.MADE, amount=5
            )
        ],
    )

    assert len(nata.active_items) == 2
    assert nata.name == "Tecnica di base"


def test_un_gesto_solo_manda_un_avviso_solo(admin):
    """Prendere una scheda **e** aprirla è un gesto: l'istruttore riceve uno.

    Senza `avvisa=False`, `add_reader` ne manderebbe un secondo — «un allievo
    ti ha aperto una scheda» — che racconta metà della stessa cosa.
    """
    from models.notification.models import Notification

    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    modello = _scheda(istruttore, "Tecnica di base")
    prima = Notification.query.filter_by(user_id=istruttore.id).count()

    proposta = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])[0]
    AssegnazioneService.accetta(proposta.id, allievo, apri_lettura=True)

    nuove = (
        Notification.query.filter_by(user_id=istruttore.id)
        .order_by(Notification.id.desc())
        .limit(2)
        .all()
    )
    assert Notification.query.filter_by(user_id=istruttore.id).count() == prima + 1
    assert "fa leggere" in str(nuove[0].message)


# ── dire di no, e ritirare ──────────────────────────────────────────────────


def test_rifiutare_non_lascia_niente(admin):
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    modello = _scheda(istruttore, "Tecnica di base")
    quante = len(TrainingSheetService.sheets_of(allievo.id))

    proposta = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])[0]
    AssegnazioneService.rifiuta(proposta.id, allievo)

    assert proposta.outcome == EsitoProposta.DECLINED.value
    assert proposta.sheet_id is None
    assert len(TrainingSheetService.sheets_of(allievo.id)) == quante
    assert AssegnazioneService.proposte_per(allievo.id) == []


def test_l_istruttore_ritira_la_sua_proposta(admin):
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    modello = _scheda(istruttore, "Tecnica di base")
    proposta = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])[0]

    AssegnazioneService.ritira(proposta.id, istruttore)

    assert proposta.outcome == EsitoProposta.WITHDRAWN.value
    assert AssegnazioneService.proposte_per(allievo.id) == []
    # Ritirata quella, se ne può fare un'altra: l'indice guarda le aperte.
    assert AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])


def test_l_allievo_non_ritira_la_proposta_di_un_altro(admin):
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    modello = _scheda(istruttore, "Tecnica di base")
    proposta = AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])[0]

    with pytest.raises(NotFoundError):
        AssegnazioneService.ritira(proposta.id, allievo)


# ── ciò che la proposta NON fa ──────────────────────────────────────────────


def test_proporre_non_apre_niente(admin):
    """Finché non accetta, l'istruttore non ha guadagnato una sola lettura."""
    istruttore = _istruttore(admin)
    allievo = _allievo_di(istruttore)
    modello = _scheda(istruttore, "Tecnica di base")

    AssegnazioneService.proponi(istruttore, modello.id, [allievo.id])

    assert (
        TrainingAssignment.query.filter_by(user_id=allievo.id).first().sheet_id is None
    )
    schede = TrainingSheetService.sheets_of(allievo.id)
    assert all(s.name != "Tecnica di base" for s in schede)
