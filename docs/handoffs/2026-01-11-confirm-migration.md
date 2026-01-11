# Handoff: Migrazione confirm() → Bootstrap Modal

**Data**: 2026-01-11
**Stato**: Completato
**Test**: Tutti passano, pyright 0 errors

## Sommario

Migrazione completa di tutte le chiamate `confirm()` native JavaScript a modali Bootstrap via `showConfirm()`.

| Metrica | Valore |
|---------|--------|
| Chiamate `confirm()` migrate | ~67 |
| File template modificati | 36 |
| Helper functions aggiunte | 3 (`confirmSubmit`, `confirmLink`, `confirmAction`) |

## Problema Risolto

I dialog `confirm()` nativi del browser:
- Bloccano il thread JavaScript
- Hanno UI non personalizzabile
- Sono inconsistenti tra browser
- Non seguono lo stile dell'applicazione

## Soluzione

### Funzione Principale

```javascript
// showConfirm(message, onConfirm, options)
showConfirm('Eliminare questo elemento?', () => {
    deleteItem(id);
}, {
    title: 'Conferma Eliminazione',
    confirmText: 'Elimina',
    confirmClass: 'btn-danger'
});
```

### Helper Functions per Pattern Comuni

| Helper | Pattern HTML | Uso |
|--------|--------------|-----|
| `confirmSubmit(form, msg)` | `onsubmit="return confirmSubmit(this, '...')"` | Form submission |
| `confirmLink(link, msg)` | `onclick="return confirmLink(this, '...')"` | Link navigation |
| `confirmAction(msg, fn)` | `onclick="confirmAction('...', () => doIt())"` | Callback generico |

### Pattern di Trasformazione

| Prima | Dopo |
|-------|------|
| `if (confirm(msg)) { action }` | `showConfirm(msg, () => { action })` |
| `onsubmit="return confirm('...')"` | `onsubmit="return confirmSubmit(this, '...')"` |
| `onclick="return confirm('...')"` (link) | `onclick="return confirmLink(this, '...')"` |

### Pattern Avanzato: Form con Validazione

Per form che richiedono validazione prima della conferma:

```javascript
function validateAndSubmit(form) {
    // Skip confirmation if already confirmed
    if (form.dataset.confirmed === 'true') {
        return true;
    }

    // Validation logic...
    if (!valid) {
        showError('Errore validazione');
        return false;
    }

    // Show confirmation
    showConfirm('Confermi?', () => {
        form.dataset.confirmed = 'true';
        form.submit();
    });
    return false;
}
```

## File Modificati

### Core
| File | Modifica |
|------|----------|
| `static/js/notifications.js` | Aggiunte helper: `confirmSubmit()`, `confirmLink()`, `confirmAction()` |
| `docs/UI_CONVENTIONS.md` | Documentazione helper + mapping table |

### Template Migrati (36 file)

**individual_match/**
- `create_proposal.html`, `proposals.html`, `availability.html`, `match_detail.html`

**player/**
- `delete_account.html`, `match_proposals.html`, `dashboard.html`, `my_venue_requests.html`, `notifications.html`, `challenge_detail.html`

**admin/**
- `venue_manager_requests.html`, `venues_list.html`, `users_list.html`, `venue_detail.html`, `dashboard.html`, `campionato_detail.html`

**components/**
- `_gara_inscriptions.html`, `_gara_cards.html`, `_unified_cards.html`, `_challenge_management_modal.html`, `_user_info_card.html`, `_match_admin_controls.html`

**dashboard/**
- `player.html`, `director.html`, `unified.html`, `admin.html`

**gamification/admin/**
- `quests.html`, `streak_config.html`, `xp_management.html`, `level_config.html`

**Altri**
- `base.html`, `reset.html`, `challenge/_challenge_card.html`, `gara_detail.html`, `match_detail.html`

## Note Tecniche

### Differenza Chiave: Sincrono vs Asincrono

```javascript
// PRIMA: sincrono - codice dopo if viene eseguito subito
if (confirm('OK?')) {
    doAction();
}
// Continua qui immediatamente dopo confirm()

// DOPO: asincrono - callback eseguito solo su conferma
showConfirm('OK?', () => {
    doAction();
    // Il codice che prima era dopo l'if va NEL callback
});
// ATTENZIONE: questo codice viene eseguito PRIMA della conferma!
```

### Ricordare |tojson per Stringhe Tradotte

```javascript
// ✅ CORRETTO
showConfirm({{ _("Confermi l'eliminazione?")|tojson }}, callback);

// ❌ SBAGLIATO - l'apostrofo rompe la stringa JS
showConfirm('{{ _("Confermi l'eliminazione?") }}', callback);
```

## Verifica

```bash
# Conferma nessun confirm() rimasto
grep -r "confirm(" templates/ --include="*.html" | grep -v confirmSubmit | grep -v confirmLink | grep -v confirmAction | grep -v showConfirm | grep -v data-confirmed
# Output: vuoto (solo commenti se presenti)

# Test e type check
pytest tests/new/ -n auto
pyright  # 0 errors
```

## Commit

```
refactor: migrate confirm() dialogs to Bootstrap modals

- Replace all ~67 confirm() calls across 36 template files
- Add helper functions: confirmSubmit(), confirmLink(), confirmAction()
- Use showConfirm() with async callback pattern
- Update UI_CONVENTIONS.md with migration guide
```
