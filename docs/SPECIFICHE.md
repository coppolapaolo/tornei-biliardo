# Web App Campionati Biliardo

L'app permette di organizzare Campionati di Biliardo, ma è anche una community che permette ai giocatori di incontrarsi e giocare e mantenere le statistiche di gioco. 

## Tipologie di utenti

La app ha un unico **Admin** configurato nelle impostazioni lato server. Admin non può essere cancellato e non può cambiare la password. L'email di ``admin`` è configurata, come la password nelle impostazioni lato server. 

Ci sono tre tipologie di utenti:
1. **guest**: l'utente visitatore non loggato
2. **player**: l'utente registrato che può iscriversi ai campionati e alle gare e giocare
3. **director**: il player che ha chiesto e ottenuto di poter diventare direttore di gara. Mantiene tutte le funzionalità del player, ma assume i poteri di ``admin`` limitatamente alla gestione di campionati e di gare create da lui o in cui è nominato _co-direttore_

## Campionati

La app permette di organizzare campionati. ``admin`` o un utente ``director`` possono creare nuovi campionati. Un **campionato** è una collezione di ``n`` **gare**, con una **classifica** complessiva. 
Un **campionato** può avere anche dei **playoff** che possono essere giocati alla fine del **campionato** (dopo che si è conclusa l'ultima **gara** del campionato). La logica dei **playoff** può essere di tipo diverso e viene impostata da ``admin`` o da un utente ``director``. 
``admin`` o un utente ``director`` creano, modificano e cancellano un **campionato**. Non sempre le modifiche e le cancellazioni sono possibili: ad esempio, se una **gara** è in itinere (i giocatori stanno giocando le partire della **gara**) allora non è possibile modificarla. 
Nel caso di cancellazione di un **campionato** con alcune **gare** già giocate, si opera un _soft delete_ e i **match** giocati vengono mantenuti per le **statistiche** personali dei vari **player**.
Un **campionato** può avere 0 o più direttori di gara. Se ne ha zero allora viene gestito dall'``admin``. 

## Gare

Una **gara** è parte di un **campionato**. È formata da uno o più **turni** e da zero o più **challenge**. Il numero di turni e di challenge di default dipende dal toreno a cui appartiene la gara. 
Durante un **turno** i giocatori vengono abbinati e giocano un **match** sulla base del risultato del **match** si ottiene una **classifica** di **turno**. 
La app permette anche ad ``admin`` o un utente ``director`` di organizzare **gare _standalone_**. Una **gara _standalone_** è una **gara** non collegata ad un **campionato**. Una **gara _standalone_** può avere zero o più direttori di gara. Se non ha direttori di gara allora viene gestita da ``admin``. 
I **player** si iscrivono/disiscrivono alle **gare**, quando le iscrizioni sono aperte. ``admin`` o un utente ``director`` apre le iscrizioni definendo data di inizio e fine. La fine delle iscrizioni deve essere antecendente alla data e ora di inizio della gara. 
Una **gara** si svolge in una **sala biliardi** con una data e ora di inizio. 
La **gara** ha un numero minimo e massimo di iscritti (opzionali) e una quota di iscrizione in euro.
Una **gara** con un masssimo di iscritti ha anche una **lista di attesa**. I giocatori che si iscrivono alla **gara** dopo che il massimo numero è stato raggiunto vengono messi in coda. Se uno degli iscritti si disiscrive, viene iscritto il primo della lista d'attesa e gli viene inviata una notifica. 
Una gara ha una **strategia di abbinamento** tra turni, una policy per definire l'abbinamento del primo turno (ad esempio casuale oppure sulla base della classifica) e una policy per la gestione del numero dispari di giocatori (con X o con trii). Tutti questi valori hanno un default che dipende dal campionato a cui appartiene la gara.
Una gara ha una **classifica** finale con un eventuale meccanismo per definire gli spareggi. Ad esempio una gara potrebbe definire gli spareggi solo per le prime tre posizioni con uno "_spot shot rally_": se nelle prime tre posizioni ci sono 2 o più giocatori pari merito, allora si affrontano in una **challenge** di tipo spot shot. Un altro tipo di spareggio potrebbe essere un match con un solo rack. 
Ua **gara** ha una **policy per il forfait** il cui valore di default è definito dal campionato. La policy definisce come trattare un giocatore che ha dichiarato forfait negli abbinamenti e nei match successivi. La policy può essere _exclude_ e in questo caso il giocatore viene eliminato dagli abbinamenti (ma non dalla classifica), oppure _forfait_ e quindi il giocatore rimane negli abbinamenti e fa vincere per forfait i giocatori che capitano con lui.

### Turno

Un turno è legato ad una gara. È dato da un abbinamento di giocatori che giocano contemporanemente un match di tipo uguale (non è possibile, ad esempio, che in un turno due giocatori giochino a palla 9 e altri tue a palla 8, oppure che due giochino al meglio di 5 e altri al meglio di 7; tutti i match hanno le stesse caratteristiche. L'unica eccezione sono i match a tre, nella strategia di abbinamento casuale con classifiche basate sulla differenza di rack, descritti più avanti).
Una possibile **strategia di abbinamento** è **_amalfi_**. Un'altra possibile strategia di abbinamento è _round robin_. 
Una volta che tutti i match del turno sono terminati, è possibile modificare la classifica della gara. Quindi un turno prende la classifica precedente al turno, i risultati dei match e restituisce la classifica aggiornata.

#### Strategia di abbinamento

Una **strategia di abbinamento** abbina un elenco di giocatori in match. 

Ad esempio la **strategia di abbinamento _amalfi_** dipende da quanti turni mancano alla fine della gara e, dato un elenco ordinato di giocatori, abbina il giocatore `n`-esimo con il giocatore `n+i`-esimo con i pari al numero di turni che mancano da giocare per terminare la gara. 
_Amalfi_ evita che due giocatori si incontrino più di una volta, quindi se l'abbinamento derivante dalla logica generale `(n, n+i)` è stato già giocato in un turno precedente, allora scorre l'elenco in modo ciclico fino a trovare un giocatore `(n+i+j)%lunghezza_elenco` con cui il giocatore `n` non ha già giocato.

Una **strategia di abbinamento per _eliminazione diretta_**, invece, abbina tra loro i vincitori del turno precedente.

Una **sttategia di abbinamento per _doppio ko_** abbina tra loro i vincitori e ripesca una sola volta i perdenti.

La **strategia di abbinamento _casuale_** abbina a caso i giocatori assicurandosi solo che non ci sia mai lo stesso abbinamento più di una volta in turni diversi della stessa gara. Questo tipo di strategia può calcolare tutti gli abbinamenti subito e non ha bisogno di aspettare la conclusione dei match per l'abbinamento successivo.

Una strategia di abbinamento è associata anche ad una **strategia per il _primo abbinamento_** che può essere _casuale_ (in questo caso limitata al primo turno) oppure _basato su classifica_ oppure _basato su rating_ (fargo o elo).

Una strategia di abbinamento è associata anche ad una **policy per la X** che decide come trattare il caso in cui ci siano meno giocatori rispetto a quelli necessari. 
Ad esempio la strategia di _eliminazione diretta_ seleziona casualmente il numero di giocatori che eccede la potenza del 2 più alta e li fa passare tutti automaticamente al secondo turno (perché li abbina alla X e vincono atuomaticamente). 
La strategia di abbinamento _amalfi_ con classifiche basate su (match vinti, differenza rack vinti-persi) nel caso in cui i giocatori siano dispari abbina un giocatore alla X assegnando il match vinto, ma con zero differenza punti. In questo modo chi ottiene la X con l'abbinamento ottiene in classifica un posizionamento migliore di tuttii perdenti e peggiore di tutti i vincenti. 
Una variante, sempre per _amalfi_ consiste nel gestire la X con una challenge che possa dare un punteggio da zero alla massima differenza rack raggiungibile in quella gara. In questo modo il giocatore abbinato con la X, invece di stare fermo il turno, gioca la challenge e in classifica ottiene il match vinto e un differenza rack pari al punteggio nella challenge. 

Se la **strategia di abbinamento _casuale_** è abbinata a classifiche basate solo sulla differenza rack, allora in caso di numero dispari di giocatori è possible evitare la X e gesitre il numero dispari aggiungendo alle coppie di giocatori un trio. 
I giocatori nel trio giocano uno o più mini gironi all'italiana (round robin) in cui tutti giocano con gli altri un solo rack. Il punteggi che ottengono alla fine del trio è pari a 1+numero di rack vinti. Questo abbinamento à possibile solo per le distanze da 3 a 7 con il seguente schema:
| Distanza | mini gironi | rack giocati da ogni giocatore | rack totali | punteggio |
| --- | --- | ---| ---| --- |
| 3 | 1 | 2 | 3 | 1 + rack vinti |
| 4 | 2 | 4 | 6 | rack vinti |
| 5 | 2 | 4 | 6 | 1 + rack vinti |
| 6 | 3 | 6 | 9 | rack vinti |
| 7 | 3 | 6 | 9 | 1 + rack vinti |

Per la distanza oltre al 7 i rack totali da giocare diventano troppi rispetto a quelli che giocano le coppie e quindi il trio allungherebbe troppo i tempi della gara. Per questo motivo la app limita la possibilità di scegliere questa opzione solo fino a distanza 7.
### Gare amalfi

Una gara **amalfi** è una gara in cui non c'è eliminazione e tutti i giocatori giocano lo stesso numero di turni.
Inizialmente gli iscritti vengono abbinati casualmente. Una variante prevede un abbinamento iniziale basato sulla classifica del campionato (comunque nella prima gara, in cui la classifica è assente, l'abbinamento è casuale). Un'altra variante prevede che l'abbinamento iniziale sia basato sulla classifica del _Fargo rating_ o del _Elo rating_.
Amalfi abbina ad ogni turno i giocatori partendo dalla classifica precedente e saltando un numero di posizioni pari ai turni che mancano alla fine.  


## Match

Un **match** è una parte di una gara. È formato da uno o più **set**.
Il **match** ha una regola di inizio che può essere "primo giocatore" oppure "acchitto". Si gioca con "break continuo" o "break alternato". Entrambi questi valori hanno un default che dipende da quello che è impostato nella gara a cui appartiene il match. 
Il **match** ha una distanza (numero di **set** necessari per vincere un match). Di solito il set è uno solo e quindi si definisce la distanza come numero di rack necessari per vincere, ma possono essere anche più set e in questo caso vince il match il giocatore che vince per primo il numero di set prefissato (la distanza del match).  La distanza di default viene definito dalla gara a cui appartiene il match.
La distanza del **set** è il numero di **rack** che devono essere vinti per aggiudicarsi il set. La distanza può essere "al meglio di" oppure "esatto numero". Nel primo caso vince il giocatore che per primo vince un numero di triangoli (rack) pari alla distanza del set. Nel secondo caso, possibile solo se la distanza è dispari, si giocano un numero di rack pari alla distanza e si aggiudica il set il giocatore che ha vinto più rack. Il valore di default per la distanza dei set sia il fatto che siano o meno "al meglio di" viene dalla gara a cui appartiene il match.
Di solito la disciplina dei rack che compongono un set è la stessa, ma una variante prevede che la distanza sia da coprire con più discipline diverse. Ad esempio vince chi arriva prima a 7, ma i primi 5 rack sono a palla 8 e gli altri a palla 9.
Un'altra variante, che si accompagna al break continuo per il set (il giocatore che vince il rack è lo stesso che apre il successivo), prevede che chi spacca decide la disciplina tra un predeterminato insieme di discipline possibili (ad esempio un match al 5, break continuo, scelta tra palla 8 o palla 9).

Un **match** può essere con handicap o no. Se c'è l'handicap allora dipende dalla differenza di categoria dei giocatori o dalla differenza di rating (fargo o elo) dei giocatori. Un esempio di handicap può essere questo: se un giocatore di categoria A è abbinato con uno di categoria C, parte da -2, se è abbinato con uno di categoria B parte da -1 come pure un giocatore di categoria B abbinato con uno di C.

La app permette anche agli utenti ``player`` di organizzare **match _standalone_** con un altro utente.

## Rack

Un **rack** è relativo ad una disciplina come, ad esempio, "palla 8", "palla 9", "palla 10", "pool continuo", "one pocket". Il valore di default della disciplina viene dal set, che a sua volta prende il valore di default del match, che lo prende da turno, che lo prende come valore di default da gara.

### Classifica

Una **classifica** può essere collegata ad un turno, una **gara** o ad un **campionato**.

### Playoff

I **playoff** sono una **gara** speciale a cui per iscriversi occorre avere alcune caratteristiche. Ad esempio un campionato può definire un playoff per i primi 6 classificati. Oppure un playoff Elite per i primi 6 e Academy per i secondi 6. Oppure, ancora, un playoff solo per i giocatori dal terzo posto in giù che hanno partecipato ad almeno 5 gare del campionato.
Alla fine del campionato i giocatori che soddisfano i criteri del playoff ricevono una notifica di accesso ai playoff e possono iscriversi o rifiutare. Nei playoff con un numero limitato di partecipanti (ad esempio i primi 6), se un giocatore rifiuta, la notifica passa al primo degli esclusi e così via fino a quando un numero di giocatori pari ai posti disponibili ha dato l'ok oppure sono finiti i giocatori. 

### Challenge (to do)

Una **challenge** è una gara di abilità che un giocatore può affrontare da solo. Consiste in una immagine, che mostra la disposizione delle biglie sul tavolo e un testo di spiegazione. È identificata da un nome. 
Ha un punteggio minimo e massimo oppure un superato/non superato. 
I risultati delle **challenge** compaiono nelle statistiche individuali dei giocatori.  
``admin`` può vedere le statistiche delle **challenge** (numero di giocatori che hanno tentato, numero di tentativi, punteggio medio, numero di giocatori con punteggio massimo, punteggio mediano)
Un giocatore può scegliere una **challenge** da un elenco generale o da quelle che ha già provato o dalle sue preferite.
Un giocatore può aggiungere/togliere una **challenge** dalle sue preferite.

### Esame (to do)

Un **esame** è formato da più **challenge** e una griglia di valutazione che associa i punteggi ottenuti a i livelli per l'esame.
Un utente ``director`` o ``admin`` può creare un **esame**.
Gli esami compaiono nelle statitiche di ``admin`` e dell'utente ``director`` che l'ha creato.

## Casi d'uso

### Utente guest

#### Registrazione

L'utente si registra scegliendo uno username (case sensitive, unico), email, telefono (opzionale), password

#### Login

Inserisce userid e password del proprio account. 

#### Vista complessiva

Dalla home accede alla lista dei campionati e delle gare standalone con informazioni generali e relative classifiche.

#### Vista campionato

Scegliendo un campionato può vedere le gare giocate e le informazioni sulle gare future con informazioni e relative classifiche.

#### Vista gara

Scegliendo una gara può vedere l'elenco dei giocatori iscritti (username), i turni passati, le classifiche di turno, i risultati dei match finiti, gli eventuali accoppiamenti del turno successivo, i risultati dei match in tempo reale. 

### Utente player

#### Cancellazione

Soft delete con pseudonimizzazione. Vengono cancellati i dati dell'anagrafica e l'utente non può più loggarsi. Vengono mantenute le partite già giocate. 
Il vecchio userid viene mostrato solo nelle statistiche personali degli utenti `player` che hanno giocato con lui. 
Nella vista relativa alle vecchie gare e vecchi campionati, viene mostrato solo lo pseudonimo.
Le iscrizioni a nuove gare che non sono ancora iniziate vengono cancellate. Se la gara è iniziata, la cancellazione viene gestita come se fosse un forfait.

#### Dashboard 

La home mostra le attività in corso: campionati in corso, gare standalone in corso, match singoli programmati, proposte di match da parte di altri utenti.

##### Vista Campionato

#### Profilo

L'utente ha la possiblità di rendersi disponibile a giocare match individuali in una o più sale biliardo. Nell'elenco di tutte le sale disponibili imposta per quali vuole gli vengano mostrate le opportunità di match individuali.

#### Proposta di match

##### Proposta con invito per match individuale

Dal profilo utente, invia una proposta di match. Definisce il luogo, data/ora, uno o più giocatori selezionati tra i giocatori "_amici_" o quelli con cui l'utente ha già giocato in passato, una data/ora di scadenza della proposta. 
I giocatori che hanno ricevuto la proposta di match ricevono una notifica via app. La proposta viene mostrata nella dashboard e nel profilo.
Se un giocatore rifiuta la proposta prima della scadenza, vinee inviata una notifida all'utente che ha inviato la proposta.
Se un giocatore accetta la proposta prima della scadenza, viene inviata una notifica all'utente che ha inviato la proposta, tutte le notifiche inviate agli altri giocatori che non hanno risposto vengono cancellate. I due giocatori, quello che ha inviato la proposta e quello che ha accettato vedono il match nella loro dashboard.
Allo scadere della poposta, tutte le notifiche inviate ai giocatori che ancora non hanno risposto vengono cancellate e al proponente viene notificato che la proposta è scaduta e nessuno ha accettato.

##### Proposta aperta di match individuale

Dal profilo utente, invia una proposta di match aperta a tutti. Definisce il luogo, data/ora e una scadenza. 
Tutti i giocatori che hanno già giocato almeno una volta in quel luogo e quelli che hanno impostato nel loro profilo la disponibilità a giocare in quel luogo, ricevono la notifica e vedono la proposta nella dashboard. 
Se un giocatore accetta entro la scadenza, il proponente viene notificato e il match compare nella dashboard di entrambi. La proposta e le notifiche spariscono dalle dashboard di tutti gli altri.
Allo scadere della proposta, tutte le notifiche inviate ai giocatori che ancora non hanno risposto vengono cancellate e al proponente viene notificato che la proposta è scaduta e nessuno ha accettato.

### Utente director

#### Creazione di un nuovo campionato

Per creare un nuovo campionato l'utente definisce il nome, la strategia di abbinamento (che corrisponde al tipo di campionato) e se sono previsti playoff oppure no. 
Il campionato ha una descrizione opzionale. 

##### Creazione di una nuova gara all'interno di un campionato

Creare una nuova gara significa definire:
- il numero di gara, 
- il nome (opzionale), 
- la data e l'ora in cui inizierà la gara, 
- il luogo presso cui si svolgerà
- il numero minimo e massimo di iscritti (opzionali)
- la quota di partecipazione
- il numeo di turni
- la strategia di abbinamento (per default quella del campionato)
- una descrizione opzionale
- la disciplina di default per i turni
- la distanza di default per i turni

Quando un utente crea una nuova gara in un campionato, tutti i valori vengono precompilati. Ad esempio il numero di gara è incrementale, la data viene precompilata con quella di oggi per la prima gara o con quella di una settimana più avanti rispetto all'ultima gara aggiunta al campionato, gli altri valori vengono precompilati con i valori delle gare precedenti o con valori di default per la prima gara. 

## Scelte architetturali

### Privacy

Le informazioni dell'anagrafica dell'utente sono salvate cifrate.
La chiave di cifratura è nella configurazione lato server.