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
from datetime import date as date_cls
from typing import Any, Dict, Iterable, List, Optional, Tuple

from models.competition.models import Gara, Inscription, WaitlistReason
from models.match.models import Match as TournamentMatch
from models.status_enum import GaraStatus, ProvaDerivedStatus

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

#: Quante gare concluse tenere in coda a «Le tue gare». Le altre stanno nel
#: proprio storico: una gara finita non è una cosa da fare, e venti di fila
#: seppellirebbero quella in corso.
CONCLUSE_IN_CODA = 3


def is_conclusa(gara: Gara) -> bool:
    """La gara è finita: resta da leggere, non da giocare."""
    return gara.get_real_status() in STATI_CONCLUSI


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


def build_gara_cards(
    unified_items: Iterable[Any],
    my_inscriptions: Optional[Iterable[Inscription]],
    current_matches: Optional[Iterable[TournamentMatch]],
    *,
    can_inscribe: bool = True,
) -> Tuple[List[GaraCardVM], List[GaraCardVM], int]:
    """Le gare da mostrare, divise.

    Args:
        unified_items: l'uscita di `build_unified_items` — campionati e gare
            standalone con i permessi già calcolati.
        my_inscriptions: **tutte** le iscrizioni di chi guarda, con la gara
            già caricata (`vm.my_inscriptions`). Sono la sorgente di «le tue»:
            una gara a cui sono iscritto è mia anche se `unified_items` non la
            porta, il che succede per le gare concluse dentro un campionato.
        current_matches: le sue partite ancora aperte (`vm.current_matches`).
        can_inscribe: falso per l'amministratore, che non gioca — per lui
            «aperte, puoi iscriverti» è vuota.

    Returns:
        `(mie, aperte, concluse_totali)`. Il terzo valore conta **tutte** le
        gare concluse di chi guarda, non solo quelle in coda: serve alla riga
        «mostrate N di M» sotto l'elenco.
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

    # -- le tue ---------------------------------------------------------
    # Due sorgenti che si sovrappongono: le gare a cui sono iscritto e quelle
    # che dirigo. Si sovrappongono davvero — niente vieta al direttore di
    # iscriversi alla propria gara — ed è il motivo per cui l'elenco è uno
    # solo: la stessa card porta le due nature.
    mie_per_id: Dict[int, GaraCardVM] = {}

    for ins in my_inscriptions or []:
        gara = ins.gara
        if gara is None or ins.is_withdrawn:
            continue
        voce = visibili.get(gara.id)
        mie_per_id[gara.id] = _card(gara, voce)

    for gara_id, ctx in visibili.items():
        if gara_id in mie_per_id or not ctx["can_manage"]:
            continue
        gara = ctx["gara"]
        stato = gara.get_real_status()
        if stato not in LIVE_STATES and stato not in STATI_CONCLUSI:
            continue
        mie_per_id[gara_id] = _card(gara, ctx)

    # Terza sorgente, ed e' la piu' forte: una partita aperta. Se ce l'hai,
    # quella gara e' tua qualunque cosa dica l'iscrizione — e senza questo
    # giro sparirebbe in silenzio il caso in cui l'iscrizione risulta ritirata
    # ma un match e' rimasto aperto. La sezione «I tuoi match» di prima quel
    # match lo mostrava, perche' partiva dai match e non dalle iscrizioni:
    # ereditarne la copertura e' il minimo.
    for gara_id in matches_by_gara:
        if gara_id in mie_per_id:
            continue
        ctx = visibili.get(gara_id)
        if ctx is not None:
            mie_per_id[gara_id] = _card(ctx["gara"], ctx)

    tutte_mie = sorted(mie_per_id.values(), key=_ordine_delle_mie)

    # Le concluse si mostrano in coda e con il tetto: il resto sta nello
    # storico. Il conteggio totale torna al chiamante per la riga «di M».
    vive = [c for c in tutte_mie if not c.is_conclusa]
    concluse = [c for c in tutte_mie if c.is_conclusa]
    mie = vive + concluse[:CONCLUSE_IN_CODA]

    # -- aperte ---------------------------------------------------------
    aperte: List[GaraCardVM] = []
    if can_inscribe:
        for gara_id, ctx in visibili.items():
            if gara_id in mie_per_id:
                continue
            if ctx["gara"].get_real_status() != GaraStatus.INSCRIPTION.value:
                continue
            aperte.append(_card(ctx["gara"], ctx))
        aperte.sort(key=lambda c: (c.date is None, c.date or date_cls.max))

    return mie, aperte, len(concluse)


__all__ = [
    "CONCLUSE_IN_CODA",
    "GaraCardVM",
    "LIVE_STATES",
    "STATI_CONCLUSI",
    "STATI_IN_CORSO",
    "build_gara_cards",
    "is_conclusa",
]
