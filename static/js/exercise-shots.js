/* L'esecuzione colpo per colpo di un esercizio (fase 5b; ADR-066).
 *
 * Il gesto è quello del tavolo vero: si tira, e si dice dov'è finita la
 * battente toccando il panno. Il tocco **non registra**: apre l'ingrandimento
 * sul bersaglio, dove il punto si corregge trascinando — indicare un punto a
 * pochi centimetri dal centro, su un tavolo grande quanto uno schermo di
 * telefono, col dito non si fa (#183). Registra «Conferma».
 *
 * Le coordinate sono quelle del disegnatore (1 diamante = 100 unità), non
 * pixel: il conto passa dal viewBox dichiarato in `data-vb` e dal riquadro
 * dell'SVG, bande di «xMidYMid meet» comprese. È l'unica geometria qui dentro;
 * quanto vale un punto lo sa **solo il server**, che ha il bersaglio.
 *
 * Il pezzo «come sta andando» e i comandi li ridisegna il server a ogni colpo,
 * e con loro il panno: per questo qui si ascolta sul contenitore
 * (`[data-run]`), che non viene sostituito, e non sui nodi di dentro.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-run]');
  if (!root || !root.dataset.shotUrl) return;

  var TABLE_W = 800;
  var TABLE_H = 400;
  var msg = { error: root.dataset.msgError, network: root.dataset.msgNetwork };

  function q(selector) { return root.querySelector(selector); }
  function fail(message) {
    if (typeof window.showError === 'function') window.showError(message);
  }
  function clamp(valore, minimo, massimo) {
    return Math.min(massimo, Math.max(minimo, valore));
  }

  /* Da pixel dello schermo a unità del disegnatore. `xMidYMid meet` scala il
   * viewBox per il lato più stretto e centra l'avanzo: le due bande vanno
   * tolte, o il punto slitta di quanto è larga la cornice. */
  function toTable(svg, clientX, clientY) {
    var vb = (svg.dataset.vb || '').split(/\s+/).map(Number);
    var r = svg.getBoundingClientRect();
    var scala = Math.min(r.width / vb[2], r.height / vb[3]);
    if (!scala || !isFinite(scala)) return null;
    return {
      x: vb[0] + (clientX - r.left - (r.width - vb[2] * scala) / 2) / scala,
      y: vb[1] + (clientY - r.top - (r.height - vb[3] * scala) / 2) / scala
    };
  }

  /* ---- L'ingrandimento ---------------------------------------------------- */
  var punto = null;

  function mostraPunto() {
    var marker = q('[data-cloth-marker]');
    if (!marker || !punto) return;
    marker.setAttribute('cx', String(punto.x));
    marker.setAttribute('cy', String(punto.y));
    // I mirini proiettano il punto sui bordi: a occhio la distanza dal centro
    // si giudica male, una riga no.
    var cx = q('[data-cross-x]');
    var cy = q('[data-cross-y]');
    if (cx) { cx.setAttribute('x1', String(punto.x)); cx.setAttribute('x2', String(punto.x)); }
    if (cy) { cy.setAttribute('y1', String(punto.y)); cy.setAttribute('y2', String(punto.y)); }
  }

  function apriZoom(p) {
    punto = { x: Math.round(clamp(p.x, 0, TABLE_W)), y: Math.round(clamp(p.y, 0, TABLE_H)) };
    var zoom = q('[data-cloth-zoom]');
    if (zoom) zoom.hidden = false;
    mostraPunto();
  }

  function chiudiZoom() {
    var zoom = q('[data-cloth-zoom]');
    if (zoom) zoom.hidden = true;
    punto = null;
  }

  /* ---- Le richieste ------------------------------------------------------- */
  var busy = false;

  /* La casella di scheda da cui si arriva (ADR-072), o niente: la chiusura
     la rimanda al server, che aggancia la prova e riporta alla seduta. */
  function contestoScheda() {
    if (!root.dataset.sheetSession) return null;
    return {
      sheet_session_id: root.dataset.sheetSession,
      sheet_item_id: root.dataset.sheetItem,
      sheet_variant_id: root.dataset.sheetVariant || null
    };
  }

  function post(url, payload) {
    if (busy) return;
    busy = true;
    var options = {
      method: 'POST',
      headers: { 'X-CSRFToken': window.csrfToken(), 'X-Requested-With': 'XMLHttpRequest' }
    };
    if (payload) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(payload);
    }
    window.fetch(url, options).then(function (r) { return r.json(); }).then(function (data) {
      if (!data.success) { fail(data.error || msg.error); return; }
      if (data.redirect_url) { window.location.href = data.redirect_url; return; }
      redraw(data);
    }).catch(function () { fail(msg.network); }).then(function () { busy = false; });
  }

  function redraw(data) {
    // `innerHTML` è voluto: i due pezzi li rende Jinja sul nostro server, con
    // l'autoescape acceso. Il panno è dentro il primo, quindi dopo un colpo la
    // nuvola dei punti d'arrivo è aggiornata e l'ingrandimento è richiuso.
    if (typeof data.progress_html === 'string') {
      var prog = q('[data-run-progress]');
      if (prog) prog.innerHTML = data.progress_html;
    }
    if (typeof data.dock_html === 'string') {
      var dock = q('[data-run-dock]');
      if (dock) dock.innerHTML = data.dock_html;
    }
    punto = null;
  }

  /* ---- I gesti ------------------------------------------------------------ */
  root.addEventListener('pointerdown', function (ev) {
    var pieno = ev.target.closest && ev.target.closest('[data-cloth-full]');
    if (pieno) {
      var p = toTable(pieno, ev.clientX, ev.clientY);
      if (p) apriZoom(p);
      return;
    }
    var zoomsvg = ev.target.closest && ev.target.closest('[data-cloth-zoomsvg]');
    if (zoomsvg) sposta(zoomsvg, ev);
  });

  function sposta(svg, ev) {
    var p = toTable(svg, ev.clientX, ev.clientY);
    if (!p) return;
    punto = { x: Math.round(clamp(p.x, 0, TABLE_W)), y: Math.round(clamp(p.y, 0, TABLE_H)) };
    mostraPunto();
  }

  root.addEventListener('pointermove', function (ev) {
    if (!punto) return;
    var zoomsvg = ev.target.closest && ev.target.closest('[data-cloth-zoomsvg]');
    if (zoomsvg) sposta(zoomsvg, ev);
  });

  root.addEventListener('click', function (ev) {
    var el = ev.target.closest && ev.target.closest(
      '[data-cloth-confirm],[data-cloth-cancel],[data-shot-miss],[data-shot-undo],' +
      '[data-shot-close],[data-shot-restart],[data-draw-next],[data-draw-outcome]'
    );
    if (!el) return;
    // Con estrazione (#452): si estrae la consegna, si tira, si dice com'è
    // andata scegliendo una voce. Quanto vale lo sa il server.
    if (el.hasAttribute('data-draw-next')) { post(root.dataset.drawUrl, null); return; }
    if (el.hasAttribute('data-draw-outcome')) {
      post(root.dataset.outcomeUrl, { outcome_index: el.dataset.drawOutcome });
      return;
    }
    if (el.hasAttribute('data-cloth-cancel')) { chiudiZoom(); return; }
    if (el.hasAttribute('data-cloth-confirm')) {
      if (punto) post(root.dataset.shotUrl, { made: true, x: punto.x, y: punto.y });
      return;
    }
    if (el.hasAttribute('data-shot-miss')) { post(root.dataset.shotUrl, { made: false }); return; }
    if (el.hasAttribute('data-shot-undo')) { post(root.dataset.shotUndoUrl, null); return; }
    if (el.hasAttribute('data-shot-close')) { post(root.dataset.shotCloseUrl, contestoScheda()); return; }
    if (el.hasAttribute('data-shot-restart')) { post(root.dataset.shotRestartUrl, null); }
  });
})();
