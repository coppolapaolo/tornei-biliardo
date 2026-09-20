/* Il builder dei drill — disegna la disposizione invece di fotografarla.

   Adattato dal tool autonomo allegato dall'utente. Due sole modifiche di
   sostanza rispetto all'originale: il ripristino di una scena e' stato
   estratto in `applyScene` (lo usano sia il caricamento da file sia il
   precaricamento dal server), e in fondo c'e' `window.DrillBuilder`, la
   superficie da cui l'app prende scena e immagine.

   Il resto e' l'originale. Se ne arriva una versione nuova conviene
   ri-applicare queste due modifiche invece di riconciliare a mano: il file e'
   grosso e la diff sarebbe illeggibile. */

"use strict";
/* ================================================================
   GEOMETRIA  —  1 diamante = 100 unità
   Tavolo 9 ft: superficie 100"x50" = 8x4 diamanti
   Biglia 2.25" = 0.18 diamanti  ->  diametro 18, raggio 9
=================================================================*/
const NS = "http://www.w3.org/2000/svg";
const U = 100, L = 8 * U, W = 4 * U;
const BR0 = 9;
let BR = BR0, D2 = 2*BR0;
const RAIL = 42, FRAME = 16, PAD = RAIL + FRAME;
const CORNER_CUT = 26, SIDE_CUT = 20;

const COLORS = ["#f5c518","#1c56a8","#cf2027","#6a2f8f","#e97418","#137a3a","#7d2c26","#1a1a1a"];
const LINE_COLORS = ["#ffffff","#f5c518","#111111","#e63946"];
const POCKETS = [{x:0,y:0},{x:L/2,y:0},{x:L,y:0},{x:0,y:W},{x:L/2,y:W},{x:L,y:W}];
const CLOTHS = {
  blu:    {cloth:"#2f8fc0", cush:"#175f80", edge:"#0f4258", ink:"#ffffff", grid:"#ffffff"},
  verde:  {cloth:"#2f8b5a", cush:"#1c6440", edge:"#124a2e", ink:"#ffffff", grid:"#ffffff"},
  grigio: {cloth:"#8d959d", cush:"#5c646d", edge:"#41474e", ink:"#14181c", grid:"#1b2026"}
};

/* Coefficienti pratici (modello didattico, non simulazione completa) */
const K_FOLLOW = 0.30;   // ~2/7: riproduce la regola dei 30° con rullata naturale
const K_DRAW   = 0.55;   // il retro stacca di più
const K_RAIL   = 0.45;   // effetto laterale sull'uscita dalla sponda
const K_DECAY  = 0.60;   // decadimento dell'effetto a ogni sponda
const K_LOSS   = 0.60;   // percorso residuo dopo una sponda
const TIP_MAX  = 0.5;    // massimo scostamento utile della punta (in raggi)
const MAX_EVENTS = 14;
const MAX_DEPTH = 3;

/* Forza in percentuale: al 30% il percorso è 2L (due lunghezze di tavolo).
   La distanza cresce con il quadrato della velocità.                      */
const forceDist = f => 2 * L * Math.pow(f/30, 2);

/* Le parole che il JS compone da solo.

   `babel.cfg` estrae solo da `.py` e `.html`, quindi una stringa scritta qui
   non passerebbe mai da `_()` e resterebbe italiana in ogni lingua. Il
   template le mette in `window.DRILL_BUILDER_I18N` gia' tradotte; il ripiego
   qui sotto e' l'italiano, cosi' la pagina non si svuota se il dizionario
   manca. */
const T_ = (chiave, ripiego) =>
  (window.DRILL_BUILDER_I18N && window.DRILL_BUILDER_I18N[chiave]) || ripiego;

const FORCE_PRESETS = [{v:10,l:T_("forceTouch","tocco")},{v:20,l:T_("forceSoft","piano")},
                       {v:30,l:T_("forceMedium","medio")},{v:60,l:T_("forceHard","forte")},
                       {v:100,l:T_("forceBreak","spacco")}];
const forceLabel = f => f<=12 ? T_("forceTouch","tocco") : f<=22 ? T_("forceSoft","piano")
                      : f<=45 ? T_("forceMedium","medio") : f<=80 ? T_("forceHard","forte")
                      : T_("forceBreak","spacco");

const CARD_W = 250, CARD_H = 136, CARD_GAP = 10;

const state = {
  items: [], tool:"select", armed:null,
  showGrid:true, showSub:false, showMarks:true, magnets:true, cloth:"blu", ballScale:1,
  snap:"quarter", orient:"h", title:"", pocketSnap:true,
  lineStyle:"solid", lineColor:"#ffffff", lineArrow:true, lineGhost:false,
  shotDefaults:{ tip:{x:0,y:0}, elev:0, force:30,
                 showPost:true, showObj:true, showStick:true, showCard:true, showAngle:false },
  aiming:null,
  sel:null, draft:null, preview:null, drag:null
};
let history = [], future = [], gRoot = null, altDown = false;

const $ = s => document.querySelector(s);
const stage = $("#stage");
function E(tag, a, parent){
  const e = document.createElementNS(NS, tag);
  for (const k in a) if (a[k] !== undefined && a[k] !== null) e.setAttribute(k, a[k]);
  if (parent) parent.appendChild(e);
  return e;
}
const uid  = () => Math.random().toString(36).slice(2, 9);
const dist = (a,b) => Math.hypot(a.x-b.x, a.y-b.y);
const sub  = (a,b) => ({x:a.x-b.x, y:a.y-b.y});
const add  = (a,b) => ({x:a.x+b.x, y:a.y+b.y});
const mul  = (a,k) => ({x:a.x*k, y:a.y*k});
const dot  = (a,b) => a.x*b.x + a.y*b.y;
const clamp1 = v => Math.max(-1, Math.min(1, v));
function unit(v){ const m = Math.hypot(v.x, v.y) || 1; return {x:v.x/m, y:v.y/m}; }
const byId = id => state.items.find(i => i.id === id);
const theme = () => CLOTHS[state.cloth];
function ballColor(b){
  return (b.ball==="cue"||b.ball==="ghost") ? theme().ink : COLORS[((+b.ball)-1)%8];
}
function setBallScale(s){ state.ballScale = s; BR = BR0*s; D2 = 2*BR; }

/* ================================================================
   AGGANCI
=================================================================*/
function snapStep(){ return {quarter:U/4, half:U/2, full:U, off:0}[state.snap]; }
function snapAxis(v, s){ if(!s) return v; const n = Math.round(v/s)*s;
  return Math.abs(n-v) <= s*0.35 ? n : v; }
const clampBall = p => ({x:Math.min(L-BR,Math.max(BR,p.x)), y:Math.min(W-BR,Math.max(BR,p.y))});
const clampPt   = p => ({x:Math.min(L,Math.max(0,p.x)),     y:Math.min(W,Math.max(0,p.y))});

function snapPoint(p, o){
  o = o || {};
  if (altDown) return p;
  if (o.toBalls !== false)
    for (const it of state.items)
      if (it.type === "ball" && dist(it,p) < BR+4) return {x:it.x, y:it.y};
  const s = snapStep();
  return {x:snapAxis(p.x,s), y:snapAxis(p.y,s)};
}
function snapBall(p, ignoreId){
  if (altDown) return clampBall(p);
  const s = snapStep();
  let out = {x:snapAxis(p.x,s), y:snapAxis(p.y,s)};
  if (!state.magnets) return clampBall(out);
  const T = 9;
  let fixX = null, fixY = null;
  if (Math.abs(p.x-BR) < T) fixX = BR; else if (Math.abs(p.x-(L-BR)) < T) fixX = L-BR;
  if (Math.abs(p.y-BR) < T) fixY = BR; else if (Math.abs(p.y-(W-BR)) < T) fixY = W-BR;
  if (fixX !== null) out.x = fixX;
  if (fixY !== null) out.y = fixY;
  let best = null;
  for (const b of state.items){
    if (b.type !== "ball" || b.id === ignoreId) continue;
    const d = dist(p,b); if (d < 0.5) continue;
    const err = Math.abs(d - D2);
    if (err < T && (!best || err < best.err)) best = {b, err, d};
  }
  if (best){
    const b = best.b;
    if (fixY !== null && Math.abs(fixY-b.y) < D2){
      const dx = Math.sqrt(D2*D2 - (fixY-b.y)*(fixY-b.y)) * (p.x >= b.x ? 1 : -1);
      out = {x:b.x+dx, y:fixY};
    } else if (fixX !== null && Math.abs(fixX-b.x) < D2){
      const dy = Math.sqrt(D2*D2 - (fixX-b.x)*(fixX-b.x)) * (p.y >= b.y ? 1 : -1);
      out = {x:fixX, y:b.y+dy};
    } else {
      out = add(b, mul(unit(sub(p,b)), D2));
    }
  }
  return clampBall(out);
}

