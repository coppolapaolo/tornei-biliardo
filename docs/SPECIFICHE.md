# Web App Tornei Biliardo

L'app permette di organizzare Tornei di Biliardo, ma è anche una community che permette ai giocatori di incontrarsi e giocare e mantenere le statistiche di gioco. 

## Tipologie di utenti

La app ha un unico **Admin** configurato nelle impostazioni lato server. Admin non può essere cancellato e non può cambiare la password. L'email di ``admin`` è configurata, come la password nelle impostazioni lato server. 

Ci sono tre tipologie di utenti:
1. **guest**: l'utente visitatore non loggato
2. **player**: l'utente registrato che può iscriversi ai tornei e alle prove e giocare
3. **director**: il player che ha chiesto e ottenuto di poter diventare direttore di gara. Mantiene tutte le funzionalità del player, ma assume i poteri di ``admin`` limitatamente alla gestione di tornei e di gare create da lui o in cui è nominato _co-direttore_

## Tornei

La app permette di organizzare tornei. ``admin`` o un utente ``director`` possono creare nuovi tornei. Un **torneo** è una collezione di ``n`` **prove**, con una **classifica** complessiva. 
Un **torneo** può avere anche dei **playoff** che possono essere giocati alla fine del **torneo** (dopo che si è conclusa l'ultima **prova** del torneo). La logica dei **playoff** può essere di tipo diverso e viene impostata da ``admin`` o da un utente ``director``. 
``admin`` o un utente ``director`` creano, modificano e cancellano un **torneo**. Non sempre le modifiche e le cancellazioni sono possibili: ad esempio, se una **prova** è in itinere (i giocatori stanno giocando le partire della **prova**) allora non è possibile modificarla. 
Nel caso di cancellazione di un **torneo** con alcune **prove** già giocate, si opera un _soft delete_ e i **match** giocati vengono mantenuti per le **statistiche** personali dei vari **player**.
Un **torneo** può avere 0 o più direttori di gara. Se ne ha zero allora viene gestito dall'``admin``. 

## Prove

Una **prova** è parte di un **torneo**. È formata da uno o più **turni** e da zero o più **challenge**. Il numero di turni e di challenge di default dipende dal toreno a cui appartiene la prova. 
Durante un **turno** i giocatori vengono abbinati e giocano un **match** sulla base del risultato del **match** si ottiene una **classifica** di **turno**. 
La app permette anche ad ``admin`` o un utente ``director`` di organizzare **prove _standalone_**. Una **prova _standalone_** è una **prova** non collegata ad un **torneo**. Una **prova _standalone_** può avere zero o più direttori di gara. Se non ha direttori di gara allora viene gestita da ``admin``. 
I **player** si iscrivono/disiscrivono alle **prove**, quando le iscrizioni sono aperte. ``admin`` o un utente ``director`` apre le iscrizioni definendo data di inizio e fine. La fine delle iscrizioni deve essere antecendente alla data e ora di inizio della prova. 
Una **prova** si svolge in una **sala biliardi** con una data e ora di inizio. 
La **prova** ha un numero minimo e massimo di iscritti (opzionali) e una quota di iscrizione in euro.
Una prova ha una **strategia di abbinamento** tra turni, una policy per definire l'abbinamento del primo turno (ad esempio casuale oppure sulla base della classifica) e una policy per la gestione del numero dispari di giocatori (con X o con trii). Tutti questi valori hanno un default che dipende dal torneo a cui appartiene la prova.
Una prova ha una **classifica** finale con un eventuale meccanismo per definire gli spareggi. Ad esempio una prova potrebbe definire gli spareggi solo per le prime tre posizioni con uno "_spot shot rally_": se nelle prime tre posizioni ci sono 2 o più giocatori pari merito, allora si affrontano in una **challenge** di tipo spot shot. Un altro tipo di spareggio potrebbe essere un match con un solo rack. 
Ua **prova** ha una **policy per il forfait** il cui valore di default è definito dal torneo. La policy definisce come trattare un giocatore che ha dichiarato forfait negli abbinamenti e nei match successivi. La policy può essere _exclude_ e in questo caso il giocatore viene eliminato dagli abbinamenti (ma non dalla classifica), oppure _forfait_ e quindi il giocatore rimane negli abbinamenti e fa vincere per forfait i giocatori che capitano con lui.

### Turno

Un turno è legato ad una prova. È dato da un abbinamento di giocatori che giocano contemporanemente un match di tipo uguale (non è possibile, ad esempio, che in un turno due giocatori giochino a palla 9 e altri tue a palla 8, oppure che due giochino al meglio di 5 e altri al meglio di 7; tutti i match hanno le stesse caratteristiche. L'unica eccezione sono i match a tre, nella strategia di abbinamento casuale con classifiche basate sulla differenza di rack, descritti più avanti).
Una possibile **strategia di abbinamento** è **_amalfi_**. Un'altra possibile strategia di abbinamento è _round robin_. 
Una volta che tutti i match del turno sono terminati, è possibile modificare la classifica della prova. Quindi un turno prende la classifica precedente al turno, i risultati dei match e restituisce la classifica aggiornata.

#### Strategia di abbinamento

Una **strategia di abbinamento** abbina un elenco di giocatori in match. 

Ad esempio la **strategia di abbinamento _amalfi_** dipende da quanti turni mancano alla fine della prova e, dato un elenco ordinato di giocatori, abbina il giocatore `n`-esimo con il giocatore `n+i`-esimo con i pari al numero di turni che mancano da giocare per terminare la prova. 
_Amalfi_ evita che due giocatori si incontrino più di una volta, quindi se l'abbinamento derivante dalla logica generale `(n, n+i)` è stato già giocato in un turno precedente, allora scorre l'elenco in modo ciclico fino a trovare un giocatore `(n+i+j)%lunghezza_elenco` con cui il giocatore `n` non ha già giocato.

Una **strategia di abbinamento per _eliminazione diretta_**, invece, abbina tra loro i vincitori del turno precedente.

Una **sttategia di abbinamento per _doppio ko_** abbina tra loro i vincitori e ripesca una sola volta i perdenti.

La **strategia di abbinamento _casuale_** abbina a caso i giocatori assicurandosi solo che non ci sia mai lo stesso abbinamento più di una volta in turni diversi della stessa prova. Questo tipo di strategia può calcolare tutti gli abbinamenti subito e non ha bisogno di aspettare la conclusione dei match per l'abbinamento successivo.

Una strategia di abbinamento è associata anche ad una **strategia per il _primo abbinamento_** che può essere _casuale_ (in questo caso limitata al primo turno) oppure _basato su classifica_ oppure _basato su rating_ (fargo o elo).

Una strategia di abbinamento è associata anche ad una **policy per la X** che decide come trattare il caso in cui ci siano meno giocatori rispetto a quelli necessari. 
Ad esempio la strategia di _eliminazione diretta_ seleziona casualmente il numero di giocatori che eccede la potenza del 2 più alta e li fa passare tutti automaticamente al secondo turno (perché li abbina alla X e vincono atuomaticamente). 
La strategia di abbinamento _amalfi_ con classifiche basate su (match vinti, differenza rack vinti-persi) nel caso in cui i giocatori siano dispari abbina un giocatore alla X assegnando il match vinto, ma con zero differenza punti. In questo modo chi ottiene la X con l'abbinamento ottiene in classifica un posizionamento migliore di tuttii perdenti e peggiore di tutti i vincenti. 
Una variante, sempre per _amalfi_ consiste nel gestire la X con una challenge che possa dare un punteggio da zero alla massima differenza rack raggiungibile in quella prova. In questo modo il giocatore abbinato con la X, invece di stare fermo il turno, gioca la challenge e in classifica ottiene il match vinto e un differenza rack pari al punteggio nella challenge. 

Se la **strategia di abbinamento _casuale_** è abbinata a classifiche basate solo sulla differenza rack, allora in caso di numero dispari di giocatori è possible evitare la X e gesitre il numero dispari aggiungendo alle coppie di giocatori un trio. 
I giocatori nel trio giocano uno o più mini gironi all'italiana (round robin) in cui tutti giocano con gli altri un solo rack. Il punteggi che ottengono alla fine del trio è pari a 1+numero di rack vinti. Questo abbinamento à possibile solo per le distanze da 3 a 7 con il seguente schema:
| Distanza | mini gironi | rack giocati da ogni giocatore | rack totali | punteggio |
| --- | --- | ---| ---| --- |
| 3 | 1 | 2 | 3 | 1 + rack vinti |
| 4 | 2 | 4 | 6 | rack vinti |
| 5 | 2 | 4 | 6 | 1 + rack vinti |
| 6 | 3 | 6 | 9 | rack vinti |
| 7 | 3 | 6 | 9 | 1 + rack vinti |

Per la distanza oltre al 7 i rack totali da giocare diventano troppi rispetto a quelli che giocano le coppie e quindi il trio allungherebbe troppo i tempi della prova. Per questo motivo la app limita la possibilità di scegliere questa opzione solo fino a distanza 7.
### Prove amalfi

Una prova **amalfi** è una prova in cui non c'è eliminazione e tutti i giocatori giocano lo stesso numero di turni.
Inizialmente gli iscritti vengono abbinati casualmente. Una variante prevede un abbinamento iniziale basato sulla classifica del torneo (comunque nella prima prova, in cui la classifica è assente, l'abbinamento è casuale). Un'altra variante prevede che l'abbinamento iniziale sia basato sulla classifica del _Fargo rating_ o del _Elo rating_.
Amalfi abbina ad ogni turno i giocatori partendo dalla classifica precedente e saltando un numero di posizioni pari ai turni che mancano alla fine.  


## Match

Un **match** è una parte di una prova. È formato da uno o più **set**.
Il **match** ha una regola di inizio che può essere "primo giocatore" oppure "acchitto". Si gioca con "break continuo" o "break alternato". Entrambi questi valori hanno un default che dipende da quello che è impostato nella prova a cui appartiene il match. 
Il **match** ha una distanza (numero di **set** necessari per vincere un match). Di solito il set è uno solo e quindi si definisce la distanza come numero di rack necessari per vincere, ma possono essere anche più set e in questo caso vince il match il giocatore che vince per primo il numero di set prefissato (la distanza del match).  La distanza di default viene definito dalla prova a cui appartiene il match.
La distanza del **set** è il numero di **rack** che devono essere vinti per aggiudicarsi il set. La distanza può essere "al meglio di" oppure "esatto numero". Nel primo caso vince il giocatore che per primo vince un numero di triangoli (rack) pari alla distanza del set. Nel secondo caso, possibile solo se la distanza è dispari, si giocano un numero di rack pari alla distanza e si aggiudica il set il giocatore che ha vinto più rack. Il valore di default per la distanza dei set sia il fatto che siano o meno "al meglio di" viene dalla prova a cui appartiene il match.
Di solito la disciplina dei rack che compongono un set è la stessa, ma una variante prevede che la distanza sia da coprire con più discipline diverse. Ad esempio vince chi arriva prima a 7, ma i primi 5 rack sono a palla 8 e gli altri a palla 9.

Un **match** può essere con handicap o no. Se c'è l'handicap allora dipende dalla differenza di categoria dei giocatori o dalla differenza di rating (fargo o elo) dei giocatori. Un esempio di handicap può essere questo: se un giocatore di categoria A è abbinato con uno di categoria C, parte da -2, se è abbinato con uno di categoria B parte da -1 come pure un giocatore di categoria B abbinato con uno di C.

La app permette anche agli utenti ``player`` di organizzare **match _standalone_** con un altro utente.
I match standalone di solito sono privati e quindi gli uid dei giocatori vengono anonimizzati per tutti gli altri che non siano i giocatori stessi. Gli pseudonimi mostrati sono sempre ``player1`` e ``player2``. Inoltre le statistiche dei match standalone non compaiono nel profilo dell'utente per tutti quelli che accedono e non sono l'utente stesso. 
Un utente può decidere di rendere pubblico un suo match standalone e in quel caso il suo uid non viene nascosto (quello dell'altro rimane anonimizzato a meno che anche l'altro non decida per suo conto di rendere pubblico il match) e il match compare nelle statistiche individuali dell'utente. 

## Rack

Un **rack** è relativo ad una disciplina come, ad esempio, "palla 8", "palla 9", "palla 10", "pool continuo", "one pocket". Il valore di default della disciplina viene dal set, che a sua volta prende il valore di default del match, che lo prende da turno, che lo prende come valore di default da prova.

## Classifica

Una **classifica** può essere collegata ad un turno, una **prova** o ad un **torneo**.

## Playoff

I **playoff** sono una **prova** speciale a cui per iscriversi occorre avere alcune caratteristiche. Ad esempio un torneo può definire un playoff per i primi 6 classificati. Oppure un playoff Elite per i primi 6 e Academy per i secondi 6. Oppure, ancora, un playoff solo per i giocatori dal terzo posto in giù che hanno partecipato ad almeno 5 prove del torneo.
Alla fine del torneo i giocatori che soddisfano i criteri del playoff ricevono una notifica di accesso ai playoff e possono iscriversi o rifiutare. Nei playoff con un numero limitato di partecipanti (ad esempio i primi 6), se un giocatore rifiuta, la notifica passa al primo degli esclusi e così via fino a quando un numero di giocatori pari ai posti disponibili ha dato l'ok oppure sono finiti i giocatori. 

## Challenge (to do)

Una **challenge** è una prova di abilità che un giocatore può affrontare da solo. Consiste in una immagine, che mostra la disposizione delle biglie sul tavolo e un testo di spiegazione. È identificata da un nome. 
Ha un punteggio minimo e massimo oppure un superato/non superato. 
I risultati delle **challenge** compaiono nelle statistiche individuali dei giocatori.  
``admin`` può vedere le statistiche delle **challenge** (numero di giocatori che hanno tentato, numero di tentativi, punteggio medio, numero di giocatori con punteggio massimo, punteggio mediano)
Un giocatore può scegliere una **challenge** da un elenco generale o da quelle che ha già provato o dalle sue preferite.
Un giocatore può aggiungere/togliere una **challenge** dalle sue preferite.

Un utente ``director`` può aggiungere una o più challenge ad una prova, al posto di un turno o come meccanismo per definire gli spareggi in classifica. Ad esempio potrebbe organizzare una prova standalone con strategia di abbinamento casuale, policy X con trii, distanza un set al 5 esatto, il primo turno a palla 9, il secondo turno composto da due challenge, il terzo e quarto turno a palla 8. La classifica finale della prova è data dalla somma di rack vinti nei turni 1, 3 e 4 e lo spareggio viene fatto con una challege spot shot solo per le prime tre posizioni. Le challenge del secondo turno danno una seconda classifica separata e gli spareggi avvengono tramite un match di un solo rack a palla 10. 

## Esame (to do)

Un **esame** è formato da più **challenge** e una griglia di valutazione che associa i punteggi ottenuti a i livelli per l'esame.
Un utente ``director`` o ``admin`` può creare un **esame**.
Gli esami compaiono nelle statitiche di ``admin`` e dell'utente ``director`` che l'ha creato.

## Statistica

Una statistica raccoglie i kpi di successo per un determinato oggetto. Le statistiche permettono di accedere alle serie storiche. 

### statistiche di torneo per admin/director

Una statistica di torneo rivolta ad utente `admin` o `director` riporta in numero di prove totali, il numero di iscritti unici che hanno giocato almeno una prova, il numero di match e di rack giocati, il totale quote versate. 

## Casi d'uso

### Utente guest

#### Registrazione

L'utente si registra scegliendo uno username (case sensitive, unico), email, telefono (opzionale), password

#### Login

Inserisce userid e password del proprio account. 

#### Vista complessiva

Dalla home accede alla lista dei tornei e delle prove standalone con informazioni generali e relative classifiche.

#### Vista torneo

Scegliendo un torneo può vedere le prove giocate e le informazioni sulle prove future con informazioni e relative classifiche.

#### Vista prova

Scegliendo una prova può vedere l'elenco dei giocatori iscritti (username), i turni passati, le classifiche di turno, i risultati dei match finiti, gli eventuali accoppiamenti del turno successivo, i risultati dei match in tempo reale. 

### Utente player

#### Cancellazione {#soft-delete-player}

Soft delete con pseudonimizzazione. Vengono cancellati i dati dell'anagrafica e l'utente non può più loggarsi. Vengono mantenute le partite già giocate. 
Il vecchio userid viene mostrato solo nelle statistiche personali degli utenti `player` che hanno giocato con lui. 
Nella vista relativa alle vecchie prove e vecchi tornei, viene mostrato solo lo pseudonimo.
Le iscrizioni a nuove prove che non sono ancora iniziate vengono cancellate. Se la prova è iniziata, la cancellazione viene gestita come se fosse un forfait.

#### Dashboard 

La home mostra le attività in corso: tornei in corso, prove standalone in corso, match singoli programmati, proposte di match da parte di altri utenti.

##### Vista Torneo

#### Profilo

L'utente ha la possiblità di rendersi disponibile a giocare match standalone in una o più sale biliardo. Nell'elenco di tutte le sale disponibili imposta per quali vuole gli vengano mostrate le opportunità di match standalone.
L'utente può modificare il suo profilo.
L'utente può cancellare il suo profilo. In questo caso viene operato un soft delete con pseudonimizzazione ([vedi sezione Cancellazione](soft-delete-player))

#### Proposta di match standalone

##### Proposta con invito per match standalone

Dal profilo utente, invia una proposta di match. Definisce il luogo, data/ora, uno o più giocatori selezionati tra i giocatori "_amici_" o quelli con cui l'utente ha già giocato in passato, una data/ora di scadenza della proposta. 
I giocatori che hanno ricevuto la proposta di match ricevono una notifica via app. La proposta viene mostrata nella dashboard e nel profilo.
Se un giocatore rifiuta la proposta prima della scadenza, vinee inviata una notifida all'utente che ha inviato la proposta.
Se un giocatore accetta la proposta prima della scadenza, viene inviata una notifica all'utente che ha inviato la proposta, tutte le notifiche inviate agli altri giocatori che non hanno risposto vengono cancellate. I due giocatori, quello che ha inviato la proposta e quello che ha accettato vedono il match nella loro dashboard.
Allo scadere della poposta, tutte le notifiche inviate ai giocatori che ancora non hanno risposto vengono cancellate e al proponente viene notificato che la proposta è scaduta e nessuno ha accettato.

##### Proposta aperta di match standalone

Dal profilo utente, invia una proposta di match aperta a tutti. Definisce il luogo, data/ora e una scadenza. 
Tutti i giocatori che hanno già giocato almeno una volta in quel luogo e quelli che hanno impostato nel loro profilo la disponibilità a giocare in quel luogo, ricevono la notifica e vedono la proposta nella dashboard. 
Se un giocatore accetta entro la scadenza, il proponente viene notificato e il match compare nella dashboard di entrambi. La proposta e le notifiche spariscono dalle dashboard di tutti gli altri.
Allo scadere della proposta, tutte le notifiche inviate ai giocatori che ancora non hanno risposto vengono cancellate e al proponente viene notificato che la proposta è scaduta e nessuno ha accettato.

#### Richiesta di diventare director

L'utente player può chiedere di diventare `director` tramite il menù di login/logout e tramite la sua pagina di profilo. 

### Utente director

#### Creazione di un nuovo torneo

Per creare un nuovo torneo l'utente definisce il nome, la strategia di abbinamento (che corrisponde al tipo di torneo) e se sono previsti playoff oppure no. 
Il torneo ha una descrizione opzionale. 

##### Creazione di una nuova prova all'interno di un torneo

Creare una nuova prova significa definire:
- il numero di prova, 
- il nome (opzionale), 
- la data e l'ora in cui inizierà la prova, 
- il luogo presso cui si svolgerà
- il numero minimo e massimo di iscritti (opzionali)
- la quota di partecipazione
- il numeo di turni
- la strategia di abbinamento (per default quella del torneo)
- una descrizione opzionale
- la disciplina di default per i turni
- la distanza di default per i turni

Quando un utente crea una nuova prova in un torneo, tutti i valori vengono precompilati. Ad esempio il numero di prova è incrementale, la data viene precompilata con quella di oggi per la prima prova o con quella di una settimana più avanti rispetto all'ultima prova aggiunta al torneo, gli altri valori vengono precompilati con i valori delle prove precedenti o con valori di default per la prima prova. 

#### Visualizza le statistiche di un proprio torneo

L'utente può visualizzare le statistiche del torneo e navigare all'interno delle statistiche. Ad esempio dal valore del numero di prove totali può cliccare e vedere l'elenco delle singole prove e accedere alle relative statistiche. Oppure dal numero di iscritti unici che hanno partecipato almeno ad una prova del torneo può vedere l'elenco e accedere alle loro statistiche pubbliche o relative ai suoi tornei e prove standalone. 

## Scelte architetturali

### Privacy

Le informazioni dell'anagrafica dell'utente sono salvate cifrate.
La chiave di cifratura è nella configurazione lato server.