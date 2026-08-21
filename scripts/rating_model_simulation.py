"""Confronta i motori di rating candidati su circoli simulati come il nostro.

**Perché esiste.** ADR-052 doveva scegliere fra due motori di rating con un
backtest sui dati veri. Il censimento (`rating_census.py`) ha detto che i dati
non bastano: con 1375 rack la prova avrebbe separato i due modelli in un caso
su tre, e nei restanti due avrebbe risposto «indistinguibili» — cioè avrebbe
fatto scattare il pareggio invece di decidere.

Questo script decide diversamente: invece di misurare una volta su dati
insufficienti, misura molte volte su circoli **simulati con la struttura del
nostro**, dove la risposta giusta è nota per costruzione. Non sostituisce il
backtest, risponde a una domanda diversa e più modesta: *in un circolo fatto
così, quale motore predice meglio?*

**La struttura è quella misurata in produzione il 2026-08-21**: 51 giocatori,
286 partite ammissibili, 1375 rack, 9 mesi, 5 finestre mensili utilizzabili, e
le distanze osservate — quasi tutte a **rack esatti**, non a corsa, quindi con
i pareggi possibili.

**Cosa NON dice.** Le partite sono generate da un modello Bradley-Terry: non
contengono forma, stanchezza, avversari-tabù, differenze fra discipline. Se il
biliardo vero ha una di queste strutture in modo marcato, le conclusioni
cambiano. E i parametri dei modelli qui sono fissati a mano: in un backtest
vero la taratura va **annidata** dentro la validazione, altrimenti si premia il
modello con più parametri.

Uso::

    python scripts/rating_model_simulation.py
    python scripts/rating_model_simulation.py --reps 100 --volumi 1 3 10

Non usa `prod_env` e non tocca il database: è analisi, si lancia in sviluppo.
"""

from __future__ import annotations

import argparse
import logging
import math
import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# --- La struttura misurata in produzione (censimento 2026-08-21) -------------

N_GIOCATORI = 51
N_PARTITE = 286
N_MESI = 9
N_FINESTRE = 5
#: Distanze osservate, a rack esatti. La somma fa 1366 rack su 286 partite,
#: che è il riscontro che ha smascherato l'ipotesi «sono corse»: quelle ne
#: produrrebbero circa 1900, e in DB ce ne sono 1375.
DISTANZE: Tuple[int, ...] = tuple([3] * 90 + [4] * 6 + [5] * 101 + [6] * 56 + [7] * 33)

#: Scala FargoRate: 100 punti = probabilità doppia di vincere il singolo rack.
SCALA = math.log(2) / 100.0
PARTENZA = 500.0
#: Il rating di partenza del motore attuale, che vive su un'altra scala.
PARTENZA_ELO = 1200.0

Partita = Tuple[int, int, int, int, int]  # (a, b, rack_a, rack_b, mese)
Motore = Callable[[Sequence[Partita]], List[float]]


def p_rack(ra: float, rb: float) -> float:
    """Probabilità che chi vale `ra` vinca un singolo rack contro `rb`."""
    return 1.0 / (1.0 + 2.0 ** ((rb - ra) / 100.0))


# --- Generazione ------------------------------------------------------------


def simula_stagione(rng: random.Random, n_partite: int, deriva: float) -> List[Partita]:
    """Una stagione di partite a **rack esatti**, con abilità che evolvono.

    `deriva` è di quanto migliora un giocatore ogni mese, in punti Fargo. Zero
    significa abilità costanti — l'ipotesi più favorevole al rifit globale, che
    pesa il passato remoto quanto ieri.
    """
    abilita = [rng.gauss(PARTENZA, 70.0) for _ in range(N_GIOCATORI)]
    traiettorie = [list(abilita)]
    for _ in range(N_MESI):
        traiettorie.append(
            [x + rng.gauss(deriva, max(deriva, 1e-9)) for x in traiettorie[-1]]
        )

    # Attività molto disuguale: pochi giocano moltissimo, come in produzione
    # (mediana 33 rack, nono decile 185).
    pesi = [rng.lognormvariate(0, 0.9) for _ in range(N_GIOCATORI)]

    partite: List[Partita] = []
    for indice in range(n_partite):
        a = _pesca(rng, pesi)
        b = _pesca(rng, pesi)
        while b == a:
            b = _pesca(rng, pesi)
        mese = indice * N_MESI // n_partite
        n = DISTANZE[rng.randrange(len(DISTANZE))]
        p = p_rack(traiettorie[mese][a], traiettorie[mese][b])
        vinti = sum(1 for _ in range(n) if rng.random() < p)
        partite.append((a, b, vinti, n - vinti, mese))
    return partite