/* ================================================================
   MOTORE DEL TIRO
   Il raggio parte dalla battente nella direzione della mira e cerca,
   segmento per segmento, il primo evento: biglia o sponda.
=================================================================*/
function pocketAt(p, r){ return POCKETS.find(q => dist(q,p) < (r||30)); }

function firstBall(P, dir, ignore){
  let best = null;
  for (const b of state.items){
    if (b.type !== "ball" || b.ball === "ghost" || ignore.has(b.id)) continue;
    const f = sub(b, P), tca = dot(f, dir);
    if (tca <= 0) continue;
    const d2 = dot(f,f) - tca*tca, rr = D2*D2;
    if (d2 >= rr) continue;
    const t = tca - Math.sqrt(rr - d2);
    if (t < 0.5) continue;
    if (!best || t < best.t) best = {t, ball:b};
  }
  return best;
}
function railHit(P, dir){
  let t = Infinity, n = null;
  const minX=BR, maxX=L-BR, minY=BR, maxY=W-BR;
  if (dir.x >  1e-9){ const q=(maxX-P.x)/dir.x; if(q<t){t=q; n={x:-1,y:0};} }
  if (dir.x < -1e-9){ const q=(minX-P.x)/dir.x; if(q<t){t=q; n={x: 1,y:0};} }
  if (dir.y >  1e-9){ const q=(maxY-P.y)/dir.y; if(q<t){t=q; n={x:0,y:-1};} }
  if (dir.y < -1e-9){ const q=(minY-P.y)/dir.y; if(q<t){t=q; n={x:0,y: 1};} }
  return isFinite(t) ? {t, n} : null;
}

function walk(st, res){
  let p = {...st.p}, dir = unit(st.dir), b = st.budget;
  let spin = st.spin, roll = st.roll;
  const ignore = new Set(st.ignore);
  ignore.add(st.movingId);
  let path = {pts:[{...p}], color:st.color, dashed:st.dashed, kind:st.kind};
  res.paths.push(path);

  for (let i = 0; i < MAX_EVENTS; i++){
    const rb = firstBall(p, dir, ignore);
    const rr = railHit(p, dir);
    const tEvt = Math.min(rb ? rb.t : Infinity, rr ? rr.t : Infinity);
    if (!isFinite(tEvt)) break;

    if (b <= tEvt){                                    /* la biglia si ferma prima */
      const q = add(p, mul(dir, b));
      path.pts.push(q); path.stopped = true;
      res.stops.push({p:q, color:st.color});
      return;
    }
    if (rb && rb.t <= (rr ? rr.t : Infinity)){         /* impatto su una biglia */
      const G = add(p, mul(dir, rb.t));                /* fantasma tangente */
      path.pts.push(G);
      res.ghosts.push(G);
      const u = unit(sub(rb.ball, G));
      const cosT = clamp1(dot(dir, u)), th = Math.acos(cosT);
      const rest = b - rb.t;
      if (st.depth === 0 && res.cut === null){
        res.cut = th*180/Math.PI;
        res.contact = add(rb.ball, mul(u, -BR));
        res.firstGhost = G;
      }
      if (st.depth < MAX_DEPTH)
        walk({p:{x:rb.ball.x,y:rb.ball.y}, dir:u, budget:rest*cosT*cosT*0.95,
              spin:0, roll:1, movingId:rb.ball.id, color:ballColor(rb.ball),
              dashed:false, kind:"obj", depth:st.depth+1, ignore}, res);

      const vT = Math.sin(th);
      const vP = (roll >= 0 ? K_FOLLOW : K_DRAW) * roll * cosT;
      const sp2 = vT*vT + vP*vP;
      if (sp2 < 0.0015 || rest*sp2 < 6){
        path.stopped = true; res.stops.push({p:G, color:st.color});
        return;
      }
      let t = sub(dir, mul(u, cosT));
      t = Math.hypot(t.x,t.y) < 1e-6 ? {x:-u.y, y:u.x} : unit(t);
      dir = unit(add(mul(t, vT), mul(u, vP)));
      b = rest * sp2;
      p = G; roll = 1;
      ignore.add(rb.ball.id);
      path = {pts:[{...G}], color:st.color, dashed:true, kind:st.kind};
      res.paths.push(path);
      continue;
    }
    /* sponda */
    const H = add(p, mul(dir, rr.t));
    const pk = pocketAt(H, 30);
    if (pk){ path.pts.push(pk); path.pocket = pk; res.pockets.push({p:pk, kind:st.kind}); return; }
    path.pts.push(H);
    b = (b - rr.t) * K_LOSS;
    const dn = dot(dir, rr.n);
    let r = {x:dir.x - 2*dn*rr.n.x, y:dir.y - 2*dn*rr.n.y};
    const k = K_RAIL * spin;                          /* Δv = -k·s·perp(n) */
    r = {x:r.x + k*rr.n.y, y:r.y - k*rr.n.x};
    dir = unit(r); p = H; spin *= K_DECAY; roll = 1;
    ignore.clear(); ignore.add(st.movingId);
    if (b < 4){ path.stopped = true; res.stops.push({p:H, color:st.color}); return; }
  }
}

/* mira effettiva, con aggancio alla buca entro ~2° */
function aimOf(sh){
  const cue = byId(sh.cueId);
  let d = unit(sub(sh.aim, cue));
  if (!state.pocketSnap || sh.noSnap) return d;
  const rb = firstBall(cue, d, new Set([cue.id]));
  if (!rb) return d;
  const B = rb.ball;
  let best = null;
  for (const P of POCKETS){
    const u = unit(sub(P, B));
    const G = add(B, mul(u, -D2));
    const cand = unit(sub(G, cue));
    if (dot(cand, u) < 0.09) continue;                 /* taglio troppo sottile */
    const ang = Math.acos(clamp1(dot(cand, d)));
    if (ang < 0.036 && (!best || ang < best.ang)) best = {ang, cand};
  }
  return best ? best.cand : d;
}

function simulate(sh){
  const cue = byId(sh.cueId);
  if (!cue) return null;
  const tip = sh.tip || {x:0,y:0};
  const res = {paths:[], ghosts:[], stops:[], pockets:[], cut:null,
               contact:null, firstGhost:null, cue, aim:aimOf(sh)};
  walk({p:{x:cue.x,y:cue.y}, dir:res.aim, budget:forceDist(sh.force),
        spin:tip.x/TIP_MAX, roll:tip.y/TIP_MAX, movingId:cue.id,
        color:theme().ink, dashed:false, kind:"cue", depth:0, ignore:new Set()}, res);
  return res;
}

/* ================================================================
   DISEGNO — TAVOLO
=================================================================*/
function rot(x,y){ return state.orient === "v" ? `rotate(-90 ${x} ${y})` : null; }

