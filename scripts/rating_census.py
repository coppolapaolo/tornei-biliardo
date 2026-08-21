"""Censimento dei dati di rating: c'è abbastanza segnale per il backtest?

**Perché esiste.** ADR-052 lascia aperta la scelta fra due motori di rating
(Elo iterativo a rack e rifit globale Bradley-Terry) e la affida a un backtest.
Ma il backtest ha un prerequisito che va verificato *prima* di scrivere una
riga di modello: che i dati bastino a distinguere i due. Questo è il passo 0
dell'ADR.

Le tre domande a cui risponde, in ordine di importanza:

1. **Quanti rack abbiamo davvero?** Non quante partite: l'unità di misura del
   modello nuovo è il rack, e una gara di corse a 3 produce meno di un terzo
   dei dati di una a 9 a parità di partite.
2. **Il grafo dei confronti è connesso?** Un rating confronta solo *dentro* una
   componente connessa. Se il circolo è spezzato in gruppi che non si
   incontrano mai, i numeri fra gruppi diversi non significano niente — e il
   rifit globale, che pretende di ordinare tutti insieme, ne soffre più
   dell'iterativo. È la misura che può bocciare una delle due strade prima
   ancora di provarle.
3. **Quante finestre temporali si possono usare?** La validazione dell'ADR è a
   origine mobile: serve sapere quanti tagli mensili hanno abbastanza partite
   dopo di sé da valere come verifica.

**Sola lettura.** Non scrive niente: nessun `commit`, nessuna `INSERT`, nessun
`UPDATE`. Si può quindi lanciare in console **senza** disabilitare la web app,
al contrario di quasi tutti gli altri script di produzione.

**I due perimetri.** I pool esistenti non contano le stesse partite: `ELO`
(competitivo) vede solo i tornei, `ELO_GLOBAL` fonde tornei e sfide
individuali confermate. Il censimento li misura entrambi, perché il modello
nuovo erediterebbe l'uno o l'altro e la risposta può essere diversa. Il
perimetro è quello di `recalculate_all_elo` / `recalculate_all_elo_global`, e
il filtro di ammissibilità è lo stesso `RatingEligibility` del motore: se qui
comparisse un conteggio diverso da quello che il motore processa, sarebbe
questo script a sbagliare.

Uso::

    venv/bin/python scripts/rating_census.py
    venv/bin/python scripts/rating_census.py --json censimento.json
"""

import argparse
import json
import logging
import math
import os
import sys
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
# Servono entrambe: la radice del progetto (per `app`, `models`) e la cartella
# scripts (per `prod_env`), anche quando il file viene caricato per path invece
# che eseguito, come fanno i test. La radice va inserita per ultima così da
# restare davanti a `scripts/` in sys.path.
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from prod_env import bootstrap_and_create_app  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

#: Le soglie di rack per giocatore su cui si riassume la distribuzione.
#: 200 è la soglia che FargoRate chiama *established*; le altre servono a
#: vedere la forma della coda, non hanno un significato ufficiale.
SOGLIE_RACK: Tuple[int, ...] = (30, 100, 200, 500)

#: Sotto questo numero di partite ammissibili una finestra mensile non vale
#: come verifica: la differenza fra due modelli sarebbe tutta rumore.
MIN_PARTITE_PER_FINESTRA = 20


class Partita:
    """Una partita già ridotta a ciò che serve al censimento.

    Esiste per non far dipendere il resto del file dalle differenze fra le due
    tabelle (`match` e `individual_match`), che hanno colonne diverse per dire
    le stesse cose.
    """

    __slots__ = (
        "origine",
        "id",
        "player_ids",
        "racks",
        "ended_at",
        "distanza",
        "race_to",
        "multi_set",
        "is_trio",
        "esclusione",
    )

    def __init__(
        self,
        origine: str,
        id_: int,
        player_ids: Sequence[Optional[int]],
        racks: int,
        ended_at: Any,
        distanza: Optional[int],
        race_to: bool,
        multi_set: bool,
        is_trio: bool,
        esclusione: Optional[str],
    ) -> None:
        self.origine = origine
        self.id = id_
        self.player_ids = [pid for pid in player_ids if pid is not None]
        self.racks = racks
        self.ended_at = ended_at
        self.distanza = distanza
        self.race_to = race_to
        self.multi_set = multi_set
        self.is_trio = is_trio
        self.esclusione = esclusione

    @property
    def ammissibile(self) -> bool:
        return self.esclusione is None


