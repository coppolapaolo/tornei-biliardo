"""«Per oggi»: che cosa conviene allenare, e perché (#175).

Il catalogo lascia scegliere, e chi sceglie prende i tre esercizi che sa già
fare. Questo modulo propone — e **dice sempre il motivo**, che non è un
ornamento: un consiglio che non si capisce non si segue, e senza il motivo non
si può nemmeno contestare.

**A regole, non a modello.** La issue lo chiede esplicitamente, ed è la scelta
giusta finché i numeri sono pochi: quattro regole in ordine di priorità,
ciascuna che guarda un buco diverso nello storico. Ognuna produce al più un
esercizio, e la frase che lo accompagna è la regola stessa detta a parole.

Le regole, dalla più forte alla più debole:

1. **il tuo obiettivo** — se ti sei dato un traguardo, la cosa da fare è quello;
2. **dove sei indietro** — l'abilità con la banda più bassa fra quelle che hai
   abbastanza allenato da poterne parlare;
3. **fermo da tempo** — qualcosa che facevi e non tocchi da un mese;
4. **mai provato, ed è alla tua portata** — né banale né un muro, misurato su
   chi l'ha provato davvero (#174).

E una cosa che non si propone mai: un esercizio in cui si è **già al massimo**.
Insistere lì non serve, e lo dice la issue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from flask_babel import gettext as _

from ..base import utc_now
from .catalog_view import CatalogFilter, ExerciseCard, build_catalog
from .difficulty import expected_for, measure_many

#: Quanti consigli si danno. Tre è il massimo che si legge senza scegliere di
#: nuovo: oltre, «per oggi» torna a essere un catalogo.
QUANTI = 3

#: Da quanti giorni una cosa che facevi è «ferma».
FERMO_DA = 30
#: E da quanti un esercizio si considera «già fatto di recente», quindi non da
#: riproporre per colmare un buco.
DI_RECENTE = 7

#: Quanto deve valere la quota attesa perché un esercizio mai provato sia «alla
#: tua portata»: sotto è un muro, sopra è già saputo.
PORTATA_MIN = 35
PORTATA_MAX = 80

#: Sopra questa quota, su abbastanza prove, un esercizio è saputo: insistere non
#: serve.
SAPUTO = 90
SAPUTO_PROVE = 3


@dataclass(frozen=True)
class Advice:
    """Un esercizio consigliato, col motivo per cui è lì."""

    card: ExerciseCard
    kicker: str
    reason: str

    @property
    def challenge(self):
        return self.card.challenge


def _gia_saputo(card: ExerciseCard) -> bool:
    """Se su questo esercizio non c'è più niente da prendere."""
    mine = card.mine
    if mine.attempts < SAPUTO_PROVE:
        return False
    quota = mine.recent_pct if mine.recent_pct is not None else mine.average_pct
    if quota is not None and quota >= SAPUTO:
        return True
    massimo = card.challenge.max_score
    return bool(massimo and mine.best is not None and mine.best >= massimo)


def _giorni_fa(card: ExerciseCard) -> Optional[int]:
    quando = card.mine.last_attempted_at
    return (utc_now() - quando).days if quando else None


def _proponibili(cards: Sequence[ExerciseCard]) -> List[ExerciseCard]:
    return [c for c in cards if not _gia_saputo(c)]


# ────────────────────────────────────────────────────────────────────────
# Le quattro regole
# ────────────────────────────────────────────────────────────────────────
def _per_obiettivo(cards, obiettivi) -> List[Advice]:
    """La regola più forte: se ti sei dato un traguardo, la cosa da fare è quello."""
    from ..obiettivo.kinds import GoalKind
    from ..obiettivo.progress import build_progress

    per_id = {c.challenge.id: c for c in cards}
    consigli: List[Advice] = []
    for goal in obiettivi:
        kind = goal.kind_enum
        if kind is GoalKind.ESERCIZIO and goal.challenge_id in per_id:
            progresso = build_progress(goal)
            consigli.append(
                Advice(
                    card=per_id[goal.challenge_id],
                    kicker=_("Per il tuo obiettivo"),
                    reason=_(
                        "Sei a %(ora)s, il traguardo è %(t)s.",
                        ora=progresso.current_label,
                        t=goal.target,
                    ),
                )
            )
        elif kind is GoalKind.ABILITA and goal.axis_value:
            scelta = _meno_allenato(cards, goal.axis or "", goal.axis_value)
            if scelta is not None:
                consigli.append(
                    Advice(
                        card=scelta,
                        kicker=_("Per il tuo obiettivo"),
                        reason=_(
                            "Allena %(voce)s, la categoria che ti sei dato.",
                            voce=_nome_voce(goal.axis or "", goal.axis_value),
                        ),
                    )
                )
    return consigli


def _nome_voce(asse: str, valore: str) -> str:
    from ..obiettivo.progress import voce_del_vocabolario

    voce = voce_del_vocabolario(asse, valore)
    return voce.display_name if voce else valore


