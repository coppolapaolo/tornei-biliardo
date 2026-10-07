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
   - **Scontri diretti**: fra due decide chi ha vinto lo scontro. *(Fra tre o
     più la regola è cambiata il 2026-10-07: vedi «Emendamento: lo scontro
     diretto ordina solo quello che i risultati dicono». Prima era una
     mini-classifica sulle partite fra loro, che non decideva se non si erano
     incontrati tutti.)*
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

## Emendamento 2026-10-07: le catene si configurano

La seconda parte della decisione: il direttore sceglie le catene, e lo
spareggio smette di essere un interruttore.

1. **Dove stanno.** Sulla gara `catena_turno` e `catena_gara`; sul campionato
   `default_catena_turno` e `default_catena_gara`, **proposte** alle gare come
   ogni altro valore (ADR-075, `campionato/proposte.py`), e `catena_generale`,
   che è solo sua. Colonne di testo con una lista JSON di voci
   (`ordinamento.testo_della_catena`): JSON e non virgole perché la catena
   **vuota** è una scelta («si resta pari») e deve restare diversa da NULL,
   che vuol dire «come il campionato» (fuori da un campionato: il default
   dell'app). Si leggono **solo** da `catene.py`, che ripiega
   gara → campionato → default e normalizza.
2. **Nascita.** Una gara nasce con le catene scritte: quelle proposte dal
   campionato o, fuori, quelle di default (`GaraService._catene_alla_nascita`).
   Una gara senza catena rileggerebbe il campionato in diretta, e una proposta
   nuova arriverebbe anche a gara avviata — la lezione del limite di tempo.
3. **Lo spareggio è un criterio.** `tiebreaker_enabled` e
   `tiebreaker_until_position` si fondono nella catena di gara come `ssr:N`.
   La migration `20261007_catene_degli_spareggi` scrive su ogni gara la catena
   che riproduce le due colonne; le colonne (con `tiebreaker_mode`, mai letto)
   restano nel database ma escono dal modello. Chi chiede «fin dove si
   spareggia?» usa `SpareggioService.ssr_fino_al(gara)` (anche nei template,
   come `ssr_fino_al(gara)`): il podio resta di tre se lo spareggio non c'è.
4. **Regole di modifica** (`campi_modificabili`): la catena di gara sta nella
   fascia dello **spareggio** — si cambia finché lo spareggio non è
   cominciato, e vale subito. La catena di turno è una **regola di gioco** e a
   gara avviata vale **dal turno successivo**: la classifica del turno N si fa
   con la catena in vigore al turno N, letta dalla storia
   (`catene._testo_al_turno`: il primo cambio che vale da dopo N ha in «prima»
   la catena di N). Così il ricalcolo di un turno già nato, dopo una
   correzione, non cambia regola. Una conseguenza da sapere: un cambio fatto
   durante il turno 3 tocca la classifica del turno 4, quindi gli abbinamenti
   del turno 5. Sul tabellone nessuna delle due si cambia a gara avviata.
5. **Cambio di sistema.** Una catena che era quella di default del sistema
   vecchio diventa quella del nuovo (`catene.adegua_al_sistema`), sul
   campionato e sulle sue gare, e resta nella storia; una catena scelta resta
   sua, senza il criterio diventato principale. L'editor fa lo stesso nel
   modulo.
6. **Interfaccia.** Un editor (`components/_catena_spareggi.html`,
   `static/js/catena_spareggi.js`): il principale fisso in cima, le voci che
   si spostano e si tolgono, i criteri liberi da aggiungere, e sotto la frase
   del regolamento, composta con le stesse parole di `descrivi_catena`
   (`editor_catena.config_editor`). Nei moduli della gara singola, del modale
   «nuova gara», della modifica prima e dopo l'avvio, del wizard e della
   modifica del campionato. Il server riapplica le regole
   (`catene.testo_dal_modulo`): l'editor evita solo di offrire ciò che non è
   ammesso. La frase compare nel regolamento (`storia/regolamento.py`,
   `frase_della_catena`) e nella pagina pubblica della gara e del campionato.

## Emendamento 2026-10-07: lo scontro diretto ordina solo quello che i risultati dicono

Deciso dall'utente. La mini-classifica fra tre o più pari aveva due difetti:
non decideva appena mancava un incontro (con una sola partita giocata fra i
pari, l'informazione si buttava), e quando decideva poteva contraddire un
risultato diretto a favore di un conteggio. La regola nuova
(`_Motore._per_scontri`):

1. fra i pari sul criterio corrente, ogni coppia che si è incontrata dà un
   **vincolo** «X davanti a Y» se X ha vinto più scontri di Y; più partite
   fra gli stessi due — in gare diverse del campionato — si contano tutte; a
   parità, o con un pareggio (la chiusura a tempo lo ammette), nessun vincolo.
   Trio e X non sono scontri; nel campionato non contano le gare con peso 0;
2. i **cicli** (A>B>C>A) si condensano nelle componenti fortemente connesse
   (`networkx.condensation`): chi si è battuto a vicenda in giro resta pari
   sullo scontro, e fra le componenti il grafo è aciclico;
3. l'ordine è un **ordinamento topologico** del grafo condensato in cui, a
   ogni passo, fra chi non ha più nessuno davanti decide il **resto della
   catena**. Nessun risultato diretto viene contraddetto, e fra chi non si è
   incontrato decide il criterio successivo. Chi resta indistinguibile resta
   pari (gara) o va al sorteggio (turno, campionato);
4. con due soli pari coincide con la regola di sempre
   (CLASSIFICATION_SYSTEM.md §5.3).

Lo scontro diretto non dipende più dal sistema: si contano le vittorie anche
a triangoli (prima la mini-classifica a RACK sommava i triangoli fra loro).
Nessuna gara esistente lo usa: le catene di default non lo contengono.

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
- La catena diventa configurabile: vedi l'emendamento qui sopra.
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
- Editor: `models/classification/editor_catena.py`,
  `templates/components/_catena_spareggi.html`, `static/js/catena_spareggi.js`.
- Migration: `migrations/20261007_catene_degli_spareggi.py`.
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
  `test_catene_configurabili.py`, `test_catene_spareggi_route.py`
  (integrazione), `test_specifiche_conformita.py::TestLeCateneSiConfigurano`,
  `test_specifiche_conformita.py::TestCateneDegliSpareggi`