function drawTable(g){
  const th = theme();
  E("rect",{x:-PAD,y:-PAD,width:L+2*PAD,height:W+2*PAD,rx:16,fill:"#2a2118",stroke:"#160f0a","stroke-width":2},g);
  E("rect",{x:-RAIL-3,y:-RAIL-3,width:L+2*RAIL+6,height:W+2*RAIL+6,rx:8,fill:"#3a2c1f"},g);
  E("rect",{x:-2,y:-2,width:L+4,height:W+4,fill:th.cloth},g);
  E("rect",{x:-2,y:-2,width:L+4,height:W+4,fill:"#000",opacity:.06},g);
  const pk=(cx,cy,r)=>E("circle",{cx,cy,r,fill:"#0b0d0f"},g);
  pk(-10,-10,27); pk(L+10,-10,27); pk(-10,W+10,27); pk(L+10,W+10,27);
  pk(L/2,-14,25); pk(L/2,W+14,25);
  const cu=p=>E("polygon",{points:p.map(q=>q.join(",")).join(" "),
    fill:th.cush,stroke:th.edge,"stroke-width":1},g);
  const O=20,S=14;
  cu([[CORNER_CUT,0],[L/2-SIDE_CUT,0],[L/2-SIDE_CUT-S,-RAIL],[CORNER_CUT-O,-RAIL]]);
  cu([[L/2+SIDE_CUT,0],[L-CORNER_CUT,0],[L-CORNER_CUT+O,-RAIL],[L/2+SIDE_CUT+S,-RAIL]]);
  cu([[CORNER_CUT,W],[L/2-SIDE_CUT,W],[L/2-SIDE_CUT-S,W+RAIL],[CORNER_CUT-O,W+RAIL]]);
  cu([[L/2+SIDE_CUT,W],[L-CORNER_CUT,W],[L-CORNER_CUT+O,W+RAIL],[L/2+SIDE_CUT+S,W+RAIL]]);
  cu([[0,CORNER_CUT],[0,W-CORNER_CUT],[-RAIL,W-CORNER_CUT+O],[-RAIL,CORNER_CUT-O]]);
  cu([[L,CORNER_CUT],[L,W-CORNER_CUT],[L+RAIL,W-CORNER_CUT+O],[L+RAIL,CORNER_CUT-O]]);
  const dia=(cx,cy)=>E("polygon",{points:`${cx},${cy-5} ${cx+4},${cy} ${cx},${cy+5} ${cx-4},${cy}`,
    fill:"#f3ede2",opacity:.92},g);
  for(let k=1;k<=7;k++) if(k!==4){ dia(k*U,-RAIL/2); dia(k*U,W+RAIL/2); }
  for(let k=1;k<=3;k++){ dia(-RAIL/2,k*U); dia(L+RAIL/2,k*U); }
}
function drawGrid(g){
  const c = theme().grid;
  if (state.showSub){
    const p=[];
    for(let x=U/4;x<L;x+=U/4) if(x%U) p.push(`M${x} 0V${W}`);
    for(let y=U/4;y<W;y+=U/4) if(y%U) p.push(`M0 ${y}H${L}`);
    E("path",{d:p.join(" "),stroke:c,"stroke-width":.6,opacity:.22,fill:"none"},g);
  }
  if (state.showGrid){
    const p=[];
    for(let x=U;x<L;x+=U) p.push(`M${x} 0V${W}`);
    for(let y=U;y<W;y+=U) p.push(`M0 ${y}H${L}`);
    E("path",{d:p.join(" "),stroke:c,"stroke-width":1,opacity:.34,"stroke-dasharray":"5 5",fill:"none"},g);
  }
}
function drawMarks(g){
  const c = theme().grid;
  E("line",{x1:2*U,y1:0,x2:2*U,y2:W,stroke:c,"stroke-width":1.4,opacity:.5},g);
  E("line",{x1:2*U,y1:W/2,x2:L,y2:W/2,stroke:c,"stroke-width":.9,opacity:.28,"stroke-dasharray":"3 6"},g);
  [[2*U,W/2],[L/2,W/2],[6*U,W/2]].forEach(([x,y])=>E("circle",{cx:x,cy:y,r:3.4,fill:c,opacity:.8},g));
}
function ballSvg(g, kind, cx, cy, r){
  r = r || BR;
  if (kind === "ghost"){
    E("circle",{cx,cy,r:r-.6,fill:"#fff","fill-opacity":.14,stroke:theme().ink,
      "stroke-width":1.5,"stroke-dasharray":"3.2 3.2"},g);
    return;
  }
  E("ellipse",{cx:cx+1.1,cy:cy+1.8,rx:r,ry:r*.95,fill:"#000",opacity:.28},g);
  if (kind === "cue"){
    E("circle",{cx,cy,r,fill:"#fbfaf6",stroke:"#b9bdb8","stroke-width":.9},g);
    E("circle",{cx:cx-r*.3,cy:cy-r*.32,r:r*.3,fill:"#fff",opacity:.85},g);
    return;
  }
  const n=+kind, col=COLORS[(n-1)%8];
  if (n > 8){
    E("circle",{cx,cy,r,fill:"#fbfaf6",stroke:"#b9bdb8","stroke-width":.9},g);
    const h=r*.56, w=Math.sqrt(r*r-h*h);
    E("path",{d:`M${cx-w} ${cy-h}L${cx+w} ${cy-h}A${r} ${r} 0 0 1 ${cx+w} ${cy+h}`+
      `L${cx-w} ${cy+h}A${r} ${r} 0 0 1 ${cx-w} ${cy-h}Z`,fill:col},g);
  } else {
    E("circle",{cx,cy,r,fill:col,stroke:"rgba(0,0,0,.35)","stroke-width":.7},g);
  }
  E("circle",{cx:cx-r*.3,cy:cy-r*.34,r:r*.26,fill:"#fff",opacity:.28},g);
  const t=E("text",{x:cx,y:cy,dy:r*.38,"text-anchor":"middle",
    "font-family":"Arial, Helvetica, sans-serif","font-size":r*1.05,"font-weight":"700",
    fill:"#fff",stroke:"rgba(0,0,0,.45)","stroke-width":r*.06,"paint-order":"stroke",
    transform:rot(cx,cy)},g);
  t.textContent = kind;
}
function polyline(g, pts, o){
  if (!pts || pts.length < 2) return;
  const d = o.curve
    ? `M${pts[0].x} ${pts[0].y}Q${o.curve.x} ${o.curve.y} ${pts[1].x} ${pts[1].y}`
    : "M" + pts.map(p=>`${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join("L");
  if (o.halo) E("path",{d,fill:"none",stroke:"#f5c518","stroke-width":6,opacity:.45,
    "stroke-linecap":"round","stroke-linejoin":"round"},g);
  E("path",{d,fill:"none",stroke:o.color,"stroke-width":o.w||2.2,
    "stroke-linecap":"round","stroke-linejoin":"round",
    "stroke-dasharray":o.dashed?"8 6":null,opacity:o.opacity==null?1:o.opacity},g);
  if (o.arrow){
    const b = pts[pts.length-1];
    const a = o.curve ? o.curve : pts[pts.length-2];
    const an = Math.atan2(b.y-a.y, b.x-a.x), s = 9;
    E("polygon",{points:`${b.x},${b.y} ${b.x-s*Math.cos(an-.38)},${b.y-s*Math.sin(an-.38)} `+
      `${b.x-s*Math.cos(an+.38)},${b.y-s*Math.sin(an+.38)}`,fill:o.color,
      opacity:o.opacity==null?1:o.opacity},g);
  }
}
function stopMark(g, p, col, op){
  E("circle",{cx:p.x,cy:p.y,r:BR,fill:"none",stroke:col||theme().ink,
    "stroke-width":1.3,"stroke-dasharray":"2.6 2.6",opacity:op==null?.9:op},g);
}
function trimSeg(from, to, d){
  const m = dist(from,to); if (m < d+.5) return {...from};
  return {x:from.x+(to.x-from.x)*d/m, y:from.y+(to.y-from.y)*d/m};
}
function ballNear(p, id){
  let best=null;
  for (const it of state.items){
    if (it.type!=="ball" || it.id===id) continue;
    const d=dist(it,p); if (d<=BR+3 && (!best||d<best.d)) best={it,d};
  }
  return best && best.it;
}
function freeGeo(p){
  const pts = p.points.map(q=>({...q}));
  const n = pts.length;
  if (n < 2) return {pts, ghost:null};
  let ghost = null;
  const last = pts[n-1], dir = unit(sub(last, pts[n-2]));
  const hit = ballNear(last);
  if (p.ghostEnd){
    ghost = hit ? add(hit, mul(dir,-D2)) : {...last};
    pts[n-1] = trimSeg(ghost, pts[n-2], BR+1.5);
  } else if (hit){
    pts[n-1] = trimSeg({x:hit.x,y:hit.y}, pts[n-2], BR+1.5);
  }
  if (ballNear(pts[0])) pts[0] = trimSeg(pts[0], pts[1], BR+1.5);
  return {pts, ghost};
}
function cueStick(g, at, dir, elev, op){
  const len = 150*Math.cos(elev*Math.PI/180) + 26;
  const b = add(at, mul(dir, -(BR+4)));
  const e = add(at, mul(dir, -(BR+4+len)));
  const p = {x:-dir.y, y:dir.x};
  const pts = [add(b,mul(p,1.9)), add(b,mul(p,-1.9)), add(e,mul(p,-4.4)), add(e,mul(p,4.4))];
  E("polygon",{points:pts.map(q=>`${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(" "),
    fill:"#c9a163",stroke:"#5b4426","stroke-width":.8,opacity:op==null?.95:op},g);
  E("circle",{cx:b.x,cy:b.y,r:2.2,fill:"#2f6f9e",opacity:op==null?1:op},g);
}
function labelAt(g, x, y, txt, col, size){
  const t=E("text",{x,y,"text-anchor":"middle","font-family":"Arial, Helvetica, sans-serif",
    "font-size":size||12,"font-weight":"700",fill:col||"#f5c518",
    stroke:"rgba(0,0,0,.55)","stroke-width":2.4,"paint-order":"stroke",transform:rot(x,y)},g);
  t.textContent = txt;
}

