/* «Parti da un preset» e «Salva come preset» (ADR-082).
 *
 * Applicare un preset vuol dire **scrivere nei campi** del modulo, come farebbe
 * il direttore: niente si salva finché non preme il pulsante del modulo, e lì
 * valgono le validazioni di sempre. I valori arrivano dal server già tradotti
 * nei nomi dei campi HTML (`payload.valori_per_il_modulo`).
 *
 * Le sezioni che dipendono da altri campi (gironi, fase finale, tabellone,
 * punti, catene) si aprono da sole: ogni campo scritto riceve gli eventi
 * `input` e `change`, gli stessi che ascoltano `strategia_gara.js`,
 * `campo_gironi.js`, `bracket_options.js`, `campo_punti.js` e l'editor delle
 * catene. I valori si scrivono **due volte**: la prima apre le sezioni, la
 * seconda riempie i campi che la prima ha appena acceso (la strategia viene
 * dopo la distanza nel modulo, i gironi dopo la strategia…).
 *
 * Lo stesso script serve i moduli della gara e quelli del campionato (wizard
 * e modifica): cambiano solo i campi che il server manda.
 *
 * I campi che il direttore ha già toccato a mano non si sovrascrivono senza
 * chiedere: si applica il resto, poi il foglio di conferma (ADR-074) chiede se
 * usare anche lì i valori del preset.
 *
 * I playoff di un preset di campionato si scrivono dove il modulo li chiede,
 * cioè al passo 1 del wizard (Elite e Academy). Nella modifica del campionato
 * non ci sono: la pagina dice che il preset li comprende e che si cambiano
 * dalla pagina del campionato (`nota_playoff_altrove`).
 */
