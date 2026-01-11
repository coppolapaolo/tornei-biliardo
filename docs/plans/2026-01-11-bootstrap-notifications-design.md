# Design: Sostituzione alert() con componenti Bootstrap

**Data**: 2026-01-11
**Stato**: Approvato

## Obiettivo

Sostituire le chiamate JavaScript `alert()` con componenti Bootstrap per una UX migliore.

## Mappatura tipi messaggio → componenti

| Tipo messaggio | Componente | Comportamento |
|----------------|------------|---------------|
| **Successo** | Toast verde | Auto-hide 3s |
| **Errore operazione** | Toast rosso | Click to dismiss |
| **Validazione form** | Alert inline | Sotto il campo, stile Bootstrap |
| **Azione critica** | Modal conferma | Due bottoni (Annulla/Conferma) |

## Implementazione

### 1. Toast container (`base.html`)

```html
<div id="toast-container" class="toast-container position-fixed top-0 end-0 p-3">
</div>
```

### 2. Modal di conferma (`base.html`)

```html
<div class="modal fade" id="confirmModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Conferma</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body" id="confirmModalBody"></div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Annulla</button>
        <button type="button" class="btn btn-danger" id="confirmModalBtn">Conferma</button>
      </div>
    </div>
  </div>
</div>
```

### 3. Utility JavaScript (`static/js/notifications.js`)

```javascript
/**
 * Sistema di notifiche Bootstrap
 * Sostituisce alert() con Toast, Modal e validazione inline
 */

// === TOAST ===

function showToast(message, type = 'success', autohide = true) {
  const container = document.getElementById('toast-container');

  const toast = document.createElement('div');
  toast.className = `toast align-items-center text-bg-${type} border-0`;
  toast.setAttribute('role', 'alert');

  const wrapper = document.createElement('div');
  wrapper.className = 'd-flex';

  const body = document.createElement('div');
  body.className = 'toast-body';
  body.textContent = message;  // textContent per sicurezza XSS

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'btn-close btn-close-white me-2 m-auto';
  closeBtn.setAttribute('data-bs-dismiss', 'toast');

  wrapper.appendChild(body);
  wrapper.appendChild(closeBtn);
  toast.appendChild(wrapper);
  container.appendChild(toast);

  const bsToast = new bootstrap.Toast(toast, { autohide, delay: 3000 });
  bsToast.show();
  toast.addEventListener('hidden.bs.toast', () => toast.remove());
}

function showSuccess(message) {
  showToast(message, 'success', true);
}

function showError(message) {
  showToast(message, 'danger', false);
}

// === MODAL CONFERMA ===

function showConfirm(message, onConfirm) {
  const modalBody = document.getElementById('confirmModalBody');
  const confirmBtn = document.getElementById('confirmModalBtn');

  modalBody.textContent = message;

  const modal = new bootstrap.Modal(document.getElementById('confirmModal'));

  // Rimuovi handler precedenti clonando il bottone
  const newBtn = confirmBtn.cloneNode(true);
  confirmBtn.parentNode.replaceChild(newBtn, confirmBtn);

  newBtn.addEventListener('click', () => {
    modal.hide();
    onConfirm();
  });

  modal.show();
}

// === VALIDAZIONE INLINE ===

function showValidationError(element, message) {
  clearValidationError(element);
  element.classList.add('is-invalid');

  const feedback = document.createElement('div');
  feedback.className = 'invalid-feedback';
  feedback.textContent = message;
  element.parentNode.appendChild(feedback);
}

function clearValidationError(element) {
  element.classList.remove('is-invalid');
  const existing = element.parentNode.querySelector('.invalid-feedback');
  if (existing) existing.remove();
}
```

## Piano di migrazione

| Priorità | File | Alert stimati |
|----------|------|---------------|
| 1 | `gara_detail.html` | ~30 |
| 2 | `match_detail.html` | ~20 |
| 3 | `components/_match_admin_controls.html` | ~6 |
| 4 | `individual_match/match_detail.html` | ~10 |
| 5 | Altri (challenge, dashboard, etc.) | ~15 |

## Pattern di sostituzione

```javascript
// Errore
alert("Errore: " + msg);        → showError(msg);

// Successo
alert("Completato!");           → showSuccess("Completato!");

// Conferma
if (confirm("Eliminare?")) {    → showConfirm("Eliminare?", () => {
  doDelete();                       doDelete();
}                                });

// Validazione
alert("Campo obbligatorio");    → showValidationError(input, "Campo obbligatorio");
```
