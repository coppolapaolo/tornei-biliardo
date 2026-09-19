/**
 * La pagina del referto TPA (ADR-044).
 *
 * Questo modulo **non conosce le regole**: disegna lo stato che il server gli
 * dà e rimanda ogni tocco al server, che risponde con lo stato intero. Quali
 * tasti sono ammessi, chi è al tavolo, quanto vale il TPA lo decide
 * `models/tpa/engine.py`, e solo lui.
 *
 * Tutto ciò che dipende dalla pagina arriva dall'involucro: gli indirizzi e i
 * testi tradotti negli attributi `data-*`, lo stato iniziale in un blocco
 * `<script type="application/json" id="tpaStato">`. Fino al 19/09/2026 stava
 * inline nel template, con gli indirizzi scritti a mano, e non si poteva
 * provare; ora lo prova `tests/frontend/test_tpa_referto.cjs`.
 *
 * Dalla pagina ospite usa `csrfToken()` (base.html), `showError()`
 * (notifications.js) e `Polling` (polling.js).
 */
(function (root) {
  'use strict';

  /* Il TPA va da 0 a 1000 e si scrive senza punto (D20): il server manda
     gia' i millesimi interi, quindi qui non c'e' niente da calcolare. */
  function formatTpa(value) {
    if (value === null || value === undefined) return '—';
    return String(value);
  }

  function has(value) { return value !== null && value !== undefined; }

  /* Il numero del giocatore cerchiato in piccolo: e' cosi' che il referto
     Accu-Stats scrive «il primo tiro e' stato di calcio». */
  function kickNode(doc, player, aria) {
    const kick = doc.createElement('span');
    kick.className = 'c7-tpa-kick';
    kick.textContent = player;
    if (aria) kick.setAttribute('aria-label', aria.replace('{n}', player));
    return kick;
  }

  /* L'annotazione di un turno come la scrive il referto: le bilie della
     spaccata in apice *prima* del totale (mai «1/3»), il totale cerchiato se
     il turno ha vinto il triangolo (non una «G»), poi la lettera grande col
     suo apice: M^n, S^x, S^p. Una funzione sola per le caselle e per il
     referto sotto, cosi' non possono scriverla in due modi. */
  function notationNode(doc, turn) {
    const note = turn.annotation;
    const wrap = doc.createElement('span');
    wrap.className = 'c7-tpa-nt';
    if (turn.is_break && has(note.break_potted)) {
      const brk = doc.createElement('sup');
      brk.className = 'c7-tpa-nt__break';
      brk.textContent = note.break_potted;
      wrap.appendChild(brk);
    }
    if (has(note.total_potted)) {
      const balls = doc.createElement('span');
      balls.className = 'c7-tpa-nt__balls' + (turn.winning ? ' c7-tpa-nt__balls--won' : '');
      balls.textContent = note.total_potted;
      wrap.appendChild(balls);
    }
    if (turn.main_note) {
      const parts = String(turn.main_note).split('^');
      const main = doc.createElement('span');
      main.className = 'c7-tpa-nt__main';
      main.appendChild(doc.createTextNode(parts[0]));
      if (parts.length > 1) {
        const sup = doc.createElement('sup');
        sup.textContent = parts[1];
        main.appendChild(sup);
      }
      wrap.appendChild(main);
    }
    return wrap;
  }

  /* Il tastierino e' uno ed e' sempre tutto visibile, a tre colonne come
     quello di un telefono: e' cosi' nell'app Accu-Stats originale. Le lettere
     stanno dove il referto cartaceo le mette (motivo di fine turno, falli,
     annotazioni piccole) e i tasti non ammessi si spengono invece di sparire.
     Se i pulsanti si riordinassero a ogni tocco, chi annota mentre gioca
     finirebbe per premere quello sbagliato. */
  const LETTER_SLOTS = [
    ['M', 'c7-tpa-key', 'etCapM'],
    ['K', 'c7-tpa-key', 'etCapK'],
    ['S', 'c7-tpa-key', 'etCapS'],
    ['P', 'c7-tpa-key c7-tpa-key--foul', 'etCapP'],
    ['G', 'c7-tpa-key c7-tpa-key--game', 'etCapG'],
    ['N', 'c7-tpa-key c7-tpa-key--foul', 'etCapN'],
    ['n', 'c7-tpa-key c7-tpa-key--small', null],
    ['x', 'c7-tpa-key c7-tpa-key--small', null],
    ['p', 'c7-tpa-key c7-tpa-key--small', null]
  ];

  function avvia(host, opzioni) {
    opzioni = opzioni || {};
    const doc = host.ownerDocument;
    const dati = host.dataset;
    const CURRENT_USER_ID = Number(dati.currentUserId);
    const CAN_WRITE = dati.canWrite === 'true';
    const ricarica = opzioni.ricarica || function () { root.location.reload(); };
    /* Il foglio e' un modal di Bootstrap: aprirlo e chiuderlo e' l'unica cosa
       che qui dipende da Bootstrap, e nei test la sostituisce un finto. */
    const foglio = opzioni.foglio || {
      apri: (node) => root.bootstrap.Modal.getOrCreateInstance(node).show(),
      chiudi: (node) => root.bootstrap.Modal.getOrCreateInstance(node).hide()
    };

    let state = JSON.parse(doc.getElementById('tpaStato').textContent);

    const el = (id) => doc.getElementById(id);

    function seatOf(n) { return state.players[n] || state.players[String(n)] || {}; }

    /* Rileggere il referto e' una **vista**: sta tutta qui, nel browser, e non
       tocca ne' il registro ne' il punteggio (ADR-044, emendamento del
       19/09/2026). `leggendo` e' l'indice del turno che si sta rileggendo fra
       tutti i turni della partita messi in fila; `null` vuol dire «il turno in
       corso», ed e' l'unico stato in cui si scrive. */
    let leggendo = null;

    function allTurns() {
      const all = [];
      (state.racks || []).forEach((rack) => {
        rack.turns.forEach((turn, index) => all.push({ rack: rack.number, index: index, turn: turn }));
      });
      return all;
    }

    function view() {
      const all = allTurns();
      const total = Math.max(all.length, 1);
      if (leggendo === null || leggendo >= all.length - 1) {
        leggendo = null;
        return {
          live: true, position: total, total: total, all: all,
          turn: state.current, rack: state.current_rack, index: Infinity,
          player: state.current_player, score: state.score
        };
      }
      const at = all[leggendo];
      return {
        live: false, position: leggendo + 1, total: total, all: all,
        turn: at.turn, rack: at.rack, index: at.index,
        player: at.turn.player,
        /* Il punteggio di allora: la fotografia che il motore ha scattato
           subito dopo quel turno. */
        score: at.turn.score_snapshot || state.score
      };
    }

    function tallyOf(score, n) { return score[n] || score[String(n)] || {}; }

    function span(className, text) {
      const node = doc.createElement('span');
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    }

    function figure(label, value, title) {
      const fig = span('c7-tpa-fig');
      fig.appendChild(span('c7-tpa-fig__k', label));
      const v = span('c7-tpa-fig__v', value);
      if (title) v.title = title;
      fig.appendChild(v);
      return fig;
    }

    /* L'ultimo turno giocato da un posto in questo triangolo: e' quello che
       resta scritto nella card di chi non e' al tavolo. A triangolo nuovo non
       c'e', e le caselle restano bianche. */
    function lastTurnOf(seat, v) {
      const rack = (state.racks || []).filter((r) => r.number === v.rack)[0];
      if (!rack) return null;
      for (let i = Math.min(rack.turns.length, v.index) - 1; i >= 0; i--) {
        const turn = rack.turns[i];
        if (turn.player === seat && has(turn.annotation.total_potted)) return turn;
      }
      return null;
    }

    function renderPlayers(v) {
      const players = el('tpaPlayers');
      players.textContent = '';
      [1, 2].forEach((seat) => {
        const tally = tallyOf(v.score, seat);
        const active = v.player === seat;
        const name = seatOf(seat).name || ('#' + seat);
        /* Il proprio riquadro non si tocca: si tocca quello dell'altro, ed
           e' quello il gesto che passa il tavolo. */
        const tappable = CAN_WRITE && v.live && !active && state.can_switch_player;
        const node = doc.createElement(tappable ? 'button' : 'div');
        node.className = 'c7-tpa-half' +
          (active ? ' c7-tpa-half--on' : '') + (tappable ? ' c7-tpa-half--tap' : '');
        if (tappable) {
          node.type = 'button';
          /* Prima della spaccata il tocco sceglie chi spacca; dopo,
             chiude il turno. Chi dei due lo dice il motore. */
          node.addEventListener('click', () => send(dati.pressUrl, {
            command: state.current.can_choose_seat ? ('seat:' + seat) : 'end'
          }));
        }

        node.appendChild(span('c7-tpa-half__name', name));

        /* Il TPA conta quanto il punteggio: stessa misura, stesso peso. */
        const figs = span('c7-tpa-figs');
        figs.appendChild(figure(dati.etTriangoli, tally.racks_won || 0));
        figs.appendChild(figure(dati.etTpa, formatTpa(tally.tpa), has(tally.tpa) ? '' : dati.etSenzaTpa));
        node.appendChild(figs);

        const balls = tally.balls_potted || 0;
        const errors = tally.total_errors || 0;
        let meta = balls + ' ' + (balls === 1 ? dati.etBilia : dati.etBilie) +
          ' · ' + errors + ' ' + (errors === 1 ? dati.etErroreUno : dati.etErrori);
        if (active) meta = (v.turn.is_break ? dati.etSpacca : dati.etAlTavolo) + ' · ' + meta;
        node.appendChild(span('c7-tpa-half__meta', meta));

        /* Le due caselle del referto, dentro la card di ciascuno. Chi e' al
           tavolo ci vede il turno che sta scrivendo, l'altro il suo ultimo. */
        const turn = active ? v.turn : lastTurnOf(seat, v);
        const slip = span('c7-tpa-slip');
        /* La riga del calcio c'e' sempre, anche vuota: senza, le caselle dei
           due giocatori finirebbero a due altezze diverse. */
        const kickrow = span('c7-tpa-kickrow');
        if (turn && turn.annotation.first_shot_kick_in) {
          kickrow.appendChild(kickNode(doc, turn.player || seat, dati.etKickInAria));
        }
        slip.appendChild(kickrow);
        slip.appendChild(span(''));

        const white = span('c7-tpa-box c7-tpa-box--white');
        const shaded = span('c7-tpa-box c7-tpa-box--shaded');
        if (turn) {
          if (has(turn.annotation.total_potted) || has(turn.annotation.break_potted)) {
            white.appendChild(notationNode(doc, turn));
          }
          /* Un solo suggerimento, corto, e solo a chi compila: a casella
             bianca si chiedono le bilie. Dopo, il suggerimento sono le lettere che si accendono —
             una frase qui andrebbe a capo e le caselle dei due giocatori
             finirebbero a due altezze diverse. */
          if (CAN_WRITE && v.live && active && !has(turn.annotation.total_potted)) {
            white.appendChild(span('c7-tpa-box__hint', dati.etQuante));
          }
          shaded.textContent = turn.secondary_note || '';
        }
        slip.appendChild(white);
        slip.appendChild(shaded);
        node.appendChild(slip);

        if (tappable) {
          const template = state.current.can_choose_seat ? dati.etSpaccaLui : dati.etPassa;
          node.appendChild(span('c7-tpa-half__tap', template.replace('{nome}', name)));
        }
        players.appendChild(node);
      });
    }

    function renderPad(v) {
      if (!CAN_WRITE) return;
      const numbers = el('tpaNumbers');
      const letters = el('tpaLetters');
      numbers.textContent = '';
      letters.textContent = '';
      /* Mentre si rilegge non si scrive: il tastierino resta dov'e', spento. */
      const available = v.live ? (state.buttons || []) : [];
      const allowed = (b) => available.indexOf(b) >= 0;

      /* «Cancella» sta nel posto vuoto accanto allo 0: toglie l'annotazione
         di questo turno, tutta. Non e' l'annulla, che toglie un tocco solo. */
      const clear = key('clear', '×', 'c7-tpa-key c7-tpa-key--clear', v.live && !!state.can_clear, dati.etCancella);
      clear.setAttribute('aria-label', dati.etCancellaAria);
      numbers.appendChild(clear);
      numbers.appendChild(key('0', '0', 'c7-tpa-key', allowed('0')));
      /* Il terzo posto della prima riga: il 10 a palla 10, vuoto altrimenti. */
      if (state.game_type >= 10) numbers.appendChild(key('10', '10', 'c7-tpa-key', allowed('10')));
      else numbers.appendChild(span('c7-tpa-pad__gap'));
      for (let n = 1; n <= 9; n++) {
        numbers.appendChild(key(String(n), String(n), 'c7-tpa-key', allowed(String(n))));
      }

      LETTER_SLOTS.forEach(([command, className, caption]) => {
        letters.appendChild(key(command, command, className, allowed(command), caption ? dati[caption] : null));
      });

      if (!v.live) {
        /* Da un turno del passato si puo' solo ripartire, e dopo una conferma. */
        const restart = key('restart', dati.etRiparti, 'c7-tpa-key c7-tpa-key--wide c7-tpa-key--restart', false);
        restart.disabled = false;
        restart.addEventListener('click', () => askRestart(v));
        letters.appendChild(restart);
        return;
      }
      letters.appendChild(key('K-in', dati.etKickIn, 'c7-tpa-key c7-tpa-key--wide', allowed('K-in')));
      /* Il run-out si chiede solo quando e' ambiguo: capita di rado, e un
         tasto spento in piu' tutto il resto del tempo sarebbe solo rumore. */
      if (allowed('runout')) {
        const on = state.current.annotation.run_out === true;
        letters.appendChild(key(
          'runout',
          on ? dati.etRunoutSi : dati.etRunoutChiedi,
          'c7-tpa-key c7-tpa-key--wide' + (on ? ' c7-tpa-key--on' : ''),
          true
        ));
      }
    }

    function key(command, label, className, enabled, caption) {
      const button = doc.createElement('button');
      button.type = 'button';
      button.className = className;
      button.setAttribute('data-command', command);
      button.appendChild(doc.createTextNode(label));
      if (caption) button.appendChild(span('c7-tpa-key__cap', caption));
      button.disabled = !enabled;
      if (enabled) {
        button.addEventListener('click', () => send(
          command === 'clear' ? dati.clearUrl : dati.pressUrl,
          command === 'clear' ? {} : { command: command }
        ));
      }
      return button;
    }

    function renderSheet() {
      const sheet = el('tpaSheet');
      sheet.textContent = '';
      (state.racks || []).forEach((rack) => {
        const head = doc.createElement('div');
        head.className = 'c7-tpa-sheet__rack';
        const title = doc.createElement('span');
        title.textContent = dati.etTriangolo + ' ' + rack.number;
        head.appendChild(title);
        const last = rack.turns[rack.turns.length - 1];
        if (last && last.score_snapshot) {
          const snap = last.score_snapshot;
          const one = snap[1] || snap['1'] || {};
          const two = snap[2] || snap['2'] || {};
          const score = doc.createElement('span');
          score.textContent = (one.racks_won || 0) + '–' + (two.racks_won || 0);
          head.appendChild(score);
        }
        sheet.appendChild(head);

        rack.turns.forEach((turn) => {
          const row = doc.createElement('div');
          row.className = 'c7-tpa-sheet__turn' + (turn.winning ? ' c7-tpa-sheet__turn--won' : '');
          const seat = doc.createElement('span');
          seat.className = 'c7-tpa-sheet__seat';
          seat.textContent = turn.player;
          const who = doc.createElement('span');
          who.className = 'c7-tpa-sheet__who';
          who.textContent = seatOf(turn.player).name || ('#' + turn.player);
          const note = doc.createElement('span');
          note.className = 'c7-tpa-sheet__note';
          if (turn.annotation.first_shot_kick_in) {
            note.appendChild(kickNode(doc, turn.player, dati.etKickInAria));
          }
          if (has(turn.annotation.total_potted)) note.appendChild(notationNode(doc, turn));
          else note.appendChild(doc.createTextNode('–'));
          if (turn.secondary_note) note.appendChild(span('c7-tpa-nt__foul', turn.secondary_note));
          row.appendChild(seat);
          row.appendChild(who);
          row.appendChild(note);
          sheet.appendChild(row);
        });
      });
    }

    function renderHistory(v) {
      const back = el('tpaIndietro');
      if (!back) return;
      const fill = (text) => text.replace('{n}', v.position).replace('{m}', v.total);
      el('tpaPosizione').textContent = fill(dati.etPosizione);
      back.disabled = v.position <= 1;
      el('tpaAvanti').disabled = v.live;
      const reading = el('tpaRileggi');
      reading.hidden = v.live;
      reading.textContent = v.live ? '' : fill(dati.etRileggi);
      host.classList.toggle('c7-tpa--reading', !v.live);
    }

    function step(delta) {
      const v = view();
      const next = v.position - 1 + delta;
      if (next < 0 || next > v.total - 1) return;
      leggendo = next;
      render();
    }

    /* Il foglio di conferma nomina cio' che esce dal referto: il turno che si
       riapre vuoto, e sotto i turni gia' scritti che vengono dopo. Quello in
       corso, se e' ancora bianco, non e' una perdita e non compare. */
    let pending = null;
    function askRestart(v) {
      pending = { rack: v.rack, turn: v.index + 1 };
      el('tpaRipartiTitolo').textContent = dati.etRipartiTitolo.replace('{n}', v.position);
      el('tpaRipartiConferma').textContent = dati.etRipartiConferma.replace('{n}', v.position);
      const list = el('tpaRipartiElenco');
      list.textContent = '';
      v.all.slice(v.position - 1).forEach((item, offset) => {
        const written = has(item.turn.annotation.total_potted) || has(item.turn.annotation.break_potted);
        if (offset > 0 && !written) return;
        const row = span('c7-tpa-sheet__turn' + (offset > 0 ? ' c7-tpa-out' : ''));
        row.appendChild(span('c7-tpa-sheet__seat', item.turn.player));
        row.appendChild(span('c7-tpa-sheet__who', seatOf(item.turn.player).name || ('#' + item.turn.player)));
        const note = span('c7-tpa-sheet__note');
        if (offset === 0) {
          note.textContent = dati.etSiRiannota;
          note.className += ' c7-tpa-sheet__note--text';
        } else {
          note.appendChild(notationNode(doc, item.turn));
          if (item.turn.secondary_note) note.appendChild(span('c7-tpa-nt__foul', item.turn.secondary_note));
        }
        row.appendChild(note);
        list.appendChild(row);
      });
      foglio.apri(el('tpaRipartiModal'));
    }

    function render() {
      const v = view();
      renderPlayers(v);
      renderPad(v);
      renderSheet();
      renderHistory(v);
    }

    let busy = false;
    function send(url, body) {
      if (busy) return;
      busy = true;
      root.fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': root.csrfToken() },
        body: JSON.stringify(body || {})
      })
        .then((response) => response.json())
        .then((data) => {
          if (data.success && data.state) {
            state = data.state;
            leggendo = null;
            render();
          } else {
            root.showError(data.message || dati.etErrore);
          }
        })
        .catch(() => root.showError(dati.etErrore))
        .finally(() => { busy = false; });
    }

    if (el('tpaIndietro')) {
      el('tpaIndietro').addEventListener('click', () => step(-1));
      el('tpaAvanti').addEventListener('click', () => step(1));
      el('tpaRipartiConferma').addEventListener('click', () => {
        foglio.chiudi(el('tpaRipartiModal'));
        if (pending) send(dati.restartUrl, pending);
        pending = null;
      });
    }

    function refresh() {
      root.fetch(dati.stateUrl)
        .then((response) => response.json())
        .then((data) => {
          if (data.success && data.state) {
            state = data.state;
            leggendo = null;
            render();
            /* Il referto e' stato chiuso mentre lo guardavi: da qui in
               poi la pagina e' un'altra cosa, e va ripresa dal server. */
            if (state.closed) ricarica();
          }
        })
        .catch(() => {});
    }

    /* Chi guarda senza compilare deve vedere il referto crescere dall'altro
       capo del tavolo. Si aggancia al canale del match — lo stesso che usa la
       pagina della partita — e rilegge lo stato **quando qualcosa e' successo**
       invece che a orologio.

       E ridisegna, non ricarica: chi guarda sta seguendo una partita, e una
       pagina che si ricarica da sola gli fa perdere il segno ogni volta. */
    if (!CAN_WRITE && !state.closed && root.Polling) {
      root.Polling.create({
        url: dati.pollUrl,
        onEvent: function (event) {
          if (event.type !== 'tpa_updated') return;
          if (event.data && event.data.by === CURRENT_USER_ID) return;
          refresh();
        }
      }).start();
    }

    /* La parola sotto le lettere si puo' spegnere: e' una comodita' di chi
       guarda, quindi sta nel suo browser e la pagina funziona anche senza. */
    const parole = el('tpaParole');
    if (parole) {
      let spente = false;
      try { spente = root.localStorage.getItem('tpaParole') === 'no'; } catch (e) { /* niente */ }
      parole.checked = !spente;
      host.classList.toggle('c7-tpa--nocap', spente);
      parole.addEventListener('change', () => {
        host.classList.toggle('c7-tpa--nocap', !parole.checked);
        try { root.localStorage.setItem('tpaParole', parole.checked ? 'si' : 'no'); } catch (e) { /* niente */ }
        misuraDock();
      });
    }

    /* Sotto lg il tastierino e' agganciato in basso: il contenuto deve poter
       scorrere fin sopra, e quanto e' alto lo sa solo il browser. */
    function misuraDock() {
      const dock = el('tpaDock');
      if (!dock || !dock.getBoundingClientRect) return;
      doc.documentElement.style.setProperty('--c7-tpa-dock-h', Math.round(dock.getBoundingClientRect().height) + 'px');
    }

    render();
    misuraDock();
    /* Su un telefono basso il tastierino coprirebbe il fondo delle card: si
       scorre, una volta sola, quel tanto che le porta sopra. */
    const dock = el('tpaDock');
    if (dock && dock.getBoundingClientRect && root.getComputedStyle &&
        root.getComputedStyle(dock).position === 'fixed') {
      const sotto = el('tpaPlayers').getBoundingClientRect().bottom - dock.getBoundingClientRect().top;
      if (sotto > 0) root.scrollTo(0, (root.scrollY || 0) + sotto + 8);
    }
    if (root.addEventListener) root.addEventListener('resize', misuraDock);
  }

  root.c7TpaReferto = { avvia: avvia, formatTpa: formatTpa };
})(window);
