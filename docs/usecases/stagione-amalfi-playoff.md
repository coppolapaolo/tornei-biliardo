# Una stagione Amalfi con playoff — gli user journey

Questo documento descrive, dal punto di vista di chi la vive, la stagione che
il direttore ha in programma: **quattro gare Amalfi da tre turni, con playoff
finale per i primi otto**. Non è una specifica di prodotto e non decide niente:
racconta i percorsi, e ciascuno rimanda ai test end-to-end che lo percorrono
davvero, solo con richieste HTTP.

I casi d'uso generali del prodotto stanno in [`gare.md`](./gare.md). Questo è
il seguito di **UC4**, che si ferma alla classifica di campionato e non arriva
ai playoff.

---

## La configurazione

| | Gara 1 | Gara 2 | Gara 3 | Gara 4 | Playoff |
|---|---|---|---|---|---|
| Disciplina | Palla 8 | Palla 9 | Palla 10 | per turno | per turno |
| Distanza | **esatti** 5 | **esatti** 6 | **esatti** 5 | per turno | per turno |
| Turno 1 | — | — | — | Palla 8, esatti 5 | Palla 8, esatti 5 |
| Turno 2 | — | — | — | Palla 9, esatti 6 | Palla 9, esatti 6 |
| Turno 3 | — | — | — | Palla 10, esatti 5 | Palla 10, esatti 5 |

Uguale per tutte: formato **Amalfi**, **tre turni**, dispari gestito **con la
X** (chi resta spaiato vince a tavolino), **minimo 6** e **massimo 15**
iscritti, classifica a **vittorie** (a parità, differenza triangoli), spareggio
SSR **fino al terzo posto**, **handicap acceso**.

Due conseguenze della configurazione che conviene avere chiare prima di
cominciare, perché non sono ovvie e non sono errori:

* **Distanza esatta, non «al N».** La partita finisce quando i rack giocati
  sono N, non quando uno arriva a N. Alla distanza 5 un 3-2 è una partita
  chiusa; il quinto rack si gioca sempre, anche quando il risultato è già
  deciso.
* **Alla gara 2 il pareggio esiste.** Sei è pari: un 3-3 chiude la partita
  senza vincitore. Nelle gare a distanza 5 non può capitare. Vale anche per il
  secondo turno della gara 4 e della finale.
* **L'handicap non cambia le distanze.** È la cosa che il nome suggerisce e che
  l'applicazione non fa: nessuno gioca al 5 contro uno che gioca al 3. Il flag
  governa le **categorie** degli iscritti e, tramite quelle, l'**Elo**. Le
  distanze restano quelle della gara, uguali per tutti.

La specifica in forma eseguibile sta in `tests/new/e2e/stagione.py`: è l'unica
copia: se il calendario cambia si cambia là, e tutti i test seguono.

---

## Journey 1 — Il direttore prepara la stagione

**Quando**: una volta, prima della prima serata. **Chi**: il direttore, da solo.

1. Apre il **wizard del campionato**. Nel primo passo dà il nome, dichiara
   quattro gare in programma, sceglie **Amalfi**, classifica a **vittorie**, e
   accende il **playoff Elite a 8**. Nel secondo passo imposta i default che le
   gare erediteranno: tre turni, dispari con la X, anti-reincontro acceso.
2. Crea le **quattro gare** una alla volta, ciascuna con la sua data — che deve
   crescere col numero, perché le gare numerate di un campionato stanno in
   ordine cronologico. Per ognuna sceglie disciplina, distanza, spunta
   **«numero esatto di rack»**, mette minimo 6 e massimo 15, accende lo
   spareggio fino al terzo posto, e dichiara gli otto tavoli della sala.
3. Sulla **quarta gara** apre il pannello degli override e configura i tre
   turni uno per uno. Questo si può fare **solo finché la gara è in setup**:
   dopo l'avvio il pannello rifiuta le modifiche, perché cambiare il formato a
   metà gara falserebbe i turni già giocati.

**Cosa può andare storto qui**: una gara datata prima della precedente viene
rifiutata; un override su un turno che non esiste (il quarto, di una gara che
ne ha tre) viene rifiutato; una gara Amalfi senza anti-reincontro non si crea.

→ `tests/new/e2e/test_stagione_e2e_configurazione.py`

---

## Journey 2 — La serata: dalle iscrizioni al primo turno

**Quando**: ogni martedì. **Chi**: il direttore e i giocatori.

1. Il direttore **apre le iscrizioni** della gara di serata.
2. I giocatori si iscrivono **ciascuno dal proprio telefono**. Chi non ce l'ha,
   o chi paga al banco, lo **iscrive il direttore** al posto suo.
