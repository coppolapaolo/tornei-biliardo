# models/competition/tabellone_view.py
"""Il tabellone intero, anche dove non si e' ancora giocato (issue #240).

`models/matchmaking/bracket_view.py` raggruppa i match **esistenti**: le
strategie a tabellone materializzano un turno per volta, quindi dopo il
sorteggio si vede il solo primo turno e il tabellone non risponde alla domanda
per cui esiste — chi incontrera' chi. Eppure l'albero e' gia' tutto
determinato: `bracket_schedule` dice quali round stanno in quale turno, e le
regole di avanzamento di ADR-038 dicono dove va chi vince e dove chi perde.
Mancano solo i nomi dei vincitori futuri, che e' esattamente cio' che un
tabellone appeso al muro lascia in bianco.

Qui si costruisce quell'albero, **senza scrivere niente** e senza i18n: i
nodi giocati sono i match, quelli futuri sono nodi vuoti con i due posti
riempiti per quanto si sa gia' (il vincitore di un quarto chiuso e' gia' in
semifinale). Le regole di avanzamento stanno in un punto solo,
`_uscite`: da li' discendono sia gli alimentatori dei nodi futuri sia la nota
della card «chi vince: semifinale contro chi vince A–B».

Le etichette («Semifinali», «Recupero 2», «Bella») sono valori simbolici
(`NomeRound`): le frasi le compone il template, dove sta `_()`.

Regole di dominio lette, non inventate:

* taglia del tabellone = due volte i nodi del primo turno (i bye sono nodi
  pieni, ADR-038); bye solo al primo turno dei vincenti;
* un bye non produce perdenti, quindi il nodo dei ripescati che ne avrebbe
  due non esiste mai, e quello che ne avrebbe uno e' una X;
* la finalina 3°/4° si gioca nello stesso turno della finale (Step 8), solo
  nell'eliminazione diretta o nel tabellone finale della formula a gironi;
* nella finale del doppio KO `player1` e' il campione dei vincenti: la bella
  esiste solo se vince `player2`;
* nei gironi FISBB si esce qualificati dall'ultimo turno dei vincenti e
  dall'ultimo recupero.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from models.matchmaking.bracket import (
    BRACKET_GRAND_FINAL,
    BRACKET_GRAND_FINAL_RESET,
    BRACKET_LOSERS,
    BRACKET_THIRD_PLACE,
    BRACKET_WINNERS,
    MIN_BRACKET_SIZE_DIRECT_ELIMINATION,
    MIN_BRACKET_SIZE_DOUBLE_KNOCKOUT,
    bracket_levels,
    bracket_schedule,
    bracket_size,
    final_bracket_size,
    group_count,
    group_format_total_rounds,
    group_phase_rounds,
    group_schedule,
    group_size_for,
    total_rounds,
)
from models.matchmaking.configuration import MatchmakingStrategy
from models.status_enum import MatchStatus

SEZIONE_VINCENTI = "winners"
SEZIONE_RIPESCATI = "losers"

_ORDINE_COLONNE = {
    BRACKET_WINNERS: 0,
    BRACKET_LOSERS: 0,
    BRACKET_THIRD_PLACE: 1,
    BRACKET_GRAND_FINAL: 2,
    BRACKET_GRAND_FINAL_RESET: 3,
}

# Il nome di un turno dei vincenti a eliminazione diretta dipende da quante
# partite contiene: una e' la finale, due le semifinali, e cosi' via.
_NOMI_PER_NODI = {
    1: "finale",
    2: "semifinali",
    4: "quarti",
    8: "ottavi",
    16: "sedicesimi",
}

Chiave = Tuple[str, int, int]


# ---------------------------------------------------------------------------
# I nomi
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NomeRound:
    """Il nome simbolico di un round, o di un turno di gara.

    `chiave`: finale, semifinali, quarti, ottavi, sedicesimi, turno (numero),
    vincenti (numero: il turno dei vincenti nel doppio KO), recupero (numero),
    finalina, bella, gironi (numero: il turno di gara della fase a gironi).
    """

    chiave: str
    numero: Optional[int] = None


def nome_colonna(
    bracket_type: str, bracket_round: int, *, taglia: int, con_ripescati: bool
) -> NomeRound:
    """Il nome di una colonna del tabellone.

    Nel doppio KO e nei gironi un turno dei vincenti non elimina nessuno, quindi
    «quarti» e «semifinali» non vogliono dire niente: resta il numero, come
    nella vista tabellone di sempre.
    """
    if bracket_type == BRACKET_GRAND_FINAL:
        return NomeRound("finale")
    if bracket_type == BRACKET_GRAND_FINAL_RESET:
        return NomeRound("bella")
    if bracket_type == BRACKET_THIRD_PLACE:
        return NomeRound("finalina")
    if bracket_type == BRACKET_LOSERS:
        return NomeRound("recupero", bracket_round)
    if con_ripescati:
        return NomeRound("turno", bracket_round)
    chiave = _NOMI_PER_NODI.get(taglia >> bracket_round)
    return NomeRound(chiave) if chiave else NomeRound("turno", bracket_round)


# ---------------------------------------------------------------------------
# I nodi
# ---------------------------------------------------------------------------


@dataclass
class Posto:
    """Un posto di un nodo: chi c'e', o da dove arrivera'.

    * `giocatore` noto (un `User`);
    * altrimenti `fonte`: il nodo da cui arriva e con quale esito
      («vincitore» o «perdente»);
    * `vuoto`: nessuno arrivera' mai, il nodo sara' una X;
    * nessuna delle tre: si sapra' al sorteggio (tabellone finale dei gironi).
    """

    giocatore: Any = None
    fonte: Optional["Fonte"] = None
    vuoto: bool = False

    @property
    def noto(self) -> bool:
        return self.giocatore is not None


@dataclass(frozen=True)
class Fonte:
    esito: str  # "vincitore" | "perdente"
    nodo: "Nodo"


@dataclass(eq=False)
class Nodo:
    """Un nodo dell'albero: un match giocato o da giocare, o uno futuro."""

    bracket_type: str
    bracket_round: int
    slot: int
    gruppo: Optional[int]
    turno: int
    nome: NomeRound
    match: Any = None
    posti: List[Posto] = field(default_factory=list)
    condizionale: bool = False

    @property
    def futuro(self) -> bool:
        return self.match is None

    @property
    def is_x(self) -> bool:
        if self.match is not None:
            return bool(getattr(self.match, "is_bye", False))
        return sum(1 for p in self.posti if p.vuoto) == 1

    @property
    def chiave(self) -> Chiave:
        return (self.bracket_type, self.bracket_round, self.slot)


