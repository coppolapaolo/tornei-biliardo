# Stato del redesign 7c

Diario di lavoro sul branch `claude/redesign-7c`. Il piano originale
dell'handoff è in `README.md`, qui c'è cosa è stato fatto davvero e cosa
resta. Aggiornare a ogni passo.

## Fatto

**Import** (`d529554`) — `files/` copiato nel repo con `cp -R` (merge, non
sostituzione: il Finder di macOS rimpiazza l'intera cartella e cancella
quello che c'era). 61 template, `tokens-7c.css`, `theme-7c.css`,
`gamification.js`, documenti di riferimento in `docs/redesign-7c/`.

**CSP** (`d529554`) — `base.html` chiede Manrope e JetBrains Mono a Google
Fonts, che non erano fra i domini consentiti: aggiunti
`fonts.googleapis.com` a `style-src` e `fonts.gstatic.com` a `font-src`,
con test. L'header è impostato in un `after_request` non condizionato
all'ambiente, quindi senza la correzione la tipografia cadeva sul fallback
anche in sviluppo.

**Endpoint inventati** (`f53eb80`) — i template convertiti puntavano a
`player.match_proposals`, `player.accept_match_proposal` e
`player.create_match_proposal`: nomi plausibili ma mai registrati. Le
proposte di match stanno nel blueprint `individual_match`. Senza la
correzione, dashboard direttore e header dashboard davano 500.

**Due guasti preesistenti** (`bf08f69`) — `_pagination.html` non compilava
(esempio d'uso dentro un commento HTML, che non nasconde i tag a Jinja):
le tre pagine admin di gamification che lo includono davano 500.
`_player_challenges.html` puntava a `challenge.attempt_challenge`, che non
esiste, e perdeva comunque il contesto gara. Aggiunto
`tests/new/unit/test_template_integrity.py`, che copre l'intera classe:
compila ogni template e verifica ogni `url_for` letterale.

**Giro pagine** — 38 pagine visitate nei tre ruoli via test client:
**zero errori server**. Le tre pagine admin riparate rispondono 200.

**Giro visivo** (`c2dd915`, `28960e1`) — fatto in mobile **e** in desktop.
Dodici template convertiti disegnavano una seconda testata dentro
`content`: ora riempiono `page_title` / `page_sub` / `page_actions` /
`page_back`. Aggiunta la pagina 403, che non esisteva. Corretti i difetti
di testo nelle streak.

**Il desktop era stato trascurato dall'handoff.** Due difetti che sul
mobile non si vedono: nessun `max-width`, quindi su monitor larghi filtri
e tabelle si stiravano per l'intera finestra; e le utility `bg-*` di
Bootstrap non erano ridefinite, quindi le pagine non convertite mostravano
riquadri a tinta piena in mezzo alla palette. Entrambi risolti nel tema —
la seconda correzione vale per tutte le pagine non ancora convertite.
**Regola: ogni pagina va guardata in entrambe le viste prima di dirla
fatta.**

**`gara_detail.html`: il guscio** — la pagina piu' grande del progetto
(2048 righe) e' passata al design system. Il lavoro e' stato solo di
guscio: nessuna variabile `vm.*`, nessun `onclick`, nessun commento sulle
issue e' cambiato.

- **Testata.** `components/_gara_header.html` non disegna piu' una seconda
  `c7-head` dentro `content`: e' diventato un modulo di macro (`back`,
  `sub`, `actions`) che le due pagine di gara usano per riempire
  `page_back` / `page_title` / `page_sub` / `page_actions`. Era l'ultima
  testata doppia rimasta. L'`import` sta in cima al template figlio, fuori
  dai blocchi: Jinja esegue i nodi di primo livello prima di rendere il
  genitore, quindi il nome e' visibile dentro i blocchi.
- **Colonne.** Via la griglia Bootstrap (`row`, `col-md-8`, `col-md-4`):
  restano `c7-cols` e `c7-stack`. Con essa se n'e' andato un `col-md-8`
  che su mobile era vuoto e lasciava un buco di mezzo schermo sotto la
  Gestione.
- **Il punto di rottura passa da `md` (768px) a `lg` (992px)**, che e'
  dove il guscio 7c cambia davvero impaginazione: compaiono barra laterale
  e seconda colonna, sparisce la nav flottante. Prima, fra 768 e 992, la
  pagina mostrava il layout a due colonne dentro una finestra che era
  ancora "mobile", e le tabelle delle partite ci stavano strette.
- **Spaziature.** Niente piu' `mb-3`/`mb-4` sparsi: la distanza fra le
  sezioni la da' la pila. `.c7-cols` ora e' una colonna flex anche sotto i
  992px (prima era un blocco qualunque e le due colonne si toccavano —
  valeva anche per `player/profile.html`), e `.c7-sections` nasconde le
  sezioni che non hanno prodotto nulla, che altrimenti lasciavano il buco
  del `gap`.
- **Due duplicazioni tolte.** Lo spareggio SSR su desktop era ricopiato a
  mano dentro `gara_detail.html` accanto al componente usato su mobile;
  ora c'e' solo `components/_ssr_section.html`, convertito. Le sezioni
  richiudibili Info e Iscritti su mobile ricopiavano a mano il contenuto
  di `_gara_info.html` e `_gara_inscriptions.html`, e le copie erano gia'
  divergenti (su mobile mancavano challenge, direzione di gara e data
  d'iscrizione): ora includono gli stessi componenti in versione
  headerless, con la stessa convenzione di `management_headerless`.
- **Modali** (risultato rapido, assegnazione tavolo, spareggio) portati sul
  tema: niente testate a tinta piena, punteggi come `c7-stepper` invece
  che come campi numerici, griglia dei tavoli ridisegnata.

**Difetti trovati strada facendo e riparati** (nessuno introdotto da questo
passo):

- **Le dialog di pagina non arrivavano piu'.** La riscrittura del guscio
  aveva perso `{% include "components/_page_modal.html" %}` da `base.html`.
  I flash di categoria `page_modal` restavano quindi non consumati e
  finivano fra i messaggi normali: chi arrivava dal link pubblico di
  iscrizione (issue #61) vedeva il **JSON grezzo** del payload dentro un
  avviso. Tre test di `test_issue_61_gara_invite_link.py` erano rossi da
  allora. Include ripristinato, categoria esclusa dai flash, componente
  convertito.
- **La data d'iscrizione non compariva mai.** `_player_inscription_info`
  leggeva `user_inscription.inscription_date`, attributo che sul modello
  non esiste: Jinja lo risolveva a Undefined e il ramo `else` mostrava
  sempre "N/D". Nessun errore da nessuna parte. Ora legge `created_at`,
  con test di regressione.
- **Secondari e campi invisibili sulle card.** `.btn-secondary`,
  `.form-control` e `.form-select` hanno il fondo delle card, quindi su una
  card o dentro un modal sparivano ("Estendi Iscrizioni" era testo nudo).
  In quei contesti prendono ora il fondo pagina.
- **Bottoni "outline" fuori palette.** `btn-outline-primary` e compagni non
  erano ridefiniti: restavano azzurro Bootstrap (il "Copia" del link
  pubblico). In 7c la gerarchia la fa la superficie, non il bordo: seguono
  la variante piena.
- **Griglia dei tavoli** con la vecchia palette e il bianco pieno; il
  tavolo gia' assegnato, essendo un bottone disabilitato, veniva grigiato
  come "non disponibile" invece di essere evidenziato.
- **Bottoni dei modali** accavallati su schermo stretto: ora si impilano
  sotto i 576px.
- **Card dei direttori** con un `m-3` proprio, che la rientrava rispetto a
  tutte le altre sezioni.
- **Permesso troppo largo** in `_gara_inscriptions.html`: il bottone di
  disiscrizione compariva a qualunque direttore, non solo a chi gestisce
  quella gara (`user_can_manage`, la stessa capability che il server
  verifica sulla POST).

**Giro nel browser.** Mobile (331px) e desktop (1512px), nei tre ruoli e in
tutti gli stati: iscrizione, gioco, conclusa con spareggio. Nessun difetto
residuo.

**Test.** `tests/new/unit/` **verde** (era gia' rosso su 5 test prima di
questo passo, per asserzioni scritte sul markup pre-7c: flash, etichetta
"Pos. Turno Prec", icona `fa-8-ball`, template orfani). Aggiornati
all'invariante invece che alla stringa esatta. `tests/new/integration/`:
9 rossi prima, 1 adesso (vedi sotto). `pyright` 0 errori, `black` pulito,
`flake8` invariato sui file toccati.

**`match_detail.html`: il guscio** — chiusa l'altra meta' del punto 1 della
lista "da rifare a mano". Come per la gara, solo guscio: nessuna variabile
`vm.*`, nessun `onclick`, nessun commento sulle issue e' cambiato.

- **Testata.** `components/_match_header.html` e' diventato un modulo di
  macro (`back`, `names`, `sub`, `actions`, `meta`) come `_gara_header.html`:
  la pagina riempie `page_back` / `page_title` / `page_sub` / `page_actions`
  e la testata dentro `content` (il `d-none d-md-flex` a riga 28) e' sparita.
  Con essa se ne vanno i badge ELO gialli con `style` inline: l'ELO era gia'
  nella card del punteggio, in palette.
- **Identita' in testata, stato operativo sopra il punteggio.** Su 390px un
  sottotitolo di cinque voci mandava la `c7-head` sticky a tre righe. Il
  sottotitolo dice ora dove si colloca la partita (gara · turno ·
  disciplina); distanza, tavolo e stato stanno nella riga `meta()`, sopra il
  punteggio, uguale in mobile e desktop.
- **Colonne.** Via `container-fluid` / `row` / `col-md-8` / `col-md-4`:
  restano `c7-cols` e `c7-stack`, con il punto di rottura a **lg (992px)**,
  non piu' `md`. Via anche la card che avvolgeva il punteggio: i componenti
  disegnano gia' la propria superficie, quindi era una card dentro una card.
- **Un solo ritorno per viewport.** Su desktop vive nella testata, su mobile
  e' la freccia piu' il bottone largo di `_match_navigation.html` — in cima
  a punteggio definitivo, in fondo altrimenti. Prima "Torna alla Gara"
  compariva due volte su desktop.
- **`_match_info.html` e `_match_navigation.html`** (usati solo qui, quindi
  di fatto guscio) portati sul tema: `dl` a due colonne come `_gara_info`,
  stringhe finalmente dentro `_()` — erano tutte in italiano fisso — e via
  la ripetizione di distanza e tavolo, che ora sono nella riga `meta()`.
- **`_match_admin_controls.html`** non e' piu' una card gialla: in 7c il
  giallo e' il semantico "attenzione", e quelli sono i controlli ordinari di
  chi dirige. I punteggi sono `c7-stepper` invece che campi numerici, con
  `name`, `min`/`max` e validazione invariati.

**Difetti trovati strada facendo e riparati:**

- **Tabelle tagliate su mobile.** `.c7-table-wrap` (e `.table-responsive`,
  che il tema sovrascrive) avevano `overflow: hidden`: una tabella piu' larga
  dello schermo perdeva le ultime colonne **senza modo di raggiungerle**. Su
  390px lo faceva lo storico rack; la regola vale per ogni tabella larga
  della app, quindi la correzione (`overflow-x: auto`) e' generale — e
  probabilmente allevia anche il rilievo su `public/garas_list.html`.
- **"Tavolo non assegnato" su partite gia' validate.** La condizione era
  `status != 'completed'`, che non copre `validated`: a validazione fatta il
  tavolo e' stato liberato, e la pagina invitava ad assegnarne uno. Ora usa
  `MatchStatus.is_finished`. Stessa cosa per il "Senza tavolo" della riga
  meta e per il divisorio dei tempi, che restava orfano.
- **La linguetta del browser leggeva "Matchplayer2 vs player3".** Il
  `{%- if -%}` del blocco `title` mangiava lo spazio dopo "Match".
- **Stepper illeggibili su mobile.** Due stepper affiancati sotto i ~200px
  lasciavano zero spazio al numero fra i due tasti: la griglia e' ora
  `auto-fit`, e su mobile si impilano da soli.
- **"Bye" al posto di "X a tavolino"** in `_match_bye.html`, con le stringhe
  fuori da `_()`.
- **`tests/new/unit` era rosso** (non per colpa di questo passo): il test di
  regressione sulla data d'iscrizione chiamava `render_template(TEMPLATE)`
  con una costante di modulo, e il guardiano di `test_no_orphan_templates`
  vede solo i letterali.

**Aggiunto `tests/new/unit/test_single_page_header.py`**: nessuna pagina che
estende `base.html` puo' contenere una `c7-head`. E' la classe di difetti
piu' ricorrente della conversione — dodici occorrenze, tutte scoperte a mano
nel browser. Passa su tutti i template.

**Giro nel browser.** 390px e 1512px, nei tre ruoli, su partita in gioco,
validata e vinta a tavolino (verificata forzando `is_bye` in locale e
ripristinando subito il dato). Nessun difetto residuo.

**Segnapunti e tabellone** — la pagina partita era 7c nel guscio ma non nel
punto in cui si usa. Rifatti sul prototipo (schermate 7c e 8b): card del
punteggio chiara con cifre grandi e chi insegue in grigio, due bersagli "+1"
da 104px invece dei punteggi dentro pulsanti neri, un solo "Annulla ultimo
rack", storico come lista col progressivo. Nuovo
`components/_match_scoreboard.html`: il **tabellone orizzontale** compare da
solo quando lo schermo e' basso, largo e touch — il telefono appoggiato alla
sponda — e usa le stesse funzioni JS del segnapunti verticale.

Un secondo giro, fatto da un subagente con la skill `ui-7c`, ha trovato
quattro scostamenti dal prototipo sfuggiti al primo: chi insegue aveva grigio
il numero ma non il nome; i trattini di progresso del tabellone seguivano la
posizione invece di chi conduce (mentre nome e numero accanto seguivano gia'
il punteggio); il "+1" dell'avversario aveva perso il bordo; padding a 14/18px
invece di 16/20px.

**Cosa e' verificato e cosa no.** Verticale: 390px e 1512px, nei due ruoli,
segnando e annullando un rack contro l'endpoint vero. Tabellone orizzontale:
i valori CSS sono confermati con `getComputedStyle`, **la resa su un telefono
vero no** — sta dietro `pointer: coarse`, che il browser pilotato non emula.
Da guardare col device mode prima di dirlo chiuso.

## Disallineamenti fra prototipo e codice

Rilevati confrontando le schermate del prototipo con l'app in esecuzione.
Quelli sopra sono chiusi; questi no.

1. **Pagina gara, mobile (8a·1) — linguette Turni / Classifica / Iscritti.**
   Il prototipo divide la pagina in tre viste e mette in cima una card scura
   "IL TUO MATCH · TAVOLO 1 → Apri". Oggi e' una pila unica di sezioni: chi
   gioca scorre parecchio per trovare la propria partita, e Info/Iscritti
   restano il compromesso della PR #36. **Le linguette risolvono anche quel
   compromesso**, perche' ogni vista diventa corta. Lavoro medio: i contenuti
   esistono gia' tutti, serve il commutatore e la card di scorciatoia.
2. **Notifiche (8a·3) — azioni dentro la notifica.** Il prototipo divide "DA
   FARE" da "PRIMA" e mette i bottoni nella notifica ("Firmo" / "Contesto").
   Oggi la pagina si apre con il pannello di auto-cancellazione, poi una lista
   con selezione multipla: le impostazioni prima delle cose da fare, e ogni
   azione richiede di navigare altrove.
3. **Classifica larga in orizzontale (8b·2).** In orizzontale la classifica
   mostrerebbe match, vinti, rack e turno precedente. Rimandata per scelta.
4. **Copy della conferma.** Il prototipo parla di **firma** ("serve la tua
   firma", "Invia risultato"), il codice di conferma ("Accetta il risultato").
   Da decidere: la firma e' una metafora piu' chiara di cosa comporta.
5. ~~Cifre: mono o Manrope.~~ **Chiuso: vince il prototipo.** I punteggi sono
   Manrope 800. La regola scritta ("numeri e punteggi sempre in mono") era
   piu' grossolana delle schermate: il mono vale per i numeri di servizio
   (quote, XP, conteggi, orari — nel prototipo fino a ~32px), la cifra
   protagonista e' un titolo. Precisazione riportata in `README.md` e in
   `Design System 7c.md`, che erano la fonte dell'equivoco.
6. **Il verde e' un colore d'azione, nel prototipo.** "Crea campionato" e
   "Crea gara" della 14c sono verde pieno. Questo **chiude il rilievo aperto**
   sui bottoni verdi del catalogo challenge: non sono un errore, sono la
   conferma conclusiva di un flusso.
7. **Match individuali (9a).** Il prototipo ha linguette "Da giocare / In
   attesa / Giocati", proposta di date come lista di opzioni selezionabili e
   calendario delle disponibilita'. I dieci template dell'area sono ancora
   nella lista "da verificare": il divario e' probabilmente ampio.
8. **Gara pubblica per l'ospite (10a).** Due tessere ("Turno corrente",
   "Stato"), classifica provvisoria e invito a registrarsi in card scura. Da
   confrontare con `_guest_info.html`.

## Da fare

1. **Gamification giocatore.** Primo lavoro, prima delle pagine: **il badge
   XP della navbar non esiste piu'.** L'handoff lo ha tolto sia da
   `base.html` (anello di progresso, livello, XP, i `data-*` che alimentano
   il count-up) sia da `static/js/gamification.js`, dove il modulo
   `GamificationBadge` e' sparito. Conseguenze verificate: il test
   `tests/new/integration/gamification/test_navbar_badge_render.py` e'
   **rosso di proposito** (unico rosso rimasto: e' il promemoria), e la
   suite headless `tests/frontend` (26 controlli su §11/§11-quater) non
   parte nemmeno — muore all'import su `GamificationBadge is not defined`.
   Va deciso dove vive il badge nel guscio 7c e ricostruito il modulo JS.
   Poi le pagine: **flusso challenge**, poi **pannelli admin di
   gamification**.
2. **Traduzioni EN — deciso: alla fine del redesign.** Oggi ci sono 76
   stringhe nuove senza traduzione e 346 fuzzy, che sono accoppiamenti
   automatici sbagliati ("amministrazione" → *Registrations*, "Persone" →
   *Lost*). Non fanno danno: `pybabel` scarta le fuzzy dal `.mo` e
   l'interfaccia inglese mostra l'italiano. Convertire le pagine restanti
   cambierà altri testi, quindi tradurre prima significherebbe ritradurre.
   A conversione finita: `/translate`, poi riscrivere le fuzzy invece di
   approvarle in blocco.
3. **Pulizia di `main.css` e `variables.css`** — solo a verifica completata.

## Rilievi aperti dal giro visivo

Visti ma non ancora affrontati, in ordine di dubbio:

- ~~Bottoni verdi nel catalogo challenge.~~ **Chiuso dal prototipo**: nella
  14c "Crea campionato" e "Crea gara" sono verde pieno. Il verde e' la
  conferma conclusiva di un flusso, non solo il semantico "ok".
- **Card "Unisci utenti (merge)" in `/admin/users`.** Fondo giallo con
  sotto una striscia vuota: sembra un accordion o un alert malformato. Da
  guardare da vicino.
- **`admin/gara_challenge_classification.html` non e' internazionalizzata.**
  Il corpo della pagina ha le stringhe in italiano fuori da `_()` ("Pos.",
  "Giocatore", "Classifica Challenge"). Qui e' stata toccata solo la
  testata, per non collidere con il branch challenge: la conversione della
  pagina se ne fa carico.
- **La card "Gestione" resta visibile e vuota a gara conclusa** — solo
  titolo e badge di stato, nessuna azione. Il badge e' l'unico posto in
  pagina dove lo stato e' scritto, quindi non basta nasconderla.
- **Info e Iscritti richiudibili su mobile** stanno ancora dentro la
  sezione Partite, quindi in fase di gioco risalgono con lei (compromesso
  della PR #36). Con la pila di sezioni ora spostarli in fondo assoluto e'
  molto meno costoso di prima.
- **`public/garas_list.html` su mobile.** È una tabella a sei colonne
  dentro `c7-table-wrap`: i nomi delle gare vanno a capo su ogni parola.
  Il pacchetto ha `_match_cards_mobile` e `_classification_mobile` proprio
  per questo caso: valutare una resa a card sotto i 992px. (Da riguardare
  dopo la correzione dell'`overflow-x`: ora almeno la tabella scorre.)
- **Multi-set e trio: non verificabili in locale.** Il DB di sviluppo non ha
  nemmeno una partita `is_multi_set` o `is_trio`, quindi
  `_multi_set_score_display.html` (ancora `card-header bg-secondary`, ma il
  tema ridefinisce le utility `bg-*`, quindi resta in palette) e
  `_trio_rack_input.html` sono stati lasciati come sono: il README chiede di
  non riscrivere un template senza averlo aperto nel browser. Gli stepper
  del trio in `_match_admin_controls.html` sono invece convertiti, ma
  verificati solo per il caso a due giocatori. Da guardare quando ci sara'
  un dato — o creandone uno.
- **Storico rack su mobile.** Quattro colonne che a 390px scorrono in
  orizzontale. Funziona, ma la resa a card sarebbe migliore: stesso
  ragionamento di `garas_list`.

## Ambiente di lavoro locale

- **Prima di toccare interfaccia, invoca la skill `ui-7c`**
  (`.claude/skills/ui-7c/SKILL.md`): regola zero, aprire la schermata del
  prototipo che corrisponde a quello che si sta per fare. Contiene la mappa
  delle ancore, come interpretare le schermate che il prototipo non copre, le
  regole non negoziabili e la procedura di verifica.

- L'app di sviluppo gira su **porta 5001**, non 5000 (`python app.py`).
- Per entrare senza password: `/debug/login/<username>` — utenti utili
  `admin`, `pa` (direttore), `player1`, `player2`. **Esiste solo con
  `DEBUG_MODE` attivo** (default in sviluppo, `False` in produzione): come
  tutte le route `/debug/*` e `/reset`. Il guard leggeva pero'
  `Config.DEBUG_MODE`, cioe' la classe base, dove il valore arriva dalla
  variabile d'ambiente col default `true` — in produzione, che quella
  variabile non la imposta, non scattava. A tenere chiusa la porta restava la
  sola allowlist di ADR-028, **che pero' fa bypass per gli admin**: un
  amministratore autenticato poteva aprire `/reset` in produzione. Corretto:
  ora tutte e dodici le route leggono `current_app.config`, con
  `tests/new/unit/test_debug_routes_off_in_production.py` a presidiarle.
- La migration `20260607_onboarding` mette `onboarding_completed = 0` a
  **tutti** gli utenti esistenti, che quindi vengono dirottati sulla
  schermata di benvenuto a ogni pagina finché non la completano. In locale
  sono stati sbloccati con un UPDATE. **In produzione è già applicata**:
  gli utenti registrati vedranno l'onboarding al prossimo accesso.
- Il CSS è servito con `?v=ASSET_VERSION`: dopo averlo modificato serve un
  ricaricamento forzato del browser, altrimenti si guarda la versione
  vecchia e si crede che il fix non funzioni.
- **Il ricaricamento forzato dal browser pilotato non basta**: `?v=` fissa la
  versione del CSS e la scheda continua a servire quella in cache. Funziona
  invece riscrivere gli href da JS —
  `document.querySelectorAll('link[rel=stylesheet]').forEach(l => { const u =
  new URL(l.href); u.searchParams.set('cb', String(performance.now()));
  l.href = u.toString(); })`. Senza questo si guarda la versione vecchia e si
  crede che la correzione non funzioni (verificare con
  `getComputedStyle(...)`, non a occhio).
- **Il mobile si guarda con i DevTools di Chrome** (device toolbar,
  cmd+shift+M): e' l'unico modo in cui viewport, media query e touch sono
  davvero quelli di un telefono. Ridimensionare la finestra non basta —
  su macOS non scende sotto ~500px, quindi 390px non si raggiungono.
  Ripiego per la sessione pilotata, quando la device toolbar non e'
  raggiungibile: `document.documentElement.style.zoom = '1.282'` (500 / 390)
  impagina il contenuto su 390px logici, mentre le media query restano sul
  valore vero della finestra — sotto i 992px e' comunque il ramo mobile.
  `document.body.scrollWidth` dice se c'e' overflow. Serve a vedere il
  ritorno a capo e gli sbordamenti, non a sostituire la verifica vera.
- **Se il browser pilotato smette di ridimensionarsi**, la scheda e' andata,
  non la finestra: `resize_window` risponde "success" mentre `innerWidth`
  resta fermo e `outerWidth` diventa uguale a `innerWidth` (impossibile per
  una finestra vera). Si risolve aprendo una scheda nuova — che nasce con la
  misura chiesta — e chiudendo la vecchia. Sintomo collaterale: gli
  screenshot restano indietro di uno scroll o escono grigi.

## Lavori in parallelo

Due branch procedono su altre macchine: tornei a eliminazione diretta /
doppio KO, e drill/challenge.

- **Eliminazione diretta**: nessun attrito. Nell'area bracket/playoff
  esiste un solo template (`player/playoff_invitation.html`, già
  convertito); il resto saranno file nuovi, e il grosso del lavoro è in
  `models/` e `routes/`, che il redesign non tocca.
- **Challenge**: collisione reale. Dei 19 template dell'area solo 3 sono
  convertiti; gli altri sono nella lista "da rifare a mano". **Non
  convertire l'area challenge finché quel branch non è merged** — il
  `README.md` la mette al punto 4, quindi rimandarla non costa nulla.
- Chi lavora su quei branch può ignorare le classi `.c7-*`: il tema
  ridefinisce `.card`, `.btn`, `.table`, `.badge`, quindi **markup
  Bootstrap standard eredita il design**. La regola è solo negativa:
  niente `style="..."` con colori, niente `<style>` con gradienti.
- File conteso: `base.html`. Voci di menu e script nuovi vanno aggiunti
  dopo il merge del tema.
- Attriti minori attesi: `utils/feature_flags.py` (stesso dict
  `ENDPOINT_ROLES`), `translations/*.po` (rigenerare, non risolvere a
  mano), `CLAUDE.md`. Le migration non collidono: nomi date-prefixed
  distinti e il runner traccia per nome.

Ordine di merge: **tema → eliminazione diretta → challenge**. Il tema è il
branch orizzontale, e più resta fuori più conflitti genera.
