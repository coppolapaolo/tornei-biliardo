# [078] La catena degli spareggi: un motore solo, tre classifiche, tre catene

**Data**: 2026-10-07
**Stato**: Accepted
**Decisori**: Paolo Coppola (dominio), Claude (implementazione)

## Contesto

Fino a oggi i criteri di classifica erano **scritti nel codice**, uno per ogni
posto che ordinava:

- la classifica di **turno**, nelle chiavi `get_sort_key` di
  `round_strategies.py` (WINS: vittorie → differenza → posizione precedente →
  id; RACK: rack → SSR → differenza → posizione precedente → id);
- la classifica di **gara**, nella chiave di merito di
  `SpareggioService.apply_final_positions` (WINS: vittorie → differenza → SSR;
  RACK: rack → SSR), più una seconda copia nelle strategie `*_gara`;
- chi è **a pari merito** per lo spareggio, in tre posti con la loro chiave:
  `SpareggioService._group_by_classification`, `TiebreakerService.detect_ties`
  (mai chiamato fuori dai test) e la chiave di `apply_final_positions`;
- la classifica **generale**, in `TournamentStatisticsService._sort_and_rank_players`,
  dove a pari merito restava l'ordine in cui i giocatori comparivano nei dati.

Il direttore non poteva scegliere come si risolvono i pari merito, e la gara
settimanale di Biliardo 74 (gironi, classifica a punti, «a pari punti conta lo
scontro diretto») non era configurabile. Lo scontro diretto, per giunta, non è
una chiave di ordinamento: vale **fra i soli pari**.

## Decisione

1. **Un motore solo**, puro: `models/classification/ordinamento.py`. Riceve i
   giocatori già aggregati (`Concorrente`), il **criterio principale** del
   sistema (vittorie, rack vinti) e una **catena** di criteri, e restituisce le
   **fasce** della classifica. Lavora **a gruppi**: ordina sul principale, poi
   applica il primo criterio a ogni gruppo di pari, poi il secondo ai gruppi
   ancora pari, e così via.

2. **I criteri**: scontri diretti, differenza rack, rack vinti, vittorie,
   spareggio SSR (con un posto «fino al N°», o senza limite nella classifica
   generale, dove è la somma), posizione precedente, sorteggio.
   - **Scontri diretti**: fra due decide chi ha vinto lo scontro; fra tre o più
     una mini-classifica sulle partite fra loro (vittorie a WINS, rack a RACK).
     Se non si sono incontrati **tutti**, non decide. Se la mini-classifica
     lascia un sottogruppo più piccolo ancora pari, lo scontro diretto si
     ripete fra quei soli giocatori prima di passare al criterio successivo.
   - **Spareggio SSR**: oltre il suo posto non decide; chi non ha tirato vale
     -1, cioè viene dopo chi ha fatto zero.
   - **Sorteggio**: deterministico, un hash del seme e del giocatore. Il seme
     della gara è `draw_seed` (risorteggiare all'avvio cambia anche questo);
     quello del campionato è il suo id. Mai l'id del giocatore, che è l'ordine
     di registrazione.

3. **Tre classifiche, tre catene**, con lo stesso criterio principale:

   | Classifica | WINS | RACK | Chi resta pari |
   |---|---|---|---|
   | Turno | differenza → posizione al turno precedente → sorteggio | posizione al turno precedente → sorteggio | nessuno (serve agli abbinamenti) |
   | Gara | differenza → SSR fino al 3° | SSR fino al 3° | condivide la posizione |
   | Campionato | differenza → SSR (somma) → posizione dopo la gara precedente → sorteggio | SSR (somma) → posizione dopo la gara precedente → sorteggio | nessuno (ne discendono gli inviti ai playoff) |

   Lo SSR **non entra nel turno**: si gioca a gara finita, e la classifica
   dell'ultimo turno la riscrive comunque quella di gara.

4. **Una risposta sola a «chi è pari?»**: `SpareggioService._fasce` applica la
   catena di gara; con `fino_allo_ssr` si ferma prima dello spareggio, e dà i
   gruppi che lo spareggio deve sciogliere. `TiebreakerService` è tolto.

5. **POSITION non passa dal motore** (ADR-040): le sue bande sono l'esito.

## Cosa cambia per chi gioca

Deciso dall'utente il 2026-10-07, scritto in SPECIFICHE.md con nota datata:

- **turno RACK**: escono SSR e differenza rack (la specifica dice «rack, poi
  spareggio», e lo spareggio non c'è ancora);
- **turno**: l'ultima risorsa è il sorteggio, non l'id;
- **campionato**: a pari merito decide la posizione dopo la gara precedente,
  poi il sorteggio, invece dell'ordine di comparsa.

Restano **identiche** la classifica di turno WINS e le due di gara: presidio
in `tests/new/unit/test_ordinamento_equivalenza.py`, che le confronta con le
vecchie chiavi su scenari casuali.

## Alternative Considerate

### Alternativa 1: una chiave di ordinamento configurabile

**Descrizione**: costruire una tupla dalla catena e fare un `sorted()`.

- **Pro**: semplice, lo stesso schema di `get_sort_key`.
- **Contro**: lo scontro diretto non è una proprietà del singolo giocatore e
  non si esprime come chiave; lo SSR «fino al N° posto» dipende dalla
  posizione del gruppo, che la chiave non conosce.

### Alternativa 2: una catena sola per i tre livelli

**Descrizione**: il direttore sceglie una catena, che vale ovunque.

- **Pro**: un solo editor.
- **Contro**: i tre livelli hanno bisogni diversi. Il turno deve dare un
  ordine completo (abbinamenti) e non ha lo SSR; la gara deve lasciare i pari
  merito perché è lì che lo spareggio scatta; il campionato deve dare un
  ordine completo per gli inviti. Scartata dall'utente.

## Conseguenze

### Positive

- Un criterio nuovo si scrive in un posto solo e vale per tutte le classifiche.
- La catena diventa configurabile (PR successive): basta salvarla e passarla.
- Il criterio «posizione dopo la gara precedente» rende la classifica generale
  calcolata gara per gara: il trend mostrato in pagina è proprio quella
  posizione.

### Negative

- Il sorteggio non è leggibile a colpo d'occhio come l'ordine di iscrizione:
  va spiegato nella guida.
- La classifica generale si calcola dopo ogni gara (le query restano una
  volta sola: `_aggregate_player_totals(progressivi=…)`).

### Rischi

- Uno SSR registrato per un gruppo che, dopo una correzione, parte oltre il
  posto dello spareggio non decide più: prima lo faceva. È il comportamento
  che la regola «fino al N° posto» dice, ma è una differenza.

## Note Implementative

- Motore: `models/classification/ordinamento.py` (puro, nessun DB).
- Catene e scontri dalla gara/campionato: `models/classification/catene.py`.
- Turno e gara: `strategies/base.py::_ordina_con_la_catena`, chiamato da
  `round_strategies.py` e `gara_strategies.py`.
- Classifica di gara mostrata: `SpareggioService.apply_final_positions` →
  `_fasce`.
- Classifica generale: `TournamentStatisticsService._sort_and_rank_players`.

## Riferimenti

- ADR-040 (pari merito per banda nel tabellone), ADR-047 (il sistema decide
  l'ordinamento), ADR-073 (la classifica generale si calcola in un posto solo)
- SPECIFICHE.md, «Classifica», «Come si risolvono i pari merito»
- Test: `test_ordinamento_motore.py`, `test_ordinamento_equivalenza.py`,
  `test_specifiche_conformita.py::TestCateneDegliSpareggi`