def _partite_torneo() -> List[Partita]:
    """Le partite di gara finite, con il motivo di esclusione già risolto.

    Stesso perimetro e stesso ordine di `recalculate_all_elo`: stato finito,
    cronologico per `ended_at` e poi `id`. Le categorie si caricano con
    `build_index` in una query sola — senza, l'ammissibilità farebbe due
    letture per ogni partita.
    """
    from models.match.models import Match
    from models.rating.eligibility import RatingEligibility
    from models.status_enum import MatchStatus

    matches = (
        Match.query.filter(Match.status.in_(MatchStatus.finished_values()))
        .order_by(Match.ended_at.asc(), Match.id.asc())
        .all()
    )
    categorie = RatingEligibility.build_index(matches)

    partite: List[Partita] = []
    for match in matches:
        motivo = RatingEligibility.exclusion_reason(match, categorie)
        partite.append(
            Partita(
                origine="torneo",
                id_=match.id,
                player_ids=RatingEligibility.player_ids(match),
                racks=_racks_di(match),
                ended_at=match.ended_at,
                distanza=_distanza_di(match),
                race_to=_e_race_to(match),
                multi_set=_e_multi_set(match),
                is_trio=bool(getattr(match, "is_trio", False)),
                esclusione=motivo.value if motivo is not None else None,
            )
        )
    return partite


def _partite_casual() -> List[Partita]:
    """Le sfide individuali confermate dai due giocatori.

    Stesso filtro di `recalculate_all_elo_global`: solo `CONFIRMED_BY_BOTH`.
    Gli altri stati non sono partite giocate e confermate, quindi non sono
    dati. Qui non si applica `RatingEligibility`: non esiste una gara, quindi
    non esistono handicap né categorie da confrontare.
    """
    from models.individual_match.models import IndividualMatch
    from models.status_enum import MatchStatus

    matches = (
        IndividualMatch.query.filter(
            IndividualMatch.status == MatchStatus.CONFIRMED_BY_BOTH
        )
        .order_by(IndividualMatch.ended_at.asc(), IndividualMatch.id.asc())
        .all()
    )
    return [
        Partita(
            origine="casual",
            id_=im.id,
            player_ids=[im.player1_id, im.player2_id],
            racks=(im.player1_score or 0) + (im.player2_score or 0),
            ended_at=im.ended_at,
            distanza=getattr(im, "distance", None),
            race_to=_e_race_to(im),
            multi_set=False,
            is_trio=False,
            esclusione=None,
        )
        for im in matches
    ]


def _racks_di(match: Any) -> int:
    """I rack giocati nella partita, trii compresi."""
    if getattr(match, "is_trio", False) and getattr(match, "trio_match", None):
        trio = match.trio_match
        return (
            (trio.player1_racks or 0)
            + (trio.player2_racks or 0)
            + (trio.player3_racks or 0)
        )
    return (match.player1_score or 0) + (match.player2_score or 0)


def _e_race_to(match: Any) -> bool:
    """La partita è una **corsa** a N, o si giocano N rack **esatti**?

    È la distinzione più importante di tutto il censimento, e per mesi è stata
    invisibile perché lo script etichettava tutto «al N», il modo di dire delle
    corse. Nelle gare fatte finora la distanza è quasi sempre esatta: si
    giocano N rack e si può pareggiare, non si smette appena uno arriva a N.

    Cambia due cose concrete: quanti rack produce una partita (esattamente N
    contro N..2N-1) e come si passa dalla probabilità di rack a quella di
    partita — binomiale contro binomiale negativa.

    Come per il multi-set, la fonte è il value object `Distance` (ADR-027).
    """
    try:
        return bool(match.distance_config.is_race_to_racks)
    except Exception:  # pragma: no cover - dati storici incompleti
        return True