3. Chi cambia idea **si toglie da solo**; chi non si presenta lo **cancella il
   direttore**.
4. Il sedicesimo finisce in **lista d'attesa**, e ci finisce anche se a
   iscriverlo è il direttore: l'iscrizione d'ufficio non scavalca la capienza.
5. Quando la sala è pronta il direttore **avvia il primo turno**. Il sorteggio
   abbina i giocatori, assegna un tavolo a ogni partita, e — essendo gli
   iscritti dispari — assegna **la X** a uno di loro, che vince a tavolino.

**Il caso limite della serata storta**: alle 21 gli iscritti sono cinque. Il
pulsante «avvia» rifiuta, dice che ne servono almeno sei, e **la gara resta in
iscrizione**: non si rompe niente, e appena arriva il sesto — che il direttore
può iscrivere lui — la gara parte. Vale anche al contrario: sei iscritti e uno
che si cancella all'ultimo riportano sotto il minimo.

→ `tests/new/e2e/test_stagione_e2e_iscrizioni.py`

---

## Journey 3 — Segnare i risultati

**Quando**: durante tutta la serata. **Chi**: i giocatori al tavolo, il
direttore dal suo posto.

La stessa partita si può chiudere da cinque strade, e non sono equivalenti:

1. **I due giocatori segnano rack per rack** dal telefono. Arrivati alla
   distanza la partita **non è chiusa**: serve la firma di tutti e due. Una
   firma sola non basta.
2. **Il direttore segna rack per rack**. Qui la partita si chiude subito: è già
   la parola del direttore, e non c'è nessuno che debba confermargliela.
3. **Il direttore mette il risultato secco**. In «esattamente N» il totale deve
   fare **esattamente N**: un 5-3 alla distanza 5 viene rifiutato con un
   messaggio, non accettato in silenzio.
4. **Il direttore valida** una partita che i giocatori hanno lasciato a metà.
5. **Uno dei due si ritira**: perde, e i rack non giocati vanno all'altro, così
   la somma resta N.

E si torna indietro in tre modi: **l'avversario rifiuta** il risultato (sparisce
l'ultimo rack e la partita riapre), **il giocatore annulla** il proprio ultimo
rack, **il direttore resetta** l'intera partita.

**Il caso limite del reset tardivo**: una volta avviato il turno successivo, il
reset di una partita del turno precedente è **bloccato**. In Amalfi il turno 2
nasce dalla classifica del turno 1: cambiarla a posteriori renderebbe gli
abbinamenti già estratti il frutto di una classifica che non esiste più.

**I tavoli**: il direttore può ridefinire i tavoli della sala fino all'avvio,
spostare una partita su un altro tavolo, e — se quel tavolo è già occupato da
un'altra partita dello stesso turno — le due si **scambiano**, che è il gesto
vero di chi gestisce la sala, non un errore. Un tavolo si può anche togliere.

→ `tests/new/e2e/test_stagione_e2e_risultati.py`

---

## Cosa vale la X, e come Amalfi decide chi incontra chi

Due dettagli del motore che cambiano la classifica, e che conviene conoscere
prima di spiegarli in sala.

**La X vale una vittoria — e oggi anche i triangoli della distanza.** Chi resta
spaiato entra in classifica con una vittoria *e* con `+5` di differenza
triangoli (`+6` nella seconda gara), perché la partita con la X nasce col
punteggio pieno a favore e nessun triangolo subìto. Siccome la classifica
ordina per `(vittorie, differenza triangoli)`, a parità di vittorie **chi ha
riposato sta davanti a chiunque abbia vinto giocando**: la X vale come la
vittoria più larga possibile. È un rilievo aperto — l'attesa è che valga una
vittoria e differenza **zero** — ed è fissato da un test `xfail(strict=True)`
che diventerà il test di regressione il giorno in cui si decide di cambiarlo.
La correzione tocca `ScoreAggregator._process_bye_match` e sposterebbe le
classifiche di tutte le gare con numero dispari, quindi è una decisione, non
una svista da correggere di nascosto.

Quel che invece è già garantito: **nessuno prende la X due volte** nella stessa
gara.

**Gli abbinamenti seguono la classifica col «salto».** Il primo turno è
sorteggiato. Dal secondo in poi Amalfi abbina secondo la classifica del turno
precedente con un salto che si accorcia: `turni_totali − turno + 1`, quindi 2 al
secondo turno e 1 al terzo. Con un numero **pari** di giocatori il sorteggio
risolve un matching di peso massimo sul grafo dei non-incontri: fra tutti gli
accoppiamenti senza reincontri sceglie quello che minimizza lo scarto
complessivo dal salto — ed è verificato per confronto, enumerando tutte le
combinazioni possibili.

