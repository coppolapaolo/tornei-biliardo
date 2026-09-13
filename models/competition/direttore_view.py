# models/competition/direttore_view.py
"""La pagina della gara vista da chi la dirige: in che fase è, e i numeri.

La pagina del direttore non ha più le quattro linguette (Turni / Classifica /
Iscritti / Gestione): mostra una **striscia di fase** — preparazione →
iscrizioni → gioco → [spareggio] → chiusura — e il contenuto è la fase in
corso. Qui si risponde, in Python e senza toccare il database, alle domande
che la pagina fa prima di disegnare:

* in che fase è la gara (`fase_della_gara`);
* quali tacche mostra la striscia e in che stato (`striscia`);
* quanto del turno è fatto: partite chiuse, tavoli occupati, risultati da
  validare, partite senza tavolo (`conteggi_turno`).

Il **comando** che la gara aspetta dal direttore (apri le iscrizioni, avvia
il turno, termina) non è calcolato qui: lo sa già `models/dashboard/
comandi.py`, che rispecchia i rami del pannello di gestione, e la fascia
scura della pagina lo legge da lì. Due macchine a stati per la stessa domanda
si staccherebbero al primo cambiamento.

Canvas di riferimento: `docs/redesign-7c/canvas-gara-direttore/` (decisione
2, «la striscia di fase», del 12/09/2026).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Optional, Sequence

from models.status_enum import GaraStatus, MatchStatus


class FaseGara(str, Enum):
    """Le fasi della striscia, nell'ordine in cui si attraversano."""

    PREPARAZIONE = "preparazione"
    ISCRIZIONI = "iscrizioni"
    GIOCO = "gioco"
    SPAREGGIO = "spareggio"
    CONCLUSA = "conclusa"


#: Lo stato persistito decide la fase; gli stati derivati (iscrizioni non
#: ancora aperte, scadute, turno concluso) restano dentro la stessa tacca e
#: cambiano solo la fascia. Una gara annullata è finita quanto una conclusa.
_FASE_PER_STATO = {
    GaraStatus.SETUP.value: FaseGara.PREPARAZIONE,
    GaraStatus.INSCRIPTION.value: FaseGara.ISCRIZIONI,
    GaraStatus.PLAYING.value: FaseGara.GIOCO,
    GaraStatus.AWAITING_SSR.value: FaseGara.SPAREGGIO,
    GaraStatus.COMPLETED.value: FaseGara.CONCLUSA,
    GaraStatus.CANCELLED.value: FaseGara.CONCLUSA,
}

_ORDINE = list(FaseGara)


def fase_della_gara(status: str) -> FaseGara:
    """La fase della striscia per uno `Gara.status`.

    Uno stato sconosciuto vale «in preparazione»: è la fase in cui la gara
    non è ancora visibile a nessuno, quindi l'errore meno costoso.
    """
    return _FASE_PER_STATO.get(status, FaseGara.PREPARAZIONE)


class StatoTacca(str, Enum):
    FATTA = "fatta"
    ATTIVA = "attiva"
    DA_FARE = "da_fare"


@dataclass(frozen=True)
class Tacca:
    fase: FaseGara
    stato: StatoTacca


def spareggio_nella_striscia(
    fase: FaseGara,
    *,
    ha_dati_ssr: bool = False,
    parimerito_aperti: bool = False,
    turni_conclusi: bool = False,
) -> bool:
    """La tacca dello spareggio compare solo nelle gare che ce l'hanno.

    Ce l'hanno: la gara che è nello spareggio adesso; quella che l'ha già
    giocato (ci sono punti SSR registrati); e quella in cui i turni sono
    finiti e c'è un pari merito da sciogliere — è il momento in cui la fascia
    dice «serve uno spareggio», e la striscia deve dire la stessa cosa.
    Mentre i turni si giocano non si sa, e una tacca «forse» non informa.
    """
    if fase == FaseGara.SPAREGGIO:
        return True
    if ha_dati_ssr:
        return True
    return turni_conclusi and parimerito_aperti


