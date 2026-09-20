"""Chi sancisce il passaggio di livello, e quando (D8, ADR-071).

La fase 6 aveva lasciato aperta una domanda sola — chi dice che hai passato il
livello? — e la 8c l'aveva **mostrata** senza chiuderla. Qui si chiude, con tre
risposte che non sono l'una il ripiego dell'altra:

* `none` — la scheda non è fatta a livelli, e non c'è niente da passare;
* `auto` — lo sancisce la soglia, alla seduta in cui viene tenuta. È la
  risposta di chi si allena da solo: senza, il suo gradino non lo timbrerebbe
  mai nessuno;
* `instructor` — lo conferma una persona, fra quelle che leggono la scheda.

E una frase che vale per tutte e tre: **superato è un fatto**, non uno stato
che va e viene. Timbrato, resta timbrato anche se la seduta dopo va male.
"""

from __future__ import annotations

import uuid

import pytest

from models.base import db, utc_now
from models.challenge.models import Challenge
from models.exceptions import ConflictError, PermissionDeniedError
from models.training_sheet import (
    LevelUp,
    SheetItemSpec,
    SheetMeasure,
    TrainingSheetService,
)
from models.training_sheet.gradino import GradinoService, gradino_raggiunto
from models.training_sheet.models import TrainingSheet
from models.training_sheet.session_service import TrainingSessionService
from models.user.models import User
from models.user.role_enum import GrantableRole, UserRole
from models.user.role_grant_service import RoleGrantService

ISTRUTTORE = GrantableRole.INSTRUCTOR


def _user(role: str = UserRole.PLAYER.value) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(username=f"grd_{uid}", email=f"grd_{uid}@test.local", role=role)
    user.set_password("pwd12345")
    db.session.add(user)
    db.session.flush()
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


def _scheda(
    proprietario: User,
    *,
    level_up: LevelUp = LevelUp.AUTO,
    livello: int = 3,
    soglia: int = 4,
    di_fila: int = 1,
) -> TrainingSheet:
    """Una scheda «al 4 su 5», col suo gradino."""
    scheda = TrainingSheetService.create_sheet(proprietario, "Tecnica")
    TrainingSheetService.save_composition(
        scheda.id,
        proprietario,
        name="Tecnica",
        items=[
            SheetItemSpec(
                challenge_id=_challenge().id, measure=SheetMeasure.MADE, amount=5
            )
        ],
        level=livello,
        threshold=soglia,
        threshold_streak=di_fila,
        level_up=level_up,
    )
    return scheda


def _seduta(scheda: TrainingSheet, giocatore: User, quanti: int) -> None:
    """Una seduta chiusa con `quanti` riusciti sull'unica voce."""
    seduta = TrainingSessionService.start(scheda.id, giocatore)
    TrainingSessionService.record(
        seduta.id, scheda.active_items[0].id, giocatore, value=quanti
    )
    TrainingSessionService.close(seduta.id, giocatore)


@pytest.fixture
def admin(db_session) -> User:
    return _user(UserRole.ADMIN.value)


# ── alla soglia ─────────────────────────────────────────────────────────────


def test_con_auto_la_soglia_timbra_da_sola(db_session):
    giocatore = _user()
    scheda = _scheda(giocatore, level_up=LevelUp.AUTO)

    _seduta(scheda, giocatore, 4)

    assert scheda.is_passed
    assert scheda.passed_by_id is None


def test_sotto_la_soglia_non_timbra_niente(db_session):
    giocatore = _user()
    scheda = _scheda(giocatore, level_up=LevelUp.AUTO)

    _seduta(scheda, giocatore, 3)

    assert not scheda.is_passed


def test_con_due_sedute_di_fila_la_prima_non_basta(db_session):
    giocatore = _user()
    scheda = _scheda(giocatore, level_up=LevelUp.AUTO, di_fila=2)

    _seduta(scheda, giocatore, 5)
    assert not scheda.is_passed

    _seduta(scheda, giocatore, 4)
    assert scheda.is_passed


def test_superato_resta_superato(db_session):
    """Un attestato, non un termometro: la seduta storta dopo non lo toglie."""
    giocatore = _user()
    scheda = _scheda(giocatore, level_up=LevelUp.AUTO)
    _seduta(scheda, giocatore, 5)
    quando = scheda.passed_at

    _seduta(scheda, giocatore, 0)

    assert scheda.is_passed
    assert scheda.passed_at == quando


def test_senza_livelli_non_si_passa_niente(db_session):
    giocatore = _user()
    scheda = _scheda(giocatore, level_up=LevelUp.NONE)

    _seduta(scheda, giocatore, 5)

    assert not scheda.is_passed


