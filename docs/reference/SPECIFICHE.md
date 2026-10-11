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

> **Nota (2026-09-29, ADR-075).** Fino a questa data una **gara** non si poteva modificare appena aveva **un** iscritto, anche prima di cominciare: la finale dei playoff, che nasce con gli iscritti dentro, non si correggeva mai. Ora una gara si modifica **fino all'avvio del primo turno**, anche con gli iscritti, e ogni modifica resta nella sua **storia delle modifiche** (chi, quando, cosa, motivo facoltativo). **A gara avviata** (aggiornato il 2026-09-29) si cambiano ancora la logistica — nome, data, ora, sala, quota, descrizione — che vale subito, e le **regole di gioco** — distanza, «al N» o «esattamente N», disciplina, chi apre, chi spacca, handicap e categorie, dispari, ritiri, anche per singolo turno non ancora avviato — che valgono **dal turno successivo**: i match già nati hanno le regole fissate. La **struttura** (strategia, numero di turni, sistema di classifica, primo turno, set, anti-reincontro, opzioni del tabellone, minimo e capienza) si cambia solo annullando l'avvio. Con la strategia casuale, dove tutti i turni nascono all'avvio, le regole di gioco restano quelle dell'avvio. Lo spareggio si cambia finché non è cominciato. Il dettaglio sta in [`docs/usecases/regolamento-di-gara.md`](../usecases/regolamento-di-gara.md) e in `models/competition/campi_modificabili.py`.

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

> **Nota (2026-10-06, ADR-079).** Oltre alla quota unica, una **gara singola** o un **campionato** può avere un **listino delle quote per categoria** (es. «Serie A 30 € · Serie B e C 20 € · Amatori 15 €»). Ogni voce è una **categoria** della competizione: scriverla nel listino la crea, toglierla la toglie dal listino senza cancellarla. Il listino di un campionato vale per tutte le sue gare. È **solo informazione**: si mostra al posto della quota unica dove la quota si vede, ordinato dalla quota più alta alla più bassa e, a parità di quota, in ordine alfabetico; la categoria la assegna il direttore, quindi il giocatore vede il listino e non «la sua» quota. Niente incasso, niente «ha pagato». Le categorie così esistono **anche senza handicap**, e lì non cambiano niente per l'ELO: la categoria pesa sull'ELO solo nelle gare con handicap. Ogni cambio del listino resta nella storia delle modifiche.
Una **gara** con un masssimo di iscritti ha anche una **lista di attesa**. I giocatori che si iscrivono alla **gara** dopo che il massimo numero è stato raggiunto vengono messi in coda. Se uno degli iscritti si disiscrive, viene iscritto il primo della lista d'attesa e gli viene inviata una notifica. 

> **Nota (2026-09-29, ADR-075).** Lo stesso vale quando il direttore **alza la capienza** prima dell'avvio: entrano dalla lista d'attesa, in ordine, tanti giocatori quanti sono i posti nuovi, ciascuno con la sua notifica. Fino ad allora la lista si muoveva solo quando qualcuno si toglieva.

> **Nota (2026-09-16).** La finestra di iscrizione vale per i **giocatori**. Il direttore iscrive e toglie un giocatore **anche a iscrizioni chiuse**, finché la gara non è avviata: chi arriva in sala senza essersi iscritto in tempo entra lo stesso, e chi avvisa che non viene si toglie. Un'iscrizione fatta dal direttore resta riconoscibile — «iscritto da X» nell'elenco, come «registrato da X» per gli inviti ai playoff — e rispetta posti e parità come tutte le altre: oltre il massimo si va in lista d'attesa anche se a iscrivere è il direttore. Nasce dal campionato 4 (15/09/2026), dove la finale è finita in una gara a parte perché nessuno poteva più aggiungere chi si era presentato.

Una gara ha una **strategia di abbinamento** tra turni, una policy per definire l'abbinamento del primo turno (ad esempio casuale oppure sulla base della classifica) e una policy per la gestione del numero dispari di giocatori (NO, Bye, Bye+Challenge, Bye+N rack, o Trio). Tutti questi valori hanno un default che dipende dal campionato a cui appartiene la gara.

Una gara ha un **sistema di classifica** che può essere RACK (rack totali vinti), WINS (match vinti + differenza rack), POINTS (punti per risultato: vittoria, pareggio, sconfitta) o POSITION (punti per posizione nel tabellone). Il sistema di classifica determina i vincoli sulle altre opzioni (distanza, multi-set, gestione dispari). Vedi [CLASSIFICATION_SYSTEM.md](CLASSIFICATION_SYSTEM.md) per i dettagli completi.
Una gara ha una **classifica** finale con un eventuale meccanismo per definire gli spareggi. Ad esempio una gara potrebbe definire gli spareggi solo per le prime tre posizioni con uno "_spot shot rally_": se nelle prime tre posizioni ci sono 2 o più giocatori pari merito, allora si affrontano in una **challenge** di tipo spot shot. Un altro tipo di spareggio potrebbe essere un match con un solo rack. 
Una **gara** ha una **policy per il forfait** il cui valore di default è definito dal campionato. La policy definisce come trattare un giocatore che ha dichiarato forfait negli abbinamenti e nei match successivi:
- **EXCLUDE**: il giocatore viene eliminato dagli abbinamenti futuri (ma resta in classifica con i punti accumulati). Se questo cambia la parità dei giocatori, si applica la gestione dispari configurata. Nel **girone all'italiana** invece chi viene escluso resta al suo posto nel calendario, e il suo avversario dei turni successivi **vince a tavolino**, come contro un forfait: vittoria e rack pieni fino alla distanza di quel turno. Se l'escluso era chi riposava in quel turno, o se sono esclusi tutti e due i giocatori di una coppia, quel posto non produce nessun match (nota del 2026-10-11 qui sotto, «Turno»).
- **FORFEIT**: il giocatore rimane negli abbinamenti e fa vincere per forfait i giocatori che capitano con lui (con rack pieni fino alla distanza).

Nel match in cui avviene il forfait, l'avversario vince tutti i rack rimanenti fino alla distanza. Nel trio, gli altri due giocatori vincono i rack rimanenti.

### Turno

