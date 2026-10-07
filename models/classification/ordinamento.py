"""Il motore unico della catena degli spareggi (ADR-078).

Una classifica a vittorie, a rack o a punti si stila in due tempi:

1. il **criterio principale**, che discende dal sistema di classifica
   (`ClassificationSystem`): vittorie, rack vinti o punti;
2. fra chi è pari sul principale, la **catena degli spareggi**: una lista
   ordinata di criteri, applicati uno dopo l'altro *a gruppi*.

Si lavora a gruppi, e non con una chiave di ordinamento, perché lo scontro
diretto non è una proprietà del singolo giocatore: vale **fra i soli pari**.
Fra due decide chi ha vinto lo scontro; fra tre o più una mini-classifica sulle
partite giocate fra loro; se non si sono incontrati tutti, il criterio non
decide e si passa al successivo.

Le classifiche sono tre, e ognuna ha la sua catena (decisione del 2026-10-07):

- **turno** (`RoundClassification`): serve agli abbinamenti, quindi l'ordine è
  sempre completo — se la catena non finisce col sorteggio, lo si aggiunge;
- **gara** (classifica finale): chi resta pari dopo la catena condivide la
  posizione (1, 2, 2, 4), a meno che la catena non finisca col sorteggio;
- **campionato** (classifica generale, ADR-073): l'ordine è sempre completo,
  perché da quella posizione discendono gli inviti ai playoff.

Il sistema POSITION non passa di qui: le sue bande di pari merito sono l'esito
voluto (ADR-040).

Il modulo è **puro**: niente database. Chi lo chiama aggrega i numeri
(`Concorrente`) e, se la catena contiene lo scontro diretto, gli passa le
partite (`Scontro`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
)

from flask_babel import gettext as _
from flask_babel import lazy_gettext as _l

from models.status_enum import ClassificationSystem


class Criterio(str, Enum):
    """Un criterio di ordinamento. Il valore è quello salvato nella catena."""

    VITTORIE = "vittorie"
    RACK_VINTI = "rack_vinti"
    PUNTI = "punti"
    DIFFERENZA_RACK = "differenza_rack"
    SCONTRI_DIRETTI = "scontri_diretti"
    SPAREGGIO_SSR = "ssr"
    POSIZIONE_PRECEDENTE = "posizione_precedente"
    SORTEGGIO = "sorteggio"

    def __str__(self) -> str:  # pragma: no cover – banale
        return str(self.value)


class Livello(str, Enum):
    """Le tre classifiche, ognuna con la sua catena."""

    TURNO = "turno"
    GARA = "gara"
    CAMPIONATO = "campionato"

    def __str__(self) -> str:  # pragma: no cover – banale
        return str(self.value)


#: Fin dove lo spareggio SSR scioglie i pari merito, se nessuno lo dice: il
#: podio. Stesso valore del vecchio `tiebreaker_until_position or 3`.
SSR_FINO_AL_DEFAULT = 3

#: Il posto più lontano fin dove si può chiedere lo spareggio SSR.
SSR_FINO_AL_MASSIMO = 99

#: Chi non ha una posizione precedente (iscritto dopo, nessuna gara prima)
#: viene dopo tutti quelli che ce l'hanno. Stessa sentinella di
#: `seeding_service.NO_SEEDING_POSITION`.
_NESSUNA_POSIZIONE = 10**6


@dataclass(frozen=True)
class Voce:
    """Un anello della catena. ``fino_al`` vale solo per lo spareggio SSR.

    Per lo SSR ``fino_al=None`` vuol dire «a ogni posizione»: è la forma della
    classifica generale, dove lo SSR è la somma degli spareggi delle gare.
    """

    criterio: Criterio
    fino_al: Optional[int] = None

    def serializza(self) -> str:
        if self.criterio is Criterio.SPAREGGIO_SSR and self.fino_al is not None:
            return f"{self.criterio.value}:{self.fino_al}"
        return self.criterio.value

    @classmethod
    def parse(cls, testo: object) -> Optional["Voce"]:
        """La voce scritta in ``testo``, o None se non è una voce valida."""
        if isinstance(testo, Voce):
            return testo
        if not isinstance(testo, str) or not testo.strip():
            return None
        nome, _sep, resto = testo.strip().partition(":")
        try:
            criterio = Criterio(nome)
        except ValueError:
            return None
        if criterio is not Criterio.SPAREGGIO_SSR:
            return None if resto else cls(criterio)
        if not resto:
            return cls(criterio)
        try:
            fino_al = int(resto)
        except ValueError:
            return None
        if not 1 <= fino_al <= SSR_FINO_AL_MASSIMO:
            return None
        return cls(criterio, fino_al)


Catena = Tuple[Voce, ...]


def parse_catena(valori: Optional[Iterable[object]]) -> Catena:
    """La catena salvata (lista di stringhe), con le voci illeggibili scartate."""
    if not valori:
        return ()
    voci = (Voce.parse(v) for v in valori)
    return tuple(v for v in voci if v is not None)


def serializza_catena(catena: Iterable[Voce]) -> List[str]:
    return [voce.serializza() for voce in catena]


def testo_della_catena(catena: Iterable[Voce]) -> str:
    """La catena come si salva in colonna: una lista JSON di voci.

    JSON e non una lista separata da virgole perché la catena **vuota** è una
    scelta («a pari vittorie si resta pari») e deve restare diversa da NULL,
    che vuol dire «come il campionato»: ``[]`` e NULL nella storia si leggono
    come due valori diversi. La forma è canonica (stessi separatori sempre),
    così due catene uguali hanno lo stesso testo e la storia non vede cambi
    che non ci sono.
    """
    return json.dumps(serializza_catena(catena))


def catena_dal_testo(testo: object) -> Optional[Catena]:
    """La catena salvata in ``testo``, o None se non ce n'è una.

    None (o una stringa vuota) vuol dire «nessuna catena scelta qui»: chi
    legge ripiega sul campionato o sul default. Accetta anche la forma
    separata da virgole.
    """
    if not isinstance(testo, str) or not testo.strip():
        return None
    grezzo = testo.strip()
    if grezzo.startswith("["):
        try:
            valori = json.loads(grezzo)
        except ValueError:
            return None
        if not isinstance(valori, list):
            return None
        return parse_catena(valori)
    return parse_catena(v for v in grezzo.split(",") if v.strip())


# ── Criterio principale e criteri ammessi ─────────────────────────────────

_PRINCIPALE: Dict[ClassificationSystem, Criterio] = {
    ClassificationSystem.WINS: Criterio.VITTORIE,
    ClassificationSystem.RACK: Criterio.RACK_VINTI,
}


def criterio_principale(sistema: ClassificationSystem) -> Criterio:
    """Il criterio principale di un sistema. POSITION non ne ha (ADR-040)."""
    try:
        return _PRINCIPALE[sistema]
    except KeyError:
        raise ValueError(
            f"Il sistema {sistema} non ordina con la catena degli spareggi"
        ) from None


def criteri_ammessi(
    livello: Livello, sistema: ClassificationSystem
) -> Tuple[Criterio, ...]:
    """I criteri che una catena di quel livello può contenere, nell'ordine dell'editor.

    - il **principale** no: due giocatori sono nella catena proprio perché lì
      sono pari;
    - i **punti** sono solo un criterio principale;
    - lo **spareggio SSR** non nel turno: si gioca a gara finita, quindi nei
      turni intermedi non c'è, e la classifica dell'ultimo turno la riscrive
      comunque la classifica di gara.
    """
    principale = criterio_principale(sistema)
    candidati = [
        Criterio.SCONTRI_DIRETTI,
        Criterio.DIFFERENZA_RACK,
        Criterio.RACK_VINTI,
        Criterio.VITTORIE,
        Criterio.SPAREGGIO_SSR,
        Criterio.POSIZIONE_PRECEDENTE,
        Criterio.SORTEGGIO,
    ]
    return tuple(
        c
        for c in candidati
        if c is not principale
        and not (livello is Livello.TURNO and c is Criterio.SPAREGGIO_SSR)
    )


def catena_completa(livello: Livello) -> bool:
    """Se a quel livello l'ordine dev'essere completo (sorteggio implicito)."""
    return livello is not Livello.GARA


def normalizza_catena(
    catena: Iterable[Voce], livello: Livello, sistema: ClassificationSystem
) -> Catena:
    """La catena com'è ammessa a quel livello.

    Toglie i criteri non ammessi e i doppioni (lo SSR al massimo una volta: vale
    il primo), mette il sorteggio in fondo e, dove l'ordine dev'essere completo,
    ce lo aggiunge. Nella gara lo SSR senza posto prende quello di default;
    nel campionato il posto si ignora, perché lì lo SSR è la somma.
    """
    ammessi = set(criteri_ammessi(livello, sistema))
    visti: set = set()
    voci: List[Voce] = []
    sorteggio = False
    for voce in catena:
        c = voce.criterio
        if c not in ammessi or c in visti:
            continue
        visti.add(c)
        if c is Criterio.SORTEGGIO:
            sorteggio = True
            continue
        if c is Criterio.SPAREGGIO_SSR:
            if livello is Livello.CAMPIONATO:
                voce = Voce(c)
            elif voce.fino_al is None:
                voce = Voce(c, SSR_FINO_AL_DEFAULT)
        voci.append(voce)
    if sorteggio or catena_completa(livello):
        voci.append(Voce(Criterio.SORTEGGIO))
    return tuple(voci)


def catena_di_default(
    livello: Livello,
    sistema: ClassificationSystem,
    *,
    ssr_fino_al: Optional[int] = SSR_FINO_AL_DEFAULT,
) -> Catena:
    """La catena che l'app usa quando nessuno ne ha scelta una.

    Decise il 2026-10-07 (ADR-078); le differenze col codice di prima sono
    scritte in SPECIFICHE.md, «Classifica». ``ssr_fino_al=None`` toglie lo
    spareggio dalla catena di gara (la gara che non lo prevede).
    """
    d = Voce(Criterio.DIFFERENZA_RACK)
    prec = Voce(Criterio.POSIZIONE_PRECEDENTE)
    sort = Voce(Criterio.SORTEGGIO)
    if livello is Livello.TURNO:
        voci: List[Voce] = [prec, sort]
        if sistema is not ClassificationSystem.RACK:
            voci.insert(0, d)
        return tuple(voci)
    if livello is Livello.GARA:
        voci = [] if sistema is ClassificationSystem.RACK else [d]
        if ssr_fino_al is not None:
            voci.append(Voce(Criterio.SPAREGGIO_SSR, ssr_fino_al))
        return tuple(voci)
    voci = [] if sistema is ClassificationSystem.RACK else [d]
    return tuple(voci + [Voce(Criterio.SPAREGGIO_SSR), prec, sort])


def ssr_della_catena(catena: Iterable[Voce]) -> Optional[Voce]:
    """La voce dello spareggio SSR, se la catena ce l'ha."""
    for voce in catena:
        if voce.criterio is Criterio.SPAREGGIO_SSR:
            return voce
    return None


