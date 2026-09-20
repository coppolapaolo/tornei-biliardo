"""Porre un obiettivo, lasciarlo, e segnare il giorno in cui è stato raggiunto.

Il servizio fa tre cose e nessun conto: i numeri li legge ``progress.py``, ogni
volta, dalle stesse fonti dell'andamento.

**«Raggiunto» si scrive una volta sola.** Il progresso è derivato e può
scendere — ci si allena male per un mese e la media cala — ma la data in cui
l'obiettivo è stato raggiunto è un fatto, e i fatti non si tolgono (#184).
``refresh`` la timbra la prima volta che la vede, e non la cancella mai.
"""

from __future__ import annotations

from datetime import timedelta
from typing import List, Optional, Sequence

from flask_babel import gettext as _

from ..base import db, utc_now
from ..challenge.models import Challenge
from ..challenge.vocabulary import CategoryAxis
from ..exceptions import ConflictError, NotFoundError, ValidationError
from ..transaction.manager import transactional
from .kinds import (
    MAX_ATTIVI,
    MAX_SETTIMANE,
    MAX_VOLTE,
    MIN_SETTIMANE,
    MIN_VOLTE,
    GoalDeadline,
    GoalKind,
    GoalRule,
)
from .models import TrainingGoal
from .progress import (
    valore_abilita,
    valore_corrente,
    valore_costanza,
    valore_esercizio,
    voce_del_vocabolario,
)


class TrainingGoalService:
    """Gli obiettivi di un giocatore."""

    # ── letture ────────────────────────────────────────────────────────────
    @staticmethod
    def active(user_id: int) -> List[TrainingGoal]:
        """Gli obiettivi ancora aperti, dal più vecchio: l'ordine in cui sono nati."""
        return (
            TrainingGoal.query.filter_by(
                user_id=user_id, reached_at=None, abandoned_at=None
            )
            .order_by(TrainingGoal.created_at.asc(), TrainingGoal.id.asc())
            .all()
        )

    @staticmethod
    def reached(user_id: int, limit: int = 10) -> List[TrainingGoal]:
        """Quelli raggiunti, dal più recente: restano, con la loro data."""
        return (
            TrainingGoal.query.filter(
                TrainingGoal.user_id == user_id,
                TrainingGoal.reached_at.isnot(None),
            )
            .order_by(TrainingGoal.reached_at.desc())
            .limit(limit)
            .all()
        )

    # ── scritture ──────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="obiettivo")
    def refresh(user_id: int) -> List[TrainingGoal]:
        """Timbra gli obiettivi che risultano raggiunti. Restituisce quelli timbrati.

        La chiamano le pagine che mostrano gli obiettivi. È una scrittura dentro
        una lettura, e va detto: non calcola niente — registra che una cosa
        derivata è successa, e lo fa una volta sola per obiettivo. Senza,
        «raggiunto» sarebbe uno stato che si accende e si spegne col variare
        della media, e la data non esisterebbe.
        """
        adesso = utc_now()
        timbrati = []
        for goal in TrainingGoalService.active(user_id):
            corrente = valore_corrente(goal)
            if corrente is not None and corrente >= goal.target:
                goal.reached_at = adesso
                timbrati.append(goal)
        return timbrati

    @staticmethod
    @transactional(domain="obiettivo")
    def abandon(goal_id: int, user_id: int) -> TrainingGoal:
        """Lascia un obiettivo. La riga resta: è successo, e si può raccontare."""
        goal = TrainingGoal.query.filter_by(id=goal_id, user_id=user_id).first()
        if goal is None:
            raise NotFoundError(_("Obiettivo non trovato."))
        if not goal.is_active:
            raise ConflictError(_("Questo obiettivo è già concluso."))
        goal.abandoned_at = utc_now()
        return goal

    @staticmethod
    @transactional(domain="obiettivo")
    def create(
        user_id: int,
        kind: Optional[GoalKind],
        *,
        challenge_id: Optional[int] = None,
        rule: GoalRule = GoalRule.MEDIA,
        axis: Optional[CategoryAxis] = None,
        axis_value: Optional[str] = None,
        per_week: Optional[int] = None,
        target: Optional[int] = None,
        deadline: GoalDeadline = GoalDeadline.NESSUNA,
    ) -> TrainingGoal:
        """Pone un obiettivo, dopo aver verificato che sia un obiettivo."""
        if kind is None:
            raise ValidationError(_("Scegli che cosa vuoi ottenere."))
        if len(TrainingGoalService.active(user_id)) >= MAX_ATTIVI:
            raise ConflictError(
                _(
                    "Hai già %(n)s obiettivi aperti: lasciane uno prima di "
                    "aggiungerne un altro.",
                    n=MAX_ATTIVI,
                )
            )
        if target is None:
            raise ValidationError(_("Scegli dove vuoi arrivare."))

        goal = TrainingGoal(
            user_id=user_id,
            kind=kind.value,
            target=target,
            deadline_kind=deadline.value,
        )
        if kind is GoalKind.ESERCIZIO:
            _prepara_esercizio(goal, user_id, challenge_id, rule, target)
        elif kind is GoalKind.ABILITA:
            _prepara_abilita(goal, user_id, axis, axis_value, target)
        else:
            _prepara_costanza(goal, user_id, per_week, target)

        giorni = deadline.giorni
        if giorni is not None:
            goal.deadline = (utc_now() + timedelta(days=giorni)).date()

        db.session.add(goal)
        return goal


