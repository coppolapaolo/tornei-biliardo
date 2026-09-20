"""«I miei allievi»: chi ti ha aperto una scheda, e come sta andando.

La pagina divide gli allievi in tre, e **le tre definizioni sono qui dentro,
scritte per esteso**. È la parte di questo lavoro in cui è più facile inventare
una metrica che sembra vera: «sta migliorando», «è costante», «è a rischio»
sono frasi che un programma può scrivere con qualunque formula, e nessuno se ne
accorge finché un istruttore non ci crede.

Quindi:

* **Valuta il passaggio di livello** non è una stima, è il gradino della scheda
  che la fase 6 aveva lasciato senza nessuno che lo sancisse: tante sedute di
  fila sopra la soglia quante la scheda ne chiede
  (`streak_above_threshold`, la stessa funzione che usa la fine seduta).
  Qui si **mostra**: dare la scheda del livello dopo è un gesto a parte;
* **Da guardare** sono due fatti, ciascuno con la sua costante dichiarata qui
  sotto — «non si allena da N giorni» e «da N sedute non supera il suo
  massimo». Nessuno dei due dice perché, e non devono: dicono che c'è qualcosa
  da chiedere;
* **Tutto bene** *non è una metrica*: è il resto. Sotto il nome non c'è un
  giudizio ma un fatto verificabile — quando si è allenato l'ultima volta, e
  quante sedute ha chiuso nelle ultime quattro settimane.

Ciò che si è deliberatamente **lasciato fuori** è «6 sedute su 7 previste»:
«previste» non esiste nel modello. Una scheda dichiara le settimane e i giorni
A · B · C, non la frequenza, e dedurre «un giro a settimana» sarebbe
esattamente la metrica inventata contro cui è scritto questo docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Optional, Sequence

from flask_babel import gettext as _
from flask_babel import ngettext

from ..base import utc_now
from ..training_sheet.gradino import gradino_raggiunto
from ..training_sheet.measure import LevelUp
from ..training_sheet.models import TrainingSession, TrainingSheet
from ..user.models import User
from .gruppi import GruppoService
from .models import TrainingGroup, TrainingGroupMember
from .viste import Legame, allievi_di

#: Da quanti giorni un permesso smette di essere una novità. «Appena» vuol dire
#: questa settimana: più in là, quella sezione diventerebbe un secondo elenco
#: di tutti.
GIORNI_NUOVI = 7

#: Dopo quanti giorni senza chiudere una seduta si finisce fra quelli da
#: guardare. Due settimane: una saltata capita a chiunque, due sono una cosa
#: che si chiede.
GIORNI_ASSENZA = 14

#: Quante sedute di fila senza superare il proprio massimo fanno uno stallo.
SEDUTE_SENZA_MIGLIORARE = 5

#: La finestra in cui si contano le sedute per la riga di «Tutto bene».
GIORNI_FINESTRA = 28

#: Quante sedute per scheda si guardano. Venti, come il registro che
#: l'istruttore apre subito dopo: i due devono raccontare la stessa cosa.
SEDUTE_LETTE = 20

#: Fin dove si va a ritroso nel database. Una pagina che legge tutto lo storico
#: di venti allievi diventa lenta l'anno prossimo, e nessuno guarda una seduta
#: di due anni fa per dire come sta andando adesso.
GIORNI_STORICO = 365

#: Quanti totali si mostrano accanto alla soglia.
NUMERI_MOSTRATI = 3


@dataclass(frozen=True)
class Segnale:
    """Perché questo allievo sta dov'è, in una frase e un tono.

    Insieme e non in due campi calcolati altrove: il tono discende da *quale*
    osservazione si è fatta, e ricavarlo rileggendo la frase vorrebbe dire
    confrontare del testo tradotto — la stessa ragione per cui
    `register_view._nota_e_tono` restituisce la coppia.
    """

    #: `passaggio` · `assenza` · `stallo` · `sereno`
    tipo: str
    frase: str
    tono: str
    #: La scheda che ha fatto scattare il segnale, quando ce n'è una sola
    #: responsabile: serve a nominarla se l'allievo te ne ha aperte più d'una.
    scheda: Optional[TrainingSheet] = None


@dataclass(frozen=True)
class RigaAllievo:
    """Una persona nell'elenco: il legame, il segnale, il gruppo."""

    legame: Legame
    segnale: Segnale
    iscrizione: Optional[TrainingGroupMember] = None
    nuovo: bool = False

    @property
    def persona(self) -> User:
        return self.legame.persona

    @property
    def schede(self) -> List[TrainingSheet]:
        return self.legame.schede

    @property
    def gruppo(self) -> Optional[TrainingGroup]:
        return self.iscrizione.group if self.iscrizione else None


