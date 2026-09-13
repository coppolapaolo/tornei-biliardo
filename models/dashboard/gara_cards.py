# models/dashboard/gara_cards.py
"""Le gare della dashboard, divise fra «le tue» e «aperte».

Prima questa divisione non esisteva: la sezione si chiamava «Gare» e conteneva
tutto ciò che `build_unified_items` rende visibile — ogni campionato e ogni
gara standalone viva, iscritto o no. Il titolo prometteva una cosa e l'elenco
ne conteneva un'altra, e la propria partita in corso finiva mescolata alle gare
di sconosciuti.

Qui la domanda è una sola e ha due risposte diverse:

* **le tue** — c'è dentro un fatto tuo: sei iscritto (anche in lista d'attesa),
  oppure la dirigi. È l'elenco delle cose che ti riguardano, e ci sta dentro
  anche la tua partita;
* **aperte** — non ci sei ancora e potresti entrarci.

Una gara viva in cui non c'entri niente e a cui non puoi iscriverti non compare
più: sta nell'elenco pubblico, a un tocco di distanza dal «Vedi tutte».

La divisione si fa **qui e non in Jinja** per due ragioni. La prima è che il
template la ricostruiva iterando `gara.inscriptions` a ogni card, cioè una
query per gara per cercare una riga che la dashboard aveva già in mano
(`vm.my_inscriptions`). La seconda è che una regola su chi vede cosa è una
regola di dominio, e in un template non la copre nessun test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import joinedload, selectinload

from models.base import db
from models.classification.models import GaraClassification, RoundClassification
from models.dashboard.comandi import ComandoVM, comando_per
from models.competition.models import Gara, Inscription, WaitlistReason
from models.match.models import Match as TournamentMatch
from models.status_enum import GaraStatus, MatchStatus, ProvaDerivedStatus

#: Gli stati in cui una gara è ancora "viva", cioè ha senso mostrarla fra le
#: cose correnti invece che negli archivi.
#:
#: `INSCRIPTION_NOT_YET_OPEN` è nell'elenco e prima non c'era: una gara con la
#: finestra di iscrizione programmata nel futuro spariva dalla dashboard di
#: tutti — compreso il direttore che l'aveva appena creata, che quindi non
#: aveva più da nessuna parte il pulsante per gestirla. Il caso passava
#: inosservato perché una gara nasce in `SETUP` (visibile) e ci resta finché
#: qualcuno non apre le iscrizioni: solo chi le programma in anticipo lo vede.
LIVE_STATES: frozenset[str] = frozenset(
    {
        GaraStatus.SETUP.value,
        GaraStatus.INSCRIPTION.value,
        GaraStatus.PLAYING.value,
        GaraStatus.AWAITING_SSR.value,
        ProvaDerivedStatus.INSCRIPTION_NOT_YET_OPEN.value,
        ProvaDerivedStatus.INSCRIPTION_CLOSED.value,
        ProvaDerivedStatus.ROUND_COMPLETED.value,
    }
)

#: Gli stati di una gara finita. `TOURNAMENT_COMPLETED` ha un nome storico
#: infelice — il suo valore è la stringa `campionato_completed` — ma vale
#: «gara conclusa»: è quello che `get_real_status()` restituisce quando tutti
#: i turni sono giocati, anche se il direttore non ha ancora premuto
#: «Termina Gara» e quindi la colonna dice ancora `playing`.
STATI_CONCLUSI: frozenset[str] = frozenset(
    {
        GaraStatus.COMPLETED.value,
        ProvaDerivedStatus.TOURNAMENT_COMPLETED.value,
    }
)

#: Gli stati in cui la gara si sta giocando adesso: vanno in cima a «le tue».
STATI_IN_CORSO: frozenset[str] = frozenset(
    {
        GaraStatus.PLAYING.value,
        GaraStatus.AWAITING_SSR.value,
        ProvaDerivedStatus.ROUND_COMPLETED.value,
    }
)

#: Gli stati di una gara che deve ancora cominciare: creata, iscrizioni
#: programmate, iscrizioni chiuse in attesa dell'avvio. Per chi non c'entra è
#: «in arrivo», cioè contesto: non c'è ancora niente da fare.
STATI_IN_ARRIVO: frozenset[str] = frozenset(
    {
        GaraStatus.SETUP.value,
        ProvaDerivedStatus.INSCRIPTION_NOT_YET_OPEN.value,
        ProvaDerivedStatus.INSCRIPTION_CLOSED.value,
    }
)

#: Quanto dura la finestra delle concluse in dashboard e in home (regola 2
#: del 2026-09-10): l'ultima, sempre, più quelle dell'ultimo mese. Le altre
#: stanno nello storico. Si ancora a `Gara.date` perché una data di chiusura
#: non esiste: lo stato «conclusa» è derivato.
FINESTRA_CONCLUSE = timedelta(days=30)


def is_conclusa(gara: Gara) -> bool:
    """La gara è finita: resta da leggere, non da giocare."""
    return gara.get_real_status() in STATI_CONCLUSI


@dataclass(frozen=True)
class PosizioneVM:
    """Dove sei in classifica, e dopo quale turno.

    Il turno fa parte del dato e non è un dettaglio: la classifica si calcola
    **quando un turno finisce**, quindi mentre giochi il terzo turno quella
    che esiste è la classifica dopo il secondo. Mostrarla senza dirlo la
    farebbe leggere come se tenesse conto della partita che hai in mano.
    """

    posizione: int
    su: int
    turno: int


@dataclass(frozen=True)
class PiazzamentoVM:
    """Come è finita per chi guarda, su una gara conclusa che ha giocato."""

    posizione: int
    su: int
    vinte: int
    giocate: int


@dataclass
class ElenchiGare:
    """Le gare della dashboard, già divise per quello che chiedono.

    Ogni elenco è una sezione. Sono cinque perché rispondono a cinque domande
    diverse: cosa devo fare io (`mie`), cosa sta succedendo (`in_diretta`),
    dove posso entrare (`aperte`), cosa arriva (`in_arrivo`), com'è andata
    (`concluse`). Senza un fatto mio la gara sta in uno degli ultimi quattro,
    ed è la stessa tessera che vede l'ospite.
    """

    mie: List["GaraCardVM"] = field(default_factory=list)
    in_diretta: List["GaraCardVM"] = field(default_factory=list)
    aperte: List["GaraCardVM"] = field(default_factory=list)
    in_arrivo: List["GaraCardVM"] = field(default_factory=list)
    #: L'ultima più quelle dell'ultimo mese, di tutti (`finestra_concluse`).
    concluse: List["GaraCardVM"] = field(default_factory=list)
    #: Quante ne esistono in tutto: la riga «le altre N sono nello storico».
    concluse_totali: int = 0


@dataclass
class GaraCardVM:
    """Una gara come la vede **una persona precisa**.

    Non è una `Gara`: è una gara più il posto che ci occupa chi sta guardando
    — la sua iscrizione, le sue partite, se la dirige. Sono esattamente i tre
    dati che la card deve mostrare e che il template altrimenti ricava da capo
    a ogni giro.
    """

    gara: Gara
    name: str
    campionato_name: Optional[str] = None
    can_manage: bool = False
    can_view_details: bool = True
    #: L'iscrizione di chi guarda a questa gara, se ce n'è una. Porta con sé
    #: la lista d'attesa: posizione e **motivo**.
    inscription: Optional[Inscription] = None
    #: Le sue partite ancora aperte in questa gara, per turno crescente.
    matches: List[TournamentMatch] = field(default_factory=list)
    #: Dove sei in classifica adesso, se la gara ne ha già prodotta una.
    #: La riempie `enrich_with_progress`, che fa le query.
    classifica: Optional["PosizioneVM"] = None
    #: Le partite **degli altri** nel turno in corso, al più tre.
    altre_partite: List[TournamentMatch] = field(default_factory=list)
    #: Quante ne restano oltre quelle mostrate.
    altre_restanti: int = 0
    #: Il comando che questa gara aspetta dal suo direttore, se lo dirigi.
    #: Vedi `models/dashboard/comandi.py`: qui si **annuncia**, si esegue
    #: nella pagina della gara.
    comando: Optional["ComandoVM"] = None
    #: Su una gara conclusa che hai giocato: dove sei arrivato. La riempie
    #: `enrich_with_piazzamento`.
    piazzamento: Optional["PiazzamentoVM"] = None

    #: Negli elenchi può stare anche una `PlayoffCardVM` (il playoff prima del
    #: primo turno): il template le distingue da qui.
    is_scheda_playoff = False

    # -- scorciatoie per il template ------------------------------------
    # Tutte derivate: nessuno stato in più da tenere allineato.

    @property
    def id(self) -> int:
        return self.gara.id

    @property
    def date(self) -> Optional[date_cls]:
        return getattr(self.gara, "date", None)

    @property
    def real_status(self) -> str:
        return self.gara.get_real_status()

    @property
    def is_conclusa(self) -> bool:
        return self.real_status in STATI_CONCLUSI

    @property
    def is_in_corso(self) -> bool:
        """Si sta giocando adesso: la tessera è scura per chiunque la guardi."""
        return self.real_status in STATI_IN_CORSO

    @property
    def ha_un_fatto_mio(self) -> bool:
        """Iscritto, la dirigo, o ho una partita: senza, la tessera è quella
        dell'ospite (regola 1 del 2026-09-10)."""
        return self.is_inscribed or self.can_manage or bool(self.matches)

    @property
    def hai_giocato(self) -> bool:
        """Conclusa e c'ero: la pastiglia «Hai giocato». A gara finita
        «Iscritto» non dice più niente."""
        return self.is_conclusa and self.is_inscribed

    @property
    def hai_diretto(self) -> bool:
        return self.is_conclusa and self.can_manage

    @property
    def is_inscribed(self) -> bool:
        """Iscritto davvero, lista d'attesa compresa.

        Un ritirato non è iscritto: la riga resta per storia, ma la gara non è
        più «sua» da giocare.
        """
        return self.inscription is not None and not self.inscription.is_withdrawn

    @property
    def is_waitlist(self) -> bool:
        return self.inscription is not None and bool(self.inscription.is_waitlist)

    @property
    def waitlist_position(self) -> Optional[int]:
        return self.inscription.waitlist_position if self.inscription else None

    @property
    def waitlist_is_parity(self) -> bool:
        """La lista d'attesa è per **parità**, non perché la gara è piena.

        Sono due cose diverse e finora l'interfaccia ne mostrava una sola:
        «Lista d'attesa #1» su una gara con 17 posti occupati su 24 si legge
        come un errore del sito. Il motivo è in colonna da sempre
        (`Inscription.waitlist_reason`), non lo leggeva nessuno.
        """
        return (
            self.inscription is not None
            and self.inscription.waitlist_reason == WaitlistReason.PARITY.value
        )

    @property
    def prossima_partita(self) -> Optional[TournamentMatch]:
        """La partita da giocare adesso, se ce n'è una.

        La prima per turno: chi ha due partite aperte le gioca in ordine.
        """
        return self.matches[0] if self.matches else None


