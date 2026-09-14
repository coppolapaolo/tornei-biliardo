# Web App Campionati Biliardo

L'app permette di organizzare Campionati di Biliardo, ma è anche una community che permette ai giocatori di incontrarsi e giocare e mantenere le statistiche di gioco. 

## Tipologie di utenti

La app ha un unico **Admin** configurato nelle impostazioni lato server. Admin non può essere cancellato e non può cambiare la password. L'email di ``admin`` è configurata, come la password nelle impostazioni lato server. **L'utente admin è un utente speciale di sistema e non appare nella lista utenti dell'interfaccia di gestione**, che è dedicata alla gestione dei membri della community (player e director).

Ci sono tre tipologie di utenti:
1. **guest**: l'utente visitatore non loggato
2. **player**: l'utente registrato che può iscriversi ai campionati e alle gare e giocare
3. **director**: il player che ha chiesto e ottenuto di poter diventare direttore di gara. Mantiene tutte le funzionalità del player, ma assume i poteri di ``admin`` limitatamente alla gestione di campionati e di gare create da lui o in cui è nominato _co-direttore_

## Campionati

La app permette di organizzare campionati. ``admin`` o un utente ``director`` possono creare nuovi campionati. Un **campionato** è una collezione di ``n`` **gare**, con una **classifica** complessiva. 
Un **campionato** può avere anche dei **playoff** che possono essere giocati alla fine del **campionato** (dopo che si è conclusa l'ultima **gara** del campionato). La logica dei **playoff** può essere di tipo diverso e viene impostata da ``admin`` o da un utente ``director``. 

> **Nota (2026-09-14).** Le **gare previste** di un campionato sono quelle della stagione: la gara di playoff **non è una di queste**, è la conclusione. Ogni conteggio mostrato — pagina del direttore, vetrina, tessere, elenchi — conta le gare regolari e aggiunge la finale a parte: «5 gare + finale», «2 di 2 · finale». Una gara è di playoff se è collegata a una configurazione dei playoff, non per il nome. Fino a questa data la finale finiva nel numeratore e la pagina del direttore scriveva «3 di 2».

``admin`` o un utente ``director`` creano, modificano e cancellano un **campionato**. Non sempre le modifiche e le cancellazioni sono possibili: ad esempio, se una **gara** è in itinere (i giocatori stanno giocando le partire della **gara**) allora non è possibile modificarla. 
Nel caso di cancellazione di un **campionato** con alcune **gare** già giocate, si opera un _soft delete_ e i **match** giocati vengono mantenuti per le **statistiche** personali dei vari **player**.
Un **campionato** può avere 0 o più direttori di gara. Se ne ha zero allora viene gestito dall'``admin``. 

### Stati di un campionato

Lo stato di un campionato non è un dato salvato: si **calcola** dalle sue gare e
da `terminated_at`, l'istante in cui il direttore lo chiude consolidando la
classifica generale. Le due domande sono distinte e vanno tenute distinte:
«si può ancora giocare?» e «il direttore ha chiuso?».

| Stato | Etichetta mostrata | Vale quando |
|---|---|---|
| `SETUP` | Setup | non c'è ancora niente di aperto |
| `REGISTRATION_OPEN` | Iscrizioni aperte | almeno una gara raccoglie iscrizioni **adesso**: è nella fase iscrizioni *e* la finestra è aperta |
| `IN_PROGRESS` | In corso | almeno una gara si sta giocando, **oppure** restano gare da creare rispetto a quelle pianificate, **oppure** il campionato è già cominciato (qualche gara conclusa) e ne restano da giocare |
| `AWAITING_CLOSURE` | **In attesa di chiusura** | tutte le gare previste sono finite, ma `terminated_at` è NULL: la classifica generale **non è consolidata** |
| `AWAITING_PLAYOFF` | **In attesa dei playoff** | il direttore ha chiuso, e restano playoff da giocare |
| `COMPLETED` | Completato | non c'è più niente da giocare: nessun playoff previsto, o tutti conclusi |

Cinque regole, e la ragione di ciascuna:

1. **`COMPLETED` è l'unico stato finale.** Fino alla issue #242 copriva anche
   «gare esaurite ma nessuno ha premuto Termina»: due situazioni diverse sotto
   la stessa parola, e chi guardava l'elenco non poteva distinguerle.
2. **Ogni etichetta constata un fatto, nessuna impartisce un ordine.** Il badge
   non lo legge solo il direttore: lo vedono il giocatore iscritto e il
   visitatore anonimo, nella lista pubblica e in homepage. Per questo lo stato
   nuovo si chiama «In attesa di chiusura» e non «Da chiudere», che sarebbe un
   promemoria rivolto a qualcun altro. I due stati non finali dicono **che
   cosa** si sta aspettando, e letti in fila sono una scala:
   *In attesa di chiusura → In attesa dei playoff → Completato*.
3. **`AWAITING_CLOSURE` non è uno stato terminale.** Un campionato che lo porta
   resta fra gli **attivi** nella dashboard del direttore ed è elencato fra
   quelli «in corso» nella lista pubblica. È così che il pulsante «Termina»
   torna sotto gli occhi di chi deve premerlo, invece di finire in archivio.
4. **«Raccoglie iscrizioni» è una domanda sull'orologio, non sulla colonna.**
   `status = INSCRIPTION` dice che la gara è *nella fase* delle iscrizioni;
   quando la finestra si apre lo dicono `inscription_start` e
   `inscription_end`. Fino al 2026-09-04 il campionato guardava la sola colonna
   e la gara la finestra, quindi nella stessa schermata il campionato mostrava
   «Iscrizioni aperte» e le sue due gare «Iscrizioni programmate» — visto in
   produzione. La distinzione la fa già `Gara.get_real_status()`, ed è a lui che
   va chiesta invece di riscriverla una terza volta.
5. **Un campionato cominciato non torna in Setup.** Quando le gare giocate
   stanno alle spalle e la prossima non ha ancora aperto le iscrizioni, nessuna
   delle prime tre righe della tabella si applicava e lo stato cadeva su
   `SETUP`: il campionato sarebbe passato da «Campionati in corso» a «in
   preparazione» a metà stagione. Da qui il terzo ramo di `IN_PROGRESS`,
   aggiunto il 2026-09-04 insieme alla regola 4.

> **Nota storica (2026-08-29).** Lo stato che oggi si chiama `AWAITING_PLAYOFF`
> si chiamava `TERMINATED`, etichetta «Terminato», e significava il contrario di
> quello che sembrava: non «finito», ma «chiuso, con i playoff ancora da
> giocare». In italiano *terminato* suona più definitivo di *completato*, cioè
> l'opposto della semantica del codice, e la pagina del campionato mostrava le
> due parole a pochi pixel di distanza. Il **valore** persistito nelle URL resta
> `terminated`; è cambiato il nome del membro, come già fatto per `MatchStatus`.

## Gare

Una **gara** è parte di un **campionato**. È formata da uno o più **turni** e da zero o più **challenge**. Il numero di turni e di challenge di default dipende dal toreno a cui appartiene la gara. 
Durante un **turno** i giocatori vengono abbinati e giocano un **match** sulla base del risultato del **match** si ottiene una **classifica** di **turno**. 
La app permette anche ad ``admin`` o un utente ``director`` di organizzare **gare _standalone_**. Una **gara _standalone_** è una **gara** non collegata ad un **campionato**. Una **gara _standalone_** può avere zero o più direttori di gara. Se non ha direttori di gara allora viene gestita da ``admin``. 
I **player** si iscrivono/disiscrivono alle **gare**, quando le iscrizioni sono aperte. ``admin`` o un utente ``director`` apre le iscrizioni definendo data di inizio e fine. La fine delle iscrizioni deve essere antecendente alla data e ora di inizio della gara. 
Una **gara** si svolge in una **sala biliardi** con una data e ora di inizio. 
La **gara** ha un numero minimo e massimo di iscritti (opzionali) e una quota di iscrizione in euro.
Una **gara** con un masssimo di iscritti ha anche una **lista di attesa**. I giocatori che si iscrivono alla **gara** dopo che il massimo numero è stato raggiunto vengono messi in coda. Se uno degli iscritti si disiscrive, viene iscritto il primo della lista d'attesa e gli viene inviata una notifica. 
Una gara ha una **strategia di abbinamento** tra turni, una policy per definire l'abbinamento del primo turno (ad esempio casuale oppure sulla base della classifica) e una policy per la gestione del numero dispari di giocatori (NO, Bye, Bye+Challenge, Bye+N rack, o Trio). Tutti questi valori hanno un default che dipende dal campionato a cui appartiene la gara.

Una gara ha un **sistema di classifica** che può essere RACK (rack totali vinti), WINS (match vinti + differenza rack) o POSITION (punti per posizione nel tabellone). Il sistema di classifica determina i vincoli sulle altre opzioni (distanza, multi-set, gestione dispari). Vedi [CLASSIFICATION_SYSTEM.md](CLASSIFICATION_SYSTEM.md) per i dettagli completi.
Una gara ha una **classifica** finale con un eventuale meccanismo per definire gli spareggi. Ad esempio una gara potrebbe definire gli spareggi solo per le prime tre posizioni con uno "_spot shot rally_": se nelle prime tre posizioni ci sono 2 o più giocatori pari merito, allora si affrontano in una **challenge** di tipo spot shot. Un altro tipo di spareggio potrebbe essere un match con un solo rack. 
Una **gara** ha una **policy per il forfait** il cui valore di default è definito dal campionato. La policy definisce come trattare un giocatore che ha dichiarato forfait negli abbinamenti e nei match successivi:
- **EXCLUDE**: il giocatore viene eliminato dagli abbinamenti futuri (ma resta in classifica con i punti accumulati). Se questo cambia la parità dei giocatori, si applica la gestione dispari configurata.
- **FORFEIT**: il giocatore rimane negli abbinamenti e fa vincere per forfait i giocatori che capitano con lui (con rack pieni fino alla distanza).

Nel match in cui avviene il forfait, l'avversario vince tutti i rack rimanenti fino alla distanza. Nel trio, gli altri due giocatori vincono i rack rimanenti.

### Turno

Un turno è legato ad una gara. È dato da un abbinamento di giocatori che giocano contemporanemente un match di tipo uguale (non è possibile, ad esempio, che in un turno due giocatori giochino a palla 9 e altri tue a palla 8, oppure che due giochino al meglio di 5 e altri al meglio di 7; tutti i match hanno le stesse caratteristiche. L'unica eccezione sono i match a tre, nella strategia di abbinamento casuale con classifiche basate sulla differenza di rack, descritti più avanti).
Una possibile **strategia di abbinamento** è **_amalfi_**. Un'altra possibile strategia di abbinamento è _round robin_. 
Una volta che tutti i match del turno sono terminati, è possibile modificare la classifica della gara. Quindi un turno prende la classifica precedente al turno, i risultati dei match e restituisce la classifica aggiornata.

**Cosa deve essere chiuso prima del turno successivo** (2026-09-13). Il turno successivo si avvia solo quando il turno precedente è chiuso davvero: tutte le sue partite concluse, **la prova giocata al posto della X convalidata dal direttore** — è come una partita non ancora validata, perché il suo punteggio è la differenza rack di quel turno — e **ogni esercizio fra i turni agganciato a quel turno registrato**, con almeno un tentativo, per ogni iscritto ancora in gara. Chi ha dato forfait non ha esercizi da registrare. Lo stesso vale per l'**ultimo turno** e la **chiusura della gara**: «Termina la gara», e lo spareggio che porta alla chiusura, non partono finché la prova della X e gli esercizi dell'ultimo turno non sono a posto — sono punteggi della classifica finale. La regola vale per le strategie che costruiscono ogni turno sulla classifica: con la strategia _casuale_, dove i turni nascono tutti all'avvio, né la prova della X né gli esercizi bloccano qualcosa, né il turno dopo né la chiusura.

Un tentativo di esercizio fra i turni registrato per sbaglio si può **togliere** (2026-09-13), a gara in corso e finché il turno successivo non è partito; con la strategia _casuale_ per tutta la gara. Il tentativo esce dalla classifica degli esercizi e i tentativi rimasti si rinumerano. L'XP dell'esercizio segue i tentativi rimasti, in qualunque ordine si tolgano: finché ne resta uno l'esercizio è fatto e l'XP resta, anche se si è tolto proprio il tentativo che l'aveva pagato; tolto l'ultimo, l'XP torna indietro.

#### Strategia di abbinamento

Una **strategia di abbinamento** abbina un elenco di giocatori in match. 

Ad esempio la **strategia di abbinamento _amalfi_** dipende da quanti turni mancano alla fine della gara e, dato un elenco ordinato di giocatori, abbina il giocatore `n`-esimo con il giocatore `n+i`-esimo con i pari al numero di turni che mancano da giocare per terminare la gara. 
_Amalfi_ evita che due giocatori si incontrino più di una volta, quindi se l'abbinamento derivante dalla logica generale `(n, n+i)` è stato già giocato in un turno precedente, allora scorre l'elenco in modo ciclico fino a trovare un giocatore `(n+i+j)%lunghezza_elenco` con cui il giocatore `n` non ha già giocato.

Una **strategia di abbinamento per _eliminazione diretta_**, invece, abbina tra loro i vincitori del turno precedente.

Una **sttategia di abbinamento per _doppio ko_** abbina tra loro i vincitori e ripesca una sola volta i perdenti.

> **Quanti turni dura un doppio KO** (nota del 2026-08-29, issue #239). Con un
> tabellone di `S` posti (`S` potenza di 2, minimo 8) e `k = log₂ S`, i turni
> **programmati** sono `2k`: `k` per il winners bracket, `2k - 2` per il
> losers — che si intercalano — e la finale. La **bella** e' un turno in piu',
> il `2k + 1`, e si gioca **solo se la finale la vince chi arriva dal losers
> bracket**: chi e' imbattuto non puo' essere eliminato da una sola partita,
> quindi in quel caso si rigioca da pari; se invece la finale la vince
> l'imbattuto, la gara e' conclusa e quel turno non esiste.
>
> Nella variante con **fase a gironi** (formula FISBB) non c'e' mai una bella.
> Il girone e' un doppio KO da `2^(w+1)` giocatori che **non deve produrre un
> vincitore**: si ferma appena i qualificati sono determinati — due imbattuti
> e due ripescati, quattro per girone — e quindi dura `2w - 1` turni, tre in
> meno del doppio KO completo della stessa taglia (gli mancano la finale e gli
> ultimi due round del recupero, che servirebbero a stringere i quattro fino a
> uno). Il tabellone finale e' a eliminazione diretta. I turni della gara sono
> `(2w - 1) + log₂` della taglia del tabellone finale.

La **strategia di abbinamento _casuale_** abbina a caso i giocatori assicurandosi solo che non ci sia mai lo stesso abbinamento più di una volta in turni diversi della stessa gara. Questo tipo di strategia può calcolare tutti gli abbinamenti subito e non ha bisogno di aspettare la conclusione dei match per l'abbinamento successivo.

Una strategia di abbinamento è associata anche ad una **strategia per il _primo abbinamento_** che può essere _casuale_ (in questo caso limitata al primo turno) oppure _basato su classifica_ oppure _basato su rating_ (elo).

Una strategia di abbinamento è associata anche ad una **policy per la X** che decide come trattare il caso in cui ci siano meno giocatori rispetto a quelli necessari. 
Ad esempio la strategia di _eliminazione diretta_ seleziona casualmente il numero di giocatori che eccede la potenza del 2 più alta e li fa passare tutti automaticamente al secondo turno (perché li abbina alla X e vincono atuomaticamente). 
La strategia di abbinamento _amalfi_ con classifiche basate su (match vinti, differenza rack vinti-persi) nel caso in cui i giocatori siano dispari abbina un giocatore alla X assegnando il match vinto, ma con zero differenza punti. In questo modo chi ottiene la X con l'abbinamento ottiene in classifica un posizionamento migliore di tuttii perdenti e peggiore di tutti i vincenti. 
Una variante, sempre per _amalfi_ consiste nel gestire la X con una challenge che possa dare un punteggio da zero alla massima differenza rack raggiungibile in quella gara. In questo modo il giocatore abbinato con la X, invece di stare fermo il turno, gioca la challenge e in classifica ottiene il match vinto e un differenza rack pari al punteggio nella challenge. 

**A chi tocca la X nel primo turno** (2026-08-26). Normalmente la decide il sorteggio insieme agli abbinamenti. Quando però la gara usa la strategia _amalfi_ o _casuale_, il primo turno è a sorteggio e i dispari sono gestiti con la X (o con la X con esercizio), all'avvio il direttore può assegnare la X **all'ultimo iscritto** invece di lasciarla al caso: è la risposta a una situazione ricorrente, in cui l'ultimo arrivato è quello che ha completato il numero all'ultimo momento. Il resto degli abbinamenti resta casuale: chi riceve la X viene scambiato di posto con chi l'aveva sorteggiata, e nient'altro si muove. Nella strategia casuale, dove tutti i turni nascono insieme, lo scambio vale per l'intero calendario, così ognuno continua ad avere una sola X e nessuno reincontra nessuno.

Se il numero di giocatori è dispari, si può gestire con diverse opzioni:
- **NO**: i giocatori che rendono dispari vanno in lista d'attesa fino a quando non si iscrive un altro giocatore
- **Bye**: un giocatore salta il turno (solo per sistema WINS: ottiene 1 vittoria, 0 diff rack)
- **Bye+Challenge**: un giocatore esegue una challenge che determina il suo punteggio
- **Bye+N rack**: un giocatore ottiene automaticamente N rack (solo per sistema RACK)
- **Trio**: tre giocatori giocano insieme mini gironi

Il **trio** è possibile solo per le distanze da 2 a 7. I giocatori nel trio giocano uno o più mini gironi all'italiana (round robin) in cui tutti giocano con gli altri un solo rack:

| Distanza | mini gironi | rack giocati da ogni giocatore | rack totali | punteggio (RACK) |
| --- | --- | ---| ---| --- |
| 2 | 1 | 2 | 3 | rack vinti |
| 3 | 1 | 2 | 3 | 1 + rack vinti |
| 4 | 2 | 4 | 6 | rack vinti |
| 5 | 2 | 4 | 6 | 1 + rack vinti |
| 6 | 3 | 6 | 9 | rack vinti |
| 7 | 3 | 6 | 9 | 1 + rack vinti |

Per il sistema WINS, nel trio vince chi ha il punteggio più alto (1 vittoria), gli altri ottengono 0 vittorie. Se il punteggio più alto è di due o tre giocatori, nessuno prende la vittoria: il pari in testa non si scioglie con lo scontro diretto. Chi si ritira dal trio non vince, e il pari si guarda fra gli altri due. La differenza rack è sempre calcolata dai risultati effettivi. _Nota del 2026-09-13: la frase «se c'è pareggio» è stata riscritta perché ambigua. Il codice scioglieva il pari in testa con lo scontro diretto, per una scelta presa il 2026-05-10 durante una sessione di prove e mai riportata qui, `docs/_archive/2026-05-10-test-session.md`; la decisione del 2026-09-13 conferma la specifica e supera quella scelta. Lo stesso giorno è stata decisa la regola del ritiro: chi si ritira dal trio non vince mai, nemmeno col totale più alto, e il pari si guarda solo fra gli altri due; prima lo scioglieva lo scontro diretto fra i due rimasti. Esempi alla distanza 6, nove triangoli: Marco 3, Luca 3 e Gianni ritirato con 3, nessuno vince; Marco 3, Luca 2 e Gianni ritirato con 4, vince Marco, anche se Gianni ha il totale più alto._

Per distanze superiori a 7, i rack totali da giocare diventano troppi rispetto a quelli che giocano le coppie e quindi il trio allungherebbe troppo i tempi della gara.
### Gare amalfi

Una gara **amalfi** è una gara in cui non c'è eliminazione e tutti i giocatori giocano lo stesso numero di turni.
Inizialmente gli iscritti vengono abbinati casualmente. Una variante prevede un abbinamento iniziale basato sulla classifica del campionato (comunque nella prima gara, in cui la classifica è assente, l'abbinamento è casuale). Un'altra variante prevede che l'abbinamento iniziale sia basato sull'_Elo rating_. Il _Fargo rating_, previsto nelle prime stesure, non viene implementato (2026-08).
Amalfi abbina ad ogni turno i giocatori partendo dalla classifica precedente e saltando un numero di posizioni pari ai turni che mancano alla fine.

#### Garanzia anti-rematch nel caso pari

Quando il numero di giocatori è **pari** e l'opzione `anti_rematch_enabled` è attiva, l'algoritmo Amalfi **garantisce zero rematch quando matematicamente possibile**, ovvero quando esiste un matching perfetto sul grafo complementare degli incontri già giocati. La garanzia è raggiunta sostituendo il greedy salto con un _maximum weighted matching_ sul grafo complementare:

- **Cardinalità massima** — gli archi del grafo sono solo le coppie di giocatori che NON si sono ancora incontrati; un matching perfetto (cardinalità `N/2`) implica zero rematch.
- **Pesi per spirito Amalfi** — gli archi sono pesati per minimizzare lo scostamento dal salto target (`max_turni - turno + 1`): tra tutti i matching perfetti possibili, viene scelto quello che meglio rispetta il salto Amalfi.
- **Fallback** — quando il matching perfetto sul complementare non esiste (rematch matematicamente inevitabile), l'algoritmo accetta il numero minimo di rematch e usa il greedy salto come tie-breaker.

Per il caso **dispari** la priorità è descritta nella sezione successiva (selezione trio): la rotazione equa dei trii vince sull'anti-rematch.

#### Selezione trio nell'algoritmo Amalfi

Quando il numero di giocatori è dispari e la policy è "trio", la selezione dei 3 giocatori per il trio segue un algoritmo a 3 step:

**Step 1 — Salto con BYE sentinel.** Il salto Amalfi standard gira con un BYE sentinel al posto del giocatore mancante. Chi atterra sul BYE diventa l'"ancora" del trio. Le restanti coppie formano la rappresentazione intermedia.

**Step 2 — Swap dell'ancora per rotazione.** Se l'ancora ha un conteggio trio superiore al minimo tra tutti i giocatori, viene scambiata con il giocatore in coppia che ha il conteggio trio più basso; a parità, quello più basso in classifica (più "spirito Amalfi"). Nessun check anti-rematch in questo step.

**Step 3 — Selezione compagni per score.** Tra tutte le combinazioni C(N-1, 2) di 2 giocatori dal pool delle coppie, si calcola uno score a tuple:
1. `companion_count_sum` — somma dei conteggi trio dei 2 compagni (rotazione equa)
2. `trio_rematches` — quante delle 3 coppie nel trio si sono già incontrate (anti-rematch)
3. `orphan_rematch` — 1 se i 2 orfani (giocatori rimasti senza partner) si sono già incontrati, 0 altrimenti
4. `-position_sum` — somma delle posizioni in classifica dei 2 compagni (spirito Amalfi — preferisce entrambi i compagni bassi in classifica, non solo uno dei due)

Si sceglie la combinazione con score minimo (lessicografico). La ricomposizione produce i Pairing finali: un trio con i 3 giocatori ordinati per classifica, le coppie invariate, e l'eventuale coppia orfani.

**Ordine di sacrificio** (cosa si cede per prima quando i vincoli confliggono):
1. Posizione in classifica — si devia dallo spirito Amalfi pur di evitare rematch
2. Anti-rematch — si accetta un rematch nel trio pur di garantire rotazione equa
3. Rotazione equa (ultima a cedere) — la differenza di conteggio trio tra giocatori deve restare minima


## Match

Un **match** è una parte di una gara. È formato da uno o più **set**.
Il **match** ha una **regola di inizio** e una **regola di apertura**, entrambe ereditate dalla gara a cui appartiene: sul singolo match non si scelgono.

La **regola di inizio** dice chi esegue il tiro di apertura del primo rack e può essere:
- **"primo giocatore"**: apre il primo dei due, senza sorteggio;
- **"acchito"**: si tira l'acchito. Chi lo vince **sceglie chi** esegue il tiro di apertura, e può scegliere l'avversario.

La **regola di apertura** dice come il tiro di apertura passa da un rack al successivo e può essere:
- **"spacca chi ha vinto"** (`winner_breaks`): apre chi ha vinto il rack precedente;
- **"a turno"** (`alternate`): tiri di apertura alternati, la regola standard FIBiS. È il default;
- **"a turno ogni due"** (`alternate_two`): due rack a testa, poi si cambia;
- **"spacca chi ha perso"** (`loser_breaks`): apre chi ha perso il rack precedente.

Un rack chiuso in **una sola visita** è un **run-out**; se a quel rack l'apertura era di chi l'ha vinto è un **break and run**. Non si sceglie: si deduce da chi apriva. Nel profilo del giocatore i due numeri si mostrano come insieme e sottoinsieme («Runout: 26, di cui 9 break and run»).

> **Nota del 2026-08-28 (ADR-056).** Questo paragrafo emenda la versione precedente, che diceva: «Il match ha una regola di inizio che può essere "primo giocatore" oppure "acchitto". Si gioca con "break continuo" o "break alternato". Entrambi questi valori hanno un default che dipende da quello che è impostato nella gara a cui appartiene il match.» Quattro cose non tornavano.
> 1. La specifica prevedeva **due** modalità di apertura; il codice ne aveva già **tre** (`alternate`, `winner_breaks`, `loser_breaks`), sulle sole sfide individuali. «A turno ogni due» è **nuova**.
> 2. La regola di inizio lasciava intendere che chi vince l'acchito cominci. Il regolamento FIBiS («Regole generali pool», 1.2) dice altro: «Il giocatore che vince l'acchito **sceglie chi** eseguirà il tiro di apertura.» Sono due domande, non una.
> 3. Sui match di **gara** non esisteva nulla: né le due regole su `Campionato`/`Gara`/`Match`, né il posto dove scrivere chi avesse aperto un rack. Esisteva solo sulle sfide individuali, dove il match **è** la radice perché una gara da cui ereditare non c'è.
> 4. Il default della regola di apertura è `alternate` perché è quello che le sfide individuali avevano già dal 2026-02: cambiarlo riscriverebbe il passato di quelle partite.
>
> Nota lessicale, dallo stesso regolamento: «acchito» ha **due** significati — il primo tiro che decide l'ordine di gioco (1.2) e la preparazione delle bilie nel triangolo (1.4, «Acchito delle bilie», «Riacchito»). Qui vale sempre il primo. Per *run-out* e *break and run* un termine italiano nel regolamento non c'è, e «serie» è già occupato (indica il **gruppo** di bilie assegnato): restano in inglese.

Il **match** ha una distanza (numero di **set** necessari per vincere un match). Di solito il set è uno solo e quindi si definisce la distanza come numero di rack necessari per vincere, ma possono essere anche più set e in questo caso vince il match il giocatore che vince per primo il numero di set prefissato (la distanza del match).  La distanza di default viene definito dalla gara a cui appartiene il match.
La distanza del **set** è il numero di **rack** che devono essere vinti per aggiudicarsi il set. La distanza può essere:
- **"Race to N"** (al meglio di): vince il giocatore che per primo vince N rack. Produce sempre un vincitore.
- **"Exactly N"** (esatto numero): si giocano esattamente N rack, vince chi ne ha vinti di più. Se N è pari, sono possibili pareggi (gestiti con 0 vittorie e 0 diff rack per entrambi nel sistema WINS).

Il tipo di distanza ha implicazioni sul sistema di classifica:
- Sistema RACK: preferisce "Exactly N" (tutti giocano lo stesso numero di rack). "Race to N" è permesso con warning.
- Sistema WINS: preferisce "Race to N" o "Exactly N dispari" (serve un vincitore). "Exactly N pari" ammette pareggi.
- Sistema POSITION: richiede "Race to N" o "Exactly N dispari" (serve sempre un vincitore).

Il valore di default per la distanza dei set viene dalla gara a cui appartiene il match.
Di solito la disciplina dei rack che compongono un set è la stessa, ma una variante prevede che la distanza sia da coprire con più discipline diverse. Ad esempio vince chi arriva prima a 7, ma i primi 5 rack sono a palla 8 e gli altri a palla 9.
Un'altra variante, che si accompagna al break continuo per il set (il giocatore che vince il rack è lo stesso che apre il successivo), prevede che chi spacca decide la disciplina tra un predeterminato insieme di discipline possibili (ad esempio un match al 5, break continuo, scelta tra palla 8 o palla 9).

Un **match** può essere con handicap o no. Se c'è l'handicap allora dipende dalla differenza di categoria dei giocatori o dalla differenza di rating (elo) dei giocatori. Un esempio di handicap può essere questo: se un giocatore di categoria A è abbinato con uno di categoria C, parte da -2, se è abbinato con uno di categoria B parte da -1 come pure un giocatore di categoria B abbinato con uno di C.

La app permette anche agli utenti ``player`` di organizzare **match _standalone_** (casual match) con un altro utente. Questi match utilizzano la stessa interfaccia di gestione dei rack dei match di torneo tramite un componente unificato (**BaseMatchMixin**), garantendo una UX coerente.

### Ciclo di vita dei Match

Tutti i match (sia di torneo che individuali) condividono un set unificato di stati (**MatchStatus**):

- **Stati Torneo**: `pending` (in attesa di inizio) -> `playing` (in corso) -> `completed` (finito, attesa conferma) -> `validated` (confermato).
- **Stati Individuali**: `scheduled` (proposto/accettato) -> `in_progress` (giocato) -> `completed` (finito).
- **Stati Comuni**: `cancelled` (annullato).

Questa unificazione permette di tracciare le statistiche e gestire i risultati in modo centralizzato.

Una sfida a due si chiude con la **conferma di entrambi i giocatori** (ADR-051). Raggiunta la distanza chi vince conferma d'ufficio; nel formato libero conferma chi dichiara finita la partita. Da quel momento la partita è **in attesa di conferma** dell'altro giocatore.

- Passato **un giorno** dalla prima conferma, la partita non compare più nella dashboard, né per chi deve confermare né per chi aspetta. Resta nell'elenco delle sfide con lo stato «In attesa di conferma».
- Chi ha almeno una partita in attesa della **propria** conferma non può lanciare una nuova sfida (proposta, avvio rapido, richiesta da disponibilità) né accettarne una ricevuta, finché non la conferma o la rifiuta. Il blocco vale da subito, non dopo il giorno. Invece di un errore il sistema gli propone le partite da chiudere, ognuna con conferma e rifiuto, e chiusa l'ultima lo riporta a quello che stava facendo. Chi aspetta la conferma dell'avversario non è bloccato.

_Nota del 2026-09-14: regole nuove, decise dall'utente. Prima una partita mai confermata restava «in corso» a tempo indeterminato, in dashboard e fuori, come l'ADR-051 aveva messo in conto fra le conseguenze negative; e nulla impediva a chi non confermava di aprire altre sfide. Il giorno si conta dalla prima conferma perché è il momento in cui la partita smette di aspettare un gioco e comincia ad aspettare una firma: una partita ancora da finire non è in attesa di nessuno._

## Rack

Un **rack** è relativo ad una disciplina come, ad esempio, "palla 8", "palla 9", "palla 10", "pool continuo", "one pocket". Il valore di default della disciplina viene dal set, che a sua volta prende il valore di default del match, che lo prende da turno, che lo prende come valore di default da gara.

> **Le regole numeriche di questo documento sono eseguibili.**
> Punteggi, classifiche, valore della X, cascata dei rifiuti ai playoff: ogni
> regola con un numero dentro ha un test che la cita in
> `tests/new/unit/test_specifiche_conformita.py`. Se cambi una regola qui,
> cambia il test nello stesso commit; se trovi che il codice diverge, il test
> va scritto `xfail(strict=True)` invece che adattato al codice. Il perché sta
> in `CLAUDE.md`, sezione «Prima di tutto: la specifica, se c'è».

### Classifica

Una **classifica** può essere collegata ad un turno, una **gara** o ad un **campionato**.

Esistono tre sistemi di classifica:
- **RACK**: ordina per rack totali vinti (decrescente), poi spareggio
- **WINS**: ordina per match vinti (decrescente), poi differenza rack (decrescente), poi spareggio
- **POSITION**: assegna punti per posizione nel tabellone (solo per gare a eliminazione)

Tutte le gare di un campionato devono usare lo stesso sistema di classifica, compresa la gara di playoff (salvo che si giochi a tabellone: allora è POSITION, l'unico sistema che un tabellone ammette). Il sistema si può cambiare solo finché nessuna gara del campionato ha aperto le iscrizioni o ha già degli iscritti: dopo, cambierebbe le regole a chi si è iscritto o ha già giocato; prima, il cambio arriva a tutte le gare ancora da aprire *(precisato il 2026-09-14: fino ad allora la gara di playoff nasceva a vittorie qualunque fosse il sistema, e il cambio sul campionato lasciava le gare già create col sistema vecchio)*. La classifica del campionato aggrega sommando le classifiche delle singole gare.

Per i dettagli completi sul sistema di classificazione, vincoli e combinazioni valide, vedi [CLASSIFICATION_SYSTEM.md](CLASSIFICATION_SYSTEM.md).

### Playoff

I **playoff** sono una **gara** speciale a cui per iscriversi occorre avere alcune caratteristiche. Ad esempio un campionato può definire un playoff per i primi 6 classificati. Oppure un playoff Elite per i primi 6 e Academy per i secondi 6. Oppure, ancora, un playoff solo per i giocatori dal terzo posto in giù che hanno partecipato ad almeno 5 gare del campionato.
Alla fine del campionato i giocatori che soddisfano i criteri del playoff ricevono una notifica di accesso ai playoff e possono iscriversi o rifiutare. Nei playoff con un numero limitato di partecipanti (ad esempio i primi 6), se un giocatore rifiuta, la notifica passa al primo degli esclusi e così via fino a quando un numero di giocatori pari ai posti disponibili ha dato l'ok oppure sono finiti i giocatori. 

La gara di playoff **non ha una fase di iscrizioni**: gli iscritti sono chi ha accettato l'invito, quindi la gara nasce in preparazione e il direttore la avvia da lì, senza aprire nessuna finestra; se annulla l'avvio, torna in preparazione. Il playoff si gioca con chi ha accettato, anche se sono meno dei posti: la gara di playoff chiede almeno **due** iscritti, non il minimo delle gare di serata. Gli inviti partono prima che il direttore crei la gara, e le risposte non arrivano tutte insieme: chi accetta dopo la creazione — compreso il primo degli esclusi chiamato da un rifiuto — **entra fra gli iscritti** fino all'avvio del primo turno, e allo stesso modo il direttore aggiunge o toglie qualificati fino all'avvio. **All'avvio** gli inviti ancora senza risposta scadono e nessun altro viene chiamato: la finale è cominciata. Se il direttore **annulla l'avvio**, gli inviti chiusi proprio da quell'avvio tornano in attesa, purché la loro scadenza non sia ancora passata, e chi non aveva risposto può accettare ed entrare come prima; gli inviti scaduti per la loro scadenza o già sostituiti restano come sono. Il limite dei posti vale **per la cascata degli inviti**: chi accetta tardi e trova i posti pieni va in lista d'attesa. Un giocatore **aggiunto a mano dal direttore** entra invece sempre, prima e dopo la creazione della gara, anche oltre i posti, e il massimo della gara non ne blocca l'avvio: è una sua decisione esplicita. La **parità** invece vale anche per lui: se la gara non ammette un numero dispari di giocatori — né X né trio — chi renderebbe dispari gli iscritti aspetta in lista d'attesa come gli altri, finché non arriva un secondo giocatore, e intanto la gara resta avviabile.

> **Nota (2026-09-13).** Fino a questa data la gara di playoff nasceva col minimo di sei iscritti, quindi un playoff da quattro posti non partiva nemmeno con quattro sì; e la lista si congelava alla **creazione** della gara, per cui chi accettava dopo restava confermato ma fuori, senza modo di rientrare. L'ordine «prima gli inviti, poi la gara» resta: cambia il momento in cui la lista si chiude.

> **Nota (2026-09-13, sera).** Fino a questa data per avviare il playoff il direttore doveva **aprire le iscrizioni**, con inizio e fine, su una gara a cui non si iscrive nessuno: inviti, accettazioni e rifiuti erano già avvenuti. Ora la gara di playoff si avvia dalla preparazione e aprirne le iscrizioni è rifiutato. Le gare di playoff già aperte prima di questa data si avviano come prima.

### Challenge

Una **challenge** è una gara di abilità che un giocatore può affrontare da solo. Consiste in una immagine, che mostra la disposizione delle biglie sul tavolo e un testo di spiegazione. È identificata da un nome. 
Ha un punteggio minimo e massimo oppure un superato/non superato. 
I risultati delle **challenge** compaiono nelle statistiche individuali dei giocatori.  
``admin`` può vedere le statistiche delle **challenge** (numero di giocatori che hanno tentato, numero di tentativi, punteggio medio, numero di giocatori con punteggio massimo, punteggio mediano)
Un giocatore può scegliere una **challenge** da un elenco generale o da quelle che ha già provato o dalle sue preferite.
Un giocatore può aggiungere/togliere una **challenge** dalle sue preferite.

### Esame

Un **esame** è una sequenza ordinata di **challenge**, ciascuna con il proprio
punteggio massimo *per quell'esame* — lo stesso drill può valere 10 in un esame e
15 in un altro.

L'esito è **booleano**: superato o non superato. Niente voto, niente griglia di
valutazione, nessuna nota. La ragione sta in ADR-042: chi certifica lo fa in
piedi accanto a un tavolo, e un sì/no è un fatto che si registra in un gesto,
mentre un voto è un giudizio che va argomentato e che il giorno dopo si contesta.

Un esame si può affrontare in due modi:

- **in autonomia**, come allenamento. Non certifica mai, nemmeno a posteriori;
- **davanti a un esaminatore**, di persona. È l'unica modalità che certifica, e
  il candidato deve **accettare esplicitamente l'inizio** prima che qualsiasi
  punteggio sia registrabile.

A comporre e somministrare un esame è un **esaminatore** — un ruolo *concedibile*
e ortogonale a quello primario (ADR-041), non un `director`: chi lo riceve resta
player, e continua a iscriversi alle gare e a sostenere esami altrui. Il ruolo lo
concede un admin oppure un altro esaminatore.

Il creatore di un esame può aggiungere **co-esaminatori**, così che i candidati
non dipendano da lui solo.

L'esame certificato richiede un **appuntamento**: il candidato chiede a uno o più
esaminatori, si concorda data, ora e sala con controproposte a oltranza, e il
primo esaminatore che accetta chiude la richiesta per gli altri.

Gli esami compaiono nelle statistiche di ``admin`` e dell'esaminatore che li
somministra. Nel profilo del giocatore, quelli certificati portano il badge
«certificato da …»; quelli in autonomia no.

## Casi d'uso

### Utente guest

#### Registrazione

L'utente si registra scegliendo uno username (case sensitive, unico), email, telefono (opzionale), password

#### Login

Inserisce userid e password del proprio account. Gli utenti devono verificare la propria email per attivare completamente tutte le funzionalità dell'account (invio email, notifiche avanzate).

#### Verifica Email

Dopo la registrazione, il sistema invia un'email automatica con un link di verifica. L'utente può anche richiedere l'invio di un nuovo link dal proprio profilo. Lo stato di verifica è tracciato tramite il campo `is_verified`.

#### Recupero Password

Se un utente dimentica la propria password, può richiederne il reset fornendo l'email. Riceverà un link sicuro e temporaneo per impostare una nuova password.

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

_Nota del 2026-09-14: un match singolo in attesa di conferma da più di un giorno non è più un'attività in corso e non compare nella home; resta fra le sfide. Vedi «Ciclo di vita dei Match»._

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

#### Competizione di prova

Un direttore può creare una gara singola o un campionato **di prova** (ADR-058, specifica completa in `docs/usecases/competizione-di-prova.md`): la stessa competizione con un flag, per imparare le schermate di gestione senza toccare dati reali.

- Una prova è visibile **solo** a chi la dirige (direttore, co-direttori, admin). Non compare in nessun elenco pubblico, non ha link pubblico né vetrina.
- Un direttore può avere al massimo **3 prove aperte** contemporaneamente (gare singole e campionati sommati).
- A una prova si iscrivono **solo giocatori fittizi**, creati dalla prova stessa con nomi generici e rating iniziali fissi e diversi fra loro. Nessun utente reale, nemmeno il direttore.
- In una prova avviata il direttore **simula i risultati**: una partita, il turno o tutta la gara. Ogni rack passa dal segnapunti vero, con l'id del fittizio che lo segna, e il punteggio rispetta la distanza effettiva del turno (ADR-027). Le partite si chiudono **in entrambi i modi**, deciso dalla parità dell'id: le **pari** con la doppia conferma dei giocatori, le **dispari** restano a distanza raggiunta in attesa che il direttore le validi. «Simula tutta la gara» chiude tutto, validando le dispari come farebbe lui. Il segnapunti vero resta usabile.
- In un **campionato di prova** le gare ereditano il flag e i giocatori fittizi sono **del campionato**: la seconda gara riusa quelli della prima e ne crea di nuovi solo se non bastano, così la classifica generale si forma. Le date delle gare vengono proposte **nei prossimi giorni e in ordine** (domani la prima, il giorno dopo l'ultima le altre, ADR-016). Al playoff il direttore accetta o rifiuta l'invito **per ciascun fittizio**, con gli stessi servizi del giocatore, e può accettare tutti i rimanenti insieme; un rifiuto fa scattare il primo degli esclusi.
- Le partite di una prova **non muovono alcun rating** e nessun evento di una prova assegna XP, badge o missioni a nessuno. Le statistiche del direttore (gare organizzate) ignorano le prove.
- Le notifiche originate da una prova arrivano al direttore solo in app, con il prefisso «Prova ·».
- Una prova si può eliminare in qualunque stato; l'eliminazione è **fisica** e include partite, iscrizioni, qualificazioni e giocatori fittizi.
- Una prova non eliminata sparisce da sola **14 giorni** dopo la creazione; il direttore riceve un avviso in app **3 giorni** prima.

## Internazionalizzazione

La piattaforma supporta più lingue:
- **Italiano** (lingua predefinita)
- **Inglese** (completo)

La lingua viene rilevata automaticamente dalle impostazioni del browser dell'utente.

## Scelte architetturali

### Privacy

Le informazioni dell'anagrafica dell'utente sono salvate cifrate.
La chiave di cifratura è nella configurazione lato server.