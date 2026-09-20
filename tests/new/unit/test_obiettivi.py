"""Gli obiettivi di allenamento: porli, misurarli, timbrarli (#316).

Le tre forme leggono **tre fonti diverse**, e ciascuna è quella giusta per la
sua domanda: un obiettivo su un esercizio guarda le prove di quell'esercizio,
uno su un'abilità guarda l'andamento (dove catalogo e schede entrano insieme,
ADR-068), la costanza conta i giorni. È la cosa che questo file difende per
prima, perché scambiarle non darebbe errore: darebbe numeri plausibili e
sbagliati.

Poi due regole che valgono per tutte e tre: un obiettivo già raggiunto non si
pone, e «raggiunto» una volta scritto non si toglie.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from models.base import utc_now
from models.challenge.models import Challenge, ChallengeAttempt
from models.challenge.profile_service import ChallengeProfileService
from models.challenge.vocabulary import Abilita, CategoryAxis
from models.exceptions import ConflictError, ValidationError
from models.obiettivo import (
    MAX_ATTIVI,
    GoalDeadline,
    GoalKind,
    GoalRule,
    TrainingGoalService,
    build_progress,
)
from models.training_sheet.measure import SheetMeasure
from models.training_sheet.models import (
    TrainingEntry,
    TrainingSession,
    TrainingSheet,
    TrainingSheetItem,
)
from models.user.models import User
from models.user.role_enum import UserRole


# ── allestimento ────────────────────────────────────────────────────────────
def _user(db_session) -> User:
    uid = uuid.uuid4().hex[:8]
    user = User(
        username=f"ob_{uid}", email=f"ob_{uid}@test.local", role=UserRole.PLAYER.value
    )
    user.set_password("p")
    db_session.add(user)
    db_session.flush()
    return user


def _challenge(db_session, titolo, *, max_score=10, pass_fail=False, abilita=()):
    challenge = Challenge(
        title=titolo,
        description=f"{titolo}: istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=pass_fail,
        max_score=max_score,
    )
    db_session.add(challenge)
    db_session.flush()
    if abilita:
        ChallengeProfileService.set_profile(
            challenge.id, abilita=[a.value for a in abilita]
        )
        db_session.flush()
    return challenge


def _prova(db_session, user, challenge, *, score=None, giorni_fa=1):
    db_session.add(
        ChallengeAttempt(
            challenge_id=challenge.id,
            user_id=user.id,
            score=score,
            completed=True,
            attempted_at=utc_now() - timedelta(days=giorni_fa),
        )
    )
    db_session.flush()


def _seduta(db_session, user, challenge, valore, quanti, *, giorni_fa=1):
    """Una scheda di una voce sola, con una seduta chiusa già compilata."""
    quando = utc_now() - timedelta(days=giorni_fa)
    sheet = TrainingSheet(name="Scheda", owner_id=user.id)
    db_session.add(sheet)
    db_session.flush()
    item = TrainingSheetItem(
        sheet_id=sheet.id,
        challenge_id=challenge.id,
        position=1,
        measure=SheetMeasure.MADE.value,
        amount=quanti,
    )
    db_session.add(item)
    db_session.flush()
    sessione = TrainingSession(
        sheet_id=sheet.id, user_id=user.id, started_at=quando, ended_at=quando
    )
    db_session.add(sessione)
    db_session.flush()
    db_session.add(
        TrainingEntry(
            session_id=sessione.id,
            item_id=item.id,
            value=valore,
            measure=SheetMeasure.MADE.value,
            target_amount=quanti,
        )
    )
    db_session.flush()
    return sessione


# ── ogni forma legge la sua fonte ───────────────────────────────────────────
def test_un_obiettivo_su_un_esercizio_guarda_solo_le_prove_di_quell_esercizio(
    db_session,
):
    """Una casella di scheda è tarata altrimenti (ADR-067): qui non entra."""
    user = _user(db_session)
    challenge = _challenge(db_session, "Spot shot", max_score=10)
    _prova(db_session, user, challenge, score=6)
    # Una seduta perfetta sullo stesso esercizio: non deve spostare la media.
    _seduta(db_session, user, challenge, 5, 5)

    goal = TrainingGoalService.create(
        user.id, GoalKind.ESERCIZIO, challenge_id=challenge.id, target=8
    )
    assert build_progress(goal).current == 6


def test_un_obiettivo_su_un_abilita_guarda_l_andamento_quindi_anche_le_schede(
    db_session,
):
    """Lì la domanda è «quanto bene tiro», e le due fonti entrano insieme."""
    user = _user(db_session)
    dal_catalogo = _challenge(db_session, "A", max_score=10, abilita=[Abilita.TIRO])
    in_scheda = _challenge(db_session, "B", max_score=None, abilita=[Abilita.TIRO])
    _prova(db_session, user, dal_catalogo, score=4)
    _seduta(db_session, user, in_scheda, 4, 5)  # 80%

    goal = TrainingGoalService.create(
        user.id,
        GoalKind.ABILITA,
        axis=CategoryAxis.ABILITA,
        axis_value=Abilita.TIRO.value,
        target=70,
    )
    assert build_progress(goal).current == 60, "media di 40% e 80%"


def test_la_costanza_conta_i_giorni_non_le_registrazioni(db_session):
    """Dieci tiri in una sera sono una volta sola."""
    user = _user(db_session)
    challenge = _challenge(db_session, "C")
    for _volta in range(5):
        _prova(db_session, user, challenge, score=5, giorni_fa=1)

    goal = TrainingGoalService.create(user.id, GoalKind.COSTANZA, per_week=2, target=4)
    assert build_progress(goal).current == 0, "un giorno solo non fa due volte"

    _prova(db_session, user, challenge, score=5, giorni_fa=2)
    assert build_progress(goal).current == 1, "due giorni nella stessa settimana"


# ── le due regole comuni ────────────────────────────────────────────────────
def test_un_obiettivo_gia_raggiunto_non_si_pone(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Facile", max_score=10)
    _prova(db_session, user, challenge, score=9)

    with pytest.raises(ValidationError):
        TrainingGoalService.create(
            user.id, GoalKind.ESERCIZIO, challenge_id=challenge.id, target=8
        )


def test_raggiunto_si_scrive_una_volta_e_non_si_toglie(db_session):
    """Il progresso può scendere; la data in cui ci si è arrivati è un fatto."""
    user = _user(db_session)
    challenge = _challenge(db_session, "Serie", max_score=10)
    _prova(db_session, user, challenge, score=5)

    goal = TrainingGoalService.create(
        user.id,
        GoalKind.ESERCIZIO,
        challenge_id=challenge.id,
        rule=GoalRule.UNA_VOLTA,
        target=8,
    )
    assert TrainingGoalService.refresh(user.id) == []

    _prova(db_session, user, challenge, score=9, giorni_fa=0)
    assert TrainingGoalService.refresh(user.id) == [goal]
    quando = goal.reached_at
    assert quando is not None

    # Un secondo giro non ritimbra, e non cancella.
    assert TrainingGoalService.refresh(user.id) == []
    assert goal.reached_at == quando
    assert not goal.is_active


def test_non_si_aprono_piu_di_tre_obiettivi(db_session):
    user = _user(db_session)
    for numero in range(MAX_ATTIVI):
        challenge = _challenge(db_session, f"E{numero}", max_score=10)
        TrainingGoalService.create(
            user.id, GoalKind.ESERCIZIO, challenge_id=challenge.id, target=8
        )

    ultimo = _challenge(db_session, "Uno di troppo", max_score=10)
    with pytest.raises(ConflictError):
        TrainingGoalService.create(
            user.id, GoalKind.ESERCIZIO, challenge_id=ultimo.id, target=8
        )


def test_lasciare_un_obiettivo_libera_il_posto(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Uno", max_score=10)
    goal = TrainingGoalService.create(
        user.id, GoalKind.ESERCIZIO, challenge_id=challenge.id, target=8
    )

    TrainingGoalService.abandon(goal.id, user.id)
    assert TrainingGoalService.active(user.id) == []
    with pytest.raises(ConflictError):
        TrainingGoalService.abandon(goal.id, user.id)


# ── che cosa si rifiuta ─────────────────────────────────────────────────────
def test_un_esercizio_superato_o_no_non_ha_un_punteggio_a_cui_arrivare(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Netto", max_score=None, pass_fail=True)

    with pytest.raises(ValidationError):
        TrainingGoalService.create(
            user.id, GoalKind.ESERCIZIO, challenge_id=challenge.id, target=8
        )


def test_il_traguardo_non_supera_il_massimo_dell_esercizio(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Da dieci", max_score=10)

    with pytest.raises(ValidationError):
        TrainingGoalService.create(
            user.id, GoalKind.ESERCIZIO, challenge_id=challenge.id, target=12
        )


@pytest.mark.parametrize("volte, settimane", [(0, 4), (99, 4), (2, 1), (2, 999)])
def test_la_costanza_vuole_numeri_sensati(db_session, volte, settimane):
    user = _user(db_session)
    with pytest.raises(ValidationError):
        TrainingGoalService.create(
            user.id, GoalKind.COSTANZA, per_week=volte, target=settimane
        )


def test_una_categoria_che_il_vocabolario_non_conosce_si_rifiuta(db_session):
    user = _user(db_session)
    with pytest.raises(ValidationError):
        TrainingGoalService.create(
            user.id,
            GoalKind.ABILITA,
            axis=CategoryAxis.ABILITA,
            axis_value="giocoleria",
            target=70,
        )


# ── la barra ────────────────────────────────────────────────────────────────
def test_la_barra_parte_da_dove_si_partiva_non_da_zero(db_session):
    """Da 6 a 8, con 7 fatto: metà — non l'87 per cento che darebbe lo zero."""
    user = _user(db_session)
    challenge = _challenge(db_session, "Barra", max_score=10)
    _prova(db_session, user, challenge, score=6)

    goal = TrainingGoalService.create(
        user.id,
        GoalKind.ESERCIZIO,
        challenge_id=challenge.id,
        rule=GoalRule.UNA_VOLTA,
        target=8,
    )
    assert goal.baseline == 6
    assert build_progress(goal).pct == 0

    _prova(db_session, user, challenge, score=7, giorni_fa=0)
    assert build_progress(goal).pct == 50