@dataclass
class Colonna:
    bracket_type: str
    bracket_round: int
    turno: int
    nome: NomeRound
    nodi: List[Nodo]

    @property
    def is_losers(self) -> bool:
        return self.bracket_type == BRACKET_LOSERS

    @property
    def size(self) -> int:
        return len(self.nodi)


@dataclass
class Sezione:
    key: str
    columns: List[Colonna]


@dataclass
class Lavagna:
    """Un girone della formula FISBB, o il tabellone (finale o unico)."""

    group: Optional[int]
    sections: List[Sezione]

    @property
    def is_group(self) -> bool:
        return self.group is not None

    @property
    def has_losers(self) -> bool:
        return any(s.key == SEZIONE_RIPESCATI for s in self.sections)


@dataclass(frozen=True)
class Destinazione:
    """Dove va chi vince una partita, e contro chi; e dove scende chi perde.

    `tipo`: «nodo» (un altro turno, `nome` e `avversario`), «campione» (la
    finale dell'eliminazione diretta, la bella), «terzo» (la finalina),
    «qualificato» (fine del girone), «finale_doppio» (la finale del doppio
    KO: se vince chi arriva dai ripescati si gioca la bella).
    """

    tipo: str
    nome: Optional[NomeRound] = None
    avversario: Optional[Posto] = None
    perdente: Optional[NomeRound] = None