def _gare_visibili(unified_items: Iterable[Any]) -> Dict[int, Dict[str, Any]]:
    """Da `unified_items` a una mappa `gara_id -> gara + contesto`.

    `build_unified_items` restituisce campionati **e** gare mescolati, e le
    gare di un campionato stanno dentro `item.entity.gare`. Il template
    srotolava questa struttura a mano a ogni render, costruendo dizionari con
    le stesse chiavi della dataclass accanto — due forme per la stessa cosa,
    che Jinja tollera e pyright no.
    """
    per_gara: Dict[int, Dict[str, Any]] = {}

    for item in unified_items or []:
        if item.type == "gara":
            per_gara[item.entity.id] = {
                "gara": item.entity,
                "name": item.name,
                "campionato_name": None,
                "can_manage": item.can_manage,
                "can_view_details": item.can_view_details,
            }
        elif item.type == "campionato":
            for gara in item.entity.gare or []:
                per_gara[gara.id] = {
                    "gara": gara,
                    "name": gara.display_name,
                    "campionato_name": item.entity.name,
                    # I permessi sul campionato valgono per le sue gare: chi
                    # dirige il campionato dirige le prove che contiene.
                    "can_manage": item.can_manage,
                    "can_view_details": item.can_view_details,
                }

    return per_gara


