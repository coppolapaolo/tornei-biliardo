/**
 * La sequenza di esercizi che si compone (templates/components/_sequence_editor.html).
 *
 * È la forma di un esame e sarà quella di una scheda di allenamento: per
 * questo il modulo **non sa cosa sia un esame**. Sa riordinare una lista,
 * togliere una voce, ritoccare un numero piccolo, pescare una voce nuova da un
 * foglio e tenere un totale. Quali numeri porti una voce lo dice il markup.
 *
 * Non parla col server: l'ordine che conta è quello del DOM, e lo spedisce il
 * modulo HTML che contiene la lista. Qui non c'è stato oltre alla pagina.
 *
 * Il contratto sono gli attributi `data-seq-*`:
 *   [data-seq-editor]            l'involucro
 *   [data-seq-list]              la lista; [data-seq-item][data-seq-key] le voci
 *   [data-seq-grip]              si trascina, o si muove con le frecce
 *   [data-seq-remove]            toglie la voce
 *   [data-seq-stepper]           meno · cifra · più (la cifra è un <input>)
 *   [data-seq-weight]            l'input (o l'elemento, col valore
 *                                nell'attributo) entra nel totale
 *   [data-seq-total]             dove si scrive il totale; il testo viene da
 *                                data-seq-total-text, con {n}
 *   <template data-seq-template> lo stampo di una voce nuova:
 *       [data-seq-fill="x"]      testo ← data-seq-x dell'opzione scelta
 *       [data-seq-from="x"]      valore dell'input ← data-seq-x dell'opzione
 *       [data-seq-slot="thumb"]  ← copia della miniatura dell'opzione
 *       [data-seq-if="tipo"]     resta solo se data-seq-kind dell'opzione è quello
 *   [data-seq-picker]            il foglio (fuori dall'involucro: si passa a
 *                                `avvia`, o lo indica data-seq-picker-id);
 *       [data-seq-option]        un esercizio; sparisce se è già in sequenza
 *       [data-seq-search]        filtra per nome
 *
 * Provato in tests/frontend/test_sequence_editor.cjs.
 */
