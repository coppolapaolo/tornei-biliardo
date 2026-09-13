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
  validare, partite senza tavolo (`conteggi_turno`);
* cosa la gara riceve dal campionato che la contiene: numero, peso, playoff,
  regola di apertura ereditata, finestra delle date (`contesto_campionato`).

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
from datetime import date, time
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
    """Lo stato della card, per ogni forma di partita.

    * la X — anche quella con esercizio — resta `X`: non si gioca e non
      trattiene il turno; lo stato della prova lo dice `scheda_prova_x`;
    * il **trio** e' da validare quando i triangoli sono tutti giocati e il
      trio aspetta le conferme dei tre (`awaiting_confirmation`);
    * la partita **a set** non e' mai da validare: ogni set si chiude alla
      sua distanza e la partita ai set, senza firme da raccogliere.
    """
    if getattr(match, "is_bye", False):
        return StatoPartita.X
    if MatchStatus.is_finished(match.status):
        return StatoPartita.CONCLUSA
    trio = match_trio(match)
    if trio is not None:
        if getattr(trio, "awaiting_confirmation", False) and _e_da_validare(match):
            return StatoPartita.DA_VALIDARE
    elif not getattr(match, "is_multi_set", False) and _e_da_validare(match):
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


# ---------------------------------------------------------------------------
# Le forme della card: trio, partita a set, X con esercizio
# ---------------------------------------------------------------------------


class FormaPartita(str, Enum):
    """Quale card disegna la partita. La geometria e' una sola (nome sopra,
    numero grande sotto): cambia quanti lati ha e cosa segnano gli stepper."""

    DUE = "due"
    TRIO = "trio"
    SET = "set"
    X = "x"
    X_ESERCIZIO = "x_esercizio"


def forma_partita(match) -> FormaPartita:
    if getattr(match, "is_bye", False):
        if getattr(match, "is_x_with_challenge", False):
            return FormaPartita.X_ESERCIZIO
        return FormaPartita.X
    if match_trio(match) is not None:
        return FormaPartita.TRIO
    if getattr(match, "is_multi_set", False):
        return FormaPartita.SET
    return FormaPartita.DUE


@dataclass(frozen=True)
class SchedaTrio:
    """I tre lati del trio: triangoli vinti e quali «+» hanno senso.

    `massimo` sono i triangoli che ognuno gioca (due per girone), `totale`
    quelli del trio. Il bonus delle distanze dispari non si segna: non e' un
    triangolo giocato. `piu` dipende dall'ordine del girone
    (`models/match/trio_punteggio.py`), non solo dai due limiti.
    """

    trio_id: int
    ids: tuple
    nomi: tuple
    punti: tuple
    gironi: int
    massimo: int
    totale: int
    piu: tuple
    vincitore_id: Optional[int]


def scheda_trio(match) -> Optional[SchedaTrio]:
    from models.match.trio_punteggio import massimo_per_giocatore, piu_ammessi

    trio = match_trio(match)
    if trio is None:
        return None
    config = trio.trio_config
    punti = tuple(trio.player_racks_list)
    giocatori = (trio.player1, trio.player2, trio.player3)
    return SchedaTrio(
        trio_id=trio.id,
        ids=tuple(trio.player_ids),
        nomi=tuple(p.username if p else "" for p in giocatori),
        punti=punti,
        gironi=config.num_rounds,
        massimo=massimo_per_giocatore(config),
        totale=config.total_played_racks,
        piu=tuple(piu_ammessi(config, punti)),
        vincitore_id=trio.winner_id,
    )


@dataclass(frozen=True)
class SchedaSet:
    """La partita a set: i set vinti sopra, il set in corso sotto.

    `numero` e' il set che si gioca (None se nessuno e' in corso), `prossimo`
    quello da iniziare quando il set e' chiuso e la partita no. `chiusi` sono
    i set finiti come `(numero, triangoli 1, triangoli 2)`.
    """

    set_vinti: tuple
    set_da_vincere: int
    race_to_set: bool
    numero: Optional[int]
    punti: tuple
    distanza: int
    race_to: bool
    prossimo: Optional[int]
    chiusi: tuple

    @property
    def in_corso(self) -> bool:
        return self.numero is not None


