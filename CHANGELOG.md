# Changelog

Tutte le modifiche degne di nota a questo progetto sono annotate qui.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e il
versionamento segue [Semantic Versioning](https://semver.org/lang/it/).

> **Questo file si scrive a mano** ed è il posto in cui una modifica viene
> raccontata: cosa cambia per chi usa l'app, e perché è stata fatta così.
>
> Il numero di versione, invece, non lo decide più nessuno a mano: lo calcola
> release-please dai titoli delle PR unite (`fix:` alza la patch, `feat:` la
> minor, `feat!:` la major) e lo scrive in `config.py`, da dove arriva nel
> footer di ogni pagina. L'elenco secco dei rilasci con le PR che li compongono
> sta in [`docs/RELEASES.md`](docs/RELEASES.md), generato dal bot: è un indice,
> non un racconto — questo resta il racconto.

## [Non rilasciato]

### Corretto

- **Tolti i playoff, il campionato restava «In attesa dei playoff» per
  sempre.** Se dopo «Passa alla fase playoff» il direttore toglieva l'unica
  configurazione, il campionato non si chiudeva più e mostrava una linguetta
  Playoff vuota: una configurazione disattivata contava ancora come un playoff
  da giocare. Ora contano solo quelle attive, e il campionato terminato risulta
  completato (PR #733).
- **La partita riaperta riprende il tavolo.** Annullando l'ultimo triangolo di
  una partita già chiusa con la doppia conferma, la partita si riapriva senza
  tavolo — passato nel frattempo alla prima in attesa — e il tabellone lasciava
  solo annullare, non segnare. Ora riprende il suo tavolo se è libero,
  altrimenti un altro; e se non ce n'è nessuno continua lo stesso, perché il
  tavolo serve per cominciare una partita, non per finirla. Quando il tavolo
  non è quello di prima i direttori ricevono un avviso. Vale anche per il trio
  (PR #729).
- **L'admin elimina un utente dalla sua scheda, e la conferma dice chi.** Il
  cestino stava in fondo a una riga di quindici colonne, dove il nome non si
  vedeva più, e il dialogo chiedeva di eliminare «questo utente» senza
  nominarlo: sbagliare riga era facile e niente lo faceva notare. Ora l'elenco
  non scorre di lato — sul telefono è una pila di card — e il nome porta alla
  scheda, dove sta l'eliminazione: il foglio di conferma dice chi è, quante
  iscrizioni e partite ha e che cosa succede, e il pulsante porta il suo nome.
  Anche i messaggi dopo unione, promozione e verifica dell'email nominano
  l'account (PR #728).
- **La registrazione non rivela più quali email sono sul sito.** Registrandosi
  con un indirizzo già presente la pagina rispondeva «email già in uso», e
  chiunque poteva scoprire chi ha un account. Ora risponde come a una
  registrazione riuscita e non crea niente: è al proprietario dell'indirizzo
  che arriva una mail, con scritto che qualcuno ha provato a registrarsi e i
  collegamenti per entrare o recuperare la password. Dal profilo, inoltre, non
  si può più prendere l'email di un altro account: prima nessuno controllava, e
  nascevano due account con lo stesso indirizzo (PR #719).
- **Chi si registrava non riceveva la mail di verifica.** Il codice di verifica
  veniva creato, ma la mail partiva solo modificando l'email dal profilo. Ora
  parte alla registrazione (PR #708).
- **Sul telefono «Inizia a segnare» era alto 23 pixel invece di 56.** Nella
  barra in fondo alla pagina i pulsanti messi in colonna si schiacciavano; sul
  desktop non si vedeva. Lo stesso difetto stava in altre quattro pagine:
  proposta e modifica di una sfida, modulo e dettaglio di un esercizio (PR
  #696).
- **La vetrina della gara mostrava solo il co-direttore sotto «Organizza»**,
  senza il titolare; e il riquadro delle informazioni, nelle gare di
  campionato, faceva il contrario e taceva i co-direttori. Ora tutte e due
  elencano chi dirige davvero: prima i titolari, poi i co-direttori (PR #694).
- **La classifica decisa dalla finale dei playoff mostra i numeri della
  finale.** Dove è la finale a decidere la classifica del campionato, la pagina
  mostrava solo vittorie e differenza della stagione, e l'ordine dei primi non
  si spiegava. Ora chi ha giocato la finale sta in una fascia propria, «Decisa
  dalla finale», con le colonne della finale, e sotto c'è «Poi l'ordine del
  campionato» con le colonne di sempre. Chi è pari merito in finale resta pari
  merito anche nel campionato: prima li separava un numero interno, senza
  nessun significato di gioco (PR #690).
- **Il tabellone non si accavalla più.** Sul desktop la casella «chi vince A –
  B» sbordava su quella accanto, sul telefono l'ultima colonna restava
  tagliata, e sullo schermo in sala, a gironi finiti, le classifiche dei gironi
  si sovrapponevano sotto il tabellone. Nello stesso giro: un campionato a
  piazzamenti si presenta come «A piazzamenti» invece che col formato di una
  sola delle sue serate, e la sua classifica non ha più la colonna della
  differenza triangoli, che lì non decide niente; sulla card di una partita a
  tempo scaduto il tavolo resta al suo posto (PR #686).
- **Quattro difetti visti guardando le schermate della guida.** Il trio diceva
  «2 gironi» per i suoi giri, la stessa parola dei gironi della gara. In
  inglese le posizioni uscivano senza suffisso («You are 2 of 6»): ora «2nd»,
  «3rd», «11th». Il riquadro degli orari di una partita rimetteva nei campi
  l'ora UTC e salvava come UTC quella digitata, due ore fuori d'estate
  (ADR-043). E la stessa quota si leggeva «€30.00» in una pagina e «30 €» in
  un'altra (PR #684).
- **Chi usa l'app in inglese leggeva ancora molto italiano.** I nomi dei
  formati uscivano grezzi («Round Robin», «Direct Elimination») o diversi dalla
  guida («Random» dove dappertutto si dice «Casuale»); i messaggi della
  gestione di una gara — avvio dei turni, iscrizioni, spareggio, ritiri, trio —
  erano frasi italiane composte a mano, e così l'errore generico del server.
  Ora passano tutti dal catalogo delle traduzioni, e i formati hanno un nome
  solo in ogni pagina. Per strada: nella gara singola a triangoli spariva la
  voce dei dispari che il server avrebbe rifiutato, e l'editor delle catene
  degli spareggi sul telefono non spezza più i nomi lettera per lettera (PR
  #605, #651, #653, #655).
- **Una gara coi turni tutti modificati si presentava col formato che nessun
  turno gioca.** Testata, card, elenchi e storico dicevano disciplina e
  distanza con cui la gara era nata, anche quando i tre turni giocavano altro.
  Ora il formato si ricava dai turni: se sono uguali fra loro si dice quello,
  se cambiano si elencano le discipline e si scrive «distanze diverse per
  turno». Il formato della gara resta dove è davvero un valore predefinito: nei
  moduli (PR #634, #635).
- **Un aggiornamento interrotto a metà lasciava il sito mezzo vecchio e mezzo
  nuovo.** L'8 ottobre l'aggiornamento notturno ha scaricato il codice nuovo e
  poi si è fermato, correttamente, perché il servizio che ferma il sito non
  rispondeva. Ma un sito non riavviato non resta sul codice vecchio: usa i
  moduli già caricati e legge dal disco i template nuovi, e tre pagine davano
  errore. Ora ogni uscita anticipata riporta il disco al codice di prima, e il
  giro successivo riparte da capo (PR #632).
- **Il girone all'italiana tiene il calendario fissato all'avvio.** Il
  calendario si rifaceva a ogni turno a partire dagli iscritti rimasti: il
  primo turno ignorava il sorteggio appena fatto, e se un giocatore veniva
  escluso le coppie dei turni dopo cambiavano, con reincontri e incontri mai
  giocati. Ora l'ordine è quello dell'avvio e chi esce resta al suo posto nel
  calendario. Inoltre un girone con la classifica a triangoli si ordinava sulle
  vittorie, come ogni altro girone: ora sui triangoli (PR #612, #614).
- **«Valida risultato» mancava sulle partite finite in pareggio.** Con
  «esattamente N» e N pari una partita può finire 3-3: la card della gara la
  dava «da validare», ma nella pagina della partita il pulsante compariva solo
  se c'era un vincitore (PR #615).
- **Gli avvisi dei traguardi KPI non arrivavano a nessun admin**, e il
  traguardo risultava comunque già segnalato: l'avviso era perso per sempre. La
  ricerca degli admin a cui mandarlo non trovava mai nessuno, e per lo stesso
  motivo una scheda della pagina KPI mostrava sempre zero utenti (PR #603).
- **Il direttore di un campionato poteva toccare i playoff di un altro.** Sei
  azioni dei playoff — aggiungere o togliere un giocatore, rispondere per suo
  conto, cambiare punteggio o configurazione, disattivare — verificavano il
  permesso sul campionato dell'indirizzo, ma non che la configurazione fosse la
  sua: bastava cambiare un numero. Ora una configurazione di un altro
  campionato risulta non trovata (PR #583).
- **Le conferme non passano più dal dialogo del browser.** Il 27 settembre, in
  produzione, un «Accetta» non faceva niente, con i log puliti: dopo qualche
  conferma di fila il browser aveva offerto «impedisci altre finestre di
  dialogo», e da lì ogni conferma rispondeva di no in silenzio. Ora la forma
  della conferma la decide l'azione: se è frequente e si può disfare parte dopo
  tre secondi con «Annulla» accanto; se tocca altri o non si disfa apre un
  foglio dell'app, e il pulsante porta il nome dell'azione invece di «OK». In
  tre pagine di schede e gruppi, poi, la conferma non compariva affatto e
  l'azione partiva al primo tocco (ADR-074, PR #559).
- **Le pagine in inglese si dichiaravano italiane.** L'attributo `lang` era
  fisso su `it`: chi aveva scelto l'inglese se lo sentiva leggere dal lettore
  di schermo con la pronuncia italiana, e il browser gli proponeva di tradurre
  «dall'italiano». Ora segue la lingua scelta.
- **Gli inviti ai playoff non tenevano conto della X.** La classifica in
  pagina conta la X come una vittoria, come dice la specifica; quella da cui
  partono gli inviti la scartava. Chi aveva avuto una X aveva una vittoria in
  meno proprio al momento di decidere chi entra: nel campionato 5 l'ottavo
  posto, che la pagina dava a serpico67, è andato a RIZA. Ora le due
  classifiche contano la X allo stesso modo, anche per le gare minime.
- **La classifica generale del campionato è una sola.** Profilo, export e
  inviti ai playoff leggevano una classifica calcolata a parte, con regole
  proprie, che poteva dire una cosa diversa dalla pagina: oltre alla X,
  ignorava lo spareggio (a pari merito passava chi si era registrato prima) e
  contava anche le gare ancora in corso. Ora è la copia esatta della classifica
  in pagina. Nei campionati a piazzamenti la pagina usa la tabella punti della
  specifica (25, 18, 15, 12…), la stessa del profilo, e i pari merito
  condividono la posizione; nessun campionato in corso è a piazzamenti. Una
  gara chiusa con meno turni del previsto ora entra nella classifica generale
  (ADR-073).
- **Gli esercizi fra i turni davano 404 ai giocatori**, e solo in produzione:
  le due pagine con cui si registra un tentativo non erano dichiarate
  nell'elenco degli endpoint visibili, quindi l'app le nascondeva a tutti
  tranne l'admin. In sviluppo il controllo è disattivato, per questo non si era
  mai visto (#469, ADR-028).
- **Un esercizio già usato in un esame risultava «mai utilizzato».** Le prove
  d'esame non sono tentativi del catalogo, e chi contava gli usi guardava solo
  quelli: cancellare quell'esercizio se lo portava via insieme alla voce
  dell'esame e ai risultati già dati. Ora contano anche esami e schede (#511).
- **Di un esercizio si modificava solo il disegno**, le statistiche davano
  errore, «Esami» non compariva nel menu del telefono e la guida aveva testi
  corrotti da una rinomina («dgli esercizi»). Erano quattro difetti che
  arrivavano dalla stessa rinomina mai completata (#470).
- **Chi svuota il tavolo senza premere «G» ora vede il triangolo vinto**: il
  motore del referto leggeva un valore in cache prima di ricalcolare quali
  tasti fossero ammessi (#476).
- **Chi ha nominato chi adesso si vede.** I ruoli delegabili erano generici nel
  meccanismo ma scritti a mano nei tre posti che li usano: l'admin non poteva
  far partire la catena degli istruttori, la pagina che mostra «concesso da»
  non era raggiungibile da nessun collegamento, e in produzione un istruttore
  avrebbe preso 404 proprio sull'approvazione della richiesta di un collega
  (#526, ADR-041 emendato).
- **Invitare a una sfida un giocatore che non esiste** dà un errore chiaro
  invece di fallire più avanti (#485).
- **All'avvio del turno il primo tavolo finiva a due partite e l'ultimo
  restava vuoto** (gara 3 della Ronin Cup, 16/09/2026). La X si chiude da
  sola mentre il turno sta nascendo, e ogni chiusura riassegna i tavoli
  liberi alle partite già create; subito dopo l'avvio del turno ripartiva dal
  primo tavolo senza guardare quelli occupati. Succedeva solo con la X in
  mezzo agli abbinamenti, per questo non si era mai visto. Ora l'avvio parte
  dai soli tavoli liberi (#459).
- **All'acchito, sul tabellone orizzontale, dopo la prima risposta non si
  andava avanti**: per proseguire serviva «Comincia», nella fascia in basso,
  che su iPhone può finire sotto la barra del browser. Ora si risponde
  toccando i nomi tutte e due le volte, il primo tocco dice chi ha vinto e il
  secondo chi apre; nella fascia resta «Ricomincia». Il tabellone si misura
  sull'altezza visibile dello schermo (#461, emendamento all'ADR-056).
- **La vetrina di una gara a turni misti mostrava la sola disciplina
  predefinita**: la riga «Formato» non sapeva delle configurazioni per turno.
  Ora nomina le discipline e le elenca turno per turno; e in una gara a set un
  turno modificato non mostra più i triangoli al posto dei set (#463).
- **Una regola dei ritiri sconosciuta finiva sulla gara in silenzio** e
  faceva fallire il primo ritiro a gara in corso. Ora il form la rifiuta
  subito. In produzione non era capitato: l'interfaccia manda i valori
  giusti (#466).

### Modificato

- **Il pari merito si mostra sempre sulla posizione più alta.** Chi è pari col
  primo è «1° pari merito», non secondo: le posizioni si leggono 1, 1, 3. Sono
  pari merito due giocatori uguali su tutti i criteri tranne il sorteggio, che
  continua a ordinare le righe e a decidere dove il posto è uno solo —
  abbinamenti, inviti e zona playoff, punti del piazzamento non cambiano. Lo
  dicono classifiche, schermo in sala, tessera («Sei 1° pari merito su 4»),
  podi, storico e profilo. Anche le bande del tabellone seguono la regola: i
  quattro usciti ai quarti leggono «5° pari merito» invece di «5°–8°» (PR #661,
  #667; ADR-078 e ADR-040 emendati).
- **Nel girone all'italiana il riposo non vale niente.** Con un numero dispari
  di giocatori chi riposava riceveva la X, cioè una vittoria: fra gironi di
  taglia diversa era una vittoria regalata a chi stava nel girone dispari. Ora
  il riposo è un turno senza partita — zero vittorie, zero punti, zero
  triangoli — e ognuno ne fa uno. Chi doveva incontrare un giocatore escluso
  vince a tavolino, alla distanza del turno. La X con esercizio nel girone non
  si può più scegliere. In produzione non c'erano gironi già giocati, quindi
  nessuna classifica è cambiata (PR #637).

### Aggiunto

- **I playoff si cambiano dal modulo di modifica del campionato.** In fondo al
  modulo c'è il riquadro «Playoff finali»: finché il campionato è in corso il
  direttore modifica una configurazione, la toglie o ne aggiunge una, per
  allargare o restringere i playoff secondo la partecipazione, oppure toglierli
  e chiudere il campionato sulle sole gare. Le regole lo permettevano già prima
  degli inviti; mancava un posto da cui farlo (#732, PR #734).
- **Il testo segue «Dimensioni testo» dell'iPhone.** Ogni misura del testo era
  scritta in pixel, e una pagina web segue quell'impostazione solo se lo
  chiede: chi alzava il cursore per leggere senza occhiali doveva zoomare a due
  dita. Ora il testo cresce col cursore fino a un terzo in più; titoli e cifre
  grandi crescono meno, come nelle app native, e oltre quel tetto resta lo
  zoom. Alla misura normale l'app è identica a prima. Perché le pagine
  reggessero col testo grande pulsanti e pillole hanno un'altezza minima invece
  che fissa, e tre difetti che si vedevano già prima sono spariti: il punteggio
  «4 – 3» spezzato accanto a un nome lungo, «Iscrizioni aperte» fuori dalla sua
  pillola, l'etichetta su due righe fuori dal pulsante (PR #723).
- **Il campionato propone il primo abbinamento delle gare.** Un campionato
  Amalfi può far partire il primo turno di ogni gara dalla classifica generale
  scegliendolo una volta sola, invece che gara per gara: è un valore proposto
  come gli altri, che la gara riceve quando nasce e può cambiare. La partenza
  «dalla classifica» legge ora la stessa classifica generale della pagina, e
  non più una sua copia che poteva essere rimasta indietro (PR #692; ADR-073,
  ADR-075).

#### Sfide, certificazione e giocatori senza account (16–25/10/2026)

In sala si gioca spesso con qualcuno che l'app non la usa. Fino a ottobre
quella partita o non si poteva segnare, o restava appesa a una firma che non
sarebbe mai arrivata, bloccando anche le successive; e il profilo non
distingueva un risultato garantito da un direttore di gara da uno dichiarato da
un giocatore solo. I casi d'uso stanno in
[`sfide-e-certificazione.md`](docs/usecases/sfide-e-certificazione.md).

- **I numeri del profilo dicono quanto sono certificati.** Un risultato vale
  quanto chi lo garantisce: un direttore di gara, i due giocatori che firmano,
  o solo chi l'ha segnato. In testa al profilo, proprio e altrui, il selettore
  **Tornei · Confermate · Tutte** cambia insieme ELO, vittorie, sconfitte,
  pareggi, TPA, runout e partite recenti; le viste sono cumulative e la
  predefinita è «Confermate», cioè quello che il profilo mostrava già. Una
  sfida firmata da uno solo entra in «Tutte» col risultato dichiarato, e
  «Tutte» ha un ELO suo. Per strada: TPA e runout contavano anche sfide
  annullate o mai firmate (PR #698, #700; ADR-083).
- **Una firma che non arriva non blocca più.** Chi ha firmato una sfida può
  aprirne un'altra con lo stesso avversario, mentre chi deve ancora firmare
  viene riportato a quella da chiudere; e una sfida rimasta senza seconda firma
  si può **ritirare**, con un avviso all'altro. Alla prima firma parte la
  richiesta di conferma a chi manca, e una sfida giocata fino in fondo non si
  chiama più «in corso»: sta in una sezione sua, «In attesa di conferma». Dopo
  la doppia firma, invece, la sfida non si tocca più — né ritiro né triangoli
  tolti — perché l'ELO si è già mosso. La doppia conferma resta la difesa
  contro chi bara: nessuno firma al posto di un altro (PR #697, #703, #716,
  #717; ADR-051 emendato).
- **Il video della partita e una riga che dice che partita è.** Sfide e partite
  di gara possono avere un collegamento a YouTube, che si apre in una scheda
  nuova e si aggiunge anche a partita chiusa. Le sfide hanno in più una
  descrizione di una riga, che si legge nella testata, negli elenchi e nello
  storico del profilo (PR #705).
- **Istruttori e direttori tengono il TPA della partita di altri due.** Da
  «Segna la partita di altri due» si scelgono i due giocatori e la partita
  nasce col referto aperto. Chi segna non firma per nessuno: chiudere il
  referto dichiara il risultato, e ciascuno dei due lo conferma o lo rifiuta
  per sé. Se uno rifiuta vale il rifiuto: la partita sparisce ai due giocatori,
  tutti vengono avvisati, e chi l'ha segnata la corregge — e la conferma si
  richiede da capo — o la cancella. L'admin non segna partite, per la regola di
  sempre: nell'app l'admin non è un giocatore (PR #706, #710; ADR-084).
- **Il referto TPA a tutto schermo.** Mentre si compila, la testata della
  pagina sparisce: chi è al tavolo lo dicono già le card dei giocatori. Alla
  distanza il referto si chiude da solo, e se la chiusura era sbagliata
  «Annulla l'ultima e riapri il referto» la disfa. L'ultima annotazione si
  annulla toccando le sue caselle o con «Annulla l'ultima», fra Indietro e
  Avanti; per tre secondi una riga dice che cosa è stato tolto e offre
  «Rimetti». Prima un tavolo passato per sbaglio non aveva un rimedio rapido
  (PR #714; ADR-044 emendato).
- **Si gioca anche con chi non ha un account.** Direttori e istruttori creano
  un **giocatore non ancora registrato** scrivendo nome e cognome: iscrivendolo
  a una gara, direttamente dalla ricerca degli iscrivibili, o mettendolo in una
  partita. Non entra nell'app e non riceve notifiche, ma le sue partite, le
  classifiche e l'ELO sono veri, e accanto al nome c'è il segno «non
  registrato». Chiunque può sceglierlo come avversario dell'avvio rapido — non
  di una proposta, a cui non potrebbe rispondere — e quella sfida si chiude con
  la sola firma di chi l'ha aperta: è «registrata da uno», e conta solo nella
  vista «Tutte» (PR #707, #712, #716, #720, #730; ADR-085).
- **Chi si registra riscatta il suo giocatore.** Accanto a un non registrato le
  pagine pubbliche mostrano «Sei tu? Riscatta»: si crea l'account o si entra, e
  la richiesta parte da sola. Decide chi aveva creato quel giocatore, e l'admin
  può sempre farlo; confermare porta sul nuovo account iscrizioni, partite,
  classifiche ed ELO. Chi ha chiesto può ritirare la richiesta. Dopo il
  riscatto il giocatore rivede le partite che altri avevano registrato per lui,
  e le riconosce — diventano confermate — o le contesta. Chi invece ha già la
  sua email scritta sul giocatore lo **attiva** da un collegamento ricevuto per
  posta, scegliendo nome utente e password: nessuna unione, le partite sono già
  sue. Per chi era già in archivio — iscritto a qualche gara ma mai entrato
  nell'app — c'è uno script, da lanciare in produzione, che lo segna come non
  registrato e ricostruisce dalla sua prima gara chi può confermarne il
  riscatto (PR #708, #709, #716, #717, #719, #720, #725; ADR-086).

#### Gironi, tempo, quote, spareggi e preset (6–12/10/2026)

Un piano solo, nato da una formula vera: la serata del lunedì di una sala, a
gironi con le finali, che l'app non sapeva condurre. Per arrivarci sono serviti
i gironi multipli, il limite di tempo, il listino delle quote, pari merito che
il direttore potesse decidere, e un campionato capace di mettere insieme serate
di formato diverso.

- **Più gironi nel girone all'italiana.** Il direttore fissa un tetto, «fino a
  N gironi», e come comporli — sorteggio, per ELO, per categoria; il numero
  esatto lo sceglie all'avvio, quando sa quanti sono venuti, e il foglio gli
  mostra per ogni scelta taglie e turni («2 gironi · 5 turni — Girone A: 6 ·
  Girone B: 5»). I gironi giocano in parallelo, ognuno con la sua classifica
  nelle pagine della gara e sullo schermo in sala; la tessera dice «Sei 2° su 6
  nel girone B». La classifica della gara mette prima tutti i primi e poi tutti
  i secondi, confrontati **per partita giocata**: in un girone da sei si gioca
  una partita in più che in uno da cinque (PR #639, #641, #643; ADR-076).
- **Dopo i gironi, il tabellone o le finali per piazzamento.** Con più gironi
  la gara può avere una fase finale. Col **tabellone** passano i primi K di
  ogni girone, con le teste di serie distribuite perché chi viene dallo stesso
  girone si ritrovi il più tardi possibile; a gironi finiti le classifiche
  dicono chi va «al tabellone» e chi è «fuori». Con le **finali per
  piazzamento**, per due gironi, il primo dell'uno incontra il primo
  dell'altro, il secondo il secondo, e ogni posto lo assegna una partita;
  accanto a ogni nome c'è già la finale che giocherà. Fase finale e finale
  possono avere distanza e limite di tempo propri («finale al 7, senza
  limite»), e la tessera dice il nome del turno: «La tua partita · Semifinale».
  Con una fase finale lo spareggio non si gioca (PR #656, #662, #665, #669,
  #671, #673, #675; ADR-081).
- **Il campionato a piazzamenti accoglie serate di ogni formato.** Sommare
  vittorie e triangoli di gironi di taglia diversa non è giusto: chi sta nel
  girone più numeroso gioca una partita in più. Per questo il campionato ora
  sceglie *come le gare entrano* in classifica: sommando i totali, e allora
  tutte le gare hanno lo stesso sistema e un girone solo, oppure **a
  piazzamenti**, dove ogni serata dà i punti del posto finale e può essere
  Amalfi, casuale, a gironi o a tabellone — formato e classifica si scelgono
  nel modale «Nuova gara». A pari punti decide chi ha più primi posti, poi più
  secondi, e così via: non più vittorie e triangoli sommati, per la stessa
  ragione (PR #645, #647, #649; ADR-080).
- **Il limite di tempo.** Accanto alla distanza una gara può avere un limite in
  minuti, anche diverso turno per turno. Il conto alla rovescia parte
  all'acchito o con «Avvia partita» e si vede sotto il punteggio, sul
  tabellone, sulla card del direttore e sullo schermo in sala. È **solo
  visivo**: a tempo scaduto la partita resta in corso, e la card sale fra
  quelle che il direttore deve guardare. È lui, se vuole, a interromperla:
  vince chi è avanti, a parità è un pareggio — nel tabellone indica chi passa —
  e la partita porta il segno «a tempo» (PR #617, #619, #621; ADR-077).
- **Il listino delle quote per categoria.** Oltre alla quota unica, una gara
  singola o un campionato possono avere un listino («Serie A 30 € · Serie B e C
  20 € · Amatori 15 €») che prende il suo posto su vetrina, tessere e
  informazioni. È solo informazione: niente incassi, niente «ha pagato». Per
  averlo le categorie esistono ora anche senza handicap, e lì non toccano l'ELO
  (PR #622; ADR-079).
- **I pari merito li decide una catena di criteri che il direttore sceglie.**
  Turno, gara e campionato hanno ciascuno la sua: differenza, triangoli vinti,
  vittorie, scontri diretti, spareggio fino al N° posto, posizione precedente,
  e in fondo un sorteggio. Si compone nei moduli spostando i criteri, e il
  regolamento ne scrive la frase («A pari vittorie conta …»). Prima le regole
  erano fisse, e l'ultima risorsa era l'ordine di registrazione dei giocatori;
  ora è un sorteggio che dà sempre lo stesso esito. Lo scontro diretto ordina
  solo ciò che i risultati dicono: fra tre giocatori che si sono battuti in
  cerchio non decide, e si passa al criterio successivo. Le gare esistenti
  hanno ricevuto la catena che riproduce il loro comportamento di prima (PR
  #624, #626, #628; ADR-078).
- **La classifica a punti.** Un sistema nuovo accanto a vittorie e triangoli:
  ogni partita dà i punti del suo esito, di norma 3 per la vittoria, 1 per il
  pareggio e 0 per la sconfitta, e si ordina solo su quelli; i pari li scioglie
  la catena. I valori si scelgono sulla gara, proposti dal campionato (PR #630;
  ADR-078 emendato).
- **I preset dei direttori.** Chi organizza ogni settimana la stessa serata
  salva la configurazione — «Salva come preset» — e la volta dopo riparte da lì
  con «Parti da un preset», nei moduli della gara e del campionato, playoff
  compresi. Il preset precompila soltanto: nome, data, sala e tavoli restano da
  scrivere, il modulo si controlla come sempre e nessuna gara resta legata al
  preset da cui è nata. In «I miei preset» si rinominano, duplicano e
  cancellano; condividerne uno con un altro direttore gliene dà una **copia**,
  che da lì è sua (PR #679, #681, #688; ADR-082).

#### Le impostazioni si correggono, e resta scritto (29/09/2026)

Una gara con gli iscritti dentro non si poteva più toccare. Il 28 settembre, in
produzione, della finale dei playoff appena creata — che nasce con dentro chi
ha accettato l'invito — non si riusciva a cambiare né la sala né chi spacca. Un
solo blocco chiudeva insieme una ventina di campi diversi: le correzioni oneste
erano impossibili, e l'aggiramento, cancellare e rifare, era peggio, perché un
blocco si vede e un aggiramento no. La scelta è stata rovesciare il mezzo:
quasi tutto si può correggere, e ogni correzione **resta scritta** — chi,
quando, da cosa a cosa — dove tutti la leggono. Resta fermo solo ciò che non
può cambiare davvero, come le regole di una partita già giocata (ADR-075,
[`docs/usecases/regolamento-di-gara.md`](docs/usecases/regolamento-di-gara.md)).

- **La gara si corregge anche con gli iscritti, e anche a gara avviata.** Fino
  all'avvio si cambia tutto. Dopo, sala, orario e quota cambiano subito; le
  regole di gioco — distanza, disciplina, chi spacca — valgono **dal turno
  successivo**, finché ce n'è uno da avviare: con la strategia casuale i turni
  nascono tutti insieme, e lì le regole non si cambiano più dopo l'avvio. La
  struttura, cioè formato e numero di turni, solo annullando l'avvio. La
  pagina mostra ciò che si può ancora cambiare ed elenca col motivo
  ciò che non si cambia più; in fondo c'è la storia delle modifiche. Se due
  direttori salvano insieme, il secondo non cancella più la modifica del primo
  (PR #585, #588).
- **Una partita giocata resta con le regole con cui è stata giocata.** Chi
  apre, chi spacca, la distanza del set e le categorie dei giocatori si fissano
  sulla partita quando nasce. Prima la partita le rileggeva dalla gara ogni
  volta: cambiare una regola avrebbe riscritto anche le partite di ieri, ELO
  compreso (PR #586).
- **Il campionato propone, la gara decide.** I valori del campionato si copiano
  sulla gara quando nasce. Cambiandoli dopo, una pagina elenca le gare non
  ancora avviate, campo per campo: già spuntate quelle che avevano il valore
  vecchio, non quelle che ne avevano scelto uno proprio. Il campionato non si
  blocca più con gli iscritti (PR #589).
- **Anche i playoff.** A inviti partiti si bloccano solo i criteri di
  qualificazione — chi entra non si ridiscute — mentre come si gioca la finale
  si corregge fino al suo avvio, e se la finale esiste già la correzione le
  viene proposta (PR #591).
- **A gara finita si corregge quanto conta.** Di una gara conclusa in un
  campionato si può ancora cambiare il peso, e così i punti per posizione: la
  classifica si ricalcola e lo dice, col peso di prima barrato accanto al nuovo
  e una riga «Classifica ricalcolata il …» con autore e motivo. Se il ricalcolo
  cambia chi rientra nei posti dei playoff, il direttore riceve una proposta —
  chi perde l'invito, chi lo riceve — che può eseguire o lasciar cadere (PR
  #592).
- **Gli iscritti lo sanno, con una notifica sola.** Le modifiche a una gara si
  raccolgono e partono mezz'ora dopo l'ultima, o subito con «Invia ora», o
  subito se la gara è entro tre ore: sala A → B → C arriva come «A → C», e A →
  B → A non manda niente. Si annuncia ciò che cambia la serata di un giocatore,
  non un ritocco al nome. E se prima dell'avvio cambiano data o sala, l'orario
  si sposta di più di un'ora o la quota sale, l'iscritto trova «La gara è
  cambiata: ci sei ancora?»: finché non risponde il direttore lo vede «da
  riconfermare», e nessuno viene ritirato in automatico. Uno spostamento più
  piccolo, o una modifica a gara avviata, manda solo la notifica (PR #594,
  #595).
- **Una data che scavalca le gare successive propone di spostarle.** Prima
  c'era solo il rifiuto; ora il modulo mostra quali gare si sposterebbero e a
  quando, e il direttore sceglie. Alzando la capienza, poi, chi è in lista
  d'attesa entra da solo, in ordine (PR #596; ADR-016 emendato).
- **Il regolamento è una pagina pubblica.** «Regolamento di gara» e
  «Regolamento del campionato», aperte anche a chi non ha un account, mostrano
  le regole in vigore — turno per turno, se cambiano — e la storia delle
  modifiche; un campo nuovo permette di collegare il documento completo (PR
  #597, #599).

#### Allenarsi nell'app (19–20/09/2026)

Fino a settembre l'app sapeva fare tornei. Chi voleva usarla il mercoledì, per
allenarsi da solo o con un istruttore, trovava un catalogo di esercizi con
poche funzioni e un referto TPA che nessuno aveva mai ripensato. In due giorni
sono state disegnate 46 schermate su un canvas, congelate venti decisioni e
portate a termine undici fasi di lavoro, una per sessione. Il piano e lo stato
schermata per schermata stanno in
[`docs/redesign-7c/canvas-tpa-esercizi/`](docs/redesign-7c/canvas-tpa-esercizi/PIANO.md).

- **Il referto TPA si compila con una mano sola.** Il tastierino è uno solo,
  sempre tutto visibile, su tre colonne come l'app Accu-Stats da cui viene il
  motore: prima su schermo largo si stirava su sei colonne e i tasti non
  premibili sparivano invece di spegnersi. Il tavolo si passa **toccando il
  riquadro del giocatore** in alto, senza un pulsante apposta; il TPA sta su
  scala 0–1000 e ha la stessa evidenza del punteggio, perché è il numero per
  cui si compila un referto. Si torna indietro a rileggere — e rileggere è
  **sola lettura**: per ricominciare da un turno del passato si dice
  esplicitamente, così guardare non sposta mai il punteggio della partita. Su
  schermo largo il referto sta a fianco del tavolo, e a partita chiusa diventa
  un racconto con i numeri di ciascuno, non sommati (PR #475, #478, #479,
  #481, #482, #483; ADR-044 emendato).
- **Gli esami hanno una pagina per ogni momento.** L'esame si compone in una
  pagina sola, scegliendo gli esercizi per nome invece di scriverne l'ID a
  mano; il catalogo dice, esame per esame, che cosa sei tu — candidato,
  esaminatore, nessuno dei due. L'appuntamento si accetta **dentro la card
  della proposta**, e la controproposta si fa con tre campi, giorno, ora e
  sala. La sessione mette a fuoco un esercizio per volta, col tastierino
  agganciato in basso, e l'esito si dà dal riepilogo. Con una sessione
  certificata aperta la composizione aspetta: cambiare le regole a esame in
  corso sarebbe cambiare la prova sotto i piedi di chi la sta sostenendo
  (PR #484, #486, #487, #488, #489; ADR-042 emendato).
- **Un esercizio dice che cosa allena.** Abilità e gesto vengono da un
  vocabolario fisso, il livello è dichiarato da chi lo scrive, e le varianti
  — destra e sinistra, A e B — sono **etichette dello stesso esercizio**, non
  un secondo esercizio da tenere allineato a mano. Creare, modificare e
  duplicare passano da un modulo solo; se il cambiamento toccherebbe prove già
  registrate l'app lo dice e chiede se copiarle o sovrascriverle, invece di
  decidere da sé. L'area si apre su **«Oggi»**, con dietro il catalogo che si
  filtra per abilità, gesto, livello e voto. E un esercizio si vota da 1 a 5
  **con cinque bilie** — gli oggetti del gioco al posto delle stelle — ma solo
  dopo averlo provato (PR #490, #492, #494, #496, #498; ADR-065).
- **Una prova si può fare colpo per colpo.** Si tocca il panno dove si è
  fermata la bianca, e il punteggio **discende dai colpi** invece di essere
  digitato: è lo stesso rapporto che c'è fra il referto TPA e il punteggio di
  una partita. L'app può anche estrarre la consegna a ogni colpo, con la
  richiesta scritta a parole e conservata. A fine sessione il tavolo mostra la
  nuvola dei punti d'arrivo, letta in una frase: lungo o corto è forza, di lato
  è mira (PR #501, #503, #504, #507, #508, #509; ADR-066).
- **Le schede di allenamento.** Una scheda ha **una forma sola** — livello,
  soglia, giorni e durata sono interruttori, non schede diverse — e si compone
  come un esame, con lo stesso oggetto. La seduta si segna con un tocco per
  casella, e il registro dice com'è andata voce per voce e da che parte si
  sbaglia. Quando si segna, la casella **copia la misura e il «su quanto»**, e
  una voce che ha registrazioni si ritira invece di sparire: è ciò che rende
  il registro ancora leggibile fra sei mesi (PR #511, #513, #514, #515, #516;
  ADR-067).
- **L'andamento, gli obiettivi e i consigli.** Un radar dice dove sei forte,
  mettendo prove del catalogo e caselle delle schede **su una scala sola** — la
  quota di ciò che era ottenibile, dove 12 su 15 e 4 su 5 tiri valgono lo
  stesso 80% — senza però fonderle mai su un esercizio: media e record restano
  quelli del catalogo. Un obiettivo si sceglie da sé e ha una barra che si
  riempie; i traguardi premiano la **tenuta** e non solo la quantità; e l'app
  stima quanto è difficile davvero un esercizio dai risultati di chi l'ha
  provato, per dire che cosa conviene fare oggi (PR #517, #519, #520, #521,
  #522; ADR-068).
- **Istruttori e allievi.** Il ruolo di istruttore non apre niente: rende
  **trovabili**. Il legame nasce sempre dall'allievo, che apre una sua scheda a
  un istruttore e può richiuderla quando vuole; «I miei istruttori» e «I miei
  allievi» sono la stessa riga letta dai due lati. L'istruttore ordina gli
  allievi in gruppi, vede un triage in tre sezioni e i numeri del corso, e
  **propone** una scheda invece di assegnarla: nasce quando l'allievo accetta,
  e nasce sua. Il passaggio di livello si sancisce — per soglia o con un gesto
  dell'istruttore — e resta timbrato anche se le sedute dopo vanno peggio
  (PR #523, #525, #528, #530, #531, #532, #534; ADR-069, ADR-070, ADR-071).
- **Il disegnatore degli esercizi parla la lingua dell'app.** Colori dal design
  system invece di una tavolozza sua; sul telefono il tavolo sta in cima, gli
  strumenti in una striscia che scorre, e sotto restano le proprietà del solo
  strumento acceso — prima il tavolo finiva sotto «Salva». Il **bersaglio è un
  dato**, in due forme che fanno due domande diverse: i cerchi chiedono *quanto
  vicino* e graduano, il riquadro chiede *dentro o fuori* e non gradua. Con
  loro arrivano posizioni numerate, richiami col filo legato, marcatori,
  varianti ribaltate e l'inquadratura, che ritaglia l'immagine e non il tavolo
  su cui si lavora (PR #536, #538, #540, #541; ADR-065 e ADR-066 emendati).
- **La guida racconta tutto questo**, in italiano e in inglese, con le
  schermate catturate dall'app su un dataset dimostrativo. Ha una sezione nuova
  **«Insegnare»**, e il seed ha ora un istruttore vero con sei allievi, ognuno
  messo lì per illustrare una frase della guida (PR #483, #489, #498, #509,
  #516, #522, #534, #541).

- **Sul telefono si resta collegati**: la casella «Resta collegato su questo
  dispositivo», spuntata per default, tiene la sessione per trenta giorni
  dall'ultimo uso. Prima il cookie nasceva senza scadenza e iOS lo buttava a
  ogni chiusura dell'app, quindi in sala si rifaceva l'accesso a ogni
  dall'ultimo uso. Prima il cookie nasceva senza scadenza e iOS lo buttava a
  ogni chiusura dell'app, quindi in sala si rifaceva l'accesso a ogni
  apertura, con i suggerimenti di due gestori di password che l'app non
  chiedeva. L'admin resta scollegato dopo mezz'ora di inattività (#460,
  ADR-064).
- **La card del direttore risponde al tocco.** Il numero cambia subito, non
  quando risponde il server, e i tocchi ravvicinati non si perdono. Il tocco
  che porta alla distanza aspetta tre secondi, con «Si chiude fra 3 s» e
  «Annulla» accanto; a chiusura confermata la card dice «Partita chiusa» e
  solo dopo la pagina si aggiorna. Prima la card spariva in fondo all'elenco
  senza che si capisse se l'ultimo + era andato (#462).

- **Il direttore che non dirige un campionato non aveva «Dettagli» sulle
  tessere delle sue gare**, nemmeno su quella a cui era iscritto: restava solo
  «Disiscriviti», senza una via per l'elenco degli iscritti, e sul campionato
  un pulsante «Classifica» spento. Le pagine sono aperte a tutti, e ora i
  pulsanti ci sono per tutti.
- **La barra della zona playoff saltava dei giocatori**: nella classifica
  generale segnava chi era fra i primi in un ricalcolo vecchio delle righe
  persistite, ferme a prima dell'ultima gara, e non chi è fra i primi nella
  classifica mostrata. Ora la zona si calcola dalla stessa classifica che la
  pagina disegna. Gli inviti non erano a rischio: l'avvio dei playoff
  ricalcola le righe prima di leggerle (PR #433).
- **Un'operazione che salvava dentro un'altra poteva lasciare i dati a
  metà o perderli**: se falliva l'esterna restavano scritti i passi interni,
  e se falliva un passo interno si perdeva il lavoro fatto prima. Ora salva
  solo l'operazione più esterna, e le reazioni automatiche a un risultato,
  come notifiche e punti, non possono più cancellarlo (ADR-061, PR #385).
- **Trio**: se il punteggio più alto è di due o tre giocatori nessuno prende
  la vittoria, come dice la specifica; prima decideva lo scontro diretto,
  anche quando il direttore inseriva solo i totali (PR #388).
- **Con la distanza «esattamente N» la card del direttore rifiutava ogni
  triangolo** perché pretendeva subito il totale finale (PR #389).
- **Un playoff con meno accettazioni dei posti non partiva**, perché la gara
  nasceva col minimo di sei iscritti; e chi accettava dopo la creazione della
  gara restava fuori in silenzio (PR #390).
- **Le notifiche arrivavano nella lingua di chi aveva premuto il pulsante**,
  con gli orari in UTC in alcune di esse; ora nella lingua e nel fuso di chi
  le riceve (ADR-062, PR #391).
- **Nella lista dei parimerito compariva l'HTML della pastiglia «pari»** al
  posto della pastiglia (PR #393).
- **Nel wizard di una nuova gara di campionato l'auto-copia degli iscritti
  nasceva accesa** e copiava gli iscritti se il direttore non la toglieva
  (PR #394).
- **Il direttore non vedeva «Iscriviti» sulle gare che dirige**; e sul
  playoff la tessera mostrava «Disiscriviti» anche a chi ci entra solo per
  invito (PR #395).
- **Il tavolo liberato non passava alla partita in attesa** quando la
  partita si chiudeva con la doppia firma, per esempio dal segnapunti del
  direttore che gioca (PR #396).
- **Annullando un allenamento un giocatore poteva tenere punti non suoi**,
  scambiati con quelli di un esercizio di gara (PR #387).

- **Sul telefono le righe delle partite troncavano nome e cognome**: ora i
  due nomi vanno uno sopra l'altro (PR #364).
- **La formula dei dispari compariva col valore grezzo inglese** («Bye With
  Challenge») in cinque schermate; ora ha i suoi nomi: lista d'attesa, X a
  tavolino, X a tavolino con esercizio, trio. Tutti i moduli di gare e
  campionati leggono le stesse voci (PR #364, #367).
- **L'export CSV del profilo perdeva le partite confermate dai due
  giocatori**: contava solo quelle chiuse dal direttore (PR #364).
- **Il modulo di modifica del campionato non aveva la lista d'attesa**: un
  campionato nato così, salvato, passava in silenzio alla X (PR #367).
- **Trio**: il risultato inserito dal direttore ignorava i turni bloccati e
  i trio già chiusi e non avvisava gli altri telefoni; l'azzeramento
  rispondeva con un errore del server; la correzione delle partite a set
  era bloccata solo nel template; una partita al meglio dei set a triangoli
  esatti risultava «alla distanza» a 1–1 (PR #368).
- **Doppio KO**: fra la finale e la bella la fascia proponeva di avviare un
  turno che non esiste (PR #363).
- **Una gara di un campionato si poteva spostare prima della precedente**
  modificandola: l'ordine delle date si controllava solo alla creazione
  (ADR-016, PR #373).
- **Sul desktop le card delle partite si schiacciavano** a 1024 e 1280: nomi
  troncati, il + fuori dal lato, stato e tavolo attaccati. Ora le card vanno
  affiancate solo dove ci stanno (PR #375).
- **Esercizi**: il direttore che non è amministratore, dalla pagina della
  partita, finiva sull'indirizzo del giocatore e riceveva un rifiuto, o
  registrava a proprio nome il tentativo dell'avversario; l'indirizzo del
  direttore accettava tentativi di chi non gioca la gara; il punteggio
  massimo dell'esercizio non era applicato, i negativi passavano, e un
  «riuscito/non riuscito» senza esito diventava «non riuscito» in silenzio
  (PR #377).
- **Eliminare una gara in preparazione con un turno modificato o degli
  esercizi rispondeva con un errore del server**; il forfait di un giocatore
  poteva sovrascrivere una partita già confermata da entrambi; togliendo la
  squadra a un iscritto il direttore leggeva «Giocherai senza squadra»
  (PR #379).
- **Difetti trovati rifacendo la pagina gara del direttore** (PR #345,
  #347, #349, #358, #360). All'avvio della gara un giocatore ritirato
  contava per il minimo e finiva nell'ordine di partenza: ora contano solo
  gli attivi. La dashboard cadeva quando un turno aveva un tavolo con la
  lettera e uno senza. Nel foglio «Apri le iscrizioni» un minimo lasciato
  vuoto diventava zero invece di lasciare quello che c'era. La scheda
  informazioni del campionato non mostrava mai il blocco dei playoff,
  perché leggeva i campi del modulo di creazione invece delle
  configurazioni. Quando un invitato ai playoff rifiutava o lasciava
  scadere l'invito, nessuno scriveva chi aveva preso il suo posto: ora la
  qualificazione lo ricorda, e la pagina del campionato lo dice.
- **Rilievi della revisione automatica sulle tappe della prova** (PR #305,
  #314, #318, #319). «Simula il turno» contava come chiuse anche le partite
  dispari già a distanza e in attesa del direttore, e il messaggio diceva
  partite simulate che non lo erano: ora una partita conta solo se la
  simulazione ci ha fatto qualcosa. I messaggi della simulazione hanno la
  forma singolare («Simulata 1 partita»). Chiedere la data proposta per un
  campionato inesistente solleva `NotFoundError` invece di rispondere una
  data. Nel modale «Nuova gara» l'etichetta «Esercizio per la X» punta al
  suo controllo, quindi toccarla porta il fuoco sulla tendina. Lo script di
  riparazione delle iscrizioni duplicate propaga il codice di uscita.

### Aggiunto

- **Il direttore ritira chi se ne va.** Dalla lista degli iscritti, a gara in
  corso, il ritiro di un giocatore vale come il suo forfait, con la regola
  della gara; il ritiro nel trio applica la stessa regola; nessun ritiro
  passa su un turno già superato. Ogni ritiro deciso dal direttore riesce per
  intero o non lascia traccia, e il giocatore riceve una notifica (PR #386).
- **Il turno dopo aspetta la prova della X e gli esercizi.** Il turno
  successivo, la chiusura e lo spareggio non partono finché la prova della X
  non è convalidata e gli esercizi del turno non sono registrati, tranne col
  sorteggio casuale; la fascia dice cosa manca. Un tentativo registrato per
  sbaglio si toglie (PR #387).
- **Trio e partita a set si correggono come le partite a due**, anche a
  turno concluso: il foglio mostra tre punteggi o i set uno per uno, e
  classifica e schermo in sala si aggiornano senza ricaricare (PR #388).
- **Nei playoff chi accetta tardi entra fino all'avvio**, e il direttore può
  aggiungere un giocatore anche oltre i posti; se annulla l'avvio, gli inviti
  tornano in attesa (PR #390).
- **Nelle gare a eliminazione il tabellone prende il posto della classifica.**
  Sulla pagina del direttore, a gara in gioco, la colonna laterale mostra il
  turno che si gioca con quello prima e quello dopo, i posti futuri già
  disegnati dal sorteggio («chi vince A – B»). Le intestazioni dicono Quarti,
  Semifinali, Finale, Recupero; la card di chi passa il turno lo dice; ogni
  partita dice dove va chi vince. Prima del sorteggio c'è la forma del
  tabellone («Tabellone da 8 · 2 passano il turno · 3 turni»). A gara
  conclusa la classifica è per bande, 3°–4°, 5°–8°, con il turno d'uscita,
  senza vittorie e differenza triangoli che nel tabellone non ordinano
  niente. Il tabellone completo disegna anche i posti futuri (PR #363).
- **Lo schermo in sala anche per le gare a tabellone.** Accanto ai tavoli,
  il turno del tabellone in corso e quello dopo, i due tabelloni del doppio
  KO insieme, il podio a gara conclusa; niente con i puntini, perché si
  legge a tre metri (PR #365).
- **Trio, partite a set e X con esercizio sulla card del direttore.** Tre
  lati con − e + per il trio, i set vinti sopra e gli stepper del set in
  corso per le partite a set, uno stepper da zero alla distanza del turno
  per l'esercizio della X; niente più finestre di conferma del browser
  (PR #368).
- **La gara di un campionato lo dice.** Sopra la striscia di fase «Gara 4 di
  6 · Campionato», con il peso o «Playoff»; nella preparazione e nelle
  impostazioni il gruppo «Dal campionato» con peso, regola di apertura
  ereditata e date ammesse. A gara conclusa il testo sui punti dipende dalla
  gara: niente per una gara singola, «vale ×N» per una gara del campionato,
  «il playoff decide la classifica finale» se il playoff pesa zero. Nella
  prova il banner con la modalità aiuto e «Elimina la prova» c'è anche nei
  passi della preparazione e nelle impostazioni, e la simulazione sta in un
  foglio (PR #373).
- **Gli esercizi fra i turni si segnano dalla pagina della gara.** Finito il
  turno, «Esercizio dopo il turno N» elenca i giocatori con i tentativi e il
  migliore; toccando la riga si registra il tentativo con − e + o con
  «Riuscito» / «Non riuscito» (PR #377).
- **Squadre, categorie, ritiro ed eliminazione nella pagina del direttore.**
  Squadre e categorie sono righe che aprono un foglio, e dopo il sorteggio
  restano visibili in sola lettura invece di sparire; la squadra di un
  iscritto si cambia da un chip. Il direttore registra il ritiro di un
  giocatore dal menu della partita, e il foglio dice prima cosa comporta la
  regola della gara sui ritiri. In preparazione, finché la gara non ha
  iscritti, «Elimina la gara» sta in fondo, con un foglio che avvisa che non
  si torna indietro (PR #379).
- **La pagina della gara per chi la dirige, fase per fase.** Chi dirige una
  gara non vede più le quattro linguette di prima: in cima una striscia
  dice in che fase è la gara — preparazione, iscrizioni, in gioco,
  spareggio, chiusura — e sotto c'è solo quella fase, con una fascia scura
  che dice l'unica cosa da fare adesso (la stessa che propone la
  dashboard). La preparazione è fatta di passi con avanti e indietro, e i
  tavoli si possono cambiare in ogni momento, anche a serata iniziata. Le
  iscrizioni hanno il campo per iscrivere in cima, con i candidati che
  compaiono mentre si scrive, e il foglio «Avvia la gara» racconta cosa
  succederà. In gioco il punteggio si segna sulla card della partita con
  − e +, il tavolo si assegna toccando una tessera libera, e un risultato
  chiuso si corregge scrivendo il perché. La classifica ha le frecce di chi
  sale e scende. Lo spareggio si segna con gli stessi pulsanti, e a gara
  conclusa c'è il podio con le medaglie. Chi guarda la gara — giocatori e
  ospiti — continua a vedere la pagina di sempre (ADR-059, ADR-060; PR
  #343, #345, #347, #349, #351, #355).
- **Lo schermo in sala.** Un indirizzo da aprire sulla TV del locale, a
  partire da quello della vetrina (`/g/<indirizzo>/sala`): la locandina, i
  tavoli con i nomi e i punteggi leggibili a tre metri, la classifica. Si
  aggiorna da solo quando un risultato cambia. Per le gare a tabellone non
  c'è ancora, issue #352 (PR #354).
- **La classifica generale mostra la zona playoff**, e la pagina del
  campionato ha la stessa forma di quella della gara: una fascia che dice a
  che punto è la stagione, le gare in righe con stato e peso, gli invitati
  ai playoff con chi ha preso il posto di chi (PR #358, #360).

- **La cifra del punteggio si vede cambiare.** Quando un triangolo viene
  segnato, il numero grande della partita sale da sotto e si accende in un
  quarto di secondo, invece di trovarsi già cambiato: sul tabellone da
  tavolo al tocco, e sull'altro telefono quando arriva l'aggiornamento;
  sulla card del punteggio anche dopo il ricaricamento della pagina, perché
  lo script si ricorda cosa diceva prima e fa saltare solo la cifra diversa.
  Un aggiornamento che porta lo stesso numero non muove niente.
- **Il cambio pagina senza lampo bianco.** L'app è fatta di pagine intere:
  ogni tocco su un link ne chiede una nuova al server, e fra le due c'era un
  istante di bianco — su PythonAnywhere anche un terzo di secondo — che
  faceva sembrare l'app un sito. Ora la pagina che si lascia resta sullo
  schermo finché quella nuova non è pronta, poi le due si dissolvono l'una
  nell'altra in un quarto di secondo, mentre testata, barra laterale e
  barra di navigazione del telefono restano ferme al loro posto. Funziona
  su Chrome e Safari; dove il browser non lo sa fare non cambia niente. Chi
  ha «riduci movimento» attivo non vede nessuna dissolvenza.
- **Una scala del movimento per tutta l'interfaccia.** Fino a oggi ogni
  animazione del tema aveva i suoi tempi, scritti a mano e diversi fra loro:
  il toast di Chalky entrava in 320 ms con una curva sua, il chevron delle
  sezioni ruotava in 200, il riscontro sul tabellone durava 120 o 100 a
  seconda del pezzo, e le sezioni richiudibili di Bootstrap si aprivano in
  350. Ora le durate sono due, decise guardando i gesti a confronto
  (`docs/redesign-7c/movimento/`): 250 ms per ciò che entra o si apre, 150
  per ciò che esce, si chiude o torna dal tocco, una curva sola. I comandi
  grossi del segnapunti si schiacciano leggermente sotto il dito, all'istante,
  e tornano su in 150 ms. Chi ha «riduci movimento» attivo sul telefono ottiene
  tutto fermo alla fonte, senza che ogni animazione debba ricordarsene: il
  pallino live del tabellone orizzontale, che non lo faceva, ora si ferma
  anche lui. Il tocco sul segnapunti è la prima applicazione; il cambio pagina
  senza lampo bianco e la cifra del punteggio che si anima arrivano dopo.
- **Aiuto contestuale dentro le prove** (ADR-058, quarta tappa). Le
  schermate di una competizione di prova si spiegano da sole: la prima volta
  che se ne apre una compare una breve presentazione, un passo alla volta,
  che evidenzia i comandi principali; poi accanto a ogni comando importante
  resta una «?» che apre due frasi e il collegamento alla pagina della guida.
  I testi sono quelli di `hints.yaml`, scritti mesi fa come predisposizione e
  finora letti solo dal catalogo `/aiuto/microaiuto`: ora ogni ancora ha il
  suo elemento nei template (`data-help`), i suggerimenti mancanti per
  campionato, playoff e prova sono stati scritti in italiano e inglese, e un
  test statico tiene allineati i due lati del contratto. Il componente
  (`static/js/help-hints.js`) non sa cos'è una prova: è una «modalità
  aiuto» che si accende dove la pagina la offre — oggi il banner della prova,
  con l'interruttore «Suggerimenti» — e resta accesa finché l'utente non la
  spegne, per il suo browser. Nella guida nasce la pagina «Fare una prova
  prima della serata vera», con le schermate catturate da un seed
  dimostrativo esteso con due prove; «Chi fa cosa» e «Diventare direttore»
  la indicano.
- **Competizione di prova** (ADR-058, prima tappa). Un direttore appena
  promosso deve poter capire le schermate di gestione prima di condurre una
  serata vera, e finora poteva solo leggere la guida o fare esperimenti su
  gare reali. Ora nel modulo della gara singola c'è la spunta «Competizione
  di prova»: nasce la stessa gara di sempre, con un flag. La vede **solo chi
  la dirige** (co-direttori e admin compresi), non ha link pubblico né
  vetrina, non compare in nessun elenco. A iscrizioni aperte la si popola con
  tre pulsanti — il minimo, fino al massimo, uno in più — che creano
  **giocatori fittizi** con nomi generici e rating fissi e diversi; nessun
  utente vero può iscriversi. Le partite di una prova non muovono l'ELO e
  nessun evento di prova dà XP, badge o missioni a nessuno; le statistiche
  del direttore la ignorano; le notifiche che genera arrivano con il prefisso
  «Prova ·». Al massimo tre prove aperte per direttore. Si elimina in
  qualunque stato dal banner in cima alla pagina, **fisicamente**, con
  partite, iscrizioni e fittizi; una prova dimenticata sparisce da sola dopo
  14 giorni, con un avviso in app tre giorni prima. L'invisibilità è un
  filtro di sessione come il soft delete: una schermata nuova che se ne
  dimentica non la mostra, invece di mostrarla per errore. Le tappe
  successive — simulazione dei risultati, campionato di prova, aiuto
  contestuale — sono in `docs/usecases/competizione-di-prova.md`.

- **Competizione di prova, terza tappa: il campionato di prova.** Nel wizard
  del campionato c'è la spunta «Competizione di prova», con lo stesso limite
  di tre prove delle gare singole. Le gare del campionato nascono di prova da
  sole, il modale «Nuova gara» propone le date nei prossimi giorni e in
  ordine — domani la prima, il giorno dopo l'ultima le altre — e i giocatori
  fittizi sono **del campionato**: la seconda gara riusa quelli della prima,
  così la classifica generale si forma come in un campionato vero. Al
  playoff il direttore accetta o rifiuta l'invito per ciascun fittizio, o
  accetta tutti i rimanenti con un pulsante; un rifiuto fa scattare il primo
  degli esclusi, come nella realtà. Il banner della prova sta anche sulle
  pagine del campionato e da lì elimina tutto, gare e playoff compresi. Il
  modale «Nuova gara» dei campionati veri ora propone la data che la
  specifica prevedeva da sempre: oggi per la prima gara, una settimana dopo
  l'ultima per le altre.

- **Competizione di prova, seconda tappa: la simulazione dei risultati.** In
  una prova avviata il pannello di gestione ha tre pulsanti — **Simula una
  partita**, **Simula il turno**, **Simula tutta la gara** — con cui il
  direttore fa andare avanti la gara senza giocatori veri. Le partite si
  chiudono **nei due modi che deve imparare**: metà con la doppia conferma dei
  giocatori, chiuse da sole; l'altra metà con il risultato segnato da un solo
  giocatore, in attesa che lui le validi dal segnapunti, esattamente come gli
  succederà con giocatori veri che non passano dal suo tavolo. «Tutta la gara»
  chiude tutto, validando anche quelle. Ogni rack passa dal segnapunti vero con
  l'id del fittizio che lo segna, quindi il tabellino è vero e il segnapunti
  resta usabile dopo; i punteggi rispettano la distanza del turno, e in
  «esattamente N» con N pari il pareggio esiste come nella realtà. Le vecchie
  azioni di debug del footer di sviluppo usano lo stesso servizio: una sola
  implementazione.

- **Segnalare un problema dall'app.** Chi usa l'app non aveva nessun modo di
  dire che qualcosa non va: il backlog vive su GitHub, e i giocatori non hanno
  un account GitHub. Ora **Segnalazioni** sta nel menu sotto la Guida, nel
  footer di ogni pagina e sulla schermata di errore; il modulo ha tre campi, e
  il contesto tecnico — pagina di provenienza, versione, ruolo, browser — lo
  allega l'app. Le segnalazioni diventano issue vere e gli stati tornano
  indietro come notifiche, in italiano corrente: «ricevuta», «presa in
  considerazione», «fatto», «per ora non la faremo». La segnalazione si salva
  **prima** su DB e si spedisce dopo, così un GitHub irraggiungibile non porta
  via il testo appena scritto. (#255, PR #287)

  > **Nota sul rilascio**: questa voce è a mano perché il commit della #287
  > non è entrato in `docs/RELEASES.md` — vedi «Corretto» qui sotto.

### Corretto

- **Gli aggiornamenti live arrivano sempre.** La pagina della gara, il tabellone
  della partita e il badge delle notifiche chiedono al server ogni tre secondi
  se è successo qualcosa, e a volte la risposta era «niente» anche quando un
  rack era appena stato segnato: l'archivio degli eventi stava nella memoria
  di **uno** dei tre processi che servono il sito, e solo le richieste capitate
  su quello lo vedevano. Circa un evento su tre arrivava. Ora gli eventi
  passano da una tabella condivisa, l'evento nasce insieme al fatto che lo
  genera, il turno nuovo compare da solo sulla pagina della gara (prima non
  si annunciava mai), e chi torna su una scheda rimasta chiusa per minuti la
  vede aggiornata invece di vecchia. Non dipende più dall'orologio del
  telefono (ADR-057).

- **Un messaggio di commit con parentesi annidate spariva dal changelog.**
  Il corpo del commit della #287 conteneva `matchMedia('(min-width: 992px)')`:
  il parser Conventional Commits di release-please legge quella `(` come
  l'apertura di uno *scope* e si ferma con «unexpected token». Il commit viene
  **saltato in silenzio** — il workflow risulta verde e la PR di rilascio
  «remained the same» — quindi la funzione non compare in `docs/RELEASES.md` e,
  se fosse stata l'unica `feat:`, non avrebbe alzato la versione. La regola sta
  ora in `CLAUDE.md`.


- **Le sfide individuali non offrivano le regole di apertura che il modello
  aveva già imparato.** Le tre schermate — avvio rapido, proposta, correzione —
  avevano ancora tre opzioni scritte a mano con etichette diverse da quelle
  della gara, quindi lo stesso formato si chiamava in due modi a seconda di
  dove lo leggevi; «a turno ogni due» non era raggiungibile; e l'acchito, pur
  funzionando sul tabellone, non si poteva accendere da nessuna parte. Adesso
  le opzioni le detta l'enum, come nei moduli di gara e campionato, e la regola
  di inizio viaggia anche con la **proposta**: chi accetta una sfida sa a cosa
  sta dicendo di sì.

### Modificato

- **Rinominata la statistica «gare giocate» nel codice** (`provas_played` →
  `gare_played`). Era l'anti-pattern «radice italiana con la `-s` inglese» che
  `NAMING_CONVENTIONS.md` vieta, e per giunta con la parola sbagliata: il
  termine di dominio è *gara*. Nessun effetto visibile — è un identificatore,
  non un'etichetta.

- **Il profilo non ha più i colori di Bootstrap in mezzo.** «Rating» e «Le mie
  Statistiche» erano rimasti in markup Bootstrap: le card le ridisegnava già il
  tema, ma i quattro numeri — campionati, gare, vittorie, percentuale — erano
  il blu, il ciano, il verde e l'ambra di Bootstrap, e nessun foglio di stile
  li sovrascriveva. Erano l'unico punto della pagina dove si vedevano colori
  fuori dalla palette, per giunta accanto a una sezione, «Esercizi», che era
  già a posto. Adesso le tre sezioni hanno la stessa forma; le etichette non
  cambiano. Sistemato anche un «e'» al posto di «è» nella spiegazione del TPA.
- **Sul tabellone, a risultato da confermare, le risposte sono due e non tre.**
  «Rifiuta» toglie l'ultimo triangolo — è quello che ha sempre fatto — quindi
  era la stessa mossa del pulsante ⟲ che gli stava accanto: tre pulsanti per
  due azioni, con quello muto schiacciato in mezzo. In quello stato l'ultimo
  triangolo è per l'appunto quello che ha **chiuso la partita**, e «Rifiuta» è
  il nome giusto per il gesto: non si corregge un punto qualunque, si dice che
  il risultato non torna. Il ⟲ resta in tutti gli altri stati, dove non è un
  doppione ma la sola via d'uscita per un triangolo segnato per sbaglio.

### Aggiunto

- **Chi apre, l'acchito e i triangoli chiusi in una visita** (ADR-056). Il
  tabellone orizzontale — il telefono appoggiato alla sponda — registrava solo
  chi vinceva il triangolo. Adesso registra anche le tre cose che al tavolo
  esistono da sempre.
  - **La pastiglia «spacca»** sopra il nome dice di chi è il tiro di apertura
    *adesso*, e si sposta da sola triangolo per triangolo seguendo la regola
    della gara. È la regola in forma viva: per questo dalla riga dei metadati
    non compare come configurazione: sarebbe la stessa cosa detta due volte.
  - **Il runout si marca premendo il trattino** che si è appena acceso, non con
    un pulsante. Un pulsante dedicato è stato scartato tre volte per una
    ragione di proporzione: il runout è un evento **raro** su una superficie
    fatta per un gesto **frequente**, e qualunque bersaglio permanente o ruba
    spazio al gesto che si fa sempre, o è troppo piccolo per prenderlo al buio.
    Sul trattino compare **B** se ad aprire era chi ha vinto, **R** se ha
    chiuso rispondendo: la distinzione **si deduce**, non si chiede.
  - **L'acchito fa due domande, non una.** Il regolamento FIBiS dice che chi
    vince l'acchito *sceglie chi* esegue il tiro di apertura, e può mandare al
    tavolo l'avversario: prima del primo triangolo il tabellone chiede
    entrambe. Compare solo dove la gara lo prevede — la regola predefinita
    resta «apre il primo giocatore», e chi non configura niente non vede
    cambiare niente.
  - **Quattro modalità di apertura** — a turno (la standard FIBiS), a turno
    ogni due (nuova), spacca chi ha vinto, spacca chi ha perso — scelte sul
    campionato e ereditate dalle gare, con la voce «eredita dal campionato»
    sempre disponibile. Una gara **fuori da un campionato** le sceglie alla
    nascita, nel modulo di creazione: non avendo nulla da cui ereditare,
    l'alternativa sarebbe crearla e poi modificarla. A gara cominciata i campi si bloccano: cambiarli a metà
    riscriverebbe chi ha aperto i triangoli già giocati.
  - **In testata il numero del tavolo** in evidenza, che è come si riconosce il
    proprio tabellone attraversando una sala con otto biliardi, e l'ora
    d'inizio della partita.
  - Nel profilo, una riga nuova: **«Runout: 26 — di cui 9 break and run»**. Il
    numero unisce due fonti che non convivono mai sulla stessa partita — i
    trattini marcati sul tabellone e il referto TPA, che i runout li riconosce
    da sé.
  - `SPECIFICHE.md` emendata con nota datata su quattro punti: prevedeva due
    modalità di apertura mentre il codice ne aveva già tre, «a turno ogni due»
    non esisteva, l'acchito era descritto al contrario del regolamento, e sui
    match di gara non esisteva nulla.

- **Referto TPA sui match singoli** (ADR-044). Nelle partite amichevoli a palla
  8, 9 e 10 si può annotare tutta la partita — quante bilie a ogni visita al
  tavolo e perché il turno è finito — e ricavarne il *Total Performance
  Average*, il metodo Accu-Stats usato nel biliardo professionistico. È una
  funzione **da sbloccare** (feature gamification `tpa_scoresheet`): la vede
  chi ha già giocato gare, campionati, match singoli, drill ed esami.
  - Il **punteggio del match discende dal referto**: chi lo compila non segna i
    rack, li registra il referto. Con un referto aperto il segnapunti normale
    sparisce, così le due cose non possono divergere.
  - Il motore delle regole (`models/tpa/engine.py`) è un port fedele dell'app
    JS di riferimento, **verificato per differenza** su 600 partite generate a
    caso: stessi totali, stesso tastierino, stessi momenti in cui si passa il
    tavolo. Zero divergenze.
  - Si salva il registro dei comandi premuti, non lo stato che ne risulta:
    l'annulla è esatto e i totali non possono disallinearsi.
- Due metriche nuove per lo sblocco delle funzioni, disponibili anche nel menù
  della gestione gamification: `campionati_played` e
  `individual_matches_played`.
- Pagina di guida **«Il referto TPA»** in italiano e inglese, con i
  suggerimenti per l'interfaccia adattiva. Le figure sono ancora da catturare.
- Il **TPA nel profilo** (accanto all'Elo) e nelle **statistiche dei match
  individuali**, con il dettaglio di dove nascono gli errori e l'elenco delle
  partite con referto. Si somma su tutti i referti — bilie ed errori sommati e
  divisi una volta sola, non la media dei TPA di partita. Compare a chi ha
  sbloccato la funzione **oppure** a chi ha gia' giocato una partita in cui il
  referto lo teneva l'avversario.
- Filtro `|tpa_display`: il TPA come si scrive sul referto (`.780`, `1.000`).
- **Il referto si vede cambiare dall'altro capo del tavolo.** Ogni tocco
  annuncia `tpa_updated` sul canale del match e la pagina di chi guarda
  ridisegna **senza ricaricarsi**; il punteggio annuncia `rack_updated` solo
  quando si e' mosso davvero, e li' la pagina del match si ricarica come fa
  gia' per il segnapunti normale. Prima la pagina del referto faceva polling a
  orologio per conto suo, e la pagina del match non si accorgeva di niente.
- Le sei route del referto in `docs/reference/PRODUCTION_INVENTORY.md`.
- **Il referto TPA si sceglie all'avvio rapido.** Nel modulo, per chi ha
  sbloccato la funzione, c'è la spunta «Tengo il referto TPA»: la partita nasce
  col referto già aperto e si va lì invece che al segnapunti. Il referto va
  aperto **prima del primo triangolo**, e l'avvio rapido porta dritti a
  segnare: la finestra per prenderlo era larga un tocco e si chiudeva senza
  dire niente. Su una disciplina che il TPA non copre, o su un match a set, la
  domanda sparisce e la partita parte comunque — senza referto.

### Corretto

- **A partita finita non si segna più.** L'aggiunta di un triangolo non
  chiedeva mai `can_add_rack()`: la pagina i «+1» li toglie da sola, ma il
  tabellone orizzontale resta aperto sul telefono appoggiato alla sponda e una
  pagina vecchia mandava comunque il triangolo. In «esattamente N» non era
  contabilità: a 2-2 su quattro la partita è **pari**, e un triangolo di troppo
  la portava a 3-2 assegnando la vittoria a chi aveva premuto, dopo che era
  finita. Il formato libero non è toccato.
- **L'ora scritta è l'ora che si rilegge, anche nella richiesta di partita.**
  La richiesta che parte dalla scoperta giocatori rimetteva insieme data e ora
  con `datetime.strptime` e salvava la stringa grezza in una colonna che il DB
  tiene naive-UTC: un appuntamento per le 21:00 tornava alle 23:00 (ADR-043).
- Un `.po` inglese di nuovo al 100%, senza voci fuzzy.

### Rimosso

- **Il rating Fargo, da tutte le parti.** Era predisposto e mai alimentato: la
  colonna `user.fargo_rating` esisteva dal principio, nessuna riga di codice ci
  ha mai scritto dentro, e il profilo e l'elenco utenti mostravano comunque un
  trattino perenne. Un dato che non arriva mai non e' una funzione a meta': e'
  una promessa che l'interfaccia continua a fare per conto di nessuno.
  - Via la colonna, il membro `RatingSystem.FARGO`, le regole di handicap
    costruite su quel sistema e l'importazione massiva mai usata
    (`bulk_import_fargo_ratings`).
  - Il sorteggio per rating (Amalfi ed eliminazione diretta) ora guarda solo
    l'Elo. Chi non ha un Elo vale zero e finisce in coda.
  - Migration `20260816_drop_fargo_rating`: elimina colonna, righe di
    `player_rating` e regole di handicap.

## [1.0.0] — 2026-08-13

Prima release numerata. L'applicazione era già in produzione su
[torneibiliardo.it](https://www.torneibiliardo.it) da mesi: questa versione non
segna l'inizio del progetto ma il momento in cui i rilasci diventano
tracciabili. La storia precedente resta nei commit e nelle PR #1–#93.

Il contenuto che caratterizza la 1.0.0 è il **redesign 7c** (PR #93, 32
commit), che porta l'intera interfaccia sotto un unico design system.

### Aggiunto

- Design system **7c**: `static/css/theme-7c.css` e `tokens-7c.css`, con
  impaginazione mobile first verificata anche su desktop.
- Pagina di errore **403**, che non esisteva: un permesso negato mostrava la
  pagina grezza di Werkzeug, in inglese e fuori dal design.
- Le tabelle larghe si impaginano a card sotto i 992px (`.c7-table-cards`)
  mantenendo un solo DOM, quindi filtri e ordinamento in JavaScript continuano
  a funzionare.
- `Discipline.normalize()` per ricondurre i dati storici al vocabolario unico
  delle discipline, con la migration
  `20260811_normalize_discipline_vocabulary.py`.
- Due test che presidiano classi di guasto invece dei singoli casi:
  `test_template_integrity.py` compila ogni template e verifica ogni `url_for`
  letterale; `test_single_page_header.py` impedisce il ritorno delle testate
  doppie.
- La versione dell'applicazione è mostrata nel footer.

### Rinominato

- L'applicazione si chiama **Tornei Biliardo**, come il dominio
  torneibiliardo.it, e non più "Campionato Biliardo". Il nome era scritto a
  mano in 28 punti (titoli di scheda, oggetti delle email, informativa
  privacy): ora arriva tutto da `Config.APP_NAME`. Era anche dentro `_()` in
  dieci template, cioè dato in traduzione: un nome proprio non si traduce.

### Modificato

- Il punto di rottura del layout passa da `md` (768px) a `lg` (992px), dove il
  guscio cambia davvero impaginazione.
- Le utility `bg-*` di Bootstrap sono ridefinite dal tema: anche le pagine non
  ancora convertite restano in palette.
- Le discipline hanno un solo vocabolario (`Discipline.*.value`), con il nome
  mostrato tradotto tramite `display_name`.
- Catalogo di traduzione inglese completo: 2151 stringhe, 100%.

### Corretto

- `_pagination.html` non compilava (un esempio d'uso dentro un commento HTML,
  che non nasconde i tag a Jinja): le tre pagine admin di gamification che lo
  includono rispondevano **500**.
- Tre endpoint inesistenti nei template (`player.match_proposals` e altri due):
  le proposte di match stanno nel blueprint `individual_match`. Dashboard
  direttore e header dashboard rispondevano 500.
- `_player_challenges.html` puntava a `challenge.attempt_challenge`, che non
  esiste, e perdeva il contesto gara.
- Le route di debug leggevano `Config.DEBUG_MODE` invece di
  `current_app.config`: in produzione il guard non scattava.
- La Content Security Policy non consentiva Google Fonts, quindi la tipografia
  cadeva sul fallback.
- Dodici template disegnavano una seconda testata dentro `content`.
- Il messaggio del 403 restituito in JSON non era tradotto.

[Non rilasciato]: https://github.com/coppolapaolo/tornei-biliardo/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/coppolapaolo/tornei-biliardo/releases/tag/v1.0.0
