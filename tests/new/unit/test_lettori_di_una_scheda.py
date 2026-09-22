"""Che cosa vede davvero chi legge una scheda (ADR-069, fase 8b).

L'ADR dice *chi* può leggere; questo file dice *fin dove*. Tre confini:

* **la seduta si apre**, perché un registro le cui righe rispondono 404 non è
  un permesso di lettura. Il lettore la vede senza poterci scrivere;
* **le note della seduta no**, a meno che il proprietario non le condivida:
  sono il posto dove si scrive «oggi malissimo, braccio rigido», e aprirle per
  default trasformerebbe un diario in un rapportino;
* **la ricerca trova solo istruttori**, e non ripropone chi la scheda già la
  legge.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db
from models.challenge.models import Challenge
from models.exceptions import PermissionDeniedError
from models.istruttore import cerca_istruttori
from models.training_sheet import (
    SheetItemSpec,
    SheetMeasure,
    TrainingSessionService,
    TrainingSheetService,
)
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService


def _user(role: str = UserRole.PLAYER.value, **kwargs) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"let_{uid}", email=f"let_{uid}@test.local", role=role, **kwargs
    )
    user.set_password("p")
    db.session.add(user)
    db.session.flush()
    return user


def _istruttore(admin: User, **kwargs) -> User:
    user = _user(**kwargs)
    RoleGrantService.grant(user.id, GrantableRole.INSTRUCTOR, admin)
    return user


def _scheda(owner: User):
    challenge = Challenge(
        title=f"Esercizio {uuid.uuid4().hex[:6]}",
        description="istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=True,  # «riusciti» vuole un esito netto (ADR-072)
    )
    db.session.add(challenge)
    db.session.flush()
    scheda = TrainingSheetService.create_sheet(owner, "Tecnica di base")
    TrainingSheetService.save_composition(
        scheda.id,
        owner,
        name="Tecnica di base",
        items=[
            SheetItemSpec(
                challenge_id=challenge.id, measure=SheetMeasure.MADE, amount=5
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
# Le note
# ────────────────────────────────────────────────────────────────────────────
def test_le_note_restano_del_proprietario(db_session, admin, allievo):
    scheda = _scheda(allievo)
    istruttore = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)

    assert scheda.readers_see_notes is False
    assert TrainingSheetService.can_read_notes(scheda, istruttore) is False
    assert TrainingSheetService.can_read_notes(scheda, allievo) is True


def test_il_proprietario_puo_aprirle(db_session, admin, allievo):
    scheda = _scheda(allievo)
    istruttore = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)

    TrainingSheetService.set_notes_shared(scheda.id, allievo, True)

    assert TrainingSheetService.can_read_notes(scheda, istruttore) is True


def test_chi_legge_non_decide_di_leggere_le_note(db_session, admin, allievo):
    scheda = _scheda(allievo)
    istruttore = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)

    with pytest.raises(PermissionDeniedError):
        TrainingSheetService.set_notes_shared(scheda.id, istruttore, True)


def test_un_estraneo_non_legge_le_note_nemmeno_condivise(db_session, admin, allievo):
    """La condivisione allarga ai lettori, non a chiunque."""
    scheda = _scheda(allievo)
    TrainingSheetService.set_notes_shared(scheda.id, allievo, True)

    assert TrainingSheetService.can_read_notes(scheda, _user()) is False


# ────────────────────────────────────────────────────────────────────────────
# La seduta vista da chi legge
# ────────────────────────────────────────────────────────────────────────────
def test_chi_legge_apre_una_seduta_dell_allievo(db_session, admin, allievo):
    """Un registro le cui righe rispondono 404 non è un permesso di lettura."""
    scheda = _scheda(allievo)
    istruttore = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    seduta = TrainingSessionService.start(scheda.id, allievo)

    assert TrainingSessionService.can_read(seduta, istruttore) is True
    assert TrainingSessionService.can_read(seduta, _user()) is False


def test_chi_legge_non_scrive_nella_seduta(db_session, admin, allievo):
    scheda = _scheda(allievo)
    istruttore = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    seduta = TrainingSessionService.start(scheda.id, allievo)
    voce = scheda.active_items[0]

    with pytest.raises(PermissionDeniedError):
        TrainingSessionService.record(seduta.id, voce.id, istruttore, value=3)


# ────────────────────────────────────────────────────────────────────────────
# La ricerca
# ────────────────────────────────────────────────────────────────────────────
def test_la_ricerca_trova_solo_istruttori(db_session, admin):
    istruttore = _istruttore(admin, organization="Rōnin ASD")
    nome = istruttore.username
    non_insegna = _user()  # stesso prefisso nel nome, ma senza il ruolo
    non_insegna.username = f"{nome}_copia"
    db_session.flush()

    trovati = cerca_istruttori(nome[:6])

    assert [u.id for u in trovati] == [istruttore.id]


def test_la_ricerca_guarda_anche_la_scuola(db_session, admin):
    istruttore = _istruttore(admin, organization="Rōnin ASD")
    db_session.flush()

    assert istruttore.id in [u.id for u in cerca_istruttori("rōnin")]


def test_chi_legge_gia_non_si_ripropone(db_session, admin, allievo):
    scheda = _scheda(allievo)
    istruttore = _istruttore(admin)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)

    trovati = cerca_istruttori(istruttore.username[:6], escludi={istruttore.id})

    assert trovati == []


def test_una_ricerca_vuota_non_elenca_tutti(db_session, admin):
    """Senza una domanda non c'è una risposta: l'elenco degli istruttori
    della piattaforma non è una pagina che si apre per sbaglio."""
    _istruttore(admin)
    db_session.flush()

    assert cerca_istruttori("") == []
    assert cerca_istruttori("  ") == []
