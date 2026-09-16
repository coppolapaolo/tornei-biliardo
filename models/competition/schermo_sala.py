"""Lo schermo in sala (canvas «Pagina gara del direttore», schermata 3.10).

La pagina che il direttore proietta sulla TV della sala: pubblica, senza
menu, da leggere a tre metri. In testa la locandina della vetrina, sotto i
tavoli con le partite in corso — nome grande, punteggio grandissimo — e a
destra la classifica dopo l'ultimo turno chiuso con il turno prima.

Una partita che finisce non deve sparire (issue #443): resta sulla casella
del tavolo dove si è giocata — che intanto risulta libero — e se quel tavolo
è già tornato in uso passa nell'elenco accanto alla classifica. Che la
classifica invece non si muova fino a fine turno è voluto: in formula Amalfi
è la base con cui si abbina il turno dopo, e aggiornarla a metà turno
ordinerebbe anche per «chi ha finito prima».

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

from dataclasses import dataclass, field, replace
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
    #: La partita che su questo tavolo si e' appena conclusa (issue #443).
    #: Il tavolo e' libero davvero — `libero` resta vero e la casella lo
    #: dichiara — ma il risultato ha ancora un posto dove stare.
    conclusa: Tuple[LatoTavolo, ...] = ()

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
    """Un posto di un nodo. Senza `nome` si dice chi arrivera'.

    Se chi arrivera' esce da una partita gia' nata, `esito` («vincitore» o
    «perdente») e `da` (i due nomi) lo dicono per esteso, e `tavolo` e' il
    tavolo su cui quella partita si sta giocando: lo schermo lo scrive in una
    riga sola quando lo spazio non basta per due nomi. Altrimenti resta il
    `posto` del tabellone, che il template racconta a parole.
    """

    nome: Optional[str] = None
    punti: Optional[int] = None
    vince: bool = False
    posto: Optional[Posto] = None
    esito: Optional[str] = None
    da: Tuple[str, ...] = ()
    tavolo: Optional[str] = None


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

    @property
    def stretto(self) -> bool:
        """Poco spazio per nodo: piu' di quattro righe, o i due rami del doppio KO.

        Allora un posto futuro che esce da una partita in corso si scrive col
        tavolo invece che con i due nomi, che stanno gia' in grande sulla sua
        casella.
        """
        return self.righe > 4 or any(lavagna.con_ripescati for lavagna in self.lavagne)


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
    #: Le partite del turno **in corso** gia' concluse che su un tavolo non
    #: stanno: quello e' tornato in uso, e' promesso alla prossima partita,
    #: o la gara non ha tavoli dichiarati (issue #443).
    chiuse_del_turno: List[PartitaChiusa] = field(default_factory=list)
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


def _lati_tavolo(m) -> Tuple[LatoTavolo, ...]:
    """I due nomi col punteggio, o i tre del trio; pieno chi non e' dietro."""
    trio = m.trio_match if getattr(m, "is_trio", False) else None
    if trio is not None:
        return tuple(
            LatoTavolo(_nome(p), punti or 0, True)
            for p, punti in (
                (trio.player1, trio.player1_racks),
                (trio.player2, trio.player2_racks),
                (trio.player3, trio.player3_racks),
            )
        )
    s1, s2 = m.player1_score or 0, m.player2_score or 0
    return (
        LatoTavolo(_nome(m.player1), s1, s1 >= s2),
        LatoTavolo(_nome(m.player2), s2, s2 >= s1),
    )


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
        caselle.append(
            TavoloSala(
                nome=tessera.nome,
                lati=_lati_tavolo(m),
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


def _partita_chiusa(m) -> PartitaChiusa:
    return PartitaChiusa(
        _nome(m.player1),
        m.player1_score or 0,
        _nome(m.player2),
        m.player2_score or 0,
    )


def _partite_chiuse(matches: List, numero: int) -> List:
    """Le partite **giocate** e concluse del turno `numero`, per id.

    Fuori restano la X, che non si gioca, e il trio, che ha tre punteggi e
    non entra in una riga a due.
    """
    return sorted(
        (
            m
            for m in matches
            if m.round_number == numero
            and MatchStatus.is_finished(m.status)
            and not m.is_bye
            and not getattr(m, "is_trio", False)
        ),
        key=lambda m: m.id or 0,
    )


def _piazza_le_concluse(
    caselle: List[TavoloSala], chiuse: List
) -> Tuple[List[TavoloSala], List[PartitaChiusa]]:
    """Rimette ogni partita conclusa sul tavolo dove si e' giocata.

    Il tavolo si legge da `played_on_table` e non da `table_assignment`:
    quest'ultima dice chi occupa cosa *adesso* e viene azzerata proprio alla
    chiusura, per rimettere il tavolo in circolo. Il fatto «si e' giocata al
    tavolo 3» vive nella colonna sua (issue #154).

    La casella pero' non e' sempre libera di ospitarlo: quando i tavoli sono
    pochi quel tavolo e' gia' tornato in uso, o e' promesso alla prossima
    partita in attesa — e li' vince l'informazione operativa, chi deve
    andare al tavolo. Chi resta senza posto finisce nel secondo valore, che
    lo schermo elenca accanto alla classifica: il risultato si sposta, non
    si perde. Stessa sorte per le gare senza tavoli dichiarati, dove caselle
    non ce ne sono affatto.
    """
    per_tavolo: Dict[str, List] = {}
    altrove: List = []
    for m in chiuse:
        tavolo = getattr(m, "played_on_table", None)
        if tavolo:
            per_tavolo.setdefault(str(tavolo), []).append(m)
        else:
            altrove.append(m)

    nuove: List[TavoloSala] = []
    for casella in caselle:
        del_tavolo = per_tavolo.pop(str(casella.nome), [])
        # Sullo stesso tavolo puo' essersene chiusa piu' d'una: la casella
        # mostra l'ultima, le altre scendono nell'elenco.
        ultima = del_tavolo.pop() if del_tavolo else None
        altrove.extend(del_tavolo)
        if ultima is not None and casella.libero and casella.prossima is None:
            nuove.append(replace(casella, conclusa=_lati_tavolo(ultima)))
        else:
            nuove.append(casella)
            if ultima is not None:
                altrove.append(ultima)
    for senza_casella in per_tavolo.values():
        altrove.extend(senza_casella)

    altrove.sort(key=lambda m: m.id or 0)
    return nuove, [_partita_chiusa(m) for m in altrove]


def _lato_futuro(posto: Posto) -> LatoNodo:
    """Il posto di un nodo non ancora nato: chi c'e', o da quale partita."""
    if posto.noto:
        return LatoNodo(nome=posto.giocatore.username)
    fonte = posto.fonte
    partita = fonte.nodo.match if fonte is not None else None
    if (
        fonte is not None
        and partita is not None
        and partita.player1 is not None
        and partita.player2 is not None
    ):
        in_gioco = stato_partita(partita) in (
            StatoPartita.IN_CORSO,
            StatoPartita.DA_VALIDARE,
        )
        return LatoNodo(
            esito=fonte.esito,
            da=(_nome(partita.player1), _nome(partita.player2)),
            tavolo=partita.table_assignment if in_gioco else None,
        )
    return LatoNodo(posto=posto)


def _nodo_sala(nodo: Nodo) -> NodoSala:
    m = nodo.match
    if m is None:
        return NodoSala(
            stato=StatoNodo.VUOTO,
            lati=tuple(_lato_futuro(p) for p in nodo.posti if not p.vuoto),
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
    chiuse_del_turno: List[PartitaChiusa] = []
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
            # A turno concluso le stesse partite stanno gia' tutte sotto
            # «turno prima», qui sotto: elencarle due volte non aggiunge.
            if not concluso:
                caselle, chiuse_del_turno = _piazza_le_concluse(
                    caselle, _partite_chiuse(partite, turno)
                )
        numero_turno_prima = _ultimo_turno_chiuso(
            partite, turno + 1 if concluso else turno
        )
        if numero_turno_prima:
            turno_prima = [
                _partita_chiusa(m) for m in _partite_chiuse(partite, numero_turno_prima)
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
        chiuse_del_turno=chiuse_del_turno,
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