function drawShot(g, sh, sel, forExport, index, many){
  const res = simulate(sh);
  if (!res) return;
  const op = sh.preview ? 0.85 : 1;
  const cue = res.cue;
  if (sh.showStick) cueStick(g, cue, res.aim, sh.elev, op*0.95);

  for (const path of res.paths){
    if (path.kind === "cue" && !sh.showPost && path.dashed) continue;
    if (path.kind === "obj" && !sh.showObj) continue;
    const pts = path.pts.slice();
    if (pts.length < 2) continue;
    pts[0] = trimSeg(pts[0], pts[1], BR+1.5);
    let curve = null;
    if (path.kind === "cue" && !path.dashed && Math.abs((sh.elev/60)*(sh.tip.x/TIP_MAX)) > 0.02
        && pts.length === 2){
      const sw = (sh.elev/60)*(sh.tip.x/TIP_MAX);
      const mid = mul(add(pts[0],pts[1]), .5);
      const pp = {x:-res.aim.y, y:res.aim.x};
      curve = add(mid, mul(pp, sw*dist(pts[0],pts[1])*0.44));
    }
    polyline(g, pts, {color:path.color, dashed:path.dashed, halo:sel,
      arrow:!path.stopped, opacity:op, curve, w:path.kind==="obj"?2.4:2.2});
  }
  for (const q of res.ghosts) ballSvg(g, "ghost", q.x, q.y);
  if (res.contact) E("circle",{cx:res.contact.x,cy:res.contact.y,r:2.4,fill:"#e63946"},g);
  for (const s of res.stops){
    if (s.color === theme().ink && !sh.showPost) continue;
    stopMark(g, s.p, s.color, op*0.9);
  }
  for (const p of res.pockets)
    if (p.kind === "cue") labelAt(g, p.p.x+(p.p.x<L/2?32:-32), p.p.y+(p.p.y<W/2?22:-14),
      "fallo", "#e63946", 12);

  if (sh.showAngle && res.cut !== null && res.firstGhost){
    const at = add(res.firstGhost, mul(res.aim, -34));
    labelAt(g, at.x, at.y, "taglio " + Math.round(res.cut) + "\u00B0", "#f5c518", 13);
  }
  if (many && res.firstGhost){
    const mid = mul(add(cue, res.firstGhost), .5);
    const pp = {x:-res.aim.y, y:res.aim.x};
    const at = add(mid, mul(pp, 15));
    E("circle",{cx:at.x,cy:at.y,r:9,fill:"#17181a",stroke:"#f5c518","stroke-width":1.2},g);
    const t=E("text",{x:at.x,y:at.y,dy:4,"text-anchor":"middle","font-size":11,"font-weight":"700",
      "font-family":"Arial, Helvetica, sans-serif",fill:"#f5c518",transform:rot(at.x,at.y)},g);
    t.textContent = index;
  }
}

/* ================================================================
   SCHEDA DEL TIRO (fuori dal tavolo)
=================================================================*/
function drawShotCard(root, sh, idx, x, y, sel){
  const g = E("g",{transform:`translate(${x} ${y})`}, root);
  E("rect",{x:0,y:0,width:CARD_W,height:CARD_H,rx:8,fill:"#17181a",
    stroke:sel?"#f5c518":"#39424d","stroke-width":sel?1.8:1.2},g);
  const T=(x,y,s,o)=>{const t=E("text",Object.assign({x,y,
    "font-family":"Arial, Helvetica, sans-serif","font-size":11,fill:"#8d97a3"},o||{}),g);
    t.textContent=s; return t;};
  T(12,20,T_("shotN","Tiro")+" "+idx,{fill:"#f5c518","font-weight":"700","font-size":12,"letter-spacing":"1"});

  const cx=46, cy=74, r=27, tip=sh.tip||{x:0,y:0};
  E("circle",{cx,cy,r,fill:"#fbfaf6",stroke:"#c9ccc8","stroke-width":1.2},g);
  E("line",{x1:cx-r,y1:cy,x2:cx+r,y2:cy,stroke:"#a9b0b7","stroke-width":.9},g);
  E("line",{x1:cx,y1:cy-r,x2:cx,y2:cy+r,stroke:"#a9b0b7","stroke-width":.9},g);
  E("circle",{cx,cy,r:r*TIP_MAX,fill:"none",stroke:"#a9b0b7","stroke-width":.8,"stroke-dasharray":"3 3"},g);
  E("circle",{cx:cx+tip.x*r,cy:cy-tip.y*r,r:5,fill:"#e63946",stroke:"#fff","stroke-width":1.6},g);
  T(cx,cy+r+13,"punto di impatto",{"text-anchor":"middle","font-size":9.5});

  const bedY=94, bx=100, bR=14, cB={x:bx+26,y:bedY-bR};
  E("line",{x1:bx,y1:bedY,x2:CARD_W-14,y2:bedY,stroke:"#3f4a55","stroke-width":2},g);
  E("circle",{cx:cB.x,cy:cB.y,r:bR,fill:"#fbfaf6",stroke:"#c9ccc8","stroke-width":1},g);
  const p0 = {x:cB.x-bR+1, y:cB.y-(tip.y||0)*bR*0.9};
  const a = sh.elev*Math.PI/180;
  const p1 = {x:p0.x - 74*Math.cos(a), y:p0.y - 74*Math.sin(a)};
  E("line",{x1:p0.x,y1:p0.y,x2:p0.x-74,y2:p0.y,stroke:"#4c5561","stroke-width":.9,"stroke-dasharray":"3 3"},g);
  E("line",{x1:p0.x,y1:p0.y,x2:p1.x,y2:p1.y,stroke:"#c9a163","stroke-width":3.4,"stroke-linecap":"round"},g);
  E("circle",{cx:p0.x,cy:p0.y,r:2.6,fill:"#2f6f9e"},g);
  T(CARD_W-14,26,sh.elev+"\u00B0 stecca",{"text-anchor":"end",fill:"#e8eaed","font-weight":"700","font-size":12});

  const f = sh.force==null?30:sh.force;
  T(12,CARD_H-12,T_("force","forza")+" · "+f+"% "+forceLabel(f),{fill:"#e8eaed","font-weight":"600","font-size":11.5});
  for (let i=1;i<=10;i++)
    E("rect",{x:CARD_W-14-(10-i+1)*10, y:CARD_H-21, width:7, height:10, rx:1.5,
      fill: i*10<=f ? "#f5c518" : "#333b45"},g);
}

/* ================================================================
   SCENA
=================================================================*/
function previewShot(){
  const a = state.aiming;
  const base = a.shotId ? byId(a.shotId) : state.shotDefaults;
  return Object.assign({}, base, {id:a.shotId||"__pv", type:"shot",
    cueId:a.cueId, aim:a.aim, noSnap:a.free, preview:true});
}
function effectiveShots(){
  const arr = state.items.filter(i=>i.type==="shot");
  if (state.aiming){
    const pv = previewShot();
    const i = arr.findIndex(s=>s.id===state.aiming.shotId);
    if (i >= 0) arr[i] = pv; else arr.push(pv);
  }
  return arr;
}
/* ---------- Il bersaglio (ADR-066) ----------
   L'unica voce della scena che il server legge come **dato**: centro, anelli
   di uguale spessore (`step`, in multipli di un quarto di diamante), valori dal
   centro verso l'esterno. Da qui nasce l'esecuzione colpo per colpo: il punto
   in cui si ferma la bianca prende i punti dell'anello in cui cade.
   La tinta è l'oro del canvas, a fasce sempre più tenui verso l'esterno: si
   deve leggere sopra ogni panno senza sembrare una bilia. */
