"""Il motore di rating a rack: `ΔR = k · (vinti − attesi)`.

Decisione: `docs/adr/ADR-052-rating-model-decided-by-measurement.md`.

**Cosa cambia rispetto al motore storico.** Quello legge solo chi ha vinto:
un 7–0 e un 7–6 muovono i rating allo stesso modo, benché il numero di rack sia
già in tabella. Qui l'unità di misura è il **rack**, quindi il punteggio esatto
entra nel calcolo. Sui dati simulati con la struttura del circolo il guadagno è
di 0,02–0,03 di log-loss per partita — l'unico margine ampio fra tutte le
varianti provate (ADR-052, sezione *Esito*).

**La scala è quella di FargoRate, non quella degli scacchi.** Logistica in base
2 con divisore 100: cento punti di differenza significano probabilità **doppia**
di vincere *il singolo rack*. Non è convertibile nella scala 10/400 del pool
storico, perché le due misurano cose diverse — 2:1 per rack corrisponde a circa
l'80% per partita in una corsa a 7. I due pool convivono e non si confrontano.

**Perché è un modulo puro.** Niente DB, niente sessione, niente app context:
le regole si possono verificare con l'aritmetica, e la simulazione che ha
deciso l'ADR (`scripts/rating_model_simulation.py`) usa le stesse formule.
Un motore intrecciato alla persistenza si sarebbe potuto solo osservare.
"""

from __future__ import annotations

#: Il rating di un giocatore mai visto. Vale come qualunque altro valore: la
#: scala non ha uno zero, solo differenze.
PARTENZA: float = 500.0

#: Punti che raddoppiano la probabilità di vincere un rack.
SCALA: float = 100.0

#: Il fattore di sensibilità parte alto e cala coi rack accumulati: un
#: giocatore nuovo deve raggiungere in fretta il proprio livello, uno con
#: storico non deve ballare per una serata storta.
#:
#: I valori vengono dalla ricerca fatta in ADR-052 su circoli simulati, e sono
#: **provvisori per dichiarazione**: la taratura definitiva va rifatta sui dati
#: veri quando il pool avrà accumulato abbastanza rack, con validazione
#: annidata (emendamento al protocollo, ADR-052). Non sono numeri di
#: riferimento presi da qualche parte: a parametri non tarati questo motore
#: perde contro quello storico, ed è successo davvero durante l'analisi.
K_MAX: float = 10.0
K_MIN: float = 1.6
#: Rack necessari a dimezzare lo scarto fra `K_MAX` e `K_MIN`.
N_MEZZA_VITA: float = 120.0


def probabilita_rack(rating_a: float, rating_b: float) -> float:
    """Probabilità che A vinca **un singolo rack** contro B."""
    return 1.0 / (1.0 + 2.0 ** ((rating_b - rating_a) / SCALA))


def fattore_k(rack_giocati_a: int, rack_giocati_b: int) -> float:
    """La sensibilità dell'aggiornamento, **comune ai due giocatori**.

    Comune, e non uno per ciascuno, perché altrimenti i punti persi da uno non
    sarebbero quelli guadagnati dall'altro: il totale del pool si muoverebbe a
    ogni partita, e il rating perderebbe l'unica proprietà che lo rende
    confrontabile nel tempo. È la variante che il materiale di partenza
    consigliava, e che su mille incontri fra un novizio e un veterano faceva
    comparire decine di punti dal nulla.

    Si usa quindi la media dei due: il novizio si muove comunque più in fretta
    di quanto farebbe con un `k` fisso, senza che il sistema crei punteggio.
    """
    singolo = [
        K_MIN + (K_MAX - K_MIN) / (1.0 + giocati / N_MEZZA_VITA)
        for giocati in (rack_giocati_a, rack_giocati_b)
    ]
    return sum(singolo) / 2.0


def variazione(
    rating_a: float,
    rating_b: float,
    rack_a: int,
    rack_b: int,
    giocati_a: int = 0,
    giocati_b: int = 0,
) -> float:
    """Di quanto si muove il rating di A. B si muove dell'opposto.

    `rack_a` e `rack_b` sono i rack vinti nella partita; `giocati_*` quelli
    accumulati prima, che regolano la sensibilità.

    La formula è il gradiente esatto della log-verosimiglianza di
    Bradley-Terry, non un'approssimazione — ed è lecito applicarla anche alle
    corse a N, dove la partita si ferma appena uno arriva al traguardo: la
    regola d'arresto dipende solo dagli esiti già osservati, quindi il nucleo
    della verosimiglianza resta `p^vinti · q^persi`.
    """
    totale = rack_a + rack_b
    if totale <= 0:
        # Nessun rack giocato: non c'è niente da cui imparare. Il caso arriva
        # dai walkover, che `RatingEligibility` esclude già a monte; qui è la
        # rete, non la regola.
        return 0.0

    attesi = totale * probabilita_rack(rating_a, rating_b)
    return fattore_k(giocati_a, giocati_b) * (rack_a - attesi)
