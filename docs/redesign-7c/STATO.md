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

**Pagina gara a linguette** — chiuso il punto 1 dei disallineamenti. Sotto i
992px la pagina non e' piu' una pila unica: si divide nelle viste del prototipo
(8a) **Turni · Classifica · Iscritti**, piu' **Gestione** per chi dirige, con la
barra di pill appiccicata sotto la testata e la card scura "IL TUO MATCH ·
TAVOLO n → Apri" in cima alla vista Turni.

- **Come e' fatto: filtro CSS, non pannelli separati.** Ogni sezione dichiara le
  viste a cui appartiene (`data-c7-tab="turni gestione"`), il contenitore
  dichiara quella attiva (`data-c7-view`) e la sezione 16 di `theme-7c.css`
  nasconde il resto. **Un solo nodo nel DOM per sezione**: costruire pannelli
  per il mobile avrebbe richiesto di includere due volte `_round_management`
  (9 `id` e uno `<script>`), `_gara_public_link` e `_gara_tables_config`, cioe'
  di rompere il loro JS. Il selettore usa `~=`, quindi una sezione puo' stare
  in due viste — e' cosi' che lo spareggio e la Gestione a turno finito restano
  raggiungibili dalla vista di partenza oltre che da Gestione.
- **`display: contents` sui contenitori di impaginazione** (`c7-tabflat`). Il
  filtro svuota una delle due colonne di `c7-cols`, che resterebbe un flex item
  alto zero: il `gap` lo conta comunque e fra le sezioni compare un buco
  doppio. Su mobile quei contenitori non disegnano box e le sezioni diventano
  figlie della pila di pagina — misurato, i distacchi sono tutti 12px.
- **Vista di partenza**: le partite se ci sono, altrimenti Gestione per chi
  dirige (in iscrizione l'azionabile e' avviare la gara), altrimenti Iscritti.
  **Con meno di due viste la barra non compare** e la pagina resta la pila di
  prima: e' il caso del giocatore o dell'ospite su una gara in iscrizione.
- **La vista scelta sopravvive al ricaricamento** (`sessionStorage`, chiave per
  gara): quasi ogni azione della pagina ricarica, e senza memoria il direttore
  tornava ogni volta sulla vista di partenza.
- **Il compromesso della PR #36 e' chiuso davvero** (verificato, era la
  richiesta): informazioni e iscritti non stanno piu' *dentro* la sezione
  Partite — hanno una vista loro, quindi non risalgono piu' con lei in fase di
  gioco. E gli iscritti non sono piu' richiusi: nella loro vista sono il
  soggetto, resta richiudibile la sola informativa. Anche la **Gestione mobile
  non e' piu' un collapse**: in una linguetta dedicata richiuderla era solo un
  tap in piu' per arrivare all'unica cosa che contiene.
- **Area tattile.** Il pill del prototipo e' alto 42px, sotto il minimo di 48:
  l'area sensibile si allarga di 3px per lato con uno `::after`, quindi
  l'aspetto e' quello del prototipo e il bersaglio e' 48. Verificato con
  `elementFromPoint`. Aggiunte anche le frecce sinistra/destra: dichiarare
  `role="tablist"` senza gestirle e' una promessa ARIA non mantenuta.

**Difetti trovati strada facendo e riparati:**

- **Le partite in corso erano card scure.** `_match_card.html` dava
  `c7-card--accent` a ogni partita in gioco, mentre nella 8a le partite del
  turno sono card **chiare** e il fondo accento e' riservato alla scorciatoia:
  una lista di card scure svuotava di significato la card scura che conta. Ora
  la superficie e' quella normale, con il pill "IN CORSO". Nello stesso file
  sono spariti i letterali di stato (`'completed'`, `'playing'`, `'pending'`) in
  favore di `MatchStatus`, e il pill non ha piu' i colori scritti a mano.
- **Lo script del commutatore non partiva.** Inline durante il parsing, cercava
  `#garaViews`, che viene dopo: `getElementById` tornava `null` e la funzione
  usciva subito, in silenzio. Ora aspetta `DOMContentLoaded`.
- **Due test rossi da settimane, e non per un difetto vero.**
  `test_rilievi_20260728_mobile_azionabile.py` asseriva
  `id="matchNavSidebar" class="d-none d-md-block"` come stringa esatta: il
  guscio 7c della pagina partita (`3e83e1b`) ha cambiato quelle classi e reso
  la copia condizionale, e i due test sono rimasti indietro. Riscritti
  sull'invariante — **un solo ritorno per viewport** — con un helper che non
  assume l'ordine degli attributi. (STATO diceva "1 rosso in integrazione":
  erano 3.)

