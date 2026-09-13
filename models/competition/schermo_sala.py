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

Le gare a tabellone hanno una forma diversa, ancora da disegnare (issue
#352): lo schermo lo dice invece di mostrare una classifica di turno che lì
non esiste.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Optional, Sequence, Tuple

from models.competition.direttore_view import (
    StatoPartita,
    stato_partita,
    tavoli_del_turno,
)
from models.matchmaking.configuration import BRACKET_STRATEGIES, MatchmakingStrategy
from models.status_enum import GaraStatus, MatchStatus


class FaseSchermo(str, Enum):
    """Che cosa mostra lo schermo, dallo stato della gara."""

    ATTESA = "attesa"
    GIOCO = "gioco"
    SPAREGGIO = "spareggio"
    CONCLUSA = "conclusa"
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


def fase_schermo(gara) -> FaseSchermo:
    stato = gara.status
    if stato in (GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value):
        return FaseSchermo.ATTESA
    if gara.matchmaking_strategy in BRACKET_STRATEGIES:
        return FaseSchermo.TABELLONE
    if stato == GaraStatus.PLAYING.value:
        return FaseSchermo.GIOCO
    if stato == GaraStatus.AWAITING_SSR.value:
        return FaseSchermo.SPAREGGIO
    return FaseSchermo.CONCLUSA


def _nome(giocatore) -> str:
    return giocatore.username if giocatore is not None else ""


def _tavoli(matches: List, turno: int, tavoli: Sequence[str]) -> List[TavoloSala]:
    """Le caselle dei tavoli: chi gioca e quanto sta, o la prossima in attesa.

    Le partite in attesa si distribuiscono sui tavoli liberi nell'ordine in
    cui sono nate, che e' anche l'ordine con cui l'app assegna il tavolo che
    si libera (`TableAssignmentService.release_and_reassign_table`).
    """
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


def schermo_sala(
    gara,
    matches: Iterable,
    classifica: Iterable,
    tavoli: Sequence[str],
    iscritti: int,
) -> SchermoSala:
    """Tutto quello che lo schermo in sala mostra, per questa gara."""
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

    caselle: List[TavoloSala] = []
    turno_prima: List[PartitaChiusa] = []
    numero_turno_prima: Optional[int] = None
    if fase in (FaseSchermo.GIOCO, FaseSchermo.SPAREGGIO):
        del_turno = [m for m in partite if m.round_number == turno]
        concluso = bool(del_turno) and all(
            MatchStatus.is_finished(m.status) for m in del_turno
        )
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
    )


__all__ = [
    "FaseSchermo",
    "LatoTavolo",
    "TavoloSala",
    "RigaSala",
    "PartitaChiusa",
    "SchermoSala",
    "fase_schermo",
    "schermo_sala",
]