const TARGET_GOLD = "201,168,76";
const TARGET_STEPS = [U/4, U/2, 3*U/4, U];
const TARGET_MAX_RINGS = 5;
function theTarget(){ return state.items.find(i=>i.type==="target") || null; }
function drawTarget(gTable, it, sel){
  const n = it.values.length;
  /* Ritagliato al panno: la bianca non si ferma sulle sponde, e un anello che
     le copre nasconde i diamanti. La selezione invece resta intera, fuori. */
  const clipId = "clothClip-" + it.id;
  const cp = E("clipPath",{id:clipId},gTable);
  E("rect",{x:0,y:0,width:L,height:W},cp);
  const g = E("g",{"clip-path":`url(#${clipId})`},gTable);
  for (let i=n-1;i>=0;i--){
    E("circle",{cx:it.x,cy:it.y,r:it.step*(i+1),
      fill:`rgba(${TARGET_GOLD},${(0.78 - 0.5*i/Math.max(1,n-1||1)).toFixed(2)})`,
      stroke:"rgba(0,0,0,.35)","stroke-width":.8},g);
  }
  for (let i=0;i<n;i++){
    /* Il valore sta a metà dello spessore del suo anello, sopra il centro; se
       lì finisce fuori dal panno passa sotto, perché il gruppo è ritagliato e
       un numero fuori sparirebbe — l'anello resterebbe senza il suo valore. */
    const off = it.step*(i+.5);
    let ry = i===0 ? it.y : it.y - off;
    if (i && ry < 8) ry = Math.min(W - 8, it.y + off);
    const t = E("text",{x:it.x,y:ry,dy:4,"text-anchor":"middle",
      "font-family":"Arial, Helvetica, sans-serif","font-size":i===0?13:11,"font-weight":"700",
      fill:"#1b2124",transform:rot(it.x,ry)},g);
    t.textContent = it.values[i];
  }
  if (sel) E("circle",{cx:it.x,cy:it.y,r:it.step*n+4,fill:"none",stroke:"#f5c518",
    "stroke-width":1.6,"stroke-dasharray":"3 3"},gTable);
}
function buildScene(o){
  o = o || {};
  const vert = state.orient === "v";
  const tw = vert ? W+2*PAD : L+2*PAD;
  const th = vert ? L+2*PAD : W+2*PAD;
  const minX = vert ? -(W+PAD) : -PAD;
  const minY = -PAD;

  const shots = effectiveShots();
  const cards = shots.filter(s=>s.showCard);
  const perRow = Math.max(1, Math.floor((tw-CARD_GAP)/(CARD_W+CARD_GAP)));
  const rows = cards.length ? Math.ceil(cards.length/perRow) : 0;
  const bandH = rows ? rows*(CARD_H+CARD_GAP)+CARD_GAP : 0;

  const svg = document.createElementNS(NS,"svg");
  svg.setAttribute("xmlns",NS);
  svg.setAttribute("viewBox", `${minX} ${minY} ${tw} ${th+bandH}`);
  const g = E("g",{transform: vert ? "rotate(90)" : null}, svg);

  drawTable(g);
  if (state.showMarks) drawMarks(g);
  if (o.forExport ? o.includeGrid : true) drawGrid(g);

  for (const it of state.items){
    if (it.type === "target") drawTarget(g, it, !o.forExport && state.sel === it.id);
  }
  for (const it of state.items){
    if (it.type !== "path") continue;
    const sel = !o.forExport && state.sel === it.id;
    const fg = freeGeo(it);
    if (fg.ghost) ballSvg(g,"ghost",fg.ghost.x,fg.ghost.y);
    polyline(g, fg.pts, {color:it.color, dashed:it.style==="dashed", arrow:it.arrow, halo:sel});
    if (sel) it.points.forEach(q=>E("circle",{cx:q.x,cy:q.y,r:4.5,fill:"#f5c518",
      stroke:"#17181a","stroke-width":1},g));
  }
  shots.forEach((sh,i)=>drawShot(g, sh, !o.forExport && state.sel===sh.id,
    o.forExport, i+1, shots.length>1));

  for (const it of state.items){
    const sel = !o.forExport && state.sel === it.id;
    if (it.type === "ball"){
      if (sel) E("circle",{cx:it.x,cy:it.y,r:BR+4,fill:"none",stroke:"#f5c518",
        "stroke-width":1.6,"stroke-dasharray":"3 3"},g);
      ballSvg(g,it.ball,it.x,it.y);
    } else if (it.type === "text"){
      if (sel) E("circle",{cx:it.x,cy:it.y,r:12,fill:"none",stroke:"#f5c518","stroke-width":1.4},g);
      const t=E("text",{x:it.x,y:it.y,dy:5,"text-anchor":"middle",
        "font-family":"Arial, Helvetica, sans-serif","font-size":18,"font-weight":"700",
        fill:theme().ink,stroke:"rgba(0,0,0,.5)","stroke-width":2.6,"paint-order":"stroke",
        transform:rot(it.x,it.y)},g);
      t.textContent = it.text;
    }
  }
  if (!o.forExport && state.draft){
    const pv = state.draft.points.concat(state.preview?[state.preview]:[]);
    polyline(g,pv,{color:state.lineColor,dashed:state.lineStyle==="dashed",
      arrow:state.lineArrow,opacity:.75});
    pv.forEach(q=>E("circle",{cx:q.x,cy:q.y,r:3.2,fill:"#f5c518"},g));
  }
  if (state.title){
    const bw = Math.max(80, state.title.length*9.4+24), bx = L-14-bw, by = 12;
    E("rect",{x:bx,y:by,width:bw,height:26,rx:4,fill:"#17181a",opacity:.88},g);
    const t=E("text",{x:bx+bw/2,y:by+18,"text-anchor":"middle",
      "font-family":"Arial, Helvetica, sans-serif","font-size":15,"font-weight":"700",
      fill:"#f5c518",transform:rot(bx+bw/2,by+13)},g);
    t.textContent = state.title;
  }
  if (rows){
    const band = E("g",{},svg);
    cards.forEach((sh,i)=>{
      const r = Math.floor(i/perRow), c = i%perRow;
      const inRow = Math.min(perRow, cards.length - r*perRow);
      const rowW = inRow*CARD_W + (inRow-1)*CARD_GAP;
      drawShotCard(band, sh, shots.indexOf(sh)+1,
        minX + (tw-rowW)/2 + c*(CARD_W+CARD_GAP),
        minY + th + CARD_GAP + r*(CARD_H+CARD_GAP),
        !o.forExport && (state.sel===sh.id || sh.preview));
    });
  }
  return {svg, g};
}

function render(){
  const {svg, g} = buildScene();
  svg.style.width = "100%"; svg.style.height = "100%";
  stage.replaceChildren(svg);
  gRoot = g;
  stage.className = "mode-" + state.tool;
  document.querySelectorAll("[data-tool]").forEach(b=>b.classList.toggle("on",b.dataset.tool===state.tool));
  document.querySelectorAll("[data-lstyle]").forEach(b=>b.classList.toggle("on",b.dataset.lstyle===state.lineStyle));
  $("#shotHint").textContent = state.tool!=="shot"
    ? T_("hintTool","Attiva Tiro: la traiettoria segue il puntatore e si ricalcola in tempo reale.")
    : state.aiming
      ? T_("hintAiming","Muovi per mirare. Premi e rilascia per fissare; tieni premuto e trascina per la mira fine. Esc annulla.")
      : T_("hintPick","Clicca la biglia da giocare per iniziare a mirare. Clicca un tiro esistente per correggerlo.");
  renderPalette(); renderTip(); syncShotControls(); syncTargetControls();
}

/* Il pannello del bersaglio: c'è un bersaglio solo, quindi lavora su quello
   senza bisogno che sia selezionato. Vuoto finché non lo si posa. */
function syncTargetControls(){
  const box = $("#targetControls"); if (!box) return;
  const tg = theTarget();
  box.hidden = !tg;
  const vuoto = $("#targetEmpty"); if (vuoto) vuoto.hidden = !!tg;
  if (!tg) return;
  $("#targetStep").value = String(tg.step);
  $("#targetRings").textContent = tg.values.length;
  const riga = $("#targetValues");
  if (riga.childElementCount !== tg.values.length){
    riga.replaceChildren(...tg.values.map((v,i)=>{
      const inp = document.createElement("input");
      inp.type="number"; inp.min="0"; inp.max="99"; inp.inputMode="numeric";
      inp.dataset.ring=i; inp.value=v;
      inp.onchange = ()=>{ const t=theTarget(); if(!t) return;
        const n = Math.max(0, Math.min(99, parseInt(inp.value,10)||0));
        push(); t.values[i]=n; render(); };
      return inp;
    }));
  } else {
    [...riga.children].forEach((inp,i)=>{ if (document.activeElement!==inp) inp.value=tg.values[i]; });
  }
}
function setTargetRings(delta){
  const tg = theTarget(); if (!tg) return;
  const n = tg.values.length + delta;
  if (n < 1 || n > TARGET_MAX_RINGS) return;
  push();
  /* L'anello nuovo vale uno meno del precedente, ma mai zero: un anello da
     zero punti è panno qualunque con un cerchio disegnato sopra. */
  if (delta > 0) tg.values.push(Math.max(1, tg.values[tg.values.length-1]-1));
  else tg.values.pop();
  render();
}

