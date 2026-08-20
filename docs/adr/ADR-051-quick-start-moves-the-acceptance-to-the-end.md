# ADR-051 L'avvio rapido non toglie l'accettazione: la sposta alla fine

**Data**: 2026-08-20
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Segnare una partita fra due persone **già in sala, una di fronte all'altra**
passava per un percorso costruito per organizzare un incontro **futuro** fra
due che non si erano ancora accordati (issue #176):

1. si compila una proposta (`/match/proposals/create`), dove `scheduled_at`,
   `location` e `discipline` sono tutti obbligatori;
2. l'avversario **accetta**;
3. qualcuno fa **start**;
4. solo allora si segna.

Quattro passaggi e tre campi obbligatori per due persone che hanno già le
stecche in mano. La domanda peggiore è la data programmata: a chi sta per
spaccare si chiede *quando*, e la risposta è «adesso».

Il nodo non è l'interfaccia, è l'accettazione. Se l'avversario deve accettare
siamo di nuovo a due passaggi, e uno dei due resta a guardare il telefono
dell'altro. Se non deve accettare niente, allora chiunque può attribuire a
chiunque una partita mai giocata — e quel risultato conta per l'Elo.

## Decisione

L'avvio rapido crea una `IndividualMatch` **già in corso**, senza proposta e
senza accettazione: si sceglie l'avversario e si è al segnapunti. Quando, dove
e come si precompilano dall'ultima partita giocata (o dalla sala in cui il
giocatore risulta disponibile, o da un default di sistema) e si cambiano solo
se si vuole.

L'accettazione **non sparisce: si sposta a fine partita**, dove esiste già —
la doppia conferma del risultato (`CONFIRMED_BY_BOTH`). Il punto è che alla
fine la domanda ha una risposta che l'avversario conosce davvero: il
punteggio. All'inizio gli si chiederebbe di ratificare un'intenzione; alla
fine gli si chiede di riconoscere un fatto.

Questo regge perché per le sfide individuali **l'Elo globale si muove solo
sulla validazione bilaterale**: `IndividualMatch.confirm_result` emette
`IndividualMatchCompletedEvent` unicamente dopo la seconda conferma, ed è quel
solo evento che `RatingEventHandlers.handle_individual_match_completed`
ascolta. Una partita aperta contro qualcuno che non l'ha mai giocata resta
quindi **senza effetti sul rating** finché quel qualcuno non la riconosce: il
danno possibile è una riga «in corso» da ignorare, non un punteggio falso.

## Alternative Considerate

### Alternativa 1: l'avversario accetta prima, come nelle proposte
- Pro: nessuno può aprire una partita a nome di altri, nemmeno per sbaglio.
- Contro: restano due passaggi e un'attesa proprio nel momento in cui i due
  giocatori sono nello stesso posto e possono parlarsi. Non risolve l'issue:
  la sposta di un campo.

### Alternativa 2: parte subito e resta non validata per sempre
- Pro: massima libertà, nessuna richiesta a nessuno.
- Contro: è la stessa cosa scelta, meno la conferma finale — e senza quella la
  partita non entra mai nel rating né nello storico «giocate». Il tempo speso a
  segnarla non produce niente.

### Alternativa 3: includere subito l'avversario senza account (l'ospite)
- Pro: in sala capita spesso di giocare con chi non è iscritto.
- Contro: `individual_match.player2_id` è `NOT NULL` con FK su `user`, quindi
  servirebbero una migration e una revisione di Elo, statistiche, traguardi e
  storico unificato. È un'issue a sé, non un dettaglio di questa: rimandata
  esplicitamente.

## Conseguenze

### Positive
- Dalla sala al segnapunti in un passaggio, senza rispondere a niente.
- Nessun meccanismo nuovo di validazione: si riusa quello che c'è, e l'Elo
  resta protetto dalla stessa condizione di prima.
- La rivincita immediata (`Rigioca adesso` sulla partita conclusa) diventa un
  collegamento all'avvio rapido con l'avversario già scelto.

### Negative
- Un giocatore può comparire in una partita che non ha aperto lui. La vede
  fra le sue sfide e riceve una notifica, ma non l'ha chiesta.
- Chi non conferma mai lascia la partita «in corso» a tempo indeterminato,
  esattamente come una partita ordinaria mai chiusa.

### Rischi
- **Doppio avvio**: due partite in corso fra le stesse due persone non esistono
  al biliardo. Il servizio lo previene restituendo quella già in corso invece
  di aprirne un'altra (`QuickMatchService.find_open_match`).
- **Sfide non richieste**: l'avversario deve comunque aver sbloccato le sfide
  individuali (`can_access("create_match_direct")`), lo stesso filtro
  dell'elenco avversari e della ricerca giocatori. Se in futuro dovesse
  servire, il rifiuto esplicito di una partita aperta da altri è il naturale
  seguito di questa decisione.

## Note Implementative

- `models/individual_match/quick_match_service.py` — precompilazioni
  (`get_defaults`), guardia sul doppio avvio (`find_open_match`) e avvio
  (`start`). La partita nasce `SCHEDULED` e chiama `start_match()`: la
  transizione è quella di sempre, non uno stato scritto a mano (nel multi-set
  apre anche il primo set).
- `routes/individual_match/quick.py` — `GET/POST /match/quick`, con
  `?opponent_id=` per arrivarci dalla partita appena conclusa. Endpoint
  registrato in `ENDPOINT_ROLES` (ADR-028).
- `templates/individual_match/quick_match.html` — riepilogo delle
  precompilazioni con «Cambia» che apre i campi; gli avversari abituali sono
  card da toccare, la ricerca completa resta per gli altri.
- Test: `tests/new/unit/test_quick_match_service.py` (fra cui
  `test_il_risultato_resta_da_confermare_in_due`, che presidia il patto di
  questo ADR) e `tests/new/integration/test_individual_match_quick_routes.py`.