def _ordine_delle_mie(card: GaraCardVM) -> Tuple[int, int]:
    """Prima quello che chiede qualcosa, poi quello che è già successo.

    Tre gruppi: in corso, in arrivo, concluse. Dentro ogni gruppo la data —
    crescente per ciò che deve ancora accadere, decrescente per ciò che è
    passato, perché di una gara finita interessa l'ultima, non la prima.
    Le date mancanti vanno in fondo al proprio gruppo.
    """
    giorno = card.date.toordinal() if card.date else date_cls.max.toordinal()

    if card.real_status in STATI_IN_CORSO:
        return (0, giorno)
    if card.is_conclusa:
        return (2, -giorno)
    return (1, giorno)


def finestra_concluse(
    cards: Iterable[GaraCardVM], oggi: Optional[date_cls] = None
) -> List[GaraCardVM]:
    """L'ultima conclusa, sempre, più quelle dell'ultimo mese.

    Regola 2 del 2026-09-10. «Sempre» è il punto: chi apre la dashboard dopo
    l'estate trova comunque un aggancio al passato invece di un vuoto. La
    finestra si misura su `Gara.date`, il giorno in cui si è giocata — una
    data di chiusura non esiste — quindi una gara chiusa dal direttore due
    mesi dopo averla giocata esce dalla dashboard nel momento in cui viene
    chiusa: accettato.

    Pura: non tocca il database, ordina quello che riceve.
    """
    oggi = oggi or date_cls.today()
    ordinate = sorted(
        (c for c in cards if c.is_conclusa),
        key=lambda c: (c.date is None, -(c.date.toordinal() if c.date else 0)),
    )
    if not ordinate:
        return []
    soglia = oggi - FINESTRA_CONCLUSE
    ultima, altre = ordinate[0], ordinate[1:]
    return [ultima] + [c for c in altre if c.date is not None and c.date >= soglia]


