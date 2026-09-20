"""«Il tuo allenamento»: l'andamento per abilità e per gesto (#181, ADR-068).

Tre modi di dire la stessa cosa, come nel registro di una scheda: due numeri in
cima (adesso, e il periodo prima), il radar, e una riga per asse con la banda e
quante prove la reggono.

**L'unità è la quota di ciò che era ottenibile.** Un 12 su 15 e un 4 su 5 tiri
valgono entrambi l'ottanta per cento: è l'unica scala su cui esercizi diversi si
possono confrontare, e senza di essa un radar sommerebbe punteggi tarati in modi
incomparabili. Ne segue che *entra solo ciò che ha un massimo*: una prova su un
esercizio senza tetto dichiarato, i minuti e le spunte restano fuori — e la
pagina lo dice, invece di far sparire dei numeri in silenzio.

**Due mondi, una scala** (ADR-068). Le prove del catalogo e le caselle delle
schede sono tarate diversamente sullo *stesso esercizio*, e ADR-067 vieta di
mescolarle lì: media e record di un esercizio restano quelli del catalogo. Qui
la domanda è un'altra — «quanto bene tiro di draw?» — e non cambia a seconda di
dove il numero è stato segnato: le due fonti entrano insieme, una osservazione
per registrazione, e sotto ogni asse si dice quante vengono dalle schede.

Un esercizio con due abilità entra in **entrambe**: le categorie sono un
vocabolario, non una partizione, e dividere il suo punteggio a metà direbbe che
quel tiro è valso meno.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from flask_babel import gettext as _

from ..base import utc_now
from ..challenge.vocabulary import Abilita, CategoryAxis, Gesto
from ..status_enum import _StrEnum
from .radar import RadarShape, build_radar

#: Quante osservazioni servono perché la percentuale di un asse voglia dire
#: qualcosa. Sotto, l'asse resta **sul radar** — dove la forma si legge come un
#: insieme — ma non prende una riga con un numero e una banda: un asse
#: costruito su due prove è rumore disegnato bene (#181).
MIN_OSSERVAZIONI = 5

#: Le due soglie che separano le tre bande. Non sono del dominio — nessuno ha
#: mai deciso che il settanta per cento sia «solido» — sono un modo di dire a
#: parole ciò che il numero dice in cifre, e stanno qui perché si cambino in un
#: posto solo.
SOGLIA_SOLIDO = 70
SOGLIA_CRESCITA = 50


class Periodo(_StrEnum):
    """Su che finestra si guarda. Il confronto è sempre con la finestra prima."""

    MESE = "mese"
    TRIMESTRE = "trimestre"
    SEMPRE = "sempre"

    @property
    def giorni(self) -> Optional[int]:
        return {Periodo.MESE: 30, Periodo.TRIMESTRE: 90}.get(self)

    @property
    def label(self) -> str:
        return {
            Periodo.MESE: _("Ultimi 30 giorni"),
            Periodo.TRIMESTRE: _("3 mesi"),
            Periodo.SEMPRE: _("Sempre"),
        }[self]

    @property
    def before_label(self) -> str:
        """Come si chiama la finestra precedente. Vuoto quando non ce n'è una."""
        return {
            Periodo.MESE: _("Il mese prima"),
            Periodo.TRIMESTRE: _("I tre mesi prima"),
            Periodo.SEMPRE: "",
        }[self]

    @classmethod
    def parse(cls, value: object) -> "Periodo":
        try:
            return cls(str(value or "").strip().lower())
        except ValueError:
            return cls.MESE


def axis_label(asse: CategoryAxis) -> str:
    return {
        CategoryAxis.ABILITA: _("Per abilità"),
        CategoryAxis.GESTO: _("Per gesto"),
    }[asse]


def _vocabolario(asse: CategoryAxis):
    return Abilita if asse == CategoryAxis.ABILITA else Gesto


def _voci(challenge, asse: CategoryAxis):
    return challenge.abilita if asse == CategoryAxis.ABILITA else challenge.gesti


# ────────────────────────────────────────────────────────────────────────
# Le osservazioni
# ────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Osservazione:
    """Una registrazione ridotta a quota di ciò che era ottenibile."""

    challenge: Any
    pct: float
    when: Any
    from_sheet: bool


