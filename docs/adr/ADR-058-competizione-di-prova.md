# ADR-058: La competizione di prova è invisibile per default e si cancella fisicamente

**Data**: 2026-09-04
**Stato**: Accepted
**Decisori**: Paolo, Claude

## Contesto

Un direttore appena promosso deve capire le schermate di gestione — creazione,
iscrizioni, avvio dei turni, risultati, classifica — prima di condurre una
serata vera. Oggi può solo leggere la guida o fare esperimenti su gare reali,
con giocatori veri, notifiche, ELO, XP ed elenchi pubblici. Le azioni di
simulazione esistono già ma solo in modalità debug (`routes/main.py`,
`/debug/*`), quindi non in produzione.

La specifica completa, uscita dall'intervista del 2026-09-04, è in
`docs/usecases/competizione-di-prova.md`. Qui si registrano le due decisioni
con conseguenze durature, che condizionano ogni funzione futura dell'app:

1. **come** una competizione di prova resta invisibile a chi non la dirige,
   anche nelle schermate che verranno scritte fra un anno;
2. **cosa** succede ai giocatori fittizi quando la prova finisce, dato che
   il progetto vieta l'hard delete di `User` (`models/CLAUDE.md`).

Il vincolo di fondo è che la prova **non è una seconda interfaccia**: è la
stessa gara con un flag, sulle stesse route, sugli stessi template. Una
funzione nuova nella parte generale deve comparire nella prova senza lavoro
aggiuntivo, e — questo è il punto delicato — **non deve far comparire la
prova** a chi non deve vederla.

## Decisione

### 1. Invisibilità per default, con lo stesso meccanismo del soft delete

