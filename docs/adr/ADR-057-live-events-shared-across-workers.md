# ADR-057: Gli aggiornamenti live passano da una tabella condivisa fra i worker

**Data**: 2026-09-02
**Stato**: Accepted
**Decisori**: Paolo, Claude

## Contesto

Le pagine che seguono una gara, una partita o il tabellone TPA chiedono al
server ogni tre secondi «è successo qualcosa?» (polling, ADR-021). Fra un poll
e l'altro l'evento — rack segnato, partita chiusa, turno nuovo, XP — doveva
stare da qualche parte: `routes/sse.py` lo teneva in un dizionario Python a
livello di modulo, nato con gli SSE (ADR-006) e sopravvissuto alla migrazione
al polling.

Il 2026-09-02 l'utente ha segnalato che «in alcuni casi» i cambiamenti non si
propagano. Il server log di PythonAnywhere, dopo un reload, ha chiuso la
questione:

```
Gracefully killing worker 3 (pid: 35)...
Gracefully killing worker 1 (pid: 29)...
Gracefully killing worker 2 (pid: 32)...
```

Tre worker uWSGI, tre **processi**, tre copie del dizionario che non si
parlano. Un evento scritto dal processo che ha servito il giocatore lo vedeva
solo un poll capitato sullo stesso processo. E siccome il cursore del client
era un timestamp che avanzava a ogni poll, anche vuoto, un evento mancato una
volta era perso per sempre: circa un evento su tre arrivava. In sviluppo, con
un processo solo, funzionava sempre — da qui l'impressione di un difetto
intermittente.

La verifica ha trovato altri quattro difetti nello stesso meccanismo, tutti
figli della stessa scelta:

1. `round_started` non veniva mai emesso: il bridge ascoltava
   `CompetitionStartedEvent`, che nessuno pubblicava. Il turno nuovo si
   scopriva ricaricando a mano;
2. gli eventi vivono 60 secondi, ma una scheda nascosta più a lungo tornava
   fingendo di riprendere da dove aveva lasciato: pagina vecchia, nessun
   avviso;
3. i servizi emettevano **dentro** la transazione, prima del commit: un poll
   in quella finestra ricaricava una pagina che leggeva ancora lo stato
   vecchio, e consumava l'evento. Il servizio notifiche aveva già trovato il
   problema e lo aggirava rinviando l'emit a un listener `after_commit`;
4. il cursore iniziale era l'orologio del **client**: un telefono avanti
   perdeva i primi eventi, uno indietro riceveva eventi vecchi, ricaricava, e
   li riceveva di nuovo — un ciclo di ricaricamenti finché non invecchiavano.

## Decisione

**L'archivio degli eventi è la tabella `live_event`**, l'unica cosa che i tre
processi condividono. Ne discendono le altre scelte:

- **il cursore è l'`id`** dell'ultimo evento visto, non un orologio. SQLite ha
  un solo scrittore per volta, quindi gli id si committano in ordine: «id
  maggiore del cursore» non salta niente. La tabella è `AUTOINCREMENT`,
  altrimenti SQLite riuserebbe il numero della riga più alta appena
  cancellata e un cursore fermo lì non vedrebbe più nulla;
- **il primo poll parte senza `since`** e riceve solo il cursore corrente. Il
  client non ha più un orologio da confrontare col server;
- **l'evento viaggia con la transazione.** Dentro `@transactional`,
  `emit_event` aggiunge la riga e basta: compare al commit, insieme al fatto
  che l'ha generato, e se la transazione salta salta anche lui. Fuori da una
  transazione gestita — le route che emettono dopo il servizio — committa da
  solo. Il rinvio `after_commit` delle notifiche è stato tolto: non serve più,
  e dentro `after_commit` SQLAlchemy non ammette altre query;
- **la conservazione resta di 60 secondi** e la pulizia gira a ogni emit (una
  DELETE ogni 30 secondi per processo), da chi sta già scrivendo: il poll
  resta una lettura pura e non compete mai per il lock di scrittura. Il server
  dichiara la conservazione al client (`retention`), e una scheda rimasta
  nascosta più a lungo **ricarica** invece di fingere;