def _quota(valore: Optional[int], massimo: Optional[int]) -> Optional[float]:
    """La percentuale, o ``None`` quando la scala non c'è.

    Il tetto a cento non è cosmesi: una voce a minuti si può superare, e un
    asse al 140 per cento renderebbe il radar illeggibile per tutti gli altri.
    """
    if valore is None or not massimo or massimo <= 0:
        return None
    return max(0.0, min(valore / massimo * 100, 100.0))


def _dal_catalogo(user_id: int) -> Tuple[List[Osservazione], int]:
    """Le prove del catalogo e di gara, dalla fonte unica dello storico."""
    from ..challenge.training_service import TrainingHistoryService

    osservazioni: List[Osservazione] = []
    senza_scala = 0
    for voce in TrainingHistoryService.get_drill_attempts(user_id):
        challenge = voce.get("challenge")
        if challenge is None or voce.get("attempted_at") is None:
            continue
        if voce["is_pass_fail"]:
            # Riuscita o no **è** una quota dell'ottenibile, con l'ottenibile a
            # uno. Mediata su molte prove dà la percentuale di successo, che è
            # la stessa domanda delle altre: «quanto di quello che potevi».
            quota: Optional[float] = 100.0 if voce["passed"] else 0.0
        else:
            quota = _quota(voce["score"], voce["max_score"])
        if quota is None:
            senza_scala += 1
            continue
        osservazioni.append(
            Osservazione(
                challenge=challenge,
                pct=quota,
                when=voce["attempted_at"],
                from_sheet=False,
            )
        )
    return osservazioni, senza_scala


def _dalle_schede(user_id: int) -> Tuple[List[Osservazione], int]:
    """Le caselle delle sedute **chiuse**: una seduta aperta è quella in corso."""
    from sqlalchemy.orm import joinedload

    from ..base import db
    from ..training_sheet.measure import SheetMeasure
    from ..training_sheet.models import (
        TrainingEntry,
        TrainingSession,
        TrainingSheetItem,
    )

    righe = (
        db.session.query(TrainingEntry)
        .join(TrainingSession, TrainingEntry.session_id == TrainingSession.id)
        .options(
            joinedload(TrainingEntry.session),
            joinedload(TrainingEntry.item).joinedload(TrainingSheetItem.challenge),
        )
        .filter(
            TrainingSession.user_id == user_id,
            TrainingSession.ended_at.isnot(None),
        )
        .all()
    )

    osservazioni: List[Osservazione] = []
    senza_scala = 0
    for entry in righe:
        voce = entry.item
        challenge = getattr(voce, "challenge", None)
        if challenge is None:
            continue
        misura = entry.measure_kind
        if misura is SheetMeasure.SCORE:
            # Il massimo lo dice l'esercizio, come nel catalogo: è la stessa
            # prova, segnata dentro una scheda.
            quota = _quota(entry.value, challenge.max_score)
        elif misura.caps_value:
            # Riusciti e partite vinte: il «su quanto» è quello **di quella
            # sera**, copiato sulla casella (ADR-067). Rileggerlo dalla voce di
            # oggi rifarebbe i conti su una scheda che nel frattempo è cambiata.
            quota = _quota(entry.value, entry.target_amount)
        else:
            quota = None
        if quota is None:
            senza_scala += 1
            continue
        osservazioni.append(
            Osservazione(
                challenge=challenge,
                pct=quota,
                when=entry.session.ended_at,
                from_sheet=True,
            )
        )
    return osservazioni, senza_scala


# ────────────────────────────────────────────────────────────────────────
# Le righe
# ────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AxisRow:
    """Un asse del radar: com'è adesso, com'era, e su quante prove."""

    value: Any
    label: str
    pct: int
    pct_before: Optional[int]
    count: int
    sheet_count: int

    @property
    def delta(self) -> Optional[int]:
        return None if self.pct_before is None else self.pct - self.pct_before

    @property
    def is_thin(self) -> bool:
        return self.count < MIN_OSSERVAZIONI

    @property
    def band(self) -> str:
        if self.pct >= SOGLIA_SOLIDO:
            return _("solido")
        if self.pct >= SOGLIA_CRESCITA:
            return _("in crescita")
        return _("da costruire")

    @property
    def tone(self) -> str:
        """Il colore della riga: dal delta, non dalla banda.

        Una banda bassa non è una cattiva notizia — è il punto da cui si parte;
        scendere sì.
        """
        if self.delta is None or self.delta == 0:
            return ""
        return "ok" if self.delta > 0 else "err"