@dataclass
class Tabellone:
    """L'albero intero, pronto per la pagina del tabellone e quella del direttore."""

    lavagne: List[Lavagna]
    nodi: List[Nodo]
    doppio_ko: bool
    con_gironi: bool

    # -- letture -----------------------------------------------------------

    def nodo_del_match(self, match_id: int) -> Optional[Nodo]:
        for nodo in self.nodi:
            if nodo.match is not None and nodo.match.id == match_id:
                return nodo
        return None

    def nomi_turni(self) -> Dict[int, List[NomeRound]]:
        """Turno di gara → i nomi dei round che vi si giocano."""
        per_turno: Dict[int, List[NomeRound]] = {}
        for lavagna in self.lavagne:
            for sezione in lavagna.sections:
                for colonna in sezione.columns:
                    nomi = per_turno.setdefault(colonna.turno, [])
                    nome = _nome_nel_turno(colonna, lavagna, self)
                    if nome is not None and nome not in nomi:
                        nomi.append(nome)
        return dict(sorted(per_turno.items()))

    def compatto(self, turno: int, ampiezza: int = 1) -> List[Lavagna]:
        """Le sole colonne dei turni da `turno - ampiezza` a `turno + ampiezza`."""
        vicine: List[Lavagna] = []
        for lavagna in self.lavagne:
            sezioni = []
            for sezione in lavagna.sections:
                colonne = [
                    c for c in sezione.columns if abs(c.turno - turno) <= ampiezza
                ]
                if colonne:
                    sezioni.append(Sezione(sezione.key, colonne))
            if sezioni:
                vicine.append(Lavagna(lavagna.group, sezioni))
        return vicine


def _nome_nel_turno(
    colonna: Colonna, lavagna: Lavagna, tabellone: Tabellone
) -> Optional[NomeRound]:
    if lavagna.is_group:
        return NomeRound("gironi", colonna.turno)
    if colonna.bracket_type == BRACKET_THIRD_PLACE:
        return None  # sta nel turno della finale, che gia' lo nomina
    if tabellone.doppio_ko and not tabellone.con_gironi:
        if colonna.bracket_type == BRACKET_WINNERS:
            return NomeRound("vincenti", colonna.bracket_round)
    return colonna.nome


# ---------------------------------------------------------------------------
# Le regole di avanzamento: un posto solo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Struttura:
    """La forma di una lavagna: taglia, formato, dove comincia."""

    taglia: int
    doppio: bool  # si esce alla seconda sconfitta
    turni_girone: Optional[int]  # `w` nei gironi FISBB, None altrove
    finalina: bool
    offset: int  # turni di gara prima del primo round di questa lavagna


