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
iscritti, classifica a **vittorie**, spareggio SSR **fino al terzo posto**.

Due conseguenze della configurazione che conviene avere chiare prima di
cominciare, perché non sono ovvie e non sono errori:

* **Distanza esatta, non «al N».** La partita finisce quando i rack giocati
  sono N, non quando uno arriva a N. Alla distanza 5 un 3-2 è una partita
  chiusa; il quinto rack si gioca sempre, anche quando il risultato è già
  deciso.
* **Alla gara 2 il pareggio esiste.** Sei è pari: un 3-3 chiude la partita
  senza vincitore. Nelle gare a distanza 5 non può capitare. Vale anche per il
  secondo turno della gara 4 e della finale.

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

## Journey 4 — Chiudere la gara, e lo spareggio

**Quando**: a fine serata. **Chi**: il direttore.

1. Giocato l'ultimo rack del terzo turno, il direttore **apre la pagina della
   gara** — che non è un gesto decorativo: è l'apertura della pagina a scrivere
   la classifica di turno, e senza di quella il turno successivo non parte.
2. Preme **«termina»**. Se in cima alla classifica ci sono pari merito nelle
   prime tre posizioni, il pulsante **rifiuta** e rimanda allo spareggio.
3. Il direttore **avvia lo spareggio**, inserisce i punteggi di ogni gruppo di
   pari merito, e a spareggi risolti la gara si chiude.

Con la classifica a vittorie e tre turni i pari merito in cima sono la norma,
non l'eccezione: **lo spareggio è parte della serata**, non un imprevisto.

→ `chiudi_gara` in `tests/new/e2e/campionato_driver.py`, usato da
`tests/new/e2e/test_stagione_e2e_stagione.py`

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
6. Crea la **gara di playoff**, che nasce con i confermati già iscritti.

**Variante**: il direttore può saltare del tutto gli inviti e comporre la lista
a mano dall'inizio. È il percorso di chi la finale se la organizza al telefono.

**Casi limite coperti**: lo stesso giocatore aggiunto due volte; un giocatore
che il campionato non l'ha giocato; la lista che si congela appena la gara di
playoff è creata; un giocatore che prova ad avviare i playoff (403).

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