Un turno è legato ad una gara. È dato da un abbinamento di giocatori che giocano contemporanemente un match di tipo uguale (non è possibile, ad esempio, che in un turno due giocatori giochino a palla 9 e altri tue a palla 8, oppure che due giochino al meglio di 5 e altri al meglio di 7; tutti i match hanno le stesse caratteristiche. L'unica eccezione sono i match a tre, nella strategia di abbinamento casuale con classifiche basate sulla differenza di rack, descritti più avanti).
Una possibile **strategia di abbinamento** è **_amalfi_**. Un'altra possibile strategia di abbinamento è _round robin_. Il **_round robin_** (girone all'italiana) fa incontrare ogni giocatore con ogni altro esattamente una volta. Con `N` giocatori servono `N-1` turni se `N` è pari e `N` turni se `N` è dispari: nel dispari ogni giocatore riposa una volta. **Il riposo nel girone non vale niente**: zero vittorie, zero punti, zero rack, e non è un match giocato; chi riposa resta in classifica, e il riposo resta visibile nel turno. Vale con ogni sistema di classifica ammesso dal girone (WINS, RACK, POINTS), e per questo nel girone il riposo è ammesso anche col sistema RACK: ognuno riposa esattamente una volta, e lo zero tocca tutti allo stesso modo. Nel girone il dispari si gestisce **solo col riposo**: la X con esercizio non si può scegliere, e se il campionato la propone a una gara a girone, la gara ripiega sul riposo. Il calendario si fissa all'avvio, dal sorteggio del primo turno, e non cambia più. _Nota del 2026-10-06: il numero di turni del caso dispari è scritto qui per la prima volta; fino a quella data una delle due funzioni che lo calcolavano dava `N-1` anche con `N` dispari. Lo stesso giorno è stata scritta la conseguenza della policy EXCLUDE (più sopra, «policy per il forfait») sul girone: chi viene escluso resta al suo posto nel calendario e il suo avversario di quel turno riposa, invece di ricalcolare il calendario su chi resta, che spostava le coppie dei turni successivi._ _Nota del 2026-10-11: fino a questa data nel girone dispari si riposava «con la X», che vale una vittoria e zero differenza (più sotto, «policy per la X»), e l'avversario di un escluso riposava allo stesso modo. È cambiato con il piano dei gironi multipli: fra gironi di taglia diversa la X regalava una vittoria a chi stava nel girone dispari. L'utente ha deciso che nel girone all'italiana il riposo non vale niente, che l'avversario di un escluso vince a tavolino, e che la X con esercizio nel girone non c'è più (avrebbe dato in classifica qualcosa al posto di un riposo che non vale niente). In produzione non c'erano gare a girone giocate, quindi la regola nuova vale per tutte. Le strategie _amalfi_ e _casuale_ non cambiano: lì la X vale ancora una vittoria._

**Gironi multipli** (2026-10-11, ADR-076). Il girone all'italiana può dividere gli iscritti in più **gironi**, giocati in parallelo: ognuno incontra tutti gli altri del **suo** girone, una volta, con le regole del paragrafo qui sopra (riposo che non vale niente, avversario dell'escluso che vince a tavolino).

- La gara dice un **tetto**, «gironi: fino a N», da 1 a 8; vuoto o 1 vuol dire **girone unico**, cioè il girone all'italiana di sempre. Il campionato **a piazzamenti** lo propone alle sue gare (il campionato propone, la gara decide); una gara singola lo sceglie da sé. In un campionato che **somma i totali** (vittorie, rack o punti) le gare restano a girone unico: il tetto non si sceglie, e una gara con più gironi viene rifiutata (vedi «Classifica», nota del 2026-10-11). Le altre strategie non hanno gironi.
- Il **numero esatto** lo fissa il direttore all'avvio, sugli iscritti presenti: da 1 al tetto, con almeno **3 giocatori per girone**. La proposta è **un girone ogni 6 iscritti, arrotondato per eccesso**, dentro quei limiti: con 11 iscritti e tetto 2, due gironi. Con troppo pochi iscritti il massimo scende (8 iscritti: al più 2 gironi).
- Le **taglie** differiscono al più di uno, e il giocatore in più va ai primi gironi: 11 iscritti in 2 gironi fanno 6 e 5, in 3 gironi 4, 4 e 3.
- La **composizione dei gironi** si sceglie fra tre voci: **sorteggio**, **per ELO** (dal più alto; chi non ha ELO in fondo), **per categoria** (nell'ordine del listino, dalla quota più alta, poi le categorie senza quota per nome; chi non ha categoria in fondo; dentro la categoria per ELO). A pari merito decide il sorteggio della gara. La fila si distribuisce **uno per girone a turno, andata e ritorno**: con due gironi il 1° va in A, il 2° e il 3° in B, il 4° e il 5° in A, e così via. Così i primi della fila finiscono in gironi diversi. Se la gara separa i compagni di squadra, i compagni si spostano fra gironi della stessa passata, quando possibile.
- I gironi si fissano all'avvio e **non cambiano più**: un ritiro non sposta nessuno, e chi si ritira resta nel suo girone. Annullare l'avvio annulla anche i gironi, che si ricompongono al riavvio.
- **Turni paralleli**: il turno `r` contiene il turno `r` del calendario di ogni girone. I turni della gara sono quelli del **girone più numeroso**; un girone che ha finito il suo calendario non gioca più, nemmeno un riposo. 11 iscritti in 6 e 5: entrambi i gironi giocano 5 turni (il girone da 5 riposa una volta a testa, quello da 6 no). 13 iscritti in 7 e 6: 7 turni, e il girone da 6 si ferma dopo il quinto.
- Anche nel **girone unico** il numero di turni si fissa all'avvio sugli iscritti presenti (con `N` iscritti, `N-1` o `N`), come per il tabellone: il valore scritto alla creazione era una stima sui posti dichiarati.

**Fase finale dopo i gironi** (2026-10-11). Il girone all'italiana — a uno o più gironi — può finire con una **fase finale**, scelta fra tre: **nessuna** (la gara finisce coi gironi, ed è il default), **tabellone** fra i primi `K` di ogni girone, **finali per piazzamento** (il p-esimo di un girone contro il p-esimo dell'altro: regola in arrivo, non ancora attiva). La sceglie la gara, anche una gara singola; il campionato a piazzamenti la propone. Il **tabellone** esiste solo nelle gare che possono avere **più gironi** («gironi: fino a 2» o più): con il girone unico non si sceglie. Se una gara col tabellone parte con **un girone solo**, perché gli iscritti sono pochi, il tabellone **non si gioca**: la gara finisce col girone, e la classifica del girone è quella finale (con lo spareggio SSR, se la catena di gara lo prevede). In un campionato che **somma i totali** la fase finale non c'è: la classifica di una gara col tabellone viene dal tabellone, non dai totali. Il campionato a piazzamenti **propone** alle sue gare a girone la fase finale, i qualificati per girone, la finalina e il limite di tempo della fase finale: la gara li riceve quando nasce e li può cambiare (il campionato propone, la gara decide); una gara che nasce a girone unico non riceve il tabellone. Un campionato che passa a **sommare i totali** toglie la fase finale alle gare non ancora avviate, come i gironi tornano uno, e lo scrive nella loro storia. _Nota del 2026-10-12: proposta del campionato e moduli, con l'interfaccia della fase finale._