def scheda_set(match) -> Optional[SchedaSet]:
    if not getattr(match, "is_multi_set", False) or getattr(match, "is_bye", False):
        return None
    sets = sorted(getattr(match, "sets", None) or [], key=lambda s: s.set_number)
    in_corso = next((s for s in sets if s.status == MatchStatus.PLAYING.value), None)
    chiusi = tuple(
        (s.set_number, s.player1_racks, s.player2_racks)
        for s in sets
        if s.status == MatchStatus.CLOSED_UNILATERALLY.value
    )
    distanza = match.distance_config
    finita = MatchStatus.is_finished(match.status)
    prossimo = None
    if in_corso is None and not finita:
        prossimo = len(sets) + 1
    riferimento = in_corso or (sets[-1] if sets else None)
    return SchedaSet(
        set_vinti=(match.player1_score or 0, match.player2_score or 0),
        set_da_vincere=distanza.get_winning_sets(),
        race_to_set=bool(distanza.is_race_to_sets),
        numero=in_corso.set_number if in_corso is not None else None,
        punti=(
            (in_corso.player1_racks, in_corso.player2_racks)
            if in_corso is not None
            else (0, 0)
        ),
        distanza=riferimento.distance if riferimento is not None else distanza.racks,
        race_to=(
            bool(riferimento.is_race_to)
            if riferimento is not None
            else bool(distanza.is_race_to_racks)
        ),
        prossimo=prossimo,
        chiusi=chiusi,
    )


class StatoProvaX(str, Enum):
    """A che punto e' l'esercizio giocato al posto della X."""

    DA_REGISTRARE = "da_registrare"
    DICHIARATA = "dichiarata"
    CONVALIDATA = "convalidata"


@dataclass(frozen=True)
class SchedaProvaX:
    """L'unico lato della X con esercizio.

    Il massimo e' la distanza **del turno** (`effective_distance`, ADR-027):
    la differenza piu' ampia che una partita di quel turno puo' dare
    (SPECIFICHE riga 65). Il punteggio di partenza e' quello convalidato, o
    quello dichiarato dal giocatore, o zero.
    """

    stato: StatoProvaX
    punteggio: int
    massimo: int
    esercizio: Optional[str]


def scheda_prova_x(match) -> Optional[SchedaProvaX]:
    if forma_partita(match) != FormaPartita.X_ESERCIZIO:
        return None
    ponte = getattr(match, "bye_challenge", None)
    tentativo = getattr(ponte, "challenge_attempt", None) if ponte else None
    dichiarato = getattr(tentativo, "score", None) if tentativo else None
    if ponte is not None and ponte.is_validated:
        stato = StatoProvaX.CONVALIDATA
        punteggio = dichiarato if dichiarato is not None else match.player1_score
    elif ponte is not None and ponte.is_completed and dichiarato is not None:
        stato = StatoProvaX.DICHIARATA
        punteggio = dichiarato
    else:
        stato = StatoProvaX.DA_REGISTRARE
        punteggio = 0
    massimo = match.effective_distance
    esercizio = None
    sfida = getattr(tentativo, "challenge", None) if tentativo else None
    if sfida is None and getattr(match, "gara", None) is not None:
        sfida = getattr(match.gara, "x_challenge", None)
    if sfida is not None:
        esercizio = sfida.get_display_name()
    return SchedaProvaX(
        stato=stato,
        punteggio=max(0, min(int(punteggio or 0), massimo)),
        massimo=massimo,
        esercizio=esercizio,
    )


@dataclass(frozen=True)
class SchedaPartita:
    forma: FormaPartita
    trio: Optional[SchedaTrio] = None
    set: Optional[SchedaSet] = None
    prova: Optional[SchedaProvaX] = None


def scheda_partita(match) -> SchedaPartita:
    """Tutto quello che la card chiede alla partita, per la sua forma."""
    forma = forma_partita(match)
    if forma == FormaPartita.TRIO:
        return SchedaPartita(forma, trio=scheda_trio(match))
    if forma == FormaPartita.SET:
        return SchedaPartita(forma, set=scheda_set(match))
    if forma == FormaPartita.X_ESERCIZIO:
        return SchedaPartita(forma, prova=scheda_prova_x(match))
    return SchedaPartita(forma)


