/**
 * Sistema di notifiche Bootstrap
 * Sostituisce alert() con Toast, Modal e validazione inline
 */

// === TOAST ===

/**
 * Mostra un toast Bootstrap
 * @param {string} message - Messaggio da mostrare
 * @param {string} type - Tipo Bootstrap: 'success', 'danger', 'warning', 'info'
 * @param {boolean} autohide - Se true, scompare dopo 3 secondi
 */
function showToast(message, type = 'success', autohide = true) {
  const container = document.getElementById('toast-container');
  if (!container) {
    console.error('Toast container not found! Add #toast-container to base.html');
    return;
  }

  // Bootstrap 5.1.x compatibility: use bg-* + text-* instead of text-bg-*
  // Determine text color and close button style based on background
  const darkBgTypes = ['success', 'danger', 'primary', 'dark'];
  const isDarkBg = darkBgTypes.includes(type);
  const textClass = isDarkBg ? 'text-white' : 'text-dark';
  const closeBtnClass = isDarkBg ? 'btn-close-white' : '';

  const toast = document.createElement('div');
  toast.className = `toast align-items-center bg-${type} ${textClass} border-0`;
  toast.setAttribute('role', 'alert');

  const wrapper = document.createElement('div');
  wrapper.className = 'd-flex';

  const body = document.createElement('div');
  body.className = 'toast-body';
  body.textContent = message;

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = `btn-close ${closeBtnClass} me-2 m-auto`.trim();
  closeBtn.setAttribute('data-bs-dismiss', 'toast');

  wrapper.appendChild(body);
  wrapper.appendChild(closeBtn);
  toast.appendChild(wrapper);
  container.appendChild(toast);

  const bsToast = new bootstrap.Toast(toast, { autohide, delay: 3000 });
  bsToast.show();
  toast.addEventListener('hidden.bs.toast', () => toast.remove());
}

/**
 * Mostra un messaggio di successo (toast verde, auto-hide)
 * @param {string} message - Messaggio da mostrare
 */
function showSuccess(message) {
  showToast(message, 'success', true);
}

/**
 * Chiude tutti i toast di errore esistenti
 */
function clearErrorToasts() {
  const container = document.getElementById('toast-container');
  if (!container) return;

  container.querySelectorAll('.text-bg-danger').forEach(toast => {
    const bsToast = bootstrap.Toast.getInstance(toast);
    if (bsToast) {
      bsToast.hide();
    } else {
      toast.remove();
    }
  });
}

/**
 * Mostra un messaggio di errore (toast rosso, persistente)
 * Rimuove automaticamente gli errori precedenti
 * @param {string} message - Messaggio da mostrare
 */
function showError(message) {
  clearErrorToasts();  // Rimuovi errori precedenti
  showToast(message, 'danger', false);
}

/**
 * Mostra un messaggio di warning (toast giallo, auto-hide)
 * @param {string} message - Messaggio da mostrare
 */
function showWarning(message) {
  showToast(message, 'warning', true);
}

/**
 * Mostra un messaggio informativo (toast blu, auto-hide)
 * @param {string} message - Messaggio da mostrare
 */
function showInfo(message) {
  showToast(message, 'info', true);
}

// === MODAL CONFERMA ===

/**
 * Mostra un modal di conferma
 * @param {string} message - Messaggio da mostrare
 * @param {function} onConfirm - Callback da eseguire se l'utente conferma
 * @param {object} options - Opzioni aggiuntive
 * @param {string} options.title - Titolo del modal (default: "Conferma")
 * @param {string} options.confirmText - Testo bottone conferma (default: "Conferma")
 * @param {string} options.confirmClass - Classe bottone conferma (default: "btn-danger")
 */
// Store current callback globally so we can access it from the click handler
let _confirmCallback = null;

