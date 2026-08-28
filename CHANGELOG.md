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