@dataclass(frozen=True)
class Allievi:
    """La pagina: le sezioni, i gruppi che la filtrano, e quanti sono."""

    nuovi: List[RigaAllievo]
    passaggio: List[RigaAllievo]
    guardare: List[RigaAllievo]
    bene: List[RigaAllievo]
    gruppi: List[TrainingGroup]
    gruppo: Optional[TrainingGroup] = None

    @property
    def righe(self) -> List[RigaAllievo]:
        """Tutti gli allievi, nell'ordine in cui la pagina li mostra.

        `nuovi` non entra: non è una quarta sezione ma una ripetizione in cima
        di gente che sta già in una delle tre, e contarla due volte darebbe un
        totale che non torna con l'elenco.
        """
        return self.passaggio + self.guardare + self.bene

    @property
    def totale(self) -> int:
        return len(self.righe)

    @property
    def vuota(self) -> bool:
        return self.totale == 0


def build_allievi(instructor: User, gruppo: Optional[TrainingGroup] = None) -> Allievi:
    """L'elenco degli allievi di questo istruttore, diviso in tre.

    Con ``gruppo`` si guarda un corso solo: gli stessi allievi, filtrati a chi
    ne fa parte adesso. Un allievo che non ti fa più leggere niente non compare
    nemmeno lì — la riga del gruppo resta, ma questa è la pagina di chi si
    allena, non l'anagrafica.
    """
    legami = allievi_di(instructor.id)
    iscrizioni = GruppoService.iscrizioni_correnti(instructor.id)
    sedute = sedute_per_scheda([s.id for legame in legami for s in legame.schede])

    adesso = utc_now()
    righe: List[RigaAllievo] = []
    for legame in legami:
        if gruppo is not None:
            iscrizione = iscrizioni.get(legame.persona.id)
            if iscrizione is None or iscrizione.group_id != gruppo.id:
                continue
        righe.append(
            RigaAllievo(
                legame=legame,
                segnale=_segnale(legame, sedute, adesso),
                iscrizione=iscrizioni.get(legame.persona.id),
                nuovo=(adesso - legame.dal) <= timedelta(days=GIORNI_NUOVI),
            )
        )

    return Allievi(
        nuovi=[riga for riga in righe if riga.nuovo],
        passaggio=[riga for riga in righe if riga.segnale.tipo == "passaggio"],
        guardare=[riga for riga in righe if riga.segnale.tipo in _DA_GUARDARE],
        bene=[riga for riga in righe if riga.segnale.tipo == "sereno"],
        gruppi=GruppoService.gruppi_di(instructor.id, aperti=True),
        gruppo=gruppo,
    )


_DA_GUARDARE = frozenset({"assenza", "stallo"})


# ── le sedute, in una query sola ────────────────────────────────────────────


def sedute_per_scheda(sheet_ids: Sequence[int]) -> Dict[int, List[TrainingSession]]:
    """Le sedute chiuse di tutte le schede lette, raggruppate per scheda.

    Una query per l'intera pagina, e non una per allievo: con venti allievi e
    due schede a testa sarebbero quaranta interrogazioni per disegnare un
    elenco. Le sedute arrivano **dalla più recente**, come le dà
    ``closed_sessions``, perché è l'ordine che tutte le regole qui sotto danno
    per scontato.
    """
    if not sheet_ids:
        return {}

    da = utc_now() - timedelta(days=GIORNI_STORICO)
    righe = (
        TrainingSession.query.filter(
            TrainingSession.sheet_id.in_(list(sheet_ids)),
            TrainingSession.ended_at.isnot(None),
            TrainingSession.ended_at >= da,
        )
        .order_by(TrainingSession.ended_at.desc())
        .all()
    )

    per_scheda: Dict[int, List[TrainingSession]] = {}
    for seduta in righe:
        elenco = per_scheda.setdefault(seduta.sheet_id, [])
        if len(elenco) < SEDUTE_LETTE:
            elenco.append(seduta)
    return per_scheda


# ── le tre definizioni ──────────────────────────────────────────────────────


def _segnale(
    legame: Legame, sedute: Dict[int, List[TrainingSession]], adesso
) -> Segnale:
    """Il segnale più forte fra quelli che le sue schede fanno scattare.

    L'ordine non è arbitrario. Il gradino viene prima di tutto perché è l'unica
    cosa che chiede una **decisione**; l'assenza viene prima dello stallo
    perché a chi non si allena da tre settimane non si va a dire che il
    punteggio non sale.
    """
    tutte = [s for scheda in legame.schede for s in sedute.get(scheda.id, [])]

    for scheda in legame.schede:
        gradino = _gradino(scheda, sedute.get(scheda.id, []))
        if gradino is not None:
            return gradino

    assenza = _assenza(tutte, legame, adesso)
    if assenza is not None:
        return assenza

    for scheda in legame.schede:
        stallo = _stallo(scheda, sedute.get(scheda.id, []))
        if stallo is not None:
            return stallo

    return _sereno(tutte, adesso)


