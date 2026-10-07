/* L'editor della catena degli spareggi (ADR-078).
 *
 * Una lista riordinabile di criteri: il primo è il criterio principale del
 * sistema di classifica, che non si tocca; poi le voci della catena, che si
 * spostano, si tolgono e si aggiungono. Sotto, la frase del regolamento.
 *
 * Il server manda tutto già tradotto in `data-config`
 * (`models/classification/editor_catena.py`), e riapplica le regole al
 * salvataggio (`catene.testo_dal_modulo`): qui si evita solo di offrire ciò
 * che non è ammesso.
 *
 * Regole: il sorteggio è sempre l'ultimo, e a turno e campionato c'è sempre
 * (chiude l'ordine); lo spareggio SSR compare una volta sola e mai nel turno;
 * il criterio principale non è una voce della catena.
 *
 * Con `data-sistema-da` l'editor segue un <select> del sistema di classifica:
 * se la catena era quella di default del sistema vecchio, diventa quella del
 * nuovo; altrimenti perde solo il criterio che è diventato principale.
 *
 * Il valore viaggia nel campo nascosto `[data-catena-valore]`, le voci
 * separate da virgole.
 */
(function () {
  'use strict';

  var SORTEGGIO = 'sorteggio';
  var SSR = 'ssr';

  function criterio(voce) {
    return String(voce).split(':')[0];
  }

  function posto(voce) {
    var parti = String(voce).split(':');
    return parti.length > 1 ? parseInt(parti[1], 10) : null;
  }

  function sistemaValido(valore) {
    return valore === 'RACK' || valore === 'RACKS' ? 'RACK' : 'WINS';
  }

  function uguali(a, b) {
    return a.length === b.length && a.every(function (v, i) { return v === b[i]; });
  }

  function crea(tag, classe, testo) {
    var el = document.createElement(tag);
    if (classe) el.className = classe;
    if (testo !== undefined) el.textContent = testo;
    return el;
  }

  function bottone(icona, etichetta, azione, disabilitato) {
    var b = crea('button', 'c7-iconbtn');
    b.type = 'button';
    b.setAttribute('aria-label', etichetta);
    b.title = etichetta;
    b.dataset.azione = azione;
    if (disabilitato) b.disabled = true;
    var i = crea('i', 'fas ' + icona);
    i.setAttribute('aria-hidden', 'true');
    b.appendChild(i);
    return b;
  }

  function Editor(radice) {
    this.radice = radice;
    this.cfg = JSON.parse(radice.getAttribute('data-config'));
    this.sistema = sistemaValido(this.cfg.sistema);
    this.voci = this.cfg.voci.slice();
    this.valore = radice.querySelector('[data-catena-valore]');
    this.lista = radice.querySelector('[data-catena-voci]');
    this.aggiungi = radice.querySelector('[data-catena-aggiungi]');
    this.frase = radice.querySelector('[data-catena-frase]');
    this.normalizza();
    this.disegna();
    this.ascolta();
  }

  Editor.prototype.ammessi = function () {
    return this.cfg.ammessi[this.sistema] || [];
  };

  /* Le stesse regole di `ordinamento.normalizza_catena`. */
  Editor.prototype.normalizza = function () {
    var ammessi = this.ammessi();
    var cfg = this.cfg;
    var visti = {};
    var sorteggio = false;
    var voci = [];
    this.voci.forEach(function (voce) {
      var c = criterio(voce);
      if (ammessi.indexOf(c) < 0 || visti[c]) return;
      visti[c] = true;
      if (c === SORTEGGIO) { sorteggio = true; return; }
      if (c === SSR) {
        voce = cfg.ssrConPosto ? SSR + ':' + (posto(voce) || cfg.ssrDefault) : SSR;
      }
      voci.push(voce);
    });
    if (sorteggio || cfg.completa) voci.push(SORTEGGIO);
    this.voci = voci;
  };

  Editor.prototype.nome = function (voce) {
    return this.cfg.nomi[criterio(voce)] || voce;
  };

  Editor.prototype.pezzoDiFrase = function (voce) {
    var n = posto(voce);
    if (criterio(voce) === SSR && n) return this.cfg.frasi.ssr_n.replace('{n}', n);
    return this.cfg.frasi[criterio(voce)] || voce;
  };

  /* La stessa frase di `ordinamento.descrivi_catena`. */
  Editor.prototype.componiFrase = function () {
    var t = this.cfg.testi;
    var aPari = this.cfg.aPari[this.sistema];
    if (!this.voci.length) return t.vuota.replace('{a_pari}', aPari);
    var self = this;
    var parti = this.voci.map(function (v) { return self.pezzoDiFrase(v); });
    var elenco = parti[0] + parti.slice(1).map(function (p) {
      return t.poi.replace('{x}', p);
    }).join('');
    return t.conta.replace('{a_pari}', aPari).replace('{elenco}', elenco);
  };

  Editor.prototype.riga = function (voce, indice) {
    var cfg = this.cfg;
    var t = cfg.testi;
    var c = criterio(voce);
    var li = crea('li', 'c7-catena__voce');
    li.dataset.indice = String(indice);
    li.appendChild(crea('span', 'c7-catena__n', String(indice + 2)));
    var corpo = crea('span', 'c7-catena__corpo');
    corpo.appendChild(crea('span', 'c7-catena__nome', this.nome(voce)));
    var fisso = c === SORTEGGIO && cfg.completa;
    if (c === SORTEGGIO) {
      corpo.appendChild(crea('span', 'c7-catena__nota', t.sorteggioNota));
    }
    li.appendChild(corpo);

    if (c === SSR && cfg.ssrConPosto) {
      var n = posto(voce) || cfg.ssrDefault;
      var stepper = crea('span', 'c7-catena__posto');
      stepper.appendChild(bottone('fa-minus', t.meno, 'meno', n <= 1));
      stepper.appendChild(crea('span', 'c7-catena__postovalore', t.finoAl.replace('{n}', n)));
      stepper.appendChild(bottone('fa-plus', t.piu, 'piu', n >= cfg.ssrMassimo));
      li.appendChild(stepper);
    }

    var comandi = crea('span', 'c7-catena__comandi');
    if (c !== SORTEGGIO) {
      var ultimaMobile = this.voci.length - 1 - (this.voci[this.voci.length - 1] === SORTEGGIO ? 1 : 0);
      comandi.appendChild(bottone('fa-arrow-up', t.su, 'su', indice === 0));
      comandi.appendChild(bottone('fa-arrow-down', t.giu, 'giu', indice >= ultimaMobile));
    }
    if (!fisso) comandi.appendChild(bottone('fa-xmark', t.togli, 'togli'));
    li.appendChild(comandi);
    return li;
  };

  Editor.prototype.disegna = function () {
    var self = this;
    var cfg = this.cfg;
    this.lista.textContent = '';

    var principale = crea('li', 'c7-catena__voce c7-catena__voce--principale');
    principale.appendChild(crea('span', 'c7-catena__n', '1'));
    var corpo = crea('span', 'c7-catena__corpo');
    corpo.appendChild(crea('span', 'c7-catena__nome', cfg.principale[this.sistema]));
    corpo.appendChild(crea('span', 'c7-catena__nota', cfg.testi.principaleNota));
    principale.appendChild(corpo);
    var lucchetto = crea('i', 'fas fa-lock c7-catena__lucchetto');
    lucchetto.setAttribute('aria-hidden', 'true');
    principale.appendChild(lucchetto);
    this.lista.appendChild(principale);

    this.voci.forEach(function (voce, i) { self.lista.appendChild(self.riga(voce, i)); });

    this.aggiungi.textContent = '';
    var presenti = this.voci.map(criterio);
    var liberi = this.ammessi().filter(function (c) {
      return presenti.indexOf(c) < 0;
    });
    liberi.forEach(function (c) {
      var b = crea('button', 'c7-catena__chip');
      b.type = 'button';
      b.dataset.aggiungi = c;
      var i = crea('i', 'fas fa-plus');
      i.setAttribute('aria-hidden', 'true');
      b.appendChild(i);
      b.appendChild(document.createTextNode(' ' + cfg.nomi[c]));
      self.aggiungi.appendChild(b);
    });
    if (!liberi.length) {
      this.aggiungi.appendChild(crea('span', 'c7-catena__nota', cfg.testi.nessunAltro));
    }

    this.frase.textContent = this.componiFrase();
    this.valore.value = this.voci.join(',');
  };

  Editor.prototype.sposta = function (da, a) {
    var voce = this.voci.splice(da, 1)[0];
    this.voci.splice(a, 0, voce);
  };

  Editor.prototype.cambiaSistema = function (nuovo) {
    nuovo = sistemaValido(nuovo);
    if (nuovo === this.sistema) return;
    var predefinita = this.cfg.default[this.sistema];
    var ssr = this.voci.filter(function (v) { return criterio(v) === SSR; })[0];
    var senzaSsr = this.voci.filter(function (v) { return criterio(v) !== SSR; });
    var eraDefault = uguali(this.voci, predefinita) || (
      this.cfg.ssrConPosto && uguali(senzaSsr, predefinita.filter(function (v) {
        return criterio(v) !== SSR;
      }))
    );
    this.sistema = nuovo;
    if (eraDefault) {
      var dopo = this.cfg.default[nuovo].slice();
      if (this.cfg.ssrConPosto) {
        dopo = dopo.filter(function (v) { return criterio(v) !== SSR; });
        if (ssr) dopo.splice(dopo.indexOf(SORTEGGIO) < 0 ? dopo.length : dopo.indexOf(SORTEGGIO), 0, ssr);
      }
      this.voci = dopo;
    }
    this.normalizza();
    this.disegna();
  };

  Editor.prototype.ascolta = function () {
    var self = this;
    this.radice.addEventListener('click', function (evento) {
      var chip = evento.target.closest('[data-aggiungi]');
      if (chip) {
        var c = chip.dataset.aggiungi;
        var voce = c === SSR && self.cfg.ssrConPosto ? SSR + ':' + self.cfg.ssrDefault : c;
        // Un criterio nuovo entra prima dello spareggio SSR e del sorteggio,
        // che di solito sono le ultime risorse; lo SSR entra prima del
        // sorteggio. Poi lo si sposta dove si vuole.
        var coda = c === SSR ? [SORTEGGIO] : [SSR, SORTEGGIO];
        var dove = self.voci.findIndex(function (v) { return coda.indexOf(criterio(v)) >= 0; });
        if (c === SORTEGGIO || dove < 0) self.voci.push(voce);
        else self.voci.splice(dove, 0, voce);
        self.normalizza();
        self.disegna();
        return;
      }
      var b = evento.target.closest('[data-azione]');
      if (!b || b.disabled) return;
      var li = b.closest('[data-indice]');
      var i = parseInt(li.dataset.indice, 10);
      var azione = b.dataset.azione;
      if (azione === 'su' && i > 0) self.sposta(i, i - 1);
      else if (azione === 'giu') self.sposta(i, i + 1);
      else if (azione === 'togli') self.voci.splice(i, 1);
      else if (azione === 'meno' || azione === 'piu') {
        var n = (posto(self.voci[i]) || self.cfg.ssrDefault) + (azione === 'piu' ? 1 : -1);
        n = Math.max(1, Math.min(self.cfg.ssrMassimo, n));
        self.voci[i] = SSR + ':' + n;
      }
      self.normalizza();
      self.disegna();
      // Il fuoco resta sul comando che si è appena usato, ora nella riga nuova.
      var riga = self.lista.querySelector('[data-indice="' + (
        azione === 'su' ? i - 1 : azione === 'giu' ? i + 1 : i
      ) + '"] [data-azione="' + azione + '"]');
      if (riga && !riga.disabled) riga.focus();
    });

    var sorgente = this.radice.getAttribute('data-sistema-da');
    if (sorgente) {
      var select = document.querySelector(sorgente);
      if (select) {
        this.cambiaSistema(select.value);
        select.addEventListener('change', function () { self.cambiaSistema(select.value); });
      }
    }
  };

  function avvia(contenitore) {
    (contenitore || document).querySelectorAll('[data-catena]:not([data-catena-pronta])')
      .forEach(function (radice) {
        radice.setAttribute('data-catena-pronta', '1');
        radice.c7Catena = new Editor(radice);
      });
  }

  window.c7CatenaSpareggi = { avvia: avvia, Editor: Editor };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { avvia(); });
  } else {
    avvia();
  }
})();
