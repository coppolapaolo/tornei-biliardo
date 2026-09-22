/**
 * Comporre una scheda di allenamento (templates/sheet/compose.html, ADR-067).
 *
 * Lavora **sopra** `sequence-editor.js`, che sa riordinare e togliere e non sa
 * cosa sia una scheda. Qui c'è ciò che è della scheda: come si segna una voce,
 * quanto farne, se destra e sinistra vanno separate, in che sezione sta e in
 * che giorno. Sono cinque campi nascosti per voce — il modulo li manda tutti,
 * sempre, anche vuoti — e un foglio solo che li scrive.
 *
 * Il foglio è **uno per pagina**, non uno per voce: dieci voci vorrebbero dire
 * dieci copie dello stesso modale con gli stessi `id`. Si apre con
 * `data-bs-toggle`, e `show.bs.modal` dice da quale voce arriva
 * (`event.relatedTarget`).
 *
 * Il peso di una voce nel totale della scheda lo scrive questo modulo, perché
 * dipende da tre cose insieme: la misura (solo «riusciti» fa totale), il
 * numero, e quante varianti si segnano separate.
 *
 * Dall'ADR-072 la misura discende dall'esercizio: la voce nuova nasce con la
 * sua (`data-seq-measure`), il foglio mostra solo quelle ammesse, e il numero
 * di tiri o di prove non ha un default — finché manca la pillola lo dice e il
 * salvataggio si ferma lì. Col punteggio si sceglie anche come contare le
 * prove.
 *
 * Provato in tests/frontend/test_sheet_compose.cjs.
 */
