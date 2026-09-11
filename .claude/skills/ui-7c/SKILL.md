---
name: ui-7c
description: Costruisce o modifica interfacce nel design system 7c — mobile first ma verificate anche su desktop, coerenti col prototipo. Attiva quando si crea una pagina nuova, si cambia un layout, si tocca un template o del CSS, o quando l'utente dice che una schermata non gli piace / non è bella.
allowed-tools: Read, Edit, Write, Glob, Grep, Bash, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__computer, mcp__claude-in-chrome__javascript_tool, mcp__claude-in-chrome__resize_window, mcp__claude-in-chrome__tabs_context_mcp, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__tabs_close_mcp, mcp__claude-in-chrome__read_console_messages
---

# Interfacce nel design system 7c

L'app deve sembrare un'app moderna e professionale, non un'impalcatura
Bootstrap ricolorata. Questa skill serve a **produrre** interfaccia; chi
documenta le decisioni è `ui-conventions`, chi rivede è l'agente
`design-review`.

## Regola zero: il prototipo prima del codice

**Non scrivere markup prima di aver guardato la schermata corrispondente del
prototipo.** È l'errore che si ripete: si lavora "in stile 7c" a memoria e si
consegna qualcosa che il committente vede subito più povero dell'originale.

Il prototipo è `docs/redesign-7c/Redesign Mobile.dc.html` (5.400 righe, 30+
schermate). Il browser pilotato **non apre `file://`**, quindi:

```bash
cd docs/redesign-7c && python3 -m http.server 8899   # poi chiudilo a fine lavoro
# http://127.0.0.1:8899/Redesign%20Mobile.dc.html#8b
```

### Quale schermata guardare

Il documento è cronologico al contrario: **turno 14 in cima, turno 1 in
fondo**. I turni **1–6 sono direzioni scartate: non sono riferimento**. Valgono
7c e tutto ciò che viene dopo.

| Ancora | Cosa mostra |
|---|---|
| `#7c` | Origine della direzione: home giocatore e **partita in corso** |
| `#8a` | Gara (a linguette), calendario gare, notifiche, profilo |
| `#8b` | **Orizzontale**: tabellone da tavolo e classifica larga |
| `#9a` `#9b` | Match individuali (proposte, disponibilità) · challenge |
| `#10a` `#10b` | Ospite in sola lettura · direttore che gioca e gestisce |
| `#11a` | Progressi: XP, streak, achievement, quest |
| `#12a` `#12b` | Sale biliardo · account e fine gara |
| `#13a` `#13b` | Messaggi flash · gamification (toast, ricompense) |
| `#14a` `#14b` `#14c` | Admin desktop · direttore desktop · direttore mobile (wizard) |

### Se la schermata non c'è nel prototipo

Succede spesso: il prototipo copre il percorso principale, non tutta l'app.
Allora **si interpreta**, non si inventa:

1. **Cerca la schermata più vicina per funzione**, non per argomento. Una
   lista con filtri → `#8a` (elenco gare). Un form lungo → `#14c` (wizard).
   Una pagina di sola lettura → `#10a`. Una pagina dove si compie l'azione
   principale → `#7c` (partita).
2. **Riusa la soluzione già presa lì**, alla lettera: stessa gerarchia
   (kicker → titolo → dato), stessi raggi, stesse altezze dei comandi.
3. **Non introdurre valori nuovi.** Colori, raggi, spaziature e misure sono in
   `static/css/tokens-7c.css`. Se serve un valore che non c'è, quasi sempre
   significa che stai risolvendo il problema in un modo che il design system
   già risolve diversamente.
4. **In dubbio, copia invece di creare.** Due schermate che si somigliano
   troppo sono un problema molto minore di due che si somigliano poco.

## Le regole non negoziabili

- **Mai bianco puro.** Fondo pagina `--c7-bg`, superfici `--c7-card`,
  affossato `--c7-sunken`.
- **Niente ombre sulle card, niente gradienti.** Le superfici si distinguono
  per tono. Ombre solo su toast e overlay.
- **Target tattile ≥ 48px.** I comandi frequenti sono grossi: il segnapunti
  usa bersagli da 104px.
- **Tipografia**: Manrope per l'interfaccia. JetBrains Mono per i **numeri di
  servizio** (quote, XP, conteggi, orari, date — fino a ~32px). La **cifra
  protagonista** di una schermata (il punteggio) è Manrope 800, come nel
  prototipo: è un titolo, non un dato tabellare. Aggiungi
  `font-variant-numeric: tabular-nums` dove il numero cambia sotto gli occhi.
- **Il verde è la conferma conclusiva di un flusso** ("Crea gara"), non solo il
  semantico "ok". Il rosso pieno solo per il pallino live; le azioni
  distruttive usano fondo tenue `--c7-err-bg`.
