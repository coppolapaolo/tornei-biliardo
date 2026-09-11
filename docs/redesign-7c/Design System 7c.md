# Design System 7c — handoff di implementazione

Documento di riferimento per portare il redesign (prototipo `Redesign Mobile.dc.html`, turni 1–14)
sul progetto Flask `coppolapaolo/tornei-biliardo`.

I mockup sono **vincolanti su colore, tipografia, densità, raggi e pattern**; sono **indicativi sui
contenuti di esempio** (nomi, date, punteggi). Dove il layout cambia davvero rispetto all'attuale
è segnalato nella sezione 6 — quelle pagine vanno rifatte, non solo ricolorate.

---

## 1. Token

### 1.1 Colore

| Token | Valore | Uso |
|---|---|---|
| `--surface-bg` | `#E4E8E7` | fondo pagina, sempre. Mai bianco puro. |
| `--surface-card` | `#F5F7F6` | card, campi form, righe tabella, pill inattivi |
| `--surface-sunken` | `#ECEEED` | elementi disabilitati / bloccati |
| `--ink` | `#1B2124` | testo principale, bottone primario, sidebar desktop |
| `--ink-soft` | `#3D474A` | testo secondario forte, bottone terziario |
| `--ink-muted` | `#6B7679` | label, metadati, testo di supporto |
| `--ink-faint` | `#9AA3A6` | placeholder, icone inerti |
| `--line` | `#D3D8D7` | bordi e separatori su fondo pagina |
| `--line-soft` | `#E4E8E7` | separatori dentro le card |
| `--accent` | `#2C4A52` | accento primario: link, stati attivi, card in evidenza |
| `--accent-ink` | `#F2F8F7` | testo su `--accent` |
| `--accent-bright` | `#8FCDE8` | evidenza dentro blocchi `--accent` (barre, numeri) |
| `--accent-tint` | `#DDE9EE` | sfondo tenue info / badge neutro-accento |
| `--accent-tint-ink` | `#23404A` | testo su `--accent-tint` |

Semantici (usati **solo** per stato, mai decorativi):

| Ruolo | Fondo | Testo/icona | Forte |
|---|---|---|---|
| Successo | `#E4EDE9` | `#1D5F4A` | `#2C8A6B` |
| Errore | `#F3E2E0` | `#8A2C2C` | `#B23B3B` |
| Avviso | `#F0E9D8` | `#6E5417` | `#8A6A1F` |
| Info | `#DDE9EE` | `#23404A` | `#2C4A52` |

**Regola:** un solo colore semantico per schermata alla volta. Il verde non è un colore
decorativo: significa "confermato / pagato / completato".

### 1.2 Tipografia

- **Corpo e titoli:** Manrope (400 / 600 / 700 / 800). Fallback `system-ui, sans-serif`.
- **Cifre, codici, timestamp, stati:** JetBrains Mono (600 / 700 / 800).
  Vale per i numeri di servizio, fino a ~32px. La cifra protagonista di una
  schermata — il punteggio di una partita nelle 7c e 8b — è Manrope 800:
  lì il numero è un titolo. (Precisazione 2026-08-10, dalle schermate.)
  Tutto ciò che è un numero confrontabile (punteggi, iscritti, quote, XP, orari, `14 / 16`)
  va in mono, così le colonne si allineano.
- Titoli pagina: 22–24 px / 800 / `letter-spacing: -.025em`.
- Titolo card: 15–17 px / 800 / `-.02em`.
- Corpo: 13–14 px / 600. Metadati: 12 px / 600 `--ink-muted`.
- Label di campo e intestazioni tabella: 11–12 px / 800 / `letter-spacing: .06em` / MAIUSCOLO.
- Mobile: mai sotto 12 px; target tattili ≥ 44 px (i bottoni del prototipo sono 46–58 px).

### 1.3 Raggi, spaziature, ombre

| Token | Valore | Uso |
|---|---|---|
| `--r-pill` | `999px` | chip, badge, tab, toggle |
| `--r-card` | `20–26px` | card mobile (22 tipico), 20–22 desktop |
| `--r-field` | `18px` | campi form, bottoni pieni mobile |
| `--r-control` | `12–16px` | bottoni secondari, icone quadrate |
| Padding card | `16–20px` | mobile 16–18, desktop 18–20 |
| Gutter schermata | `18px` mobile · `28px` desktop | |
| Gap tra card | `10–16px` | |
| Ombra | `0 10px 24px -18px rgba(27,33,36,.6)` | solo su toast e overlay; le card **non** hanno ombra |

