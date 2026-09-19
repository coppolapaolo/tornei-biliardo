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

  /* Il TPA si mostra come sul referto: .780, non 780. Il caso pieno e'
     l'unico che sfugge: mille millesimi sono 1.000, non .1000. */
  function formatTpa(value) {
    if (value === null || value === undefined) return '—';
    if (value >= 1000) {
      return Math.floor(value / 1000) + '.' + String(value % 1000).padStart(3, '0');
    }
    return '.' + String(value).padStart(3, '0');
  }

  function turnLabel(turn) {
    const note = turn.annotation;
    let text = '';
    if (turn.is_break && note.break_potted !== null && note.break_potted !== undefined) {
      text += note.break_potted + '/';
    }
    text += (note.total_potted === null || note.total_potted === undefined) ? '–' : note.total_potted;
    if (turn.main_note) text += ' ' + turn.main_note.replace('^', '');
    if (turn.secondary_note) text += ' ' + turn.secondary_note;
    if (note.first_shot_kick_in) text += ' ↺';
    if (turn.winning) text += ' ●';
    return text;
  }

  /* "M^n" e "S^x" sul foglio sono una lettera grande con un apice. */
  function noteNode(doc, text) {
    const wrap = doc.createElement('span');
    const parts = String(text).split('^');
    wrap.appendChild(doc.createTextNode(parts[0]));
    if (parts.length > 1) {
      const sup = doc.createElement('sup');
      sup.textContent = parts[1];
      wrap.appendChild(sup);
    }
    return wrap;
  }

  /* Il tastierino ha caselle fisse, sempre le stesse: le lettere stanno
     dove il referto cartaceo le mette (motivo di fine turno, falli,
     annotazioni piccole) e quelle non ammesse si spengono invece di
     sparire. Se i pulsanti si riordinassero a ogni tocco, chi annota
     mentre gioca finirebbe per premere quello sbagliato. */
  const LETTER_SLOTS = [
    ['M', 'c7-tpa-key'],
    ['K', 'c7-tpa-key'],
    ['S', 'c7-tpa-key'],
    ['P', 'c7-tpa-key c7-tpa-key--foul'],
    ['G', 'c7-tpa-key c7-tpa-key--game'],
    ['N', 'c7-tpa-key c7-tpa-key--foul'],
    ['n', 'c7-tpa-key c7-tpa-key--small'],
    ['x', 'c7-tpa-key c7-tpa-key--small'],
    ['p', 'c7-tpa-key c7-tpa-key--small']
  ];

  function avvia(host, opzioni) {
    opzioni = opzioni || {};
    const doc = host.ownerDocument;
    const dati = host.dataset;
    const CURRENT_USER_ID = Number(dati.currentUserId);
    const CAN_WRITE = dati.canWrite === 'true';
    const ricarica = opzioni.ricarica || function () { root.location.reload(); };

    let state = JSON.parse(doc.getElementById('tpaStato').textContent);

    const el = (id) => doc.getElementById(id);

    function seatOf(n) { return state.players[n] || state.players[String(n)] || {}; }
    function tallyOf(n) { return state.score[n] || state.score[String(n)] || {}; }

    function renderPlayers() {
      const players = el('tpaPlayers');
      players.textContent = '';
      [1, 2].forEach((seat) => {
        const tally = tallyOf(seat);
        const active = state.current_player === seat;
        /* Il proprio riquadro non si tocca: si tocca quello dell'altro, ed
           e' quello il gesto che passa il tavolo. */
        const tappable = CAN_WRITE && !active && state.can_switch_player;
        const node = doc.createElement(tappable ? 'button' : 'div');
        node.className = 'c7-tpa-player' + (active ? ' c7-tpa-player--active' : '');
        if (tappable) {
          node.type = 'button';
          /* Prima della spaccata il tocco sceglie chi spacca; dopo,
             chiude il turno. Chi dei due lo dice il motore. */
          node.addEventListener('click', () => send(dati.pressUrl, {
            command: state.current.can_choose_seat ? ('seat:' + seat) : 'end'
          }));
        }

        const left = doc.createElement('span');
        const name = doc.createElement('span');
        name.className = 'c7-tpa-player__name';
        name.textContent = seatOf(seat).name || ('#' + seat);
        const meta = doc.createElement('span');
        meta.className = 'c7-tpa-player__meta';
        const errors = tally.total_errors || 0;
        let metaText = 'B' + (tally.balls_potted || 0) + ' E' + errors;
        if (active) metaText += ' · ' + (state.current.is_break ? dati.etSpacca : dati.etAlTavolo);
        else if (tappable) {
          metaText += ' · ' + (state.current.can_choose_seat ? dati.etSpaccaLui : dati.etPassa);
        }
        meta.textContent = metaText;
        left.appendChild(name);
        left.appendChild(meta);

        const tpa = doc.createElement('span');
        tpa.className = 'c7-tpa-player__tpa';
        tpa.textContent = formatTpa(tally.tpa);
        if (tally.tpa === null || tally.tpa === undefined) tpa.title = dati.etSenzaTpa;

        const racks = doc.createElement('span');
        racks.className = 'c7-tpa-player__racks';
        racks.textContent = tally.racks_won || 0;

        node.appendChild(left);
        node.appendChild(tpa);
        node.appendChild(racks);
        players.appendChild(node);
      });
    }

    function renderBoxes() {
      const current = state.current;
      const note = current.annotation;
      const white = el('tpaWhiteBox');
      const shaded = el('tpaShadedBox');
      white.textContent = '';
      shaded.textContent = '';
      white.classList.toggle('c7-tpa-box--won', !!current.winning);

      /* Sulla spaccata le bilie della spaccata si annotano per prime e
         restano scritte in piccolo, in alto: e' cosi' sul foglio. */
      if (current.is_break && note.break_potted !== null && note.break_potted !== undefined) {
        const brk = doc.createElement('span');
        brk.className = 'c7-tpa-box__break';
        brk.textContent = note.break_potted;
        white.appendChild(brk);
      }

      if (note.total_potted === null || note.total_potted === undefined) {
        const hint = doc.createElement('span');
        hint.className = 'c7-tpa-box__hint';
        hint.textContent = dati.etBilie;
        white.appendChild(hint);
      } else {
        const balls = doc.createElement('span');
        balls.textContent = note.total_potted;
        white.appendChild(balls);
        if (current.main_note) white.appendChild(noteNode(doc, current.main_note));
        else if (!current.winning) {
          const hint = doc.createElement('span');
          hint.className = 'c7-tpa-box__hint';
          hint.style.marginLeft = '8px';
          hint.textContent = dati.etPerche;
          white.appendChild(hint);
        }
        if (note.first_shot_kick_in) {
          const kick = doc.createElement('span');
          kick.className = 'c7-tpa-box__hint';
          kick.style.marginLeft = '8px';
          kick.textContent = '↺';
          kick.title = dati.etKickIn;
          white.appendChild(kick);
        }
      }
      shaded.textContent = current.secondary_note || '';
    }

    function renderPad() {
      if (!CAN_WRITE) return;
      const numbers = el('tpaNumbers');
      const letters = el('tpaLetters');
      numbers.textContent = '';
      letters.textContent = '';
      const available = state.buttons || [];
      const has = (b) => available.indexOf(b) >= 0;

      /* Le bilie: una casella per ogni numero possibile in questa
         disciplina. Quando non se ne puo' premere nessuna il blocco sparisce
         del tutto, invece di lasciare una griglia spenta. */
      const anyNumber = available.some((b) => /^\d+$/.test(b));
      numbers.style.display = anyNumber ? '' : 'none';
      if (anyNumber) {
        for (let n = 0; n <= state.game_type; n++) {
          numbers.appendChild(key(String(n), String(n), 'c7-tpa-key', has(String(n))));
        }
      }

      LETTER_SLOTS.forEach(([command, className]) => {
        letters.appendChild(key(command, command, className, has(command)));
      });

      if (has('K-in')) {
        letters.appendChild(key('K-in', '↺ ' + dati.etKickIn, 'c7-tpa-key c7-tpa-key--wide', true));
      }
      if (has('runout')) {
        const on = state.current.annotation.run_out === true;
        letters.appendChild(key(
          'runout',
          on ? '✓ ' + dati.etRunoutSi : dati.etRunoutChiedi,
          'c7-tpa-key c7-tpa-key--wide' + (on ? ' c7-tpa-key--on' : ''),
          true
        ));
      }
    }

    function key(command, label, className, enabled) {
      const button = doc.createElement('button');
      button.type = 'button';
      button.className = className;
      button.textContent = label;
      button.disabled = !enabled;
      if (enabled) {
        button.addEventListener('click', () => send(dati.pressUrl, { command: command }));
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
          note.appendChild(doc.createTextNode(turnLabel(turn)));
          row.appendChild(seat);
          row.appendChild(who);
          row.appendChild(note);
          sheet.appendChild(row);
        });
      });
    }

    function render() {
      renderPlayers();
      renderBoxes();
      renderPad();
      renderSheet();
      const undo = el('tpaUndo');
      if (undo) undo.disabled = !state.commands;
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
            render();
          } else {
            root.showError(data.message || dati.etErrore);
          }
        })
        .catch(() => root.showError(dati.etErrore))
        .finally(() => { busy = false; });
    }

    const undoButton = el('tpaUndo');
    if (undoButton) undoButton.addEventListener('click', () => send(dati.undoUrl, {}));

    function refresh() {
      root.fetch(dati.stateUrl)
        .then((response) => response.json())
        .then((data) => {
          if (data.success && data.state) {
            state = data.state;
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

    render();
  }

  root.c7TpaReferto = { avvia: avvia, formatTpa: formatTpa, turnLabel: turnLabel };
})(window);
