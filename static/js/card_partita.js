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
 * Due regole sul tocco, nate alla gara 3 della Ronin Cup (16/09/2026), dove
 * «tap e non succede niente» e la card che spariva in fondo alla chiusura
 * hanno fatto dubitare di ogni tocco:
 *
 * - **il numero cambia al tocco**, non alla risposta. L'indirizzo riceve il
 *   punteggio intero e non un incremento, quindi i tocchi arrivati mentre una
 *   richiesta e' in volo si accodano senza rischio: a volo concluso parte
 *   l'ultimo punteggio. Un rifiuto rimette quello confermato dal server. Il
 *   trio resta un tocco alla volta: quali + sono accesi lo sa solo il server.
 * - **il tocco che chiude aspetta** (`attesaChiusura`, tre secondi): il numero
 *   finale si vede subito, la card dice che si sta chiudendo e offre
 *   «Annulla». Chiudere libera il tavolo, avvia la partita in attesa e muove
 *   i rating: si ripensa prima, non dopo. Se la pagina se ne va durante
 *   l'attesa, `pagehide` spedisce la chiusura con `keepalive`. A chiusura
 *   confermata la card lo dice, e solo dopo un attimo la pagina si ricarica
 *   (`attesaRicarica`) — altrimenti la card sparisce in fondo senza che si
 *   capisca se il tocco e' andato.
 * - **anche «Valida il risultato» aspetta** (`attendi`), con la stessa
 *   striscia: chiude la partita quanto l'ultimo + (gara del 23/09/2026).
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

  /* Lo stato di una card fra un tocco e l'altro: cosa ha confermato il
     server, se una richiesta e' in volo, se ne serve un'altra, e l'attesa
     prima della chiusura. */
  const stati = new WeakMap();
  const inAttesa = new Set();

  function statoDi(card) {
    let st = stati.get(card);
    if (!st) {
      st = { confermati: punti(card), inVolo: null, ancora: false, timer: null, tic: null, prima: null, opzioni: {} };
      stati.set(card, st);
    }
    return st;
  }

  /** Se con questo punteggio la partita (o il set) e' alla distanza. */
  function chiude(card, p) {
    const tipo = card.dataset.tipo || 'due';
    if (tipo !== 'due' && tipo !== 'set') return false;
    const max = parseInt(card.dataset.max || '0', 10);
    if (!max) return false;
    return card.dataset.raceTo === '1' ? (p[0] >= max || p[1] >= max) : (p[0] + p[1] >= max);
  }

  function uguali(a, b) {
    return a.length === b.length && a.every(function (v, i) { return v === b[i]; });
  }

  function richiesta(card, o, keepalive) {
    const dati = new root.FormData();
    const p = punti(card);
    String(card.dataset.campi || '').split(',').forEach(function (campo, i) {
      dati.append(campo, p[i]);
    });
    const init = {
      method: 'POST',
      headers: { 'X-CSRFToken': o.csrf || '', 'X-Requested-With': 'XMLHttpRequest' },
      body: dati
    };
    if (keepalive) init.keepalive = true;
    return root.fetch(card.dataset.url, init);
  }

  function testo(o, chiave, ripiego) {
    return (o.testi && o.testi[chiave]) || ripiego;
  }

  /* Subito sotto i punteggi, vicino al dito che ha appena toccato il +: in
     fondo alla card «Annulla» finiva sotto la nav flottante del telefono. */
  function appendi(card, striscia) {
    const lati = card.querySelector('.c7-partita__lati');
    if (lati && typeof lati.after === 'function') lati.after(striscia);
    else card.appendChild(striscia);
  }

  function togliStriscia(card) {
    const s = card.querySelector('.c7-partita__chiusura');
    if (s) s.remove();
  }

  function fermaAttesa(card) {
    const st = statoDi(card);
    if (st.timer) root.clearTimeout(st.timer);
    if (st.tic) root.clearInterval(st.tic);
    st.timer = null;
    st.tic = null;
    inAttesa.delete(card);
    togliStriscia(card);
  }

  /** La striscia «si chiude fra N» con «Annulla», sotto i punteggi.
   *  `alAnnulla` e' quel che fa «Annulla»: tornare al punteggio di prima per
   *  gli stepper, rimettere il pulsante per «Valida il risultato». */
  function mostraAttesa(card, o, millisecondi, alAnnulla) {
    togliStriscia(card);
    const doc = card.ownerDocument;
    const striscia = doc.createElement('div');
    striscia.className = 'c7-partita__chiusura';
    striscia.setAttribute('role', 'status');
    const scritta = doc.createElement('span');
    scritta.className = 'c7-partita__chiusura-testo';
    const annulla = doc.createElement('button');
    annulla.type = 'button';
    annulla.className = 'btn btn-secondary c7-partita__chiusura-annulla';
    annulla.textContent = testo(o, 'annulla', 'Annulla');
    striscia.appendChild(scritta);
    striscia.appendChild(annulla);
    appendi(card, striscia);

    let restano = Math.max(1, Math.round(millisecondi / 1000));
    function scrivi() {
      scritta.textContent = testo(o, 'chiusura', 'Si chiude fra {n} s').replace('{n}', restano);
    }
    scrivi();
    statoDi(card).tic = root.setInterval(function () {
      if (restano > 1) { restano -= 1; scrivi(); }
    }, 1000);

    annulla.addEventListener('click', alAnnulla);
  }

  function mostraChiusa(card, o, soloSet) {
    togliStriscia(card);
    const doc = card.ownerDocument;
    const striscia = doc.createElement('div');
    striscia.className = 'c7-partita__chiusura c7-partita__chiusura--fatta';
    striscia.setAttribute('role', 'status');
    const icona = doc.createElement('i');
    icona.className = 'fas fa-check';
    const scritta = doc.createElement('span');
    scritta.className = 'c7-partita__chiusura-testo';
    scritta.textContent = soloSet
      ? testo(o, 'setChiuso', 'Set chiuso')
      : testo(o, 'chiusa', 'Partita chiusa');
    striscia.appendChild(icona);
    striscia.appendChild(scritta);
    appendi(card, striscia);
    card.querySelectorAll('.c7-partita__meno[data-lato], .c7-partita__piu[data-lato]')
      .forEach(function (b) { b.disabled = true; });
  }

  function avviaAttesa(card, o, prima) {
    const st = statoDi(card);
    const millisecondi = o.attesaChiusura === undefined ? 3000 : o.attesaChiusura;
    // `prima` e' il punteggio a cui torna «Annulla»: quello di prima del
    // tocco che ha portato alla distanza, anche se nell'attesa ne arrivano
    // altri (un − sull'altro lato resta alla distanza e fa ripartire il conto).
    if (!st.timer) st.prima = prima;
    fermaAttesa(card);
    st.opzioni = o;
    st.parti = function (keepalive) { return richiesta(card, o, keepalive); };
    inAttesa.add(card);
    mostraAttesa(card, o, millisecondi, function () {
      const prima = st.prima;
      fermaAttesa(card);
      if (!prima) return;
      card.dataset.punti = prima.join(',');
      aggiorna(card);
      if (!uguali(prima, st.confermati)) spedisci(card, o);
    });
    st.timer = root.setTimeout(function () {
      fermaAttesa(card);
      spedisci(card, o);
    }, millisecondi);
  }

  /**
   * «Valida il risultato» (e ogni comando che chiude una partita senza
   * passare dagli stepper): la stessa attesa del tocco che chiude, con la
   * stessa striscia e lo stesso «Annulla». Rilievo della gara del
   * 2026-09-23: segnando i punteggi il direttore aveva tre secondi per
   * ripensarci, validando no — e validare chiude quanto l'ultimo +.
   *
   * `azione(keepalive)` fa la richiesta; `keepalive` e' vero quando parte
   * perche' la pagina se ne sta andando (`pagehide`). Durante l'attesa il
   * pulsante e' spento: un secondo tocco non accoda una seconda chiusura.
   */
  function attendi(btn, azione, opzioni) {
    const o = opzioni || {};
    const card = btn.closest('.c7-partita') || btn.parentElement;
    const st = statoDi(card);
    if (st.timer) return false;
    const millisecondi = o.attesaChiusura === undefined ? 3000 : o.attesaChiusura;
    btn.disabled = true;
    st.prima = null;
    st.opzioni = o;
    st.parti = function (keepalive) { return azione(keepalive); };
    inAttesa.add(card);
    mostraAttesa(card, o, millisecondi, function () {
      fermaAttesa(card);
      btn.disabled = false;
    });
    st.timer = root.setTimeout(function () {
      fermaAttesa(card);
      azione(false);
    }, millisecondi);
    return true;
  }

  /** Spedisce il punteggio della card; una richiesta alla volta per card. */
  function spedisci(card, o) {
    const st = statoDi(card);
    if (st.inVolo) {
      st.ancora = true;
      return st.inVolo;
    }
    const ricarica = o.ricarica || function () { root.location.reload(); };
    const spediti = punti(card);
    const trio = card.dataset.tipo === 'trio';
    if (trio) {
      card.querySelectorAll('.c7-partita__meno[data-lato], .c7-partita__piu[data-lato]')
        .forEach(function (b) { b.disabled = true; });
    }
    card.dataset.inCorso = '1';
    st.inVolo = richiesta(card, o, false)
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (esito) {
        const d = esito.d || {};
        if (!esito.ok || !d.success) throw new Error(d.error || o.messaggioErrore || '');
        st.inVolo = null;
        delete card.dataset.inCorso;
        const eraDaValidare = card.dataset.stato === 'da_validare';
        if (d.finished || d.set_chiuso) {
          // La card lo dice, e la pagina si ricarica un attimo dopo: senza,
          // la card sparisce in fondo e non si capisce se il tocco e' andato.
          mostraChiusa(card, o, Boolean(d.set_chiuso) && !d.finished);
          root.setTimeout(ricarica, o.attesaRicarica === undefined ? 1200 : o.attesaRicarica);
          return true;
        }
        if (Boolean(d.at_distance) !== eraDaValidare) {
          ricarica();
          return true;
        }
        st.confermati = d.punti || [d.player1_score, d.player2_score];
        if (st.confermati.some(function (v) { return v === undefined; })) st.confermati = spediti;
        if (d.piu) card.dataset.piu = d.piu.map(function (b) { return b ? 1 : 0; }).join(',');
        if (st.ancora) {
          // Nel frattempo il punteggio e' andato avanti: la risposta vecchia
          // non riscrive il numero nuovo, parte quello.
          st.ancora = false;
          if (!uguali(punti(card), st.confermati) && !st.timer) return spedisci(card, o);
          return true;
        }
        if (!st.timer) card.dataset.punti = st.confermati.join(',');
        aggiorna(card);
        return true;
      })
      .catch(function (e) {
        st.inVolo = null;
        st.ancora = false;
        delete card.dataset.inCorso;
        fermaAttesa(card);
        card.dataset.punti = st.confermati.join(',');
        aggiorna(card);
        if (o.errore) o.errore(e.message || o.messaggioErrore || '');
        return false;
      });
    return st.inVolo;
  }

  /* Se la pagina se ne va durante l'attesa — un ricaricamento dal poll, il
     telefono che cambia app — la chiusura parte lo stesso: il tocco c'e'
     stato, e perderlo in silenzio e' peggio di chiudere tre secondi prima. */
  root.addEventListener('pagehide', function () {
    Array.from(inAttesa).forEach(function (card) {
      const parti = statoDi(card).parti;
      fermaAttesa(card);
      try { if (parti) parti(true); } catch (e) { /* la pagina sta uscendo */ }
    });
  });

  /**
   * Un tocco su − o +. Il numero cambia subito; ritorna una promessa, risolta
   * quando il server ha risposto (o subito, se non c'e' niente da inviare).
   * `opzioni`: `csrf` (il token), `ricarica` (default `location.reload`),
   * `errore(messaggio)`, `messaggioErrore` (il testo di ripiego),
   * `attesaChiusura` e `attesaRicarica` (millisecondi), `testi` (`chiusura`
   * con `{n}`, `annulla`, `chiusa`, `setChiuso`).
   */
  function passo(btn, delta, opzioni) {
    const o = opzioni || {};
    const card = btn.closest('[data-tipo]');
    if (!card) return Promise.resolve(false);
    const trio = card.dataset.tipo === 'trio';
    if (trio && card.dataset.inCorso === '1') return Promise.resolve(false);
    const lato = parseInt(btn.dataset.lato, 10) - 1;
    const attuali = punti(card);
    const l = limiti(card);
    if (delta > 0 && !l.piu[lato]) return Promise.resolve(false);
    if (delta < 0 && !l.meno[lato]) return Promise.resolve(false);
    const nuovi = attuali.slice();
    nuovi[lato] = Math.max(0, nuovi[lato] + delta);

    // Prima di toccare il numero: alla nascita lo stato fotografa il
    // punteggio come «confermato dal server», ed e' li' che torna un rifiuto.
    const st = statoDi(card);
    card.dataset.punti = nuovi.join(',');
    aggiorna(card);

    if (card.dataset.tipo === 'x' || !card.dataset.url) return Promise.resolve(true);

    if (chiude(card, nuovi)) {
      avviaAttesa(card, o, attuali);
      return Promise.resolve(true);
    }
    if (st.timer) {
      // Un − durante l'attesa e' un ripensamento: la chiusura non parte.
      fermaAttesa(card);
      if (uguali(nuovi, st.confermati) && !st.inVolo) return Promise.resolve(true);
    }
    return spedisci(card, o);
  }

  root.CardPartita = {
    limiti: limiti, aggiorna: aggiorna, passo: passo, punti: punti, attendi: attendi
  };
})(window);