Le card si distinguono per **contrasto di superficie** (`#F5F7F6` su `#E4E8E7`), non per bordi né
ombre. Niente gradienti, niente bordo colorato a sinistra.

### 1.4 Movimento

Aggiunto l'11/09/2026: il prototipo è statico e non poteva mostrarlo. Scelto
guardando i gesti a confronto (`movimento/confronto.html`, decisione in
`movimento/README.md`).

| Token | Valore | Uso |
|---|---|---|
| `--c7-dur-base` | `250ms` | ciò che entra, si apre, cambia sotto gli occhi; cambio pagina |
| `--c7-dur-quick` | `150ms` | ciò che esce, si chiude, torna dal tocco |
| `--c7-ease` | `ease-out` | l'unica curva |
| `--c7-press` | `.94` | scala del comando premuto: la pressione è a 0 ms, si vede il ritorno |

Si animano solo `transform` e `opacity` (l'altezza di una sezione che si apre è
l'unica eccezione). Niente hover, niente blur, niente durate scritte a mano:
`test_motion_tokens.py` legge il tema e fa rosso. Con `prefers-reduced-motion`
le durate vanno a zero alla fonte; i battiti (`infinite`) tengono il proprio
`animation: none`.

---

## 2. Pattern con codice

Scritti come regole CSS da mettere in `static/css/theme-7c.css`, caricato **dopo** Bootstrap.

### 2.1 Testata di pagina (mobile)

Fissa in cima, stesso fondo della pagina, senza ombra.

```css
.page-head{position:sticky;top:0;z-index:5;background:var(--surface-bg);
  padding:20px 18px 12px;display:flex;align-items:center;gap:12px}
.page-head .back{width:46px;height:46px;border-radius:50%;background:var(--surface-card);
  border:0;color:var(--accent);font-size:16px;display:grid;place-items:center}
.page-head h1{margin:0;font-size:18px;font-weight:800;letter-spacing:-.025em}
.page-head .sub{font-size:12px;font-weight:600;color:var(--ink-muted)}
```

### 2.2 Card

```css
.card{background:var(--surface-card);border:0;border-radius:22px;padding:16px}
.card.is-accent{background:var(--accent);color:var(--accent-ink)}
.card.is-locked{background:var(--surface-sunken);opacity:.7}
```

### 2.3 Bottoni

```css
.btn-primary{height:56px;border-radius:18px;background:var(--ink);color:#fff;font-weight:800}
.btn-secondary{height:56px;border-radius:18px;background:var(--surface-card);color:var(--ink-soft);font-weight:700}
.btn-confirm{background:#2C8A6B;color:#fff}      /* solo azioni che creano/confermano */
.btn-danger{background:#F3E2E0;color:#8A2C2C}    /* distruttive: fondo tenue, mai rosso pieno */
```

Barra azioni in fondo alle pagine lunghe: `position:sticky;bottom:0` con sfumatura
`linear-gradient(to top, var(--surface-bg) 70%, transparent)`. Primaria a destra, "Annulla" a sinistra e stretta.

### 2.4 Pill / chip di stato

```css
.pill{height:38px;padding:0 16px;border-radius:999px;background:var(--surface-card);
  color:var(--ink-muted);font-size:13px;font-weight:700;display:inline-flex;align-items:center}
.pill.is-active{background:var(--ink);color:#fff;font-weight:800}
.badge-state{height:26px;padding:0 11px;border-radius:999px;
  font-size:10px;font-weight:800;letter-spacing:.04em}   /* testo SEMPRE maiuscolo */
```

### 2.5 Campi form

```css
.form-control,.form-select{height:58px;border-radius:18px;background:var(--surface-card);
  border:0;padding:0 16px;font-size:15px;font-weight:700}
.form-label{font-size:12px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink-muted);padding-left:4px}
.form-control.is-invalid{background:var(--surface-card);border:1.5px solid #B23B3B}
.invalid-feedback{font-size:12px;font-weight:700;color:#8A2C2C;padding-left:4px}
.form-text{font-size:12px;font-weight:600;color:var(--ink-muted);padding-left:4px}
```

I campi **non** hanno bordo a riposo; il bordo compare solo in errore (rosso) o focus (`--accent`).
Sotto ogni campo non ovvio va una `.form-text` che spiega la conseguenza, non la sintassi
(es. «Gli iscritti riceveranno una notifica»).

### 2.6 Stepper numerico (distanza, numero gare, quota)

Sostituisce `<input type=number>` ovunque il valore sia piccolo e vada toccato al volo:
due bottoni 52×52 `--r-control` ai lati, valore al centro in mono 30/800, e sotto una riga
di 12 px che traduce il numero in parole («si vince a 5 rack»).

### 2.7 Tabella (desktop)

Niente `table-striped`, niente bordi verticali.

```css
.table-7c{background:var(--surface-card);border-radius:22px;overflow:hidden}
.table-7c thead th{padding:12px 20px;font-size:11px;font-weight:800;letter-spacing:.06em;
  color:var(--ink-muted);border-bottom:1px solid var(--line-soft)}
.table-7c td{padding:14px 20px;border-bottom:1px solid var(--line-soft);vertical-align:middle}
.table-7c tr:last-child td{border-bottom:0}
.table-7c tr.is-attention{background:#F0E9D8}   /* riga che richiede azione */
.table-7c tr.is-done{opacity:.7}                /* riga conclusa/archiviata */
```

Le colonne numeriche vanno in mono. Le azioni di riga sono icone 34×34 con fondo `--surface-bg`,
allineate a destra, mai testo «Modifica | Elimina».

### 2.8 Sidebar desktop

```css
.side{width:244px;background:var(--ink);color:var(--surface-bg);padding:24px 16px;
  display:flex;flex-direction:column;gap:26px}
.side a{height:42px;border-radius:12px;padding:0 12px;display:flex;align-items:center;gap:11px;
  font-size:13px;font-weight:600;color:#B6BEC0}
.side a.is-active{background:var(--accent);color:#EAF6F8;font-weight:700}
.side .group-label{font-size:10px;font-weight:800;letter-spacing:.12em;color:#6E797C;padding:0 10px 8px}
```

Gruppi: **Generale · Persone · Gamification** (admin); il direttore ha una lista unica.
Il contatore di richieste è una pill numerica a destra della voce (rossa se bloccante, verde se solo informativa).
In fondo, sempre, la card utente con ruolo e logout.

### 2.9 Messaggi flash

Sostituiscono `alert alert-*` di Bootstrap 1:1 (stessa posizione nel `base.html`).

```css
.flash{border-radius:20px;padding:15px 16px;display:flex;gap:13px;align-items:flex-start}
.flash .ico{width:30px;height:30px;border-radius:50%;color:#fff;display:grid;place-items:center;
  font-size:12px;flex-shrink:0}
.flash-title{font-size:14px;font-weight:800}
.flash-body{margin-top:3px;font-size:13px;font-weight:600;line-height:1.45}
```

Mappatura categorie Flask → classe: `success → .flash-success`, `danger|error → .flash-error`,
`warning → .flash-warning`, `info → .flash-info`, con le coppie colore della sezione 1.1.
Versione compatta a pillola (h 46, `--r-pill`) per conferme senza corpo testo.

**Regole di scrittura del flash:** titolo = cosa è successo (max 4 parole);
corpo = il dato specifico o la conseguenza. Mai «Operazione completata con successo».

### 2.10 Toast della mascotte (Chalky)

Famiglia separata dai flash: i flash riguardano il sistema, i toast di Chalky riguardano il giocatore.

```css
.chalky{border-radius:24px;background:var(--surface-card);padding:14px 16px 14px 12px;
  display:flex;align-items:center;gap:12px;box-shadow:0 10px 24px -18px rgba(27,33,36,.6)}
.chalky img{width:68px;height:68px;object-fit:contain;flex-shrink:0}
.chalky .kicker{font-size:10px;font-weight:800;letter-spacing:.12em;color:var(--ink-muted)}
```

Pose in `static/img/chalk1..10.png`, già nel repo. Abbinamento evento → posa usato nel prototipo:

| Evento | Immagine | Kicker | Fondo |
|---|---|---|---|
| Bentornato / login | `chalk9` | TI DIAMO IL BENTORNATO! | card |
| XP ottenuti | `chalk1` | XP OTTENUTI | card |
| Level up | `chalk2` | LEVEL UP! | `--accent` |
| Nuovo traguardo | `chalk3` | NUOVO TRAGUARDO! | card |
| Traguardo raro | `chalk8` | TRAGUARDO RARO! | avviso |
| Streak | `chalk4` | STREAK! | card |
| Streak persa | `chalk5` | STREAK PERSA | errore |
| Quest completata | `chalk7` | QUEST COMPLETATA! | card |
| Funzione sbloccata | `chalk6` | NUOVA POSSIBILITÀ! | card |
| Traguardo leggendario (overlay) | `chalk10` | NUOVO TRAGUARDO · LEGGENDARIO | overlay |

Coda: un toast alla volta, 5 s ciascuno, i successivi rientrati e attenuati sotto il primo.
Un solo toast celebrativo per evento: se scattano insieme XP + level up + badge, si mostra
il più alto in gerarchia (badge > level up > XP) e gli altri finiscono nel riepilogo di fine gara.

### 2.11 Nav flottante mobile

Barra fissa in fondo, `--r-pill`, fondo `--surface-card`, icona attiva su `--ink`.
Ogni pagina mobile segue lo stesso ordine: **testata › contenuto › nav flottante**.

---

## 3. Cambi di layout rispetto all'attuale

Questi non si ottengono con il CSS: vanno riscritti i template.

1. **Fondo pagina grigio, non bianco.** Cambia `body` e ogni `.bg-white`/`.bg-light` residuo.
2. **Desktop admin e direttore passano a sidebar fissa a sinistra + contenuto a due colonne**
   (principale + colonna laterale 360–400 px). Oggi la navigazione è in alto: la navbar orizzontale
   sparisce sulle viste ≥ 1200 px e resta solo su mobile come nav flottante.
3. **Le tabelle Bootstrap diventano card-tabella** (sezione 2.7): niente bordi, righe alte 14 px di
   padding, stato come badge in ultima colonna, azioni come icone.
4. **Le dashboard perdono le "card KPI" generiche** e guadagnano una **fascia della gara in corso**
   a piena larghezza in cima (fondo `--accent`, puntino pulsante, tre numeri, CTA «Gestisci»).
   Se non c'è nulla in corso, la fascia non si mostra affatto — non va riempita con un placeholder.
5. **La modifica gara mostra in testa un avviso con il numero di iscritti** e blocca visivamente i
   campi ereditati dal campionato (`.card.is-locked` + lucchetto) invece di nasconderli.
6. **Il wizard campionato resta a 2 passi** ma con barra di avanzamento a due segmenti in testata e
   riepilogo del passo 1 in cima al passo 2.
7. **Le scelte a poche opzioni diventano card selezionabili** (classifica, strategia, disciplina,
   gestione dispari), non `<select>`. I `<select>` restano solo per liste lunghe (sala, campionato).
8. **Distanza e conteggi usano lo stepper** (2.6) al posto degli input numerici.
9. **Stati vuoti espliciti** con icona in cerchio, titolo, una riga di spiegazione e al massimo due
   azioni. Da usare al posto delle pagine che oggi restano bianche.
10. **Gamification separata dai flash**: i toast Chalky hanno un proprio contenitore in `base.html`,
    sotto la testata, indipendente dal blocco `get_flashed_messages`.

---

## 4. Terminologia

Uniformare il testo dell'interfaccia. A sinistra ciò che compare oggi in giro per i template,
a destra la forma da usare.

| Non usare | Usare | Nota |
|---|---|---|
| Torneo (per il contenitore stagionale) | **Campionato** | «Torneo» resta solo se è un evento singolo a sé |
| Evento / competizione | **Gara** | l'unità di una serata |
| Partita (dentro una gara) | **Match** | tra due giocatori |
| Set / frame / punto | **Rack** | l'unità di punteggio dentro un match |
| Round | **Turno** | gli abbinamenti generati |
| Girone all'italiana / svizzero | **Strategia di abbinamento: Amalfi / Random** | nomi già usati nel codice |
| Bye | **X · vinto a tavolino** | e le altre politiche: Lista d'attesa, X con challenge, Match a 3 |
| Iscrizione confermata/pagata | **Pagato / Da saldare** | badge in lista iscritti |
| Utente | **Giocatore** | «Utente» solo nell'area admin |
| Admin / superuser | **Amministratore** | |
| Organizzatore | **Direttore di gara** | ruolo; abbreviato «Direttore» nei badge |
| Gestore locale | **Gestore sala** | |
| Punti esperienza / punti | **XP** nei toast, **punti** nei riepiloghi | non mischiare nella stessa schermata |
| Achievement | **Traguardo** | «Badge» è l'immagine, «Traguardo» è l'obiettivo |
| Streak | **Streak** | resta invariato (è già nel prodotto) |
| Salva con successo | **Salva modifiche** | i bottoni dicono l'azione, non l'esito |
| Sei sicuro? | **Elimina la gara / Sospendi il set** | la conferma ripete l'azione con il nome dell'oggetto |

Regole di tono: seconda persona singolare, niente punto esclamativo fuori dai toast di Chalky,
date in `gg/mm/aaaa` nelle tabelle e in forma estesa («martedì 5 agosto») nelle intestazioni mobile.

---

## 5. Ordine di lavoro consigliato

**Già scritti e pronti da committare** (in questo progetto):

| File | Contenuto |
|---|---|
| `static/css/tokens-7c.css` | tutte le variabili della sezione 1. Nessuna regola. Non tocca `variables.css` esistente. |
| `static/css/theme-7c.css` | la sezione 2 completa + override dei componenti Bootstrap usati (card, btn, form, table, alert, badge, modal, dropdown, nav-tabs, progress) |
| `templates/base.html` | guscio 7c: sidebar da `lg` in su, nav flottante sotto, testata a blocchi, flash riscritti, contenitore `#chalky-container`. Logica Jinja invariata (auth, ABAC, `feature_visible`, debug footer, gamification bridge, polling, analytics). |
| `templates/components/_user_menu.html` | menu utente condiviso fra sidebar e testata mobile (sostituisce il dropdown della vecchia navbar) |
| `templates/components/_form_macros.html` | macro `field`, `textarea`, `choice`, `stepper`, `toggle`, `notice`, `inherited` + `form_macros_scripts()` |
| `static/js/gamification.js` | riscritto sui toast `.c7-chalky` in `#chalky-container`. API invariata (`showGamificationEvent`, `testGamificationEffects`) |
| `templates/components/_unified_dashboard_header.html` | intestazione dashboard 7c (titolo + azioni da `vm.caps`) |
| `templates/components/_separated_dashboard_content.html` | sezioni match / gare / campionati in card 7c. Logica `vm.*`, `GaraStatus`, filtri e `url_for` invariata |
| `templates/components/_director_dashboard_content.html` | match individuali proposti in card 7c |
| `templates/components/_gara_management.html` | pannello gestione gara: macchina a stati invariata, azioni e avvisi 7c |
| `templates/components/_gara_inscriptions.html` | iscritti + lista d'attesa in righe 7c |
| `templates/components/_round_management.html` | configurazione per turno: markup 7c, API ADR-027 e id invariati |
| `templates/components/_gara_edit_form.html` | modifica gara: avviso iscritti, classifica ereditata bloccata, campi 7c |
| `templates/admin/gara_edit.html` | pagina modifica gara sui blocchi `page_*`; script invariato |
| `templates/admin/campionato_wizard_step1.html` | wizard passo 1: barra a due segmenti, playoff Elite/Academy |
| `templates/admin/campionato_wizard_step2.html` | wizard passo 2: riepilogo passo 1 + default gare |

> Nei due wizard il blocco `scripts`, prima annidato dentro `content`, è stato portato al livello
> corretto del template (stesso comportamento, posizione giusta nella pagina).

Ordine:

1. Committa i file sopra. Da soli, cambiano l'aspetto di **tutte** le pagine.
2. Verifica le pagine più dense (dashboard, gestione gara): la vecchia navbar è nascosta via CSS,
   quindi eventuali link che stavano solo lì vanno spostati in sidebar.
3. Rimuovi da `static/css/gamification.css` le regole `.gamification-toast*` ormai morte.
4. Applica le macro form (`_form_macros.html`) ai template di creazione e modifica.
5. Le schermate con layout nuovo della sezione 6 (in grassetto).
6. Passata di rifinitura sul resto, che a quel punto eredita già lo stile.

### 5.1 Toast di Chalky — fatto

`gamification.js` è già riscritto: monta in `#chalky-container`, emette `.c7-chalky`, applica
`--level` / `--rare` / `--lost`, accoda con un toast pieno e fino a due anteprime `.is-queued`,
collassa gli eventi simultanei tenendo il più alto in gerarchia (badge > level up > XP), rispetta
`prefers-reduced-motion` e legge le pose da `#gamification-config`.

Da verificare al primo giro: `ConfettiEffect` è richiamato con la stessa guardia `typeof` di prima;
se nel repo vive in un file separato continua a funzionare, altrimenti i coriandoli semplicemente
non partono (nessun errore).

Controlla anche `static/css/gamification.css`: le vecchie regole `.gamification-toast*` non servono
più e vanno rimosse per non lasciare CSS morto.

### 5.2 Note di integrazione

- I CSS 7c vanno caricati **per ultimi**, dopo `variables.css` e `main.css`: se qualche regola di
  `main.css` usa `!important`, va rimossa lì, non duplicata qui.
- `.navbar { display: none !important }` in `theme-7c.css` neutralizza eventuali navbar residue in
  altri template: se ne trovi, vanno rimosse dal markup, non lasciate nascoste.
- Il `<main>` non è più `.container`: le pagine che davano per scontato il gutter Bootstrap vanno
  riviste (ora il gutter è su `.c7-content`).
- `base.html` definisce quattro blocchi nuovi utilizzabili dalle pagine:
  `page_head` (sostituisce l'intera testata), `page_title`, `page_sub`, `page_actions`, `actionbar`.

---

## 6. Mappa schermate → template

Prototipo `Redesign Mobile.dc.html`. **In grassetto = layout da riscrivere**, il resto eredita dal tema.

| Prototipo | Template |
|---|---|
| 13a messaggi flash | **`templates/base.html`** (blocco alert), `templates/errors/*.html` |
| 13b toast Chalky, livello, traguardi | **`templates/base.html`** (contenitore toast), `static/js/gamification.js`, `templates/gamification/*` |
| 14a admin desktop | **`templates/dashboard/admin.html`**, `templates/components/_admin_dashboard_content.html`, `templates/admin/kpi.html`, `templates/admin/users_list.html`, `templates/admin/director_requests.html`, `templates/admin/venue_manager_requests.html` |
| 14b direttore desktop | **`templates/dashboard/director.html`**, `templates/components/_director_dashboard_content.html`, `_separated_dashboard_content.html`, `_gara_management.html`, `_gara_inscriptions.html`, `_round_management.html` |
| 14c wizard campionato | `templates/admin/campionato_wizard_step1.html`, `campionato_wizard_step2.html`, `templates/components/_campionato_create_modal.html` |
| 14c nuova gara | `templates/components/_new_gara_modal.html`, `_distance_configurator.html` |
| 14c modifica gara | **`templates/admin/gara_edit.html`**, `templates/components/_gara_edit_form.html` |
| turni precedenti: live match, inserimento rack, trio, multi-set | `templates/match/*`, `templates/components/_round_management.html` |

> I nomi dei partial sotto `templates/components/` vanno verificati sul branch corrente prima di
> iniziare: alcuni sono stati rinominati e la mappa riflette lo stato al 5 agosto 2026.

---

## 7. Cosa nei mockup è indicativo

- Nomi giocatori, sale, date, punteggi, XP e classifiche: dati di scena.
- Il numero di voci in sidebar e di colonne nelle tabelle: adattare a ciò che il modello espone davvero.
- Le icone Font Awesome scelte: sostituibili, purché resti una sola famiglia e una sola dimensione per contesto.
- Le altezze dei frame (390×844, 1440×900): servono a inquadrare, non sono breakpoint. I breakpoint
  reali restano quelli di Bootstrap; l'unico salto strutturale è a `lg` (sidebar ↔ nav flottante).
