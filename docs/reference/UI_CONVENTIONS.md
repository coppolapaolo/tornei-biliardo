# UI Conventions

Questa documentazione raccoglie le convenzioni UI del progetto per mantenere coerenza visiva e semantica.

**Framework**: Bootstrap 5.1.3 + Font Awesome 6.0.0

---

## Sommario

1. [Icone (Font Awesome)](#icon-conventions-font-awesome-6)
2. [Colori e Stati](#colori-e-stati)
3. [Bottoni](#bottoni)
4. [Badge](#badge)
5. [Alert e Messaggi](#alert-e-messaggi)
6. [Card](#card-structure)
7. [Layout e Spacing](#layout-e-spacing)
8. [Typography](#typography)
9. [Form](#form-conventions)
10. [**Mobile-First Design**](#mobile-first-design) ⭐
11. [Responsive](#responsive-breakpoints)
12. [Pagina gara del direttore](#pagina-gara-del-direttore)
13. [Movimento](#movimento)
14. [Changelog Decisioni](#changelog-decisioni)

---

## Icon Conventions (Font Awesome 6)

Le icone sono fornite da [Font Awesome 6 Free](https://fontawesome.com/icons). Questa tabella definisce l'associazione standard tra concetti e icone.

### Entità Principali

| Concetto | Icona | Classe FA | Note |
|----------|:-----:|-----------|------|
| **Partite/Match** | 🛡️ | `fa-shield-halved` | Duello 1v1 - scudo diviso evoca due contendenti |
| **Gare** | 🎯 | `fa-bullseye` | Competizione singola |
| **Campionati** | 🏆 | `fa-trophy` | Serie di gare |
| **Discipline** | 🎱 | `fa-8-ball` | Tipo di gioco (palla 8, 9, 10...) |
| **Challenge** | ⭐ | `fa-star` | Sfide tecniche opzionali |

### Utenti e Ruoli

| Concetto | Icona | Classe FA | Note |
|----------|:-----:|-----------|------|
| **Utenti/Iscritti** | 👥 | `fa-users` | Gruppi di persone |
| **Profilo Utente** | 👤 | `fa-user` | Singolo utente |
| **Admin** | 🔧 | `fa-cogs` | Gestione sistema |
| **Direttore** | 📋 | `fa-clipboard-list` | Gestione gare |

### Azioni e Stati

| Concetto | Icona | Classe FA | Note |
|----------|:-----:|-----------|------|
| **Azioni Rapide** | ⚡ | `fa-bolt` | Quick actions nel sidebar |
| **Proposte Match** | 🤝 | `fa-handshake` | Inviti/accordi tra giocatori |
| **Streak** | 🔥 | `fa-fire` | Serie consecutive |
| **Calendario/Date** | 📅 | `fa-calendar` | Eventi e scadenze |
| **Luogo/Venue** | 📍 | `fa-map-marker-alt` | Posizione geografica |

### Gamification

| Concetto | Icona | Classe FA | Note |
|----------|:-----:|-----------|------|
| **XP/Livelli** | ⭐ | `fa-star` | Progressione |
| **Achievement** | 🏅 | `fa-medal` | Obiettivi raggiunti |
| **Leaderboard** | 📊 | `fa-chart-line` | Classifiche |

### Navigazione e UI

| Concetto | Icona | Classe FA | Note |
|----------|:-----:|-----------|------|
| **Lista/Elenco** | 📋 | `fa-list` | Visualizzazione lista |
| **Dettagli/Vedi** | 👁️ | `fa-eye` | Visualizza dettaglio |
| **Modifica** | ✏️ | `fa-edit` | Azione modifica |
| **Elimina** | 🗑️ | `fa-trash` | Azione elimina |
| **Aggiungi** | ➕ | `fa-plus` | Azione aggiungi |
| **Indietro** | ⬅️ | `fa-arrow-left` | Navigazione indietro |

### Privacy e Visibilità

| Concetto | Icona | Classe FA | Note |
|----------|:-----:|-----------|------|
| **Privacy/Sicurezza** | 🔒 | `fa-lock` | Impostazioni privacy, protezione dati |
| **Nascondi** | 👁️‍🗨️ | `fa-eye-slash` | Rende elemento non visibile ad altri |
| **Mostra** | 👁️ | `fa-eye` | Rende elemento visibile (unhide) |
| **Profilo privato** | 🔒 | `fa-user-lock` | Indica profilo con restrizioni privacy |

---

## Colori e Stati

### Semantica Colori Bootstrap

| Colore | Classe | Significato | Uso nel progetto |
|--------|--------|-------------|------------------|
| **Verde** | `success` | Positivo, completato | Vittorie, azioni riuscite, conferme |
| **Giallo** | `warning` | Attenzione, in corso | Stati intermedi, pending, attenzione |
| **Rosso** | `danger` | Negativo, errore | Sconfitte, errori, azioni distruttive |
| **Blu chiaro** | `info` | Informativo | Dati neutrali, statistiche |
| **Blu** | `primary` | Principale | CTA, azioni primarie, link |
| **Grigio** | `secondary` | Secondario | Azioni minori, elementi disabilitati |

### Stati Gara/Match

| Stato | Badge | Alert | Descrizione |
|-------|-------|-------|-------------|
| Draft | `bg-secondary` | - | Bozza, non visibile |
| Iscrizioni Aperte | `bg-info` | `alert-info` | Accetta nuove iscrizioni |
| Iscrizioni Chiuse | `bg-warning` | `alert-warning` | Pronto per iniziare |
| In Corso | `bg-primary` | `alert-primary` | Partite attive |
| Completato | `bg-success` | `alert-success` | Terminato con successo |
| Annullato | `bg-danger` | `alert-danger` | Cancellato |

---

## Bottoni

### Gerarchia Bottoni

| Tipo | Classe | Uso |
|------|--------|-----|
| **Primario** | `btn-primary` | Azione principale della pagina (1 per pagina) |
| **Successo** | `btn-success` | Conferme, salvataggi, azioni positive |
| **Warning** | `btn-warning` | Azioni che richiedono attenzione |
| **Danger** | `btn-danger` | Eliminazioni, azioni distruttive |
| **Outline** | `btn-outline-*` | Azioni secondarie, navigazione |
| **Secondary** | `btn-secondary` | Azioni terziarie, annulla |

### Dimensioni

| Size | Classe | Uso |
|------|--------|-----|
| Small | `btn-sm` | Azioni inline, tabelle, card (più comune: 170 occorrenze) |
| Default | - | Form principali, modali |
| Large | `btn-lg` | Hero sections, CTA prominenti |

### Pattern Comuni

```html
<!-- Azione primaria -->
<button class="btn btn-primary">Salva</button>

<!-- Azione secondaria -->
<button class="btn btn-outline-secondary">Annulla</button>

<!-- Azione distruttiva -->
<button class="btn btn-outline-danger btn-sm">
    <i class="fas fa-trash"></i> Elimina
</button>

<!-- Gruppo azioni in card -->
<div class="btn-group btn-group-sm">
    <a class="btn btn-outline-primary"><i class="fas fa-eye"></i></a>
    <a class="btn btn-outline-secondary"><i class="fas fa-edit"></i></a>
</div>
```

---

## Badge

### Uso per Stato

| Contesto | Classe | Esempio |
|----------|--------|---------|
| Vittoria | `badge bg-success` | "Vinto", conteggi positivi |
| Sconfitta | `badge bg-danger` | "Perso", errori |
| In corso | `badge bg-warning` | "Pending", "In attesa" |
| Info/Neutro | `badge bg-info` | Statistiche, conteggi |
| Contatori | `badge bg-secondary` | Numeri, quantità neutre |
| Nuovo/Attivo | `badge bg-primary` | Elementi evidenziati |

### Pattern Comuni

```html
<!-- Badge su tab -->
<span class="badge bg-warning ms-1">{{ count }}</span>

<!-- Badge stato -->
<span class="badge bg-success">Completata</span>

<!-- Badge con icona -->
<span class="badge bg-info"><i class="fas fa-star"></i> +50 XP</span>
```

---

## Alert e Messaggi

### Tipologie

| Tipo | Classe | Uso |
|------|--------|-----|
| Info | `alert-info` | Informazioni generali (più comune: 68 occorrenze) |
| Warning | `alert-warning` | Avvisi, attenzione richiesta |
| Success | `alert-success` | Conferme, operazioni riuscite |
| Danger | `alert-danger` | Errori, problemi |

### Pattern

```html
<!-- Alert informativo -->
<div class="alert alert-info">
    <i class="fas fa-info-circle"></i> Messaggio informativo
</div>

<!-- Alert dismissibile -->
<div class="alert alert-warning alert-dismissible fade show">
    Attenzione: ...
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
</div>

<!-- Alert compatto -->
<div class="alert alert-success py-2 mb-0">
    <small><i class="fas fa-check"></i> Operazione completata</small>
</div>
```

---

## Sistema Notifiche JavaScript

**File**: `static/js/notifications.js`

Sostituisce i nativi `alert()` con componenti Bootstrap per una UX migliore.

### Funzioni Disponibili

| Funzione | Uso | Comportamento |
|----------|-----|---------------|
| `showSuccess(msg)` | Operazioni riuscite | Toast verde, auto-hide 3s |
| `showError(msg)` | Errori | Toast rosso, persistente (click per chiudere) |
| `showWarning(msg)` | Avvisi | Toast giallo, auto-hide 3s |
| `showInfo(msg)` | Informazioni | Toast blu, auto-hide 3s |
| `showConfirm(msg, onConfirm, options)` | Conferme critiche | Modal Bootstrap con callback |
| `showValidationError(el, msg)` | Validazione form | Alert inline sotto l'elemento |
| `clearValidationError(el)` | Rimuove validazione | Pulisce stato errore |

### Helper per Form/Link con Conferma

| Funzione | Uso | Pattern HTML |
|----------|-----|--------------|
| `confirmSubmit(form, msg, opts)` | Form submission | `onsubmit="return confirmSubmit(this, 'Confermi?')"` |
| `confirmLink(link, msg, opts)` | Link navigation | `onclick="return confirmLink(this, 'Confermi?')"` |
| `confirmAction(msg, action, opts)` | Azione generica | `onclick="confirmAction('Confermi?', () => doSomething())"` |

### Esempi d'Uso

```javascript
// Successo
showSuccess('Operazione completata!');

// Errore
showError('Errore durante il salvataggio');

// Conferma con callback
showConfirm('Eliminare questo elemento?', () => {
    deleteItem(id);
});

// Conferma con opzioni personalizzate
showConfirm('Terminare la gara?', onConfirm, {
    title: 'Conferma Terminazione',
    confirmText: 'Termina',
    confirmClass: 'btn-warning'
});

// Validazione form
if (!isValid) {
    showValidationError(inputElement, 'Campo obbligatorio');
    return;
}
```

### Componenti HTML Richiesti

Presenti in `base.html`:

```html
<!-- Toast Container -->
<div id="toast-container" class="toast-container position-fixed top-0 end-0 p-3"></div>

<!-- Confirm Modal -->
<div class="modal fade" id="confirmModal" tabindex="-1">...</div>
```

### Mapping da alert()/confirm() Nativi

| Prima | Dopo |
|-------|------|
| `alert('Errore: ' + msg)` | `showError('Errore: ' + msg)` |
| `alert('Completato!')` | `showSuccess('Completato!')` |
| `if (confirm(msg)) { ... }` | `showConfirm(msg, () => { ... })` |
| `if (!confirm(msg)) { return; }` | `showConfirm(msg, () => { /* resto funzione */ })` |
| `onsubmit="return confirm('...')"` | `onsubmit="return confirmSubmit(this, '...')"` |
| `onclick="return confirm('...')"` (link) | `onclick="return confirmLink(this, '...')"` |
| `onclick="return confirm('...')"` (button) | `onclick="confirmSubmit(this.closest('form'), '...')"` + `type="button"` |

### Separazione Jinja2 e JavaScript

**Decisione Architetturale**: [ADR-018](adr/ADR-018-jinja2-js-separation.md)

Per mantenere il codice JavaScript pulito e compatibile con i formatter, **non inserire espressioni Jinja2 `{{ ... }}` direttamente nel codice JS**.

1. Centralizza dati e traduzioni in un blocco `<script type="application/json">` con un ID univoco.
2. Leggi i dati in JS tramite `JSON.parse()`.
3. In JS, usa esclusivamente l'oggetto risultante.

```html
<!-- ✅ CORRETTO: Dati centralizzati -->
<script type="application/json" id="config-data">
{ "id": {{ item.id }}, "msg": {{ _("Conferma") | tojson }} }
</script>

<script>
const config = JSON.parse(document.getElementById('config-data').textContent);
// ... logica JS pura ...
</script>
```

---

## Card Structure

### Struttura Standard

```html
<div class="card mb-4">
    <div class="card-header d-flex justify-content-between align-items-center">
        <h5 class="mb-0"><i class="fas fa-icon"></i> Titolo</h5>
        <span class="badge bg-info">Status</span>
    </div>
    <div class="card-body">
        <!-- Contenuto -->
    </div>
    <div class="card-footer text-muted">
        <small>Footer info</small>
    </div>
</div>
```

### Card con Bordo Stato

```html
<!-- Card con bordo colorato per stato -->
<div class="card border-success">...</div>
<div class="card border-warning">...</div>
<div class="card border-danger">...</div>
```

### Card Grid

```html
<div class="row">
    <div class="col-md-6 col-lg-4 mb-3">
        <div class="card h-100">...</div>
    </div>
</div>
```

---

## Layout e Spacing

### Grid System

| Breakpoint | Classe | Viewport |
|------------|--------|----------|
| Extra small | `col-*` | < 576px |
| Small | `col-sm-*` | ≥ 576px |
| Medium | `col-md-*` | ≥ 768px |
| Large | `col-lg-*` | ≥ 992px |
| Extra large | `col-xl-*` | ≥ 1200px |

### Pattern Layout Comuni

```html
<!-- Dashboard 2 colonne -->
<div class="row">
    <div class="col-md-8"><!-- Contenuto principale --></div>
    <div class="col-md-4"><!-- Sidebar --></div>
</div>

<!-- Grid cards -->
<div class="row">
    <div class="col-md-6 col-lg-4 mb-3">...</div>
</div>
```

### Pattern Profilo Utente

Layout condiviso per profilo proprio e profilo pubblico:

```html
<div class="row">
    <div class="col-md-8">
        <!-- Statistiche, partite, classifiche -->
        {% if is_own_profile or is_admin or privacy.show_statistics %}
            {% include "components/_player_statistics.html" %}
        {% endif %}
    </div>
    <div class="col-md-4">
        <!-- Info personali (solo owner) o card pubblica -->
        {% if is_own_profile %}
            {% include "components/_player_personal_info.html" %}
        {% else %}
            <!-- Card info pubblica con filtri privacy -->
        {% endif %}
    </div>
</div>
```

**Convenzioni profilo:**
- Contenuto sinistro: dati di gioco (statistiche, partite, classifiche)
- Sidebar destra: info personali + iscrizioni attive
- Titoli context-aware: "Le mie Statistiche" vs "Statistiche"
- Admin bypassa tutti i filtri privacy

### Spacing Convenzioni

| Uso | Classe | Note |
|-----|--------|------|
| Margine card | `mb-4` | Tra card verticali |
| Margine elementi | `mb-3` | Tra elementi in card |
| Padding card body | default | Card body ha padding built-in |
| Gap buttons | `me-2` | Tra bottoni inline |

---

## Typography

### Headings

| Elemento | Uso |
|----------|-----|
| `<h1>` | Titolo pagina principale (1 per pagina) |
| `<h4>`, `<h5>` | Titoli card header |
| `<h6>` | Titoli secondari, sottosezioni |

### Text Utilities

| Classe | Uso |
|--------|-----|
| `text-muted` | Testo secondario, metadata |
| `text-success` | Valori positivi, vittorie |
| `text-danger` | Valori negativi, sconfitte |
| `small` | Dettagli, note, timestamp |
| `fw-bold` | Enfasi, valori importanti |

---

## Form Conventions

### Input Standard

```html
<div class="mb-3">
    <label class="form-label">Label</label>
    <input type="text" class="form-control">
    <small class="text-muted">Help text</small>
</div>
```

### Select

```html
<select class="form-select">
    <option value="">Seleziona...</option>
</select>
```

### Validazione

```html
<!-- Valido -->
<input class="form-control is-valid">
<div class="valid-feedback">Perfetto!</div>

<!-- Non valido -->
<input class="form-control is-invalid">
<div class="invalid-feedback">Errore</div>
```

### Toggle Switch (Privacy Settings)

Per impostazioni ON/OFF usare Bootstrap form-switch:

```html
<div class="form-check form-switch mb-2">
    <input class="form-check-input" type="checkbox" id="show_email"
           name="show_email" {% if settings.show_email %}checked{% endif %}>
    <label class="form-check-label" for="show_email">
        <i class="fas fa-envelope me-1 text-muted"></i> Mostra Email
    </label>
</div>
```

**Convenzioni toggle:**
- Icona a sinistra del label (`me-1`)
- Icona in `text-muted` per non distogliere attenzione
- `mb-2` tra toggle consecutivi
- Label descrive cosa succede quando è ON (es. "Mostra Email" non "Nascondi Email")

---

## Mobile-First Design

### Principio Fondamentale

**Mobile-First** significa progettare PRIMA per schermi piccoli, poi aggiungere complessità per schermi più grandi. Non è "adattare il desktop al mobile".

```css
/* ✅ CORRETTO: Mobile-first */
.element { /* stili mobile di default */ }
@media (min-width: 768px) { /* aggiunte per tablet+ */ }

/* ❌ SBAGLIATO: Desktop-first */
.element { /* stili desktop */ }
@media (max-width: 767px) { /* fix per mobile */ }
```

---

### L'azionabile va prima ⭐

**L'interfaccia (specialmente mobile) mostra prima le cose che servono in
quel momento e sposta dopo tutto il resto.** Su mobile non c'è spazio per
"tutto in vista": l'ordine delle sezioni È la gerarchia. Cosa è azionabile
dipende dalla **fase** e dal **ruolo**:

| Vista | Fase | Azionabile (in alto) | Il resto (dopo, eventualmente collassato) |
|-------|------|----------------------|-------------------------------------------|
| admin/gara | iscrizioni | Gestione (apri/avvia) | Partite (non esistono ancora) |
| admin/gara | gioco, turno in corso | Partite (risultati da inserire), Gestione Turni | Gestione collassata, Direttori, Info/Iscritti |
| admin/gara | gioco, turno finito (Amalfi) | Gestione **aperta** (Avvia Turno N+1 / Avvia Spareggio SSR / Termina Gara) | Partite, Gestione Turni, Direttori |
| admin/gara | SSR fase A | SSR (inserire punteggi) | Classifica, Gestione collassata |
| admin/gara | SSR fase B | Classifica finale, Termina Gara | SSR riepilogo, Direttori |
| admin/match | punteggio in corso | Punteggio (aggiungi/togli rack) | Ritorno a fondo pagina |
| admin/match | punteggio definitivo (rack massimi raggiunti o match chiuso) | Ritorno (alla Gara per chi gestisce, alla Dashboard per chi gioca) | Punteggio, storico rack, info |

**Pattern implementativi:**

1. **Riordino solo visivo con flex `order-*`** quando il componente non è
   duplicabile (contiene `id=` o `<script>`): wrapper `d-flex flex-column`
   e classi `order-N order-md-M` sui figli — il DOM resta unico, mobile e
   desktop hanno ordini diversi. Vedi `gara_detail.html` (fase di gioco).
2. **Duplicazione mobile/desktop** (`d-md-none` + `d-none d-md-block`) solo
   per componenti SENZA `id`/`<script>` (la doppia inclusione duplicherebbe
   gli id e rieseguirebbe gli script).
3. **Collassato di default** ciò che resta utile ma non serve ora
   (es. Gestione in fase di gioco, Info Gara, Iscritti).
4. **Dentro una lista, l'elemento azionabile più urgente va primo**: turni
   attivi in ordine crescente (il più basso ha risultati da inserire),
   vedi `_match_cards_mobile.html`.
5. **Aperto, non solo in alto**: quando l'azione è *una sola e probabile*,
   il collapse è un tap di troppo — la sezione va renderizzata già espansa
   (`round_action_ready` in `gara_detail.html`). Il collapse resta per ciò
   che è "utile ma non ora".
6. **Le condizioni di visibilità delle copie devono essere mutuamente
   esclusive**: chi promuove una sezione in alto deve sopprimere la copia
   che sta più in basso, altrimenti su mobile compare due volte (vedi
   `round_action_ready` che esclude `is_gara_ending`, dove la Gestione è già
   in cima nella sidebar `order-1`).

**Flag lato route** (pre-calcolati in `routes/`, non `{% set %}` nel template):
`playing_admin`, `ssr_needs_input`, `ssr_ready_to_terminate`,
`round_action_ready` (`admin/competition/detail.py`), `score_is_final`
(`admin/match/detail.py`).

---

### Header e Titoli Pagina

#### ❌ DA EVITARE: Titolo e bottoni affiancati

```html
<!-- SBAGLIATO: Su mobile il titolo viene schiacciato -->
<div class="d-flex justify-content-between">
    <h1>Il mio Profilo</h1>
    <div>
        <a class="btn">Azione 1</a>
        <a class="btn">Azione 2</a>
    </div>
</div>
```

#### ✅ CORRETTO: Layout impilato su mobile, affiancato su desktop

```html
<!-- CORRETTO: Stack su mobile, flex su desktop -->
<div class="d-flex flex-column flex-md-row justify-content-md-between align-items-md-center mb-3">
    <h1 class="mb-2 mb-md-0">Il mio Profilo</h1>
    <div class="d-flex flex-wrap gap-2">
        <a class="btn btn-outline-primary btn-sm">Azione 1</a>
        <a class="btn btn-outline-secondary btn-sm">Azione 2</a>
    </div>
</div>
```

**Regole header:**
- Titolo sempre a larghezza piena su mobile
- Bottoni sotto il titolo su mobile, a destra su desktop
- Usare `flex-column flex-md-row` per lo switch
- Gap tra bottoni con `gap-2` invece di `me-2` (più flessibile)

---

### Immagini dei drill: mostrare, non riempire (ADR-044)

L'immagine di un drill **è** l'esercizio: dice dove stanno le bilie e dov'è la
battente. Riempire il riquadro ritagliandola toglie le teste del tavolo, cioè
ciò che dà senso alle posizioni — e non si vede, perché un tavolo tagliato
somiglia a un tavolo.

#### ❌ DA EVITARE: riempire ritagliando

```html
<!-- SBAGLIATO: cover taglia il 43% di una foto 1.74:1 in un riquadro quadrato -->
<span style="width:56px;height:56px;overflow:hidden;background:var(--c7-sunken)">
  <img src="..." style="width:100%;height:100%;object-fit:cover">
</span>
```

#### ✅ CORRETTO: il riquadro del tema, che mostra intero

```html
<span class="c7-diagram c7-diagram--thumb" style="width:56px;height:56px">
  <img class="c7-diagram__img" src="..." alt="">
</span>

<div class="c7-diagram c7-diagram--card">…</div>   <!-- card catalogo, 16/9 -->
<div class="c7-diagram c7-diagram--full">…</div>   <!-- dettaglio, 16/9 max 380px -->
```

**Regole immagini drill:**
- Mai `object-fit: cover` su un'immagine di drill: usa `.c7-diagram__img`
- Il riquadro è `.c7-diagram` — fondo `--c7-sunken` come passe-partout, e regge
  il segnaposto quando l'immagine manca
- Le due bande laterali su una foto quadrata sono volute: meglio una banda che
  una bilia in meno
- Non ridefinire la regola in un `style=`: era ricopiata in cinque punti, ed è
  così che quattro restano indietro quando se ne sistema uno
- ⚠️ Dentro un riquadro a `aspect-ratio`, `height: 100%` **non** basta: la
  percentuale non ha un'altezza definita su cui risolvere e una foto quadrata
  esce dal riquadro venendo ritagliata lo stesso. Per questo `.c7-diagram__img`
  si posiziona (`position: absolute; inset: 0`)
- Presidiato da `tests/new/unit/test_drill_diagram_not_cropped.py`

---

### Azioni Distruttive (Elimina, Annulla, etc.)

#### ❌ DA EVITARE: Bottone elimina prominente nell'header

```html
<!-- SBAGLIATO: Azione pericolosa troppo visibile e accessibile -->
<div class="d-flex gap-2">
    <a class="btn btn-outline-primary">Dashboard</a>
    <a class="btn btn-outline-danger">Elimina Account</a>  <!-- PERICOLOSO! -->
</div>
```

#### ✅ CORRETTO: Azioni distruttive separate e protette

```html
<!-- CORRETTO: Azioni distruttive in fondo alla pagina o in sezione dedicata -->
<div class="card border-danger mt-4">
    <div class="card-header bg-danger text-white">
        <i class="fas fa-exclamation-triangle"></i> Zona Pericolosa
    </div>
    <div class="card-body">
        <p class="text-muted">Queste azioni sono irreversibili.</p>
        <button class="btn btn-outline-danger"
                onclick="return confirmAction('Sei sicuro?', () => {...})">
            <i class="fas fa-trash"></i> Elimina Account
        </button>
    </div>
</div>
```

**Regole azioni distruttive:**
- MAI nell'header o accanto a bottoni di navigazione
- Posizionare in fondo alla pagina
- Usare card con `border-danger` per evidenziare la zona
- Sempre richiedere conferma con `confirmAction()` o `showConfirm()`
- Preferire `btn-outline-danger` a `btn-danger` (meno invitante al click)

---

### Tabelle su Mobile

#### ❌ DA EVITARE: Tabella che tronca contenuto

```html
<!-- SBAGLIATO: Colonne troncate, illeggibili -->
<table class="table">
    <tr><th>Campionato</th><th>Gara</th><th>Turno</th><th>Avversario</th><th>Risultato</th></tr>
    <!-- Su mobile "Risultato" diventa "Risul" -->
</table>
```

#### ✅ CORRETTO: Tabella desktop + Card mobile

```html
<!-- Desktop: tabella normale -->
<div class="d-none d-md-block">
    <table class="table table-striped">
        <thead>
            <tr>
                <th>Campionato</th>
                <th>Gara</th>
                <th>Turno</th>
                <th>Avversario</th>
                <th>Risultato</th>
            </tr>
        </thead>
        <tbody>
            {% for match in matches %}
            <tr>...</tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<!-- Mobile: card impilate -->
<div class="d-md-none">
    {% for match in matches %}
    <div class="card mb-2">
        <div class="card-body py-2">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <strong>{{ match.opponent }}</strong>
                    <br><small class="text-muted">{{ match.campionato }} - {{ match.gara }}</small>
                </div>
                <span class="badge bg-{{ 'success' if match.won else 'danger' }} fs-6">
                    {{ match.score }}
                </span>
            </div>
        </div>
    </div>
    {% endfor %}
</div>
```

**Regole tabelle:**
- Se più di 4 colonne: usare pattern table+card
- `d-none d-md-block` per tabella (visibile solo ≥768px)
- `d-md-none` per card (visibili solo <768px)
- Card mobile: info essenziali, layout compatto
- Badge per risultati invece di colonna dedicata

---

### Touch Target e Bottoni

#### ❌ DA EVITARE: Bottoni troppo piccoli o ravvicinati

```html
<!-- SBAGLIATO: Touch target insufficiente -->
<a class="btn btn-sm" style="padding: 2px 5px;">X</a>
<a class="btn btn-sm" style="padding: 2px 5px;">✓</a>
```

#### ✅ CORRETTO: Touch target minimo 44x44px

```html
<!-- CORRETTO: Touch target adeguato -->
<a class="btn btn-outline-danger btn-sm" style="min-height: 44px; min-width: 44px;">
    <i class="fas fa-times"></i>
</a>
```

**Regole touch target:**
- Minimo **44x44 pixel** per tutti gli elementi interattivi
- Distanza minima **8px** tra bottoni adiacenti (usare `gap-2`)
- Bottoni icon-only: aggiungere `min-width: 44px; min-height: 44px`
- Link in liste: padding verticale sufficiente (`py-3`)

---

### Statistiche e Metriche

#### ❌ DA EVITARE: Lista verticale infinita

```html
<!-- SBAGLIATO: Troppo scroll verticale -->
<div class="text-center">
    <h2>1</h2><p>Campionati</p>
    <h2>2</h2><p>Gare</p>
    <h2>4</h2><p>Vittorie</p>
    <h2>80%</h2><p>Win Rate</p>
    <!-- ...continua... -->
</div>
```

#### ✅ CORRETTO: Griglia 2x2 su mobile

```html
<!-- CORRETTO: Griglia compatta -->
<div class="row g-2 text-center">
    <div class="col-6">
        <div class="card h-100">
            <div class="card-body py-2">
                <h3 class="text-primary mb-0">1</h3>
                <small class="text-muted">Campionati</small>
            </div>
        </div>
    </div>
    <div class="col-6">
        <div class="card h-100">
            <div class="card-body py-2">
                <h3 class="text-primary mb-0">2</h3>
                <small class="text-muted">Gare</small>
            </div>
        </div>
    </div>
    <!-- altre metriche -->
</div>
```

**Regole statistiche:**
- Griglia **2 colonne su mobile** (`col-6`), 3-4 su desktop
- Card compatte con `py-2`
- Numeri grandi, label piccole (`small`)
- `h-100` per altezza uniforme

---

### Form e Input

#### ❌ DA EVITARE: Input troppo stretti

```html
<!-- SBAGLIATO: Input numerico troppo stretto -->
<input type="number" style="width: 50px;">
```

#### ✅ CORRETTO: Input con larghezza minima adeguata

```html
<!-- CORRETTO: Larghezza minima per usabilità -->
<input type="number" class="form-control form-control-sm text-center"
       style="width: 80px; min-width: 80px;">
```

**Regole form:**
- Input numerici: minimo **80px** larghezza
- Select: larghezza automatica o 100%
- Label sempre sopra l'input su mobile (non a fianco)
- Usare `form-control-lg` per input principali su mobile

---

### Navigazione e Menu

#### ❌ DA EVITARE: Troppi bottoni inline

```html
<!-- SBAGLIATO: Bottoni che wrappano male -->
<div>
    <a class="btn">Home</a>
    <a class="btn">Profilo</a>
    <a class="btn">Impostazioni</a>
    <a class="btn">Notifiche</a>
    <a class="btn">Logout</a>
</div>
```

#### ✅ CORRETTO: Max 2-3 azioni visibili, resto in menu

```html
<!-- CORRETTO: Azioni principali + menu overflow -->
<div class="d-flex gap-2">
    <a class="btn btn-primary">Azione Principale</a>
    <div class="dropdown">
        <button class="btn btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown">
            <i class="fas fa-ellipsis-v"></i>
        </button>
        <ul class="dropdown-menu dropdown-menu-end">
            <li><a class="dropdown-item">Impostazioni</a></li>
            <li><a class="dropdown-item">Notifiche</a></li>
            <li><hr class="dropdown-divider"></li>
            <li><a class="dropdown-item text-danger">Logout</a></li>
        </ul>
    </div>
</div>
```

**Regole navigazione:**
- Max **2-3 bottoni visibili** su mobile
- Usare **dropdown menu** per azioni secondarie
- Icona `fa-ellipsis-v` (tre puntini) per menu overflow
- Azioni distruttive sempre in fondo al menu con `text-danger`

---

### Checklist Mobile-First

Prima di committare qualsiasi template, verificare:

- [ ] **Header**: titolo e bottoni si impilano su mobile?
- [ ] **Tabelle**: hanno versione card per mobile?
- [ ] **Touch target**: tutti i bottoni sono almeno 44x44px?
- [ ] **Azioni distruttive**: sono separate e richiedono conferma?
- [ ] **Form**: input hanno larghezza adeguata?
- [ ] **Scroll**: la pagina non richiede scroll orizzontale?
- [ ] **Contenuto critico**: visibile senza scroll su mobile?

---

## Responsive Breakpoints

### Comportamento Standard

| Viewport | Layout | Note |
|----------|--------|------|
| Mobile (< 768px) | Single column | Card full-width, menu collapsed |
| Tablet (768-991px) | 2 columns | Grid `col-md-6` |
| Desktop (≥ 992px) | 3+ columns | Grid `col-lg-4`, sidebar visibile |

### Utility Classes

```html
<!-- Nascosto su mobile -->
<div class="d-none d-md-block">...</div>

<!-- Visibile solo su mobile -->
<div class="d-md-none">...</div>
```

### Tabelle Responsive (Mobile Card Pattern)

Le tabelle con molte colonne devono essere sostituite da card su mobile per garantire leggibilità e usabilità.

**Pattern:**
```html
{# === DESKTOP VIEW (≥768px): Table === #}
<div class="table-responsive d-none d-md-block">
    <table class="table table-striped">...</table>
</div>

{# === MOBILE VIEW (<768px): Cards === #}
<div class="d-md-none">
    {% for item in items %}
    <div class="card mb-3 border-{{ status_color }}" style="border-width: 2px;">
        <div class="card-header py-2">...</div>
        <div class="card-body py-2">...</div>
        <div class="card-footer py-2">
            <div class="d-flex gap-2">
                <a class="btn btn-primary btn-sm flex-grow-1" style="min-height: 44px;">...</a>
            </div>
        </div>
    </div>
    {% endfor %}
</div>
```

**Convenzioni card mobile:**
- Border colorato (`border-width: 2px`) in base allo stato
- Padding ridotto (`py-2`) per compattezza
- Bottoni con `min-height: 44px` per touch target adeguato
- Footer con `d-flex gap-2` per bottoni in riga

**File che usano questo pattern:**
- `_campionato_garas.html` - Lista gare del campionato
- `_match_cards_mobile.html` - Partite della gara

### Mobile Form Input Sizing

Gli input su mobile devono essere sufficientemente larghi per facilitare l'inserimento:

| Tipo Input | Larghezza Minima | Esempio |
|------------|------------------|---------|
| Numero (score/racks) | `80px` | Input SSR, punteggi |
| Select compatto | `auto` | Toggle vista classifica |
| Testo breve | `100%` | Nomi, date |

```html
<!-- Input numerico mobile-friendly -->
<input type="number" class="form-control form-control-sm text-center"
       style="width: 80px; display: inline-block;">
```

### Modal Fullscreen Mobile

I modali frequentemente usati su mobile devono avere `modal-fullscreen-sm-down` per occupare tutto lo schermo su dispositivi piccoli (`<576px`).

**Modali con fullscreen mobile:**
- Quick Result Modal (`#quickResultModal`)
- Table Assignment Modal (`#tableAssignmentModal`)
- SSR Modal (`#ssrModal`)
- Open Inscriptions Modal (`#openInscriptionsModal`)
- Modify Dates Modal (`#modifyDatesModal`)

```html
<!-- Modal con fullscreen su mobile -->
<div class="modal fade" id="myModal" tabindex="-1">
  <div class="modal-dialog modal-fullscreen-sm-down">
    ...
  </div>
</div>

<!-- Con centramento desktop -->
<div class="modal-dialog modal-dialog-centered modal-fullscreen-sm-down">
```

**Quando usare:**
- Modali con form di input
- Modali usati frequentemente durante gestione gara
- Modali con contenuto che richiede scroll su mobile

**Quando NON usare:**
- Modali già `modal-lg` o `modal-xl` (troppo contenuto)
- Modali di conferma semplice (pochi elementi)

---

## Ordine Dinamico Sezioni (Mobile)

> **Superata per chi dirige dal 12/09/2026 (ADR-059).** Il direttore non
> apre più `gara_detail.html` ma `direttore/gara.html`, dove la pagina *è*
> la fase in corso: vedi «Pagina gara del direttore» più sotto. Le regole
> che seguono raccontano come si riordinava la pagina di prima e restano
> come storia delle decisioni; lo spareggio oggi è la fase «Spareggio»
> della striscia.

### Gara Detail - Ordine Sezioni per Fase (Director View)

Su mobile, le sezioni vengono riordinate in base alla fase della gara per mostrare prima il contenuto più rilevante per l'azione corrente. Il principio guida è: **l'azione principale della fase deve essere immediatamente visibile**.

| Fase Gara | Ordine Sezioni Mobile | Rationale |
|-----------|----------------------|-----------|
| Setup/Iscrizioni | Management → Info | Director configura la gara |
| In corso (giocando) | Management → Partite → Classifica | Director gestisce i match |
| **SSR - Da inserire** | **SSR → Classifica → Management (collapsed) → Partite → Directors (bottom)** | Azione: inserire punteggi spareggio |
| **SSR - Pronto per terminare** | **Classifica → Management (Termina Gara) → Partite → SSR** | Azione: confermare termine gara |
| Gara completata | Classifica → Partite | Consultazione risultati |

### SSR Sub-Phases (Dettaglio)

La fase SSR (`gara.status == 'awaiting_ssr'`) ha due sotto-stati con layout diversi:

#### Phase A: `ssr_needs_input` (parimerito da risolvere)
```
has_unresolved_tiebreakers = True
```
**Priorità UX**: Il director deve inserire i punteggi SSR.
- SSR section **in alto** (form di input)
- Classifica sotto (mostra chi è in parimerito)
- Management **collassato** (meno importante)
- Directors section **in fondo** (non rilevante in questa fase)

#### Phase B: `ssr_ready_to_terminate` (spareggi risolti)
```
has_unresolved_tiebreakers = False
```
**Priorità UX**: Il director deve confermare il termine della gara.
- Classifica **in alto** (mostra la classifica finale)
- Management **espanso** con pulsante "Termina Gara" prominente (verde, btn-lg)
- Partite (consultazione)
- SSR section **in basso** (read-only, mostra punteggi inseriti)

### Variabili Template

```jinja2
{% set is_ssr_phase = gara.status == 'awaiting_ssr' %}
{% set ssr_needs_input = is_ssr_phase and has_unresolved_tiebreakers %}
{% set ssr_ready_to_terminate = is_ssr_phase and not has_unresolved_tiebreakers %}
{% set is_gara_ending = (gara.get_real_status() == 'campionato_completed' and not has_unresolved_tiebreakers) or (has_ssr_data and not has_unresolved_tiebreakers) %}
```

**Principio generale**: L'interfaccia si adatta alla fase mostrando prima la sezione con l'azione richiesta, minimizzando lo scroll per completare il task principale.

### Badge Classifica Mobile con SSR

Quando sono presenti punteggi SSR, i badge sono ordinati:
1. **SSR** (giallo, a sinistra) - solo per giocatori con punteggio
2. **Rack** (grigio, a destra) - sempre presente, allineato

```html
<td class="text-end">
  {% if ssr_score is not none %}
  <span class="badge bg-warning text-dark me-1">{{ ssr_score }}</span>
  {% endif %}
  <span class="badge bg-secondary">{{ rack_difference }}</span>
</td>
```

---

## Pagina gara del direttore

Implementata dal canvas approvato il 13/09/2026
(`docs/redesign-7c/canvas-gara-direttore/`, ADR-059). Le regole CSS stanno
in `static/css/theme-7c.css`, sezioni 20–28; qui la forma e il perché.

### Striscia di fase e fascia scura

| Elemento | Classe | Regola |
|---|---|---|
| Striscia | `.c7-fasi`, `.c7-fasi__tacca--fatta` / `--attiva` | Preparazione → Iscrizioni → In gioco → [Spareggio] → Chiusura. Fatta = spunta verde; attiva = pill scura con etichetta; da fare = sola icona. Sotto 992px l'etichetta ce l'ha solo l'attiva |
| Icone delle fasi | `fa-gear`, `fa-users`, `fa-play`, `fa-scale-balanced`, `fa-flag-checkered` | Una per fase; la tacca fatta mostra `fa-check` |
| Fascia | `.c7-fascia` | Dove siamo e **l'unica** cosa da fare adesso. Telefono: pila kicker, titolo, corpo, comando; desktop: testo a sinistra, comando a destra. Il comando viene da `comando_per`, lo stesso della dashboard |

Ciò che non appartiene a una fase (direttori, vetrina, tavoli, squadre,
categorie) sta in «Impostazioni gara», non in una linguetta.

### Card della partita

`direttore/_card_partita.html`, `.c7-partita`. **Una geometria sola**: nome
sopra, numero grande sotto, niente «vs». Lo stato cambia la superficie, non
la forma: in corso bianca con gli stepper (`.c7-partita__meno` /
`__piu`, 48px, salvano al tocco); da validare verde (`--da_validare`); da
giocare con il tavolo da assegnare (`__tavolo--btn`); conclusa in sola
lettura con chi ha vinto pieno (`--conclusa`); la partita di chi dirige e
gioca in cima, scura (`--mia`). Il + si spegne a `match.effective_distance`
(ADR-027). A turno concluso le partite diventano righe
(`.c7-riga-partita`) con la matita.

### Tessere dei tavoli

`.c7-tavoli` (due colonne, quattro sul desktop con `--quattro`) e
`.c7-tavolo`: libero chiaro con «libero», occupato in accento con i due
giocatori, quello della partita che si sta assegnando scuro (`--attuale`).
Si assegna **toccando la tessera libera**, non scegliendo da una tendina.

### Righe di classifica

`direttore/_classifica.html`, `.c7-classifica__riga`: posizione, freccia di
tendenza rispetto al turno prima (`__trend`, trattino se fermo; `role="img"`
con etichetta), avatar, nome e due colonne che seguono
`classification_system` (ADR-047). Medaglie con `c7-pos--1..3`. Pastiglie in
riga: «SSR» dove lo spareggio ha deciso, «pari» sul parimerito aperto
(`__pill`). Le prime sei e «tutti» con due pillole da 48px (`__pillole`,
`aria-pressed`). La stessa riga serve la classifica generale del campionato.

### Schermo in sala

`/g/<indirizzo>/sala`, `.c7-sala`: da leggere a tre metri su una TV 16:9.
Locandina 1200×630 a tutta larghezza, barra scura con nome e turno, tavoli
come caselle con nome grande e punteggio grandissimo, classifica a destra.
Sul desktop occupa esattamente lo schermo; sotto lg si impila. Nessun menu,
nessun comando.

### Podio finale

`direttore/_podio.html`, `.c7-podio-finale`: il primo al centro e più
grande, i tre nei colori delle medaglie (`--oro`, `--argento`, `--bronzo`).
**Non** `.c7-podio`, che è il podio compatto della tessera in dashboard: le
sue regole sui figli rendevano invisibili i nomi.

### Zona playoff

Nella classifica generale: barra d'accento a sinistra sulle righe dentro la
zona (`.c7-cg__riga--zona`), etichetta sopra la prima (`.c7-cg__etichetta`)
e «Fuori dai playoff» dopo l'ultima (`--fuori`). La zona la decide il
dominio (`models/playoff/zona.py`), non il template.

### Pagina del campionato

`admin/campionato_detail.html`: la stessa fascia scura della gara, poi sul
telefono tre linguette (`data-c7-view` = `classifica`, `gare`, `gestione` o
`playoff`) e sul desktop due colonne. Le gare sono righe (`.c7-cgara`) con
stato, peso (`__peso`) e comandi che vanno a capo prima di stringere il
nome; gli invitati ai playoff sono righe (`.c7-invitato`) che dicono «al suo
posto» e «invitato al posto di»; la gestione è fatta di righe che aprono le
schede.

---

## Movimento

Deciso l'11/09/2026 guardando i gesti a confronto
(`docs/redesign-7c/movimento/`): il prototipo è statico e non poteva
mostrarlo. La scala sta in `static/css/tokens-7c.css`, le regole nella skill
`ui-7c`, il presidio in `tests/new/unit/test_motion_tokens.py`.

| Token | Valore | Quando |
|---|---|---|
| `--c7-dur-base` | 250 ms | entra, si apre, cambia sotto gli occhi, cambio pagina |
| `--c7-dur-quick` | 150 ms | esce, si chiude, torna dal tocco |
| `--c7-ease` | `ease-out` | sempre |
| `--c7-press` | `.94` | scala del comando premuto; la pressione è a 0 ms |

Principi, in ordine di importanza:

1. **Il movimento è informazione.** Spiega un cambio di stato, dà riscontro
   al tocco, toglie i salti. Se non fa una di queste tre cose non si mette.
   Niente hover (l'app è touch), niente blur, niente effetti che si ripetono
   da soli salvo il pallino live.
2. **Non fa aspettare.** L'azione parte al tocco e l'animazione accompagna;
   lo schiacciamento è istantaneo, si vede il ritorno. Le uscite sono più
   veloci delle entrate. Niente sopra i 250 ms, salvo i momenti di
   celebrazione della gamification, che ha un lessico suo.
3. **Non costa.** Solo `transform` e `opacity`, che stanno sul compositore.
   L'altezza di una sezione che si apre è l'unica eccezione, un elemento
   alla volta. Mai una cascata su una lista lunga.
4. **Chi chiede meno movimento lo ottiene alla fonte**: con
   `prefers-reduced-motion: reduce` le due durate vanno a zero in
   `tokens-7c.css`. Solo i battiti (`infinite`) portano il proprio guard.
5. **Il cambio pagina è una view transition cross-document.** L'app è
   multipagina: `@view-transition { navigation: auto }` tiene la pagina
   vecchia sullo schermo finché la nuova non è pronta e poi dissolve a
   `base`; testata, barra laterale e nav mobile hanno un nome e restano
   ferme. Un nome duplicato nella stessa pagina annulla la transizione in
   silenzio; `location.reload()` non transita, si usa
   `location.replace(location.href)`. Con «riduci movimento» non parte.
6. **Una cifra che cambia sotto gli occhi salta** (`.is-pop`, keyframe
   `c7-pop`, durata `base`): la cifra nuova sale da sotto e si accende.
   Chi la riscrive in JavaScript passa da `window.c7ScorePop.segna(el,
   valore)`, che anima solo se il valore è cambiato e rigioca la seconda
   volta; chi la cambia con un ricaricamento non fa niente, `score_pop.js`
   confronta da solo con quello che c'era prima (`pagehide` →
   `sessionStorage`, stessa pagina, entro 15 s). Vale per `.c7-score__num`
   e `.c7-board__num`; una cifra nuova si aggiunge a quel selettore.

---

## Changelog Decisioni

| Data | Decisione | Motivazione |
|------|-----------|-------------|
| 2025-12-28 | `fa-shield-halved` per partite | Lo scudo diviso evoca due contendenti in un duello 1v1. Sostituisce `fa-gamepad` e `fa-table-tennis` per uniformità |
| 2025-12-28 | `fa-8-ball` per discipline | Specifico per il biliardo, rappresenta le discipline di gioco |
| 2025-12-28 | `fa-bullseye` per gare | Evoca precisione e competizione |
| 2025-12-28 | Icone privacy: `fa-lock`, `fa-eye-slash`, `fa-user-lock` | Sistema privacy profilo utente. Usato `fa-lock` invece di `fa-shield-alt` per evitare confusione con `fa-shield-halved` (partite) |
| 2025-12-28 | Form switch per toggle privacy | Bootstrap `form-switch` per impostazioni ON/OFF - feedback visivo immediato |
| 2025-12-28 | Layout profilo context-aware | Stesso template per profilo proprio e pubblico con condizionali `is_own_profile` |
| 2025-12-28 | Titoli context-aware nei componenti | "Le mie Statistiche" vs "Statistiche" in base a chi visualizza |
| 2026-01-11 | Sistema notifiche Bootstrap (Toast/Modal) | Sostituisce `alert()` nativi per UX migliore. Toast per feedback, Modal per conferme |
| 2026-01-11 | Migrazione completa `confirm()` → `showConfirm()` | 67 chiamate migrate in 36 file. Helper: `confirmSubmit()`, `confirmLink()`, `confirmAction()` |
| 2026-01-14 | Ordine dinamico sezioni mobile gara | Sezioni attive mostrate in alto: Classifica → SSR → Partite quando gara in fase finale |
| 2026-01-14 | SSR badge a sinistra di rack in classifica mobile | Per mantenere allineamento rack a destra per tutti i giocatori |
| 2026-01-22 | SSR sub-phases mobile layout | Distingue `ssr_needs_input` (SSR first, Management collapsed) da `ssr_ready_to_terminate` (Classifica first, Termina Gara prominent) |
| 2026-01-22 | Directors section at bottom during SSR | Sezione Direttori spostata in fondo (collapsible) durante fase SSR - non rilevante per azione corrente |
| 2026-01-22 | Tabelle responsive con card mobile | `_campionato_garas.html` ora usa card su mobile invece di tabella - migliora leggibilità e touch target |
| 2026-01-22 | Input SSR min-width 80px | Aumentato da 70px a 80px per facilitare inserimento su mobile |
| 2026-01-22 | Modal fullscreen mobile | Aggiunto `modal-fullscreen-sm-down` a 5 modali director: Quick Result, Table Assignment, SSR, Open Inscriptions, Modify Dates |
| 2026-01-24 | Sezione Mobile-First Design | Linee guida complete DO/DON'T per interfacce mobile-first: header layout, azioni distruttive, tabelle responsive, touch target, statistiche, form, navigazione |
| 2026-06-10 | Principio "l'azionabile va prima" (mobile) | Decisione utente da test manuale: l'interfaccia mostra prima ciò che serve in quel momento. Applicato in gara_detail.html fase gioco (Partite→Turni→Gestione collassata→Direttori via flex order-*) e turni attivi crescenti in _match_cards_mobile.html |
| 2026-06-10 | fa-8-ball per "Ai tavoli adesso" | Card "In diretta ora": era fa-table-tennis-paddle-ball (racchetta ping pong!) — allineata alla convenzione biliardo |
| 2026-08-16 | Immagini dei drill mai ritagliate (`.c7-diagram`) | L'immagine **è** l'esercizio: `object-fit: cover` toglieva fino al 43% della foto, cioè le teste del tavolo. Cinque superfici passano a `contain` su riquadro affossato, regola unica nel tema (ADR-044) |
| 2026-09-11 | Segmenti (`.c7-seg`), ricerca con chip (`.c7-search`, `.c7-chips`) e chip di posizione (`.c7-pos`) nello storico | Introdotti con lo storico delle gare (#333): i segmenti scelgono fra Gare e Campionati, i chip sono filtri persistiti nell'URL, il chip di posizione è lo stesso del podio (#332). Linguette e chip sono controlli frequenti e rispettano `--c7-touch` (48px), il minimo del design system; i 44px della sezione «Touch Target» sono il limite storico Bootstrap, il token vince |
| 2026-09-11 | La cifra del punteggio che cambia salta (`.is-pop` / `c7-pop`), sia sul tabellone sia sulla card verticale dopo il ricaricamento | Un 3 che diventa 4 senza movimento si perde, soprattutto sull'altro telefono quando arriva l'evento live: il movimento qui è informazione. Solo se il valore è cambiato davvero, così il polling che riallinea un punteggio uguale non muove niente. Scelta la colonna «250 ms» nella pagina di confronto (#342) |
| 2026-09-11 | Il cambio pagina è una view transition cross-document (`@view-transition`), con testata, barra laterale e nav mobile ferme | L'app è multipagina e il lampo bianco fra le pagine era il punto in cui sembrava un sito: la pagina vecchia resta finché la nuova è pronta, poi dissolve a `--c7-dur-base`. Scelta guardando la colonna «dissolvenza 250 ms» contro «lampo bianco» nella pagina di confronto. Spenta con «riduci movimento»; `location.reload()` non transita, si usa `location.replace(location.href)` (#341) |
| 2026-09-11 | Scala del movimento: 250 ms entra/apre, 150 ms esce/chiude/torna dal tocco, `ease-out`, tocco a `.94` istantaneo | Decisione utente guardando cinque gesti a tre durate affiancate (`docs/redesign-7c/movimento/confronto.html`). Il prototipo è statico e non poteva fissarla. Il tema aveva cinque durate diverse per lo stesso gesto e un `cubic-bezier` isolato; ora legge i token e `test_motion_tokens.py` fa rosso su una durata scritta a mano. Con «riduci movimento» le durate vanno a zero alla fonte |
| 2026-07-28 | "L'azionabile va prima" esteso a admin/match e al turno finito Amalfi | Decisione utente: a punteggio definitivo il pulsante di ritorno sale in cima su mobile (`score_is_final`); a turno Amalfi finito la Gestione sale in cima **già aperta** con Avvia Turno/SSR/Termina (`round_action_ready`). Regressioni in `tests/new/integration/test_rilievi_20260728_mobile_azionabile.py` |
| 2026-09-12 | Striscia di fase (`.c7-fasi`) e fascia scura (`.c7-fascia`) al posto delle quattro linguette nella pagina gara del direttore | Decisione 2 del canvas, direzione «C · Fasi»: in gioco il 90% delle linguette non serviva e il comando stava in fondo a Gestione. La pagina è la fase in corso, la fascia dice l'unica cosa da fare e legge il comando dalla stessa macchina a stati della dashboard (ADR-059, #343) |
| 2026-09-13 | Card della partita con una geometria sola e gli stepper − / + da 48px che salvano al tocco | Canvas 3.1–3.4: il direttore segna dalla card senza aprire il segnapunti. Nome sopra e numero sotto in ogni stato, così lo sguardo non cerca; lo stato cambia la superficie, non la forma. 48px è `--c7-touch`, rilievo della revisione automatica (#349) |
| 2026-09-13 | Tavolo assegnato toccando la tessera libera (`.c7-tavolo`), gli occupati con i due giocatori | Canvas 3.2: la tendina dei tavoli non diceva chi c'era sopra, e sul telefono erano due tocchi in più (#349) |
| 2026-09-13 | Righe di classifica con freccia di tendenza, medaglie e pillole «Prime 6 / Tutti» | Canvas 3.5–3.6: la tabella non stava in 354px e non diceva chi saliva. Le colonne seguono il sistema di classifica (ADR-047); la riga è la stessa in gara e nel campionato (#351, #358) |
| 2026-09-13 | Schermo in sala su route pubblica senza menu (`.c7-sala`) | Canvas 3.10: una pagina pensata per la TV, non la vetrina ingrandita. Dall'indirizzo della vetrina, quindi la prova risponde 404 (ADR-058). Le gare a tabellone rimandano al tabellone: issue #352 (#354) |
| 2026-09-13 | Podio finale `.c7-podio-finale`, distinto da `.c7-podio` | Canvas 5.1: il nome `.c7-podio` era già del podio compatto in dashboard, e le sue regole sui figli nascondevano i nomi. Una classe nuova invece di sovrascrivere (#355) |
| 2026-09-13 | Zona playoff come barra d'accento sulle righe, con etichetta sopra e «Fuori dai playoff» dopo | Canvas 7.1, 7.3: la zona si legge senza una colonna in più. Chi è dentro lo decide il dominio, con la stessa funzione che manda gli inviti (#358) |
| 2026-09-13 | Pagina del campionato con fascia, linguette `classifica` / `gare` / `gestione` o `playoff`, gare e invitati in righe | Canvas 7.1–7.4: la stessa grammatica della pagina gara, così il direttore non impara due pagine. Gli invitati dicono chi ha preso il posto di chi (#360) |
| 2026-09-13 | Tabellone compatto al posto della classifica nelle gare a eliminazione, posti futuri disegnati dal sorteggio, classifica finale per bande | Nel tabellone non si scala, si esce: vittorie e differenza triangoli non ordinano niente e la sezione classifica sembrava sbagliata (#240, PR #363) |
| 2026-09-13 | Sotto lg le righe delle partite impilano i due nomi | Il canvas aveva nomi utente corti; con nome e cognome veri si troncavano (PR #364) |
| 2026-09-13 | Schermo in sala dei tabelloni: turno in corso e successivo, doppio KO a due rami, niente puntini | Da tre metri un tabellone da 16 intero non si legge; una parola troncata non si legge affatto (#352, PR #365) |
| 2026-09-13 | Card a tre lati per il trio (+ sopra, − sotto) e card a set con gli stepper del set in corso | Tre colonne da 48px stanno in 390px solo impilando i due comandi; la geometria resta quella della card a due (PR #368) |
| 2026-09-13 | Occhiello del campionato sopra la striscia di fase e gruppo di righe «Dal campionato» | Il direttore di una gara di campionato non vedeva né il peso né le regole ereditate, e i testi sui punti valevano anche per una gara singola (PR #373) |
| 2026-09-13 | Griglia delle partite `repeat(auto-fill, minmax(340px, 1fr))` e lato con gli stepper come contenitore che impila sotto i 150px | Due colonne fisse a 1024 e 1280, con la colonna laterale, facevano card da 160px (PR #375) |
| 2026-09-13 | Esercizio fra i turni come sezione di righe, un foglio per registrare il tentativo | Stessa grammatica delle partite: riga con lo stato, foglio con − e + o due scelte grandi; fra un turno e l'altro sta sopra le partite, durante il turno sotto (PR #377) |
| 2026-09-13 | Squadre e categorie come righe con foglio, chip della squadra, foglio del ritiro con le conseguenze, riga distruttiva «Elimina la gara» in fondo alla preparazione | Ciò che non appartiene a una fase segue una grammatica sola, riga e foglio; il ritiro dice cosa comporta prima della conferma; l'eliminazione non è mai un pulsante rosso in vista (PR #379) |
| 2026-09-20 | Il voto di un esercizio si dà con **cinque bilie numerate** (`.c7-ballvote`, token `--c7-ball-1…5`), non con le stelle; accanto alla media, sulle card, una bilia in piccolo (`.c7-ballmark`) | Decisione dell'utente: una scala da 1 a 5 nel biliardo ha già i suoi oggetti, e le stelle sono il lessico di un negozio. I cinque colori sono **iconografia del gioco**, non semantici: non si usano per dire «ok» o «attenzione». Piatte, senza gradienti; toccare di nuovo la propria bilia toglie il voto |

---

## Come Aggiungere Nuove Convenzioni

1. Discutere la scelta con motivazione
2. Verificare che l'icona non sia già usata per altro
3. Aggiornare questa documentazione
4. Applicare la modifica in modo consistente in tutto il codebase
