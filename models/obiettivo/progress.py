"""Dove si è arrivati, letto ogni volta dai dati (#316).

Il progresso non si salva: si deriva. Un numero memorizzato accanto a dei dati
che cambiano sotto è un numero da tenere allineato a mano, e prima o poi
diverge — la stessa ragione per cui «quanti l'hanno provato» si conta
(ADR-065) e il punteggio di una prova a colpi discende dai colpi (ADR-066).

**Ogni forma legge la fonte giusta per la sua domanda**, e non è una
distinzione accademica:

* un obiettivo **su un esercizio** guarda le sole prove del catalogo e di gara.
  «Arrivare a 8 su 10 su Spot Shot Rally» parla della scala di quell'esercizio,
  e una casella di scheda è tarata altrimenti (ADR-067);
* un obiettivo **su un'abilità** guarda l'andamento, dove catalogo e schede
  entrano insieme sulla quota di ciò che era ottenibile (ADR-068). Lì la
  domanda non è «quanto vale questo esercizio» ma «quanto bene tiro»;
* la **costanza** conta i giorni, non le registrazioni: dieci tiri in una sera
  sono una volta sola.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

from flask_babel import gettext as _

from ..andamento.view import Periodo, build_andamento, training_days
from ..base import utc_now
from ..challenge.vocabulary import Abilita, CategoryAxis, Gesto
from .kinds import FINESTRA_MEDIA, GoalKind, GoalRule
from .models import TrainingGoal


@dataclass(frozen=True)
class GoalProgress:
    """Un obiettivo, con dove si è arrivati."""

    goal: TrainingGoal
    title: str
    #: Dove si è **adesso**, nell'unità della domanda. ``None`` quando non c'è
    #: ancora niente da cui leggere: è diverso da zero, e si scrive «–».
    current: Optional[float]
    target: int
    unit: str

    @property
    def reached(self) -> bool:
        return self.goal.reached_at is not None or (
            self.current is not None and self.current >= self.target
        )

    @property
    def pct(self) -> int:
        """Quanto è piena la barra, da dove si partiva.

        Da `baseline` e non da zero: un obiettivo che parte da 61 e arriva a 70
        con la barra a zero racconterebbe che non si è fatto niente, quando
        invece manca poco. Senza un punto di partenza si misura da zero, che è
        l'unica altra cosa onesta.
        """
        if self.reached:
            return 100
        if self.current is None:
            return 0
        partenza = self.goal.baseline if self.goal.baseline is not None else 0
        corsa = self.target - partenza
        if corsa <= 0:
            return 100
        fatto = (self.current - partenza) / corsa * 100
        return max(0, min(round(fatto), 100))

    @property
    def current_label(self) -> str:
        if self.current is None:
            return "–"
        if float(self.current).is_integer():
            return str(int(self.current))
        return ("%.1f" % self.current).replace(".", ",")

    @property
    def days_left(self) -> Optional[int]:
        """Quanti giorni restano. Negativo quando il tempo è finito."""
        if self.goal.deadline is None or self.reached:
            return None
        return (self.goal.deadline - utc_now().date()).days

    @property
    def expired(self) -> bool:
        giorni = self.days_left
        return giorni is not None and giorni < 0


# ────────────────────────────────────────────────────────────────────────
# Le tre letture
# ────────────────────────────────────────────────────────────────────────
def _prove_sull_esercizio(user_id: int, challenge_id: int) -> List[Dict[str, Any]]:
    """Le prove a punteggio su un esercizio, dalla più recente."""
    from ..challenge.training_service import TrainingHistoryService

    return [
        voce
        for voce in TrainingHistoryService.get_drill_attempts(user_id)
        if voce["challenge_id"] == challenge_id
        and not voce["is_pass_fail"]
        and voce["score"] is not None
    ]


def valore_esercizio(
    user_id: int, challenge_id: int, rule: GoalRule
) -> Optional[float]:
    """La media delle ultime prove, o la migliore di sempre."""
    prove = _prove_sull_esercizio(user_id, challenge_id)
    if not prove:
        return None
    if rule is GoalRule.UNA_VOLTA:
        return float(max(voce["score"] for voce in prove))
    ultime = [voce["score"] for voce in prove[:FINESTRA_MEDIA]]
    return sum(ultime) / len(ultime)


def valore_abilita(user_id: int, asse: CategoryAxis, valore: str) -> Optional[float]:
    """La percentuale di una categoria, come la mostra l'andamento.

    Sulla finestra di un mese, la stessa su cui si apre la pagina: un obiettivo
    che si misurasse su «Sempre» si muoverebbe sempre più piano man mano che lo
    storico cresce, cioè punirebbe chi si allena da più tempo.
    """
    andamento = build_andamento(user_id, Periodo.MESE, asse)
    for riga in andamento.radar_rows:
        if riga.value.value == valore:
            return float(riga.pct)
    return None


def _settimana(giorno: date) -> tuple:
    anno, numero, _giorno = giorno.isocalendar()
    return (anno, numero)


def valore_costanza(user_id: int, per_week: int) -> Optional[float]:
    """Quante settimane **di fila**, fino a oggi, si è arrivati alla frequenza.

    La settimana in corso conta se la frequenza è già raggiunta, e non conta
    contro se non lo è ancora: altrimenti ogni lunedì mattina una serie di
    otto settimane tornerebbe a zero.
    """
    giorni = training_days(user_id)
    if not giorni:
        return None

    per_settimana: Dict[tuple, int] = {}
    for giorno in giorni:
        chiave = _settimana(giorno)
        per_settimana[chiave] = per_settimana.get(chiave, 0) + 1

    oggi = utc_now().date()
    corrente = _settimana(oggi)
    quante = 0
    # Si cammina all'indietro di settimana in settimana: una settimana senza
    # abbastanza giorni interrompe la serie, ed è il punto dell'obiettivo.
    cursore = oggi
    if per_settimana.get(corrente, 0) < per_week:
        cursore = oggi - timedelta(days=7)
    while per_settimana.get(_settimana(cursore), 0) >= per_week:
        quante += 1
        cursore -= timedelta(days=7)
    return float(quante)


def valore_corrente(goal: TrainingGoal) -> Optional[float]:
    """Dove si è adesso, qualunque sia la forma dell'obiettivo."""
    kind = goal.kind_enum
    if kind is GoalKind.ESERCIZIO and goal.challenge_id:
        return valore_esercizio(goal.user_id, goal.challenge_id, goal.rule_enum)
    if kind is GoalKind.ABILITA and goal.axis and goal.axis_value:
        asse = CategoryAxis(goal.axis)
        return valore_abilita(goal.user_id, asse, goal.axis_value)
    if kind is GoalKind.COSTANZA and goal.per_week:
        return valore_costanza(goal.user_id, goal.per_week)
    return None