def prima_dello_ssr(catena: Iterable[Voce]) -> Catena:
    """La catena fino allo spareggio SSR escluso.

    È la domanda «chi deve tirare?»: i gruppi ancora pari dopo questi criteri,
    se partono entro il posto dello spareggio.
    """
    voci: List[Voce] = []
    for voce in catena:
        if voce.criterio is Criterio.SPAREGGIO_SSR:
            break
        voci.append(voce)
    return tuple(voci)


# ── I dati ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Concorrente:
    """Un giocatore con i numeri che la catena può guardare.

    ``ssr`` è None per chi non ha tirato: ordina dopo chi ha fatto zero, che è
    un risultato. ``sorteggio`` è una chiave: più bassa viene prima.
    """

    player_id: int
    vittorie: int = 0
    rack_vinti: int = 0
    differenza_rack: int = 0
    punti: int = 0
    ssr: Optional[int] = None
    posizione_precedente: Optional[int] = None
    sorteggio: int = 0


@dataclass(frozen=True)
class Scontro:
    """Una partita fra due giocatori, per lo scontro diretto.

    ``vincitore`` None è un pareggio. Nel tabellone, a pari punteggio, è il
    giocatore che il direttore ha fatto passare (ADR-077).
    """

    giocatore1: int
    giocatore2: int
    rack1: int
    rack2: int
    vincitore: Optional[int] = None