/* ================================================================
   PALETTE E CONTROLLI
=================================================================*/
const KINDS = ["cue","1","2","3","4","5","6","7","8","9","10","11","12","13","14","15","ghost"];
function renderPalette(){
  const box = $("#palette"); box.replaceChildren();
  KINDS.forEach(k=>{
    const b = document.createElement("button");
    b.className = "pball" + (state.armed===k?" armed":"") +
      (k!=="ghost" && state.items.some(i=>i.type==="ball"&&i.ball===k) ? " used":"");
    b.title = k==="cue" ? T_("ballCue","Battente")
            : k==="ghost" ? T_("ballGhost","Biglia fantasma")
            : T_("ballN","Biglia") + " " + k;
    const s = document.createElementNS(NS,"svg");
    s.setAttribute("viewBox","-12 -12 24 24");
    ballSvg(E("g",{},s), k, 0, 0, 10);
    b.appendChild(s);
    b.onclick = ()=>{ state.armed = state.armed===k?null:k; state.tool="select";
      state.aiming=null; render(); };
    box.appendChild(b);
  });
}
function activeShot(){
  if (state.aiming && state.aiming.shotId) return byId(state.aiming.shotId);
  const s = byId(state.sel); return s && s.type==="shot" ? s : null;
}
function shotProp(){ return activeShot() || state.shotDefaults; }

function renderTip(){
  const sv = $("#tipsvg"); sv.replaceChildren();
  const p = shotProp(), R = 42, t = p.tip;
  E("circle",{cx:0,cy:0,r:R,fill:"#fbfaf6",stroke:"#c9ccc8","stroke-width":1.2},sv);
  E("line",{x1:-R,y1:0,x2:R,y2:0,stroke:"#a9b0b7","stroke-width":1},sv);
  E("line",{x1:0,y1:-R,x2:0,y2:R,stroke:"#a9b0b7","stroke-width":1},sv);
  E("circle",{cx:0,cy:0,r:R*TIP_MAX,fill:"none",stroke:"#a9b0b7","stroke-width":1,"stroke-dasharray":"3 3"},sv);
  E("circle",{cx:t.x*R,cy:-t.y*R,r:7,fill:"#e63946",stroke:"#fff","stroke-width":2},sv);
  const lab=(x,y,s)=>{const e=E("text",{x,y,"text-anchor":"middle","font-size":8.5,
    fill:"#7c848c","font-family":"IBM Plex Sans, sans-serif"},sv); e.textContent=s;};
  lab(0,-R-4,T_("up","alto")); lab(0,R+10,T_("down","basso"));
  lab(-R-14,3,T_("leftShort","sx")); lab(R+14,3,T_("rightShort","dx"));
  const v = x => (Math.abs(x)/TIP_MAX).toFixed(1).replace(".0","");
  $("#tipinfo").innerHTML =
    `${T_("vertical","verticale")} <b>${t.y>0?T_("up","alto")+" "+v(t.y):t.y<0?T_("down","basso")+" "+v(t.y):T_("center","centro")}</b><br>`+
    `${T_("lateral","laterale")} <b>${t.x>0?T_("right","destro")+" "+v(t.x):t.x<0?T_("left","sinistro")+" "+v(t.x):T_("center","centro")}</b><br>`+
    `<span style="font-size:10.5px">${T_("spinMax","1 = massimo effetto utile")}</span>`;
}
(function tipDrag(){
  const sv = $("#tipsvg"); let on = false;
  const set = ev=>{
    const r = sv.getBoundingClientRect(), s = r.width/104, R = 42;
    let x =  (ev.clientX-r.left-r.width/2)/(R*s);
    let y = -(ev.clientY-r.top -r.height/2)/(R*s);
    const m = Math.hypot(x,y);
    if (m > 0.9){ x = x/m*0.9; y = y/m*0.9; }
    const q = v => Math.abs(v)<0.06 ? 0 : Math.round(v*20)/20;
    setShotProp("tip", {x:q(x), y:q(y)});
  };
  sv.addEventListener("pointerdown",e=>{on=true; sv.setPointerCapture(e.pointerId); set(e);});
  sv.addEventListener("pointermove",e=>{ if(on) set(e); });
  sv.addEventListener("pointerup",()=>{on=false;});
  sv.addEventListener("pointercancel",()=>{on=false;});
})();

const fp = $("#forcePresets");
FORCE_PRESETS.forEach(p=>{
  const b=document.createElement("button");
  b.className="btn sm wide"; b.textContent=p.l; b.dataset.force=p.v;
  b.onclick=()=>{ $("#force").value=p.v; setShotProp("force",p.v); };
  fp.appendChild(b);
});
function syncShotControls(){
  const p = shotProp();
  $("#elev").value = p.elev; $("#elevVal").textContent = p.elev+"\u00B0";
  const f = p.force==null?30:p.force;
  $("#force").value = f; $("#forceVal").textContent = f+"% · "+forceLabel(f);
  document.querySelectorAll("#forcePresets .btn").forEach(b=>
    b.classList.toggle("on", +b.dataset.force === f));
  $("#showPost").checked = p.showPost; $("#showObj").checked = p.showObj;
  $("#showStick").checked = p.showStick; $("#showCard").checked = p.showCard;
  $("#showAngle").checked = p.showAngle;
}
function setShotProp(k, v){
  const sh = activeShot();
  if (sh){ if(!state.aiming) push(); sh[k] = v; } else state.shotDefaults[k] = v;
  render();
}

/* ================================================================
   STORICO
=================================================================*/
const snapState = ()=>JSON.stringify({items:state.items, title:state.title});
function push(){ history.push(snapState()); if(history.length>80) history.shift(); future=[]; }
function restore(s){ const d=JSON.parse(s); state.items=d.items; state.title=d.title;
  $("#titleInput").value=d.title||""; state.sel=null; state.aiming=null; render(); }
function undo(){ if(!history.length) return; future.push(snapState()); restore(history.pop()); }
function redo(){ if(!future.length) return; history.push(snapState()); restore(future.pop()); }

/* ================================================================
   INTERAZIONE
=================================================================*/
function toTable(ev){
  const svg = stage.querySelector("svg");
  const pt = svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY;
  const p = pt.matrixTransform(gRoot.getScreenCTM().inverse());
  return {x:p.x, y:p.y};
}
function segDist(p,a,b){
  const dx=b.x-a.x, dy=b.y-a.y, l2=dx*dx+dy*dy;
  if(!l2) return dist(p,a);
  let t=((p.x-a.x)*dx+(p.y-a.y)*dy)/l2; t=Math.max(0,Math.min(1,t));
  return Math.hypot(p.x-(a.x+t*dx), p.y-(a.y+t*dy));
}
function nearPoly(p, pts, tol){
  if (!pts) return false;
  for(let i=0;i<pts.length-1;i++) if(segDist(p,pts[i],pts[i+1])<=tol) return true;
  return false;
}
function shotHit(p, sh){
  const res = simulate(sh); if(!res) return false;
  return res.paths.some(path=>nearPoly(p, path.pts, 6));
}
function hit(p){
  const viaBersaglio = ()=>{
    const tg = theTarget();
    return tg && dist(tg,p) <= tg.step*tg.values.length ? {it:tg} : null;
  };
  const trovato = hitItems(p);
  return trovato || viaBersaglio();
}
function hitItems(p){
  for (let i=state.items.length-1;i>=0;i--){
    const it = state.items[i];
    if (it.type==="ball" && dist(it,p)<=BR+3) return {it};
    if (it.type==="text" && dist(it,p)<=13) return {it};
    if (it.type==="path"){
      for(let v=0;v<it.points.length;v++) if(dist(it.points[v],p)<=7) return {it,vertex:v};
      if (nearPoly(p,it.points,6)) return {it};
    }
    if (it.type==="shot" && shotHit(p,it)) return {it};
  }
  return null;
}
function ballHit(p){
  for (let i=state.items.length-1;i>=0;i--){
    const it=state.items[i];
    if (it.type==="ball" && it.ball!=="ghost" && dist(it,p)<=BR+4) return it;
  }
  return null;
}