**Aggiunto `tests/new/integration/test_gara_view_tabs.py`.** L'invariante che
conta e' **nessuna sezione irraggiungibile**: se una sezione dichiara una vista
che non ha il suo pill, su mobile quel contenuto non e' raggiungibile da
nessuna parte, e la pagina non da' errori. Il test l'ha subito trovata: gli
involucri della scorciatoia e delle partite venivano emessi vuoti anche in fase
di iscrizione, dichiarando una vista Turni che non esisteva. Ora non si emettono
affatto.

**Cosa e' verificato e cosa no.** Desktop 1512px: verificato, **invariato** —
la barra e' `display:none` e `c7-cols` resta a due colonne. Ruoli: direttore,
giocatore con partita in corso, giocatore senza partita, ospite non iscritto;
stati: iscrizione, gioco, conclusa con spareggio. Provata l'azione (la
scorciatoia porta sulla partita giusta) e la memoria della vista.
**Il mobile e' stato guardato a 390px logici col ripiego dello `zoom`, non con
la device toolbar**: viewport e media query erano quelle della finestra a
500px, cioe' comunque il ramo mobile, e `document.body.scrollWidth` dice 390
senza sbordamenti. La resa vera su 390px va confermata col device mode.

**Badge di livello ricostruito** — primo pezzo del punto 1 di "Da fare". Era
sparito nell'handoff sia da `base.html` sia da `static/js/gamification.js`, e
con esso **la scala d'intensita' §11**: senza il badge il dispatcher era stato
riscritto "un toast per ogni evento", quindi ogni guadagno di XP apriva un
toast — esattamente il contrario di quello che la scala prescrive (XP =
badge, niente toast) — e il **cap anti-invasivita'** (al piu' un toast
celebrativo per sessione, con il level-up esente) non c'era piu'.

- **Dove vive**: nella testata del guscio, prima dell'avatar. E' la pill scura
  con trofeo e "Lv N" della schermata 13b — 34px su mobile, 40 da 576px, dove
  compare anche l'XP. Non sulla home, come nel prototipo, perche' gli XP si
  guadagnano in partita e in gara: se il badge non e' visibile la', un
  guadagno di XP non ha alcun riscontro (per scelta non fa toast). Su desktop
  il livello resta anche nella barra laterale, come testo — quello e' il posto
  che gli da' il prototipo, e li' non serve che sia vivo.
- **Una sola istanza per pagina**: il modulo JS cerca per `id`. Metterlo anche
  nella barra laterale avrebbe duplicato gli id.
- **Colori riportati in palette**: l'anello e l'alone del level-up erano ambra
  e oro (`#f59e0b`, `rgba(251,191,36)`), colori che in 7c non esistono — il
  giallo e' il semantico "attenzione". Ora sono `--c7-accent-bright`, lo stesso
  azzurro dell'anello che si e' appena chiuso. Il "buco" dell'anello combaciava
  con `--bs-light` di Bootstrap: ora col fondo accento della pill.
- **Conseguenza sulla testata della gara**: il sottotitolo aveva quattro voci
  (data · disciplina · distanza · sala) e con il badge andava a **tre righe** su
  390px. Ora e' quello del prototipo (8a) — **sala · distanza** — e data e
  disciplina restano da 992px in su. La disciplina della gara e' comunque solo
  il default: quella vera e' del turno, e ogni turno la scrive da se'.

**La suite e' tutta verde per la prima volta da inizio redesign**: 1520 unit,
550 integrazione (il rosso "voluto" era il promemoria del badge) e i **26
controlli headless** di `tests/frontend`, che non partivano nemmeno — morivano
all'import su `GamificationBadge is not defined`.

Verificato anche a mano: un evento `xp` fa pulse e count-up **senza toast**, un
`levelup` aggiorna il numero, accende l'alone e apre **un solo** toast.

