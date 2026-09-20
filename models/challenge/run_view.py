"""La prova in corso, colpo per colpo: ciò che si vede mentre si tira (ADR-066).

Il posto di mezzo della cornice (`execution_view`) mostra «le prove di oggi»
finché una prova non è aperta; da lì in poi mostra **questa**, che parla di
colpi invece che di prove. Sola lettura: chi registra è `ShotRunService`.

Il confronto resta con se stessi e col prima: la media per colpo delle prove
già chiuse, e la proiezione di dove si andrebbe a finire tenendo questo passo.
Una proiezione è una previsione, quindi si mostra solo quando ha di che
appoggiarsi — non al primo colpo, e non senza uno storico.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from flask_babel import gettext as _
from flask_babel import ngettext

from .draw_spec import JOIN, Outcome, parse_draw_spec
from .execution_view import decimal_label
from .live_chart import BarsChart, bars_chart
from .models import ChallengeAttempt
from .shot_service import ShotRun
from .shot_stats import pocketing_pct, position_pct
from .target import Target, target_from_scene

#: Sotto questa quota di colpi tirati la proiezione non si mostra: due colpi
#: fortunati direbbero «chiudi a 60» con la stessa sicurezza di venti.
MIN_SHOTS_FOR_PACE = 3


@dataclass(frozen=True)
class ShotMark:
    """Un colpo: il suo posto, l'esito, i punti, e dove si è fermata la bianca.

    `x` e `y` restano `None` sul colpo non imbucato — non ha un punto d'arrivo —
    ed è il motivo per cui la nuvola sul panno mostra **solo** le imbucate.
    """

    position: int
    made: bool
    points: int
    x: Optional[float] = None
    y: Optional[float] = None
    #: Con estrazione: che cosa era uscito, e come è andata.
    prompt: Optional[str] = None
    outcome_label: Optional[str] = None


@dataclass(frozen=True)
class RunProgress:
    """La prova in corso: titolo, cifra, grafico, frase, striscia dei colpi."""

    kicker: str
    figure: str
    sentence: str
    chart: Optional[BarsChart]
    shots: List[ShotMark]
    total: int
    shots_count: int
    is_full: bool
    target: Optional[Target]
    pocketing: Optional[int]
    position: Optional[int]
    # Con estrazione (#452): la consegna in attesa e la scala fra cui scegliere.
    # `None` e lista vuota su ogni altro modo.
    prompt: Optional[str] = None
    outcomes: Sequence[Outcome] = ()

    @property
    def can_undo(self) -> bool:
        return bool(self.shots)

    @property
    def prompt_lead(self) -> str:
        """La prima voce della consegna: quella grande, «3 o più sponde»."""
        return (self.prompt or "").split(JOIN)[0]

    @property
    def prompt_rest(self) -> str:
        """Il resto, in tono minore: «bilia 7»."""
        return JOIN.join((self.prompt or "").split(JOIN)[1:])


def build_run(run: ShotRun) -> Optional[RunProgress]:
    """Come sta andando la prova aperta, o ``None`` se non ce n'è una."""
    if run.attempt is None:
        return None

    bersaglio = target_from_scene(run.challenge.diagram_scene)
    spec = parse_draw_spec(run.challenge.draw_spec)
    punti = [s.points for s in run.shots]
    media = _media_per_colpo(run)

    return RunProgress(
        kicker=_(
            "Colpo %(n)s di %(tot)s",
            n=min(len(run.shots) + 1, run.shots_count),
            tot=run.shots_count,
        ),
        figure=_("%(n)s punti", n=run.total),
        sentence=_sentence(run, media),
        chart=bars_chart(
            punti,
            top=(bersaglio.max_points if bersaglio else None)
            or (spec.max_points if spec else None),
            reference=media,
            reference_label=(
                None
                if media is None
                else _("la tua media %(avg)s a colpo", avg=decimal_label(media))
            ),
        ),
        shots=[
            ShotMark(
                position=s.position,
                made=bool(s.made),
                points=s.points,
                x=s.x,
                y=s.y,
                prompt=s.prompt,
                outcome_label=s.outcome_label,
            )
            for s in run.shots
        ],
        total=run.total,
        shots_count=run.shots_count,
        is_full=run.is_full,
        target=bersaglio,
        pocketing=pocketing_pct(run.shots) if bersaglio else None,
        position=position_pct(run.shots, bersaglio),
        prompt=run.attempt.pending_prompt,
        outcomes=spec.outcomes if spec else (),
    )


def _media_per_colpo(run: ShotRun) -> Optional[float]:
    """Quanto vale in media un colpo, nelle prove già **chiuse**.

    Si divide per i colpi dell'esercizio e non per quelli registrati: una prova
    chiusa li ha tutti, ed è l'unico modo perché il confronto regga se domani
    l'autore cambia quel numero.
    """
    chiuse = (
        ChallengeAttempt.query.filter_by(
            user_id=run.attempt.user_id if run.attempt else None,
            challenge_id=run.challenge.id,
            completed=True,
        )
        .filter(ChallengeAttempt.score.isnot(None))
        .all()
    )
    if not chiuse or not run.shots_count:
        return None
    return sum(a.score for a in chiuse) / len(chiuse) / run.shots_count


def _sentence(run: ShotRun, media: Optional[float]) -> str:
    fatti = len(run.shots)
    if run.is_full:
        return _("Hai tirato tutti i colpi: chiudi la prova quando vuoi.")
    if media is None:
        return _("È la tua prima prova su questo esercizio.")
    if fatti < MIN_SHOTS_FOR_PACE:
        return _(
            "Di solito chiudi a %(solito)s.",
            solito=round(media * run.shots_count),
        )

    proiezione = round(run.total / fatti * run.shots_count)
    solito = round(media * run.shots_count)
    scarto = proiezione - solito
    # Una frase intera per caso: comporla a pezzi non regge l'ordine delle
    # parole in nessuna lingua che non sia la nostra.
    if scarto > 0:
        return ngettext(
            "A questo ritmo chiudi a %(proj)s: %(num)s punto sopra il tuo solito.",
            "A questo ritmo chiudi a %(proj)s: %(num)s punti sopra il tuo solito.",
            scarto,
            proj=proiezione,
        )
    if scarto < 0:
        return ngettext(
            "A questo ritmo chiudi a %(proj)s: %(num)s punto sotto il tuo solito.",
            "A questo ritmo chiudi a %(proj)s: %(num)s punti sotto il tuo solito.",
            -scarto,
            proj=proiezione,
        )
    return _("A questo ritmo chiudi a %(proj)s: il tuo solito.", proj=proiezione)


__all__ = ["RunProgress", "ShotMark", "build_run", "MIN_SHOTS_FOR_PACE"]
