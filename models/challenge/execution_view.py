"""La cornice di esecuzione di un esercizio: ciò che si vede mentre ci si allena.

Sola lettura. La pagina dell'allenamento (``challenge/training.html``) è una
cornice con tre posti fissi — il disegno dell'esercizio, **come sta andando**,
i comandi agganciati in basso — e ogni modo di registrare ci mette i suoi
comandi. Questo modulo riempie il posto di mezzo.

«Le prove di oggi» **non** è un'entità: è una finestra sull'ora delle prove,
nel fuso di chi legge (ADR-043). Per questo la modalità a punteggio entra nella
cornice senza toccare i dati, e chi chiude il browser a metà non lascia
indietro niente da ripulire.

Il confronto è sempre **con se stessi, e con il prima**: la media è quella
delle prove fino a ieri. Una media che contenesse le prove di oggi si
muoverebbe insieme a loro, e «sei sopra la tua media» diventerebbe quasi
impossibile da dire proprio la sera in cui è più vero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import List, Optional
from zoneinfo import ZoneInfo

from flask_babel import gettext as _
from flask_babel import ngettext

from models.base import utc_now
from utils.local_time import to_local_naive, to_utc_naive

from .live_chart import BarsChart, bars_chart
from .models import Challenge, ChallengeAttempt


@dataclass(frozen=True)
class TodayAttempt:
    """Una prova di oggi, come la mostra l'elenco sotto il grafico."""

    id: int
    label: str
    attempted_at: datetime
    score: Optional[int]
    passed: Optional[bool]
    variant: Optional[str]


@dataclass(frozen=True)
class ExecutionProgress:
    """Il posto di mezzo della cornice: titolo, grafico, frase, elenco."""

    kicker: str
    next_label: str
    sentence: str
    chart: Optional[BarsChart]
    average: Optional[float]
    best: Optional[int]
    today: List[TodayAttempt] = field(default_factory=list)


def _ordinal_label(numero: int) -> str:
    """«quarta prova»: a parole fin dove si dice, poi in cifre."""
    a_parole = [
        _("prima prova"),
        _("seconda prova"),
        _("terza prova"),
        _("quarta prova"),
        _("quinta prova"),
        _("sesta prova"),
        _("settima prova"),
        _("ottava prova"),
        _("nona prova"),
        _("decima prova"),
    ]
    if 1 <= numero <= len(a_parole):
        return a_parole[numero - 1]
    return _("prova %(n)s", n=numero)


def decimal_label(valore: float) -> str:
    """Un decimale, con la virgola di chi legge, e niente «,0» in coda."""
    testo = f"{valore:.1f}"
    if testo.endswith(".0"):
        return testo[:-2]
    return testo.replace(".", _(","))


def _start_of_today_utc(tz: ZoneInfo, now: datetime) -> datetime:
    """La mezzanotte di chi legge, riportata in UTC naive come la tiene il DB."""
    oggi = to_local_naive(now, tz).date()
    return to_utc_naive(datetime.combine(oggi, time.min), tz)


def build_progress(
    challenge: Challenge,
    user_id: int,
    *,
    tz: ZoneInfo,
    now: Optional[datetime] = None,
) -> ExecutionProgress:
    """Come sta andando, per chi sta guardando questo esercizio adesso."""
    adesso = now or utc_now()
    da = _start_of_today_utc(tz, adesso)

    prove = (
        ChallengeAttempt.query.filter_by(
            user_id=user_id, challenge_id=challenge.id, completed=True
        )
        .order_by(ChallengeAttempt.attempted_at.asc(), ChallengeAttempt.id.asc())
        .all()
    )
    di_oggi = [p for p in prove if p.attempted_at and p.attempted_at >= da]
    di_prima = [p for p in prove if not (p.attempted_at and p.attempted_at >= da)]

    oggi = [
        TodayAttempt(
            id=p.id,
            label=_ordinal_label(indice + 1),
            attempted_at=p.attempted_at,
            score=p.score,
            passed=p.passed,
            variant=p.variant.label if p.variant else None,
        )
        for indice, p in enumerate(di_oggi)
    ]
    oggi.reverse()  # la più recente per prima: è quella che si vuole rivedere

    comune = dict(
        kicker=_("Le prove di oggi"),
        next_label=_ordinal_label(len(di_oggi) + 1),
        today=oggi,
    )
    if challenge.pass_fail_only:
        return _pass_fail_progress(di_oggi, di_prima, comune)
    return _score_progress(challenge, di_oggi, di_prima, comune)


def _score_progress(challenge, di_oggi, di_prima, comune) -> ExecutionProgress:
    punteggi_prima = [p.score for p in di_prima if p.score is not None]
    punteggi_oggi = [p.score for p in di_oggi if p.score is not None]
    tutti = punteggi_prima + punteggi_oggi

    media = sum(punteggi_prima) / len(punteggi_prima) if punteggi_prima else None
    record = max(tutti) if tutti else None

    grafico = None
    if punteggi_oggi:
        grafico = bars_chart(
            punteggi_oggi,
            top=challenge.max_score,
            reference=media,
            reference_label=(
                None
                if media is None
                else _("la tua media %(avg)s", avg=decimal_label(media))
            ),
        )

    return ExecutionProgress(
        sentence=_score_sentence(punteggi_oggi, media, record),
        chart=grafico,
        average=media,
        best=record,
        **comune,
    )


def _score_sentence(oggi: List[int], media: Optional[float], record) -> str:
    if record is None:
        return _("È la tua prima prova su questo esercizio.")
    coda = _("Record: %(best)s.", best=record)
    if not oggi or media is None:
        return coda

    sopra = 0
    for punteggio in reversed(oggi):
        if punteggio <= media:
            break
        sopra += 1
    if sopra:
        testa = ngettext(
            "Sei sopra la tua media da %(num)s prova.",
            "Sei sopra la tua media da %(num)s prove.",
            sopra,
        )
    elif oggi[-1] == media:
        testa = _("L'ultima prova è sulla tua media.")
    else:
        testa = _("L'ultima prova è sotto la tua media.")
    return f"{testa} {coda}"


def _pass_fail_progress(di_oggi, di_prima, comune) -> ExecutionProgress:
    esiti_oggi = [1 if p.passed else 0 for p in di_oggi]
    esiti_prima = [1 if p.passed else 0 for p in di_prima]
    quota = sum(esiti_prima) / len(esiti_prima) if esiti_prima else None

    grafico = None
    if esiti_oggi:
        grafico = bars_chart(
            esiti_oggi,
            top=1,
            reference=quota,
            reference_label=(
                None
                if quota is None
                else _("di solito %(pct)s su 100", pct=round(quota * 100))
            ),
        )

    if not esiti_oggi and not esiti_prima:
        frase = _("È la tua prima prova su questo esercizio.")
    elif not esiti_oggi:
        frase = ngettext(
            "Finora %(num)s riuscita su %(n)s.",
            "Finora %(num)s riuscite su %(n)s.",
            sum(esiti_prima),
            n=len(esiti_prima),
        )
    else:
        frase = ngettext(
            "Oggi %(num)s riuscita su %(n)s.",
            "Oggi %(num)s riuscite su %(n)s.",
            sum(esiti_oggi),
            n=len(esiti_oggi),
        )

    return ExecutionProgress(
        sentence=frase, chart=grafico, average=quota, best=None, **comune
    )


__all__ = [
    "ExecutionProgress",
    "TodayAttempt",
    "build_progress",
    "decimal_label",
]