stage.addEventListener("pointerdown", ev=>{
  if (!gRoot) return;
  altDown = ev.altKey;
  const raw = toTable(ev);
  if (ev.button === 2){ ev.preventDefault();
    if (state.draft) finishLine();
    else if (state.aiming){ state.aiming=null; render(); }
    return; }

  if (state.tool === "shot"){
    if (state.aiming){                    /* premuta: mira fine, si fissa al rilascio */
      state.aiming.hold = true;
      state.aiming.down = raw;
      state.aiming.aim = clampPt(raw);
      render(); return;
    }
    const b = ballHit(raw);
    if (b){ state.aiming = {shotId:null, cueId:b.id, aim:clampPt(raw), hold:false, free:false};
      state.sel=null; render(); return; }
    const sh = state.items.slice().reverse().find(i=>i.type==="shot" && shotHit(raw,i));
    if (sh){ push();
      state.aiming = {shotId:sh.id, cueId:sh.cueId, aim:clampPt(raw), hold:false, free:false};
      state.sel = sh.id; render(); return; }
    toast(T_("toastPickBall","Clicca una biglia per iniziare a mirare"));
    return;
  }

  if (state.tool === "line"){
    const p = clampPt(snapPoint(raw));
    if (!state.draft) state.draft = {points:[p]};
    else {
      const last = state.draft.points[state.draft.points.length-1];
      if (dist(last,p) < 9) return finishLine();
      state.draft.points.push(p);
    }
    render(); return;
  }
  if (state.tool === "target"){
    push();
    const dove = clampPt(snapPoint(raw,{toBalls:false}));
    let tg = theTarget();
    if (tg) Object.assign(tg, dove);
    else { tg = {id:uid(),type:"target",step:U/2,values:[3,2,1],...dove}; state.items.push(tg); }
    state.sel = tg.id; state.tool = "select"; render(); return;
  }
  if (state.tool === "text"){
    const t = prompt(T_("textNew","Testo da inserire:"));
    if (t){ push(); state.items.push({id:uid(),type:"text",text:t,...clampPt(snapPoint(raw,{toBalls:false}))}); }
    state.tool = "select"; render(); return;
  }
  if (state.armed){
    push();
    const k = state.armed;
    if (k !== "ghost") state.items = state.items.filter(i=>!(i.type==="ball"&&i.ball===k));
    state.items.push({id:uid(),type:"ball",ball:k,...snapBall(raw)});
    state.armed = null; state.sel = null; render(); return;
  }

  const h = hit(raw);
  if (h){
    state.sel = h.it.id;
    state.drag = {id:h.it.id, vertex:h.vertex, handle:h.handle, start:raw, moved:false,
                  orig:JSON.parse(JSON.stringify(h.it))};
    push();
  } else state.sel = null;
  render();
});

window.addEventListener("pointermove", ev=>{
  altDown = ev.altKey;
  if (!gRoot) return;
  if (state.tool === "shot" && state.aiming){
    const a = state.aiming, p = clampPt(toTable(ev));
    if (a.hold && a.down && dist(p, a.down) > 2) a.free = true;
    a.aim = p; render(); return;
  }
  if (state.tool==="line" && state.draft){
    state.preview = clampPt(snapPoint(toTable(ev))); render(); return;
  }
  if (!state.drag) return;
  const p = toTable(ev), d = state.drag, it = byId(d.id);
  if (!it) return;
  d.moved = true;
  if (it.type==="ball") Object.assign(it, snapBall(p, it.id));
  else if (it.type==="text" || it.type==="target") Object.assign(it, clampPt(snapPoint(p,{toBalls:false})));
  else if (it.type==="shot") return;
  else if (d.vertex !== undefined) it.points[d.vertex] = clampPt(snapPoint(p));
  else {
    const dx = p.x-d.start.x, dy = p.y-d.start.y;
    it.points = d.orig.points.map(q=>clampPt({x:q.x+dx, y:q.y+dy}));
  }
  render();
});
window.addEventListener("pointerup", ()=>{
  if (state.aiming && state.aiming.hold){          /* fissa il tiro */
    const a = state.aiming;
    if (a.shotId){
      const sh = byId(a.shotId);
      if (sh){ sh.aim = {...a.aim}; sh.noSnap = a.free; }
      state.sel = a.shotId;
    } else {
      push();
      const d = state.shotDefaults;
      const sh = {id:uid(), type:"shot", cueId:a.cueId, aim:{...a.aim}, noSnap:a.free,
        tip:{...d.tip}, elev:d.elev, force:d.force, showPost:d.showPost,
        showObj:d.showObj, showStick:d.showStick, showCard:d.showCard, showAngle:d.showAngle};
      state.items.push(sh); state.sel = sh.id;
    }
    state.aiming = null; render();
  }
  if (state.drag && !state.drag.moved) history.pop();
  state.drag = null;
});
stage.addEventListener("dblclick", ev=>{
  ev.preventDefault();
  if (state.draft) return finishLine();
  const h = hit(toTable(ev));
  if (h && h.it.type==="text"){
    const t = prompt(T_("textEdit","Testo:"), h.it.text);
    if (t !== null){ push(); h.it.text = t; render(); }
  }
});
stage.addEventListener("contextmenu", e=>e.preventDefault());

function finishLine(){
  if (state.draft && state.draft.points.length >= 2){
    push();
    state.items.push({id:uid(),type:"path",points:state.draft.points,
      color:state.lineColor,style:state.lineStyle,arrow:state.lineArrow,ghostEnd:state.lineGhost});
  }
  state.draft = null; state.preview = null; render();
}
function removeSel(){
  const it = byId(state.sel); if (!it) return;
  push();
  state.items = state.items.filter(i=>i.id!==it.id);
  if (it.type==="ball")
    state.items = state.items.filter(i=>!(i.type==="shot" && i.cueId===it.id));
  state.sel = null; render();
}
window.addEventListener("keydown", ev=>{
  if (["INPUT","SELECT","TEXTAREA"].includes(ev.target.tagName)) return;
  if (ev.key === "Alt") altDown = true;
  if (ev.key === "Escape"){ state.draft=null; state.preview=null; state.sel=null;
    state.armed=null; state.aiming=null; render(); }
  if (ev.key === "Enter" && state.draft) finishLine();
  if ((ev.key==="Delete"||ev.key==="Backspace") && state.sel){ ev.preventDefault(); removeSel(); }
  if ((ev.ctrlKey||ev.metaKey) && ev.key.toLowerCase()==="z"){ ev.preventDefault(); ev.shiftKey?redo():undo(); }
  if ((ev.ctrlKey||ev.metaKey) && ev.key.toLowerCase()==="y"){ ev.preventDefault(); redo(); }
});
window.addEventListener("keyup", ev=>{ if(ev.key==="Alt") altDown=false; });

/* ================================================================
   PRESET
=================================================================*/
function rack(order){
  const dx = D2*Math.cos(Math.PI/6), apex = {x:6*U, y:W/2}, out = [];
  order.forEach((row,i)=>row.forEach((n,j)=>out.push({id:uid(),type:"ball",ball:String(n),
    x:apex.x+i*dx, y:apex.y+(j-(row.length-1)/2)*D2})));
  return out;
}
const RACKS = {
  rack9:[[1],[2,3],[4,9,5],[6,7],[8]],
  rack10:[[1],[2,3],[4,10,5],[6,7,8,9]],
  rack8:[[1],[9,2],[10,8,3],[11,4,12,5],[6,13,7,14,15]]
};
function preset(k){
  push(); state.sel=null; state.draft=null; state.aiming=null;
  if (k==="clear") state.items = [];
  else if (RACKS[k]) state.items = rack(RACKS[k]);
  else if (k==="break9"){
    state.items = rack(RACKS.rack9);
    const cue = {id:uid(),type:"ball",ball:"cue",x:U,y:W/2-U/2};
    state.items.push(cue);
    state.items.push({id:uid(),type:"shot",cueId:cue.id,aim:{x:6*U,y:W/2},
      tip:{x:0,y:0},elev:0,force:100,showPost:true,showObj:true,
      showStick:true,showCard:true,showAngle:false});
  }
  else if (k==="wagon"){
    state.items=[{id:uid(),type:"ball",ball:"1",x:6*U,y:W/2}];
    for(let i=0;i<7;i++){
      const a=Math.PI*(0.62+i*0.13);
      state.items.push({id:uid(),type:"ball",ball:"ghost",
        ...clampBall({x:6*U+250*Math.cos(a), y:W/2+250*Math.sin(a)})});
    }
  }
  else if (k==="line"){
    state.items=[{id:uid(),type:"ball",ball:"cue",x:U,y:W/2}];
    [3,4,5,6,7].forEach((d,i)=>state.items.push({id:uid(),type:"ball",ball:String(i+1),x:d*U,y:W/2}));
  }
  else if (k==="lshape"){
    state.items=[{id:uid(),type:"ball",ball:"cue",x:2*U,y:3*U}];
    [1,2,3].forEach((n,i)=>state.items.push({id:uid(),type:"ball",ball:String(n),x:(3+i)*U,y:BR}));
    [4,5,6].forEach((n,i)=>state.items.push({id:uid(),type:"ball",ball:String(n),x:L-BR,y:(1+i)*U}));
  }
  render();
}