**Le quattro pagine dei progressi** (`gamification/dashboard`, `achievements`,
`streaks`, `quests`) rifatte sulla **#11a**. Erano Bootstrap puro: `container
py-4`, `row`/`col`, testate a tinta piena (`bg-primary text-white`,
`bg-success`, `bg-info`), briciole di pane — le uniche dell'app — e una tabella
a quattro colonne per le quest completate.

- **Progressi**: card scura del livello con la barra XP, streak come elenco
  raggruppato, prossimi sblocchi con le condizioni a spunta, achievement
  recenti come tessere, quest attive.
- **Achievement**: riepilogo con barra a due segmenti e tre numeri, poi gli
  achievement **per categoria come elenco**, non come griglia di medaglie. La
  **difficolta' e' una parola** ("Raro", "Epico"), come chiede il prototipo:
  via il viola `bg-purple` definito in un `<style>` inline e via la gemma
  dorata. Sbloccato = tessera accento, bloccato = tessera affossata e riga
  spenta.
- **Streak**: card scura con il fuoco e la cifra grande, poi una card per tipo
  con attuale/record, i tre traguardi (4/12/52 settimane) accesi o spenti e il
  prossimo traguardo. Via il gradiente della card principale.
- **Quest**: card con chip del tipo, ricompensa, progresso e scadenza; le
  completate diventano un elenco raggruppato invece della tabella.

**Difetti trovati e riparati:**

- **La barra XP della pagina progressi era sempre vuota.** Il markup era
  `style="width: 0%"` con `data-percentage` e l'animazione affidata a un JS
  che **non esiste**: a qualunque livello la barra restava a zero, senza errori
  da nessuna parte. Ora la larghezza la scrive il server.
- **"12 / 24%"** sotto le barre degli achievement progressivi: mescolava il
  conteggio con la percentuale. Ora e' "12 / 50" come nel prototipo — il
  traguardo non arriva dal servizio ma la percentuale lo determina.
- **I toast di questa pagina erano un sistema a parte**: toast Bootstrap propri
  e un `location.reload()` per ogni evento, quindi un guadagno di XP apriva un
  toast qui e faceva pulsare il badge altrove. Ora passa dal sistema Chalky del
  guscio, che applica la scala d'intensita'.
- **Quattro copie divergenti delle etichette dei tipi** (streak, quest,
  difficolta', categoria), come catene di `{% if %}` nel markup: i "Tornei
  settimanali" comparivano solo in due. Ora sono una mappa sola in
  `components/_gamification_labels.html`.
- **Un comando morto**: "Usa Freeze" era un pulsante `disabled`, e lato server
  la funzione non esiste (nessuna route, nessun servizio). Al suo posto lo
  stato: quanti freeze hai e cosa serve per non perdere la streak. **Il
  prototipo mostra il pulsante attivo: implementarlo e' lavoro di dominio, non
  di interfaccia** — da decidere a parte.

**Divergenza dichiarata**: il prototipo mette sulla pagina Quest tre linguette
(Attive / In arrivo / Completate). Qui sono tre sezioni: i gruppi sono corti e
gia' intitolati, e un commutatore aggiungerebbe un tap per vedere due righe.
**Quando si faranno i match individuali** — che di linguette hanno bisogno
davvero (#9a: "Da giocare / In attesa / Giocati") — conviene rendere riusabile
il commutatore della pagina gara e riconsiderare anche questa.

Aggiunte al tema le forme che il prototipo ripete dalla 8a alla 11a e che
finivano riscritte a mano ogni volta: `c7-rows` (elenco raggruppato con righe
divise), `c7-sechead` (titolo di sezione con azione a destra), `c7-tile`
(tessera icona, piena o affossata), `c7-dim`, piu' l'adattamento di `.progress`
di Bootstrap dentro una card accento.

**Match individuali: 1 pagina su 10** (`individual_match/dashboard.html`),
rifatta sulla **#9a**. E' l'ingresso dell'area, quindi va per prima.

- **Testata doppia**: la pagina ripeteva titolo e sottotitolo dentro il
  contenuto, sotto quelli del guscio. Il guardiano
  `test_single_page_header.py` non la vedeva perche' cerca una seconda
  `c7-head`, e qui erano un `<h1>` e un `<p>`. **Da tenere presente: la classe
  di difetti e' piu' larga del test.**
- **Ordine per cosa devi fare**, come il prototipo: attendono la tua risposta →
  da giocare → in attesa dell'altro → giocati (spenti). Prima era per tipo di
  oggetto (proposte, match in corso, match recenti) con le card annidate a due
  livelli e i bordi colorati per stato.
- **Niente sottotitolo ne' azione in testata su mobile**: con entrambi la
  testata sticky arrivava a **quattro righe** su 390px, un terzo dello schermo.
  La proposta nuova e' la prima voce dell'elenco in fondo (e su desktop resta
  il pulsante in testata, dove lo spazio c'e').
- Il pannello "Azioni Rapide" era in realta' **la navigazione dell'area** — la
  barra laterale ha la sola voce "Match Individuali" — e ora ha la forma di
  elenco del menu profilo del prototipo.
- `proposal.opponent` **non esiste** sul modello: una proposta ha `proposer`,
  `invitations` (proposta diretta) o nessuno (proposta aperta). Jinja lo
  risolveva a Undefined, cioe' vuoto, in silenzio.

**`individual_match/matches.html`** rifatta anche lei, e qui i difetti erano
peggio della grafica:

- **Il filtro per stato era rotto.** L'opzione "In corso" valeva `playing` —
  che e' lo stato dei match *di gara* — mentre un match individuale ha
  `in_progress`: selezionarla svuotava l'elenco. E "Completati" (`completed`)
  non prendeva i match `validated`, che sono comunque giocati. Ora si filtra
  per **gruppo** (da giocare / in corso / giocati / annullati), calcolato dal
  server con `MatchStatus.is_finished`, e i pill sono quelli del prototipo.
- **I match individuali salvano la disciplina col vocabolario vecchio.**
  `individual_match.discipline` contiene `palla_8`; `gara.discipline` contiene
  `8_ball`, il valore dell'enum `Discipline`. Le migration di quell'area hanno
  ancora `DEFAULT 'palla_8'`. Le opzioni del filtro erano scritte a mano coi
  valori vecchi, quindi funzionavano **per caso** sui dati esistenti e
  smetterebbero di funzionare su un match salvato col valore dell'enum. Ora le
  opzioni si ricavano dai record, che vale in entrambi i casi.
  ~~**Da decidere a parte: una migration che normalizzi quel campo.**~~
  **Chiuso** (vedi "Vocabolario unico delle discipline" più sotto).
- L'elenco degli avversari si ripuliva dai duplicati **lato JS**, dopo averli
  stampati: ora non li stampa.
- `Discipline` aggiunta ai globals Jinja, con la nota sul vocabolario doppio.
- `.c7-pill` non va piu' a capo: "Da giocare" sbordava dalla pastiglia.

**`individual_match/proposals.html`** rifatta anche lei. Le condizioni della
sfida erano ricopiate **tre volte**, una per linguetta: ora sono due macro.
Altri difetti trovati:

- **Stati in inglese sotto gli occhi dell'utente**: `status.value.title()`
  stampava "Pending", "Accepted". Ora una mappa tradotta, che serve anche a
  scegliere il tono del badge.
- **Il rifiuto di un invito non veniva mai riconosciuto**: il template cercava
  `declined`, l'enum `InvitationStatus` dice **`rejected`**. Un invito rifiutato
  prendeva quindi il colore neutro del ramo `else`.
- **`proposal.entry_fee` non esiste sul modello.** C'era un blocco
  `{% if proposal.entry_fee %}` che mostrava una quota d'iscrizione: Jinja lo
  risolveva a Undefined, cioe' non compariva mai. Rimosso.
- **Il ricaricamento automatico dipendeva da una classe CSS**: contava i
  `.badge.bg-warning` in pagina per decidere se ricaricare ogni 30s. Cambiando
  i badge si sarebbe spento in silenzio. Ora il conteggio delle proposte da
  rispondere arriva dal server in un `data-`.
- **Data di creazione al posto di quella utile**: la card mostrava
  `created_at`. Ora mostra in grande **quando si gioca**. La scadenza non e'
  ripetuta perche' il servizio la fissa due ore prima dell'orario del match,
  quindi sarebbe la stessa data.

**Dati di prova seminati in locale** (`ProposalService.create_direct_proposal`):
una proposta diretta di `pa` a `pb` e `player1`, 9-Ball, al 5, fra quattro
giorni. Serviva perche' l'area era **inverificabile a vuoto** — le sezioni
"attendono la tua risposta" e "in attesa" non si vedevano. **Si e' portata
dietro un effetto collaterale**: la gamification e' agganciata alla creazione,
quindi `pa` ha guadagnato achievement e due livelli. La proposta e' rimasta
apposta: serve anche ai prossimi passi. `/reset` la porta via.

**`individual_match/match_detail.html`**: il **guscio**. Il segnapunti, lo
storico rack e il punteggio erano gia' 7c (sono gli stessi componenti
`_unified_*` della pagina di gara), quindi il lavoro e' stato solo intorno:
testata dai blocchi (`pa vs pb`, disciplina · sala) invece di briciola di pane
piu' card che ripeteva disciplina, luogo e stato; `c7-cols` invece di
`row`/`col-md-8`; stati **tradotti** (erano `status.value.replace('_',' ')
.title()`, cioe' "In Progress"); il ritorno non e' piu' un pulsante fra le
azioni, perche' vive nella testata come in ogni altra pagina 7c. Tolto anche
qui il blocco **"Entry Fee"**, campo che sul modello non esiste.
Difetto mio, corretto subito: la prima stesura metteva una pastiglia di stato
sopra il punteggio, e `_unified_match_score` ne disegna gia' una — lo stato si
leggeva due volte.

**Restano 6 file** (1602 righe): `create_proposal` (489), `statistics` (345),
`proposal_detail` (224), `discover_players` (206), `admin_overview` (199),
`availability` (139). **Il prossimo da fare e' `create_proposal`**: e' il piu'
grande e il prototipo lo copre bene (#9a·2 — date come opzioni selezionabili
con `c7-choice`, sala, messaggio, barra d'azione appiccicata in fondo).
`availability` ha la sua schermata nella #9a·3 (calendario del mese).
`proposal_detail` ha ancora il blocco "Entry Fee" da togliere (due
occorrenze). Il
prototipo copre la proposta di date (#9a·2, opzioni selezionabili con
`c7-choice`) e le disponibilita' (#9a·3, calendario del mese).
**Attenzione ai dati**: in locale c'e' **una** partita individuale e **zero**
proposte, quindi le sezioni "attendono la tua risposta" e "in attesa" non sono
verificabili senza crearne una dal flusso vero.

**Vocabolario unico delle discipline** — chiuso il rilievo aperto sui match
individuali, per decisione dell'utente ("le discipline devono stare in un enum
unico; quello che si visualizza e' una stringa tradotta").

Il problema era piu' largo del campo `individual_match.discipline`. Non
esistevano due enum Python: ne esisteva **uno solo** (`Discipline`) piu' un
**vocabolario fantasma** — `palla_8`/`palla_9`/`palla_10`, il nome italiano
usato come valore persistito, mai dichiarato, sparso in **11 file** fra default
di colonna, firme di servizio e `<option>` di form. Peggio di due enum
dichiarati: due enum si vedono e prima o poi si uniscono, un vocabolario
fantasma passa da `String(50)` senza che nulla lo validi.

Perche' nessuno se n'era accorto: `Discipline("palla_8")` solleva `ValueError`,
che `discipline_display` cattura ripiegando su `raw.replace("_"," ").title()`
→ **"Palla 8"**, che a schermo sembra giusto. **Il fallback difensivo
mascherava esattamente il caso che doveva segnalare.**

- **Il secondo enum c'era davvero**, non dichiarato:
  `MultiDisciplineService.get_available_disciplines` conteneva la propria
  tabella valore/etichetta, e altre tre mappe (`get_discipline_rules`, i
  preset) erano indicizzate sulle stesse chiavi fantasma. Ora tutto deriva da
  `Discipline`.
- **Le regole per disciplina non venivano mai trovate**: indicizzate su
  `palla_*` contro dati `8_ball`, ogni chiamata cadeva sul dizionario vuoto.
  Coperte ora tutte e sette le discipline (erano quattro).
- **`Discipline.normalize`** e' il ponte per i dati storici. Restituisce `None`
  sull'ignoto invece di inventare un default: la scelta del ripiego spetta al
  chiamante, ed era proprio il ripiego nascosto a coprire il difetto.
- **Etichette tradotte**: `display_name` passa da `gettext`. Come nel resto del
  progetto il msgid e' l'italiano — **"Palla 8"** — e l'inglese e' la
  traduzione (**"8-Ball"**). Prima l'app era incoerente con se stessa: mostrava
  "8-Ball" quasi ovunque e "Palla 8" nel form di creazione proposta.
- **Migration** `20260811_normalize_discipline_vocabulary`: converte tutte e
  nove le colonne di disciplina, comprese le due **JSON** di `set`
  (`discipline_rotation`, `discipline_assignment`), dove i valori sono annidati
  nel testo. Idempotente, e segnala i residui invece di tacerli. In locale ha
  convertito 1 riga.
- **Guardia**: `tests/new/unit/test_discipline_single_vocabulary.py` presidia
  l'invariante — nessun letterale nel codice vivo (**commenti inclusi**: un
  esempio in un docstring e' il modo in cui un valore sbagliato si ripropaga),
  ogni default di colonna dentro l'enum, l'elenco dei form derivato dall'enum,
  le etichette che passano da `gettext`. L'unico file autorizzato a nominare il
  vocabolario vecchio e' `status_enum.py`, che dichiara il ponte.
- **209 letterali normalizzati nei test** (87 file). Attenzione: la
  sostituzione automatica ha colpito anche il file della guardia, svuotandone
  di senso i casi di prova — ora quei valori sono composti a runtime apposta.
- Riparate strada facendo **tre entry fuzzy del catalogo EN con placeholder
  incompatibili** (`msgid "%(n)s rack giocati"` → `msgstr "%(num)s rack"`), che
  facevano fallire `pybabel compile` con due errori.

**Non e' un cambio di comportamento in produzione**: `tiebreaker/services.py`,
dove il disallineamento produceva un confronto sempre falso, **non ha
chiamanti** fuori da `tests/legacy/` — lo spareggio vivo e'
`models/competition/tiebreaker_service.py`. Corretto per coerenza, non come
bugfix urgente.

**Match individuali: gli ultimi 6 file** — l'area e' chiusa (10 su 10).
`create_proposal` (la piu' grande) segue la 9a·2: sezioni intitolate — chi
gioca, quando, dove, come si gioca, messaggio — scelte come card `c7-choice`,
distanze come `c7-stepper`, barra d'azione in fondo. Il prototipo propone piu'
date fra cui scegliere; il dominio ne ha una sola (`scheduled_at`), quindi
resta il campo data con la stessa gerarchia. `availability` segue la 9a·3 nella
forma ma non nel calendario: qui la disponibilita' non e' per data ma **per
sala** (ADR-033), cioe' giorni della settimana e fascia oraria.

**Difetti trovati e riparati nell'area:**

- **La barra d'azione appiccicata finiva sotto la nav flottante.** `.c7-actionbar`
  era `bottom: 0`, cioe' incollata al bordo del viewport, mentre la nav mobile e'
  `fixed` sopra di essa: il comando principale della pagina non si vedeva. Era il
  **primo uso della classe** nell'app, quindi non era mai emerso.
- **La spunta delle `c7-choice` non seguiva la selezione**: era resa solo dal
  server sull'opzione preselezionata, quindi restava li' anche dopo che l'utente
  ne sceglieva un'altra. Vale per ogni pagina che usa la macro.
- **Le disponibilita' non erano modificabili**: l'unico modo di cambiare i giorni
  di una sala era riaggiungerla da zero. Ora ogni sala si modifica dov'e'. Tolto
  anche l'interruttore "attualmente disponibile": una riga spenta sparisce
  dall'elenco (il servizio filtra `is_available`), quindi spegnerla sembrava
  cancellarla — per non essere piu' disponibile si usa "Rimuovi".
- **`proposal_detail` cercava `declined`** mentre l'enum dice **`rejected`**: un
  invito rifiutato si mostrava come neutro. Etichette e toni ora vivono in
  `components/_proposal_labels.html`, condiviso con l'elenco.
- **La panoramica admin stampava "In Progress"** (`status.value.replace('_',' ')
  .title()`). Gli stati tradotti sono ora in `components/_match_status_labels.html`,
  condiviso con il dettaglio del match.
- **Le statistiche mostravano quattro traguardi finti** ("Prima Vittoria",
  "Striscia di 3"…): il servizio non restituisce alcun achievement, quindi si
  vedeva sempre e solo il ramo "vuoto" scritto a mano. Al loro posto il link ai
  traguardi veri, avvolto in `feature_visible` (in produzione la gamification e'
  ancora solo per chi dirige).
- **TomSelect era caricato dalla CDN senza `integrity`**: aggiunto SRI a CSS e JS.

**Area challenge: 16 template, chiusa** — e' il pezzo che l'utente ha chiesto
esplicitamente. Catalogo e card erano gia' 7c dall'handoff; il resto era
Bootstrap **senza una sola stringa dentro `_()`**. Il flusso segue la 9b:
dettaglio con foto, istruzioni in card scura, i tuoi tentativi; registrazione
del punteggio con la cifra grande e i due tasti tondi (`c7-scorepad`); pass/fail
come due bersagli da 96px (`c7-choice--big`); challenge di gara con la card
scura che spiega perche' stai giocando e la classifica.

**Cinque guasti veri, tutti silenziosi:**

- **Il catalogo era interamente rotto.** Il JS componeva gli indirizzi su
  `/challenge/<id>/...` mentre il blueprint e' montato su **`/challenges/`**:
  click sulla card, preferiti ed elimina rispondevano tutti 404, e l'unico
  segnale era "errore sconosciuto". Ora gli indirizzi li scrive il server.
- **`/challenges/attempt/<id>` rispondeva 500** su ogni tentativo numerico
  concluso: la pagina calcolava una percentuale su `challenge.max_score`, campo
  che **sul modello non esiste** — in Jinja, dividere per Undefined solleva.
- **Il dettaglio della challenge di gara rispondeva 500** appena la gara aveva
  una challenge: la route confrontava `c.get("gara_challenge", {}).get("id")` su
  un **modello**, non un dizionario. Con la lista vuota il generatore non
  iterava, quindi in sviluppo non si vedeva.
- **La cronologia challenge del profilo era sempre vuota**: la route costruiva i
  dizionari leggendo `challenge.max_score`, l'`AttributeError` finiva in un
  `except Exception: pass`, e il template intanto leggeva chiavi che non
  esistevano (`attempt.gara_challenge`, `attempt.created_at`). Ora l'except
  scrive nel log invece di tacere.
- **L'inserimento dei tentativi nella pagina partita era invertito**: il ramo
  "tocca a te" apriva un `<div>` che non chiudeva mai e non conteneva campi,
  mentre i campi stavano nel ramo di chi *non* puo' inserire. In piu'
  `querySelector('[data-player-id]')` prendeva sempre il primo blocco della
  pagina, quindi con due challenge la seconda registrava il valore della prima.

Aggiunti `components/_challenge_bits.html` (miniatura e pastiglia del tipo, che
sei componenti ricopiavano — con **due indirizzi diversi e sbagliati** per la
stessa immagine) e le due mappe di etichette. Le API admin restituiscono ora
l'indirizzo dell'immagine gia' pronto.

**Amministrazione** — ripresa dopo che l'utente ha chiesto il redesign completo.

- **170 icone invisibili.** Tredici pagine admin usavano `bi bi-*` (Bootstrap
  Icons), che **non e' caricato**: al loro posto c'era il vuoto. Convertite tutte
  a Font Awesome, l'unico set del design system.
- **I grafici della dashboard KPI non sono mai esistiti.** La pagina metteva
  Chart.js e i suoi script in `{% block extra_head %}` / `{% block extra_js %}`,
  **blocchi che `base.html` non definisce**: il codice veniva scartato e le
  quattro tele restavano vuote. Stessa cosa per lo stile di `venue_detail`.
  Rinominati in `head_extra` / `scripts`; i colori dei grafici vengono ora dai
  token.
- **Testate doppie** in dodici pagine (admin, sale, campionato, gamification):
  ora riempiono i blocchi del guscio. Le pagine di gamification non avevano
  nemmeno un `block title`, quindi la linguetta del browser diceva "Campionato
  Biliardo".
- **Cifre illeggibili**: dentro un blocco a fondo scuro la regola generale sui
  titoli li lasciava scuri su scuro (la card XP dei pannelli gamification).
- **Tabelle larghe su mobile**: nuova `.c7-table-cards` — sotto i 992px la
  tabella diventa una pila di card con l'etichetta di colonna a sinistra. Usata
  da utenti (14 colonne) ed elenco gare pubblico.
- **Colori Bootstrap a mano** (`#0d6efd`, `#198754`, `#e9ecef`…) nei due wizard
  di creazione gara: portati sui token.

