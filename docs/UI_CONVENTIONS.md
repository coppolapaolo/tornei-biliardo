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
12. [Changelog Decisioni](#changelog-decisioni)

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

---

## Come Aggiungere Nuove Convenzioni

1. Discutere la scelta con motivazione
2. Verificare che l'icona non sia già usata per altro
3. Aggiornare questa documentazione
4. Applicare la modifica in modo consistente in tutto il codebase
