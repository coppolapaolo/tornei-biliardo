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