def _e_multi_set(match: Any) -> bool:
    """La partita si gioca a set, quindi il punteggio non è in rack.

    Va chiesto al value object `Distance` (ADR-027), non a
    `effective_is_race_to_sets`: quella property dice *come* si contano i set
    (al meglio di N o esattamente N), non *se* la partita ne usi — e vale
    `True` anche su una normalissima partita a set singolo. Chiederlo a lei
    marcava multi-set l'intero database.
    """
    try:
        return bool(match.distance_config.is_multi_set)
    except Exception:  # pragma: no cover - dati storici incompleti
        return False


def _distanza_di(match: Any) -> Optional[int]:
    """La distanza in vigore per questa partita, override per turno compresi.

    Si passa da `effective_distance` e non da `gara.distance` perché le
    `RoundConfiguration` altrimenti sparirebbero (ADR-027), e la distanza è
    esattamente ciò di cui vogliamo la distribuzione.
    """
    try:
        return int(match.effective_distance)
    except Exception:  # pragma: no cover - dati storici incompleti
        return None


def _percentili(valori: Sequence[int], quantili: Sequence[int]) -> Dict[str, int]:
    """Percentili su interi, con interpolazione al ribasso (nearest-rank)."""
    if not valori:
        return {f"p{q}": 0 for q in quantili}
    ordinati = sorted(valori)
    risultato: Dict[str, int] = {}
    for q in quantili:
        rango = max(1, math.ceil(q / 100 * len(ordinati)))
        risultato[f"p{q}"] = ordinati[rango - 1]
    return risultato


def _censimento(partite: Sequence[Partita], etichetta: str) -> Dict[str, Any]:
    """Tutti i conteggi per un perimetro."""
    import networkx as nx

    ammissibili = [p for p in partite if p.ammissibile]
    esclusioni = Counter(p.esclusione for p in partite if not p.ammissibile)

    rack_per_giocatore: Counter = Counter()
    grafo = nx.Graph()
    mesi: Counter = Counter()
    distanze_corsa: Counter = Counter()
    distanze_esatte: Counter = Counter()
    rack_totali = 0
    trii = 0
    multi_set = 0
    senza_data = 0

    for partita in ammissibili:
        rack_totali += partita.racks
        if partita.is_trio:
            trii += 1
        if partita.multi_set:
            multi_set += 1
        if partita.distanza is not None:
            bersaglio = distanze_corsa if partita.race_to else distanze_esatte
            bersaglio[partita.distanza] += 1
        if partita.ended_at is None:
            senza_data += 1
        else:
            mesi[partita.ended_at.strftime("%Y-%m")] += 1

        for pid in partita.player_ids:
            rack_per_giocatore[pid] += partita.racks
            grafo.add_node(pid)
        # Il trio è un girone interno: tutte e tre le coppie si sono
        # incontrate, quindi il grafo prende tutti gli archi.
        for i, primo in enumerate(partita.player_ids):
            for secondo in partita.player_ids[i + 1 :]:
                grafo.add_edge(primo, secondo)

    componenti = sorted(nx.connected_components(grafo), key=len, reverse=True)
    maggiore = componenti[0] if componenti else set()
    rack_nella_maggiore = sum(rack_per_giocatore[pid] for pid in maggiore)
    # Ogni rack è contato una volta per giocatore coinvolto: il totale sui
    # giocatori è quindi un multiplo di quello sulle partite, e il rapporto
    # fra i due resta valido come frazione.
    rack_per_giocatore_totali = sum(rack_per_giocatore.values())

    finestre_utili = sorted(
        mese for mese, quante in mesi.items() if quante >= MIN_PARTITE_PER_FINESTRA
    )

    return {
        "perimetro": etichetta,
        "partite": {
            "totali": len(partite),
            "ammissibili": len(ammissibili),
            "escluse": len(partite) - len(ammissibili),
            "per_motivo": dict(esclusioni),
            "trii": trii,
            "multi_set": multi_set,
            "senza_data_di_fine": senza_data,
        },
        "rack": {
            "totali": rack_totali,
            "media_per_partita": (
                round(rack_totali / len(ammissibili), 2) if ammissibili else 0.0
            ),
            "distanze_a_corsa": dict(sorted(distanze_corsa.items())),
            "distanze_esatte": dict(sorted(distanze_esatte.items())),
            "partite_pareggiabili": sum(
                quante for n, quante in distanze_esatte.items() if n % 2 == 0
            ),
        },
        "giocatori": {
            "totali": len(rack_per_giocatore),
            "sopra_soglia": {
                str(soglia): sum(
                    1 for rack in rack_per_giocatore.values() if rack >= soglia
                )
                for soglia in SOGLIE_RACK
            },
            "percentili_rack": _percentili(
                list(rack_per_giocatore.values()), (25, 50, 75, 90)
            ),
        },
        "grafo": {
            "nodi": grafo.number_of_nodes(),
            "coppie_distinte": grafo.number_of_edges(),
            "componenti": len(componenti),
            "dimensione_componenti": [len(c) for c in componenti[:10]],
            "giocatori_nella_maggiore": len(maggiore),
            "quota_rack_nella_maggiore": (
                round(rack_nella_maggiore / rack_per_giocatore_totali, 4)
                if rack_per_giocatore_totali
                else 0.0
            ),
        },
        "tempo": {
            "partite_per_mese": dict(sorted(mesi.items())),
            "mesi_coperti": len(mesi),
            "finestre_utili": finestre_utili,
            "soglia_finestra": MIN_PARTITE_PER_FINESTRA,
        },
    }