def _pesca(rng: random.Random, pesi: Sequence[float]) -> int:
    soglia = rng.random() * sum(pesi)
    corrente = 0.0
    for indice, peso in enumerate(pesi):
        corrente += peso
        if corrente >= soglia:
            return indice
    return len(pesi) - 1


# --- I motori in gara -------------------------------------------------------


def elo_attuale(partite: Sequence[Partita], k: float = 32.0) -> List[float]:
    """Il motore di oggi: base 10/400, K costante, esito binario.

    Il pareggio vale mezzo punto, ma il modello non sa **prevederlo**: è la
    parte di informazione che un modello a rack recupera gratis.
    """
    r = [PARTENZA_ELO] * N_GIOCATORI
    for a, b, va, vb, _ in partite:
        atteso = 1.0 / (1.0 + 10 ** ((r[b] - r[a]) / 400.0))
        esito = 1.0 if va > vb else (0.0 if vb > va else 0.5)
        delta = k * (esito - atteso)
        r[a] += delta
        r[b] -= delta
    return r


def iterativo_a_rack(
    partite: Sequence[Partita],
    k_max: float = 10.0,
    k_min: float = 1.6,
    n0: float = 120.0,
) -> List[float]:
    """Elo a rack: `ΔR = k·(vinti − attesi)`, con `k` che cala coi rack giocati.

    Il `k` è **comune ai due** giocatori (la media dei loro): darne uno diverso
    a testa, come suggeriva il materiale di partenza, romperebbe la somma zero
    e farebbe comparire punti dal nulla.
    """
    r = [PARTENZA] * N_GIOCATORI
    giocati = [0] * N_GIOCATORI
    for a, b, va, vb, _ in partite:
        n = va + vb
        atteso = p_rack(r[a], r[b])
        k = sum(k_min + (k_max - k_min) / (1 + giocati[x] / n0) for x in (a, b)) / 2
        delta = k * (va - n * atteso)
        r[a] += delta
        r[b] -= delta
        giocati[a] += n
        giocati[b] += n
    return r


def globale(
    partite: Sequence[Partita],
    alpha: float = 3.0,
    emivita: Optional[float] = None,
    iterazioni: int = 150,
) -> List[float]:
    """Bradley-Terry per massima verosimiglianza, con l'algoritmo MM.

    `alpha` sono le partite fittizie contro un'ancora al valore di partenza:
    rendono il problema risolvibile anche quando il grafo dei confronti è
    spezzato — e in produzione lo è, in due componenti da 43 e 8 giocatori.

    `emivita` in mesi accende la **dimenticanza**: senza, una partita di due
    anni fa pesa quanto quella di ieri, che è l'ipotesi sbagliata se i
    giocatori migliorano.
    """
    vinti = [0.0] * N_GIOCATORI
    fra: Dict[Tuple[int, int], float] = {}
    ultimo = max((p[4] for p in partite), default=0)
    for a, b, va, vb, mese in partite:
        peso = 1.0 if emivita is None else 0.5 ** ((ultimo - mese) / emivita)
        vinti[a] += va * peso
        vinti[b] += vb * peso
        chiave = (a, b) if a < b else (b, a)
        fra[chiave] = fra.get(chiave, 0.0) + (va + vb) * peso

    forza = [1.0] * N_GIOCATORI
    for _ in range(iterazioni):
        denom = [2 * alpha / (forza[i] + 1.0) for i in range(N_GIOCATORI)]
        for (a, b), n in fra.items():
            quota = n / (forza[a] + forza[b])
            denom[a] += quota
            denom[b] += quota
        forza = [
            max((vinti[i] + alpha) / max(denom[i], 1e-12), 1e-9)
            for i in range(N_GIOCATORI)
        ]
    return [PARTENZA + math.log(f) / SCALA for f in forza]


# --- Valutazione ------------------------------------------------------------


def esiti_attesi(p: float, n: int) -> Tuple[float, float, float]:
    """(vittoria, pareggio, sconfitta) su `n` rack esatti, dalla binomiale."""
    vittoria = pareggio = 0.0
    for k in range(n + 1):
        prob = math.comb(n, k) * p**k * (1 - p) ** (n - k)
        if k * 2 > n:
            vittoria += prob
        elif k * 2 == n:
            pareggio += prob
    return vittoria, pareggio, 1.0 - vittoria - pareggio