# ---------------------------------------------------------------------------
# La gara dentro un campionato
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GaraVicina:
    """Una gara del campionato che fissa un estremo della finestra di date."""

    numero: int
    data: Optional[date]
    ora: Optional[time]


@dataclass(frozen=True)
class ContestoCampionato:
    """Cio' che una gara riceve dal campionato, per la pagina del direttore.

    `peso` e' il valore scritto sulla gara (`Gara.weight`), `peso_effettivo`
    quello che la classifica generale usa davvero
    (`Gara.classification_weight`, ADR-053): vale 0 per il playoff che decide
    la classifica finale, e allora la pagina non deve dire «vale ×N».
    `precedente` e `successiva` sono le gare che fissano la finestra di date
    ammessa dall'ADR-016: la gara con il numero piu' alto sotto e quella con
    il numero piu' basso sopra, non per forza N-1 e N+1.
    """

    campionato_id: int
    nome: str
    numero: int
    gare_previste: int
    peso: int
    peso_effettivo: int
    is_playoff: bool
    modalita: Optional[str]
    regola_apertura: object
    apertura_ereditata: bool
    precedente: Optional[GaraVicina]
    successiva: Optional[GaraVicina]

    @property
    def decide_il_playoff(self) -> bool:
        """Il playoff decide la classifica finale: la gara non si somma."""
        return self.is_playoff and self.peso_effettivo == 0


def _vicina(gara) -> GaraVicina:
    return GaraVicina(
        numero=gara.number,
        data=getattr(gara, "date", None),
        ora=getattr(gara, "time", None),
    )


def contesto_campionato(gara, gare: Optional[Iterable] = None):
    """Il contesto di campionato di `gara`, o `None` per una gara singola.

    `gare` sono le gare del campionato; senza, si leggono dalla relazione
    `campionato.gare`. Nessuna query oltre a quella: numero, peso, playoff e
    regola di apertura stanno gia' sulla gara.
    """
    from models.match.break_rules import BreakRule

    campionato = getattr(gara, "campionato", None)
    if campionato is None:
        return None
    if gare is None:
        gare = getattr(campionato, "gare", None) or []
    altre = [g for g in gare if g is not gara and g.number is not None]
    prima = [g for g in altre if g.number < gara.number]
    dopo = [g for g in altre if g.number > gara.number]

    config = getattr(gara, "playoff_config", None)
    modalita = None
    if config is not None:
        modo = getattr(config, "ranking_mode", None)
        modalita = getattr(modo, "value", modo)

    peso = 1 if getattr(gara, "weight", None) is None else int(gara.weight)
    numero = gara.number or 0
    return ContestoCampionato(
        campionato_id=campionato.id,
        nome=campionato.name,
        numero=numero,
        # Il playoff nasce dopo le gare previste, con il numero successivo:
        # «gara 7 di 6» non si scrive.
        gare_previste=max(int(campionato.planned_gare_count or 0), numero),
        peso=peso,
        peso_effettivo=int(gara.classification_weight),
        is_playoff=config is not None,
        modalita=modalita,
        regola_apertura=gara.effective_break_rule,
        apertura_ereditata=BreakRule.normalize(getattr(gara, "break_rule", None))
        is None,
        precedente=_vicina(max(prima, key=lambda g: g.number)) if prima else None,
        successiva=_vicina(min(dopo, key=lambda g: g.number)) if dopo else None,
    )


__all__ = [
    "FaseGara",
    "StatoTacca",
    "Tacca",
    "ConteggiTurno",
    "ContestoCampionato",
    "GaraVicina",
    "StatoPartita",
    "FormaPartita",
    "StatoProvaX",
    "SchedaTrio",
    "SchedaSet",
    "SchedaProvaX",
    "SchedaPartita",
    "forma_partita",
    "scheda_trio",
    "scheda_set",
    "scheda_prova_x",
    "scheda_partita",
    "Tavolo",
    "fase_della_gara",
    "spareggio_nella_striscia",
    "striscia",
    "conteggi_turno",
    "contesto_campionato",
    "stato_partita",
    "partite_del_turno",
    "prima_in_attesa",
    "tavoli_del_turno",
]