- **Chi passa**: i primi `K` di ogni girone (di norma 2), fra chi è ancora in gara: chi si è ritirato lascia il posto al successivo del suo girone. `K` va da 1 al numero di giocatori del girone più piccolo. Se all'avvio i gironi composti non lo permettono — 7 iscritti in due gironi da 4 e 3 con `K` = 4 — l'avvio si ferma e il direttore sceglie meno gironi o meno qualificati.
- **Pari merito al taglio**: chi passa fra il `K`-esimo e il `K+1`-esimo di un girone si decide **come in una classifica di turno**: con la **catena di turno** della gara all'ultimo turno dei gironi (di norma principale → differenza → posizione al turno precedente → sorteggio), che lascia sempre un ordine completo. Niente spareggio SSR a metà gara. Lo stesso ordine dice chi è migliore fra i primi dei gironi. _Nota del 2026-10-11: decisione dell'utente («si decide con la catena di criteri: è come se fosse una classifica di turno»), presa sulla prima versione della PR, che usava la catena di gara senza lo SSR e poi il sorteggio._
- **Il tabellone** è a eliminazione diretta, con la taglia della potenza di 2 subito sopra i qualificati (da 2 in su: con due gironi e un qualificato si gioca la sola finale). _Nota del 2026-10-11: «solo con più gironi» è una decisione dell'utente; la prima versione della PR ammetteva il tabellone anche col girone unico._. Le teste di serie si leggono **per colonne**: prima tutti i primi dei gironi, poi tutti i secondi, e così via; dentro una colonna i migliori nell'ordine della classifica a gironi (per partita giocata). Chi viene dallo **stesso girone** si tiene lontano il più a lungo possibile, come nel tabellone finale della formula FISBB: con due gironi e `K` = 2 le semifinali sono **1ºA–2ºB** e **1ºB–2ºA**. Se la gara separa i compagni di squadra, si separano le squadre. Quando i qualificati non sono una potenza di 2 i **bye** vanno alle prime teste di serie: con tre gironi e `K` = 2, ai due migliori primi.
- **La finalina** 3°/4° si gioca se la gara la prevede, nel turno della finale.
- **Turni**: quelli dei gironi più quelli del tabellone, fissati all'avvio: due gironi da 4 con `K` = 2 fanno 3 + 2 turni. Il primo turno del tabellone si avvia, come ogni turno, quando i gironi sono chiusi.
- Nel tabellone **il pareggio non esiste**: le partite si giocano «al N» (con «esattamente N» la gara col tabellone viene rifiutata, come ogni tabellone), e una partita interrotta a tempo in parità la decide il direttore indicando chi passa (vedi «Limite di tempo»).

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
Una variante, sempre per _amalfi_ (e per la strategia _casuale_, ma non per il _round robin_, dove il riposo non vale niente: vedi la nota del 2026-10-11 più sopra) consiste nel gestire la X con una challenge che possa dare un punteggio da zero alla massima differenza rack raggiungibile in quella gara. In questo modo il giocatore abbinato con la X, invece di stare fermo il turno, gioca la challenge e in classifica ottiene il match vinto e un differenza rack pari al punteggio nella challenge. 

**A chi tocca la X nel primo turno** (2026-08-26). Normalmente la decide il sorteggio insieme agli abbinamenti. Quando però la gara usa la strategia _amalfi_ o _casuale_, il primo turno è a sorteggio e i dispari sono gestiti con la X (o con la X con esercizio), all'avvio il direttore può assegnare la X **all'ultimo iscritto** invece di lasciarla al caso: è la risposta a una situazione ricorrente, in cui l'ultimo arrivato è quello che ha completato il numero all'ultimo momento. Il resto degli abbinamenti resta casuale: chi riceve la X viene scambiato di posto con chi l'aveva sorteggiata, e nient'altro si muove. Nella strategia casuale, dove tutti i turni nascono insieme, lo scambio vale per l'intero calendario, così ognuno continua ad avere una sola X e nessuno reincontra nessuno.

Se il numero di giocatori è dispari, si può gestire con diverse opzioni:
- **NO**: i giocatori che rendono dispari vanno in lista d'attesa fino a quando non si iscrive un altro giocatore
- **Bye**: un giocatore salta il turno (solo per sistema WINS: ottiene 1 vittoria, 0 diff rack; vale anche per il sistema POINTS, dove la vittoria dà i suoi punti)
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

Per il sistema POINTS il trio dà i punti dell'esito: la vittoria al vincitore e la sconfitta agli altri due; senza vincitore, il pareggio a chi è a pari merito in testa e la sconfitta al terzo staccato (vedi «Classifica», «La classifica a punti»).

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

