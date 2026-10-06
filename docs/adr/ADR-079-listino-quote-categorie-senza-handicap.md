# [079] Il listino delle quote: categorie anche senza handicap, solo informazione

**Data**: 2026-10-06
**Stato**: Accepted
**Decisori**: Paolo Coppola (committente), Claude

## Contesto

Biliardo 74 organizza ogni lunedì una serata con quote diverse per categoria:
«Serie A 30 € · Serie B e C 20 € · Amatori 15 €». Oggi una gara ha **una**
quota (`Gara.entry_fee`, proposta dal campionato con `default_entry_fee`).

Le categorie esistono già dall'ADR-049: un elenco **per competizione** (del
campionato, condiviso da tutte le sue gare, oppure della gara singola), che il
direttore assegna agli iscritti. Ma fino a oggi esistevano **solo con
l'handicap**, perché servivano a una cosa sola: decidere quali partite muovono
l'ELO. Senza handicap la schermata delle categorie non compariva.

Vincoli emersi con il committente:

1. il listino è **solo informazione**: si mostra dove oggi si mostra la quota.
   Niente incasso, niente «ha pagato»;
2. la categoria la assegna **il direttore**, quindi il giocatore non vede
   «la sua» quota: vede il listino;
3. il listino vale per **tutte le serate** di un campionato, ma si deve poter
   compilare anche su una **gara singola**;
4. una gara senza handicap che usa le categorie per il listino **non deve
   cambiare nulla** per l'ELO né per le regole fissate sulla partita.

## Decisione

### Una quota sulla categoria

`Categoria.entry_fee`, nullable. Il listino di una competizione è l'insieme
delle sue categorie **attive con una quota**. NULL vuol dire «non nel listino»:
la categoria può esistere comunque, assegnata a qualcuno.

Il listino appartiene a chi possiede le categorie (`CategoriaService.owner_of`):
il campionato per le sue gare, la gara singola altrimenti. Non è un valore
che il campionato *propone* alle gare (ADR-075): è il suo elenco, e le gare lo
leggono com'è.

### Le categorie esistono anche senza handicap

`Gara.usa_categorie` = handicap effettivo **oppure** listino non vuoto. È la
condizione con cui la pagina del direttore mostra il foglio delle categorie e
il combo accanto agli iscritti, e con cui l'iscrizione riporta la categoria
dalla gara precedente del campionato.

Senza handicap la categoria è informazione. L'ELO non la guarda:
`RatingEligibility.exclusion_reason` esce prima di leggere le categorie quando
la partita non ha l'handicap, e `has_handicap` si fissa sulla partita dalla
gara come sempre. Le categorie finiscono comunque in `categories_snapshot`
(si fissano su ogni partita, ADR-075): è un dato, non una regola, e
servirebbe se la gara passasse all'handicap dal turno dopo.

L'avviso «N iscritti senza categoria: le loro partite non conteranno per
l'Elo» resta legato all'handicap: senza, non è vero.

### Scrivere una voce crea la categoria

Il listino si compila nella configurazione: creazione e modifica della gara
singola (anche a gara avviata), wizard e modifica del campionato, e la quota
di una voce anche dal foglio delle categorie. `ListinoService.salva`:

- una voce con l'id di una categoria la rinomina e le cambia quota;
- una voce senza id ritrova per nome (a meno di maiuscole e spazi) la
  categoria già scritta accanto a un iscritto, o la crea;
- una categoria del listino che non compare più **esce dal listino** (quota a
  NULL) ma **non si cancella**: può essere assegnata.

Il modulo manda un marcatore `listino_presente`: un modulo che non mostra
l'editor non tocca il listino. Nella modifica di una gara di campionato il
listino si legge e non si scrive: si cambia dal campionato.

### Ordine e forma

Dalla quota più alta, a parità in ordine alfabetico; le quote uguali si
raggruppano («Serie B, Serie C 20 €»). Stabile e leggibile come una
locandina, senza bisogno di una colonna d'ordinamento (ADR-049 l'aveva
rinviata a quando servirà davvero).

Dove c'è un listino, vetrina, tessera, card, informazioni della gara e
dettagli del campionato lo mostrano **al posto** della quota unica; senza,
resta la quota unica di sempre.

### Storia delle modifiche

Ogni cambio del listino scrive una voce nella storia del proprietario
(ADR-075), con un campo solo, `listino`, che porta prima e dopo per intero
(JSON nell'ordine del listino, tradotto in lettura). Alla creazione no: la
storia racconta le modifiche, non la nascita.

## Alternative Considerate

### Alternativa 1: listino come testo libero sulla gara

**Descrizione**: un campo «quote» da scrivere a mano, mostrato così com'è.

- **Pro**: banale, nessun legame con le categorie.
- **Contro**: il direttore scriverebbe due volte le stesse categorie — nel
  testo e accanto agli iscritti — e i due elenchi divergerebbero al primo
  refuso. La quota personale, se un giorno servisse, non avrebbe dove appoggiarsi.

### Alternativa 2: tabella `quota` separata (categoria, competizione, importo)

**Descrizione**: il listino come entità a sé, che punta alle categorie.

- **Pro**: lascerebbe la categoria intatta.
- **Contro**: la categoria è già per competizione; una seconda tabella con la
  stessa chiave sarebbe una colonna travestita, con un join in più ovunque.

### Alternativa 3: mostrare al giocatore la sua quota

- **Contro**: la categoria la decide il direttore, spesso in sala: prima è
  ignota, e mostrarne una sbagliata è peggio che mostrare il listino. Rinviata
  insieme a incasso e «ha pagato».

## Conseguenze

### Positive

- La formula della locandina si configura senza testo libero, e il listino
  resta allineato alle categorie assegnate.
- Una gara senza handicap e senza listino è esattamente quella di prima.

### Negative

- Una categoria creata dal listino di un campionato con l'handicap acceso
  entra anche nella regola dell'ELO: è voluto (è la stessa categoria), ma va
  saputo.
- La modifica del listino non manda l'avviso «riconferma» agli iscritti, come
  invece fa il cambio di `entry_fee`: il listino è informazione, e chi ha già
  una categoria non ha un termine da riaccettare.

### Rischi

- Disattivare una categoria la toglie dal listino senza una voce di storia
  dedicata: la disattivazione non è un cambio di quota.

## Note Implementative

- Modello e regole: `models/categoria/listino.py`, `Categoria.entry_fee`,
  `Gara.usa_categorie`.
- Migration: `migrations/20261006_listino_quote_categoria.py`.
- Moduli: `templates/components/_listino.html` (editor e testo).
- Presidi: `tests/new/unit/test_listino_quote.py`,
  `tests/new/integration/test_listino_quote_route.py`.