def striscia(fase: FaseGara, *, con_spareggio: bool) -> list[Tacca]:
    """Le tacche della striscia con il loro stato rispetto alla fase attiva."""
    attiva = _ORDINE.index(fase)
    tacche: list[Tacca] = []
    for i, f in enumerate(_ORDINE):
        if f == FaseGara.SPAREGGIO and not con_spareggio:
            continue
        if i < attiva:
            stato = StatoTacca.FATTA
        elif i == attiva:
            stato = StatoTacca.ATTIVA
        else:
            stato = StatoTacca.DA_FARE
        tacche.append(Tacca(fase=f, stato=stato))
    return tacche


@dataclass(frozen=True)
class ConteggiTurno:
    """Quanto del turno è fatto, per la card scura in cima alla fase di gioco.

    Le X a tavolino non si contano fra le partite: non si giocano e non
    occupano un tavolo. `da_validare` sono le partite arrivate alla distanza
    dal segnapunti dei giocatori senza la doppia conferma — l'unica cosa che
    chiede davvero il direttore mentre il turno gira — e `senza_tavolo` le
    partite da giocare che aspettano un tavolo libero.
    """

    turno: int
    turni_totali: int
    chiuse: int
    totali: int
    tavoli_occupati: int
    tavoli_totali: int
    da_validare: int
    senza_tavolo: int

    @property
    def aperte(self) -> int:
        return self.totali - self.chiuse

    @property
    def percentuale(self) -> int:
        if not self.totali:
            return 0
        return round(self.chiuse * 100 / self.totali)


def _e_da_validare(match) -> bool:
    if MatchStatus.is_finished(match.status):
        return False
    return bool(getattr(match, "is_at_distance", False)) and not bool(
        getattr(match, "is_player_validated", False)
    )


def conteggi_turno(
    matches: Iterable,
    turno: int,
    turni_totali: int,
    tavoli: Sequence[str],
    occupati: Optional[Mapping[str, int]] = None,
) -> ConteggiTurno:
    """I conteggi del turno `turno` a partire dalle partite della gara.

    `tavoli` è l'elenco dei tavoli della gara e `occupati` la mappa
    tavolo → partita in corso (`TableAssignmentService.get_occupied_tables`);
    senza la mappa, gli occupati si contano dai tavoli assegnati alle
    partite in corso del turno.
    """
    del_turno = [m for m in matches if m.round_number == turno and not m.is_bye]
    chiuse = sum(1 for m in del_turno if MatchStatus.is_finished(m.status))
    da_validare = sum(1 for m in del_turno if _e_da_validare(m))
    senza_tavolo = sum(
        1
        for m in del_turno
        if not MatchStatus.is_finished(m.status) and not m.table_assignment
    )
    if occupati is not None:
        tavoli_occupati = len(occupati)
    else:
        tavoli_occupati = sum(
            1
            for m in del_turno
            if m.status == MatchStatus.PLAYING.value and m.table_assignment
        )
    return ConteggiTurno(
        turno=turno,
        turni_totali=turni_totali,
        chiuse=chiuse,
        totali=len(del_turno),
        tavoli_occupati=tavoli_occupati,
        tavoli_totali=len(tavoli),
        da_validare=da_validare,
        senza_tavolo=senza_tavolo,
    )


# ---------------------------------------------------------------------------
# Le partite del turno (canvas 3.1–3.9)
# ---------------------------------------------------------------------------


class StatoPartita(str, Enum):
    """Lo stato con cui la card della partita si presenta al direttore.

    Non è lo stato persistito (`MatchStatus`): «da validare» è una partita
    ancora in corso arrivata alla distanza dal segnapunti dei giocatori senza
    la doppia conferma, e «da giocare» è una partita senza tavolo. La card
    cambia forma per ognuno (canvas 3.2–3.4).
    """

    X = "x"
    DA_VALIDARE = "da_validare"
    IN_CORSO = "in_corso"
    DA_GIOCARE = "da_giocare"
    CONCLUSA = "conclusa"


def stato_partita(match) -> StatoPartita:
    if getattr(match, "is_bye", False):
        return StatoPartita.X
    if MatchStatus.is_finished(match.status):
        return StatoPartita.CONCLUSA
    if _e_da_validare(match):
        return StatoPartita.DA_VALIDARE
    if match.table_assignment:
        return StatoPartita.IN_CORSO
    return StatoPartita.DA_GIOCARE


