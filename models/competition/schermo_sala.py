"""Lo schermo in sala (canvas «Pagina gara del direttore», schermata 3.10).

La pagina che il direttore proietta sulla TV della sala: pubblica, senza
menu, da leggere a tre metri. In testa la locandina della vetrina, sotto i
tavoli con le partite in corso — nome grande, punteggio grandissimo — e a
destra la classifica dopo l'ultimo turno chiuso con il turno prima.

Questo modulo decide **cosa** si proietta e non tocca il database: riceve le
partite, le righe di classifica già calcolate e i tavoli della gara. La
classifica in particolare non si ricalcola qui, come per la vetrina
(`showcase_service.classifica_gia_calcolata`): la pagina è anonima e si
ricarica a ogni evento live, e un ricalcolo per ogni passaggio vorrebbe dire
scritture innescate da chiunque abbia il link.

Le gare a tabellone (issue #352) tengono i tavoli, ma nella colonna a destra
al posto della classifica mettono il turno del tabellone che si gioca e il
turno dopo, con i nodi futuri vuoti: a tre metri un tabellone da 16 o 32
intero non si legge. Nel doppio KO i vincenti stanno sopra e i ripescati
sotto, insieme e senza rotazione. A gara conclusa il podio e le bande della
classifica finale (ADR-040), dalle posizioni del tabellone che il chiamante
ha gia' letto. L'albero lo costruisce `tabellone_view`, qui si sceglie solo
la finestra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.competition.direttore_view import (
    StatoPartita,
    stato_partita,
    tavoli_del_turno,
)
from models.competition.tabellone_view import (
    Banda,
    Nodo,
    NomeRound,
    Posto,
    Tabellone,
    bande_finali,
    costruisci_tabellone,
    nome_del_nodo,
)
from models.matchmaking.configuration import BRACKET_STRATEGIES, MatchmakingStrategy
from models.status_enum import GaraStatus, MatchStatus


class FaseSchermo(str, Enum):
    """Che cosa mostra lo schermo, dallo stato della gara."""

    ATTESA = "attesa"
    GIOCO = "gioco"
    SPAREGGIO = "spareggio"
    CONCLUSA = "conclusa"
    #: Una gara a tabellone in gioco: tavoli e turno del tabellone.
    TABELLONE = "tabellone"


@dataclass(frozen=True)
class LatoTavolo:
    nome: str
    punti: int
    #: Pieno se e' in vantaggio o alla pari, spento se e' dietro.
    avanti: bool


@dataclass(frozen=True)
class TavoloSala:
    nome: str
    lati: Tuple[LatoTavolo, ...] = ()
    alla_distanza: bool = False
    #: Sul tavolo libero, la prossima partita in attesa («a – b»).
    prossima: Optional[str] = None
    #: Nelle gare a tabellone, il round della partita sul tavolo o in attesa.
    round: Optional[NomeRound] = None

    @property
    def libero(self) -> bool:
        return not self.lati


@dataclass(frozen=True)
class RigaSala:
    posizione: int
    nome: str
    valore: int
    #: La seconda colonna, gia' scritta: «+4» a vittorie, i persi a RACK.
    secondo: str


@dataclass(frozen=True)
class PartitaChiusa:
    p1: str
    s1: int
    p2: str
    s2: int

    @property
    def vince1(self) -> bool:
        return self.s1 > self.s2

    @property
    def vince2(self) -> bool:
        return self.s2 > self.s1


# ---------------------------------------------------------------------------
# Il turno del tabellone
# ---------------------------------------------------------------------------


class StatoNodo(str, Enum):
    VUOTO = "vuoto"  # il match non e' ancora nato
    DA_GIOCARE = "da_giocare"
    IN_CORSO = "in_corso"
    CONCLUSO = "concluso"
    X = "x"


@dataclass(frozen=True)
class LatoNodo:
    """Un posto di un nodo. Senza `nome` si dice chi arrivera' (`posto`)."""

    nome: Optional[str] = None
    punti: Optional[int] = None
    vince: bool = False
    posto: Optional[Posto] = None


@dataclass(frozen=True)
class NodoSala:
    stato: StatoNodo
    lati: Tuple[LatoNodo, ...]
    #: Un nodo futuro con un solo posto possibile: sara' una X.
    x: bool = False


