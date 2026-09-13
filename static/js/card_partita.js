/**
 * Gli stepper della card della partita, per chi dirige (canvas 3C).
 *
 * Una card sola per quattro forme, distinte da `data-tipo`:
 *
 * - `due`  — due lati; «al N» spegne i due + quando uno arriva a N,
 *            «esattamente N» quando la somma arriva a N (`data-max`,
 *            `data-race-to`). Salva a ogni tocco.
 * - `set`  — gli stepper del set in corso di una partita a set: stessa regola
 *            di `due`, con la distanza del set. Salva a ogni tocco.
 * - `trio` — tre lati; quali + sono accesi lo dice il server (`data-piu`),
 *            perché dipende dall'ordine del girone e non solo dai numeri.
 *            Salva a ogni tocco.
 * - `x`    — un lato, da 0 a `data-max`. Non salva: il punteggio parte con
 *            «Convalida».
 *
 * Il punteggio sta in `data-punti` («3,1» o «2,1,0»), i nomi dei campi da
 * inviare in `data-campi`, l'indirizzo in `data-url`. I pulsanti portano
 * `data-lato` (da 1) e i numeri `data-num` (da 1).
 *
 * Il foglio della correzione usa le stesse funzioni sui suoi lati: `due`, o
 * `trio` senza `data-piu` e con `data-massimo` e `data-totale`, i limiti del
 * trio giocato per intero.
 */
(function (root) {
  'use strict';

  function numeri(testo) {
    return String(testo || '')
      .split(',')
      .filter(function (s) { return s !== ''; })
      .map(function (s) { return parseInt(s, 10) || 0; });
  }

  function punti(el) {
    return numeri(el.dataset.punti);
  }

  /** Quali − e + sono accesi, lato per lato. */
  function limiti(el) {
    const tipo = el.dataset.tipo || 'due';
    const p = punti(el);
    const max = parseInt(el.dataset.max || '0', 10);
    const meno = p.map(function (v) { return v > 0; });
    let piu;
    if (tipo === 'trio' && el.dataset.piu !== undefined) {
      const accesi = numeri(el.dataset.piu);
      piu = p.map(function (_, i) { return accesi[i] === 1; });
    } else if (tipo === 'trio') {
      // Il foglio della correzione: il trio e' gia' giocato per intero, quindi
      // l'ordine del girone non spegne niente. Restano i due limiti: i
      // triangoli che ognuno gioca e quelli del trio.
      const massimo = parseInt(el.dataset.massimo || '0', 10);
      const totale = parseInt(el.dataset.totale || '0', 10);
      const somma = p.reduce(function (a, b) { return a + b; }, 0);
      piu = p.map(function (v) { return v < massimo && somma < totale; });
    } else if (tipo === 'x') {
      piu = [p[0] < max];
    } else {
      const raceTo = el.dataset.raceTo === '1';
      const stop = raceTo ? (p[0] >= max || p[1] >= max) : (p[0] + p[1] >= max);
      piu = [!stop, !stop];
    }
    return { piu: piu, meno: meno };
  }

  function scriviNumero(n, valore) {
    if (root.c7ScorePop && typeof root.c7ScorePop.segna === 'function') {
      root.c7ScorePop.segna(n, valore);
    } else {
      n.textContent = valore;
    }
  }

  /** Accende e spegne − e + e riscrive i numeri dal punteggio. */
  function aggiorna(el) {
    const p = punti(el);
    const l = limiti(el);
    el.querySelectorAll('.c7-partita__piu[data-lato]').forEach(function (b) {
      b.disabled = !l.piu[parseInt(b.dataset.lato, 10) - 1];
    });
    el.querySelectorAll('.c7-partita__meno[data-lato]').forEach(function (b) {
      b.disabled = !l.meno[parseInt(b.dataset.lato, 10) - 1];
    });
    el.querySelectorAll('[data-num]').forEach(function (n) {
      const v = p[parseInt(n.dataset.num, 10) - 1];
      if (v !== undefined && String(n.textContent).trim() !== String(v)) scriviNumero(n, v);
    });
  }

  /**
   * Un tocco su − o +. Ritorna una promessa, risolta quando la card è
   * aggiornata (o la pagina si ricarica). `opzioni`: `csrf` (il token),
   * `ricarica` (default `location.reload`), `errore(messaggio)`,
   * `messaggioErrore` (il testo di ripiego).
   */
  function passo(btn, delta, opzioni) {
    const o = opzioni || {};
    const card = btn.closest('[data-tipo]');
    if (!card || card.dataset.inCorso === '1') return Promise.resolve(false);
    const lato = parseInt(btn.dataset.lato, 10) - 1;
    const attuali = punti(card);
    const l = limiti(card);
    if (delta > 0 && !l.piu[lato]) return Promise.resolve(false);
    if (delta < 0 && !l.meno[lato]) return Promise.resolve(false);
    const nuovi = attuali.slice();
    nuovi[lato] = Math.max(0, nuovi[lato] + delta);

    if (card.dataset.tipo === 'x' || !card.dataset.url) {
      card.dataset.punti = nuovi.join(',');
      aggiorna(card);
      return Promise.resolve(true);
    }

    const ricarica = o.ricarica || function () { root.location.reload(); };
    card.dataset.inCorso = '1';
    card.querySelectorAll('.c7-partita__meno[data-lato], .c7-partita__piu[data-lato]')
      .forEach(function (b) { b.disabled = true; });
    const dati = new root.FormData();
    String(card.dataset.campi || '').split(',').forEach(function (campo, i) {
      dati.append(campo, nuovi[i]);
    });
    return root.fetch(card.dataset.url, {
      method: 'POST',
      headers: { 'X-CSRFToken': o.csrf || '', 'X-Requested-With': 'XMLHttpRequest' },
      body: dati
    })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (esito) {
        const d = esito.d || {};
        if (!esito.ok || !d.success) throw new Error(d.error || o.messaggioErrore || '');
        const eraDaValidare = card.dataset.stato === 'da_validare';
        if (d.finished || d.set_chiuso || Boolean(d.at_distance) !== eraDaValidare) {
          delete card.dataset.inCorso;
          ricarica();
          return true;
        }
        const conferma = d.punti || [d.player1_score, d.player2_score];
        card.dataset.punti = conferma.join(',');
        if (d.piu) card.dataset.piu = d.piu.map(function (b) { return b ? 1 : 0; }).join(',');
        delete card.dataset.inCorso;
        aggiorna(card);
        return true;
      })
      .catch(function (e) {
        delete card.dataset.inCorso;
        aggiorna(card);
        if (o.errore) o.errore(e.message || o.messaggioErrore || '');
        return false;
      });
  }

  root.CardPartita = { limiti: limiti, aggiorna: aggiorna, passo: passo, punti: punti };
})(window);
