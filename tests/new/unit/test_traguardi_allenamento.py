"""I traguardi dell'allenamento: tenuta, miglioramento, obiettivi (#184).

I tre traguardi che c'erano contavano **quanti** esercizi, mai **come**. Le
quattro metriche nuove guardano l'altra metà, e ognuna ha un modo tutto suo di
essere sbagliata:

* la **serie di colpi** è dentro *una* prova. Venti colpi riusciti sparsi in un
  mese non sono una serie, e la issue avverte di non confonderla con la serie
  settimanale di `StreakService` — stessa parola, due meccaniche;
* i **record personali** si contano rigiocando la storia in ordine: il primo
  punteggio su un esercizio non è un record battuto, è il punto di partenza;
* gli **obiettivi raggiunti** sono monotoni, perché `reached_at` non si toglie;
* le **sedute** contano solo se chiuse e con qualcosa segnato.

In coda, la cosa che l'ADR-067 aveva rinviato qui: una seduta chiusa emette un
evento, e da lì XP e serie settimanale.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from models.base import utc_now
from models.challenge.models import Challenge, ChallengeAttempt, ChallengeShot
from models.events.base import EventBus
from models.gamification.achievement_metrics import AchievementMetrics
from models.gamification.achievement_seeds import PREDEFINED_ACHIEVEMENTS
from models.obiettivo import GoalKind, TrainingGoalService
from models.training_sheet.events import TrainingSessionClosedEvent
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
        username=f"tr_{uid}", email=f"tr_{uid}@test.local", role=UserRole.PLAYER.value
    )
    user.set_password("p")
    db_session.add(user)
    db_session.flush()
    return user


def _challenge(db_session, titolo, *, max_score=10, pass_fail=False) -> Challenge:
    challenge = Challenge(
        title=titolo,
        description=f"{titolo}: istruzioni",
        image_path="/static/challenges/x.png",
        pass_fail_only=pass_fail,
        max_score=max_score,
    )
    db_session.add(challenge)
    db_session.flush()
    return challenge


def _prova(db_session, user, challenge, *, score=None, passed=None, minuti_fa=1):
    attempt = ChallengeAttempt(
        challenge_id=challenge.id,
        user_id=user.id,
        score=score,
        passed=passed,
        completed=True,
        attempted_at=utc_now() - timedelta(minutes=minuti_fa),
    )
    db_session.add(attempt)
    db_session.flush()
    return attempt


def _colpi(db_session, attempt, esiti):
    """`esiti` è una stringa di `1` (imbucato), `0` (no) e `?` (senza esito)."""
    for posizione, segno in enumerate(esiti, start=1):
        db_session.add(
            ChallengeShot(
                attempt_id=attempt.id,
                position=posizione,
                made={"1": True, "0": False}.get(segno),
                points=1 if segno == "1" else 0,
            )
        )
    db_session.flush()


# ── la serie di colpi ───────────────────────────────────────────────────────
def test_la_serie_di_colpi_e_dentro_una_prova_sola(db_session):
    """Cinque e cinque in due prove non fanno dieci."""
    user = _user(db_session)
    challenge = _challenge(db_session, "Colpo per colpo")
    _colpi(db_session, _prova(db_session, user, challenge, score=5), "11111")
    _colpi(db_session, _prova(db_session, user, challenge, score=5), "11111")

    assert AchievementMetrics.current_value(user.id, "shot_streak", {}) == 5


def test_la_serie_si_interrompe_a_uno_sbagliato(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Colpo per colpo")
    _colpi(db_session, _prova(db_session, user, challenge, score=7), "111011111")

    assert AchievementMetrics.current_value(user.id, "shot_streak", {}) == 5


def test_un_colpo_senza_esito_interrompe_la_serie(db_session):
    """Gli esercizi con estrazione non dicono se la bilia è entrata.

    Saltarli farebbe attraversare la serie a colpi di cui non si sa niente.
    """
    user = _user(db_session)
    challenge = _challenge(db_session, "Con estrazione")
    _colpi(db_session, _prova(db_session, user, challenge, score=6), "111?111")

    assert AchievementMetrics.current_value(user.id, "shot_streak", {}) == 3


def test_senza_colpi_la_serie_e_zero(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "A punteggio")
    _prova(db_session, user, challenge, score=9)

    assert AchievementMetrics.current_value(user.id, "shot_streak", {}) == 0


# ── i record personali ──────────────────────────────────────────────────────
def test_il_primo_punteggio_non_e_un_record_battuto(db_session):
    """È il punto di partenza: contarlo premierebbe chi comincia."""
    user = _user(db_session)
    challenge = _challenge(db_session, "Spot shot")
    _prova(db_session, user, challenge, score=6, minuti_fa=30)

    assert AchievementMetrics.current_value(user.id, "personal_bests", {}) == 0


def test_si_contano_i_miglioramenti_in_ordine_di_tempo(db_session):
    """6 · 8 · 7 · 9 fa due record: l'8 e il 9. Il 7 non batte niente."""
    user = _user(db_session)
    challenge = _challenge(db_session, "Spot shot")
    for minuti, punteggio in ((40, 6), (30, 8), (20, 7), (10, 9)):
        _prova(db_session, user, challenge, score=punteggio, minuti_fa=minuti)

    assert AchievementMetrics.current_value(user.id, "personal_bests", {}) == 2


def test_ogni_esercizio_ha_il_suo_record(db_session):
    user = _user(db_session)
    primo = _challenge(db_session, "Uno")
    secondo = _challenge(db_session, "Due")
    _prova(db_session, user, primo, score=5, minuti_fa=40)
    _prova(db_session, user, primo, score=7, minuti_fa=30)
    _prova(db_session, user, secondo, score=3, minuti_fa=20)
    _prova(db_session, user, secondo, score=4, minuti_fa=10)

    assert AchievementMetrics.current_value(user.id, "personal_bests", {}) == 2