@dataclass(frozen=True)
class ColonnaSala:
    nome: NomeRound
    turno: int
    #: La colonna del turno che si gioca; l'altra e' il turno dopo.
    attuale: bool
    nodi: Tuple[NodoSala, ...]


@dataclass(frozen=True)
class RamoSala:
    #: `winners` o `losers`, come le sezioni di `tabellone_view`.
    key: str
    colonne: Tuple[ColonnaSala, ...]


@dataclass(frozen=True)
class LavagnaSala:
    girone: Optional[int]
    rami: Tuple[RamoSala, ...]

    @property
    def con_ripescati(self) -> bool:
        return len(self.rami) > 1 or any(r.key == "losers" for r in self.rami)


@dataclass(frozen=True)
class TabelloneSala:
    lavagne: Tuple[LavagnaSala, ...]
    #: Il nome del turno di gara in corso: «Quarti», «Turno 2 dei vincenti ·
    #: Recupero 1».
    nomi_turno: Tuple[NomeRound, ...] = ()

    @property
    def righe(self) -> int:
        """Le righe di nodi impilate nella colonna: rami di tutte le lavagne."""
        return sum(
            max((len(c.nodi) for c in ramo.colonne), default=0)
            for lavagna in self.lavagne
            for ramo in lavagna.rami
        )


@dataclass(frozen=True)
class SchermoSala:
    fase: FaseSchermo
    turno: int
    turni: int
    iscritti: int
    tavoli: List[TavoloSala] = field(default_factory=list)
    classifica: List[RigaSala] = field(default_factory=list)
    #: Il turno della classifica; 0 vuol dire complessiva (formula casuale).
    turno_classifica: int = 0
    rack: bool = False
    turno_prima: List[PartitaChiusa] = field(default_factory=list)
    numero_turno_prima: Optional[int] = None
    #: Tutte le partite del turno che si vede sono chiuse.
    turno_concluso: bool = False
    #: Gare a tabellone in gioco: il turno del tabellone e quello dopo.
    tabellone: Optional[TabelloneSala] = None
    #: Gare a tabellone concluse: le bande della classifica finale.
    bande: List[Banda] = field(default_factory=list)

    @property
    def podio(self) -> List[Tuple[Any, ...]]:
        """I gradini del podio dalle bande: sul bronzo possono stare in due."""
        return [b.righe for b in self.bande if b.posizione <= 3]


def fase_schermo(gara) -> FaseSchermo:
    stato = gara.status
    if stato in (GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value):
        return FaseSchermo.ATTESA
    if gara.matchmaking_strategy in BRACKET_STRATEGIES:
        # Nel tabellone non si spareggia (ADR-040): o si gioca, o e' finita.
        if stato in (GaraStatus.COMPLETED.value, GaraStatus.CANCELLED.value):
            return FaseSchermo.CONCLUSA
        return FaseSchermo.TABELLONE
    if stato == GaraStatus.PLAYING.value:
        return FaseSchermo.GIOCO
    if stato == GaraStatus.AWAITING_SSR.value:
        return FaseSchermo.SPAREGGIO
    return FaseSchermo.CONCLUSA


def _nome(giocatore) -> str:
    return giocatore.username if giocatore is not None else ""


