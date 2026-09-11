"""Lo storico delle gare concluse, di tutti, con i fatti di chi guarda.

È la pagina «Storico» del canvas «Tessera» (10/09): una riga per gara,
raggruppate per mese, con la ricerca per nome o sala e quattro filtri —
«che ho giocato», «che ho diretto», «nei primi N», l'anno. Niente filtro
per disciplina: deciso lì.

Due cose sono qui e non nella route perché sono regole, non impaginazione:

* **quali gare sono concluse**: la stessa domanda della dashboard
  (`is_conclusa`, che legge lo stato *reale*), così i conteggi tornano —
  la dashboard dice «le altre N sono nello storico» e qui ce ne devono
  essere N;
* **cosa vuol dire «mio»**: iscritto e non ritirato per «giocato»;
  direttore della gara, o assegnato a lei o al suo campionato, per
  «diretto». Sono i fatti, non i permessi: un admin dirige tutto per
  permesso ma non ha diretto niente.

Le funzioni di filtro e raggruppamento sono pure e lavorano su `RigaStorico`
già costruite: si provano senza database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from sqlalchemy import func, or_, tuple_
from sqlalchemy.orm import joinedload, selectinload

from models.base import db
from models.campionato.models import Campionato
from models.classification.models import GaraClassification, RoundClassification
from models.competition.models import Gara, Inscription
from models.match.models import Match
from models.dashboard.gara_cards import is_conclusa
from models.status_enum import EntityType, GaraStatus
from models.user.models import DirectorAssignment, User

#: Quante righe si mostrano per volta: «Mostra altre» ne aggiunge altrettante.
PASSO = 20

#: Le scelte di «nei primi N». Un numero libero sarebbe un campo da compilare
#: per una domanda che ha quattro risposte sensate.
SCELTE_PRIMI: Tuple[int, ...] = (1, 3, 5, 10)

CHI_TUTTE = "tutte"
CHI_GIOCATE = "giocate"
CHI_DIRETTE = "dirette"
SCELTE_CHI: Tuple[str, ...] = (CHI_TUTTE, CHI_GIOCATE, CHI_DIRETTE)

#: Solo da questi stati una gara può risultare conclusa: `COMPLETED` lo è
#: per definizione, le altre due lo diventano quando i turni sono tutti
#: giocati e il direttore non ha ancora premuto «Termina» (stato derivato).
_STATI_DA_VERIFICARE = (GaraStatus.PLAYING.value, GaraStatus.AWAITING_SSR.value)


@dataclass(frozen=True)
class FiltriStorico:
    """Cosa ha chiesto chi guarda. Immutabile: si passa in giro senza paura."""

    testo: str = ""
    chi: str = CHI_TUTTE
    primi: Optional[int] = None
    anno: Optional[int] = None
    mostra: int = PASSO

    @classmethod
    def da_parametri(cls, args: Mapping[str, Any]) -> "FiltriStorico":
        """Dai parametri dell'indirizzo, scartando ciò che non ha senso.

        Un valore fuori dalle scelte non è un errore da mostrare: è un link
        vecchio o un indirizzo scritto a mano, e la pagina risponde come se
        il filtro non ci fosse.
        """
        chi = str(args.get("chi") or CHI_TUTTE)
        primi = _intero(args.get("primi"))
        anno = _intero(args.get("anno"))
        mostra = _intero(args.get("mostra")) or PASSO
        return cls(
            testo=str(args.get("q") or "").strip(),
            chi=chi if chi in SCELTE_CHI else CHI_TUTTE,
            primi=primi if primi in SCELTE_PRIMI else None,
            anno=anno if anno and 2000 <= anno <= 2100 else None,
            mostra=max(mostra, PASSO),
        )

    def parametri(self, **cambi: Any) -> Dict[str, Any]:
        """I parametri per `url_for`, con qualche cambiamento: è così che i
        chip costruiscono il proprio link senza perdere gli altri filtri.
        I valori vuoti restano fuori dall'indirizzo."""
        valori: Dict[str, Any] = {
            "q": self.testo or None,
            "chi": None if self.chi == CHI_TUTTE else self.chi,
            "primi": self.primi,
            "anno": self.anno,
        }
        valori.update(cambi)
        return {k: v for k, v in valori.items() if v not in (None, "", CHI_TUTTE)}


