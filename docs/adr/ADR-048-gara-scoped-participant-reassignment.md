# ADR-048 Spostare la partecipazione a una gara: fatti riassegnati, derivati ricalcolati

**Data**: 2026-08-19
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Il direttore di gara iscrive un giocatore scegliendolo da un elenco di nomi. Con
due account che si somigliano — `LUIGI` e `LUIGI R` — la scelta sbagliata non dà
nessun segnale: la gara si apre, si gioca e si chiude regolarmente. L'errore
diventa visibile solo alla fine, in classifica generale di campionato, dove
compaiono **due giocatori dove doveva essercene uno**: uno con le prime gare,
l'altro con l'ultima.

A quel punto la partecipazione sbagliata non è una riga: è iscrizione, partite,
rack, eventuali set e prove di esercizio, incontri anti-rivincita, tre classifiche
(turno, gara, campionato), ELO, movimenti XP, livello, serie e traguardi.

Esisteva già `UserMergeService` (unione di due account duplicati), che risolve un
problema **vicino ma diverso**: fonde *tutto* un account in un altro e anonimizza
il sorgente. Qui i due account sono due persone vere, e quella iscritta per
sbaglio deve restare in piedi con la sua storia altrove.

## Decisione

Un servizio dedicato, `GaraParticipantReassignService`
(`models/competition/participant_reassign_service.py`), sposta la partecipazione
a **una sola gara** da un giocatore a un altro. Quattro scelte lo definiscono.

### 1. I fatti si riassegnano, i derivati si ricalcolano

Iscrizione, partite, rack, set, prove: sono **fatti**, e cambiano proprietario
con un UPDATE. Classifiche, ELO, livello, traguardi sono **derivati**: non si
spostano, si ricostruiscono da zero dalla fonte di verità dopo che i fatti sono
a posto.

È la stessa distinzione di `UserMergeService`, ed è quello che rende il
risultato corretto *per costruzione* invece che per fortuna. Spostare una riga
di classifica sarebbe il modo comodo di sbagliare: la posizione di un giocatore
dipende da quelle di tutti gli altri.

L'ELO in particolare **non si può correggere in un punto solo**: è
path-dependent, ogni partita parte dal rating che le precedenti hanno prodotto.
Si azzera e si rigioca tutto (`recalculate_all_elo` + `recalculate_all_elo_global`).

### 2. L'elenco delle tabelle si deriva dal grafo delle chiavi esterne

Le tabelle toccate sono ventisei. Scriverle a memoria vuol dire dimenticarne una
oggi, e dimenticarne una nuova domani — con l'aggravante che la dimenticanza non
dà errore: sposta metà partecipazione e lascia l'altra metà dov'era.

La mappa `_GARA_SCOPES` dice, per ogni tabella, **come si restringe a una gara**;
`tests/new/unit/test_gara_participant_reassign_map.py` cammina il grafo delle FK
partendo da `gara` e pretende che ogni tabella raggiungibile con una colonna
verso `user.id` sia classificata: spostata, cancellata, o esclusa **con un motivo
scritto**. Una tabella nuova non classificata fa diventare rosso il test.

Due esclusioni non ovvie:

- **`player_encounter`** (memoria anti-rivincita) porta l'ordinamento
  `player1_id < player2_id` dentro la riga, sotto un `UNIQUE(gara_id, p1, p2)`.
  Riassegnare un id romperebbe l'ordine in silenzio: gli incontri della gara si
  **cancellano e si rigenerano** dalle partite.
- **`hidden_match` / `hidden_inscription`** sono preferenze di visibilità di chi
  le ha messe, non fatti della gara: le righe del sorgente si cancellano.

### 3. I traguardi non più meritati si tolgono

Lo sblocco degli achievement è **monotòno** per scelta di dominio
(`_rebuild_achievements` sa solo sbloccare, non revoca mai): giusto finché i
fatti non si possono disfare. Qui però un fatto viene disfatto davvero, e senza
revoca resterebbe acceso il badge di «Debutto Torneo» su un giocatore che non ha
mai partecipato a una gara.

Si usa `AchievementService.revoke_no_longer_earned` limitata alle metriche che lo
spostamento può far **scendere** (vittorie, partecipazioni, podi, avversari
diversi, serie di vittorie, strategie provate, esercizi). Non è una revoca a
colpo sicuro: è un **ricalcolo**, e se altre gare reggono il requisito il
traguardo resta. L'XP torna indietro con un movimento compensativo, quindi la
revoca va **prima** del ricalcolo del livello, che somma il registro.

I traguardi con requisito booleano o legato a un evento irripetibile restano
fuori: lì «non idoneo adesso» non vuol dire «non è mai successo».

### 4. La prova generale si fa su una copia del file, non con un rollback

