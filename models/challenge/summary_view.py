"""Il riepilogo di una prova appena chiusa (fase 5d).

Sola lettura, come le altre viste. Racconta **una** prova fatta di colpi: com'è
andata nel suo insieme, e — quando c'è un bersaglio — dove si sbaglia.

Non è «le prove di oggi» e non è l'andamento: è la fine della sessione, il
momento in cui si guarda la nuvola e si capisce che cosa correggere al tiro
dopo. Per questo ha una pagina sua, con un indirizzo: la si riapre, e domani lo
storico potrà mandarci.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from flask_babel import ngettext

from .dispersion import Dispersion, read_dispersion
from .draw_spec import parse_draw_spec
from .models import ChallengeAttempt
from .recording import RecordingMode
from .run_view import ShotMark
from .shot_stats import longest_made_streak, pocketing_pct, position_pct
from .target import Target, target_from_scene


@dataclass(frozen=True)
class AttemptSummary:
    attempt: ChallengeAttempt
    shots: List[ShotMark]
    subtitle: str
    score: int
    max_score: Optional[int]
    is_best: bool
    previous_best: Optional[int]
    pocketing: Optional[int]
    position: Optional[int]
    streak: int
    target: Optional[Target]
    dispersion: Optional[Dispersion]
    with_draw: bool

    @property
    def shots_count(self) -> int:
        return len(self.shots)


def build_summary(attempt: ChallengeAttempt) -> AttemptSummary:
    """Il riepilogo della prova. Vale solo per una prova **chiusa** e a colpi."""
    challenge = attempt.challenge
    bersaglio = target_from_scene(challenge.diagram_scene)
    colpi = list(attempt.shots)
    con_estrazione = RecordingMode.parse(challenge.recording_mode) is RecordingMode.DRAW

    # Il record di **prima**: confrontarsi con se stessi compresa la prova
    # appena fatta direbbe «record» a ogni prova migliore di niente.
    precedenti = [
        a.score
        for a in ChallengeAttempt.query.filter_by(
            user_id=attempt.user_id, challenge_id=challenge.id, completed=True
        ).all()
        if a.id != attempt.id and a.score is not None
    ]
    record_prima = max(precedenti) if precedenti else None
    punteggio = attempt.score or 0

    return AttemptSummary(
        attempt=attempt,
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
            for s in colpi
        ],
        subtitle=_subtitle(colpi, attempt),
        score=punteggio,
        max_score=challenge.max_score,
        is_best=record_prima is None or punteggio > record_prima,
        previous_best=record_prima,
        pocketing=None if con_estrazione else pocketing_pct(colpi),
        position=position_pct(colpi, bersaglio),
        streak=longest_made_streak(colpi),
        target=bersaglio,
        dispersion=read_dispersion(colpi, bersaglio),
        with_draw=con_estrazione and parse_draw_spec(challenge.draw_spec) is not None,
    )


def _subtitle(colpi, attempt: ChallengeAttempt) -> str:
    """«20 colpi · 14 minuti». I minuti solo se si sanno e se valgono."""
    quanti = ngettext("%(num)s colpo", "%(num)s colpi", len(colpi))
    if not colpi or attempt.attempted_at is None:
        return quanti
    inizio = min((s.created_at for s in colpi if s.created_at), default=None)
    if inizio is None:
        return quanti
    minuti = round((attempt.attempted_at - inizio).total_seconds() / 60)
    if minuti < 1:
        return quanti
    return quanti + " · " + ngettext("%(num)s minuto", "%(num)s minuti", minuti)


__all__ = ["AttemptSummary", "build_summary"]