def test_una_scheda_che_aspetta_una_persona_non_si_timbra_da_sola(db_session):
    giocatore = _user()
    scheda = _scheda(giocatore, level_up=LevelUp.INSTRUCTOR)

    _seduta(scheda, giocatore, 5)

    assert not scheda.is_passed
    assert gradino_raggiunto(scheda)


# ── la conferma di una persona ──────────────────────────────────────────────


def _istruttore_che_legge(admin: User, scheda: TrainingSheet, allievo: User) -> User:
    istruttore = _user()
    RoleGrantService.grant(istruttore.id, ISTRUTTORE, admin)
    TrainingSheetService.add_reader(scheda.id, istruttore.id, allievo)
    return istruttore


def test_l_istruttore_conferma_il_gradino(admin):
    allievo = _user()
    scheda = _scheda(allievo, level_up=LevelUp.INSTRUCTOR)
    istruttore = _istruttore_che_legge(admin, scheda, allievo)
    _seduta(scheda, allievo, 5)

    GradinoService.conferma(scheda.id, istruttore)

    assert scheda.is_passed
    assert scheda.passed_by_id == istruttore.id


def test_non_conferma_chi_non_legge_la_scheda(admin):
    allievo = _user()
    scheda = _scheda(allievo, level_up=LevelUp.INSTRUCTOR)
    _istruttore_che_legge(admin, scheda, allievo)
    estraneo = _user()
    RoleGrantService.grant(estraneo.id, ISTRUTTORE, admin)
    _seduta(scheda, allievo, 5)

    with pytest.raises(PermissionDeniedError):
        GradinoService.conferma(scheda.id, estraneo)


def test_non_si_promuove_chi_non_e_arrivato(admin):
    """Il gradino è un fatto: nemmeno l'istruttore lo inventa."""
    allievo = _user()
    scheda = _scheda(allievo, level_up=LevelUp.INSTRUCTOR)
    istruttore = _istruttore_che_legge(admin, scheda, allievo)
    _seduta(scheda, allievo, 2)

    with pytest.raises(ConflictError):
        GradinoService.conferma(scheda.id, istruttore)


def test_su_una_scheda_auto_non_c_e_niente_da_confermare(admin):
    allievo = _user()
    scheda = _scheda(allievo, level_up=LevelUp.AUTO)
    istruttore = _istruttore_che_legge(admin, scheda, allievo)
    scheda.passed_at = None  # la seduta non c'è ancora stata

    with pytest.raises(ConflictError):
        GradinoService.conferma(scheda.id, istruttore)


def test_non_si_conferma_due_volte(admin):
    allievo = _user()
    scheda = _scheda(allievo, level_up=LevelUp.INSTRUCTOR)
    istruttore = _istruttore_che_legge(admin, scheda, allievo)
    _seduta(scheda, allievo, 5)
    GradinoService.conferma(scheda.id, istruttore)

    with pytest.raises(ConflictError):
        GradinoService.conferma(scheda.id, istruttore)


def test_l_allievo_riceve_l_avviso_del_passaggio(admin):
    from models.notification.models import Notification

    allievo = _user()
    scheda = _scheda(allievo, level_up=LevelUp.INSTRUCTOR)
    istruttore = _istruttore_che_legge(admin, scheda, allievo)
    _seduta(scheda, allievo, 5)
    prima = Notification.query.filter_by(user_id=allievo.id).count()

    GradinoService.conferma(scheda.id, istruttore)

    assert Notification.query.filter_by(user_id=allievo.id).count() == prima + 1


# ── senza livello, «chi sancisce» non ha senso ──────────────────────────────


def test_togliere_il_livello_spegne_anche_il_sancitore(db_session):
    giocatore = _user()
    scheda = _scheda(giocatore, level_up=LevelUp.INSTRUCTOR)

    TrainingSheetService.save_composition(
        scheda.id,
        giocatore,
        name="Tecnica",
        items=[
            SheetItemSpec(
                challenge_id=scheda.active_items[0].challenge_id,
                measure=SheetMeasure.MADE,
                amount=5,
                item_id=scheda.active_items[0].id,
            )
        ],
        level=None,
        threshold=4,
        level_up=LevelUp.INSTRUCTOR,
    )

    assert scheda.level_up_kind is LevelUp.NONE


def test_il_timbro_sopravvive_a_una_seduta_annullata(db_session):
    """Il gradino discende dalla seduta: senza la seduta non deve restare."""
    giocatore = _user()
    scheda = _scheda(giocatore, level_up=LevelUp.AUTO)
    seduta = TrainingSessionService.start(scheda.id, giocatore)
    TrainingSessionService.record(
        seduta.id, scheda.active_items[0].id, giocatore, value=5
    )
    assert not scheda.is_passed  # finché è aperta, niente

    TrainingSessionService.close(seduta.id, giocatore)
    assert scheda.is_passed
    assert scheda.passed_at is not None and scheda.passed_at <= utc_now()