def _tavoli(
    matches: List,
    turno: int,
    tavoli: Sequence[str],
    rounds: Optional[Dict[int, NomeRound]] = None,
) -> List[TavoloSala]:
    """Le caselle dei tavoli: chi gioca e quanto sta, o la prossima in attesa.

    Le partite in attesa si distribuiscono sui tavoli liberi nell'ordine in
    cui sono nate, che e' anche l'ordine con cui l'app assegna il tavolo che
    si libera (`TableAssignmentService.release_and_reassign_table`).

    `rounds` da' a ogni partita di un tabellone il nome del suo round.
    """
    rounds = rounds or {}
    per_id = {m.id: m for m in matches}
    in_attesa = sorted(
        (
            m
            for m in matches
            if m.round_number == turno and stato_partita(m) == StatoPartita.DA_GIOCARE
        ),
        key=lambda m: m.id or 0,
    )
    coda = iter(in_attesa)
    caselle: List[TavoloSala] = []
    for tessera in tavoli_del_turno(matches, tavoli):
        if tessera.libero:
            prossima = next(coda, None)
            caselle.append(
                TavoloSala(
                    nome=tessera.nome,
                    prossima=(
                        f"{_nome(prossima.player1)} – {_nome(prossima.player2)}"
                        if prossima is not None
                        else None
                    ),
                    round=rounds.get(prossima.id) if prossima is not None else None,
                )
            )
            continue
        m = per_id[tessera.match_id]
        trio = m.trio_match if getattr(m, "is_trio", False) else None
        if trio is not None:
            lati = tuple(
                LatoTavolo(_nome(p), punti or 0, True)
                for p, punti in (
                    (trio.player1, trio.player1_racks),
                    (trio.player2, trio.player2_racks),
                    (trio.player3, trio.player3_racks),
                )
            )
        else:
            s1, s2 = m.player1_score or 0, m.player2_score or 0
            lati = (
                LatoTavolo(_nome(m.player1), s1, s1 >= s2),
                LatoTavolo(_nome(m.player2), s2, s2 >= s1),
            )
        caselle.append(
            TavoloSala(
                nome=tessera.nome,
                lati=lati,
                alla_distanza=stato_partita(m) == StatoPartita.DA_VALIDARE,
                round=rounds.get(m.id),
            )
        )
    return caselle


def _righe(rows: List) -> Tuple[List[RigaSala], bool]:
    """Le righe di classifica nelle colonne del sistema (ADR-047)."""
    rack = bool(rows) and bool(getattr(rows[0], "is_rack_ranking", False))
    righe: List[RigaSala] = []
    for r in rows:
        nome = _nome(r.user)
        if rack:
            persi = (
                "–"
                if r.racks_won is None
                else str(r.racks_won - (r.rack_difference or 0))
            )
            righe.append(RigaSala(r.position, nome, r.total_racks_value, persi))
        else:
            diff = r.ranking_rack_value
            righe.append(
                RigaSala(
                    r.position, nome, r.matches_won or 0, f"{diff:+d}" if diff else "0"
                )
            )
    return righe, rack


def _ultimo_turno_chiuso(matches: List, prima_di: int) -> Optional[int]:
    turni = sorted(
        {
            m.round_number
            for m in matches
            if m.round_number and m.round_number < prima_di
        },
        reverse=True,
    )
    for n in turni:
        if all(
            MatchStatus.is_finished(m.status) for m in matches if m.round_number == n
        ):
            return n
    return None


def _nodo_sala(nodo: Nodo) -> NodoSala:
    m = nodo.match
    if m is None:
        return NodoSala(
            stato=StatoNodo.VUOTO,
            lati=tuple(
                LatoNodo(
                    nome=p.giocatore.username if p.noto else None,
                    posto=None if p.noto else p,
                )
                for p in nodo.posti
                if not p.vuoto
            ),
            x=nodo.is_x,
        )
    if getattr(m, "is_bye", False):
        return NodoSala(
            stato=StatoNodo.X,
            lati=(LatoNodo(nome=_nome(m.player1), vince=True),),
            x=True,
        )
    stato = stato_partita(m)
    if stato == StatoPartita.CONCLUSA:
        stato_nodo = StatoNodo.CONCLUSO
    elif stato == StatoPartita.DA_GIOCARE:
        stato_nodo = StatoNodo.DA_GIOCARE
    else:
        stato_nodo = StatoNodo.IN_CORSO
    concluso = stato_nodo == StatoNodo.CONCLUSO
    lati = []
    for giocatore, punti in (
        (m.player1, m.player1_score),
        (m.player2, m.player2_score),
    ):
        lati.append(
            LatoNodo(
                nome=_nome(giocatore) or None,
                # A partita non ancora cominciata lo 0-0 non dice niente.
                punti=(
                    (punti or 0)
                    if concluso or stato_nodo == StatoNodo.IN_CORSO
                    else None
                ),
                vince=bool(
                    concluso and giocatore is not None and m.winner_id == giocatore.id
                ),
            )
        )
    return NodoSala(stato=stato_nodo, lati=tuple(lati))