(function (root) {
  'use strict';

  function normalizza(testo) {
    return (testo || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  }

  function avvia(editor, picker) {
    const list = editor.querySelector('[data-seq-list]');
    const empty = editor.querySelector('[data-seq-empty]');
    const live = editor.querySelector('[data-seq-live]');
    const total = editor.querySelector('[data-seq-total]');
    const stampo = editor.querySelector('template[data-seq-template]');

    function items() {
      return Array.from(list.querySelectorAll('[data-seq-item]'));
    }

    /* ── Ciò che discende dalla lista: totale, vuoto, opzioni già prese ── */
    function aggiorna() {
      const voci = items();
      if (empty) empty.hidden = voci.length > 0;

      if (total) {
        let somma = 0;
        list.querySelectorAll('[data-seq-weight]').forEach(function (nodo) {
          const grezzo = nodo.matches('input') ? nodo.value : nodo.getAttribute('data-seq-weight');
          const numero = parseInt(grezzo, 10);
          if (!isNaN(numero)) somma += numero;
        });
        total.textContent = (total.getAttribute('data-seq-total-text') || '{n}').replace('{n}', somma);
        total.hidden = voci.length === 0;
      }

      if (picker) filtra();
    }

    /* ── Riordino ────────────────────────────────────────────────────── */
    function annuncia(item) {
      if (!live) return;
      const voci = items();
      const titolo = item.querySelector('[data-seq-fill="title"]');
      live.textContent = (live.getAttribute('data-seq-live-text') || '')
        .replace('{title}', titolo ? titolo.textContent.trim() : '')
        .replace('{n}', voci.indexOf(item) + 1)
        .replace('{total}', voci.length);
    }

    /* Sposta di `delta` posizioni; torna true se si è mossa davvero. */
    function sposta(item, delta) {
      const voci = items();
      const da = voci.indexOf(item);
      const a = Math.max(0, Math.min(voci.length - 1, da + delta));
      if (a === da) return false;
      const riferimento = a > da ? voci[a].nextSibling : voci[a];
      list.insertBefore(item, riferimento);
      annuncia(item);
      return true;
    }

    /* Il trascinamento non fa volare la voce sotto il dito: la voce **cambia
       posto** quando il dito supera la metà della vicina. Niente cloni, niente
       coordinate da tenere: il DOM è sempre nell'ordine che si vede, quindi
       anche un tocco interrotto lascia una lista valida. */
    let trascinata = null;

    function alMovimento(event) {
      if (!trascinata) return;
      const y = event.clientY;
      const prima = trascinata.previousElementSibling;
      const dopo = trascinata.nextElementSibling;
      if (prima && prima.matches('[data-seq-item]')) {
        const r = prima.getBoundingClientRect();
        if (y < r.top + r.height / 2) { sposta(trascinata, -1); return; }
      }
      if (dopo && dopo.matches('[data-seq-item]')) {
        const r = dopo.getBoundingClientRect();
        if (y > r.top + r.height / 2) sposta(trascinata, 1);
      }
    }

    /* Si ascolta sul documento, non sulla lista: spostare la voce nel DOM fa
       perdere la cattura del puntatore, e da lì in poi gli eventi del dito
       arrivano a chi sta sotto — che può essere fuori dalla lista. */
    const doc = editor.ownerDocument;

    function fineTrascinamento() {
      if (!trascinata) return;
      trascinata.classList.remove('is-dragging');
      trascinata = null;
      doc.removeEventListener('pointermove', alMovimento);
      doc.removeEventListener('pointerup', fineTrascinamento);
      doc.removeEventListener('pointercancel', fineTrascinamento);
    }

    list.addEventListener('pointerdown', function (event) {
      const grip = event.target.closest('[data-seq-grip]');
      if (!grip) return;
      fineTrascinamento();
      trascinata = grip.closest('[data-seq-item]');
      trascinata.classList.add('is-dragging');
      doc.addEventListener('pointermove', alMovimento);
      doc.addEventListener('pointerup', fineTrascinamento);
      doc.addEventListener('pointercancel', fineTrascinamento);
      event.preventDefault();
    });

    list.addEventListener('keydown', function (event) {
      const grip = event.target.closest('[data-seq-grip]');
      if (!grip) return;
      const delta = event.key === 'ArrowUp' ? -1 : event.key === 'ArrowDown' ? 1 : 0;
      if (!delta) return;
      event.preventDefault();
      sposta(grip.closest('[data-seq-item]'), delta);
      grip.focus();
    });

    /* ── Togliere, ritoccare ─────────────────────────────────────────── */
    function limita(input) {
      if (input.value === '') return;
      let valore = parseInt(input.value, 10);
      if (isNaN(valore)) { input.value = input.min || ''; return; }
      if (input.min !== '' && valore < parseInt(input.min, 10)) valore = parseInt(input.min, 10);
      if (input.max !== '' && valore > parseInt(input.max, 10)) valore = parseInt(input.max, 10);
      input.value = valore;
    }

    list.addEventListener('click', function (event) {
      const togli = event.target.closest('[data-seq-remove]');
      if (togli) {
        togli.closest('[data-seq-item]').remove();
        aggiorna();
        return;
      }
      const passo = event.target.closest('[data-seq-step]');
      if (passo) {
        const input = passo.closest('[data-seq-stepper]').querySelector('input');
        const attuale = parseInt(input.value, 10);
        const base = isNaN(attuale) ? parseInt(input.min || '0', 10) : attuale;
        input.value = base + parseInt(passo.getAttribute('data-seq-step'), 10);
        limita(input);
        aggiorna();
      }
    });
    list.addEventListener('change', function (event) {
      if (event.target.closest('[data-seq-stepper]')) limita(event.target);
      aggiorna();
    });
    list.addEventListener('input', aggiorna);

    /* ── Il foglio ───────────────────────────────────────────────────── */
    function filtra() {
      const presenti = new Set(items().map(function (item) { return item.getAttribute('data-seq-key'); }));
      const cerca = picker.querySelector('[data-seq-search]');
      const ago = normalizza(cerca ? cerca.value : '');
      let visibili = 0;
      picker.querySelectorAll('[data-seq-option]').forEach(function (opzione) {
        const presa = presenti.has(opzione.getAttribute('data-seq-key'));
        const trovata = !ago || normalizza(opzione.getAttribute('data-seq-title')).indexOf(ago) !== -1;
        opzione.hidden = presa || !trovata;
        if (!opzione.hidden) visibili += 1;
      });
      const nessuno = picker.querySelector('[data-seq-noresult]');
      if (nessuno) nessuno.hidden = visibili > 0;
    }

    function aggiungi(opzione) {
      const frammento = stampo.content.cloneNode(true);
      const item = frammento.querySelector('[data-seq-item]');
      const tipo = opzione.getAttribute('data-seq-kind');

      item.setAttribute('data-seq-key', opzione.getAttribute('data-seq-key'));
      item.querySelectorAll('[data-seq-if]').forEach(function (nodo) {
        if (nodo.getAttribute('data-seq-if') !== tipo) nodo.remove();
      });
      item.querySelectorAll('[data-seq-fill]').forEach(function (nodo) {
        nodo.textContent = opzione.getAttribute('data-seq-' + nodo.getAttribute('data-seq-fill')) || '';
      });
      item.querySelectorAll('[data-seq-from]').forEach(function (input) {
        const valore = opzione.getAttribute('data-seq-' + input.getAttribute('data-seq-from'));
        if (valore !== null && valore !== '') input.value = valore;
      });
      const miniatura = opzione.querySelector('[data-seq-slot="thumb"]');
      const posto = item.querySelector('[data-seq-slot="thumb"]');
      if (miniatura && posto) {
        miniatura.childNodes.forEach(function (nodo) { posto.appendChild(nodo.cloneNode(true)); });
      }

      list.appendChild(frammento);
      aggiorna();
      return item;
    }

    if (picker) {
      picker.addEventListener('click', function (event) {
        const opzione = event.target.closest('[data-seq-option]');
        if (opzione && !opzione.hidden) aggiungi(opzione);
      });
      const cerca = picker.querySelector('[data-seq-search]');
      if (cerca) cerca.addEventListener('input', filtra);
    }

    aggiorna();
    return { sposta: sposta, aggiungi: aggiungi, aggiorna: aggiorna, items: items };
  }

  root.c7SequenceEditor = { avvia: avvia };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.c7SequenceEditor;

  /* Avvio da sé: ogni involucro trova il proprio foglio da `data-seq-picker-id`. */
  if (root.document) {
    const parti = function () {
      root.document.querySelectorAll('[data-seq-editor]').forEach(function (editor) {
        if (editor.c7Seq) return;
        const id = editor.getAttribute('data-seq-picker-id');
        editor.c7Seq = avvia(editor, id ? root.document.getElementById(id) : null);
      });
    };
    if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', parti);
    else parti();
  }
})(typeof window !== 'undefined' ? window : globalThis);