@dataclass(frozen=True)
class Fascia:
    """Una posizione della classifica e chi la occupa (più d'uno = pari merito)."""

    posizione: int
    giocatori: Tuple[Concorrente, ...]


def chiave_di_sorteggio(seme: object, player_id: int) -> int:
    """Il sorteggio deterministico: la stessa classifica a ogni lettura.

    Un hash di seme e giocatore, quindi un ordine che non è quello degli id
    (cioè di registrazione) e che cambia se cambia il seme. Il seme della gara
    è il suo `draw_seed` (risorteggiare all'avvio cambia anche questo); quello
    del campionato è il suo id.
    """
    digest = hashlib.sha256(f"{seme}:{player_id}".encode()).hexdigest()
    return int(digest[:15], 16)


def seme_della_gara(gara: object) -> str:
    seme = getattr(gara, "draw_seed", None)
    if seme is None:
        seme = f"id{getattr(gara, 'id', 0)}"
    return f"gara:{seme}"


def seme_del_campionato(campionato: object) -> str:
    return f"campionato:{getattr(campionato, 'id', 0)}"


# ── Il motore ────────────────────────────────────────────────────────────

_Gruppo = List[Concorrente]


def _valore(c: Concorrente, criterio: Criterio) -> int:
    """Il valore di un criterio semplice: più alto viene prima."""
    if criterio is Criterio.VITTORIE:
        return c.vittorie
    if criterio is Criterio.RACK_VINTI:
        return c.rack_vinti
    if criterio is Criterio.PUNTI:
        return c.punti
    if criterio is Criterio.DIFFERENZA_RACK:
        return c.differenza_rack
    if criterio is Criterio.SPAREGGIO_SSR:
        # -1 a chi non ha tirato: viene dopo chi ha fatto zero.
        return -1 if c.ssr is None else c.ssr
    if criterio is Criterio.POSIZIONE_PRECEDENTE:
        prec = c.posizione_precedente
        return -(_NESSUNA_POSIZIONE if prec is None else prec)
    if criterio is Criterio.SORTEGGIO:
        return -c.sorteggio
    raise ValueError(f"Criterio senza valore: {criterio}")