def _uscite(chiave: Chiave, s: _Struttura) -> Tuple[Any, Any]:
    """Dove va il vincitore e dove il perdente del nodo `chiave`.

    Ogni uscita e' `(chiave_destinazione, posto)`, oppure una stringa per le
    uscite dal tabellone («campione», «terzo», «qualificato»,
    «finale_doppio»), oppure None (chi perde e' fuori).
    """
    tipo, rnd, slot = chiave
    k = bracket_levels(s.taglia)

    if tipo == BRACKET_THIRD_PLACE:
        return "terzo", None
    if tipo == BRACKET_GRAND_FINAL_RESET:
        return "campione", None
    if tipo == BRACKET_GRAND_FINAL:
        return "finale_doppio", None

    if tipo == BRACKET_WINNERS:
        ultimo = s.turni_girone if s.turni_girone else k
        if rnd < ultimo:
            vince: Any = ((BRACKET_WINNERS, rnd + 1, slot // 2), slot % 2)
        elif s.turni_girone:
            vince = "qualificato"
        elif s.doppio:
            vince = ((BRACKET_GRAND_FINAL, 1, 0), 0)
        else:
            vince = "campione"

        perde: Any = None
        if s.doppio:
            if rnd == 1:
                perde = ((BRACKET_LOSERS, 1, slot // 2), slot % 2)
            else:
                # Round maggiore L_{2j}, j = rnd - 1: accoppia il perdente di
                # W_{j+1} con l'inversione σ(s) = n - 1 - s (involuzione).
                n = s.taglia >> rnd
                perde = ((BRACKET_LOSERS, 2 * (rnd - 1), n - 1 - slot), 1)
        elif s.finalina and rnd == k - 1 and k >= 2:
            perde = ((BRACKET_THIRD_PLACE, k, 0), slot)
        return vince, perde

    # Ripescati
    ultimo_l = 2 * s.turni_girone - 2 if s.turni_girone else 2 * k - 2
    if rnd >= ultimo_l:
        vince = "qualificato" if s.turni_girone else ((BRACKET_GRAND_FINAL, 1, 0), 1)
    elif rnd % 2 == 1:
        vince = ((BRACKET_LOSERS, rnd + 1, slot), 0)
    else:
        vince = ((BRACKET_LOSERS, rnd + 1, slot // 2), slot % 2)
    return vince, None


# ---------------------------------------------------------------------------
# La costruzione
# ---------------------------------------------------------------------------


def _finito(match: Any) -> bool:
    return bool(getattr(match, "is_bye", False)) or MatchStatus.is_finished(
        getattr(match, "status", None)
    )


def _vincitore(match: Any) -> Any:
    if getattr(match, "is_bye", False):
        return match.player1
    if match.winner_id is None:
        return None
    return match.player1 if match.winner_id == match.player1_id else match.player2


def _perdente(match: Any) -> Any:
    if getattr(match, "is_bye", False) or match.winner_id is None:
        return None
    return match.player2 if match.winner_id == match.player1_id else match.player1


def _posto_da(esito: str, nodo: Optional[Nodo]) -> Posto:
    """Il posto che un nodo alimenta con il suo vincitore o perdente."""
    if nodo is None:
        return Posto(vuoto=True)
    if nodo.match is not None:
        m = nodo.match
        if esito == "perdente" and getattr(m, "is_bye", False):
            return Posto(vuoto=True)
        if _finito(m):
            chi = _vincitore(m) if esito == "vincitore" else _perdente(m)
            return Posto(giocatore=chi) if chi is not None else Posto(vuoto=True)
        return Posto(fonte=Fonte(esito, nodo))
    # Nodo futuro: una X passa il suo unico giocatore e non ha perdenti.
    if nodo.is_x:
        if esito == "perdente":
            return Posto(vuoto=True)
        pieno = next(p for p in nodo.posti if not p.vuoto)
        return replace(pieno)
    return Posto(fonte=Fonte(esito, nodo))


def _schedule_lavagna(s: _Struttura) -> Dict[int, List[Tuple[str, int, int]]]:
    """Turno di gara → [(tipo, round, nodi a tabellone pieno)]."""
    if s.turni_girone:
        base = group_schedule(s.turni_girone)
    else:
        base = bracket_schedule(s.taglia, double_elimination=s.doppio)
    turni: Dict[int, List[Tuple[str, int, int]]] = {}
    for turno, rounds in base.items():
        for r in rounds:
            turni.setdefault(turno + s.offset, []).append(
                (r.bracket_type, r.bracket_round, r.n_matches)
            )
    if s.finalina and not s.doppio and s.taglia >= 4:
        k = bracket_levels(s.taglia)
        turni.setdefault(k + s.offset, []).append((BRACKET_THIRD_PLACE, k, 1))
    return turni


def _costruisci_lavagna(
    gruppo: Optional[int],
    s: _Struttura,
    reali: Dict[Chiave, Any],
    con_ripescati: bool,
    da_sorteggiare: bool = False,
) -> List[Nodo]:
    materializzati = {(t, r) for (t, r, _slot) in reali}
    nodi: Dict[Chiave, Nodo] = {}
    alimentatori: Dict[Chiave, Dict[int, Posto]] = {}

    for turno, rounds in sorted(_schedule_lavagna(s).items()):
        for tipo, rnd, quanti in rounds:
            nome = nome_colonna(tipo, rnd, taglia=s.taglia, con_ripescati=con_ripescati)
            for slot in range(quanti):
                chiave = (tipo, rnd, slot)
                match = reali.get(chiave)
                if match is not None:
                    posti = [
                        Posto(giocatore=match.player1),
                        (
                            Posto(vuoto=True)
                            if getattr(match, "is_bye", False)
                            else Posto(giocatore=match.player2)
                        ),
                    ]
                    nodo = Nodo(tipo, rnd, slot, gruppo, turno, nome, match, posti)
                elif (tipo, rnd) in materializzati:
                    continue  # il round e' nato: un nodo che non c'e' non c'e'
                elif tipo == BRACKET_WINNERS and rnd == 1:
                    if not da_sorteggiare:
                        continue
                    nodo = Nodo(
                        tipo, rnd, slot, gruppo, turno, nome, None, [Posto(), Posto()]
                    )
                elif tipo == BRACKET_GRAND_FINAL_RESET:
                    # La bella non ha alimentatori: la rigiocano i due della
                    # finale, e solo se l'ha vinta chi arrivava dai ripescati.
                    finale = nodi.get((BRACKET_GRAND_FINAL, 1, 0))
                    if finale is None:
                        continue
                    if finale.match is not None and _finito(finale.match):
                        if finale.match.winner_id != finale.match.player2_id:
                            continue  # l'ha vinta l'imbattuto: niente bella
                        posti = [
                            Posto(giocatore=finale.match.player1),
                            Posto(giocatore=finale.match.player2),
                        ]
                    else:
                        posti = [Posto(fonte=Fonte("vincitore", finale)), Posto()]
                    nodo = Nodo(tipo, rnd, slot, gruppo, turno, nome, None, posti, True)
                else:
                    arrivi = alimentatori.get(chiave, {})
                    posti = [
                        arrivi.get(0, Posto(vuoto=True)),
                        arrivi.get(1, Posto(vuoto=True)),
                    ]
                    if all(p.vuoto for p in posti):
                        continue  # nessuno arrivera' mai: il nodo non esiste
                    nodo = Nodo(tipo, rnd, slot, gruppo, turno, nome, None, posti)
                nodi[chiave] = nodo

                vince, perde = _uscite(chiave, s)
                for esito, uscita in (("vincitore", vince), ("perdente", perde)):
                    if isinstance(uscita, tuple):
                        dest, posto = uscita
                        alimentatori.setdefault(dest, {})[posto] = _posto_da(
                            esito, nodo
                        )
    return list(nodi.values())


def _lavagne_da_nodi(nodi: Sequence[Nodo]) -> List[Lavagna]:
    per_gruppo: Dict[Optional[int], Dict[Tuple[str, int], List[Nodo]]] = {}
    for nodo in nodi:
        colonne = per_gruppo.setdefault(nodo.gruppo, {})
        colonne.setdefault((nodo.bracket_type, nodo.bracket_round), []).append(nodo)

    lavagne: List[Lavagna] = []
    for gruppo in sorted(per_gruppo, key=lambda g: (g is None, g or 0)):
        vincenti: List[Colonna] = []
        ripescati: List[Colonna] = []
        for (tipo, rnd), membri in per_gruppo[gruppo].items():
            membri.sort(key=lambda n: n.slot)
            colonna = Colonna(tipo, rnd, membri[0].turno, membri[0].nome, membri)
            (ripescati if colonna.is_losers else vincenti).append(colonna)
        sezioni = []

        def ordine(c: Colonna) -> Tuple[int, int]:
            return (_ORDINE_COLONNE.get(c.bracket_type, 0), c.bracket_round)

        if vincenti:
            sezioni.append(Sezione(SEZIONE_VINCENTI, sorted(vincenti, key=ordine)))
        if ripescati:
            sezioni.append(Sezione(SEZIONE_RIPESCATI, sorted(ripescati, key=ordine)))
        lavagne.append(Lavagna(gruppo, sezioni))
    return lavagne


def costruisci_tabellone(
    matches: Iterable[Any], *, strategy: str, finalina: bool = False
) -> Optional[Tabellone]:
    """L'albero del tabellone di una gara, con i nodi futuri.

    None se la gara non ha ancora un tabellone (nessuna coordinata: prima del
    sorteggio, o gara antecedente alla persistenza del tabellone).
    """
    doppio_ko = strategy == MatchmakingStrategy.DOUBLE_KNOCKOUT.value
    per_gruppo: Dict[Optional[int], Dict[Chiave, Any]] = {}
    for match in matches:
        tipo = getattr(match, "bracket_type", None)
        if not tipo or getattr(match, "bracket_slot", None) is None:
            continue
        chiave = (tipo, match.bracket_round or 1, match.bracket_slot)
        per_gruppo.setdefault(getattr(match, "bracket_group", None), {})[chiave] = match
    if not per_gruppo:
        return None

    def taglia_di(reali: Dict[Chiave, Any]) -> int:
        primi = sum(1 for (t, r, _s) in reali if t == BRACKET_WINNERS and r == 1)
        return max(2, 2 * primi)

    gironi = sorted(g for g in per_gruppo if g is not None)
    nodi: List[Nodo] = []
    if gironi:
        taglia_girone = taglia_di(per_gruppo[gironi[0]])
        w = bracket_levels(taglia_girone) - 1
        for g in gironi:
            s = _Struttura(taglia_girone, True, w, False, 0)
            nodi += _costruisci_lavagna(g, s, per_gruppo[g], con_ripescati=True)
        finale = per_gruppo.get(None, {})
        taglia_finale = taglia_di(finale) if finale else final_bracket_size(len(gironi))
        s = _Struttura(taglia_finale, False, None, finalina, group_phase_rounds(w))
        nodi += _costruisci_lavagna(
            None, s, finale, con_ripescati=False, da_sorteggiare=not finale
        )
    else:
        reali = per_gruppo[None]
        s = _Struttura(taglia_di(reali), doppio_ko, None, finalina and not doppio_ko, 0)
        nodi += _costruisci_lavagna(None, s, reali, con_ripescati=doppio_ko)

    return Tabellone(
        lavagne=_lavagne_da_nodi(nodi),
        nodi=nodi,
        doppio_ko=doppio_ko,
        con_gironi=bool(gironi),
    )


# ---------------------------------------------------------------------------
# Le domande della pagina del direttore
# ---------------------------------------------------------------------------


def destinazione(tabellone: Tabellone, match_id: int) -> Optional[Destinazione]:
    """Dove va chi vince il match, e contro chi (la nota della card)."""
    nodo = tabellone.nodo_del_match(match_id)
    if nodo is None:
        return None
    indice = {(n.gruppo, n.chiave): n for n in tabellone.nodi}
    struttura = _struttura_di(tabellone, nodo)
    vince, perde = _uscite(nodo.chiave, struttura)

    perdente = None
    if isinstance(perde, tuple):
        dest_perdente = indice.get((nodo.gruppo, perde[0]))
        if dest_perdente is not None:
            perdente = dest_perdente.nome

    if not isinstance(vince, tuple):
        return Destinazione(tipo=vince, perdente=perdente)
    dest, posto = vince
    arrivo = indice.get((nodo.gruppo, dest))
    if arrivo is None:
        return None
    return Destinazione(
        tipo="nodo",
        nome=arrivo.nome,
        avversario=arrivo.posti[1 - posto],
        perdente=perdente,
    )


def _struttura_di(tabellone: Tabellone, nodo: Nodo) -> _Struttura:
    stessa = [n for n in tabellone.nodi if n.gruppo == nodo.gruppo]
    primi = [
        n for n in stessa if n.bracket_type == BRACKET_WINNERS and n.bracket_round == 1
    ]
    taglia = max(2, 2 * len(primi))
    if nodo.gruppo is not None:
        return _Struttura(taglia, True, bracket_levels(taglia) - 1, False, 0)
    finalina = any(n.bracket_type == BRACKET_THIRD_PLACE for n in stessa)
    doppio = tabellone.doppio_ko and not tabellone.con_gironi
    return _Struttura(taglia, doppio, None, finalina, 0)


def destinazioni(
    tabellone: Optional[Tabellone], matches: Iterable[Any]
) -> Dict[int, Destinazione]:
    if tabellone is None:
        return {}
    risultato: Dict[int, Destinazione] = {}
    for match in matches:
        dest = destinazione(tabellone, match.id)
        if dest is not None:
            risultato[match.id] = dest
    return risultato


# ---------------------------------------------------------------------------
# La forma prima del sorteggio
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FormaTabellone:
    """«Tabellone da 8 · 2 passano il turno · 3 turni», dagli iscritti."""

    iscritti: int
    posti: int
    passano: int
    turni: int
    con_bella: bool = False
    gironi: int = 0
    posti_girone: int = 0
    posti_finale: int = 0


def forma_tabellone(
    iscritti: int, strategy: str, *, double_ko_rounds: Optional[int] = None
) -> Optional[FormaTabellone]:
    """La forma che il sorteggio darebbe con `iscritti` giocatori.

    None sotto il pavimento del formato: con meno iscritti il sorteggio non
    parte, e una forma inventata direbbe una cosa falsa.
    """
    doppio = strategy == MatchmakingStrategy.DOUBLE_KNOCKOUT.value
    if strategy not in (
        MatchmakingStrategy.DIRECT_ELIMINATION.value,
        MatchmakingStrategy.DOUBLE_KNOCKOUT.value,
    ):
        return None
    pavimento = (
        MIN_BRACKET_SIZE_DOUBLE_KNOCKOUT
        if doppio
        else MIN_BRACKET_SIZE_DIRECT_ELIMINATION
    )
    if iscritti < pavimento:
        return None

    if doppio and double_ko_rounds:
        try:
            taglia_girone = group_size_for(double_ko_rounds)
            n_gironi = group_count(iscritti, taglia_girone)
            finale = final_bracket_size(n_gironi)
            turni = group_format_total_rounds(iscritti, double_ko_rounds)
        except ValueError:
            return None
        return FormaTabellone(
            iscritti=iscritti,
            posti=taglia_girone * n_gironi,
            passano=taglia_girone * n_gironi - iscritti,
            turni=turni,
            gironi=n_gironi,
            posti_girone=taglia_girone,
            posti_finale=finale,
        )

    posti = max(bracket_size(iscritti), pavimento)
    return FormaTabellone(
        iscritti=iscritti,
        posti=posti,
        passano=posti - iscritti,
        turni=total_rounds(posti, double_elimination=doppio),
        con_bella=doppio,
    )


# ---------------------------------------------------------------------------
# La classifica finale a bande (ADR-040)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RigaBanda:
    user: Any
    user_id: int
    position: int
    uscita: Optional[NomeRound] = None
    gruppo: Optional[int] = None
    vinta: bool = False  # l'ultima partita l'ha vinta (campione, finalina)


@dataclass(frozen=True)
class Banda:
    posizione: int
    ultima: int
    righe: Tuple[RigaBanda, ...]

    @property
    def condivisa(self) -> bool:
        return len(self.righe) > 1


def bande_finali(
    posizioni: Dict[int, int], tabellone: Optional[Tabellone]
) -> List[Banda]:
    """Le bande di pari merito, con il round in cui ciascuno e' uscito.

    `posizioni` e' `bracket_positions(gara)`: la banda e' la posizione (ADR-040),
    e i due quartifinalisti hanno lo stesso numero perche' sono usciti allo
    stesso punto. Il round d'uscita e' l'ultima partita giocata: dopo
    l'eliminazione non se ne giocano altre.
    """
    if not posizioni or tabellone is None:
        return []

    ultima: Dict[int, Nodo] = {}
    utenti: Dict[int, Any] = {}
    for nodo in tabellone.nodi:
        m = nodo.match
        if m is None or getattr(m, "is_bye", False) or not _finito(m):
            continue
        for giocatore in (m.player1, m.player2):
            if giocatore is None:
                continue
            utenti[giocatore.id] = giocatore
            prima = ultima.get(giocatore.id)
            if prima is None or (
                nodo.turno,
                _ORDINE_COLONNE.get(nodo.bracket_type, 0),
            ) > (
                prima.turno,
                _ORDINE_COLONNE.get(prima.bracket_type, 0),
            ):
                ultima[giocatore.id] = nodo
    # Chi e' passato solo per X e poi non ha giocato (non accade a gara
    # conclusa, ma l'utente va comunque trovato).
    for nodo in tabellone.nodi:
        for posto in nodo.posti:
            if posto.giocatore is not None:
                utenti.setdefault(posto.giocatore.id, posto.giocatore)

    per_posizione: Dict[int, List[RigaBanda]] = {}
    for user_id, posizione in posizioni.items():
        utente = utenti.get(user_id)
        if utente is None:
            continue
        nodo = ultima.get(user_id)
        per_posizione.setdefault(posizione, []).append(
            RigaBanda(
                user=utente,
                user_id=user_id,
                position=posizione,
                uscita=nodo.nome if nodo else None,
                gruppo=nodo.gruppo if nodo else None,
                vinta=bool(nodo and nodo.match.winner_id == user_id),
            )
        )

    bande = []
    for posizione in sorted(per_posizione):
        righe = tuple(
            sorted(per_posizione[posizione], key=lambda r: r.user.username.lower())
        )
        bande.append(Banda(posizione, posizione + len(righe) - 1, righe))
    return bande


__all__ = [
    "Banda",
    "Colonna",
    "Destinazione",
    "FormaTabellone",
    "Fonte",
    "Lavagna",
    "Nodo",
    "NomeRound",
    "Posto",
    "RigaBanda",
    "Sezione",
    "Tabellone",
    "bande_finali",
    "costruisci_tabellone",
    "destinazione",
    "destinazioni",
    "forma_tabellone",
    "nome_colonna",
]