def _intero(valore: Any) -> Optional[int]:
    try:
        return int(valore) if valore not in (None, "") else None
    except (TypeError, ValueError):
        return None


@dataclass
class RigaStorico:
    """Una gara conclusa come la vede una persona precisa."""

    gara: Any
    hai_giocato: bool = False
    hai_diretto: bool = False
    #: Chi ha vinto, se la classifica finale è stata pubblicata.
    vincitore: Optional[str] = None
    #: Dove è arrivato chi guarda, se l'ha giocata e c'è una classifica.
    piazzamento: Optional[int] = None

    @property
    def id(self) -> int:
        return self.gara.id

    @property
    def name(self) -> str:
        return self.gara.display_name

    @property
    def campionato_name(self) -> Optional[str]:
        campionato = getattr(self.gara, "campionato", None)
        return campionato.name if campionato is not None else None

    @property
    def date(self) -> Optional[date_cls]:
        return getattr(self.gara, "date", None)

    @property
    def location(self) -> Optional[str]:
        return getattr(self.gara, "location", None)

    @property
    def discipline(self) -> Optional[str]:
        return getattr(self.gara, "discipline", None)

    @property
    def anno(self) -> Optional[int]:
        return self.date.year if self.date else None

    def corrisponde(self, testo: str) -> bool:
        """La ricerca guarda nome, sala e campionato, senza badare alle
        maiuscole."""
        ago = testo.strip().lower()
        if not ago:
            return True
        campi = (self.name, self.location or "", self.campionato_name or "")
        return any(ago in (campo or "").lower() for campo in campi)


@dataclass
class StoricoGare:
    """Il risultato: le righe da mostrare e i numeri della riga di testa."""

    filtri: FiltriStorico
    #: Le righe mostrate, già tagliate a `filtri.mostra`.
    righe: List[RigaStorico]
    #: Quante ne corrispondono a tutti i filtri: «Mostra altre» conta da qui.
    totale: int
    #: I numeri della riga di testa, calcolati **prima** di «chi» e «nei
    #: primi»: «34 gare concluse nel 2026 · 9 giocate, 4 dirette» descrive
    #: l'anno, non il filtro che si è appena premuto.
    conteggio: int
    giocate: int
    dirette: int
    #: Gli anni in cui c'è almeno una gara conclusa, dal più recente.
    anni: List[int]

    @property
    def restanti(self) -> int:
        return max(self.totale - len(self.righe), 0)

    @property
    def altre(self) -> int:
        """Quante ne aggiunge il prossimo «Mostra altre»."""
        return min(self.restanti, PASSO)

    @property
    def gruppi(self) -> List[Tuple[Tuple[int, int], List[RigaStorico]]]:
        return raggruppa_per_mese(self.righe)


# --- le regole, senza database ------------------------------------------------


def filtra(righe: Iterable[RigaStorico], filtri: FiltriStorico) -> List[RigaStorico]:
    """Applica tutti i filtri, nell'ordine in cui sono scritti sulla pagina."""
    return [
        r
        for r in righe
        if r.corrisponde(filtri.testo)
        and (filtri.anno is None or r.anno == filtri.anno)
        and (filtri.chi != CHI_GIOCATE or r.hai_giocato)
        and (filtri.chi != CHI_DIRETTE or r.hai_diretto)
        and (
            filtri.primi is None
            or (r.piazzamento is not None and r.piazzamento <= filtri.primi)
        )
    ]


def ordina(righe: Iterable[RigaStorico]) -> List[RigaStorico]:
    """Dalla più recente; una gara senza data sta in fondo."""
    return sorted(
        righe,
        key=lambda r: (r.date or date_cls.min, r.id),
        reverse=True,
    )