- **Stato bloccato / ereditato / concluso** = superficie `--c7-sunken`, mai il
  grigio disabilitato di Bootstrap.
- **Poche opzioni importanti** = `.c7-choice` (card selezionabili), non
  `<select>`. **Numeri piccoli e frequenti** = `.c7-stepper`, non
  `input[type=number]`.
- **Terminologia**: campionato ≠ gara ≠ partita · "X a tavolino" mai *bye* ·
  "direttore di gara" mai *director* · turno mai *round* · "conclusa" per una
  gara finita, "da giocare" per una partita in attesa.

## Come si costruisce

- **La testata è una sola**, quella di `base.html`. Si riempiono i blocchi
  `page_back` / `page_title` / `page_sub` / `page_actions`. Mai una seconda
  `c7-head` dentro `content`, mai sovrascrivere `page_head` (contiene freccia
  e avatar del mobile). Lo verifica
  `tests/new/unit/test_single_page_header.py`.
- **Il punto di rottura è `lg` (992px)**, non `md`: è lì che compaiono barra
  laterale e seconda colonna e sparisce la nav flottante. Vale per ogni
  `d-*-none` e `order-*`.
- **Impaginazione**: `c7-cols` (due colonne da lg, pila sotto) e `c7-stack`
  (pila con gap). La distanza fra le sezioni la dà la pila, **non** `mb-3`
  sparsi. `c7-sections` nasconde le sezioni che non producono nulla.
- **Il tema ridefinisce `.card`, `.btn`, `.table`, `.badge`, `.form-control`,
  le utility `bg-*`**: markup Bootstrap standard eredita già il design. Serve
  lavoro solo dove cambia il layout o dove ci sono stili hardcoded.
- **Mai** `style="..."` con colori fuori palette, mai `<style>` con gradienti.
- Le classi ricorrenti: `c7-card` (+`--accent --locked --ok --warn --err`)
  `c7-grid` `c7-kpis` · `c7-pill` `c7-state` `c7-label` `c7-kicker` ·
  `c7-choice` `c7-stepper` · `c7-score` `c7-rackpad` `c7-racklist` `c7-board`
  (segnapunti e tabellone) · `c7-table-wrap` · `c7-flash` `c7-chalky` ·
  `c7-empty` `c7-avatar` `c7-divider` `c7-sep`.

## Movimento

Il prototipo è statico: sul movimento non dice niente, e la scala l'ha decisa
l'utente guardando i gesti a confronto (`docs/redesign-7c/movimento/`). Le
regole, presidiate da `tests/new/unit/test_motion_tokens.py`:

- **Durate solo dai token**, mai millisecondi scritti a mano: `--c7-dur-base`
  (250 ms) per ciò che entra, si apre o cambia sotto gli occhi;
  `--c7-dur-quick` (150 ms) per ciò che esce, si chiude o torna dal tocco.
  Una curva sola, `--c7-ease`. Le uscite sono più veloci delle entrate.
- **Solo `transform` e `opacity`**: stanno sul compositore e non costano
  niente su un telefono vecchio. Niente `box-shadow`, `filter`, colori su
  molti elementi, cascate su liste lunghe. L'altezza di una sezione che si
  apre è l'unica eccezione.
- **Il tocco è istantaneo**: lo schiacciamento (`scale(var(--c7-press))`) ha
  `transition-duration: 0ms`, è il ritorno che si vede. L'azione parte al
  tocco, l'animazione accompagna, non fa aspettare.
- **Niente hover, niente decorazione**: l'app è touch. Un movimento che non
  spiega un cambio di stato o non dà riscontro non si mette. I battiti
  (`infinite`) sono ammessi solo per il pallino live e portano il proprio
  guard `prefers-reduced-motion`; tutto il resto è coperto dai token, che con
  «riduci movimento» vanno a zero.
- `gamification.css` ha un lessico suo, voluto: non lo si allinea.

## Trappole del progetto

- **Ogni `<form method="POST">` vuole il token CSRF**, prima riga dentro il
  form: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
  Senza, la schermata è bellissima e il pulsante risponde 400 «Sessione
  scaduta». Chi invia con `fetch` usa invece l'header
  `{'X-CSRFToken': csrfToken()}`. **Nessun test te lo dirà**:
  `WTF_CSRF_ENABLED = False` nella configurazione di test, quindi il buco si
  vede solo provando l'azione a mano (punto 5 della verifica) — o in
  produzione. Dettagli in `templates/CLAUDE.md`.
- **Ogni stringa visibile dentro `_()`**, comprese quelle nei componenti che
  stai solo spostando. Le traduzioni EN si rigenerano a fine redesign.