(function () {
  'use strict';

  function testi(radice) {
    try { return JSON.parse(radice.getAttribute('data-testi') || '{}'); } catch (e) { return {}; }
  }

  function scatta(campo) {
    campo.dispatchEvent(new Event('input', { bubbles: true }));
    campo.dispatchEvent(new Event('change', { bubbles: true }));
  }

  /* I campi del modulo con quel nome che il preset può scrivere: non i
   * nascosti imposti dal server, tranne il valore delle catene. */
  function campi(form, nome) {
    return Array.prototype.filter.call(form.elements, function (el) {
      if (el.name !== nome) return false;
      return el.type !== 'hidden' || el.hasAttribute('data-catena-valore');
    });
  }

  function testo(valore) {
    return valore === null || valore === undefined ? '' : String(valore);
  }

  function acceso(casella, valore) {
    return typeof valore === 'boolean' ? valore : testo(valore) === casella.value;
  }

  /* Il valore che il campo mostra adesso, nella forma del preset. */
  function attuale(form, nome) {
    var lista = campi(form, nome);
    if (!lista.length) return null;
    var radio = lista.filter(function (el) { return el.type === 'radio'; });
    if (radio.length) {
      var scelto = radio.filter(function (el) { return el.checked; })[0];
      return scelto ? scelto.value : '';
    }
    if (lista[0].type === 'checkbox') return lista[0].checked;
    return lista[0].value;
  }

  function cambierebbe(form, nome, valore) {
    var lista = campi(form, nome);
    if (!lista.length) return false;
    if (lista[0].type === 'checkbox') return lista[0].checked !== acceso(lista[0], valore);
    return testo(attuale(form, nome)) !== testo(valore);
  }

  /* Scrive un valore: 'ok', 'assente' (il modulo non ha quel campo) o
   * 'rifiutato' (il campo c'è ma non ha più quella scelta). */
  function scrivi(form, nome, valore) {
    var lista = campi(form, nome);
    if (!lista.length) return 'assente';
    var radio = lista.filter(function (el) { return el.type === 'radio'; });
    if (radio.length) {
      var giusto = radio.filter(function (el) { return el.value === testo(valore); })[0];
      if (!giusto) return testo(valore) === '' ? 'ok' : 'rifiutato';
      if (!giusto.checked) { giusto.checked = true; scatta(giusto); }
      return 'ok';
    }
    var esito = 'ok';
    lista.forEach(function (el) {
      if (el.type === 'checkbox') {
        var si = acceso(el, valore);
        if (el.checked !== si) { el.checked = si; scatta(el); }
      } else if (el.tagName === 'SELECT') {
        var voluto = testo(valore);
        var c = Array.prototype.some.call(el.options, function (o) { return o.value === voluto; });
        // «Eredita» vuoto, dove il menu non lo offre, vuol dire «lascia com'è».
        if (!c) { if (voluto !== '') esito = 'rifiutato'; return; }
        if (el.value !== voluto) { el.value = voluto; scatta(el); }
      } else if (el.value !== testo(valore)) {
        el.value = testo(valore);
        scatta(el);
      }
    });
    return esito;
  }

  /* Il nome con cui il modulo mostra un campo: la sua etichetta. */
  function etichetta(form, nome) {
    var el = campi(form, nome)[0];
    if (!el) return nome;
    var label = el.id ? form.querySelector('label[for="' + el.id + '"]') : null;
    if (!label) {
      var gruppo = el.closest('[data-fase-regola], .mb-3, .mb-4, .col-sm-6, [role="radiogroup"]');
      if (gruppo && gruppo.getAttribute('role') === 'radiogroup') gruppo = gruppo.parentNode;
      label = gruppo ? gruppo.querySelector('label, .form-label') : null;
    }
    var parole = label ? label.textContent.replace(/\s+/g, ' ').trim() : '';
    return parole || nome;
  }

  function applicaListino(form, voci) {
    var editor = form.querySelector('[data-listino]');
    if (!editor) return false;
    var righe = editor.querySelector('[data-listino-righe]');
    var modello = editor.querySelector('template[data-listino-modello]');
    var ids = {};
    righe.querySelectorAll('[data-listino-riga]').forEach(function (riga) {
      var nome = riga.querySelector('input[name="listino_nome"]').value.trim().toLowerCase();
      var id = riga.querySelector('input[name="listino_id"]').value;
      if (nome && id) ids[nome] = id;
    });
    righe.textContent = '';
    voci.forEach(function (voce) {
      righe.appendChild(modello.content.cloneNode(true));
      var riga = righe.lastElementChild;
      riga.querySelector('input[name="listino_id"]').value = ids[voce.nome.toLowerCase()] || '';
      riga.querySelector('input[name="listino_nome"]').value = voce.nome;
      riga.querySelector('input[name="listino_quota"]').value = voce.quota === null ? '' : voce.quota;
    });
    return true;
  }

  function Preset(radice) {
    this.radice = radice;
    this.t = testi(radice);
    var sel = radice.getAttribute('data-modulo');
    this.form = sel ? document.querySelector(sel) : null;
    this.scelta = radice.querySelector('[data-preset-scelta]');
    this.foglio = radice.querySelector('[data-preset-foglio]');
    this.nome = radice.querySelector('[data-preset-nome]');
    this.sostituisci = radice.querySelector('[data-preset-sostituisci]');
    this.esito = radice.querySelector('[data-preset-esito]');
    this.toccati = {};
    this.ascolta();
    // Il preset scelto al passo 1 del wizard: il passo 2 lo applica appena si
    // apre, per i valori proposti alle gare che al passo 1 non c'erano.
    var auto = radice.getAttribute('data-preset-auto');
    if (auto && this.form) this.carica(auto);
  }

  Preset.prototype.dici = function (messaggio, errore) {
    this.esito.textContent = messaggio || '';
    this.esito.hidden = !messaggio;
    this.esito.classList.toggle('text-danger', !!errore);
  };

  Preset.prototype.ascolta = function () {
    var self = this;
    var r = this.radice;
    // Al passo 1 del wizard del campionato c'è solo «Parti da un preset».
    var apri = r.querySelector('[data-preset-apri]');
    if (apri && this.foglio) {
      apri.addEventListener('click', function () {
        self.foglio.hidden = !self.foglio.hidden;
        self.sostituisci.hidden = true;
        if (!self.foglio.hidden) self.nome.focus();
      });
      r.querySelector('[data-preset-annulla]').addEventListener('click', function () {
        self.foglio.hidden = true;
      });
      r.querySelector('[data-preset-conferma]').addEventListener('click', function () { self.salva(false); });
      this.sostituisci.addEventListener('click', function () { self.salva(true); });
      // Invio nel nome salva il preset, non il modulo che lo contiene.
      this.nome.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); self.salva(false); }
      });
    }
    if (this.scelta) {
      this.scelta.addEventListener('change', function () {
        if (self.scelta.value) self.carica(self.scelta.value);
      });
    }
    if (this.form) {
      // Solo i gesti veri del direttore: gli eventi che scrive il preset non
      // sono `isTrusted`, quindi non contano come «toccato».
      var segna = function (e) {
        if (!e.isTrusted || !e.target.name || r.contains(e.target)) return;
        var nome = e.target.name.indexOf('listino_') === 0 ? 'listino' : e.target.name;
        self.toccati[nome] = true;
      };
      this.form.addEventListener('input', segna);
      this.form.addEventListener('change', segna);
      // L'editor delle catene cambia il campo nascosto senza eventi.
      this.form.addEventListener('click', function (e) {
        if (!e.isTrusted) return;
        var catena = e.target.closest('[data-catena]');
        var valore = catena && catena.querySelector('[data-catena-valore]');
        if (valore && e.target.closest('button')) self.toccati[valore.name] = true;
      });
    }
  };

  Preset.prototype.carica = function (id) {
    var self = this;
    var url = this.radice.getAttribute('data-url-valori').replace('/0/', '/' + id + '/');
    // Dalla modifica di un campionato: la nota sui playoff sa se lì gli inviti
    // sono già partiti.
    var camp = this.radice.getAttribute('data-campionato-id');
    if (camp) url += '?campionato_id=' + encodeURIComponent(camp);
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin' })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (risposta) {
        if (!risposta.ok || !risposta.d.success) throw new Error(risposta.d.error || self.t.errore);
        self.applica(risposta.d);
        // Il wizard porta la scelta al passo successivo (`preset_id`).
        var scelto = self.form && self.form.querySelector('[data-preset-scelto]');
        if (scelto) scelto.value = String(risposta.d.id);
      })
      .catch(function (e) { self.dici(e.message || self.t.errore, true); })
      .finally(function () { if (self.scelta) self.scelta.value = ''; });
  };

  Preset.prototype.applica = function (dati) {
    var self = this;
    var form = this.form;
    var conflitti = dati.valori.filter(function (c) {
      return self.toccati[c[0]] && cambierebbe(form, c[0], c[1]);
    });
    var saltati = {};
    conflitti.forEach(function (c) { saltati[c[0]] = true; });
    var listinoInConflitto = dati.listino.length && this.toccati.listino;

    function scriviTutti(soloQuesti) {
      var rifiutati = {};
      for (var giro = 0; giro < 2; giro++) {
        dati.valori.forEach(function (c) {
          if (soloQuesti ? !soloQuesti[c[0]] : saltati[c[0]]) return;
          if (scrivi(form, c[0], c[1]) === 'rifiutato') rifiutati[c[0]] = true;
          else delete rifiutati[c[0]];
        });
      }
      return Object.keys(rifiutati);
    }

    var rifiutati = scriviTutti(null);
    var note = [];
    if (dati.listino.length && !listinoInConflitto && !applicaListino(form, dati.listino)) {
      note.push(this.t.listinoNo);
    }
    var persi = dati.scartati.concat(rifiutati.map(function (n) { return etichetta(form, n); }));
    if (persi.length) note.push(this.t.nonApplicati.replace('{campi}', persi.join(', ')));
    // I playoff: al passo 1 del wizard si scrivono (e la nota dice quelli che
    // il passo 1 non sa creare); nella modifica non si toccano, e si dice.
    var conPlayoff = !!form.querySelector('[name="playoff_elite_enabled"]');
    if (conPlayoff && dati.nota_playoff_wizard) note.push(dati.nota_playoff_wizard);
    if (!conPlayoff && !this.radice.getAttribute('data-wizard') && dati.nota_playoff_altrove) {
      note.push(dati.nota_playoff_altrove);
    }
    this.dici([this.t.applicato.replace('{nome}', dati.nome)].concat(note).join(' '));

    if (!conflitti.length && !listinoInConflitto) return;
    var nomi = conflitti.map(function (c) { return etichetta(form, c[0]); });
    if (listinoInConflitto) nomi.push(this.t.listino);
    var chiedi = typeof window.showConfirm === 'function' ? window.showConfirm : null;
    var usaIlPreset = function () {
      scriviTutti(saltati);
      if (listinoInConflitto) applicaListino(form, dati.listino);
      conflitti.forEach(function (c) { delete self.toccati[c[0]]; });
    };
    if (chiedi) {
      chiedi(this.t.conflitto.replace('{campi}', nomi.join(', ')), usaIlPreset, {
        title: this.t.conflittoTitolo,
        confirmText: this.t.conflittoOk,
        confirmClass: 'btn-primary'
      });
    }
  };

  Preset.prototype.salva = function (sostituisci) {
    var self = this;
    var nome = this.nome.value.trim();
    if (!nome) { this.dici(this.t.nomeVuoto, true); this.nome.focus(); return; }
    var dati = this.form ? new FormData(this.form) : new FormData();
    dati.set('preset_nome', nome);
    if (sostituisci) dati.set('preset_sostituisci', '1');
    var camp = this.radice.getAttribute('data-campionato-id');
    var gara = this.radice.getAttribute('data-gara-id');
    if (camp) dati.set('preset_campionato_id', camp);
    if (gara) dati.set('preset_gara_id', gara);
    if (this.radice.getAttribute('data-wizard')) dati.set('preset_wizard', '1');
    var headers = { 'X-Requested-With': 'XMLHttpRequest' };
    if (typeof window.csrfToken === 'function') headers['X-CSRFToken'] = window.csrfToken();
    fetch(this.radice.getAttribute('data-url-salva'), {
      method: 'POST', body: dati, headers: headers, credentials: 'same-origin'
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (risposta) {
        var d = risposta.d;
        if (!risposta.ok || !d.success) {
          self.sostituisci.hidden = !d.conflitto;
          self.dici(d.error || self.t.errore, true);
          return;
        }
        self.foglio.hidden = true;
        self.sostituisci.hidden = true;
        self.nome.value = '';
        self.ricorda(d.preset);
        self.dici(d.message);
      })
      .catch(function () { self.dici(self.t.errore, true); });
  };

  /* Il preset appena salvato compare subito nel selettore. */
  Preset.prototype.ricorda = function (preset) {
    if (!this.scelta || !preset) return;
    var gia = Array.prototype.some.call(this.scelta.options, function (o) {
      return o.value === String(preset.id);
    });
    if (!gia) {
      var opzione = document.createElement('option');
      opzione.value = String(preset.id);
      opzione.textContent = preset.nome;
      this.scelta.appendChild(opzione);
    }
    // Il primo preset salvato: il menu non è più «Nessun preset salvato».
    if (this.scelta.disabled && this.t.scegli) this.scelta.options[0].textContent = this.t.scegli;
    this.scelta.disabled = false;
  };

  function avvia(contenitore) {
    (contenitore || document).querySelectorAll('[data-preset]:not([data-preset-pronto])')
      .forEach(function (radice) {
        radice.setAttribute('data-preset-pronto', '1');
        radice.c7Preset = new Preset(radice);
      });
  }

  window.c7Preset = { avvia: avvia };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { avvia(); });
  } else {
    avvia();
  }
})();