def _gradino(scheda: TrainingSheet, sedute: List[TrainingSession]) -> Optional[Segnale]:
    """Il gradino della scheda è superato: tocca a qualcuno dire di sì.

    La regola è quella della fine seduta, chiamata dalla stessa funzione: tante
    sedute di fila sopra la soglia quante la scheda ne chiede.

    Compare solo per le schede che aspettano **una persona** (`instructor`):
    con `auto` il gradino se l'è già timbrato la soglia, e mettere in elenco
    chi non ha bisogno di te sarebbe un invito a premere qualcosa che non c'è.
    """
    if not sedute or scheda.level_up_kind is not LevelUp.INSTRUCTOR:
        return None
    if not gradino_raggiunto(scheda, sedute):
        return None

    ultimi = list(reversed(sedute[:NUMERI_MOSTRATI]))
    massimo = ultimi[-1].max_total or scheda.total
    return Segnale(
        tipo="passaggio",
        frase=_(
            "%(numeri)s su %(max)s · soglia %(soglia)s",
            numeri=", ".join(str(s.total) for s in ultimi),
            max=massimo,
            soglia=scheda.threshold,
        ),
        tono="ok",
        scheda=scheda,
    )


def _assenza(tutte: List[TrainingSession], legame: Legame, adesso) -> Optional[Segnale]:
    """Non chiude una seduta da troppo tempo — o non ne ha mai chiusa una.

    I due casi dicono cose diverse e vanno detti diversamente: chi ha smesso e
    chi non ha ancora cominciato non si aiutano con la stessa frase. Chi ti ha
    aperto la scheda ieri e non si è ancora allenato non è «assente»: è nuovo,
    e sta nella sezione di sopra.
    """
    if not tutte:
        if (adesso - legame.dal) <= timedelta(days=GIORNI_ASSENZA):
            return None
        return Segnale(
            tipo="assenza",
            frase=_("non ha ancora chiuso una seduta"),
            tono="err",
        )

    giorni = (adesso - max(s.ended_at for s in tutte)).days
    if giorni < GIORNI_ASSENZA:
        return None
    return Segnale(
        tipo="assenza",
        frase=ngettext(
            "non si allena da %(num)s giorno",
            "non si allena da %(num)s giorni",
            giorni,
        ),
        tono="err",
    )


def _stallo(scheda: TrainingSheet, sedute: List[TrainingSession]) -> Optional[Segnale]:
    """Da cinque sedute non supera il massimo che aveva già raggiunto.

    Serve una seduta *prima* del blocco, altrimenti non c'è un massimo «di
    allora» da non superare: con esattamente cinque sedute in tutto la frase
    direbbe che non si migliora da quando si è cominciato, che è un'altra cosa.

    Chi è **al massimo possibile** della scheda non è in stallo: ha finito i
    numeri disponibili, e dirgli che non sale sarebbe falso.
    """
    totali = [s.total for s in sedute if s.max_total]
    if len(totali) <= SEDUTE_SENZA_MIGLIORARE:
        return None

    recenti = totali[:SEDUTE_SENZA_MIGLIORARE]
    prima = totali[SEDUTE_SENZA_MIGLIORARE:]
    massimo = max(prima)
    if max(recenti) > massimo:
        return None
    if massimo >= (sedute[0].max_total or scheda.total):
        return None

    return Segnale(
        tipo="stallo",
        frase=_(
            "da %(sedute)s sedute non supera %(massimo)s",
            sedute=SEDUTE_SENZA_MIGLIORARE,
            massimo=massimo,
        ),
        tono="warn",
        scheda=scheda,
    )


def _sereno(tutte: List[TrainingSession], adesso) -> Segnale:
    """Il resto: nessun giudizio, due fatti.

    «Tutto bene» è il nome della sezione, non di una misura — e per questo la
    riga sotto il nome dice quando si è allenato e quanto, non come va.
    """
    if not tutte:
        return Segnale(tipo="sereno", frase=_("ha appena cominciato"), tono="")

    giorni = (adesso - max(s.ended_at for s in tutte)).days
    da = adesso - timedelta(days=GIORNI_FINESTRA)
    quante = sum(1 for s in tutte if s.ended_at >= da)

    return Segnale(
        tipo="sereno",
        frase=_(
            "%(quando)s · %(quante)s",
            quando=_quando(giorni),
            quante=ngettext(
                "%(num)s seduta in quattro settimane",
                "%(num)s sedute in quattro settimane",
                quante,
            ),
        ),
        tono="",
    )


def _quando(giorni: int) -> str:
    """«oggi», «ieri», «5 giorni fa»: come lo direbbe una persona."""
    if giorni <= 0:
        return _("oggi")
    if giorni == 1:
        return _("ieri")
    return _("%(num)s giorni fa", num=giorni)


__all__ = [
    "Allievi",
    "RigaAllievo",
    "Segnale",
    "build_allievi",
    "sedute_per_scheda",
    "GIORNI_ASSENZA",
    "GIORNI_FINESTRA",
    "GIORNI_NUOVI",
    "SEDUTE_LETTE",
    "SEDUTE_SENZA_MIGLIORARE",
]