def quota_pareggi(partite: Sequence[Partita]) -> float:
    """Frequenza dei pari fra le partite a numero pari di rack."""
    pari = [(va, vb) for _a, _b, va, vb, _m in partite if (va + vb) % 2 == 0]
    if not pari:
        return 0.05
    return max(1e-3, sum(1 for va, vb in pari if va == vb) / len(pari))


def perdita(
    test: Sequence[Partita], r: Sequence[float], binario: bool, pareggi: float
) -> List[float]:
    """`-log P(esito osservato)` sui tre esiti: l'unica unità comune ai tre.

    Il modello binario non prevede i pareggi: gli si concede la quota osservata
    nell'addestramento, che è il meglio che possa fare. Senza quella
    concessione il confronto sarebbe truccato a suo sfavore.
    """
    out = []
    for a, b, va, vb, _ in test:
        n = va + vb
        if binario:
            p_vinta = 1.0 / (1.0 + 10 ** ((r[b] - r[a]) / 400.0))
            quota = pareggi if n % 2 == 0 else 0.0
            vittoria, pareggio, sconfitta = (
                (1 - quota) * p_vinta,
                quota,
                (1 - quota) * (1 - p_vinta),
            )
        else:
            vittoria, pareggio, sconfitta = esiti_attesi(p_rack(r[a], r[b]), n)
        scelto = vittoria if va > vb else (sconfitta if vb > va else pareggio)
        out.append(-math.log(min(max(scelto, 1e-9), 1.0)))
    return out


def valuta(
    seed: int, volume: float, deriva: float, motore: Motore, binario: bool, reps: int
) -> float:
    """Log-loss media fuori campione, su finestre mensili a origine mobile."""
    rng = random.Random(seed)
    misure = []
    for _ in range(reps):
        partite = simula_stagione(rng, int(N_PARTITE * volume), deriva)
        perdite: List[float] = []
        for taglio in range(N_MESI - N_FINESTRE, N_MESI):
            train = [p for p in partite if p[4] < taglio]
            test = [p for p in partite if p[4] == taglio]
            if len(train) < 20 or not test:
                continue
            perdite += perdita(test, motore(train), binario, quota_pareggi(train))
        if perdite:
            misure.append(sum(perdite) / len(perdite))
    return sum(misure) / len(misure) if misure else float("nan")


MOTORI: Tuple[Tuple[str, Motore, bool], ...] = (
    ("motore attuale, K=32 (oggi)", lambda p: elo_attuale(p, 32), True),
    ("motore attuale, K=64", lambda p: elo_attuale(p, 64), True),
    ("iterativo a rack", iterativo_a_rack, False),
    ("globale, tutta la storia", lambda p: globale(p, 3.0, None), False),
    ("globale, emivita 3 mesi", lambda p: globale(p, 3.0, 3.0), False),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=40, help="stagioni per cella")
    parser.add_argument(
        "--volumi", type=float, nargs="+", default=[1, 10], help="moltiplicatori"
    )
    parser.add_argument(
        "--drift",
        type=float,
        nargs="+",
        default=[0, 8, 20],
        help="punti Fargo guadagnati al mese da un giocatore",
    )
    parser.add_argument("--seed", type=int, default=20260821)
    args = parser.parse_args()

    logger.info("Partite a rack esatti, struttura del censimento 2026-08-21.")
    logger.info("Log-loss sui tre esiti fuori campione: più bassa predice meglio.")
    logger.info("«drift» = di quanto migliora un giocatore ogni mese.")

    for volume in args.volumi:
        logger.info("")
        logger.info("--- volume %gx (~%d rack) ---", volume, int(1375 * volume))
        intestazione = "".join(f"{'drift ' + str(int(d)):>12}" for d in args.drift)
        logger.info("%-30s%s", "motore", intestazione)
        for nome, motore, binario in MOTORI:
            riga = [
                valuta(args.seed, volume, d, motore, binario, args.reps)
                for d in args.drift
            ]
            logger.info("%-30s%s", nome, "".join(f"{v:>12.4f}" for v in riga))

    logger.info("")
    logger.info(
        "Numeri simulati, non misurati: leggili come un ordinamento fra motori "
        "in un circolo fatto così, non come una previsione sul nostro."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