def _stampa(dati: Dict[str, Any]) -> None:
    """Il censimento in forma leggibile, con il verdetto in fondo."""
    partite = dati["partite"]
    rack = dati["rack"]
    giocatori = dati["giocatori"]
    grafo = dati["grafo"]
    tempo = dati["tempo"]

    logger.info("")
    logger.info("=" * 62)
    logger.info("PERIMETRO: %s", dati["perimetro"])
    logger.info("=" * 62)

    logger.info("")
    logger.info("Partite")
    logger.info("  finite/confermate ....... %d", partite["totali"])
    logger.info("  ammissibili per l'Elo ... %d", partite["ammissibili"])
    logger.info("  escluse ................. %d", partite["escluse"])
    for motivo, quante in sorted(partite["per_motivo"].items()):
        logger.info("      %-28s %d", motivo, quante)
    if partite["trii"]:
        logger.info("  di cui trii ............. %d", partite["trii"])
    if partite["multi_set"]:
        logger.info(
            "  di cui multi-set ........ %d  ⚠ il punteggio è in set, non in "
            "rack: da trattare a parte nel backtest",
            partite["multi_set"],
        )
    if partite["senza_data_di_fine"]:
        logger.info(
            "  senza data di fine ...... %d  ⚠ non collocabili in una finestra "
            "temporale",
            partite["senza_data_di_fine"],
        )

    logger.info("")
    logger.info("Rack (l'unità di misura del modello nuovo)")
    logger.info("  totali .................. %d", rack["totali"])
    logger.info("  media per partita ....... %s", rack["media_per_partita"])
    if rack["distanze_esatte"]:
        logger.info(
            "  a rack esatti ........... %s",
            ", ".join(f"{d} rack: {n}" for d, n in rack["distanze_esatte"].items()),
        )
    if rack["distanze_a_corsa"]:
        logger.info(
            "  a corsa ................. %s",
            ", ".join(f"al {d}: {n}" for d, n in rack["distanze_a_corsa"].items()),
        )
    if rack["partite_pareggiabili"]:
        logger.info(
            "  possono finire pari ..... %d  (rack esatti in numero pari)",
            rack["partite_pareggiabili"],
        )

    logger.info("")
    logger.info("Giocatori")
    logger.info("  con almeno una partita .. %d", giocatori["totali"])
    for soglia in SOGLIE_RACK:
        logger.info(
            "  con >= %-4s rack ......... %d",
            soglia,
            giocatori["sopra_soglia"][str(soglia)],
        )
    percentili = giocatori["percentili_rack"]
    logger.info(
        "  rack per giocatore ...... p25=%d  p50=%d  p75=%d  p90=%d",
        percentili["p25"],
        percentili["p50"],
        percentili["p75"],
        percentili["p90"],
    )

    logger.info("")
    logger.info("Grafo dei confronti (chi ha giocato con chi)")
    logger.info("  giocatori ............... %d", grafo["nodi"])
    logger.info("  coppie distinte ......... %d", grafo["coppie_distinte"])
    logger.info("  componenti connesse ..... %d", grafo["componenti"])
    if grafo["componenti"] > 1:
        logger.info("  dimensioni (prime 10) ... %s", grafo["dimensione_componenti"])
    logger.info(
        "  componente maggiore ..... %d giocatori, %.1f%% dei rack",
        grafo["giocatori_nella_maggiore"],
        grafo["quota_rack_nella_maggiore"] * 100,
    )

    logger.info("")
    logger.info("Copertura temporale")
    logger.info("  mesi con partite ........ %d", tempo["mesi_coperti"])
    logger.info(
        "  finestre da >= %d partite %d  %s",
        tempo["soglia_finestra"],
        len(tempo["finestre_utili"]),
        tempo["finestre_utili"] or "",
    )

    _verdetto(dati)