Il modo naturale di provare sarebbe eseguire tutto e annullare. **In questa
applicazione non funziona**, e il motivo è scritto qui perché altrimenti lo si
riscopre: un `@transactional` annidato chiama `db.session.commit()`, e dal
passaggio a SQLAlchemy 1.4 quel commit chiude la **transazione esterna** invece
di rilasciare il savepoint (il commento nel gestore di transazione — *«This
releases the savepoint in SQLAlchemy»* — è un'assunzione da SQLAlchemy 1.3).
Il ricalcolo della gamification scriverebbe per davvero e l'annullamento finale
non troverebbe più niente da annullare.

Quindi due modalità, entrambe oneste:

- `plan()` — **sola lettura**: stesse validazioni, e il conto esatto delle righe
  e degli XP che si muoverebbero. Non scrive niente;
- `reassign()` — scrive. La prova generale con la classifica finale si fa
  copiando il file `.db` e lanciando lo script con `--database` su quella copia.
  Con SQLite la copia del file è anche il backup.

*(nota 2026-09-13)* Il difetto è **corretto** (ADR-061): un `@transactional`
annidato rilascia o annulla il proprio savepoint, e salva solo il più esterno.
Le due modalità restano come sono — `plan()` è comunque più economico di un
«esegui e annulla», e la copia del file resta il backup — ma il motivo scritto
sopra non vale più.

### 5. La classifica persistita si rinfresca, non si crea

*(emendamento 2026-08-19, dall'applicazione al caso reale)*

La schermata che mostrava i due omonimi **non legge** la tabella
`classification`: `TournamentStatisticsService.calculate_general_classification`
aggrega al volo le `GaraClassification` delle gare concluse. La tabella
persistita l'applicazione la scrive solo in momenti precisi — chiusura del
campionato, avvio dei playoff, correzione manuale di un risultato — e fino ad
allora è vuota **di proposito**.

Nel caso reale il campionato 4 non ci era ancora arrivato: zero righe. Popolarle
durante la riparazione non sarebbe stato inerte, per due motivi di peso diverso.

Il primo è **certo**: da quelle righe leggono il profilo giocatore
(`profile_service`, `UserStatsService`), l'export GDPR, la dashboard
(`activity_feedback`) e le qualificazioni playoff. Il campionato sarebbe comparso
nelle classifiche di tutti i suoi giocatori perché qualcuno ha corretto un errore
di iscrizione.

Il secondo è **eventuale, e dipende dalle strategie in gioco**: per le gare
seminate l'assenza di righe *è* la condizione che fa scegliere il sorteggio
casuale — `AmalfiStrategy._seeding_order` (*«Se non c'è classifica campionato
(prima gara), fallback a random»*) e `DirectEliminationStrategy._classification_rank`.
Le strategie `random_anti_rematch`, `round_robin` e `double_knockout` quelle
righe non le leggono, quindi il rischio si presenta solo se una gara futura del
campionato usa una delle due seminate. Una riparazione dati, comunque, non deve
decidere come si accoppia la gara successiva.

Quindi: **si rinfresca ciò che esiste, non si crea ciò che non c'era.** Una riga
presente va aggiornata — lasciarla stantia dopo lo spostamento sarebbe peggio che
non averla; una riga assente resta assente, perché la sua assenza è essa stessa
uno stato che il resto del sistema legge.

Ne è uscito un difetto latente, corretto alla radice:
`ClassificationService.update_campionato_classification` era **solo upsert** —
aggiornava e creava, mai toglieva. Nel flusso normale non si nota, perché da un
campionato un giocatore non sparisce; sparisce però quando una gara viene
cancellata, un'iscrizione ritirata, o una partecipazione spostata. E la riga
rimasta indietro non è inerte: `start_playoff` qualifica leggendo proprio quelle
righe. Ora la funzione pota chi non è più nell'aggregato — ma **solo avendo un
risultato in mano**: sul `return []` da aggregato vuoto non tocca niente, perché
«non so niente» e «non c'è più nessuno» sono due cose diverse.

## Conseguenze

- La correzione è uno **script da console** (`scripts/reassign_gara_participant.py`),
  non una funzione dell'interfaccia. È un intervento raro, distruttivo e da fare
  con la web app disabilitata: metterlo dietro un bottone lo renderebbe più
  facile da sbagliare che da usare.
- Il ricalcolo dell'ELO tocca **tutti** gli utenti, per costruzione. Su un
  database grande è l'operazione più costosa dell'intero spostamento.
- Restano **fuori** dalla riparazione, e il report le elenca: le notifiche già
  recapitate al giocatore sbagliato (sono messaggi storici, non stato) e le
  eventuali qualificazioni playoff, che dipendono dalla posizione in classifica
  e vanno rigenerate a mano.
- La potatura delle righe orfane in `update_campionato_classification` vale per
  **tutti** i suoi chiamanti, non solo per lo spostamento: è il posto giusto per
  quella regola, e i due presidi stanno in
  `tests/new/integration/test_campionato_classification_pruning.py`.
- Il difetto del `@transactional` annidato descritto al punto 4 **non è stato
  corretto**: tocca il gestore di transazione di tutta l'applicazione ed è un
  intervento a sé. Qui è stato aggirato, e documentato perché non venga
  riscoperto come «strano» la prossima volta. *(nota 2026-09-13: corretto da
  ADR-061. Era peggio di come è descritto qui: oltre a salvare il lavoro
  interno quando l'esterno falliva, un guasto interno catturato dall'esterno
  cancellava il lavoro fatto prima.)*

## Alternative scartate

**Unire i due account** (`UserMergeService`). Risolverebbe la classifica in una
riga di comando, ma `LUIGI` sparirebbe come account: è una persona vera che
gioca altrove.

**Correggere a mano la classifica di campionato.** È il sintomo, non la causa:
lascerebbe l'errore in tutto il resto — storico partite, ELO, XP, traguardi — e
la prima ricostruzione della classifica lo rimetterebbe com'era.

**Cancellare la gara e rigiocarla.** Perde i referti veri di tutti gli altri
partecipanti per l'errore su uno.