**Attenzione al caso dispari**, che è quello della stagione con quindici
iscritti: la garanzia anti-reincontro di ADR-029 vale per il caso **pari**. Con
un numero dispari il sentinella della X viene aggiunto dopo quel controllo e si
prende la strada greedy, dove l'anti-reincontro è un tentativo — con un
fallback esplicito che *ammette* il reincontro quando le combinazioni si
esauriscono. Nei test con sette giocatori e tre turni non succede mai, ma la
differenza fra «garantito» e «finora è sempre riuscito» va conosciuta.

→ `tests/new/e2e/test_stagione_e2e_x_e_abbinamenti.py`

---

## Journey 4 — Chiudere la gara, e lo spareggio

**Quando**: a fine serata. **Chi**: il direttore.

1. Giocato l'ultimo rack del terzo turno, il direttore **apre la pagina della
   gara** — che non è un gesto decorativo: è l'apertura della pagina a scrivere
   la classifica di turno, e senza di quella il turno successivo non parte.
2. Preme **«termina»**. Se in cima alla classifica ci sono pari merito nelle
   prime tre posizioni, il pulsante **rifiuta** e rimanda allo spareggio.
3. Il direttore **avvia lo spareggio**, inserisce i punteggi di ogni gruppo di
   pari merito, e a spareggi risolti la gara si chiude.

Quando serva lo spareggio dipende dai risultati, non dal formato. Nel sistema
a vittorie due giocatori sono pari merito solo se hanno **le stesse vittorie e
la stessa differenza triangoli** (`SpareggioService._group_by_classification`
raggruppa sulla coppia): con punteggi vari la differenza triangoli separa quasi
sempre, e lo spareggio resta l'eccezione. Diventa invece sistematico se tutte
le partite finiscono con lo stesso margine — per esempio tutte 3-2 su una
distanza 5 — perché in quel caso la differenza triangoli è solo
`vittorie − sconfitte` e il secondo criterio smette di discriminare.

→ `chiudi_gara` in `tests/new/e2e/campionato_driver.py`, usato da
`tests/new/e2e/test_stagione_e2e_stagione.py`

---

## Journey 4-bis — Le categorie dell'handicap

**Quando**: prima di avviare il primo turno di ogni gara. **Chi**: il direttore.

1. La gara ha l'handicap perché lo ha il campionato: il campo della gara resta
   su «eredita», che non è «no».
2. Scendendo l'elenco degli iscritti, il direttore scrive la categoria accanto
   a ciascun nome. **Non c'è un elenco da preparare prima**: la categoria nasce
   quando la si scrive sul primo iscritto, e dal secondo in poi si trova già in
   tendina. Il combo salva sul posto, senza ricaricare la pagina.
3. Finché qualcuno è senza categoria la pagina lo dice, con il conteggio
   aggiornato a ogni salvataggio: *«N iscritti su M non hanno una categoria: le
   loro partite non conteranno per l'Elo, e dopo l'avvio non potrai più
   cambiarle»*.
4. **All'avvio del primo turno la finestra si chiude.** Le categorie decidono
   quali partite contano per l'Elo: cambiarle dopo sarebbe riscrivere le regole
   a partita in corso.
5. Dalla seconda gara in poi il lavoro è quasi tutto fatto: iscrivendosi, ogni
   giocatore **si porta dietro la categoria** della gara precedente dello
   stesso campionato. Il direttore corregge solo chi è cambiato di categoria, e
   la correzione non tocca le gare già giocate.

**Cosa cambia davvero**: l'Elo si aggiorna **solo fra giocatori della stessa
categoria**. Fra categorie diverse la partita vale per la classifica di gara ma
non tocca il rating, perché il risultato riflette l'handicap e non la forza. E
senza categoria il rating non si muove: «non lo so» non è «sono uguali».

→ `tests/new/e2e/test_stagione_e2e_handicap.py`

---

## Journey 5 — La fine della stagione e i playoff

**Quando**: dopo la quarta gara. **Chi**: il direttore, poi gli otto invitati.

1. Chiusa la quarta gara, il direttore **termina il campionato**. La classifica
   generale si consolida: quindici righe, posizioni da 1 a 15.
