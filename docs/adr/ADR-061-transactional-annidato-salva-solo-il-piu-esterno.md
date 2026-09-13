# ADR-061 Un `@transactional` annidato rilascia il proprio savepoint: salva solo il più esterno

**Data**: 2026-09-13
**Stato**: Accepted
**Decisori**: Paolo Coppola

## Contesto

Il decoratore `@transactional` (`models/transaction/manager.py`) apre una
transazione, o un savepoint se un altro `@transactional` è già in corso. Nel
ramo annidato il savepoint si chiudeva con `db.session.commit()` e si annullava
con `db.session.rollback()`. Il commento accanto diceva *«This releases the
savepoint in SQLAlchemy»*: era vero in SQLAlchemy 1.3. Dalla 1.4, e quindi con
la 2.0 in uso, quei due metodi agiscono sulla transazione **più esterna**.

ADR-048 (punto 4) lo aveva trovato il 2026-08-19 e aggirato, rimandando la
correzione perché tocca il meccanismo usato da tutta l'applicazione (426
decoratori). Una prova sul database il 2026-09-13 ha mostrato che gli effetti
erano due, e opposti:

1. **l'esterna fallisce dopo l'interna**: restavano scritti il lavoro interno e
   quello dell'esterna fatto *prima* della chiamata. Si annullava solo la coda.
   Un'operazione composta finiva scritta a metà;
2. **l'interna fallisce e l'esterna cattura e prosegue**: il rollback
   dell'interna cancellava anche il lavoro dell'esterna fatto *prima*, e poi
   l'esterna salvava il resto come se niente fosse. Perdita di dati senza
   errori.

Il secondo caso non è teorico. `EventBus.publish` cattura l'eccezione di ogni
handler e continua con gli altri, e gli handler decorati girano dentro la
transazione del servizio che pubblica l'evento. Un handler di gamification o di
notifica che falliva annullava in silenzio il fatto che l'aveva generato — il
risultato di una partita, la creazione di una gara. ADR-036 contava proprio
sull'«isolamento per-handler dell'EventBus», che quindi non reggeva.

Correggendo il gestore è emerso un secondo difetto, del driver. `sqlite3` in
modalità predefinita apre la transazione solo davanti a una scrittura: le
letture girano fuori da ogni transazione. Se l'esterna aveva soltanto letto, il
`SAVEPOINT` dell'interna era per SQLite il primo comando, cioè l'inizio della
transazione, e il suo `RELEASE` equivaleva a un commit. Chiudere il savepoint
giusto non basta: l'annullamento successivo non trova più niente.

## Decisione

**Salva solo il decoratore più esterno.** Quello annidato tiene il
`SessionTransaction` restituito da `db.session.begin_nested()` e chiude o
annulla **quello** (`_chiudi_savepoint`):

- l'esterna fallisce → si annulla tutto, interna compresa;
- l'interna fallisce → si annulla il suo savepoint; il chiamante decide se
  propagare o proseguire, e se prosegue il suo lavoro resta.

**Su SQLite, prima del savepoint annidato si apre la transazione con `BEGIN`**
se il driver non ne ha una (`_apri_transazione_sqlite`). È lo stesso `BEGIN`
differito che il driver emetterebbe alla prima scrittura, quindi i lock non
cambiano.

Un savepoint già chiuso — il codice interno ha chiamato `db.session.commit()`
o `rollback()` a mano, cosa che il progetto vieta — produce un warning nel log,
non un'eccezione.

Il ramo «pseudo-nested» (il decoratore più esterno per il gestore trova la
sessione già aperta da una lettura) e quello non annidato non cambiano: sono la
transazione esterna, e `db.session.commit()` lì è la cosa giusta.

## Alternative Considerate

### Alternativa 1: la ricetta SQLAlchemy per pysqlite su tutto il motore

**Descrizione**: `isolation_level = None` alla connessione e `BEGIN` sull'evento
`begin` del motore, come raccomanda la documentazione di SQLAlchemy.

- **Pro**: corregge anche i `with db.session.begin_nested()` scritti a mano.
- **Contro**: ogni lettura diventa una transazione che tiene il lock condiviso
  fino alla fine della richiesta. In produzione ci sono tre processi uWSGI su
  un file SQLite con journal di rollback, senza WAL (ADR-045): chi scrive
  aspetta tutti i lettori, e due transazioni che leggono e poi scrivono si
  bloccano a vicenda con `database is locked` immediato. Cambia la concorrenza
  di tutta l'applicazione per correggere un caso.

### Alternativa 2: vietare l'annidamento

**Descrizione**: la regola già scritta in `models/transaction/CLAUDE.md` —
«decora solo il metodo più interno» — resa obbligatoria.

- **Pro**: nessuna modifica al gestore.
- **Contro**: non si può far rispettare. Gli handler dell'EventBus sono decorati
  e girano per costruzione dentro un servizio decorato, e un servizio che ne
  chiama un altro è la norma. La regola esisteva e non ha impedito il difetto.

### Alternativa 3: l'interno senza savepoint

**Descrizione**: un `@transactional` annidato non apre niente, lavora nella
transazione esterna.

- **Pro**: il più semplice.
- **Contro**: un guasto interno catturato dall'esterno lascerebbe la sessione a
  metà, e dopo un errore di flush inutilizzabile finché qualcuno non annulla
  tutto. Si torna al caso 2 per un'altra strada.

## Conseguenze

### Positive

- Un'operazione composta è atomica: o tutto o niente.
- Un handler che fallisce non cancella più il fatto che l'ha generato.
- Un «esegui e annulla» ora annulla davvero: la motivazione del punto 4 di
  ADR-048 non vale più, anche se lo script resta con `plan()` e la copia del
  file.
- Gli eventi live scritti nella transazione (ADR-057) arrivano sul database
  insieme al fatto, non prima.

### Negative

- Il lavoro di un servizio interno diventa visibile agli altri processi solo al
  salvataggio dell'esterno, non a metà operazione. Chi contava su un salvataggio
  anticipato — non ne è stato trovato nessuno — vedrebbe i dati più tardi.

### Rischi

- **I `with db.session.begin_nested()` scritti a mano** (una dozzina, per lo
  schema di ADR-025) non passano dal gestore: se prima non c'è stata nessuna
  scrittura, il loro `RELEASE` resta un commit su SQLite. In quegli usi il
  savepoint serve a catturare un `IntegrityError`, quindi il danno è limitato,
  ma non è corretto.
- **Codice che chiama `db.session.commit()` dentro un `@transactional`**: salva
  tutto e chiude il savepoint. Ora lascia un warning nel log, che è il modo di
  trovarlo.

## Note Implementative

- `models/transaction/manager.py`: `_apri_transazione_sqlite`,
  `_chiudi_savepoint`, rami annidati di commit e rollback.
- Presidio: `tests/new/unit/test_transazioni_annidate.py` rilegge il database
  dopo aver annullato la sessione, quindi vede solo ciò che è salvato davvero:
  i due casi del contesto, l'esterna che ha solo letto, tre livelli, la sessione
  già aperta.
- Emendati con una nota datata: ADR-036, ADR-048, ADR-052.