def _verdetto(dati: Dict[str, Any]) -> None:
    """Cosa dicono i numeri sul passo successivo dell'ADR.

    Non decide niente: elenca le condizioni del passo 0 e dice quali sono
    soddisfatte. La decisione resta di chi legge — ma senza questo riassunto
    i numeri di sopra si prestano a essere letti come fa comodo.
    """
    rilievi: List[str] = []

    stabili = dati["giocatori"]["sopra_soglia"]["200"]
    if stabili < 10:
        rilievi.append(
            f"solo {stabili} giocatori hanno >= 200 rack: con così pochi rating "
            "consolidati i due modelli non hanno modo di distinguersi"
        )

    if dati["grafo"]["componenti"] > 1:
        rilievi.append(
            f"il grafo è spezzato in {dati['grafo']['componenti']} componenti "
            f"({dati['grafo']['quota_rack_nella_maggiore'] * 100:.0f}% dei rack "
            "nella maggiore): fra componenti diverse i rating non sono "
            "confrontabili, e il rifit globale ne soffre più dell'iterativo"
        )

    finestre = len(dati["tempo"]["finestre_utili"])
    if finestre < 3:
        rilievi.append(
            f"solo {finestre} finestre mensili abbastanza popolate: la "
            "validazione a origine mobile misurerebbe la fortuna di un mese"
        )

    esatte = sum(dati["rack"]["distanze_esatte"].values())
    corse = sum(dati["rack"]["distanze_a_corsa"].values())
    if esatte and corse:
        rilievi.append(
            f"convivono due formati ({esatte} a rack esatti, {corse} a corsa): "
            "la probabilità di partita si ricava dalla binomiale nel primo caso "
            "e dalla binomiale negativa nel secondo, e vanno tenuti separati"
        )
    if dati["rack"]["partite_pareggiabili"]:
        rilievi.append(
            f"{dati['rack']['partite_pareggiabili']} partite possono finire "
            "pari: l'Elo binario di oggi non sa prevedere un pareggio, un "
            "modello a rack lo deriva — il confronto va fatto sui tre esiti"
        )

    if dati["partite"]["multi_set"]:
        rilievi.append(
            f"{dati['partite']['multi_set']} partite multi-set hanno il "
            "punteggio in set: vanno convertite o escluse prima di contare i rack"
        )

    logger.info("")
    if rilievi:
        logger.info("Rilievi sul passo 0 (ADR-052):")
        for rilievo in rilievi:
            logger.info("  • %s", rilievo)
    else:
        logger.info("Nessun rilievo: i dati reggono il backtest previsto da ADR-052.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        metavar="FILE",
        help="scrive il censimento anche come JSON (per confrontarlo nel tempo)",
    )
    args = parser.parse_args()

    app = bootstrap_and_create_app()
    with app.app_context():
        torneo = _partite_torneo()
        casual = _partite_casual()

        risultati = [
            _censimento(torneo, "ELO competitivo — solo gare"),
            _censimento(torneo + casual, "ELO globale — gare + sfide individuali"),
        ]

    for dati in risultati:
        _stampa(dati)

    logger.info("")
    logger.info("Sola lettura: nessuna riga è stata scritta.")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(risultati, handle, indent=2, ensure_ascii=False)
        logger.info("Censimento scritto anche in %s", args.json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