2. Preme **«avvia playoff»**. I primi otto ricevono l'invito.
3. Ciascun invitato apre l'invito e **accetta o rifiuta**.
4. Nella realtà le risposte arrivano parziali: cinque accettano, uno rifiuta,
   due non rispondono. **Il silenzio non vale come sì**: chi non risponde non
   entra nella finale.
5. Il direttore **completa la lista da sé**: toglie chi non ha risposto e
   aggiunge chi ha detto di sì a voce. Chi aggiunge lui entra **già
   confermato**, senza passare dall'invito.
6. Crea la **gara di playoff**, che nasce con i confermati già iscritti. Non
   serve aspettare tutte le risposte: chi accetta **dopo** — anche il primo
   degli esclusi chiamato da un rifiuto — entra fra gli iscritti, e il
   direttore può ancora aggiungere o togliere qualificati.
   Chi il direttore aggiunge a mano entra anche oltre gli otto posti: il
   limite vale per la cascata degli inviti, e chi accetta tardi trovando i
   posti pieni va in lista d'attesa. La parità invece vale per tutti: se la
   finale non ammette dispari, chi il direttore aggiunge da solo aspetta un
   secondo giocatore, e la gara intanto resta avviabile.
7. **Avvia** la finale. Da quel momento la lista è chiusa: gli inviti rimasti
   senza risposta scadono, nessuno viene più chiamato, e si gioca con chi
   c'è anche se sono meno degli otto posti — la gara di playoff chiede almeno
   due iscritti, non i sei delle serate — o più, se il direttore ne ha
   aggiunti. Se **annulla l'avvio**, gli inviti chiusi da quell'avvio tornano
   in attesa fino alla loro scadenza; quelli scaduti per scadenza o già
   sostituiti no.

**Variante**: il direttore può saltare del tutto gli inviti e comporre la lista
a mano dall'inizio. È il percorso di chi la finale se la organizza al telefono.

**Casi limite coperti**: lo stesso giocatore aggiunto due volte; un giocatore
che il campionato non l'ha giocato; la lista che si chiude all'avvio della
gara di playoff, non alla sua creazione; un giocatore che prova ad avviare i
playoff (403).

> *Emendato il 2026-09-13*: fino ad allora la lista si congelava alla creazione
> della gara, e la gara nasceva col minimo di sei iscritti. Chi accettava tardi
> restava fuori e un playoff con meno di sei sì non partiva.

→ `tests/new/e2e/test_stagione_e2e_stagione.py`, classe `TestIPlayoffDeiPrimiOtto`
→ `tests/new/e2e/test_campionato_e2e_playoff.py` per le varianti della lista

---

## Journey 6 — La finale a tre turni diversi

**Quando**: la sera del playoff. **Chi**: il direttore e gli otto qualificati.

1. La gara di playoff eredita dal campionato disciplina, distanza, numero di
   turni e formato — ma **non** gli override per turno: quelli appartengono
   alla gara che li ha, non al campionato.
2. Il direttore quindi **riconfigura i tre turni a mano** sulla finale, che
   nasce in setup e quindi li accetta ancora.
3. Apre la finestra di iscrizione — la gara nasce con dentro i qualificati, ma
   il dominio ammette solo il passaggio *iscrizione → in corso* — avvia, e si
   giocano i tre turni.

→ `tests/new/e2e/test_stagione_e2e_stagione.py`, classe `TestLaFinaleATreTurniDiversi`

---

## Cosa questi journey **non** coprono

Dirlo esplicitamente serve a non scambiare il verde della suite per una
garanzia più ampia di quella che è.

* **Il trio.** La stagione usa la X, non il match a tre: il trio ha i suoi test
  altrove (`test_gara_e2e_interazioni.py`), e le sue route sono altre.
* **Il browser.** Questi test parlano HTTP: verificano le route, i permessi, i
  redirect e ciò che la pagina contiene, non il JavaScript né il rendering. Il
  segnapunti dal vivo, il polling e i modali restano una verifica manuale.
* **Le notifiche e le email.** Che l'invito ai playoff generi una notifica è
  coperto altrove a livello di servizio; qui si guarda l'effetto sul dominio.
* **La chiusura finale del campionato.** Un campionato con playoff resta in
  stato «Terminato» e non passa a «Completato»: il metodo che lo farebbe non è
  collegato a nessuna route. È un rilievo aperto, non un comportamento voluto.
* **Il carico.** Quindici iscritti sono il massimo previsto, non un test di
  carico.
* **L'handicap sui punteggi.** Non esiste nel prodotto e qui non è simulato: se
  un giorno servisse far giocare due categorie a distanze diverse, è una
  funzione da progettare, non un test da aggiungere.