> **Nota (2026-09-29, ADR-075).** «Ereditate» vuol dire **copiate quando il match nasce**, non rilette dalla gara a ogni accesso: vale per le due regole qui sopra e per tutte le regole di gioco del match (distanza, «al N» o «esattamente N», disciplina, triangoli per set, handicap, X con prova, categorie dei giocatori per l'ELO). Un cambio della gara vale così per i match che nasceranno, e un match giocato resta con le regole con cui è stato giocato. Una **correzione** di un dato scritto male (gli script `set_gara_*`, la riassegnazione di un partecipante) invece arriva anche ai match già giocati, e resta nella storia della gara.

La **regola di inizio** dice chi esegue il tiro di apertura del primo rack e può essere:
- **"primo giocatore"**: apre il primo dei due, senza sorteggio;
- **"acchito"**: si tira l'acchito. Chi lo vince **sceglie chi** esegue il tiro di apertura, e può scegliere l'avversario. È il default.

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
> **Nota del 2026-09-24.** La regola di inizio predefinita è l'**acchito**. Prima di questa data la specifica non ne indicava una e il codice proponeva «primo giocatore», che nei tornei il direttore doveva cambiare ogni volta (rilievo della gara del 2026-09-23). Il default vale per ciò che nasce: una gara senza campionato creata prima dell'ADR-056, che non ha una regola scritta, continua a cominciare dal primo giocatore.
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

### Limite di tempo

Un **match** può avere un **limite di tempo**, in minuti, **oltre** alla distanza: la distanza resta, e una partita che ci arriva si chiude come sempre. Il limite è facoltativo — senza, il match è quello di sempre — e segue la stessa catena delle altre regole: lo **propone il campionato**, lo **decide la gara** (anche una gara singola), si **fissa sul match quando nasce**. A gara avviata si cambia e vale per i match dei turni successivi. Come la distanza, si può cambiare anche **per un singolo turno**, con tre scelte: come la gara, senza limite, oppure un numero di minuti diverso.

Nelle gare col **tabellone dopo i gironi** la fase finale ha un limite **suo**, con tre scelte: **come i gironi** (il default), **senza limite**, oppure un numero di minuti diverso. L'ordine è: l'override del singolo turno, poi il limite della fase finale, poi quello della gara. I turni del tabellone si conoscono quando si fissano i gironi, all'avvio, e da lì si possono sovrascrivere uno per uno come gli altri (per esempio «finale senza limite»). _Nota del 2026-10-11: regola nuova, con la fase finale dopo i gironi._

Il **conto alla rovescia** parte una volta sola:
- con la regola di inizio **"acchito"**, quando si registra chi l'ha vinto;
- con la regola **"primo giocatore"**, quando uno dei due giocatori o il direttore preme **«Avvia partita»**. Il direttore può premerlo con qualunque regola.

Il timer è **solo un riferimento visivo**, uguale per i due giocatori, per il direttore e sullo schermo in sala. **A tempo scaduto non succede niente da sé**: il match resta in corso, e per il direttore la sua card sale fra quelle da guardare. In questa versione il limite non si applica ai match a set, al trio e alla X.

Il direttore può **interrompere** un match con il limite di tempo, anche prima dello scadere (l'app lo avverte di quanti minuti mancano). Il match si chiude sul punteggio di quel momento:
- chi è avanti **vince**;
- a parità è **pareggio** dove il pareggio è ammesso, cioè fuori dal tabellone (girone all'italiana, Amalfi, casuale);
- nel **tabellone** il pareggio non esiste: a parità il direttore indica chi passa il turno.

Il match interrotto porta il segno **«a tempo»** nei risultati. Il segno vuol dire solo «interrotto dal direttore prima della distanza»: un match che a tempo scaduto arriva comunque alla distanza si chiude come sempre, **senza** il segno. Un match interrotto si corregge come gli altri, con un punteggio che può restare sotto la distanza ma non superarla; corretto fino alla distanza perde il segno.

_Nota del 2026-10-06 (ADR-077): regole nuove, nate dalla gara settimanale «30 minuti per incontro, poi vale il punteggio maturato»._

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

Esistono quattro sistemi di classifica:
- **RACK**: ordina per rack totali vinti (decrescente), poi spareggio
- **WINS**: ordina per match vinti (decrescente), poi differenza rack (decrescente), poi spareggio
- **POINTS**: ordina per punti (decrescente), poi la catena degli spareggi; ogni match dà i punti del suo esito — vittoria, pareggio, sconfitta — di norma **3, 1 e 0**
- **POSITION**: assegna punti per posizione nel tabellone (solo per gare a eliminazione). Come sistema **di un campionato** vuol dire **a piazzamenti**: ogni gara entra nella classifica generale col suo posto finale, qualunque sia il suo formato (vedi più sotto, nota del 2026-10-11)

**La classifica a punti** (2026-10-07, ADR-078). Il criterio principale sono **solo i punti**: le vittorie non contano da sole, e fra chi è a pari punti decide la catena degli spareggi. Quanto vale ogni esito lo **sceglie la gara**, anche una gara singola: punti per la vittoria, per il pareggio e per la sconfitta, numeri interi da 0 a 99, con la vittoria che vale almeno il pareggio, il pareggio almeno la sconfitta, e la vittoria più della sconfitta. Di norma 3, 1 e 0. Il campionato li **propone** alle sue gare, che li ricevono quando nascono (il campionato propone, la gara decide); come il sistema di classifica, a gara avviata non si cambiano. Gli esiti:

- una **vittoria** dà i punti della vittoria, una **sconfitta** quelli della sconfitta;
- la **X** vale una vittoria: i punti della vittoria e zero differenza rack; con l'esercizio al posto della X, i punti della vittoria e la differenza pari al punteggio della prova (la regola della X più sopra, «Strategia di abbinamento»). Nel **girone all'italiana** il riposo vale **zero punti** (nota del 2026-10-11, «Turno»);
- il **pareggio** — a esattamente N rack con N pari, o un match interrotto a tempo a parità fuori dal tabellone (vedi «Limite di tempo») — dà i punti del pareggio a entrambi;
- nel **trio** con un vincitore, lui prende i punti della vittoria e gli altri due quelli della sconfitta. **Senza vincitore**, chi è a pari merito in testa prende i punti del pareggio e il terzo, se è staccato, quelli della sconfitta: a 4-4-1 due pareggi e una sconfitta, a 3-3-3 tre pareggi. Chi si ritira dal trio non è mai in testa, e prende la sconfitta.

Le catene di default sono quelle a vittorie, col principale cambiato: nel turno punti → differenza rack → posizione al turno precedente → sorteggio; nella gara punti → differenza rack → spareggio SSR fino al 3° posto; nel campionato punti → differenza rack → SSR (somma) → posizione dopo la gara precedente → sorteggio. La **classifica generale** di un campionato a punti somma i punti delle classifiche finali delle gare, ciascuno moltiplicato per il peso della gara, come ogni altro numero. I vincoli sono quelli del sistema WINS: X semplice ammessa, match a set, pareggi a distanza pari, strategie _amalfi_, _casuale_ e _round robin_; il tabellone resta a piazzamenti (POSITION). _Nota del 2026-10-07: sistema nuovo, nato dalla gara settimanale «a pari punti conta lo scontro diretto»; nessuna gara esistente lo usa._

**Come si risolvono i pari merito** (2026-10-07, ADR-078). Il sistema dà il **criterio principale** (vittorie, rack vinti o punti); fra chi è pari sul principale decide una **catena di criteri**, applicati uno dopo l'altro. Le classifiche sono tre — del **turno**, della **gara** e del **campionato** — e ognuna ha la sua catena:

| Classifica | WINS | RACK | Chi resta pari |
|---|---|---|---|
| Turno (serve agli abbinamenti) | vittorie → differenza rack → posizione al turno precedente → sorteggio | rack vinti → posizione al turno precedente → sorteggio | nessuno: l'ordine è sempre completo |
| Gara (classifica finale) | vittorie → differenza rack → spareggio SSR fino al 3° posto | rack vinti → spareggio SSR fino al 3° posto | condivide la posizione (1, 2, 2, 4) |
| Campionato (classifica generale) | vittorie → differenza rack → SSR (somma) → posizione dopo la gara precedente → sorteggio | rack vinti → SSR (somma) → posizione dopo la gara precedente → sorteggio | nessuno: l'ordine è sempre completo |

Il **sorteggio** è deterministico: la stessa classifica a ogni lettura, ma non l'ordine di iscrizione. Nel turno e nella gara discende dal seme del sorteggio della gara, nel campionato dal campionato. Lo **spareggio SSR** non entra nella classifica di turno: si gioca a gara finita. Nella gara vale fino al posto indicato (di norma il podio) e, se la gara non prevede lo spareggio, non c'è. Chi non ha tirato viene dopo chi ha tirato e fatto zero.

**Come si mostra il pari merito** (2026-10-11). Sono **a pari merito** i giocatori uguali su tutti i criteri della catena **tranne il sorteggio**. Il sorteggio ordina le righe e decide dove serve una posizione sola — gli abbinamenti del turno, chi passa al tabellone dopo i gironi, gli inviti e la zona playoff, i punti del piazzamento, i premi — ma non toglie il pari merito alla posizione **mostrata**: chi è pari merito si mostra alla **posizione più alta** del gruppo, e lo si dice. Due giocatori con 2 vittorie e +6 che il sorteggio ha messo 1° e 2° sono mostrati entrambi al 1° posto, e il terzo al 3° (1, 1, 3); nella tessera ognuno dei due legge «Sei 1° pari merito su 4» (nel girone, «Sei 1° pari merito su 4 nel girone B»). Vale per ogni posizione mostrata: classifiche del turno e della gara (anche per girone), schermo in sala, tessere, podio, classifica generale del campionato e storico; la freccia di tendenza confronta posizioni mostrate. L'ordine delle righe resta quello della catena, e dove la posizione decide qualcosa decide quella col sorteggio: se due giocatori pari merito all'8° posto si contendono l'ultimo posto nella zona playoff, sono mostrati entrambi all'8° e la riga «Fuori dai playoff» passa fra i due. Chi la catena lascia pari senza sorteggio condivide già la posizione che decide (1, 2, 2, 4), e lì niente cambia. _Nota del 2026-10-11: fino a questa data la posizione mostrata era quella del sorteggio, quindi uno dei due pari merito leggeva «Sei 2°». L'utente ha deciso: «Il pari merito va sempre sulla posizione più alta. Se uno è pari merito col primo allora è primo pari merito, non secondo. La tessera deve dire che è n-esimo pari merito.» Le righe già calcolate si correggono al ricalcolo successivo._

_Nota del 2026-10-07: le catene di turno RACK, l'ultima risorsa del turno e la coda della classifica generale sono cambiate per decisione dell'utente. Prima il turno RACK era «rack → SSR → differenza rack → posizione precedente → id del giocatore», cioè con due criteri che la regola qui sopra non nomina; l'ultima risorsa del turno era l'id, cioè l'ordine di registrazione; nella classifica generale due giocatori pari restavano nell'ordine in cui comparivano nei dati, con posizioni progressive. La classifica di turno WINS e le due classifiche di gara restano quelle di prima._

**Le catene si configurano** (2026-10-07, ADR-078). Quelle della tabella sono le catene **di default**. Il direttore le può cambiare, per ogni gara e per ogni campionato, aggiungendo, togliendo e spostando i criteri: scontri diretti, differenza triangoli, triangoli vinti, vittorie, spareggio SSR fino al N° posto, posizione precedente, sorteggio (la classifica generale di un campionato a piazzamenti ha criteri suoi, vedi «Come una gara entra nel campionato»). Regole:

- il **criterio principale** non entra nella catena: due giocatori ci arrivano proprio perché lì sono pari (a vittorie, «vittorie» non si sceglie);
- il **sorteggio** è sempre l'ultimo; nel turno e nel campionato c'è sempre, anche se nessuno lo sceglie, perché l'ordine dev'essere completo;
- lo **spareggio SSR** compare al massimo una volta e mai nella catena di turno; nella gara ha il suo posto «fino al N°» (di norma 3), nel campionato è la somma degli spareggi delle gare;
- una catena di gara **vuota** è ammessa: chi è pari sul principale resta pari.

La **gara** ha la catena di turno e la catena di gara; il **campionato** le propone alle sue gare, che le ricevono quando nascono e le possono cambiare (il campionato propone, la gara decide), e ha in più la catena della **classifica generale**, che è solo sua. Una gara singola parte dalle catene di default. La catena di gara si cambia finché lo spareggio non è cominciato e vale subito; la catena di turno è una regola di gioco e, a gara avviata, vale **dal turno successivo**: la classifica di un turno già cominciato si fa con la catena di allora, anche se la si ricalcola dopo una correzione. Cambiando il sistema di classifica, una catena che era quella di default del sistema vecchio diventa quella del nuovo; una catena scelta resta, senza il criterio diventato principale. Sul tabellone (POSITION) le catene di turno e di gara non si usano; la catena della classifica generale sì, anche nei campionati a tabellone (2026-10-11). La frase «A pari vittorie conta …, poi …» che ne discende compare nel regolamento e nella pagina pubblica della gara e del campionato.

**Lo scontro diretto** (2026-10-07). Fra i giocatori a pari merito, ogni coppia che si è incontrata dice chi sta davanti: chi ha vinto più scontri fra i due — più partite fra gli stessi due, anche in gare diverse del campionato, si contano tutte; a parità, o con un pareggio, quella coppia non dice niente. La X e il trio non sono scontri, e nel campionato non contano le gare che pesano zero. Chi si è battuto a vicenda in giro (A ha battuto B, B ha battuto C, C ha battuto A) resta pari sullo scontro. Poi si mettono in fila: a ogni passo, fra chi non ha più nessuno davanti per gli scontri, decide il criterio successivo della catena. Così nessun risultato diretto viene rovesciato, e fra chi non si è incontrato decide il criterio dopo. Con due giocatori pari è la regola semplice: se si sono affrontati sta davanti chi ha vinto, altrimenti decide il criterio dopo.

_Nota del 2026-10-07: fino a questa data, fra tre o più pari lo scontro diretto era una mini-classifica sulle partite fra loro, che non decideva se non si erano incontrati tutti. Nessuna gara lo usava: non è nelle catene di default._

_Nota del 2026-10-07: fino a questa data lo spareggio era un interruttore della gara («spareggio sì/no, fino al N° posto») e le catene non si sceglievano. Ogni gara esistente ha ricevuto la catena di gara che riproduce il suo interruttore: con lo spareggio, `differenza → SSR fino al N°` (a vittorie) o `SSR fino al N°` (a triangoli); senza, la stessa catena senza lo spareggio. Nessuna classifica già vista cambia._

**La classifica a gironi** (2026-10-11, ADR-076). In una gara a più gironi le classifiche di turno e di gara sono due classifiche in una:

- **dentro il girone** ognuno si ordina col sistema e la catena della gara, come in un girone unico. Lo scontro diretto vale fra i pari dello stesso girone, che si sono incontrati;
- **nella gara** (senza fase finale) vengono prima tutti i **primi** dei gironi, ordinati fra loro, poi tutti i **secondi**, e così via. Fra gironi di taglia diversa i totali non si confrontano: un girone da 6 gioca 5 partite a testa, uno da 5 ne gioca 4. Il confronto si fa **per partita giocata**: vittorie, rack vinti, differenza rack e punti divisi per le partite giocate davvero. Il riposo non è una partita giocata e non entra né nei numeri né nel divisore; la vittoria a tavolino contro un escluso sì. Esempio: il primo del girone da 6 con 4 vittorie su 5 (12 punti, 2,4 a partita) viene **dopo** il primo del girone da 5 con 4 su 4 (12 punti, 3 a partita), e **prima** di quello con 3 su 4 (9 punti, 2,25 a partita). Fra gironi diversi lo **scontro diretto non decide** — non si sono incontrati — e si passa al criterio dopo; chi resta pari condivide la posizione, come in ogni classifica di gara, e lo spareggio SSR, se c'è, guarda la posizione vera nella gara (i secondi di due gironi sono al 3° posto).

Con il **tabellone dopo i gironi** la classifica finale della gara si compone così (2026-10-11):

- prima chi ha giocato il tabellone, nell'ordine in cui ne è uscito: 1° e 2° dalla finale, 3° e 4° dalla finalina; **senza finalina** i due semifinalisti sconfitti sono **terzi a pari merito**;
- chi esce allo stesso turno prima della semifinale (quarti, ottavi) si ordina per **piazzamento nel girone** — prima i secondi, poi i terzi — e a pari piazzamento come nella classifica a gironi, per partita giocata; chi resta pari condivide il posto;
- poi i **non qualificati**, nell'ordine della classifica a gironi.

Esempio: due gironi da 4, `K` = 2, con finalina. La finale la vince 1ºA su 1ºB, la finalina 2ºB su 2ºA: 1º 1ºA, 2º 1ºB, 3º 2ºB, 4º 2ºA, poi i terzi dei due gironi e infine i quarti. Il sistema di classifica della gara (vittorie, rack o punti) ordina i gironi; il podio lo dà il tabellone, e per questo **lo spareggio SSR non si gioca**, come sul tabellone (ADR-040). Mentre il tabellone si gioca, la classifica del turno mette in cima chi è ancora in corsa, nell'ordine dei gironi; i numeri (vittorie, rack, punti) restano quelli dei gironi. Nel campionato a piazzamenti la gara entra con questo posto.

La classifica di gara conserva per ognuno il **girone** e la **posizione nel girone**. Nella classifica del campionato una gara a più gironi entra col suo **piazzamento**: i gironi esistono solo nei campionati a piazzamenti (vedi sotto, nota del 2026-10-11).

**Come una gara entra nel campionato** (2026-10-11, ADR-080). Un campionato sceglie fra due modi:

- **sommando i totali** (sistema WINS, RACK o POINTS): la classifica generale somma vittorie, rack o punti delle classifiche finali delle gare, ciascuno moltiplicato per il peso della gara. Le gare usano tutte il sistema del campionato e restano a **girone unico**;
- **a piazzamenti** (sistema POSITION): ogni gara dà al giocatore i **punti del posto** che ha preso nella sua classifica finale, con la tabella dei punti per posizione del campionato (di norma 25, 18, 15, 12, poi 8 dal 5° all'8° e 4 dal 9° al 16°), moltiplicati per il peso della gara. Le gare possono avere **formati diversi** nello stesso campionato — _amalfi_, _casuale_, girone all'italiana a uno o più gironi, tabellone — perché ognuna produce una classifica finale completa. Il sistema della gara serve solo a ordinare quella serata: lo **propone il campionato** (vittorie, rack o punti; di norma vittorie) e la gara lo può cambiare; sul tabellone è il piazzamento del tabellone. Chi non gioca una gara prende **zero** punti da quella gara. Chi è a **pari merito** nella classifica finale di una gara — le fasce del tabellone, o chi la catena di gara lascia pari — prende i punti del posto che condivide: due secondi prendono entrambi i punti del 2°. Un posto oltre l'ultimo della tabella vale **zero**. Nella classifica generale a piazzamenti si ordina per **punti**; a pari punti decide la **catena della classifica generale**, che il direttore sceglie come negli altri campionati, ma con criteri suoi:

- **migliori piazzamenti**: chi ha più primi posti; a pari primi posti, chi ha più secondi; poi più terzi, e così via. Il posto è quello della classifica finale della gara: due secondi a pari merito contano entrambi come un secondo posto. Un piazzamento pesa come i punti della gara: una gara a peso zero non conta, una gara a peso 2 conta due volte;
- **posizione dopo la gara precedente**;
- **scontri diretti**, con la regola di sempre (più sotto, «Lo scontro diretto»);
- **sorteggio**, sempre ultimo.

Vittorie, rack e differenza rack **non** sono criteri ammessi, e nemmeno lo spareggio SSR. Di norma: migliori piazzamenti, poi sorteggio. L'ordine è sempre completo, come in ogni classifica generale. _Nota del 2026-10-11: fino a questa data, a pari punti decidevano vittorie e differenza rack sommate su tutte le gare, e chi restava pari condivideva il posto. L'utente ha deciso che non va bene: con gironi di taglia diversa chi sta nel girone più numeroso gioca una partita in più, e porta più vittorie a parità di bravura. In produzione nessun campionato era a piazzamenti, quindi nessuna classifica già vista cambia._

Un campionato che propone il tabellone è sempre a piazzamenti. _Nota del 2026-10-11: fino a questa data il campionato a piazzamenti esisteva solo per i campionati a tabellone, e la regola qui sotto — «tutte le gare usano lo stesso sistema» — valeva per tutti. L'utente ha deciso che sommare i totali di gare con gironi di taglia diversa non è sensato, perché chi sta nel girone più numeroso gioca una partita in più: chi vuole i gironi in un campionato sceglie i piazzamenti, che ammettono ogni formato; chi somma i totali resta a girone unico. I campionati a tabellone già esistenti non cambiano: erano già a piazzamenti._

Nei campionati che **sommano i totali** tutte le gare devono usare lo stesso sistema di classifica *(modificato il 2026-10-11: prima valeva per ogni campionato)*. La gara di playoff lo segue quando il suo punteggio **si somma** a quello del campionato (modalità «Campionato + gara di playoff»), e per questo in quella modalità non può essere a tabellone se il campionato non lo è; quando invece la classifica finale è **solo quella dei playoff** della finale conta soltanto l'ordine d'arrivo, quindi può avere un sistema e una strategia diversi, tabellone compreso (e allora è POSITION, l'unico sistema che un tabellone ammette). Per questo non si passa alla modalità sommata se la finale ha già un sistema diverso da quello del campionato, o una strategia a tabellone. In un campionato **a piazzamenti** la finale entra col suo posto come ogni altra gara, quindi si somma qualunque sia il suo formato. Il resto della finale — turni, distanza, disciplina, gestione dei dispari — si eredita come valore iniziale e si può cambiare in entrambe le modalità. Il sistema del campionato — anche il passaggio fra «sommando i totali» e «a piazzamenti» — si può cambiare finché nessuna gara del campionato è stata **avviata**, anche se ha già degli iscritti *(modificato il 2026-09-29, ADR-075: prima bastava una gara con le iscrizioni aperte)*: dopo, cambierebbe le regole a chi ha già giocato; prima, il cambio arriva a tutte le gare e resta nella storia di ciascuna — passando ai piazzamenti ogni gara tiene il sistema della sua serata; passando a sommare i totali le gare ricevono il sistema del campionato e il girone unico, e una gara a tabellone ferma il cambio *(precisato il 2026-09-14: fino ad allora la gara di playoff nasceva a vittorie qualunque fosse il sistema, e il cambio sul campionato lasciava le gare già create col sistema vecchio)*. La classifica del campionato aggrega sommando le classifiche delle singole gare.

Per i dettagli completi sul sistema di classificazione, vincoli e combinazioni valide, vedi [CLASSIFICATION_SYSTEM.md](CLASSIFICATION_SYSTEM.md).

### Playoff

I **playoff** sono una **gara** speciale a cui per iscriversi occorre avere alcune caratteristiche. Ad esempio un campionato può definire un playoff per i primi 6 classificati. Oppure un playoff Elite per i primi 6 e Academy per i secondi 6. Oppure, ancora, un playoff solo per i giocatori dal terzo posto in giù che hanno partecipato ad almeno 5 gare del campionato.
Alla fine del campionato i giocatori che soddisfano i criteri del playoff ricevono una notifica di accesso ai playoff e possono iscriversi o rifiutare. Nei playoff con un numero limitato di partecipanti (ad esempio i primi 6), se un giocatore rifiuta, la notifica passa al primo degli esclusi e così via fino a quando un numero di giocatori pari ai posti disponibili ha dato l'ok oppure sono finiti i giocatori. 

La gara di playoff **non ha una fase di iscrizioni**: gli iscritti sono chi ha accettato l'invito, quindi la gara nasce in preparazione e il direttore la avvia da lì, senza aprire nessuna finestra; se annulla l'avvio, torna in preparazione. Il playoff si gioca con chi ha accettato, anche se sono meno dei posti: la gara di playoff chiede almeno **due** iscritti, non il minimo delle gare di serata. Gli inviti partono prima che il direttore crei la gara, e le risposte non arrivano tutte insieme: chi accetta dopo la creazione — compreso il primo degli esclusi chiamato da un rifiuto — **entra fra gli iscritti** fino all'avvio del primo turno, e allo stesso modo il direttore aggiunge o toglie qualificati fino all'avvio. **All'avvio** gli inviti ancora senza risposta scadono e nessun altro viene chiamato: la finale è cominciata. Se il direttore **annulla l'avvio**, gli inviti chiusi proprio da quell'avvio tornano in attesa, purché la loro scadenza non sia ancora passata, e chi non aveva risposto può accettare ed entrare come prima; gli inviti scaduti per la loro scadenza o già sostituiti restano come sono. Il limite dei posti vale **per la cascata degli inviti**: chi accetta tardi e trova i posti pieni va in lista d'attesa. Un giocatore **aggiunto a mano dal direttore** entra invece sempre, prima e dopo la creazione della gara, anche oltre i posti, e il massimo della gara non ne blocca l'avvio: è una sua decisione esplicita. La **parità** invece vale anche per lui: se la gara non ammette un numero dispari di giocatori — né X né trio — chi renderebbe dispari gli iscritti aspetta in lista d'attesa come gli altri, finché non arriva un secondo giocatore, e intanto la gara resta avviabile.

> **Nota (2026-09-13).** Fino a questa data la gara di playoff nasceva col minimo di sei iscritti, quindi un playoff da quattro posti non partiva nemmeno con quattro sì; e la lista si congelava alla **creazione** della gara, per cui chi accettava dopo restava confermato ma fuori, senza modo di rientrare. L'ordine «prima gli inviti, poi la gara» resta: cambia il momento in cui la lista si chiude.

> **Nota (2026-09-13, sera).** Fino a questa data per avviare il playoff il direttore doveva **aprire le iscrizioni**, con inizio e fine, su una gara a cui non si iscrive nessuno: inviti, accettazioni e rifiuti erano già avvenuti. Ora la gara di playoff si avvia dalla preparazione e aprirne le iscrizioni è rifiutato. Le gare di playoff già aperte prima di questa data si avviano come prima.

> **Nota (2026-09-16).** Un invito **scaduto** non è definitivo per il direttore: fino all'avvio della gara di playoff può **accettarlo per conto del giocatore**, e chi rientra così entra d'ufficio, anche oltre i posti, con scritto chi ha registrato la risposta. Rifiutarlo non ha senso, perché il posto è già libero e il sostituto, se c'era, è già stato chiamato alla scadenza. Nasce dal campionato 4: la scadenza coincideva con l'orario di gioco, dieci inviti sono scaduti quando il direttore ha aperto la pagina per avviare la finale, e la lista non gli offriva più niente — la finale è stata giocata in una gara a parte. Per lo stesso motivo il foglio della data avverte quando la scadenza coincide con l'orario di gioco o lo supera.

### Challenge

Una **challenge** è una gara di abilità che un giocatore può affrontare da solo. Consiste in una immagine, che mostra la disposizione delle biglie sul tavolo e un testo di spiegazione. È identificata da un nome. 
Ha un punteggio minimo e massimo oppure un superato/non superato. 
I risultati delle **challenge** compaiono nelle statistiche individuali dei giocatori.  
``admin`` può vedere le statistiche delle **challenge** (numero di giocatori che hanno tentato, numero di tentativi, punteggio medio, numero di giocatori con punteggio massimo, punteggio mediano)
Un giocatore può scegliere una **challenge** da un elenco generale o da quelle che ha già provato o dalle sue preferite.
Un giocatore può aggiungere/togliere una **challenge** dalle sue preferite.

> **Nota (2026-09-19) — il profilo dell'esercizio.** Oltre a *come si valuta*, un esercizio dice **che cosa allena**. Ha zero, una o più **abilità** (Fondamentali, Tiro, Battente, Posizione, Sponde, Difesa, Spaccata), **al più tre**, e zero, uno o più **gesti** (stop, stun, follow, draw, spin, forza, bank, kick, jump, massé), senza tetto: i due vocabolari sono fissi di piattaforma. Ha un **livello dichiarato da 1 a 5**, facoltativo; una **famiglia** con un **passo** (da 1 in su), liberi di chi lo crea; e dice se **la bianca** si rimette a ogni tiro o resta dove si ferma. Può avere **varianti** etichettate (destra e sinistra, A e B): sono lo stesso esercizio, e le prove si registrano separate. Una variante che ha già delle prove si rinomina, non si toglie. Gli esercizi nati prima restano senza profilo finché chi li ha creati non lo scrive.
>
> Un giocatore può dare a un esercizio un **voto da 1 a 5**, uno solo, che può cambiare; **vota solo chi l'ha provato**, cioè chi ha almeno una prova conclusa, dal catalogo o in gara. Accanto al voto si mostra **quanti giocatori l'hanno provato**, contati allo stesso modo.

> **Nota (2026-09-20) — la prova fatta di colpi.** Un esercizio dice anche **come si registra**: *col totale* — il punteggio, o l'esito, scritto a fine prova, com'è sempre stato — oppure **colpo per colpo**. Colpo per colpo la prova è una sequenza di **N colpi**, con N fissato da chi crea l'esercizio (da 1 a 100), e ogni colpo ha un esito: **non imbucata**, che vale zero e **non ha una posizione**, oppure **imbucata**, con il punto in cui si è fermata la battente. Il disegno dell'esercizio porta **un bersaglio**, uno solo: un centro sul panno e da uno a cinque **anelli** concentrici di uguale spessore — lo spessore si misura in **quarti di diamante** — ciascuno col suo valore in punti, dal centro verso l'esterno. Il colpo imbucato vale i punti dell'anello in cui si ferma la battente; **sul confine fra due anelli vale quello esterno**; fuori dall'ultimo anello vale zero. I punti si fissano sul colpo quando lo si registra: se poi l'autore sposta il bersaglio, i colpi già tirati valgono quello che valevano. Il punteggio della prova è la **somma dei colpi** e non si scrive a mano; il massimo dell'esercizio è N per il valore più alto. La prova si chiude **con un gesto**, dopo l'ultimo colpo; finché è aperta si può annullare l'ultimo colpo, e una prova lasciata a metà si riprende. Una prova aperta non conta in nessuna statistica.
>
> Da una prova così nascono due percentuali distinte. **Imbucate** = colpi imbucati su colpi tirati. **Posizione** = media, sui **soli colpi imbucati**, di `1 − distanza dal centro ÷ raggio esterno del bersaglio`, mai sotto zero: un colpo non imbucato non ha un punto, quindi non entra. In **esami e gare** un esercizio colpo per colpo si registra ancora col totale digitato, sul massimo derivato.

> **Nota (2026-09-20) — l'esercizio con estrazione.** Un esercizio può avere una **componente casuale, estratta dall'app prima di ogni colpo**. Chi lo crea dichiara da una a tre **liste** di voci già scritte a parole («1 sponda», «2 sponde», «3 o più sponde»; «bilia 1» … «bilia 10»), ciascuna con almeno due voci, e una **scala di esiti**: da due a otto voci con un nome e un valore in punti da 0 a 99, di cui almeno una maggiore di zero. Prima di ogni colpo l'app pesca **una voce da ogni lista, indipendentemente**, e le compone in una consegna: «3 o più sponde, bilia 7». A colpo tirato si sceglie l'esito, e il colpo vale i punti di quella voce. Il punteggio della prova è la somma dei colpi e il massimo è i colpi per il valore più alto della scala. La consegna in attesa **si persiste**: ricaricare la pagina non la cambia, e annullare un colpo la rimette in attesa com'era.
>
> **In esami e gare un esercizio con estrazione non si può mettere**: a due persone uscirebbero consegne diverse, quindi prove non confrontabili, e lì si certifica e si fa classifica. Nell'allenamento in autonomia quella stessa casualità è il senso dell'esercizio.

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

> **Nota (2026-09-29, ADR-075).** «Precompilati» vale per **tutti** i valori del campionato: chi apre, chi spacca e l'handicap, che fino a questa data la gara lasciava vuoti e rileggeva dal campionato a ogni accesso, ora si copiano come gli altri. Il campionato **propone**, la gara **decide**. Quando il direttore cambia un valore del campionato, le gare già create non cambiano da sole: l'app propone a quali, fra quelle non ancora avviate, applicarlo, gara per gara, con già spuntate quelle che avevano il valore di prima. Il campionato non si blocca più alla prima gara con le iscrizioni aperte. Fanno eccezione il sistema di classifica (sotto) e locandina e link, che seguono il campionato in diretta.

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