def _per_valore(gruppo: _Gruppo, valore: Callable[[Concorrente], int]) -> List[_Gruppo]:
    """Il gruppo spezzato per valore decrescente, ordine stabile."""
    per: Dict[int, _Gruppo] = {}
    for c in gruppo:
        per.setdefault(valore(c), []).append(c)
    return [per[v] for v in sorted(per, reverse=True)]


class _Motore:
    def __init__(
        self,
        principale: Criterio,
        scontri: Sequence[Scontro],
        punti_partita: Tuple[int, int, int],
    ) -> None:
        self.principale = principale
        self.scontri = scontri
        self.punti_partita = punti_partita

    # Scontro diretto ------------------------------------------------------

    def _mini_classifica(self, gruppo: _Gruppo) -> Optional[List[_Gruppo]]:
        ids = {c.player_id for c in gruppo}
        interne = [
            s
            for s in self.scontri
            if s.giocatore1 in ids
            and s.giocatore2 in ids
            and s.giocatore1 != s.giocatore2
        ]
        incontrati = {frozenset((s.giocatore1, s.giocatore2)) for s in interne}
        coppie = len(ids) * (len(ids) - 1) // 2
        if len(incontrati) < coppie:
            # Non si sono incontrati tutti: il criterio non decide.
            return None
        vinta, pari, persa = self.punti_partita
        mini: Dict[int, int] = {pid: 0 for pid in ids}
        for s in interne:
            if self.principale is Criterio.RACK_VINTI:
                mini[s.giocatore1] += s.rack1
                mini[s.giocatore2] += s.rack2
                continue
            if s.vincitore is None:
                if self.principale is Criterio.PUNTI:
                    mini[s.giocatore1] += pari
                    mini[s.giocatore2] += pari
                continue
            perdente = s.giocatore2 if s.vincitore == s.giocatore1 else s.giocatore1
            if self.principale is Criterio.PUNTI:
                mini[s.vincitore] += vinta
                mini[perdente] += persa
            else:
                mini[s.vincitore] += 1
        return _per_valore(gruppo, lambda c: mini[c.player_id])

    # Un criterio su un gruppo --------------------------------------------

    def _separa(
        self, voce: Voce, gruppo: _Gruppo, posizione: int
    ) -> Optional[List[_Gruppo]]:
        criterio = voce.criterio
        if criterio is Criterio.SCONTRI_DIRETTI:
            return self._mini_classifica(gruppo)
        if (
            criterio is Criterio.SPAREGGIO_SSR
            and voce.fino_al is not None
            and posizione > voce.fino_al
        ):
            # Oltre il posto dello spareggio il pari merito è un risultato.
            return None
        if criterio is Criterio.SORTEGGIO:
            return [
                [c] for c in sorted(gruppo, key=lambda c: (c.sorteggio, c.player_id))
            ]
        return _per_valore(gruppo, lambda c: _valore(c, criterio))

    def ordina_gruppo(
        self, gruppo: _Gruppo, voci: Catena, posizione: int
    ) -> List[_Gruppo]:
        if len(gruppo) <= 1 or not voci:
            return [gruppo]
        voce, resto = voci[0], voci[1:]
        sottogruppi = self._separa(voce, gruppo, posizione)
        if sottogruppi is None or len(sottogruppi) <= 1:
            return self.ordina_gruppo(gruppo, resto, posizione)
        fasce: List[_Gruppo] = []
        for sotto in sottogruppi:
            # Dalla mini-classifica può restare un gruppo più piccolo ancora
            # pari: lo scontro diretto si ripete fra quei soli giocatori prima
            # di passare al criterio successivo (fra due che si sono
            # incontrati, decide il loro scontro).
            prossime = (
                voci
                if voce.criterio is Criterio.SCONTRI_DIRETTI and len(sotto) > 1
                else resto
            )
            fasce.extend(self.ordina_gruppo(sotto, prossime, posizione))
            posizione += len(sotto)
        return fasce