# L'ordine in pagina: prima cio' che chiede qualcosa al direttore, poi cio'
# che si gioca, poi cio' che aspetta, in coda cio' che e' chiuso; la X per
# ultima, non si gioca.
_ORDINE_CARD = {
    StatoPartita.DA_VALIDARE: 0,
    StatoPartita.IN_CORSO: 1,
    StatoPartita.DA_GIOCARE: 2,
    StatoPartita.CONCLUSA: 3,
    StatoPartita.X: 4,
}


def _gioca(match, user_id: Optional[int]) -> bool:
    if user_id is None:
        return False
    if match.player1_id == user_id or match.player2_id == user_id:
        return True
    trio = getattr(match, "trio_match", None)
    return bool(
        getattr(match, "is_trio", False) and trio and trio.player3_id == user_id
    )


def partite_del_turno(
    matches: Iterable, turno: int, user_id: Optional[int] = None
) -> list:
    """Le partite del turno nell'ordine della pagina (canvas 3.3 e 3.8).

    La partita del direttore che gioca sta in cima, qualunque sia il suo
    stato, finche' non e' chiusa: e' la sua. Poi le altre per stato, e a
    parita' per id, che e' l'ordine di creazione.
    """
    del_turno = [m for m in matches if m.round_number == turno]

    def chiave(m):
        stato = stato_partita(m)
        mia = _gioca(m, user_id) and stato != StatoPartita.CONCLUSA
        return (0 if mia else 1, _ORDINE_CARD[stato], m.id or 0)

    return sorted(del_turno, key=chiave)


def prima_in_attesa(matches: Iterable, turno: int):
    """La prima partita del turno che aspetta un tavolo, o `None`.

    E' quella a cui passa il tavolo che si libera
    (`TableAssignmentService.release_and_reassign_table`): la card «da
    validare» lo dice prima che succeda.
    """
    in_attesa = [
        m
        for m in matches
        if m.round_number == turno and stato_partita(m) == StatoPartita.DA_GIOCARE
    ]
    in_attesa.sort(key=lambda m: m.id or 0)
    return in_attesa[0] if in_attesa else None


def match_trio(match):
    return (
        getattr(match, "trio_match", None) if getattr(match, "is_trio", False) else None
    )


@dataclass(frozen=True)
class Tavolo:
    """Una tessera del foglio «Assegna il tavolo» e della colonna dei tavoli."""

    nome: str
    match_id: Optional[int] = None
    giocatori: tuple = ()

    @property
    def libero(self) -> bool:
        return self.match_id is None


def tavoli_del_turno(matches: Iterable, tavoli: Sequence[str]) -> list:
    """Le tessere dei tavoli: chi c'e' sopra, o libero.

    Un tavolo e' occupato dalla partita in corso che lo ha assegnato, in
    qualunque turno (con i turni pre-generati ne girano due insieme).
    """
    occupanti = {}
    for m in matches:
        if (
            m.table_assignment
            and not getattr(m, "is_bye", False)
            and not MatchStatus.is_finished(m.status)
        ):
            occupanti[str(m.table_assignment)] = m
    tessere = []
    for nome in tavoli:
        m = occupanti.get(str(nome))
        if m is None:
            tessere.append(Tavolo(nome=str(nome)))
        else:
            tessere.append(Tavolo(nome=str(nome), match_id=m.id, giocatori=_nomi(m)))
    return tessere


def _nomi(match) -> tuple:
    trio = match_trio(match)
    if trio is not None:
        return tuple(
            p.username for p in (trio.player1, trio.player2, trio.player3) if p
        )
    return tuple(p.username for p in (match.player1, match.player2) if p)


__all__ = [
    "FaseGara",
    "StatoTacca",
    "Tacca",
    "ConteggiTurno",
    "StatoPartita",
    "Tavolo",
    "fase_della_gara",
    "spareggio_nella_striscia",
    "striscia",
    "conteggi_turno",
    "stato_partita",
    "partite_del_turno",
    "prima_in_attesa",
    "tavoli_del_turno",
]