def raggruppa_per_mese(
    righe: Iterable[RigaStorico],
) -> List[Tuple[Tuple[int, int], List[RigaStorico]]]:
    """Le righe, già ordinate, spezzate a ogni cambio di mese.

    La chiave è `(anno, mese)`; le gare senza data stanno sotto `(0, 0)`,
    che il template traduce in «Senza data». L'etichetta si forma lì, nella
    lingua di chi legge: qui non c'è una lingua.
    """
    gruppi: List[Tuple[Tuple[int, int], List[RigaStorico]]] = []
    for riga in righe:
        chiave = (riga.date.year, riga.date.month) if riga.date else (0, 0)
        if gruppi and gruppi[-1][0] == chiave:
            gruppi[-1][1].append(riga)
        else:
            gruppi.append((chiave, [riga]))
    return gruppi


def componi(righe: Iterable[RigaStorico], filtri: FiltriStorico) -> StoricoGare:
    """Da tutte le righe al risultato: filtri, numeri di testa, taglio."""
    tutte = ordina(righe)
    base = filtra(tutte, FiltriStorico(testo=filtri.testo, anno=filtri.anno))
    scelte = filtra(base, filtri)
    return StoricoGare(
        filtri=filtri,
        righe=scelte[: filtri.mostra],
        totale=len(scelte),
        conteggio=len(base),
        giocate=sum(1 for r in base if r.hai_giocato),
        dirette=sum(1 for r in base if r.hai_diretto),
        anni=sorted({r.anno for r in tutte if r.anno is not None}, reverse=True),
    )


# --- il database ---------------------------------------------------------------


def _gare_concluse() -> List[Gara]:
    """Tutte le gare concluse visibili: di campionato e standalone.

    Le `COMPLETED` lo sono per stato e non hanno bisogno delle partite; le
    altre candidate vanno lette con le partite precaricate, perché è da
    quelle che lo stato reale si deduce. Due query, non una per gara.
    Il filtro soft-delete e quello della competizione di prova (ADR-058)
    sono di sessione e si applicano da soli; il campionato eliminato va
    escluso a mano, perché la gara non lo sa.
    """
    base = (
        db.session.query(Gara)
        .outerjoin(Campionato, Gara.campionato_id == Campionato.id)
        .filter(or_(Gara.campionato_id.is_(None), Campionato.is_deleted.is_(False)))
        .options(joinedload(Gara.campionato))
    )
    concluse = base.filter(Gara.status == GaraStatus.COMPLETED.value).all()
    da_verificare = (
        base.filter(Gara.status.in_(_STATI_DA_VERIFICARE))
        .options(selectinload(Gara.matches))
        .all()
    )
    return concluse + [g for g in da_verificare if is_conclusa(g)]


def _fatti_di(user_id: int, gare: List[Gara]) -> Tuple[Set[int], Set[int]]:
    """Gli id delle gare che ho giocato e di quelle che ho diretto."""
    ids = [g.id for g in gare]
    if not ids:
        return set(), set()
    giocate = {
        gara_id
        for (gara_id,) in db.session.query(Inscription.gara_id)
        .filter(
            Inscription.user_id == user_id,
            Inscription.gara_id.in_(ids),
            Inscription.is_withdrawn.is_(False),
        )
        .all()
    }
    assegnate: Dict[str, Set[int]] = {
        EntityType.GARA.value: set(),
        EntityType.CAMPIONATO.value: set(),
    }
    for tipo, entity_id in (
        db.session.query(DirectorAssignment.entity_type, DirectorAssignment.entity_id)
        .filter(DirectorAssignment.user_id == user_id)
        .all()
    ):
        if tipo in assegnate:
            assegnate[tipo].add(entity_id)
    dirette = {
        g.id
        for g in gare
        if getattr(g, "director_id", None) == user_id
        or g.id in assegnate[EntityType.GARA.value]
        or (
            g.campionato_id is not None
            and g.campionato_id in assegnate[EntityType.CAMPIONATO.value]
        )
    }
    return giocate, dirette