# ────────────────────────────────────────────────────────────────────────
# Come si chiama, e in che unità
# ────────────────────────────────────────────────────────────────────────
def voce_del_vocabolario(asse: str, valore: str):
    """Il membro del vocabolario, o ``None`` se non è più fra le voci."""
    vocabolario = Abilita if asse == CategoryAxis.ABILITA.value else Gesto
    return vocabolario.normalize(valore)


def _titolo(goal: TrainingGoal) -> str:
    kind = goal.kind_enum
    if kind is GoalKind.ESERCIZIO:
        nome = goal.challenge.get_display_name() if goal.challenge else _("Esercizio")
        massimo = goal.challenge.max_score if goal.challenge else None
        if massimo:
            return _(
                "%(nome)s a %(t)s su %(max)s", nome=nome, t=goal.target, max=massimo
            )
        return _("%(nome)s a %(t)s", nome=nome, t=goal.target)
    if kind is GoalKind.ABILITA:
        voce = voce_del_vocabolario(goal.axis or "", goal.axis_value or "")
        nome = voce.display_name if voce else (goal.axis_value or "")
        return _("%(nome)s al %(t)s%%", nome=nome, t=goal.target)
    return _(
        "%(n)s volte a settimana, per %(s)s settimane",
        n=goal.per_week,
        s=goal.target,
    )


def _unita(goal: TrainingGoal) -> str:
    kind = goal.kind_enum
    if kind is GoalKind.ABILITA:
        return "%"
    if kind is GoalKind.COSTANZA:
        return _("settimane")
    return ""


def build_progress(goal: TrainingGoal) -> GoalProgress:
    return GoalProgress(
        goal=goal,
        title=_titolo(goal),
        current=valore_corrente(goal),
        target=goal.target,
        unit=_unita(goal),
    )


def build_all(goals: Sequence[TrainingGoal]) -> List[GoalProgress]:
    return [build_progress(goal) for goal in goals]


__all__ = [
    "GoalProgress",
    "build_all",
    "build_progress",
    "valore_abilita",
    "valore_corrente",
    "valore_costanza",
    "valore_esercizio",
    "voce_del_vocabolario",
]
