"""Correggere il risultato di una partita in una gara già conclusa.

Nell'app non si può, ed è una scelta (issue #90): un risultato si corregge
solo a gara in corso, e con Amalfi solo finché il turno dopo non è partito.
Questo modulo esiste per il caso raro in cui l'errore si scopre a gara chiusa
e va sistemato lo stesso: lo usa `scripts/correggi_risultato_gara_conclusa.py`,
da console, con la web app su Disabled. Nessuna route lo chiama.

**Cosa cambia, e cosa no.** Gli abbinamenti dei turni dopo restano quelli
giocati: si sono fatti sulla classifica sbagliata, ma sono storia. Cambia
tutto ciò che *discende* dal risultato, ed è qui che non si può lasciare
niente a metà:

* la partita — punteggio, vincitore, i triangoli il cui vincitore cambia, e
  la traccia `MatchCorrection` che mostra a tutti il risultato di prima;
* le classifiche di ogni turno, quella della gara (con le posizioni condivise
  di `apply_final_positions`, che è ciò che fa la chiusura: un pari merito
  che si apre a gara chiusa resta pari, non si spareggia) e le righe del
  campionato, se esistono;
* l'ELO, rigiocato per intero: è path-dependent;
* il podio nella gamification: l'XP di podio si toglie a chi ne esce e si dà a
  chi ci entra, poi si ricalcolano livelli e traguardi. L'XP della **partita**
  invece resta dov'è, per la regola che l'app applica già a ogni correzione:
  si dà alla prima chiusura e non si sposta
  (`_xp_di_partita_gia_dati` in `gamification/event_handlers.py`).

**Niente stati a metà.** Tutto avviene in una transazione sola: se qualcosa va
storto non resta scritto niente. E prima di toccare il risultato il modulo
**rifà i conti sui dati invariati**: classifiche, ELO e podi ricalcolati
devono coincidere esattamente con quelli salvati. Se non coincidono si ferma
e dice dove: vorrebbe dire che lo stato salvato non è quello che il codice di
oggi produrrebbe, e una correzione fatta sopra mescolerebbe due cambiamenti
— quello voluto e uno che nessuno ha guardato. Alla fine verifica che
punteggio, triangoli e vincitore si dicano la stessa cosa.

**I triangoli si girano, non si riscrivono.** La correzione dell'app li
cancella e li riscrive dal punteggio, perdendo chi ha aperto e i runout. Qui
il numero di triangoli non cambia — si sbaglia di chi è il triangolo, non
quanti se ne sono giocati — e se ne gira il vincitore al minimo indispensabile:
uno, per un 3-2 che era un 2-3. Si sceglie l'ultimo triangolo del giocatore
che ne perde, preferendo quelli senza runout; se il triangolo girato aveva un
runout, il runout si toglie, perché era di chi l'aveva vinto.

**Cosa resta fuori, e viene rifiutato.** Gare non concluse (si corregge
dall'app), trio, partite a set, la X, partite con un numero di triangoli
diverso da quello giocato, gare con uno spareggio registrato, campionati con
inviti ai playoff già partiti, e la correzione che cambierebbe il vincitore
della gara. Ognuno di questi casi avrebbe bisogno di regole sue.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from models.base import db, utc_now
from models.status_enum import GaraStatus, MatchStatus
from models.transaction.manager import transactional

#: Le metriche dei traguardi che una correzione può togliere a qualcuno.
METRICHE_TOCCATE: Tuple[str, ...] = (
    "match_wins",
    "win_streak",
    "tournament_podium",
)


class CorrezioneRifiutata(ValueError):
    """La correzione non si può fare: il motivo è nel messaggio."""


class _SoloProva(Exception):
    """Porta fuori il rapporto della prova, annullando la transazione."""

    def __init__(self, rapporto: Dict[str, Any]):
        super().__init__("prova")
        self.rapporto = rapporto


def correggi(
    match_id: int,
    player1_score: int,
    player2_score: int,
    corrected_by_id: int,
    note: Optional[str] = None,
    *,
    scrivi: bool = False,
) -> Dict[str, Any]:
    """Corregge il risultato e restituisce il rapporto di prima e dopo.

    Con `scrivi=False` fa tutto, controlli compresi, e poi annulla: il
    rapporto dice cosa succederebbe, e sul database non resta niente.

    Raises:
        CorrezioneRifiutata: se la correzione non è ammessa, o se un
            controllo di coerenza fallisce. Non resta scritto niente.
    """
    try:
        return _esegui(
            match_id, player1_score, player2_score, corrected_by_id, note, scrivi
        )
    except _SoloProva as prova:
        return prova.rapporto


@transactional(domain="match")
def _esegui(
    match_id: int,
    player1_score: int,
    player2_score: int,
    corrected_by_id: int,
    note: Optional[str],
    scrivi: bool,
) -> Dict[str, Any]:
    from models.competition.models import Gara
    from models.match.models import Match, MatchCorrection
    from models.user.models import User

    match = db.session.get(Match, match_id)
    if match is None:
        raise CorrezioneRifiutata(f"Partita {match_id} non trovata")
    gara = db.session.get(Gara, match.gara_id) if match.gara_id else None
    autore = db.session.get(User, corrected_by_id)
    _verifica_ammissibile(match, gara, autore, player1_score, player2_score)
    assert gara is not None

    prima = _fotografia(gara)

    # 1. Fedeltà: sui dati invariati il ricalcolo deve rifare lo stato salvato.
    _ricalcola(gara)
    rifatto = _fotografia(gara)
    differenze = _differenze(prima, rifatto)
    if differenze:
        raise CorrezioneRifiutata(
            "Lo stato salvato non coincide con quello che il codice ricalcola "
            "sui dati invariati, quindi la correzione non parte.\n  "
            + "\n  ".join(differenze)
        )
    podi_della_chiusura = _podio_della_chiusura(gara)
    if prima["podi"] != podi_della_chiusura:
        raise CorrezioneRifiutata(
            "L'XP di podio della gara non corrisponde alla classifica salvata: "
            f"registro {sorted(prima['podi'])}, "
            f"classifica {sorted(podi_della_chiusura)}"
        )
    vincitore_gara = _vincitore_gara(gara)
    if vincitore_gara is None:
        raise CorrezioneRifiutata("Il primo posto è a pari merito: non gestito")

    # 2. La partita.
    vincitore_prima = match.winner_id
    girati = _gira_triangoli(match, player1_score, player2_score)
    db.session.add(
        MatchCorrection(
            match_id=match.id,
            corrected_by_id=corrected_by_id,
            previous_player1_score=match.player1_score,
            previous_player2_score=match.player2_score,
            previous_status=match.status,
            new_player1_score=player1_score,
            new_player2_score=player2_score,
            note=(note or "").strip() or None,
        )
    )
    match.player1_score = player1_score
    match.player2_score = player2_score
    match.winner_id = _vincitore(match, player1_score, player2_score)
    # Come la correzione dell'app: le conferme dei giocatori erano per il
    # risultato sbagliato, e la partita la chiude chi l'ha corretta.
    match.reset_confirmations()
    match.status = MatchStatus.CLOSED_UNILATERALLY.value
    db.session.add(match)
    db.session.flush()

    # 3. Ciò che ne discende.
    _ricalcola(gara)
    if _vincitore_gara(gara) != vincitore_gara:
        raise CorrezioneRifiutata(
            "La correzione cambierebbe il vincitore della gara: questo modulo "
            "non lo gestisce"
        )
    podio = _sposta_podio(gara, prima["podi"])
    traguardi = _riallinea_traguardi(
        perdono={vincitore_prima} | podio["tolti"],
        guadagnano={match.winner_id} | podio["dati"],
    )

    # 4. Le tre cose che devono dirsi la stessa cosa.
    _verifica_coerenza(match)
    dopo = _fotografia(gara)
    if dopo["podi"] != _podio_atteso(gara):
        raise CorrezioneRifiutata("Dopo la correzione il podio non torna")

    rapporto = {
        "match_id": match.id,
        "gara": {"id": gara.id, "name": gara.name, "campionato_id": gara.campionato_id},
        "giocatori": {
            "player1": _nome(match.player1_id),
            "player2": _nome(match.player2_id),
        },
        "punteggio_prima": (
            prima["partita"][match.id]["player1_score"],
            prima["partita"][match.id]["player2_score"],
        ),
        "punteggio_dopo": (player1_score, player2_score),
        "vincitore_prima": _nome(vincitore_prima),
        "vincitore_dopo": _nome(match.winner_id),
        "triangoli_girati": girati,
        "classifica_gara_prima": _leggibile_gara(prima),
        "classifica_gara_dopo": _leggibile_gara(dopo),
        "classifica_campionato_prima": prima["generale"],
        "classifica_campionato_dopo": dopo["generale"],
        "elo": _differenze_elo(prima, dopo),
        "podio": {
            "tolto_a": sorted(_nome(u) for u in podio["tolti"]),
            "dato_a": sorted(_nome(u) for u in podio["dati"]),
        },
        "traguardi": traguardi,
        "avvisi": _avvisi(gara),
        "scritto": scrivi,
    }
    if not scrivi:
        raise _SoloProva(rapporto)
    return rapporto


# ---------------------------------------------------------------- controlli


def _verifica_ammissibile(match, gara, autore, p1: int, p2: int) -> None:
    from models.competition.spareggio_service import SpareggioService
    from models.match.correction_service import MatchCorrectionService

    if gara is None:
        raise CorrezioneRifiutata("La partita non appartiene a una gara")
    if gara.status != GaraStatus.COMPLETED.value:
        raise CorrezioneRifiutata(
            "La gara non è conclusa: il risultato si corregge dall'app"
        )
    if autore is None:
        raise CorrezioneRifiutata("Chi corregge non esiste")
    if match.is_bye:
        raise CorrezioneRifiutata("La X non ha un risultato da correggere")
    if match.is_trio or match.is_multi_set:
        raise CorrezioneRifiutata("Trio e partite a set non sono gestiti")
    if not MatchStatus.is_finished(match.status):
        raise CorrezioneRifiutata("La partita non risulta chiusa")
    if (p1, p2) == (match.player1_score, match.player2_score):
        raise CorrezioneRifiutata("Il punteggio è già questo")
    if p1 + p2 != (match.player1_score or 0) + (match.player2_score or 0):
        raise CorrezioneRifiutata(
            "Il numero di triangoli cambierebbe: qui si corregge solo di chi "
            "sono, non quanti se ne sono giocati"
        )
    MatchCorrectionService._validate_score(match, p1, p2)
    if SpareggioService.has_recorded_ssr(gara.id):
        raise CorrezioneRifiutata("La gara ha uno spareggio registrato")
    if gara.campionato_id and _inviti_playoff(gara.campionato_id):
        raise CorrezioneRifiutata(
            "Il campionato ha già inviti ai playoff, fatti sulla classifica di prima"
        )
    vinti = _triangoli_per_giocatore(match)
    if (vinti.get(match.player1_id, 0), vinti.get(match.player2_id, 0)) != (
        match.player1_score,
        match.player2_score,
    ):
        raise CorrezioneRifiutata(
            "I triangoli registrati non tornano col punteggio salvato"
        )


def _verifica_coerenza(match) -> None:
    vinti = _triangoli_per_giocatore(match)
    if (vinti.get(match.player1_id, 0), vinti.get(match.player2_id, 0)) != (
        match.player1_score,
        match.player2_score,
    ):
        raise CorrezioneRifiutata("Dopo la correzione i triangoli non tornano")
    if match.winner_id != _vincitore(match, match.player1_score, match.player2_score):
        raise CorrezioneRifiutata("Dopo la correzione il vincitore non torna")


def _inviti_playoff(campionato_id: int) -> bool:
    from models.playoff.models import PlayoffConfiguration, PlayoffQualification

    return (
        db.session.query(PlayoffQualification.id)
        .join(
            PlayoffConfiguration,
            PlayoffConfiguration.id == PlayoffQualification.configuration_id,
        )
        .filter(PlayoffConfiguration.campionato_id == campionato_id)
        .first()
        is not None
    )


def _avvisi(gara) -> List[str]:
    """Ciò che la correzione non può sistemare, detto e non taciuto."""
    from models.competition.models import Gara

    avvisi = [
        "Gli abbinamenti dei turni dopo restano quelli giocati.",
        "L'XP della partita resta dov'è: l'app lo dà alla prima chiusura.",
    ]
    if gara.campionato_id:
        dopo = (
            Gara.query.filter(
                Gara.campionato_id == gara.campionato_id,
                Gara.number > (gara.number or 0),
                Gara.status.notin_(
                    [GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value]
                ),
            )
            .order_by(Gara.number)
            .all()
        )
        for g in dopo:
            avvisi.append(
                f"La gara {g.number} «{g.name}» è già partita: se il primo turno "
                "era seminato sulla classifica del campionato, lo è stato su "
                "quella di prima."
            )
    return avvisi


# ---------------------------------------------------------------- partita


def _vincitore(match, p1: int, p2: int) -> Optional[int]:
    if p1 > p2:
        return match.player1_id
    if p2 > p1:
        return match.player2_id
    return None


def _triangoli_attivi(match) -> List[Any]:
    from models.match.models import Rack

    return (
        Rack.query.filter(Rack.match_id == match.id, Rack.is_deleted.is_(False))
        .order_by(Rack.rack_number)
        .all()
    )


def _triangoli_per_giocatore(match) -> Counter:
    return Counter(r.winner_id for r in _triangoli_attivi(match))


def _gira_triangoli(match, p1: int, p2: int) -> List[Dict[str, Any]]:
    """Gira il vincitore del minimo numero di triangoli. Restituisce quali."""
    da_girare = p1 - (match.player1_score or 0)
    if da_girare > 0:
        da, a = match.player2_id, match.player1_id
    else:
        da, a = match.player1_id, match.player2_id
    quanti = abs(da_girare)

    candidati = [r for r in _triangoli_attivi(match) if r.winner_id == da]
    # Prima quelli senza runout, poi dall'ultimo: un runout girato andrebbe
    # tolto, e un fatto in meno è meglio di uno in più.
    candidati.sort(key=lambda r: (bool(r.is_run_out), -r.rack_number))
    if len(candidati) < quanti:
        raise CorrezioneRifiutata("Non ci sono abbastanza triangoli da girare")

    oggi = utc_now().strftime("%Y-%m-%d")
    girati = []
    for rack in candidati[:quanti]:
        aveva_runout = bool(rack.is_run_out)
        rack.winner_id = a
        rack.is_run_out = False
        nota = f"Vincitore corretto il {oggi}: era {_nome(da)}."
        rack.admin_note = (
            f"{rack.admin_note} {nota}".strip() if rack.admin_note else nota
        )
        db.session.add(rack)
        girati.append(
            {
                "rack_number": rack.rack_number,
                "da": _nome(da),
                "a": _nome(a),
                "runout_tolto": aveva_runout,
            }
        )
    return girati


# ---------------------------------------------------------------- ricalcolo


def _ricalcola(gara) -> None:
    """Rifà tutto ciò che discende dai risultati, come lo farebbe la chiusura."""
    from models.classification.campionato_classification import (
        ClassificationService,
    )
    from models.classification.gara_classification import (
        StrategyBasedClassificationService,
    )
    from models.classification.models import Classification
    from models.competition.spareggio_service import SpareggioService
    from models.match.models import Match
    from models.rating.calculation_service import RatingCalculationService

    db.session.flush()
    turni = sorted(
        {
            riga[0]
            for riga in db.session.query(Match.round_number)
            .filter(Match.gara_id == gara.id, Match.round_number.isnot(None))
            .distinct()
        }
    )
    servizio = StrategyBasedClassificationService()
    for turno in turni:
        servizio.calculate_round_classification(gara.id, turno)
    if turni:
        servizio.calculate_gara_classification(gara.id)
    # È il passo con cui la chiusura scrive le posizioni (StateService.complete):
    # chi resta pari dopo la catena condivide la posizione.
    SpareggioService.apply_final_positions(gara.id)

    # Le righe del campionato sono una copia (ADR-073): si rinfrescano se ci
    # sono, e non si creano se non ci sono — stessa regola dell'ADR-048.
    if gara.campionato_id and (
        db.session.query(Classification.id)
        .filter(Classification.campionato_id == gara.campionato_id)
        .first()
        is not None
    ):
        ClassificationService.update_campionato_classification(gara.campionato_id)

    RatingCalculationService.recalculate_all_pools()
    db.session.flush()


# ---------------------------------------------------------------- podio


def _transazioni_podio(gara_id: int) -> List[Any]:
    from models.gamification.models import XPTransaction, XPTransactionType

    righe = XPTransaction.query.filter(
        XPTransaction.transaction_type == XPTransactionType.TOURNAMENT_PODIUM
    ).all()
    risultato = []
    for riga in righe:
        try:
            legati = json.loads(riga.related_entities or "{}")
        except (ValueError, TypeError):
            continue
        if legati.get("gara_id") == gara_id:
            risultato.append(riga)
    return risultato


def _podi_registrati(gara_id: int) -> Set[int]:
    return {t.user_id for t in _transazioni_podio(gara_id)}


def _vincitore_gara(gara) -> Optional[int]:
    from models.classification.models import GaraClassification

    primi = GaraClassification.query.filter_by(gara_id=gara.id, position=1).all()
    return primi[0].user_id if len(primi) == 1 else None


def _podio_della_chiusura(gara) -> Set[int]:
    """Chi ha ricevuto l'XP di podio alla chiusura, secondo la regola di allora.

    `StateService.complete` passa all'handler le righe di
    `RoundClassification.ordered_for_display` dell'ultimo turno, e l'handler
    premia le **prime tre**, vincitore escluso: con un pari merito a cavallo
    del terzo posto qualcuno dei pari resta fuori, e decide l'ordine di
    elencazione. Serve al controllo di fedeltà, che deve confrontare il
    registro con la regola che l'ha scritto.
    """
    from models.classification.models import RoundClassification
    from models.competition.spareggio_service import SpareggioService
    from models.user.models import User

    righe = RoundClassification.ordered_for_display(
        gara.id, SpareggioService.effective_final_round(gara)
    )
    if not righe:
        return set()
    vincitore = righe[0].user_id
    premiati = set()
    for riga in righe[:3]:
        if riga.user_id == vincitore:
            continue
        utente = db.session.get(User, riga.user_id)
        if utente is not None and not utente.is_admin:
            premiati.add(riga.user_id)
    return premiati


def _podio_atteso(gara) -> Set[int]:
    """Chi deve avere l'XP di podio dopo la correzione: sul podio, vincitore escluso.

    Il vincitore ha `TOURNAMENT_WIN`, non il podio. A pari merito sul terzo
    posto il podio è di **tutti** i pari: «3° pari merito» è un terzo posto.
    È una decisione dell'utente del 2026-11-19, presa per questa correzione,
    e diverge apposta da `_podio_della_chiusura`, che premia le prime tre
    righe. Gli admin non ricevono XP (`LevelService.award_xp`).
    """
    from models.classification.models import GaraClassification
    from models.user.models import User

    vincitore = _vincitore_gara(gara)
    righe = GaraClassification.query.filter(
        GaraClassification.gara_id == gara.id, GaraClassification.position <= 3
    ).all()
    attesi = set()
    for riga in righe:
        if riga.user_id == vincitore:
            continue
        utente = db.session.get(User, riga.user_id)
        if utente is not None and not utente.is_admin:
            attesi.add(riga.user_id)
    return attesi


def _sposta_podio(gara, registrati: Set[int]) -> Dict[str, Set[int]]:
    """Toglie l'XP di podio a chi non è più sul podio e lo dà a chi c'è entrato.

    La riga di chi esce si **cancella**, non si compensa: il traguardo «podio»
    conta le righe `TOURNAMENT_PODIUM` (`AchievementMetrics`), e un movimento
    negativo dello stesso tipo varrebbe come un podio in più. La traccia della
    correzione resta su `MatchCorrection`. Chi entra riceve l'XP da
    `LevelService.award_xp`, come alla chiusura.
    """
    from models.classification.models import GaraClassification
    from models.gamification.config_service import GamificationConfigService
    from models.gamification.level_service import LevelService
    from models.gamification.models import XPTransactionType

    attesi = _podio_atteso(gara)
    tolti = registrati - attesi
    dati = attesi - registrati

    for riga in _transazioni_podio(gara.id):
        if riga.user_id in tolti:
            db.session.delete(riga)
    db.session.flush()

    xp = GamificationConfigService.get_xp_rate(XPTransactionType.TOURNAMENT_PODIUM)
    for user_id in sorted(dati):
        riga = GaraClassification.query.filter_by(
            gara_id=gara.id, user_id=user_id
        ).first()
        posizione = riga.position if riga else None
        LevelService.award_xp(
            user_id=user_id,
            xp_amount=xp,
            transaction_type=XPTransactionType.TOURNAMENT_PODIUM,
            reason=f"Finished {posizione} in tournament {gara.id}",
            related_entities={"gara_id": gara.id, "position": posizione},
        )
    db.session.flush()
    return {"tolti": tolti, "dati": dati}


def _riallinea_traguardi(
    perdono: Iterable[Optional[int]], guadagnano: Iterable[Optional[int]]
) -> Dict[str, Any]:
    """Livelli e traguardi di chi la correzione ha toccato.

    Prima la revoca (che restituisce l'XP del traguardo con un movimento), poi
    il livello dal registro, poi lo sblocco: è l'ordine dell'ADR-048.
    """
    from models.gamification.achievement_service import AchievementService
    from models.gamification.recalc_service import GamificationRecalcService

    tolti: Dict[str, List[str]] = {}
    sbloccati: Dict[str, List[str]] = {}
    toccati = {u for u in list(perdono) + list(guadagnano) if u}
    for user_id in sorted(u for u in set(perdono) if u):
        revocati = AchievementService.revoke_no_longer_earned(user_id, METRICHE_TOCCATE)
        if revocati:
            tolti[_nome(user_id)] = revocati
    db.session.flush()
    for user_id in sorted(toccati):
        GamificationRecalcService._rebuild_level(user_id)
        nuovi = AchievementService.reconcile_achievements(user_id)
        if nuovi:
            sbloccati[_nome(user_id)] = nuovi
    db.session.flush()
    return {"tolti": tolti, "sbloccati": sbloccati}


# ---------------------------------------------------------------- fotografie


#: Le posizioni mostrate vuote valgono la posizione (`PosizioneMostrataMixin`):
#: sulle righe scritte prima del 2026-10-11 sono NULL, e un ricalcolo le
#: riempie con lo stesso numero. Non è una differenza.
_RIPIEGHI = {
    "shown_position": "position",
    "shown_group_position": "group_position",
    "shown_previous_position": "previous_position",
}


def _riga(oggetto) -> Tuple:
    """Una riga come tupla confrontabile: niente id né date di calcolo."""
    valori = {}
    for colonna in oggetto.__table__.columns:
        nome = colonna.name
        if nome == "id":
            continue
        valore = getattr(oggetto, colonna.key)
        if isinstance(valore, (datetime, date)):
            continue
        if isinstance(valore, float):
            valore = round(valore, 6)
        if hasattr(valore, "value"):
            valore = valore.value
        if isinstance(valore, (list, dict)):
            valore = json.dumps(valore, sort_keys=True)
        valori[nome] = valore
    for mostrata, base in _RIPIEGHI.items():
        if mostrata in valori and valori[mostrata] is None:
            valori[mostrata] = valori.get(base)
    return tuple(sorted(valori.items()))


def _fotografia(gara) -> Dict[str, Any]:
    from models.campionato.statistics_service import TournamentStatisticsService
    from models.classification.models import (
        Classification,
        GaraClassification,
        RoundClassification,
    )
    from models.match.models import Match
    from models.rating.models import MatchRatingHistory, PlayerRating
    from models.user.models import User

    db.session.flush()
    db.session.expire_all()

    def multiinsieme(righe):
        return Counter(_riga(r) for r in righe)

    generale: List[Tuple[Any, ...]] = []
    if gara.campionato_id:
        for posizione, dati in TournamentStatisticsService().classifica_generale(
            gara.campionato_id
        ):
            generale.append(
                (
                    dati.get("shown_position", posizione),
                    _nome(dati["user_id"]),
                    dati.get("total_matches_won"),
                    dati.get("total_rack_difference"),
                    dati.get("total_points"),
                )
            )

    partite = Match.query.filter_by(gara_id=gara.id).all()
    return {
        "partita": {
            m.id: {"player1_score": m.player1_score, "player2_score": m.player2_score}
            for m in partite
        },
        "gara": multiinsieme(GaraClassification.query.filter_by(gara_id=gara.id)),
        "turni": multiinsieme(RoundClassification.query.filter_by(gara_id=gara.id)),
        "campionato": multiinsieme(
            Classification.query.filter_by(campionato_id=gara.campionato_id)
            if gara.campionato_id
            else []
        ),
        "elo_utenti": {u.id: u.elo_rating for u in User.query.all()},
        "rating": multiinsieme(PlayerRating.query.all()),
        "storia_rating": multiinsieme(MatchRatingHistory.query.all()),
        "podi": _podi_registrati(gara.id),
        "righe_gara": [
            (
                r.shown_position or r.position,
                _nome(r.user_id),
                r.matches_won,
                r.rack_difference,
            )
            for r in GaraClassification.query.filter_by(gara_id=gara.id).order_by(
                GaraClassification.position, GaraClassification.user_id
            )
        ],
        "generale": generale,
    }


_CONFRONTATE = (
    "gara",
    "turni",
    "campionato",
    "elo_utenti",
    "rating",
    "storia_rating",
)


def _differenze(prima: Dict[str, Any], dopo: Dict[str, Any]) -> List[str]:
    """Dove due fotografie divergono, in righe leggibili da una console."""
    diverse = []
    for chiave in _CONFRONTATE:
        if prima[chiave] == dopo[chiave]:
            continue
        if isinstance(prima[chiave], Counter):
            in_meno = list((prima[chiave] - dopo[chiave]).elements())
            in_piu = list((dopo[chiave] - prima[chiave]).elements())
            riga = f"{chiave}: {len(in_meno)} righe salvate diverse dal ricalcolo"
            if len(in_meno) != len(in_piu):
                riga += f" (salvate {len(in_meno)}, ricalcolate {len(in_piu)})"
            if in_meno and in_piu:
                a, b = dict(in_meno[0]), dict(in_piu[0])
                campi = [k for k in a if a.get(k) != b.get(k)]
                esempio = ", ".join(f"{k} {a.get(k)} → {b.get(k)}" for k in campi[:4])
                riga += f"; per esempio {esempio}"
            diverse.append(riga)
        else:
            cambiati = [
                k for k in prima[chiave] if prima[chiave].get(k) != dopo[chiave].get(k)
            ]
            esempi = ", ".join(
                f"{_nome(k)} {prima[chiave].get(k)} → {dopo[chiave].get(k)}"
                for k in cambiati[:5]
            )
            diverse.append(f"{chiave}: {len(cambiati)} valori diversi ({esempi})")
    return diverse


def _differenze_elo(prima: Dict[str, Any], dopo: Dict[str, Any]) -> List[Tuple]:
    cambiati = []
    for user_id, valore in prima["elo_utenti"].items():
        nuovo = dopo["elo_utenti"].get(user_id)
        if nuovo != valore:
            cambiati.append((_nome(user_id), valore, nuovo))
    return sorted(cambiati)


def _leggibile_gara(foto: Dict[str, Any]) -> List[Tuple]:
    return foto["righe_gara"]


def _nome(user_id: Optional[int]) -> str:
    from models.user.models import User

    if not user_id:
        return "—"
    utente = db.session.get(User, user_id)
    return utente.username if utente else f"#{user_id}"
