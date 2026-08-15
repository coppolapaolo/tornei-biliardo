# ADR-040 Classifica per posizione: pari merito voluti, spareggio spento

**Data**: 2026-08-15
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Il sistema di classifica `POSITION` esisteva come valore ammesso ma era un
**segnaposto**: `gara_classification.py` lo mappava sulle strategie
`amalfi_round` / `amalfi_gara`, cioè si comportava esattamente come `WINS`. Su
un tabellone questo non ordina niente di sensato: in eliminazione diretta
quasi tutti hanno la stessa manciata di vittorie, e chi ha perso in finale
può averne meno di chi ha perso in semifinale dopo un bye.

In un tabellone la posizione la dice **il turno in cui sei uscito**, e nulla
altro. Chi esce allo stesso turno ha fatto lo stesso percorso.

Il vincolo che rende la cosa non ovvia è il macchinario di spareggio già
presente (`SpareggioService`, `TiebreakerResolver`): il progetto tratta i pari
merito nelle prime posizioni come qualcosa **da risolvere** con lo Spot Shot
Rally, e le strategie di classifica GARA sono scritte apposta per farli
emergere — `gara_strategies.py` esclude deliberatamente `player_id` dalla
chiave di ordinamento perché `_build_entries_with_ties` possa marcare
`has_ties=True`.

## Decisione

### La posizione viene dalle bande di eliminazione

1° il vincitore, 2° il finalista sconfitto, poi **per bande a pari merito**:
i due semifinalisti sono entrambi 3°, i quattro quartifinalisti tutti 5°, gli
otto ottavofinalisti tutti 9°. La banda vale **la sua posizione più alta**.

Due eccezioni:

- con la finalina 3°/4° attiva, il nodo `3P` scioglie la banda dei
  semifinalisti: 3° al vincitore, 4° al perdente;
- nel doppio KO il terzo posto lo decide già il tabellone (è chi perde la
  finale del losers bracket), quindi quella banda non si presenta e la
  finalina non esiste.

Il calcolo delle bande vive in un modulo suo
(`models/classification/bracket_standings.py`) e non dentro le strategie,
perché lo usano **due percorsi diversi**: la classifica di gara e
`SpareggioService.apply_final_positions`, che è la strada da cui passa la
classifica finale in produzione. Una seconda implementazione sarebbe divergita
in silenzio.

### Lo spareggio resta spento su POSITION

Le bande producono pareggi **per costruzione**: quattro quartifinalisti sono
tutti quinti, e non è un problema da risolvere — è il risultato. Quindi la
strategia `position_gara` marca `has_ties=False` e
`requires_tiebreaker=False` **anche in presenza di posizioni ripetute**.

È una divergenza deliberata dalla convenzione della classe accanto, ed è
commentata nel codice proprio per questo: chi legge `gara_strategies.py`
subito dopo trova la regola opposta e, senza la nota, la scambierebbe per un
bug.

### La tabella punti è configurabile sul campionato

I valori di default sono quelli della specifica (25 / 18 / 15 / 12, poi 8 dal
5° all'8°, 4 dal 9° al 16°), in `models/classification/position_points.py`.
Tutti i pari merito di una banda prendono lo stesso punteggio. Un campionato
che non la configura usa il default senza chiedere nulla.

Restano nel codice **due tabelle punti divergenti** —
`statistics_service.py` (10/7/5/4…) e `campionato_strategies.py`
(1000/800/500…) — che **non** vengono toccate: unificarle cambierebbe in
silenzio il punteggio di campionati già giocati. È un debito dichiarato, non
una svista.

## Alternative Considerate

### Alternativa 1: ordinare i pari merito con criteri secondari (rack, Elo)
- Pro: nessun pareggio, classifica totale.
- Contro: separerebbe giocatori che hanno fatto lo stesso percorso in base a
  qualcosa che il formato non misura. In un tabellone i rack vinti dipendono
  da chi hai incontrato, non da quanto sei andato avanti.

### Alternativa 2: lasciare attivo lo spareggio anche su POSITION
- Pro: nessuna eccezione da spiegare, una regola sola per tutti i sistemi.
- Contro: proporrebbe uno Spot Shot Rally per separare quattro
  quartifinalisti, cioè per risolvere un pareggio che è il risultato voluto.
  Il director si troverebbe una fase in più da chiudere a ogni gara.

### Alternativa 3: bande calcolate dentro ciascuna strategia
- Pro: nessun modulo nuovo.
- Contro: le due strade che le usano (classifica di gara e
  `apply_final_positions`) sono in file diversi; due implementazioni della
  stessa regola divergono, e la divergenza si vedrebbe solo a gara conclusa.

### Alternativa 4: unificare subito le tre tabelle punti
- Pro: una fonte sola per "quanto vale un piazzamento".
- Contro: cambierebbe retroattivamente il punteggio dei campionati esistenti.
  Va fatto, ma come lavoro proprio e con una migration che dica cosa cambia.

## Conseguenze

### Positive
- La classifica di una gara a tabellone dice quel che è successo: quanto sei
  andato avanti.
- Nessuno spareggio proposto dove non serve; il caso simmetrico su `WINS`
  continua a proporlo (test di non-regressione).
- I punti di campionato per posizione sono configurabili senza toccare le
  altre due tabelle già in uso.

### Negative
- Un lettore che confronta `position_gara` con `wins_gara` trova due
  convenzioni opposte sui pari merito. Mitigato dal commento nel codice e da
  questo ADR.
- Restano tre tabelle punti nel progetto.

### Rischi
- Se in futuro qualcuno rendesse il tiebreaker obbligatorio "per tutti i
  sistemi", romperebbe questa decisione senza accorgersene. Il test
  `position_non_propone_spareggi` è la rete.

## Note Implementative

- Bande: `models/classification/bracket_standings.py`.
- Strategie: `PositionRoundClassificationStrategy` /
  `PositionGaraClassificationStrategy`, registrate in `registry.py`.
- Punti: `models/classification/position_points.py`.
- Aggancio di produzione: `SpareggioService.apply_final_positions`.