def build_gara_cards(
    unified_items: Iterable[Any],
    my_inscriptions: Optional[Iterable[Inscription]],
    current_matches: Optional[Iterable[TournamentMatch]],
    *,
    oggi: Optional[date_cls] = None,
) -> ElenchiGare:
    """Le gare da mostrare, divise per quello che chiedono.

    Args:
        unified_items: l'uscita di `build_unified_items` — campionati e gare
            standalone con i permessi già calcolati. Contiene **tutte** le
            gare visibili, concluse comprese: da qui vengono anche gli
            elenchi «di tutti».
        my_inscriptions: **tutte** le iscrizioni di chi guarda, con la gara
            già caricata (`vm.my_inscriptions`). Sono la sorgente di «le tue»:
            una gara a cui sono iscritto è mia anche se `unified_items` non la
            porta, il che succede per le gare concluse dentro un campionato.
        current_matches: le sue partite ancora aperte (`vm.current_matches`).
        oggi: il giorno da cui misurare la finestra delle concluse; nei test
            si passa, altrimenti è oggi.

    Returns:
        `ElenchiGare`. Ogni gara sta in un elenco solo: se c'è un fatto mio
        sta in `mie` (finché è viva), altrimenti nell'elenco del suo stato,
        con la stessa tessera che vede l'ospite. Le concluse stanno tutte in
        `concluse`, mie comprese — riconoscibili dalle pastiglie «Hai giocato»
        e «Hai diretto» — tagliate con `finestra_concluse`.
    """
    visibili = _gare_visibili(unified_items)

    inscription_by_gara: Dict[int, Inscription] = {
        ins.gara_id: ins for ins in (my_inscriptions or [])
    }

    matches_by_gara: Dict[int, List[TournamentMatch]] = {}
    for match in current_matches or []:
        if match.gara_id is None:
            continue
        matches_by_gara.setdefault(match.gara_id, []).append(match)
    for lista in matches_by_gara.values():
        lista.sort(key=lambda m: m.round_number or 0)

    def _card(gara: Gara, ctx: Optional[Dict[str, Any]] = None) -> GaraCardVM:
        if ctx is None:
            # Una gara che arriva dalle mie iscrizioni ma non da
            # `unified_items`: tipicamente una conclusa dentro un campionato.
            # Non la dirigo (altrimenti sarei passato di lì) ma i dettagli li
            # vedo — è una gara che ho giocato.
            ctx = {
                "name": gara.display_name,
                "campionato_name": (
                    gara.campionato.name if gara.campionato is not None else None
                ),
                "can_manage": False,
                "can_view_details": True,
            }
        return GaraCardVM(
            gara=gara,
            name=ctx["name"],
            campionato_name=ctx["campionato_name"],
            can_manage=ctx["can_manage"],
            can_view_details=ctx["can_view_details"],
            inscription=inscription_by_gara.get(gara.id),
            matches=matches_by_gara.get(gara.id, []),
        )

    # -- una card per gara, con i miei fatti dentro --------------------
    # Due sorgenti che si sovrappongono: le gare visibili e quelle a cui sono
    # iscritto. Una gara che dirigo e in cui gioco compare una volta sola,
    # con entrambe le nature: è il motivo per cui l'elenco delle mie è uno.
    per_id: Dict[int, GaraCardVM] = {}
    for gara_id, ctx in visibili.items():
        per_id[gara_id] = _card(ctx["gara"], ctx)
    for ins in my_inscriptions or []:
        gara = ins.gara
        if gara is None or ins.is_withdrawn or gara.id in per_id:
            continue
        per_id[gara.id] = _card(gara)
    # Terza sorgente, ed e' la piu' forte: una partita aperta. Se ce l'hai,
    # quella gara e' tua qualunque cosa dica l'iscrizione — e senza questo
    # giro sparirebbe in silenzio il caso in cui l'iscrizione risulta ritirata
    # ma un match e' rimasto aperto.
    for gara_id in matches_by_gara:
        if gara_id not in per_id and gara_id in visibili:
            per_id[gara_id] = _card(visibili[gara_id]["gara"], visibili[gara_id])

    elenchi = ElenchiGare()
    tutte_le_concluse: List[GaraCardVM] = []
    for card in per_id.values():
        stato = card.real_status
        if card.is_conclusa:
            tutte_le_concluse.append(card)
        elif card.ha_un_fatto_mio and stato in LIVE_STATES:
            elenchi.mie.append(card)
        elif card.is_in_corso:
            elenchi.in_diretta.append(card)
        elif stato == GaraStatus.INSCRIPTION.value:
            elenchi.aperte.append(card)
        elif stato in STATI_IN_ARRIVO:
            elenchi.in_arrivo.append(card)
        # Una gara viva in nessuno di questi stati non esiste: LIVE_STATES
        # copre tutto ciò che non è concluso.

    elenchi.mie.sort(key=_ordine_delle_mie)
    per_data = lambda c: (c.date is None, c.date or date_cls.max)  # noqa: E731
    elenchi.in_diretta.sort(key=per_data)
    elenchi.aperte.sort(key=per_data)
    elenchi.in_arrivo.sort(key=per_data)
    elenchi.concluse = finestra_concluse(tutte_le_concluse, oggi)
    elenchi.concluse_totali = len(tutte_le_concluse)
    return elenchi