`Gara.is_prova`, `Campionato.is_prova` e `User.is_fittizio` sono filtrati da
un `with_loader_criteria` installato sull'evento `do_orm_execute` della
sessione (`models/prova/visibility.py`), gemello di
`models/soft_delete/filter.py`. Il criterio non è un semplice `is_prova =
false`: è

    is_prova = false  OR  id IN (le prove che l'utente corrente dirige)

dove l'insieme delle prove dirette si calcola **una volta per richiesta** da
`current_user` (admin: tutte; direttore: le sue, per `director_id` e
`DirectorAssignment`; chiunque altro, e fuori da una richiesta: nessuna) e si
tiene in `g`. I giocatori fittizi seguono la prova a cui appartengono
(`User.prova_gara_id` / `User.prova_campionato_id`).

Conseguenza voluta: **una query nuova che dimentica la prova non la mostra**.
È la stessa filosofia deny-by-default dell'allowlist ADR-028. L'alternativa —
un `if not gara.is_prova` in ogni elenco pubblico — sarebbe stata giusta il
giorno della consegna e sbagliata alla prima lista scritta dopo.

Due scelte dentro la scelta:

* **`propagate_to_loaders=False`** e salto dei caricamenti di relazione
  (`is_relationship_load`, `is_column_load`). Il filtro agisce sulle query
  esplicite — elenchi, `session.get`, ricerche — e **non** sui percorsi
  `match.gara` o `inscription.user`. Altrimenti uno script fuori richiesta
  (ricalcolo ELO, job notturno) troverebbe `match.gara is None` su una
  partita di prova e morirebbe in un punto che non c'entra niente. Il soft
  delete propaga, e la trappola documentata in `section_builders.py` — «il
  criterio vale solo per le entità presenti nella query» — nasce da lì.
* **Opt-in esplicito** per chi lavora fuori richiesta: il context manager
  `prova_visibili()` e l'opzione `execution_options(include_prova=True)`,
  usati dal servizio, dal job di scadenza e dai test.

### 2. I giocatori fittizi si cancellano fisicamente

Il divieto di hard delete su `User` esiste per una ragione precisa: le
partite giocate da una persona restano nella storia degli avversari, e una
riga cancellata romperebbe le chiavi esterne di quella storia. Un giocatore
fittizio non ha storia fuori dalla sua prova: nasce con lei, gioca solo lì,
e quando la prova sparisce non resta nessuna riga che lo riferisca.

Per questo `ProvaService.elimina_prova` cancella **tutto, fisicamente**:
gare, partite, rack, iscrizioni, qualificazioni, rating e utenti fittizi. La
cancellazione è guidata dai metadati (`db.metadata`, come
`UserMergeService._user_fk_columns`): si seguono le chiavi esterne verso la
riga da togliere, figli prima dei padri, con `PRAGMA foreign_keys=ON`
rispettato. Nessun elenco di tabelle scritto a mano, che sarebbe già vecchio
alla prossima migration.

Le due colonne `User.prova_gara_id` / `User.prova_campionato_id` **non sono
chiavi esterne**: `gara.director_id` riferisce già `user`, e una FK di
ritorno chiuderebbe un ciclo che SQLAlchemy non sa ordinare (`drop_all`
butterebbe giù `gara` con i fittizi dentro, e SQLite rifiuterebbe). Sono
l'unica eccezione al «nessun elenco a mano»: `_elimina` toglie i fittizi
esplicitamente, prima della radice.

`user.anonymize()` e `UserMergeService` rifiutano i fittizi: non sono
persone, e i loro percorsi non hanno senso per loro.

### 3. Ciò che atterra sui fittizi non conta; ciò che atterra sul direttore sì

ELO e XP dei fittizi potrebbero anche muoversi — nessuno li vede — ma per
pulizia il motore di rating li esclude (`RatingExclusion.PROVA`, nell'unico
punto che decide, `models/rating/eligibility.py`) e la gamification scarta
gli eventi la cui competizione è di prova con **un guard solo**, nel punto
in cui i handler vengono registrati. Statistiche, badge e contatori del
direttore filtrano `is_prova` esplicitamente: è un elenco finito, e ogni
voce è una query che già filtra `deleted_at`.

## Alternative Considerate

### Alternativa 1: ambiente demo separato

Una seconda web app su PythonAnywhere con `DEBUG_MODE` acceso e il footer di
debug. Si fa in un pomeriggio. Scartata: costo di un secondo piano, database
condiviso fra tutti i direttori, interfaccia da sviluppatore, e il direttore
non userebbe il proprio account. Il bisogno è provare **la propria** app.

### Alternativa 2: filtro esplicito in ogni elenco

`Gara.is_prova.is_(False)` in ogni query pubblica, senza filtro di sessione.
Scartata perché il difetto non darebbe errore: la lista nuova che lo
dimentica mostra la prova a tutti, in silenzio, e nessun test lo vede finché
qualcuno non la nota in produzione.

### Alternativa 3: filtro di sessione che propaga ai caricamenti

Come il soft delete, `propagate_to_loaders=True`. Scartata per il motivo
detto sopra: `match.gara` che torna `None` fuori richiesta è un guasto in un
punto lontano dalla causa.

### Alternativa 4: giocatori fittizi condivisi, o soft delete anche per loro

Un pool di sistema riusato da tutti i direttori eviterebbe di creare utenti
a ogni prova. Scartato nell'intervista: rating che derivano nel tempo,
iscrizioni concorrenti fra prove diverse, e un pool che non si cancella mai.
Il soft delete al posto della cancellazione fisica lascerebbe crescere la
tabella `user` di sedici righe a prova, per sempre, senza che nessuna riga
serva a qualcuno.

## Conseguenze

### Positive

* Una funzione nuova compare nella prova da sola, e la prova non compare
  altrove da sola. I due lati dell'allineamento sono per costruzione.
* La regola «chi vede cosa» sta in un modulo (`models/prova/visibility.py`),
  come per il soft delete; i test di enumerazione la verificano sugli elenchi
  pubblici.
* Il DB di produzione non accumula prove: scadono a 14 giorni e spariscono
  con i loro utenti.

### Negative

* Un servizio o uno script che tocca le prove fuori da una richiesta deve
  chiederle esplicitamente (`prova_visibili()`), altrimenti non le trova. È
  lo stesso onere di `with_deleted()`, e va ricordato.
* La cancellazione guidata dai metadati segue le FK dichiarate: una tabella
  che riferisce una gara **senza** chiave esterna (oggi `director_assignment`
  con `entity_id` polimorfico, `live_event`, il JSON di `notification`) va
  gestita a mano o lasciata come rumore innocuo. L'elenco è nel servizio.

### Rischi

* **Ricorsione nel listener.** Calcolare l'insieme delle prove dirette dentro
  `do_orm_execute` esegue query — e accede a `current_user`, che carica
  l'utente con un'altra query. Il listener si protegge con un flag su `g`
  (`_prova_scope_in_corso`): mentre calcola, non filtra. Presidiato dai test
  di visibilità, che passano dal client HTTP e non dal servizio.
* **Cache dell'insieme nella richiesta.** Se una richiesta crea una prova e
  poi la ricerca con una query esplicita, l'insieme calcolato prima non la
  contiene. `ProvaService` invalida la cache dopo ogni creazione; la
  `session.get` dopo `flush` passa comunque dall'identity map.

## Note Implementative

* Il flag vive sulla **radice** (campionato, o gara singola) e le gare di un
  campionato di prova lo ereditano alla creazione, come la regola di apertura
  (ADR-056). `prova_expires_at` sta solo sulla radice.
* I nomi dei fittizi vengono da una tabella fissa di sedici coppie comuni
  (`models/prova/nomi.py`), distinta dai nomi del seed dimostrativo. Lo
  **username è il nome verosimile** («Maria Rossi», e «Maria Rossi (2)» se
  un'altra prova l'ha già), perché è il nome con cui si gioca in classifiche
  e abbinamenti; l'email è tecnica su dominio riservato `.invalid`, la
  password non è impostabile, l'onboarding è già fatto.
* Le notifiche originate da una prova ricevono il prefisso «Prova ·» in
  `NotificationService.create_notification`; oggi non esistono canali email o
  push per le notifiche, quindi non c'è nulla da spegnere.
* Sequenza di consegna in `docs/usecases/competizione-di-prova.md`: questa
  ADR accompagna la tappa 1 (fondamenta e gara singola).