**Traduzioni EN al 100%** (2151 stringhe). Le 627 fuzzy non sono state approvate
in blocco: erano accoppiamenti automatici sbagliati, e sono state riscritte.

**Test.** 1533 unit, 550 integrazione, 26 controlli headless: tutti verdi.
`pyright` 0 errori, `black` e `flake8` puliti. Cinque test rossi durante il
lavoro erano scritti sulla stringa esatta del markup vecchio ("Crea Nuova
Challenge", `id="formatMulti"`…): riscritti sull'invariante.

**Dati di prova seminati in locale**: due challenge (una a punteggio e una
pass/fail) con sei tentativi, due challenge agganciate alla gara 3 con la
relativa classifica, e un campionato con tre gare. Servivano perche' l'area
challenge era **inverificabile a vuoto** — nel DB non c'era nemmeno una riga.
`/reset` li porta via.

## Disallineamenti fra prototipo e codice

Rilevati confrontando le schermate del prototipo con l'app in esecuzione.
Quelli sopra sono chiusi; questi no.

1. ~~**Pagina gara, mobile (8a·1) — linguette Turni / Classifica / Iscritti.**~~
   **Chiuso** (vedi "Fatto"). Restano tre scostamenti minori, tutti nel senso
   "il design system dice una cosa un po' diversa dalla singola schermata":
   il kicker della card scura e' il `c7-kicker` da 10px del tema e non i 12px
   del prototipo (cambiarlo toccherebbe ogni card convertita); il raggio della
   card e' `--c7-r-card` (22px) e non i 24px della schermata, che non e' un
   token; e la testata del turno mostra il pill "IN CORSO" invece del "2 di 4
   chiusi" del prototipo — quello sta in `_match_cards_mobile`, gia' convertito
   nell'handoff, e vale piu' come nota per quando lo si riaprira'.
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
7. ~~**Match individuali (9a).**~~ **Chiuso**: dieci template su dieci. Restano
   due divergenze dichiarate — la proposta ha **una** data e non un elenco di
   opzioni (il modello ha `scheduled_at`), e le disponibilita' sono per sala e
   non per giorno del mese (ADR-033), quindi niente calendario.
8. **Gara pubblica per l'ospite (10a).** Due tessere ("Turno corrente",
   "Stato"), classifica provvisoria e invito a registrarsi in card scura. Da
   confrontare con `_guest_info.html`.