#: Quante partite degli altri mostrare sotto la propria. Tre bastano a capire
#: come sta andando il turno; l'elenco completo sta nella pagina della gara.
ALTRE_PARTITE_MOSTRATE = 3


def enrich_with_progress(cards: Iterable[GaraCardVM], user_id: Optional[int]) -> None:
    """Riempie «come sta andando» sulle gare in corso: posizione e turno.

    Modifica le card sul posto. Sta separata da `build_gara_cards` perché
    quella non tocca il database — riordina roba già in memoria — mentre
    questa fa tre query, e vale la pena poter provare la divisione senza.

    Le query sono **quattro in tutto**, non quattro per gara: una dashboard
    con quattro gare in corso costava altrimenti sedici viaggi.

    `user_id` è `None` per l'ospite: nessuna partita è sua, quindi «altre
    partite» sono tutte, e la posizione in classifica non c'è.
    """
    cards = list(cards)
    # 0. `gara.matches` per tutte le gare che si stanno giocando, in una
    #    query, **prima** di chiedere lo stato reale: `get_real_status()` li
    #    scorre per capire se i turni sono finiti, e la tessera li rilegge
    #    (`display_round`, il conteggio delle partite chiuse con la strategia
    #    casuale). Senza, è un caricamento pigro per gara — la N+1 della
    #    issue #62, già chiusa una volta nella home. Si filtra sulla colonna,
    #    che non costa niente.
    da_caricare = [
        c.gara.id
        for c in cards
        if c.gara.id is not None and c.gara.status == GaraStatus.PLAYING.value
    ]
    if da_caricare:
        db.session.query(Gara).options(selectinload(Gara.matches)).filter(
            Gara.id.in_(da_caricare)
        ).all()

    in_corso = [
        c
        for c in cards
        if c.real_status == GaraStatus.PLAYING.value and c.gara.id is not None
    ]
    if not in_corso:
        return

    gara_ids = [c.gara.id for c in in_corso]

    # 1. Qual è l'ultimo turno con una classifica, gara per gara.
    #    Si parte da 1: il turno 0 è la classifica di **partenza**
    #    (SeedingService), cioè l'ordine del sorteggio. Spacciarla per una
    #    classifica provvisoria prima che si giochi vorrebbe dire dire a
    #    qualcuno che è quarto quando nessuno ha ancora tirato.
    ultimi = dict(
        db.session.query(
            RoundClassification.gara_id,
            func.max(RoundClassification.round_number),
        )
        .filter(
            RoundClassification.gara_id.in_(gara_ids),
            RoundClassification.round_number >= 1,
        )
        .group_by(RoundClassification.gara_id)
        .all()
    )

    # 2. Le righe di quei turni: servono la posizione di chi guarda e quante
    #    righe ci sono in tutto, cioè il «su quanti».
    if ultimi:
        righe = (
            db.session.query(
                RoundClassification.gara_id,
                RoundClassification.user_id,
                RoundClassification.position,
            )
            .filter(
                or_(
                    *[
                        and_(
                            RoundClassification.gara_id == gid,
                            RoundClassification.round_number == rnd,
                        )
                        for gid, rnd in ultimi.items()
                    ]
                )
            )
            .all()
        )
        quanti: Dict[int, int] = {}
        mia_posizione: Dict[int, int] = {}
        for gid, uid, posizione in righe:
            quanti[gid] = quanti.get(gid, 0) + 1
            if uid == user_id:
                mia_posizione[gid] = posizione

        for card in in_corso:
            posizione = mia_posizione.get(card.gara.id)
            if posizione is not None:
                card.classifica = PosizioneVM(
                    posizione=posizione,
                    su=quanti[card.gara.id],
                    turno=ultimi[card.gara.id],
                )

    # 3. Le partite degli altri nel turno in corso. `current_round` cambia da
    #    gara a gara, quindi il filtro è una coppia per gara.
    turni = {c.gara.id: (c.gara.current_round or 1) for c in in_corso}
    partite = (
        db.session.query(TournamentMatch)
        .filter(
            or_(
                *[
                    and_(
                        TournamentMatch.gara_id == gid,
                        TournamentMatch.round_number == rnd,
                    )
                    for gid, rnd in turni.items()
                ]
            )
        )
        .options(
            joinedload(TournamentMatch.player1),
            joinedload(TournamentMatch.player2),
        )
        .all()
    )

    per_gara: Dict[int, List[TournamentMatch]] = {}
    for match in partite:
        if match.player1_id == user_id or match.player2_id == user_id:
            continue  # la propria sta già in cima alla card
        if match.is_bye:
            continue  # una X non è una partita da guardare
        per_gara.setdefault(match.gara_id, []).append(match)

    for card in in_corso:
        altre = per_gara.get(card.gara.id, [])
        # Prima quelle che dicono qualcosa: una partita ancora a zero non
        # aggiunge niente a «come sta andando il turno».
        altre.sort(key=_ordine_delle_altre)
        card.altre_partite = altre[:ALTRE_PARTITE_MOSTRATE]
        card.altre_restanti = max(0, len(altre) - ALTRE_PARTITE_MOSTRATE)