def _classifiche(
    gare: List[Gara], user_id: Optional[int]
) -> Tuple[Dict[int, str], Dict[int, int]]:
    """Il vincitore di ogni gara e il piazzamento di chi guarda.

    La fonte è `GaraClassification`, che nasce quando il direttore preme
    «Termina». Una gara conclusa **per derivazione** — turni finiti, nessuno
    ha premuto — non ce l'ha ancora: per quelle si legge la classifica
    dell'ultimo turno, la stessa da cui `StateService.complete` ricava il
    vincitore. Due primi a pari merito non fanno un vincitore: come nella
    chiusura della gara, la casella resta vuota invece di scegliere a caso.
    """
    ids = [g.id for g in gare]
    if not ids:
        return {}, {}
    primi: Dict[int, List[str]] = {}
    piazzamenti: Dict[int, int] = {}
    con_classifica: Set[int] = set()

    def _accumula(righe: Iterable[Tuple[int, int, int, str]]) -> None:
        for gara_id, posizione, uid, username in righe:
            con_classifica.add(gara_id)
            if posizione == 1:
                primi.setdefault(gara_id, []).append(username)
            if user_id is not None and uid == user_id:
                piazzamenti[gara_id] = posizione

    condizioni = [GaraClassification.position == 1]
    if user_id is not None:
        condizioni.append(GaraClassification.user_id == user_id)
    _accumula(
        db.session.query(
            GaraClassification.gara_id,
            GaraClassification.position,
            GaraClassification.user_id,
            User.username,
        )
        .join(User, User.id == GaraClassification.user_id)
        .filter(GaraClassification.gara_id.in_(ids), or_(*condizioni))
        .all()
    )

    # Il turno finale è quello su cui `StateService.complete` legge il
    # vincitore: il più alto con partite (`effective_final_round`), non
    # `rounds_count` — uno spareggio aggiunge un turno oltre il programma e
    # la strategia casuale lascia `current_round` indietro. Una query per
    # tutte le gare senza classifica, non una per gara.
    ids_senza = [g.id for g in gare if g.id not in con_classifica]
    senza: List[Tuple[int, int]] = []
    if ids_senza:
        ultimo_turno = dict(
            db.session.query(Match.gara_id, func.max(Match.round_number))
            .filter(Match.gara_id.in_(ids_senza))
            .group_by(Match.gara_id)
            .all()
        )
        senza = [
            (g.id, ultimo_turno.get(g.id) or g.current_round or g.rounds_count)
            for g in gare
            if g.id in ids_senza
        ]
    if senza:
        condizioni_turno = [RoundClassification.position == 1]
        if user_id is not None:
            condizioni_turno.append(RoundClassification.user_id == user_id)
        _accumula(
            db.session.query(
                RoundClassification.gara_id,
                RoundClassification.position,
                RoundClassification.user_id,
                User.username,
            )
            .join(User, User.id == RoundClassification.user_id)
            .filter(
                tuple_(
                    RoundClassification.gara_id, RoundClassification.round_number
                ).in_(senza),
                or_(*condizioni_turno),
            )
            .all()
        )

    vincitori = {gid: nomi[0] for gid, nomi in primi.items() if len(nomi) == 1}
    return vincitori, piazzamenti


def costruisci_storico(filtri: FiltriStorico, user_id: Optional[int]) -> StoricoGare:
    """Lo storico per chi guarda: `user_id=None` è l'ospite, senza fatti."""
    gare = _gare_concluse()
    giocate, dirette = (
        _fatti_di(user_id, gare) if user_id is not None else (set(), set())
    )
    vincitori, piazzamenti = _classifiche(gare, user_id)
    righe = [
        RigaStorico(
            gara=g,
            hai_giocato=g.id in giocate,
            hai_diretto=g.id in dirette,
            vincitore=vincitori.get(g.id),
            piazzamento=piazzamenti.get(g.id),
        )
        for g in gare
    ]
    return componi(righe, filtri)


__all__ = [
    "CHI_DIRETTE",
    "CHI_GIOCATE",
    "CHI_TUTTE",
    "FiltriStorico",
    "PASSO",
    "RigaStorico",
    "SCELTE_CHI",
    "SCELTE_PRIMI",
    "StoricoGare",
    "componi",
    "costruisci_storico",
    "filtra",
    "ordina",
    "raggruppa_per_mese",
]