def test_senza_prove_il_valore_e_assente_non_zero(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Mai provato", max_score=10)

    goal = TrainingGoalService.create(
        user.id, GoalKind.ESERCIZIO, challenge_id=challenge.id, target=8
    )
    progresso = build_progress(goal)
    assert goal.baseline is None
    assert progresso.current is None
    assert progresso.current_label == "–"
    assert progresso.pct == 0


# ── la scadenza ─────────────────────────────────────────────────────────────
def test_la_scadenza_e_una_scelta_a_tre_voci(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Con scadenza", max_score=10)

    goal = TrainingGoalService.create(
        user.id,
        GoalKind.ESERCIZIO,
        challenge_id=challenge.id,
        target=8,
        deadline=GoalDeadline.MESE,
    )
    assert goal.deadline is not None
    assert 29 <= build_progress(goal).days_left <= 30

    senza = TrainingGoalService.create(
        user.id,
        GoalKind.COSTANZA,
        per_week=2,
        target=4,
        deadline=GoalDeadline.NESSUNA,
    )
    assert senza.deadline is None
    assert build_progress(senza).days_left is None


def test_una_scadenza_passata_non_chiude_l_obiettivo(db_session):
    """Resta lì, e la pagina dice che il tempo è finito.

    Chiuderlo da soli vorrebbe dire togliere dagli occhi proprio la cosa su cui
    si era indietro.
    """
    user = _user(db_session)
    challenge = _challenge(db_session, "Scaduto", max_score=10)
    goal = TrainingGoalService.create(
        user.id,
        GoalKind.ESERCIZIO,
        challenge_id=challenge.id,
        target=8,
        deadline=GoalDeadline.MESE,
    )
    goal.deadline = (utc_now() - timedelta(days=3)).date()
    db_session.flush()

    progresso = build_progress(goal)
    assert progresso.expired
    assert goal.is_active