@dataclass(frozen=True)
class Andamento:
    periodo: Periodo
    asse: CategoryAxis
    rows: List[AxisRow]
    radar_rows: List[AxisRow]
    radar: Optional[RadarShape]
    pct: Optional[int]
    pct_before: Optional[int]
    attempts: int
    exercises: int
    sheet_attempts: int
    #: Quante registrazioni non si sono potute mettere in percentuale: prove su
    #: esercizi senza tetto dichiarato, minuti, spunte. Si contano per poterlo
    #: dire — un numero che sparisce senza spiegazione è un numero sbagliato.
    senza_scala: int = 0

    @property
    def is_empty(self) -> bool:
        return self.attempts == 0

    @property
    def thin(self) -> List[AxisRow]:
        """Gli assi che stanno sul grafico ma non prendono una riga."""
        return [riga for riga in self.radar_rows if riga.is_thin]

    @property
    def delta(self) -> Optional[int]:
        if self.pct is None or self.pct_before is None:
            return None
        return self.pct - self.pct_before


def _media(osservazioni: Sequence[Osservazione]) -> Optional[int]:
    if not osservazioni:
        return None
    return round(sum(o.pct for o in osservazioni) / len(osservazioni))


def _per_asse(
    osservazioni: Sequence[Osservazione], asse: CategoryAxis
) -> Dict[Any, List[Osservazione]]:
    raccolta: Dict[Any, List[Osservazione]] = {}
    for osservazione in osservazioni:
        for voce in _voci(osservazione.challenge, asse):
            raccolta.setdefault(voce, []).append(osservazione)
    return raccolta


def _finestre(
    osservazioni: Sequence[Osservazione], periodo: Periodo
) -> Tuple[List[Osservazione], List[Osservazione]]:
    """Le osservazioni del periodo e quelle del periodo di pari durata prima.

    Con «Sempre» non c'è un prima: il confronto sparisce invece di essere
    inventato tagliando lo storico a metà.
    """
    giorni = periodo.giorni
    if giorni is None:
        return list(osservazioni), []
    adesso = utc_now()
    inizio = adesso - timedelta(days=giorni)
    prima = inizio - timedelta(days=giorni)
    return (
        [o for o in osservazioni if o.when and o.when >= inizio],
        [o for o in osservazioni if o.when and prima <= o.when < inizio],
    )


def build_andamento(
    user_id: int,
    periodo: Periodo = Periodo.MESE,
    asse: CategoryAxis = CategoryAxis.ABILITA,
) -> Andamento:
    """L'andamento di questo giocatore su un asse, in un periodo."""
    catalogo, fuori_catalogo = _dal_catalogo(user_id)
    schede, fuori_schede = _dalle_schede(user_id)
    adesso, prima = _finestre(catalogo + schede, periodo)

    gruppi_adesso = _per_asse(adesso, asse)
    gruppi_prima = _per_asse(prima, asse)

    righe_radar: List[AxisRow] = []
    for voce in _vocabolario(asse):
        sue = gruppi_adesso.get(voce)
        if not sue:
            continue
        media = _media(sue)
        assert media is not None  # `sue` non è vuota
        righe_radar.append(
            AxisRow(
                value=voce,
                label=voce.display_name,
                pct=media,
                pct_before=_media(gruppi_prima.get(voce, [])),
                count=len(sue),
                sheet_count=sum(1 for o in sue if o.from_sheet),
            )
        )

    righe = sorted(
        (riga for riga in righe_radar if not riga.is_thin),
        key=lambda riga: (-riga.pct, riga.label),
    )

    return Andamento(
        periodo=periodo,
        asse=asse,
        rows=righe,
        radar_rows=righe_radar,
        radar=build_radar(
            [riga.label for riga in righe_radar],
            [riga.pct for riga in righe_radar],
            [riga.pct_before for riga in righe_radar],
        ),
        pct=_media(adesso),
        pct_before=_media(prima),
        attempts=len(adesso),
        exercises=len({o.challenge.id for o in adesso}),
        sheet_attempts=sum(1 for o in adesso if o.from_sheet),
        senza_scala=fuori_catalogo + fuori_schede,
    )


__all__ = [
    "Andamento",
    "AxisRow",
    "Osservazione",
    "Periodo",
    "axis_label",
    "build_andamento",
    "MIN_OSSERVAZIONI",
    "SOGLIA_CRESCITA",
    "SOGLIA_SOLIDO",
]