- **`|tojson` obbligatorio** per ogni stringa tradotta dentro JavaScript: un
  apostrofo italiano rompe tutto il JS della pagina. Gli `onclick` che lo
  usano vogliono apici singoli. Vedi `templates/CLAUDE.md`.
- **Route nuova** → entry in `ENDPOINT_ROLES` (`utils/feature_flags.py`),
  altrimenti in produzione è admin-only (ADR-028); e i link nei menu vanno
  avvolti in `{% if feature_visible('endpoint.name') %}`.
- **Componenti inclusi due volte** (mobile/desktop): consentito solo se non
  contengono `id` né `<script>`.
- **Enum, non letterali**: `MatchStatus.is_finished(...)`, `UserRole.…`,
  `GaraStatus.PLAYING.value`.

## Verifica — prima di dire che è fatto

1. **Mobile e desktop 1512px**, sempre entrambi. Dal browser pilotato il
   mobile si guarda **ridimensionando la finestra**: scheda nuova,
   `resize_window` **come prima azione** (prima di navigare), poi si misura con
   `document.documentElement.clientWidth`. Chrome su macOS si ferma a 500px, ma
   500 è **sotto il punto di rottura lg (992px)**: la barra laterale sparisce,
   compare la nav flottante, e fra 390 e 500 il tema non ha altri breakpoint.
   È una verifica vera, non un ripiego. Per i soli ritorni a capo a 390 resta
   `document.documentElement.style.zoom = (innerWidth/390)`, che però **non
   sposta le media query**: dichiaralo per quello che è.

   ⚠️ **Non aprire i DevTools dal browser pilotato.** Con i DevTools aperti
   ogni misura mente: `clientWidth` riporta la larghezza dello schermo in pixel
   fisici (3008 su questo Mac), `outerWidth` diventa **0**, e
   `matchMedia('(min-width: 992px)')` resta `true` a qualunque dimensione — il
   layout sembra bloccato su desktop e `resize_window` risponde «Successfully
   resized» senza che cambi niente. Il segnale è `window.outerWidth === 0`; si
   esce con `cmd+alt+i`, che li chiude. Le scorciatoie arrivano al browser, ma
   i **controlli dentro il pannello** no (l'input va al tab), quindi la device
   toolbar parte a una larghezza arbitraria che non si può cambiare: se serve
   davvero un 390px con touch reale, chiedilo all'utente.
2. **`document.body.scrollWidth`** deve essere uguale alla larghezza del
   viewport: se è maggiore, qualcosa sborda.
3. **Il CSS è servito con `?v=`**: dopo averlo modificato il browser continua a
   servire la versione vecchia. Forzalo e controlla il risultato con
   `getComputedStyle`, non a occhio:
   ```js
   document.querySelectorAll('link[rel=stylesheet]').forEach(l => {
     const u = new URL(l.href); u.searchParams.set('cb', String(performance.now())); l.href = u.toString();
   });
   ```
4. **Componenti dietro una media query che non riesci a far scattare** (il
   tabellone `#8b` sta dietro `orientation: landscape` + `pointer: coarse`, e
   il device mode non è sempre raggiungibile dal browser pilotato): il nodo
   esiste comunque nel DOM e le regole si applicano lo stesso, quindi puoi
   leggere `getComputedStyle` sul nodo nascosto per confermare i valori —
   ma **non è una verifica visiva**. Dichiaralo, e chiedi all'utente il
   controllo con device mode + touch prima di dire che è chiuso.
5. **Prova l'azione**, non solo l'aspetto: clicca il comando che hai
   ridisegnato e verifica che l'endpoint risponda (e rimetti a posto il dato
   di prova).
6. **`pytest tests/new/unit/ -n auto`** — copre integrità dei template,
   `url_for` inesistenti e testata doppia.

## Ambiente

- App su **porta 5001** (`python app.py`). Login senza password:
  `/debug/login/admin`, `/debug/login/pa` (direttore), `/debug/login/player1`,
  `/debug/login/player2`. Funziona **solo con `DEBUG_MODE` attivo** (default in
  sviluppo): in produzione quelle route rispondono 403, ed e' bene che resti
  cosi' — sono scorciatoie che autenticano senza password.
- Se le misure smettono di avere senso (`outerWidth` uguale a `innerWidth`, o
  a `screen.width`, o **0**), quasi sempre ci sono i DevTools aperti: chiudili
  con `cmd+alt+i` e rimisura. Se non basta, apri una scheda nuova e
  ridimensionala **come prima azione**.
- Diario del redesign e disallineamenti noti col prototipo:
  `docs/redesign-7c/STATO.md`.