# ────────────────────────────────────────────────────────────────────────
# Le tre validazioni
# ────────────────────────────────────────────────────────────────────────
def _rifiuta_se_gia_raggiunto(baseline: Optional[float], target: int) -> None:
    """Un obiettivo già raggiunto non è un obiettivo.

    Si rifiuta invece di accettarlo e timbrarlo subito: la seconda strada
    riempirebbe l'elenco dei traguardi di cose che non sono state fatte.
    """
    if baseline is not None and baseline >= target:
        raise ValidationError(
            _("Ci sei già: scegli un traguardo più alto di dove sei adesso.")
        )


def _prepara_esercizio(
    goal: TrainingGoal,
    user_id: int,
    challenge_id: Optional[int],
    rule: GoalRule,
    target: int,
) -> None:
    challenge = Challenge.query.get(challenge_id) if challenge_id else None
    if challenge is None:
        raise ValidationError(_("Scegli su quale esercizio."))
    if challenge.pass_fail_only:
        raise ValidationError(
            _(
                "Questo esercizio è superato o no: non ha un punteggio a cui "
                "arrivare."
            )
        )
    massimo = challenge.max_score
    if target < 1 or (massimo and target > massimo):
        raise ValidationError(
            _("Il traguardo deve stare fra 1 e %(max)s.", max=massimo or target)
        )
    goal.challenge_id = challenge.id
    goal.rule = rule.value
    partenza = valore_esercizio(user_id, challenge.id, rule)
    _rifiuta_se_gia_raggiunto(partenza, target)
    goal.baseline = round(partenza) if partenza is not None else None


def _prepara_abilita(
    goal: TrainingGoal,
    user_id: int,
    axis: Optional[CategoryAxis],
    axis_value: Optional[str],
    target: int,
) -> None:
    if axis is None or not voce_del_vocabolario(axis.value, axis_value or ""):
        raise ValidationError(_("Scegli su quale categoria."))
    if not 1 <= target <= 100:
        raise ValidationError(_("Il traguardo è una percentuale, fra 1 e 100."))
    goal.axis = axis.value
    goal.axis_value = axis_value
    partenza = valore_abilita(user_id, axis, axis_value or "")
    _rifiuta_se_gia_raggiunto(partenza, target)
    goal.baseline = round(partenza) if partenza is not None else None


def _prepara_costanza(
    goal: TrainingGoal, user_id: int, per_week: Optional[int], target: int
) -> None:
    if per_week is None or not MIN_VOLTE <= per_week <= MAX_VOLTE:
        raise ValidationError(
            _(
                "Quante volte a settimana? Fra %(min)s e %(max)s.",
                min=MIN_VOLTE,
                max=MAX_VOLTE,
            )
        )
    if not MIN_SETTIMANE <= target <= MAX_SETTIMANE:
        raise ValidationError(
            _(
                "Per quante settimane? Fra %(min)s e %(max)s.",
                min=MIN_SETTIMANE,
                max=MAX_SETTIMANE,
            )
        )
    goal.per_week = per_week
    # La serie che si ha **già**: chi si allena da otto settimane non riparte
    # da zero perché ha scritto l'obiettivo oggi. Ma non basta a raggiungerlo
    # subito — quello lo dice `_rifiuta_se_gia_raggiunto`.
    partenza = valore_costanza(user_id, per_week)
    _rifiuta_se_gia_raggiunto(partenza, target)
    goal.baseline = int(partenza) if partenza is not None else None


def goals_for(user_id: int) -> Sequence[TrainingGoal]:
    return TrainingGoalService.active(user_id)


__all__ = ["TrainingGoalService", "goals_for"]