## Da fare

1. ~~**Gamification giocatore.**~~ **Chiusa**: badge e quattro pagine, vedi
   "Fatto".
2. ~~**Rimandati per decisione dell'utente (2026-08-10)**: 14 pannelli di
   gamification admin e 12 pagine admin.~~ **Ripresi e chiusi il 2026-08-11**,
   quando l'utente ha chiesto il redesign completo (vedi "Amministrazione" in
   "Fatto").
3. ~~**Traduzioni EN.**~~ **Fatte a redesign concluso**, come deciso: il
   catalogo EN e' al **100% (2151 stringhe)**. Le 627 fuzzy non sono state
   approvate in blocco ma riscritte: erano accoppiamenti automatici sbagliati
   ("amministrazione" → *Registrations*).
4. ~~**Match individuali** (10 file).~~ **Chiusi**, vedi "Fatto".
5. **Pulizia di `main.css` e `variables.css`** — resta l'ultimo punto del
   README. Va fatta con il browser davanti, regola per regola: sono i due file
   che il tema sovrascrive, quindi togliere quella sbagliata non da' errore, da'
   una pagina storta.
6. **Referto TPA, esercizi, schede, esami e disegnatore** (dal 2026-09-19) — il
   referto TPA non era mai passato dal redesign (nessuna schermata nel
   prototipo), e l'area esercizi aveva preso il tema senza che nessuno ne
   ripensasse i percorsi. Canvas di 46 schermate, venti
   decisioni congelate, undici fasi: lo stato schermata per schermata sta in
   [`canvas-tpa-esercizi/STATO.md`](canvas-tpa-esercizi/STATO.md), il piano in
   [`canvas-tpa-esercizi/PIANO.md`](canvas-tpa-esercizi/PIANO.md).
   **Fatte le fasi 2–5**: referto TPA (19/09, #475–#483), esami (19/09,
   #484–#489), modello dell'esercizio con «Oggi» e il voto (20/09, #490–#498),
   eseguire un esercizio colpo per colpo e con estrazione (20/09, #501–#509).
   Restano schede, andamento, istruttori, disegnatore e la chiusura.

### Rilievi di dominio trovati durante la conversione (non toccati)

Non sono lavoro di interfaccia: si annotano perche' vanno decisi, non fatti di
nascosto.

- **`Challenge.max_score` e `Challenge.name` non esistono.** `models/exam/`
  (l'area esami, in lavorazione sull'altro branch) li usa in
  `get_max_possible_score` e in `ExamChallenge.__repr__`: quelle chiamate
  sollevano `AttributeError`. Il redesign non li ha aggiunti apposta — sarebbe
  un cambio di modello con migration, in collisione con quel branch. **Una
  challenge numerica non dichiara un massimo**: l'interfaccia mostra quindi il
  punteggio e basta, senza "/N" ne' barra di progresso (divergenza dichiarata
  dal prototipo 9b·3).
- **`raise ValueError("Campionato not found")`** in
  `models/campionato/tournament_service.py` (11 occorrenze): la convenzione del
  progetto vuole `NotFoundError` → 404. Oggi la pagina di un campionato
  inesistente risponde **500**. Cambiarlo tocca anche i test legacy: da fare a
  parte.
- **`record_challenge_attempts`** (registrazione a lotti dei tentativi) non ha
  piu' chiamanti: `_match_challenge_input.html` registra un tentativo per volta.
  La route c'e' ancora.

## Rilievi aperti dal giro visivo

Visti ma non ancora affrontati, in ordine di dubbio:

- ~~Bottoni verdi nel catalogo challenge.~~ **Chiuso dal prototipo**: nella
  14c "Crea campionato" e "Crea gara" sono verde pieno. Il verde e' la
  conferma conclusiva di un flusso, non solo il semantico "ok".
- ~~**Card "Unisci utenti (merge)" in `/admin/users`.**~~ **Chiusa**: era una
  card con la testata a fondo giallo e sotto la striscia vuota del pannello
  richiuso. Ora e' una riga che si apre, come le altre sezioni richiudibili.
- ~~**`admin/gara_challenge_classification.html` non e' internazionalizzata.**~~
  **Chiusa** con la conversione dell'area challenge: il corpo della pagina —
  che era in italiano fisso, fuori da `_()` — e' tradotto e passato al design
  system.
- **La card "Gestione" resta visibile e vuota a gara conclusa** — solo
  titolo e badge di stato, nessuna azione. Il badge e' l'unico posto in
  pagina dove lo stato e' scritto, quindi non basta nasconderla.
- ~~**Info e Iscritti richiudibili su mobile** stanno ancora dentro la sezione
  Partite.~~ **Chiuso dalle linguette**: hanno una vista loro, e gli iscritti
  non sono piu' richiusi.
- ~~**`public/garas_list.html` su mobile.**~~ **Chiusa**: sotto i 992px la
  tabella si impagina a card (`.c7-table-cards`), una per gara, con
  l'etichetta di ogni colonna a sinistra e il valore a destra. La stessa
  classe serve la tabella utenti dell'admin, che di colonne ne ha quattordici.
  Un DOM solo, quindi i filtri e l'ordinamento in JS continuano a funzionare.
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
  orizzontale. Funziona, ma la resa a card sarebbe migliore: ora c'e'
  `.c7-table-cards`, quindi basta aggiungere la classe e le `data-label`.

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
- **Aprire i DevTools stringe il viewport, e questo dalla sessione pilotata
  funziona** (verificato il 2026-08-10, suggerimento dell'utente): il tasto
  `alt+cmd+i` inviato alla pagina apre davvero i DevTools, che agganciati a
  destra portano `innerWidth` a **357px** — piu' stretto dei 390 che si
  volevano provare, con media query **vere** (non il ripiego dello `zoom`, che
  le lascia al valore della finestra). E' il modo migliore per verificare il
  mobile senza chiedere aiuto.
  Quello che **non** si ottiene cosi' e' `pointer: coarse`: `cmd+shift+m` per
  la device toolbar non scatta, perche' la scorciatoia vuole il focus dentro i
  DevTools e il tasto arriva alla pagina. Per i componenti dietro il touch
  (il tabellone orizzontale) serve ancora la mano dell'utente — oppure si
  forza a runtime la regola senza la condizione, che mostra la resa ma non
  prova l'innesco.
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