def turno_del_tabellone(tabellone: Tabellone, turno: int) -> TabelloneSala:
    """Il turno di gara `turno` e quello dopo, gia' fissato dall'albero.

    Fra un turno e l'altro `turno` e' quello appena chiuso (`display_round`):
    si vede chi ha vinto accanto a dove va.
    """
    lavagne = []
    for lavagna in tabellone.finestra(turno, turno + 1):
        rami = tuple(
            RamoSala(
                key=sezione.key,
                colonne=tuple(
                    ColonnaSala(
                        nome=colonna.nome,
                        turno=colonna.turno,
                        attuale=colonna.turno == turno,
                        nodi=tuple(_nodo_sala(n) for n in colonna.nodi),
                    )
                    for colonna in sezione.columns
                ),
            )
            for sezione in lavagna.sections
        )
        lavagne.append(LavagnaSala(girone=lavagna.group, rami=rami))
    return TabelloneSala(
        lavagne=tuple(lavagne),
        nomi_turno=tuple(tabellone.nomi_turni().get(turno, [])),
    )


def schermo_sala(
    gara,
    matches: Iterable,
    classifica: Iterable,
    tavoli: Sequence[str],
    iscritti: int,
    *,
    posizioni: Optional[Dict[int, int]] = None,
) -> SchermoSala:
    """Tutto quello che lo schermo in sala mostra, per questa gara.

    `posizioni` e' `bracket_positions(gara)` per le gare a tabellone
    concluse: la lettura sta nel chiamante, perche' qui non si interroga il
    database.
    """
    fase = fase_schermo(gara)
    partite = list(matches)
    righe_classifica = list(classifica)
    turno = gara.display_round or 0
    turni = gara.rounds_count or turno
    righe, rack = _righe(righe_classifica)

    turno_classifica = 0
    if (
        righe_classifica
        and gara.matchmaking_strategy != MatchmakingStrategy.RANDOM.value
    ):
        turno_classifica = righe_classifica[0].round_number

    albero: Optional[Tabellone] = None
    if gara.matchmaking_strategy in BRACKET_STRATEGIES:
        albero = costruisci_tabellone(
            partite,
            strategy=gara.matchmaking_strategy,
            finalina=bool(getattr(gara, "third_place_match", False)),
        )

    del_turno = [m for m in partite if m.round_number == turno]
    concluso = bool(del_turno) and all(
        MatchStatus.is_finished(m.status) for m in del_turno
    )

    caselle: List[TavoloSala] = []
    turno_prima: List[PartitaChiusa] = []
    numero_turno_prima: Optional[int] = None
    tabellone: Optional[TabelloneSala] = None
    bande: List[Banda] = []

    if fase == FaseSchermo.TABELLONE:
        rounds: Dict[int, NomeRound] = {}
        if albero is not None:
            rounds = {
                n.match.id: nome_del_nodo(albero, n)
                for n in albero.nodi
                if n.match is not None
            }
            tabellone = turno_del_tabellone(albero, turno)
        caselle = _tavoli(partite, turno, tavoli, rounds)
    elif fase in (FaseSchermo.GIOCO, FaseSchermo.SPAREGGIO):
        if fase == FaseSchermo.GIOCO:
            caselle = _tavoli(partite, turno, tavoli)
        numero_turno_prima = _ultimo_turno_chiuso(
            partite, turno + 1 if concluso else turno
        )
        if numero_turno_prima:
            turno_prima = [
                PartitaChiusa(
                    _nome(m.player1),
                    m.player1_score or 0,
                    _nome(m.player2),
                    m.player2_score or 0,
                )
                for m in partite
                if m.round_number == numero_turno_prima
                and not m.is_bye
                and not getattr(m, "is_trio", False)
            ]
    elif fase == FaseSchermo.CONCLUSA and albero is not None and posizioni:
        bande = bande_finali(posizioni, albero)

    return SchermoSala(
        fase=fase,
        turno=turno,
        turni=turni,
        iscritti=iscritti,
        tavoli=caselle,
        classifica=righe,
        turno_classifica=turno_classifica,
        rack=rack,
        turno_prima=turno_prima,
        numero_turno_prima=numero_turno_prima,
        turno_concluso=concluso,
        tabellone=tabellone,
        bande=bande,
    )


__all__ = [
    "ColonnaSala",
    "FaseSchermo",
    "LatoNodo",
    "LatoTavolo",
    "LavagnaSala",
    "NodoSala",
    "PartitaChiusa",
    "RamoSala",
    "RigaSala",
    "SchermoSala",
    "StatoNodo",
    "TabelloneSala",
    "TavoloSala",
    "fase_schermo",
    "schermo_sala",
    "turno_del_tabellone",
]