def _sull_asse(cards, asse: str, valore: str) -> List[ExerciseCard]:
    from .vocabulary import CategoryAxis

    campo = "abilita" if asse == CategoryAxis.ABILITA.value else "gesti"
    return [
        c
        for c in cards
        if any(voce.value == valore for voce in getattr(c.challenge, campo))
    ]


def _meno_allenato(cards, asse: str, valore: str) -> Optional[ExerciseCard]:
    """Fra gli esercizi di una categoria, quello che si è toccato meno di recente.

    Non «il mai provato»: chi non ha mai provato niente di quella categoria si
    vedrebbe proporre sempre lo stesso esercizio, e chi li ha provati tutti non
    si vedrebbe proporre niente.
    """
    candidati = [
        c
        for c in _sull_asse(cards, asse, valore)
        if (_giorni_fa(c) is None or _giorni_fa(c) >= DI_RECENTE)
    ]
    if not candidati:
        return None
    return max(candidati, key=lambda c: (_giorni_fa(c) or 10**6, c.popularity.players))


def _dove_sei_indietro(cards, andamento) -> Optional[Advice]:
    """L'abilità con la banda più bassa, fra quelle di cui si può parlare."""
    righe = [riga for riga in andamento.rows]
    if not righe:
        return None
    peggiore = min(righe, key=lambda riga: riga.pct)
    scelta = _meno_allenato(cards, andamento.asse.value, peggiore.value.value)
    if scelta is None:
        return None
    return Advice(
        card=scelta,
        kicker=_("Dove sei indietro"),
        reason=_(
            "%(voce)s è la tua banda più bassa: %(q)s%%.",
            voce=peggiore.label,
            q=peggiore.pct,
        ),
    )


def _fermo_da_tempo(cards) -> Optional[Advice]:
    """Qualcosa che facevi e non tocchi da un mese."""
    fermi = [
        (c, _giorni_fa(c))
        for c in cards
        if c.mine.tried and (_giorni_fa(c) or 0) >= FERMO_DA
    ]
    if not fermi:
        return None
    card, giorni = max(fermi, key=lambda coppia: coppia[1] or 0)
    return Advice(
        card=card,
        kicker=_("Fermo da un po'"),
        reason=_("Non lo provi da %(n)s giorni.", n=giorni),
    )


def _alla_tua_portata(cards, user_id) -> Optional[Advice]:
    """Mai provato, e chi ha la tua forza ci riesce: né banale né un muro."""
    mai = [c for c in cards if not c.mine.tried]
    if not mai:
        return None
    stime = measure_many([c.challenge for c in mai])
    candidati = []
    for card in mai:
        stima = stime.get(card.challenge.id)
        if stima is None or not stima.has_estimate:
            continue
        attesa = expected_for(card.challenge, user_id)
        if attesa is None or not PORTATA_MIN <= attesa <= PORTATA_MAX:
            continue
        candidati.append((card, attesa))
    if not candidati:
        return None
    # Il più provato dagli altri, a parità di adeguatezza: un esercizio che
    # nessuno fa è un esercizio di cui si sa poco.
    card, attesa = max(candidati, key=lambda coppia: coppia[0].popularity.players)
    return Advice(
        card=card,
        kicker=_("Mai provato"),
        reason=_("Chi ha la tua forza ci arriva al %(q)s%%.", q=attesa),
    )


# ────────────────────────────────────────────────────────────────────────
# Comporre
# ────────────────────────────────────────────────────────────────────────
def build_advice(user_id: int, limit: int = QUANTI) -> List[Advice]:
    """I consigli per oggi, al più ``limit``, senza ripetere un esercizio.

    Lista vuota quando non c'è niente da dire — un catalogo vuoto, o un
    giocatore su cui nessuna regola ha presa. Meglio niente che un consiglio a
    caso: è il motivo per cui ogni regola può restituire ``None``.
    """
    from ..andamento.view import Periodo, build_andamento
    from ..challenge.vocabulary import CategoryAxis
    from ..obiettivo.service import TrainingGoalService

    cards = _proponibili(build_catalog(user_id, CatalogFilter()).cards)
    if not cards:
        return []

    andamento = build_andamento(user_id, Periodo.MESE, CategoryAxis.ABILITA)
    obiettivi = TrainingGoalService.active(user_id)

    proposte: List[Optional[Advice]] = []
    proposte.extend(_per_obiettivo(cards, obiettivi))
    proposte.append(_dove_sei_indietro(cards, andamento))
    proposte.append(_fermo_da_tempo(cards))
    proposte.append(_alla_tua_portata(cards, user_id))

    scelti: List[Advice] = []
    visti: Dict[int, bool] = {}
    for consiglio in proposte:
        if consiglio is None or consiglio.challenge.id in visti:
            continue
        visti[consiglio.challenge.id] = True
        scelti.append(consiglio)
        if len(scelti) >= limit:
            break
    return scelti


__all__ = [
    "Advice",
    "build_advice",
    "DI_RECENTE",
    "FERMO_DA",
    "PORTATA_MAX",
    "PORTATA_MIN",
    "QUANTI",
    "SAPUTO",
    "SAPUTO_PROVE",
]