function showConfirm(message, onConfirm, options = {}) {
  console.log('showConfirm called with message:', message);
  const {
    title = 'Conferma',
    confirmText = 'Conferma',
    confirmClass = 'btn-danger'
  } = options;

  const modalEl = document.getElementById('confirmModal');
  console.log('confirmModal element found:', !!modalEl);
  if (!modalEl) {
    console.error('Confirm modal not found! Add #confirmModal to base.html');
    // Fallback a confirm() nativo
    if (confirm(message)) {
      onConfirm();
    }
    return;
  }

  const modalTitle = modalEl.querySelector('.modal-title');
  const modalBody = document.getElementById('confirmModalBody');
  const confirmBtn = document.getElementById('confirmModalBtn');

  console.log('confirmBtn found:', !!confirmBtn, confirmBtn);

  if (modalTitle) modalTitle.textContent = title;
  modalBody.textContent = message;
  confirmBtn.textContent = confirmText;
  confirmBtn.className = `btn ${confirmClass}`;

  // Store callback for the click handler
  _confirmCallback = onConfirm;

  const modal = new bootstrap.Modal(modalEl);

  // Use onclick instead of addEventListener to ensure only one handler
  confirmBtn.onclick = function() {
    console.log('Confirm button clicked!');
    modal.hide();
    if (_confirmCallback) {
      console.log('Calling callback...');
      _confirmCallback();
      _confirmCallback = null;
    }
  };
  console.log('Click handler set via onclick');

  console.log('Showing modal...');
  modal.show();
  console.log('Modal show() called');
}

// === VALIDAZIONE INLINE ===

/**
 * Mostra un errore di validazione sotto un campo form
 * @param {HTMLElement} element - L'elemento input/select
 * @param {string} message - Messaggio di errore
 */
function showValidationError(element, message) {
  clearValidationError(element);
  element.classList.add('is-invalid');

  const feedback = document.createElement('div');
  feedback.className = 'invalid-feedback';
  feedback.textContent = message;

  // Inserisci dopo l'elemento (o dopo il parent se input-group)
  const parent = element.closest('.input-group') || element;
  parent.parentNode.insertBefore(feedback, parent.nextSibling);
}

/**
 * Rimuove l'errore di validazione da un campo
 * @param {HTMLElement} element - L'elemento input/select
 */
function clearValidationError(element) {
  element.classList.remove('is-invalid');
  const parent = element.closest('.input-group') || element;
  const feedback = parent.parentNode.querySelector('.invalid-feedback');
  if (feedback) feedback.remove();
}

/**
 * Pulisce tutti gli errori di validazione in un form
 * @param {HTMLFormElement|string} form - Il form o il suo selettore
 */
function clearAllValidationErrors(form) {
  const formEl = typeof form === 'string' ? document.querySelector(form) : form;
  if (!formEl) return;

  formEl.querySelectorAll('.is-invalid').forEach(el => {
    el.classList.remove('is-invalid');
  });
  formEl.querySelectorAll('.invalid-feedback').forEach(el => {
    el.remove();
  });
}

// === CONFIRM HELPERS (per sostituire confirm() inline) ===

/**
 * Conferma prima di submit form. Uso: onsubmit="return confirmSubmit(this, 'Messaggio')"
 * @param {HTMLFormElement} form - Il form da sottomettere
 * @param {string} message - Messaggio di conferma
 * @param {object} options - Opzioni per showConfirm
 * @returns {boolean} - Sempre false (il form viene submittato dal callback)
 */
function confirmSubmit(form, message, options = {}) {
  showConfirm(message, () => {
    // Crea e dispatcha un evento submit "trusted" per bypassare la conferma
    form.setAttribute('data-confirmed', 'true');
    form.submit();
  }, options);
  return false;
}

/**
 * Conferma prima di seguire un link. Uso: onclick="return confirmLink(this, 'Messaggio')"
 * @param {HTMLAnchorElement} link - Il link da seguire
 * @param {string} message - Messaggio di conferma
 * @param {object} options - Opzioni per showConfirm
 * @returns {boolean} - Sempre false (la navigazione avviene dal callback)
 */
function confirmLink(link, message, options = {}) {
  showConfirm(message, () => {
    window.location.href = link.href;
  }, options);
  return false;
}

/**
 * Conferma prima di eseguire un'azione. Uso: onclick="confirmAction('Messaggio', () => doSomething())"
 * @param {string} message - Messaggio di conferma
 * @param {function} action - Azione da eseguire se confermato
 * @param {object} options - Opzioni per showConfirm
 */
function confirmAction(message, action, options = {}) {
  showConfirm(message, action, options);
}
