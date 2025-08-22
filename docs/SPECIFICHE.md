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
``admin`` o un utente ``director`` creano, modificano e cancellano un **torneo**. Non sempre le modifiche e le cancellazioni sono possibili: ad esempio, se una **prova** è intinere (i giocatori stanno giocando le partire della **prova**) allora non è possibile modificarla. 
Nel caso di cancellazione di un **torneo** con alcune **prove** già giocate, si opera un _soft delete_ e i **match** giocati vengono mantenuti per le **statistiche** personali dei vari **player**.
Un **torneo** può avere 0 o più direttori di gara. Se ne ha zero allora viene gestito dall'``admin``. 

## Prove

Una **prova** è parte di un **torneo**. È formata da uno o più **turni**. Durante un **turno** i giocatori vengono abbinati e giocano un **match** sulla base del risultato del **match** si ottiene una **classifica** di **turno**.
La app permette anche ad ``admin`` o un utente ``director`` di organizzare **prove _standalone_**. Una **prova _standalone_** è una **prova** non collegata ad un **torneo**. Una **prova _standalone_** può avere zero o più direttori di gara. Se non ha direttori di gara allora viene gestita da ``admin``. 
I **player** si iscrivono/disiscrivono alle **prove**, quando le iscrizioni sono aperte. ``admin`` o un utente ``director`` apre le iscrizioni definendo data di inizio e fine. La fine delle iscrizioni deve essere antecendente alla data e ora di inizio della prova. 
Una **prova** si svolge in una **sala biliardi** con una data e ora di inizio. 
La **prova** è relativa ad una disciplina come, ad esempio, "palla 8", "palla 9", "palla 10". Si gioca con "break continuo" o "break alternato", con acchitto sì/no per decidere chi inizia (se acchitto no allora inizia il primo giocatore). La prova ha un numero minimo e massimo di iscritti (opzionali), una quota di iscrizione in euro, una distanza (numero di rack necessari per vincere un match). 
La distanza può essere "al meglio di" oppure "esatto numero". Nel primo caso vince il giocatore che per primo vince un numero di triangoli pari alla distanza. Nel secondo caso, possibile solo se la distanza è dispari, si giocano un numero di rack pari alla distanza e vince il match il giocatore che ha vinto più rack.
La distanza può anche essere composta di set. In questo caso vince il match il giocatore che vince per primo il numero di set prefissato. Ogni set viene vinto dal giocatore che vince il numero di rack prefissato (ad esempio 2 set da 5 rack).
Una variante prevede che la distanza sia da coprire con due discipline diverse. Ad esempio vince chi arriva prima a 7, ma i primi 5 rack sono a palla 8 e gli altri a palla 9.  

### Turno

Un turno è legato ad una prova. È dato da un abbinamento di giocatori che giocano contemporanemente un match di tipo uguale (non è possibile, ad esempio, che in un turno due giocatori giochino a palla 9 e altri tue a palla 8, oppure che due giochino al meglio di 5 e altri al meglio di 7; tutti i match hanno le stesse caratteristiche).
Una volta che tutti i match del turno sono terminati, è possibile modificare la classifica della prova. Quindi un turno prende la classifica precedente al turno, i risultati dei match e restituisce la classifica aggiornata.

### Prove amalfi

Una prova **amalfi** è una prova in cui non c'è eliminazione e tutti i giocatori giocano lo stesso numero di turni.
Inizialmente gli iscritti vengono abbinati casualmente. Una variante prevede un abbinamento iniziale basato sulla classifica del torneo (comunque nella prima prova, in cui la classifica è assente, l'abbinamento è casuale). Un'altra variante prevede che l'abbinamento iniziale sia basato sulla classifica del _Fargo rating_ o del _Elo rating_.
Amalfi abbina ad ogni turno i giocatori partendo dalla classifica precedente e saltando un numero di posizioni pari ai turni che mancano alla fine.  


## Match

Un **match** è una parte di una prova. È formato da uno o più **rack**.
La app permette anche agli utenti ``player`` di organizzare **match _standalone_** con un altro utente.

### Classifica

Una **classifica** può essere collegata ad un turno, una **prova** o ad un **torneo**.

### Playoff

I **playoff** sono una **prova** speciale a cui per iscriversi occorre avere alcune caratteristiche. Ad esempio un torneo può definire un playoff per i primi 6 classificati. Oppure un playoff Elite per i primi 6 e Academy per i secondi 6. Oppure, ancora, un playoff solo per i giocatori dal terzo posto in giù che hanno partecipato ad almeno 5 prove del torneo.
Alla fine del torneo i giocatori che soddisfano i criteri del playoff ricevono una notifica di accesso ai playoff e possono iscriversi o rifiutare. Nei playoff con un numero limitato di partecipanti (ad esempio i primi 6), se un giocatore rifiuta, la notifica passa al primo degli esclusi e così via fino a quando un numero di giocatori pari ai posti disponibili ha dato l'ok oppure sono finiti i giocatori. 

### Challenge (to do)

Una **challenge** è una prova di abilità che un giocatore può affrontare da solo. Consiste in una immagine, che mostra la disposizione delle biglie sul tavolo e un testo di spiegazione. È identificata da un nome. 
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

Dalla home accede alla lista dei tornei e delle prove standalone con informazioni generali e relative classifiche.

#### Vista torneo

Scegliendo un torneo può vedere le prove giocate e le informazioni sulle prove future con informazioni e relative classifiche.

#### Vista prova

Scegliendo una prova può vedere l'elenco dei giocatori iscritti (username), i turni passati, le classifiche di turno, i risultati dei match finiti, gli eventuali accoppiamenti del turno successivo, i risultati dei match in tempo reale. 

### Utente player

#### Cancellazione

Soft delete con pseudonimizzazione. Vengono cancellati i dati dell'anagrafica e l'utente non può più loggarsi. Vengono mantenute le partite già giocate. 
Il vecchio userid viene mostrato solo nelle statistiche personali degli utenti `player` che hanno giocato con lui. 
Nella vista relativa alle vecchie prove e vecchi tornei, viene mostrato solo lo pseudonimo.
Le iscrizioni a nuove prove che non sono ancora iniziate vengono cancellate. Se la prova è iniziata, la cancellazione viene gestita come se fosse un forfait.

#### Dashboard 

La home mostra le attività in corso: tornei in corso, prove standalone in corso, match singoli programmati, proposte di match da parte di altri utenti.

##### Vista Torneo

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

## Scelte architetturali

### Privacy

Le informazioni dell'anagrafica dell'utente sono salvate cifrate.
La chiave di cifratura è nella configurazione lato server.