def ordina(
    concorrenti: Iterable[Concorrente],
    principale: Criterio,
    catena: Iterable[Voce],
    *,
    scontri: Sequence[Scontro] = (),
    punti_partita: Tuple[int, int, int] = (3, 1, 0),
    completa: bool = False,
) -> List[Fascia]:
    """Ordina i giocatori: principale decrescente, poi la catena a gruppi.

    Args:
        concorrenti: i giocatori con i loro numeri.
        principale: il criterio principale del sistema.
        catena: la catena degli spareggi, già normalizzata da chi chiama.
        scontri: le partite fra giocatori, se la catena ha lo scontro diretto.
        punti_partita: punti per vittoria, pareggio e sconfitta, per la
            mini-classifica dello scontro diretto nel sistema a punti.
        completa: aggiunge il sorteggio in coda se manca (turno, campionato).

    Returns:
        Le fasce in ordine. Una fascia di più giocatori è un pari merito: i suoi
        giocatori condividono la posizione, e la successiva salta (1, 2, 2, 4).
    """
    voci = tuple(catena)
    if completa and not any(v.criterio is Criterio.SORTEGGIO for v in voci):
        voci = voci + (Voce(Criterio.SORTEGGIO),)
    motore = _Motore(principale, scontri, punti_partita)
    fasce: List[Fascia] = []
    posizione = 1
    for gruppo in _per_valore(list(concorrenti), lambda c: _valore(c, principale)):
        for fascia in motore.ordina_gruppo(gruppo, voci, posizione):
            fasce.append(Fascia(posizione, tuple(fascia)))
            posizione += len(fascia)
    return fasce


# ── Le parole del regolamento ─────────────────────────────────────────────