def enrich_with_comandi(cards: Iterable[GaraCardVM]) -> None:
    """Dice, per ogni gara che dirigi, cosa sta aspettando da te.

    Solo per quelle che dirigi: a chi gioca e basta non serve sapere che la
    gara aspetta l'avvio del turno, e chiederlo costerebbe una query di
    parimerito per gara.
    """
    for card in cards:
        if card.can_manage:
            card.comando = comando_per(card.gara)


def enrich_with_piazzamento(
    cards: Iterable[GaraCardVM], user_id: Optional[int]
) -> None:
    """Sulle concluse che hai giocato: dove sei arrivato, in una query.

    La classifica finale di gara (`GaraClassification`) ha una riga per
    giocatore; servono la tua e quante sono, cioè il «su quanti».
    """
    giocate = [c for c in cards if c.hai_giocato and c.gara.id is not None]
    if user_id is None or not giocate:
        return
    gara_ids = [c.gara.id for c in giocate]
    righe = (
        db.session.query(
            GaraClassification.gara_id,
            GaraClassification.user_id,
            GaraClassification.position,
            GaraClassification.matches_won,
            GaraClassification.matches_lost,
        )
        .filter(GaraClassification.gara_id.in_(gara_ids))
        .all()
    )
    quanti: Dict[int, int] = {}
    mie: Dict[int, Tuple[int, int, int]] = {}
    for gid, uid, posizione, vinte, perse in righe:
        quanti[gid] = quanti.get(gid, 0) + 1
        if uid == user_id:
            mie[gid] = (posizione, vinte or 0, (vinte or 0) + (perse or 0))
    for card in giocate:
        dati = mie.get(card.gara.id)
        if dati is not None:
            posizione, vinte, giocate_n = dati
            card.piazzamento = PiazzamentoVM(
                posizione=posizione,
                su=quanti[card.gara.id],
                vinte=vinte,
                giocate=giocate_n,
            )