(function (root) {
  'use strict';

  /* Il vocabolario delle misure, nello stesso ordine di `SheetMeasure`. Qui
     servono solo le tre regole che cambiano la pagina: se il numero c'è, se fa
     totale, e come si chiama l'unità. Restano in pari col server perché il
     server è l'unico che valida — qui si decide solo cosa mostrare. */
  const MISURE = {
    done: { amount: 'optional', total: false, unit: 'shots' },
    made: { amount: 'required', total: true, unit: 'shots' },
    /* Col punteggio il numero è **quante prove**, e si sceglie come contarle
       (ADR-072). */
    score: { amount: 'required', total: false, unit: 'tries', aggregation: true },
    wins: { amount: 'required', total: false, unit: 'games' },
    minutes: { amount: 'required', total: false, unit: 'minutes' }
  };

  function avvia(form, dialog) {
    const testi = dialog ? dialog.dataset : {};
    let corrente = null;

    function campi(item) {
      return {
        measure: item.querySelector('[data-sheet-measure]'),
        amount: item.querySelector('[data-sheet-amount]'),
        aggregation: item.querySelector('[data-sheet-aggregation]'),
        allowed: item.querySelector('[data-sheet-allowed]'),
        variant: item.querySelector('[data-sheet-variant]'),
        section: item.querySelector('[data-sheet-section]'),
        day: item.querySelector('[data-sheet-day]'),
        variants: item.querySelector('[data-sheet-variants]'),
        peso: item.querySelector('[data-sheet-weight]'),
        dose: item.querySelector('[data-sheet-dose]'),
        titolo: item.querySelector('[data-seq-slot="section"]')
      };
    }

    function regola(valore) {
      return MISURE[valore] || MISURE.made;
    }

    function etichettaMisura(valore) {
      const pillola = dialog && dialog.querySelector('[data-sheet-pick="' + valore + '"]');
      return pillola ? pillola.textContent.trim() : valore;
    }

    /* L'unità arriva tradotta dal template, per sé: ricavarla dall'etichetta
       («Quanti tiri» → «tiri») funziona in italiano e si rompe in ogni lingua
       in cui il nome non è l'ultima parola. */
    function unita(valore) {
      const nome = regola(valore).unit;
      if (nome === 'games') return testi.sheetUnitGames || '';
      if (nome === 'minutes') return testi.sheetUnitMinutes || '';
      if (nome === 'tries') return testi.sheetUnitTries || '';
      return testi.sheetUnitShots || '';
    }

    function etichettaAggregazione(valore) {
      const pillola = dialog ? dialog.querySelector('[data-sheet-agg="' + (valore || 'mean') + '"]') : null;
      return pillola ? pillola.textContent.trim() : (valore || '');
    }

    /* Le misure ammesse su questa voce: la sua per prima. Vuoto = tutte, per
       le pagine che non lo dicono. */
    function ammesse(c) {
      const grezzo = c.allowed ? (c.allowed.value || '') : '';
      return grezzo ? grezzo.split(',') : [];
    }

    /* Una voce senza il suo numero: la scheda non si salva finché non c'è. */
    function manca(item) {
      const c = campi(item);
      if (!c.measure) return false;
      const r = regola(c.measure.value);
      return r.amount === 'required' && isNaN(parseInt(c.amount ? c.amount.value : '', 10));
    }

    /* ── Ciò che discende dai campi di una voce ───────────────────────── */
    function aggiornaVoce(item) {
      const c = campi(item);
      if (!c.measure) return;
      const misura = c.measure.value;
      const r = regola(misura);
      const varianti = parseInt(c.variants ? c.variants.value : '0', 10) || 0;
      const separate = c.variant && c.variant.value === '1' && varianti > 1;
      const numero = parseInt(c.amount ? c.amount.value : '', 10);

      if (c.dose) {
        const parti = [];
        const nome = etichettaMisura(misura).toLowerCase();
        const senzaNumero = manca(item);
        if (senzaNumero) {
          parti.push(testi.sheetMsgMissing || '?');
        } else if (r.amount !== 'none' && !isNaN(numero)) {
          parti.push(numero + ' ' + unita(misura));
          if (separate) parti.push('×' + varianti);
        }
        /* «5 minuti · minuti» no: dove l'unità e la misura sono la stessa
           parola, dirla due volte è rumore. */
        if (parti.length === 0 || unita(misura).toLowerCase() !== nome) parti.push(nome);
        if (r.aggregation && c.aggregation && !senzaNumero) {
          parti.push(etichettaAggregazione(c.aggregation.value).toLowerCase());
        }
        c.dose.textContent = parti.join(' · ');
        const apri = c.dose.closest('[data-sheet-open]');
        if (apri) apri.classList.toggle('is-missing', senzaNumero);
      }
      if (c.peso) {
        const peso = r.total && !isNaN(numero) ? numero * (separate ? varianti : 1) : 0;
        c.peso.setAttribute('data-seq-weight', String(peso));
      }
      if (c.titolo) c.titolo.textContent = '';
    }

    /* Il titoletto compare sulla **prima** voce che apre una sezione: sta
       dentro la voce, non fra una voce e l'altra, perché una riga estranea
       nella lista spezzerebbe il trascinamento. */
    function aggiornaSezioni() {
      let precedente = null;
      form.querySelectorAll('[data-seq-item]').forEach(function (item) {
        const c = campi(item);
        const sezione = c.section ? (c.section.value || '').trim() : '';
        if (c.titolo) c.titolo.textContent = sezione && sezione !== precedente ? sezione : '';
        precedente = sezione;
      });
    }

    function aggiornaTutto() {
      form.querySelectorAll('[data-seq-item]').forEach(aggiornaVoce);
      aggiornaSezioni();
      if (form.c7Seq) form.c7Seq.aggiorna();
    }

    /* ── Il foglio ────────────────────────────────────────────────────── */
    function mostraFoglio() {
      if (!corrente || !dialog) return;
      const c = campi(corrente);
      const misura = c.measure.value;
      const r = regola(misura);
      const varianti = parseInt(c.variants ? c.variants.value : '0', 10) || 0;

      /* `is-active`, che è come il tema accende una pillola: `is-on` esiste ma
         è dei chip, e la classe sbagliata non dà errore — lascia solo la
         scelta senza riscontro. */
      const consentite = ammesse(c);
      dialog.querySelectorAll('[data-sheet-pick]').forEach(function (pillola) {
        const valore = pillola.getAttribute('data-sheet-pick');
        pillola.classList.toggle('is-active', valore === misura);
        /* «Riusciti» su un esercizio a punteggio non esiste (ADR-072): la
           pillola sparisce invece di farsi scegliere e poi rifiutare. */
        pillola.hidden = consentite.length > 0 && consentite.indexOf(valore) === -1;
      });

      const riga = dialog.querySelector('[data-sheet-amount-row]');
      if (riga) riga.hidden = r.amount === 'none';
      const etichetta = dialog.querySelector('[data-sheet-amount-label]');
      if (etichetta) {
        etichetta.textContent = r.unit === 'games' ? (testi.sheetMsgGames || '')
          : r.unit === 'minutes' ? (testi.sheetMsgMinutes || '')
          : r.unit === 'tries' ? (testi.sheetMsgTries || '') : (testi.sheetMsgShots || '');
      }
      const numero = dialog.querySelector('[data-sheet-dialog-amount]');
      if (numero) numero.value = c.amount.value;

      const rigaAgg = dialog.querySelector('[data-sheet-aggregation-row]');
      if (rigaAgg) rigaAgg.hidden = !r.aggregation;
      const scelta = (c.aggregation && c.aggregation.value) || 'mean';
      dialog.querySelectorAll('[data-sheet-agg]').forEach(function (pillola) {
        pillola.classList.toggle('is-active', pillola.getAttribute('data-sheet-agg') === scelta);
      });

      const varRow = dialog.querySelector('[data-sheet-variant-row]');
      if (varRow) varRow.hidden = varianti < 2;
      const varInput = dialog.querySelector('[data-sheet-dialog-variant]');
      if (varInput) varInput.checked = c.variant.value === '1';

      const sezione = dialog.querySelector('[data-sheet-dialog-section]');
      if (sezione) sezione.value = c.section.value;
      const giorno = dialog.querySelector('[data-sheet-dialog-day]');
      if (giorno) giorno.value = c.day.value;
      const rigaGiorno = dialog.querySelector('[data-sheet-day-row]');
      if (rigaGiorno) rigaGiorno.hidden = !giorniAccesi();

      const titolo = dialog.querySelector('[data-sheet-dialog-title]');
      const nome = corrente.querySelector('[data-seq-fill="title"]');
      if (titolo && nome) titolo.textContent = nome.textContent.trim();

      const nota = dialog.querySelector('[data-sheet-note]');
      if (nota) nota.textContent = r.total ? (testi.sheetMsgThreshold || '') : (testi.sheetMsgOut || '');
    }

    function scrivi(campo, valore) {
      if (!corrente) return;
      const c = campi(corrente);
      if (c[campo]) c[campo].value = valore;
      aggiornaVoce(corrente);
      aggiornaSezioni();
      if (form.c7Seq) form.c7Seq.aggiorna();
    }

    function giorniAccesi() {
      const interruttore = form.querySelector('[data-sheet-toggle="uses_days"]');
      return !!(interruttore && interruttore.checked);
    }

    /* ── Gli interruttori della scheda ────────────────────────────────── */
    function aggiornaOpzioni() {
      form.querySelectorAll('[data-sheet-when]').forEach(function (riga) {
        const nome = riga.getAttribute('data-sheet-when');
        const interruttore = form.querySelector('[data-sheet-toggle="' + nome + '"]');
        riga.hidden = !(interruttore && interruttore.checked);
      });
    }

    form.addEventListener('change', function (event) {
      if (event.target.matches('[data-sheet-toggle]')) aggiornaOpzioni();
    });

    if (dialog) {
      dialog.addEventListener('show.bs.modal', function (event) {
        const apri = event.relatedTarget && event.relatedTarget.closest('[data-sheet-open]');
        corrente = apri ? apri.closest('[data-seq-item]') : null;
        mostraFoglio();
      });

      dialog.addEventListener('click', function (event) {
        const pillola = event.target.closest('[data-sheet-pick]');
        if (pillola) {
          scrivi('measure', pillola.getAttribute('data-sheet-pick'));
          mostraFoglio();
          return;
        }
        const conto = event.target.closest('[data-sheet-agg]');
        if (conto) {
          scrivi('aggregation', conto.getAttribute('data-sheet-agg'));
          mostraFoglio();
          return;
        }
        const passo = event.target.closest('[data-sheet-step]');
        if (passo) {
          const numero = dialog.querySelector('[data-sheet-dialog-amount]');
          const attuale = parseInt(numero.value, 10);
          const base = isNaN(attuale) ? 1 : attuale;
          const max = parseInt(numero.max, 10) || 999;
          numero.value = Math.max(1, Math.min(max, base + parseInt(passo.getAttribute('data-sheet-step'), 10)));
          scrivi('amount', numero.value);
        }
      });

      dialog.addEventListener('input', function (event) {
        if (event.target.matches('[data-sheet-dialog-amount]')) scrivi('amount', event.target.value);
        if (event.target.matches('[data-sheet-dialog-section]')) scrivi('section', event.target.value);
        if (event.target.matches('[data-sheet-dialog-day]')) scrivi('day', event.target.value);
      });

      dialog.addEventListener('change', function (event) {
        if (event.target.matches('[data-sheet-dialog-variant]')) {
          scrivi('variant', event.target.checked ? '1' : '0');
        }
      });
    }

    /* Una voce appena pescata dal foglio degli esercizi nasce già leggibile, e
       una tolta non lascia un titoletto orfano: il componente sequenza fa la
       sua parte e questo modulo ridisegna la propria subito dopo. */
    form.addEventListener('click', function (event) {
      if (event.target.closest('[data-seq-remove]')) root.setTimeout(aggiornaTutto, 0);
    });

    /* Il salvataggio si ferma sulla prima voce senza il suo numero, e le apre
       il foglio: il server la rifiuterebbe comunque, ma qui si vede quale. */
    form.addEventListener('submit', function (event) {
      const senza = Array.prototype.find.call(form.querySelectorAll('[data-seq-item]'), manca);
      if (!senza) return;
      event.preventDefault();
      const apri = senza.querySelector('[data-sheet-open]');
      if (apri) apri.click();
    });
    const idPicker = form.getAttribute('data-seq-picker-id');
    const picker = idPicker ? form.ownerDocument.getElementById(idPicker) : null;
    if (picker) {
      picker.addEventListener('click', function (event) {
        if (event.target.closest('[data-seq-option]')) root.setTimeout(aggiornaTutto, 0);
      });
    }

    aggiornaOpzioni();
    aggiornaTutto();
    return { aggiornaTutto: aggiornaTutto, aggiornaSezioni: aggiornaSezioni };
  }

  root.c7SheetCompose = { avvia: avvia };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.c7SheetCompose;

  if (root.document) {
    const parti = function () {
      root.document.querySelectorAll('[data-sheet-compose]').forEach(function (form) {
        if (form.c7Sheet) return;
        form.c7Sheet = avvia(form, root.document.querySelector('[data-sheet-dialog]'));
      });
    };
    if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', parti);
    else parti();
  }
})(typeof window !== 'undefined' ? window : globalThis);