- **`round_started` nasce dove nasce il turno**, in `RoundService`, nella
  stessa transazione. Con la strategia casuale i turni nascono tutti insieme,
  ma per chi guarda è un avvio solo;
- gli endpoint SSE a flusso (`/sse/gara/<id>` e simili), deprecati da
  ADR-021 e mai più usati dal client, sono stati **rimossi** insieme al
  generatore che li serviva.

## Alternative Considerate

### Alternativa 1: tenere la memoria e un solo worker

- Pro: nessuna modifica al codice.
- Contro: il numero di worker è del piano PythonAnywhere, non dell'app, e
  scenderne è pagare per avere meno; e un worker solo era esattamente la
  condizione in cui gli SSE bloccavano il sito (ADR-021).

### Alternativa 2: Redis o cache condivisa di uWSGI

- Pro: è lo strumento nato per questo.
- Contro: su PythonAnywhere non c'è Redis nel piano, e la cache di uWSGI si
  configura nel file `.ini` che non controlliamo. Il database è già lì, è
  già condiviso, e un minuto di eventi sono poche decine di righe.

### Alternativa 3: cursore a timestamp con margine di sicurezza

- Pro: cambia poco il client.
- Contro: qualunque margine è un compromesso fra duplicati (che con
  `reloadOnEvents` sono ricaricamenti doppi) ed eventi persi, e non risolve
  l'emit prima del commit: un evento con timestamp vecchio committato dopo
  resta invisibile a un cursore che l'ha già superato. L'id lo risolve per
  costruzione.

## Conseguenze

### Positive

- Ogni evento arriva, qualunque worker lo scriva e qualunque worker risponda
  al poll.
- L'evento e il fatto sono atomici: niente ricaricamenti su stato vecchio,
  niente badge fantasma dopo un rollback.
- Il turno nuovo compare da solo sulla pagina della gara.
- Chi torna su una scheda dopo minuti vede la pagina aggiornata.
- Il client non dipende più dall'orologio del dispositivo.

### Negative

- Ogni evento è una INSERT e ogni poll una SELECT sull'indice
  `(scope, scope_id, id)`: su SQLite via NFS costano più di un dizionario, ma
  il poll era già una richiesta HTTP completa e l'INSERT sta in una
  transazione che scriveva comunque.
- La tabella è un'altra cosa da conoscere: una riga di `live_event` che non
  compare nel poll è un problema di scope o di cursore, non di memoria.

### Rischi

- Un database con **più scrittori concorrenti** (Postgres, un giorno) può
  committare un id più piccolo dopo uno più grande: il cursore a id
  salterebbe quell'evento. Il modulo lo dice nella docstring; il rimedio è un
  margine sul cursore o un `ts` di commit, e va deciso quando e se cambia il
  database.
- Una pagina rimasta aperta col vecchio client manda un timestamp come
  `since`: il server lo tratta come primo poll, quindi quella pagina non
  riceve eventi finché non viene ricaricata. Succede solo nella finestra del
  deploy.

## Note Implementative

- Modello: `models/live_event.py`. Migration: `migrations/20260902_live_event.py`
  (con `created_at`/`updated_at`, come pretende `BaseModel`).
- Server: `routes/sse.py` — `emit_event`, `_get_events_since`,
  `_current_cursor`, `_poll_response`. Il bridge `routes/sse_bridge.py` non
  cambia.
- Client: `static/js/polling.js` — cursore, `retention`, `onGap`.
- Test: `tests/new/unit/test_live_event_store.py` (un **processo figlio**
  emette e il padre legge, su un DB su file; visibilità al commit; id dopo la
  pulizia; protocollo del poll), `tests/new/integration/test_live_event_turno_nuovo.py`
  (`round_started`), `tests/frontend/test_polling_cursore.cjs` (jsdom).
- Supera ADR-006 per l'archivio; ADR-021 resta valido per il trasporto.