def test_un_esercizio_superato_o_no_non_ha_record(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Netto", max_score=None, pass_fail=True)
    _prova(db_session, user, challenge, passed=False, minuti_fa=20)
    _prova(db_session, user, challenge, passed=True, minuti_fa=10)

    assert AchievementMetrics.current_value(user.id, "personal_bests", {}) == 0


# ── gli obiettivi raggiunti ─────────────────────────────────────────────────
def test_gli_obiettivi_raggiunti_si_contano(db_session):
    user = _user(db_session)
    challenge = _challenge(db_session, "Obiettivo")
    _prova(db_session, user, challenge, score=5, minuti_fa=30)
    TrainingGoalService.create(
        user.id, GoalKind.ESERCIZIO, challenge_id=challenge.id, target=8
    )

    assert AchievementMetrics.current_value(user.id, "goals_reached", {}) == 0

    _prova(db_session, user, challenge, score=9, minuti_fa=1)
    _prova(db_session, user, challenge, score=9, minuti_fa=1)
    _prova(db_session, user, challenge, score=9, minuti_fa=1)
    _prova(db_session, user, challenge, score=9, minuti_fa=1)
    _prova(db_session, user, challenge, score=9, minuti_fa=1)
    TrainingGoalService.refresh(user.id)

    assert AchievementMetrics.current_value(user.id, "goals_reached", {}) == 1


# ── le sedute ───────────────────────────────────────────────────────────────
def _scheda_con_seduta(db_session, user, *, compilata=True, chiusa=True):
    challenge = _challenge(db_session, "Voce")
    sheet = TrainingSheet(name="Scheda", owner_id=user.id)
    db_session.add(sheet)
    db_session.flush()
    item = TrainingSheetItem(
        sheet_id=sheet.id,
        challenge_id=challenge.id,
        position=1,
        measure=SheetMeasure.MADE.value,
        amount=5,
    )
    db_session.add(item)
    db_session.flush()
    quando = utc_now()
    sessione = TrainingSession(
        sheet_id=sheet.id,
        user_id=user.id,
        started_at=quando,
        ended_at=quando if chiusa else None,
    )
    db_session.add(sessione)
    db_session.flush()
    db_session.add(
        TrainingEntry(
            session_id=sessione.id,
            item_id=item.id,
            value=4 if compilata else None,
            measure=SheetMeasure.MADE.value,
            target_amount=5,
        )
    )
    db_session.flush()
    return sessione


def test_una_seduta_aperta_non_conta(db_session):
    user = _user(db_session)
    _scheda_con_seduta(db_session, user, chiusa=False)

    assert AchievementMetrics.current_value(user.id, "sheet_sessions", {}) == 0


def test_una_seduta_chiusa_e_vuota_non_conta(db_session):
    """Aprirla e non segnare niente premierebbe il gesto di aprire l'app."""
    user = _user(db_session)
    _scheda_con_seduta(db_session, user, compilata=False)

    assert AchievementMetrics.current_value(user.id, "sheet_sessions", {}) == 0


def test_una_seduta_chiusa_e_compilata_conta(db_session):
    user = _user(db_session)
    _scheda_con_seduta(db_session, user)

    assert AchievementMetrics.current_value(user.id, "sheet_sessions", {}) == 1


# ── l'evento della seduta ───────────────────────────────────────────────────
def test_la_seduta_chiusa_emette_il_suo_evento(db_session):
    """È la cosa che l'ADR-067 aveva rinviato alla fase 7."""
    from models.training_sheet.session_service import TrainingSessionService

    user = _user(db_session)
    sessione = _scheda_con_seduta(db_session, user, chiusa=False)

    raccolti = []
    # Gli handler si **conservano e si rimettono**, non si azzerano: l'EventBus
    # è condiviso, e svuotarlo spegnerebbe notifiche e gamification per i test
    # che girano accanto (tests/CLAUDE.md).
    prima = {k: list(v) for k, v in EventBus._handlers.items()}
    EventBus.register_handler(
        TrainingSessionClosedEvent, lambda evento: raccolti.append(evento)
    )
    try:
        TrainingSessionService.close(sessione.id, user)
    finally:
        EventBus._handlers = prima

    assert len(raccolti) == 1
    evento = raccolti[0]
    assert evento.user_id == user.id
    assert evento.filled == 1
    assert not evento.is_empty


def test_una_seduta_vuota_si_riconosce_dall_evento(db_session):
    """Chi ascolta non deve ricaricare la seduta per sapere se è vuota."""
    evento = TrainingSessionClosedEvent(
        session_id=1, sheet_id=1, sheet_name="X", user_id=1, filled=0
    )
    assert evento.is_empty


# ── i semi ──────────────────────────────────────────────────────────────────
def test_ogni_traguardo_nuovo_ha_una_metrica_che_lo_sa_calcolare(db_session):
    """Un seme con un `type` senza resolver è un traguardo che non si sblocca mai."""
    import json

    nuovi = {
        "shot_streak_10",
        "shot_streak_20",
        "personal_best_5",
        "personal_best_25",
        "goal_reached_1",
        "goal_reached_5",
        "sheet_sessions_10",
    }
    visti = set()
    for seme in PREDEFINED_ACHIEVEMENTS:
        if seme["slug"] not in nuovi:
            continue
        visti.add(seme["slug"])
        tipo = json.loads(seme["requirements"])["type"]
        assert tipo in AchievementMetrics.COUNTABLE_TYPES, seme["slug"]
        assert AchievementMetrics.current_value(1, tipo, {}) is not None, seme["slug"]

    assert visti == nuovi
