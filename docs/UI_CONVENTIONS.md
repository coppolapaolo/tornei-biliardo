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
10. [Responsive](#responsive-breakpoints)
11. [Changelog Decisioni](#changelog-decisioni)

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

---

## Come Aggiungere Nuove Convenzioni

1. Discutere la scelta con motivazione
2. Verificare che l'icona non sia già usata per altro
3. Aggiornare questa documentazione
4. Applicare la modifica in modo consistente in tutto il codebase