#: Il nome di ogni criterio nell'editor della catena.
NOMI: Dict[Criterio, object] = {
    Criterio.VITTORIE: _l("Vittorie"),
    Criterio.RACK_VINTI: _l("Triangoli vinti"),
    Criterio.PUNTI: _l("Punti"),
    Criterio.DIFFERENZA_RACK: _l("Differenza triangoli"),
    Criterio.SCONTRI_DIRETTI: _l("Scontri diretti"),
    Criterio.SPAREGGIO_SSR: _l("Spareggio SSR"),
    Criterio.POSIZIONE_PRECEDENTE: _l("Posizione precedente"),
    Criterio.SORTEGGIO: _l("Sorteggio"),
}


def _nella_frase(voce: Voce, livello: Optional[Livello] = None) -> str:
    c = voce.criterio
    if c is Criterio.SCONTRI_DIRETTI:
        return _("lo scontro diretto")
    if c is Criterio.DIFFERENZA_RACK:
        return _("la differenza triangoli")
    if c is Criterio.RACK_VINTI:
        return _("i triangoli vinti")
    if c is Criterio.VITTORIE:
        return _("le vittorie")
    if c is Criterio.SPAREGGIO_SSR:
        if voce.fino_al is None:
            return _("lo spareggio SSR")
        return _("lo spareggio SSR fino al %(n)s° posto", n=voce.fino_al)
    if c is Criterio.POSIZIONE_PRECEDENTE:
        if livello is Livello.CAMPIONATO:
            return _("la posizione dopo la gara precedente")
        if livello is not None:
            return _("la posizione al turno precedente")
        return _("la posizione precedente")
    return _("il sorteggio")


def _a_pari(sistema: ClassificationSystem) -> str:
    if sistema is ClassificationSystem.RACK:
        return _("A pari triangoli vinti")
    return _("A pari vittorie")


def descrivi_catena(
    catena: Iterable[Voce],
    sistema: ClassificationSystem,
    livello: Optional[Livello] = None,
) -> str:
    """La frase del regolamento: «A pari vittorie conta …, poi …, poi …».

    Senza catena: «A pari vittorie i giocatori restano a pari merito.» Col
    ``livello`` la posizione precedente dice quale: al turno precedente o
    dopo la gara precedente.
    """
    voci = list(catena)
    if not voci:
        return _(
            "%(a_pari)s i giocatori restano a pari merito.", a_pari=_a_pari(sistema)
        )
    parti = [_nella_frase(v, livello) for v in voci]
    elenco = parti[0] + "".join(_(", poi %(x)s", x=p) for p in parti[1:])
    return _("%(a_pari)s conta %(elenco)s.", a_pari=_a_pari(sistema), elenco=elenco)


def nome_della_voce(voce: Voce) -> str:
    """Il nome di una voce nell'editor e nella storia: «Spareggio SSR fino al 3°»."""
    if voce.criterio is Criterio.SPAREGGIO_SSR and voce.fino_al is not None:
        return _("Spareggio SSR fino al %(n)s°", n=voce.fino_al)
    return str(NOMI[voce.criterio])


def elenca_catena(catena: Iterable[Voce]) -> str:
    """La catena in breve, senza il sistema: «Differenza triangoli → Sorteggio».

    È la forma della storia delle modifiche, che salva la catena senza sapere
    con quale sistema verrà letta.
    """
    voci = list(catena)
    if not voci:
        return _("nessun criterio: i pari merito restano tali")
    return " → ".join(nome_della_voce(v) for v in voci)


__all__ = [
    "Catena",
    "Concorrente",
    "Criterio",
    "Fascia",
    "Livello",
    "NOMI",
    "SSR_FINO_AL_DEFAULT",
    "Scontro",
    "Voce",
    "catena_completa",
    "catena_di_default",
    "chiave_di_sorteggio",
    "criteri_ammessi",
    "criterio_principale",
    "catena_dal_testo",
    "descrivi_catena",
    "elenca_catena",
    "nome_della_voce",
    "normalizza_catena",
    "ordina",
    "parse_catena",
    "prima_dello_ssr",
    "seme_del_campionato",
    "seme_della_gara",
    "serializza_catena",
    "ssr_della_catena",
    "testo_della_catena",
]