def _ordine_delle_altre(match: TournamentMatch) -> Tuple[bool, int, int, str, int]:
    """Prima le partite che dicono qualcosa, poi per tavolo, poi per id.

    `table_assignment` è una stringa («3», «A», «sala rossa») e può mancare:
    confrontarla con un intero sentinella faceva cadere la dashboard con
    `TypeError` appena un turno aveva un tavolo con la lettera e uno senza
    (trovato il 2026-09-13 sul dataset della guida). I tavoli numerici si
    ordinano per numero, gli altri per nome dopo di loro, i mancanti in coda.
    """
    tavolo = match.table_assignment
    if tavolo is None:
        rango, numero, nome = 2, 0, ""
    elif tavolo.strip().isdigit():
        rango, numero, nome = 0, int(tavolo), ""
    else:
        rango, numero, nome = 1, 0, tavolo
    return (not _ha_un_punteggio(match), rango, numero, nome, match.id or 0)


def _ha_un_punteggio(match: TournamentMatch) -> bool:
    """Qualcuno ha segnato almeno un triangolo, o la partita è chiusa."""
    return bool(
        (match.player1_score or 0)
        or (match.player2_score or 0)
        or MatchStatus.is_finished(match.status)
    )


__all__ = [
    "ALTRE_PARTITE_MOSTRATE",
    "ElenchiGare",
    "FINESTRA_CONCLUSE",
    "GaraCardVM",
    "LIVE_STATES",
    "PiazzamentoVM",
    "PosizioneVM",
    "STATI_CONCLUSI",
    "STATI_IN_ARRIVO",
    "STATI_IN_CORSO",
    "build_gara_cards",
    "enrich_with_comandi",
    "enrich_with_piazzamento",
    "enrich_with_progress",
    "finestra_concluse",
    "is_conclusa",
]
