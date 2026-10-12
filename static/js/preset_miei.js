/* «I miei preset» (ADR-082): i pannelli sotto le righe e la ricerca dei
 * direttori con cui condividere.
 *
 * Un pannello alla volta: aprirne uno chiude gli altri. Condividere cerca per
 * nome (almeno due lettere) fra i direttori, e ogni scelto diventa un
 * `<input name="user_id">` del modulo: «Manda la copia» invia il modulo come
 * un form qualsiasi, e il server crea una copia per ciascuno.
 */
(function () {
  'use strict';

  var radice = document.querySelector('[data-preset-miei]');
  if (!radice) return;
  var t = {};
  try { t = JSON.parse(radice.getAttribute('data-testi') || '{}'); } catch (e) { t = {}; }
  var urlCerca = radice.getAttribute('data-url-cerca');

  function chiudiTutti(tranne) {
    radice.querySelectorAll('[data-preset-pannello]').forEach(function (p) {
      if (p !== tranne) p.hidden = true;
    });
    radice.querySelectorAll('[data-preset-apri]').forEach(function (b) {
      var riga = b.closest('[data-preset-riga]');
      var pannello = riga.querySelector('[data-preset-pannello="' + b.getAttribute('data-preset-apri') + '"]');
      b.setAttribute('aria-expanded', pannello === tranne && !tranne.hidden ? 'true' : 'false');
    });
  }

  radice.querySelectorAll('[data-preset-apri]').forEach(function (bottone) {
    bottone.addEventListener('click', function () {
      var riga = bottone.closest('[data-preset-riga]');
      var pannello = riga.querySelector('[data-preset-pannello="' + bottone.getAttribute('data-preset-apri') + '"]');
      pannello.hidden = !pannello.hidden;
      chiudiTutti(pannello);
      if (!pannello.hidden) {
        var campo = pannello.querySelector('input[type="text"], input[type="search"]');
        if (campo) { campo.focus(); if (campo.select) campo.select(); }
      }
    });
  });

  function riga(nome, sotto, etichetta, azione) {
    var r = document.createElement('div');
    r.className = 'c7-rows__row';
    var main = document.createElement('div');
    main.className = 'c7-rows__main';
    var titolo = document.createElement('div');
    titolo.className = 'c7-rows__title';
    titolo.textContent = nome;
    main.appendChild(titolo);
    if (sotto) {
      var s = document.createElement('div');
      s.className = 'c7-rows__sub';
      s.textContent = sotto;
      main.appendChild(s);
    }
    r.appendChild(main);
    if (etichetta) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-secondary btn-sm';
      b.textContent = etichetta;
      b.addEventListener('click', azione);
      r.appendChild(b);
    }
    return r;
  }

  function Condividi(modulo) {
    this.modulo = modulo;
    this.cerca = modulo.querySelector('[data-preset-cerca]');
    this.trovati = modulo.querySelector('[data-preset-trovati]');
    this.scelti = modulo.querySelector('[data-preset-scelti]');
    this.manda = modulo.querySelector('[data-preset-manda]');
    this.scelta = {};
    this.attesa = null;
    var self = this;
    this.cerca.addEventListener('input', function () {
      clearTimeout(self.attesa);
      self.attesa = setTimeout(function () { self.chiedi(); }, 250);
    });
    // Invio nella ricerca non manda il modulo con la scelta a metà.
    this.cerca.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') e.preventDefault();
    });
  }

  Condividi.prototype.nota = function (testo) {
    this.trovati.textContent = '';
    if (testo) this.trovati.appendChild(riga(testo));
  };

  Condividi.prototype.chiedi = function () {
    var self = this;
    var q = this.cerca.value.trim();
    if (q.length < 2) { this.nota(q ? t.corto : ''); return; }
    fetch(urlCerca + '?q=' + encodeURIComponent(q), {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }, credentials: 'same-origin'
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (q !== self.cerca.value.trim()) return;
        if (!d.success) { self.nota(d.error || t.errore); return; }
        var liberi = d.direttori.filter(function (u) { return !self.scelta[u.id]; });
        if (!liberi.length) { self.nota(t.nessuno); return; }
        self.trovati.textContent = '';
        liberi.forEach(function (u) {
          self.trovati.appendChild(riga(u.nome, u.citta, t.aggiungi, function () { self.aggiungi(u); }));
        });
      })
      .catch(function () { self.nota(t.errore); });
  };

  Condividi.prototype.aggiungi = function (u) {
    var self = this;
    if (this.scelta[u.id]) return;
    var r = riga(u.nome, u.citta, t.togli, function () {
      delete self.scelta[u.id];
      r.remove();
      self.aggiorna();
    });
    var campo = document.createElement('input');
    campo.type = 'hidden';
    campo.name = 'user_id';
    campo.value = String(u.id);
    r.appendChild(campo);
    this.scelta[u.id] = r;
    this.scelti.appendChild(r);
    this.cerca.value = '';
    this.nota('');
    this.aggiorna();
    this.cerca.focus();
  };

  Condividi.prototype.aggiorna = function () {
    this.manda.disabled = !Object.keys(this.scelta).length;
  };

  radice.querySelectorAll('[data-preset-condividi]').forEach(function (modulo) {
    modulo.c7Condividi = new Condividi(modulo);
  });
})();