/* ================================================================
   AVVISI

   `download`/`exportImage` del tool autonomo non ci sono piu': qui il builder
   e' dentro l'applicazione e serve a mettere il drill nel catalogo, non a
   produrre file. L'immagine la costruisce `DrillBuilder.png()` in fondo, e
   finisce al server invece che nei download.
=================================================================*/
function toast(m){ const t=$("#toast"); t.textContent=m; t.classList.add("show");
  clearTimeout(toast._t); toast._t=setTimeout(()=>t.classList.remove("show"),1900); }

/* ================================================================
   UI
=================================================================*/
document.querySelectorAll("[data-tool]").forEach(b=>b.onclick=()=>{
  state.tool=b.dataset.tool; state.armed=null; state.aiming=null;
  if(state.tool!=="line"){ state.draft=null; state.preview=null; }
  render();
});
document.querySelectorAll("[data-lstyle]").forEach(b=>b.onclick=()=>{state.lineStyle=b.dataset.lstyle;render();});
document.querySelectorAll("[data-preset]").forEach(b=>b.onclick=()=>preset(b.dataset.preset));
const sw=$("#swatches");
LINE_COLORS.forEach(c=>{
  const b=document.createElement("button");
  b.className="sw"+(c===state.lineColor?" on":""); b.style.background=c; b.title=c;
  b.onclick=()=>{state.lineColor=c; sw.querySelectorAll(".sw").forEach(x=>x.classList.remove("on")); b.classList.add("on");};
  sw.appendChild(b);
});
const cl=$("#cloths");
Object.keys(CLOTHS).forEach(k=>{
  const b=document.createElement("button");
  b.className="cl"+(k===state.cloth?" on":""); b.style.background=CLOTHS[k].cloth; b.title=k;
  b.onclick=()=>{ state.cloth=k;
    cl.querySelectorAll(".cl").forEach(x=>x.classList.remove("on")); b.classList.add("on");
    state.lineColor = CLOTHS[k].ink;
    sw.querySelectorAll(".sw").forEach(x=>x.classList.remove("on"));
    render(); };
  cl.appendChild(b);
});
$("#undo").onclick=undo; $("#redo").onclick=redo; $("#del").onclick=removeSel;
if ($("#targetStep")){
  $("#targetStep").onchange = e=>{ const tg=theTarget(); if(!tg) return;
    const s = +e.target.value; if (!TARGET_STEPS.includes(s)) return;
    push(); tg.step = s; render(); };
  $("#targetMinus").onclick = ()=>setTargetRings(-1);
  $("#targetPlus").onclick  = ()=>setTargetRings(1);
  $("#targetRemove").onclick = ()=>{ const tg=theTarget(); if(!tg) return;
    push(); state.items = state.items.filter(i=>i!==tg); state.sel=null; render(); };
}
$("#finishLine").onclick=finishLine;
$("#elev").oninput  = e=>{ $("#elevVal").textContent=e.target.value+"\u00B0"; setShotProp("elev",+e.target.value); };
$("#force").oninput = e=>{ const f=+e.target.value;
  $("#forceVal").textContent=f+"% · "+forceLabel(f); setShotProp("force",f); };
$("#pocketSnap").onchange = e=>{ state.pocketSnap=e.target.checked; render(); };
$("#showPost").onchange = e=>setShotProp("showPost",e.target.checked);
$("#showObj").onchange  = e=>setShotProp("showObj",e.target.checked);
$("#showStick").onchange= e=>setShotProp("showStick",e.target.checked);
$("#showCard").onchange = e=>setShotProp("showCard",e.target.checked);
$("#showAngle").onchange= e=>setShotProp("showAngle",e.target.checked);
$("#magnets").onchange  = e=>{ state.magnets=e.target.checked; };
$("#ballScale").onchange= e=>{ setBallScale(+e.target.value); render(); };
$("#showGrid").onchange = e=>{ state.showGrid=e.target.checked; render(); };
$("#showSub").onchange  = e=>{ state.showSub=e.target.checked; render(); };
$("#showMarks").onchange= e=>{ state.showMarks=e.target.checked; render(); };
$("#snapSel").onchange  = e=>{ state.snap=e.target.value; };
$("#orientSel").onchange= e=>{ state.orient=e.target.value; render(); };
$("#titleInput").oninput= e=>{ state.title=e.target.value; render(); };
$("#lineArrow").onchange= e=>{ state.lineArrow=e.target.checked; };
$("#lineGhost").onchange= e=>{ state.lineGhost=e.target.checked; };
function applyScene(d){
  state.items=(d.items||[]).map(i=>{
        if(i.type==="shot"){
          if(i.aim==null && i.target) i.aim = i.target;      /* file vecchi */
          if(i.force==null) i.force = 30;
          else if(i.force<=10) i.force = Math.round(i.force*10);
          if(i.showCard==null) i.showCard=true;
        }
    return i;
  }).filter(i=>i.type!=="shot" || i.aim);
  state.title=d.title||""; state.orient=d.orient||"h";
  state.cloth=d.cloth||"blu"; setBallScale(d.ballScale||1);
  $("#titleInput").value=state.title; $("#orientSel").value=state.orient;
  $("#ballScale").value=state.ballScale;
  cl.querySelectorAll(".cl").forEach((x,i)=>
    x.classList.toggle("on", Object.keys(CLOTHS)[i]===state.cloth));
  render();
}

render();

/* ================================================================
   INTERFACCIA VERSO L'APP

   Il builder resta un tool autonomo — sa di bilie, non di drill salvati. Da
   qui l'app prende le due cose che le servono, e nient'altro: la **scena**,
   con cui si potra' riaprire il disegno, e l'**immagine**, con cui lo si
   mostra ovunque. Sono mestieri diversi: da un PNG non si torna alle bilie, e
   una scena non entra in un `<img>`.
=================================================================*/
window.DrillBuilder = {
  /* La scena nel formato che il server sa rileggere (`parse_scene`). */
  scene(){
    return {v:4, title:state.title, orient:state.orient,
            cloth:state.cloth, ballScale:state.ballScale, items:state.items};
  },

  /* Vuoto = niente da salvare. Serve a non far partire una richiesta che il
     server rifiuterebbe, e a dirlo con parole invece che con un errore. */
  isEmpty(){ return !state.items.length; },

  /* Ricarica un disegno gia' salvato. Passa dalla stessa `applyScene` del
     caricamento da file: i campi mancanti e i formati vecchi si sistemano in
     un posto solo. */
  load(scene){ try{ applyScene(scene); return true; }catch(e){ return false; } },

  /* Il PNG, come blob. Ricalca l'esportazione: la mira in corso si toglie
     prima dello scatto, altrimenti l'immagine salvata mostrerebbe una freccia
     di lavoro che nel drill non c'e'. */
  png(scale, cb){
    const keep = state.aiming; state.aiming = null;
    const {svg} = buildScene({forExport:true, includeGrid:false});
    state.aiming = keep;
    const vb = svg.getAttribute("viewBox").split(" ").map(Number);
    const w = Math.round(vb[2]*(scale||2)), h = Math.round(vb[3]*(scale||2));
    svg.setAttribute("width",w); svg.setAttribute("height",h);
    const img = new Image();
    img.onload = ()=>{
      const c=document.createElement("canvas"); c.width=w; c.height=h;
      const ctx=c.getContext("2d");
      ctx.fillStyle="#fff"; ctx.fillRect(0,0,w,h);   /* JPEG non ha trasparenza */
      ctx.drawImage(img,0,0,w,h);
      c.toBlob(b=>cb(b), "image/jpeg", .92);
    };
    img.onerror = ()=>cb(null);
    img.src = "data:image/svg+xml;charset=utf-8," +
      encodeURIComponent(new XMLSerializer().serializeToString(svg));
  }
};
