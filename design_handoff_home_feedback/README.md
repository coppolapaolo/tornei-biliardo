# Handoff: blocco di feedback attività nella home del giocatore

## Overview
La home del giocatore (`templates/dashboard/player.html`, ruolo `player`) oggi mostra solo cose da fare: match in corso, gare, campionati, gare vicine. Un giocatore che rientra non riceve nessun segnale sul proprio andamento.

Questo handoff descrive un blocco **"Come stai andando"** da inserire in cima al contenuto della dashboard (subito dopo il saluto "Ciao <username>", **prima** di "I tuoi match"), che dà feedback positivo e verificabile sull'attività svolta: Elo, TPA, forma recente, streak, drill, posizione in campionato, livello/XP.

Vincoli decisi con il committente:
- **Non deve nascondere le attività da svolgere.** Il blocco è una card compatta; chiuso occupa ~330–360px in altezza su mobile.
- **Espandibile**, chiuso per default, lo stato di apertura vale **solo per la sessione** (`sessionStorage`, non `localStorage`).
- **Nessuna CTA** dentro il blocco: è puro feedback. I bottoni restano nelle sezioni sotto.
- **Tono incoraggiante ma factual**: nessun numero inventato, nessun grafico finto quando i dati non ci sono.
- **Finestra di calcolo: ultime 10 attività** (non "ultimi 30 giorni").
- **Se l'Elo cala, il calo si mostra in chiaro**, senza allarmi: colore ambra (non rosso), e accanto una metrica vera in crescita.
- Vista di riferimento: **mobile 390px**.

## About the Design Files
`Home Giocatore.dc.html` è un **riferimento di design realizzato in HTML**, non codice di produzione da copiare. È un prototipo che mostra aspetto e comportamento voluti.

Il lavoro da fare è **ricreare questi design nell'ambiente esistente del progetto**: Flask + Jinja2 + template `templates/`, CSS del design system 7c già presente in `static/css/` (`tokens-7c.css`, `theme-7c.css`, `gamification.css`), Vanilla JS. Va scritto un partial Jinja nuovo (es. `templates/components/_player_activity_feedback.html`) usando le classi/token 7c esistenti, **non** inline styles come nel prototipo: gli stili inline nel file di design servono solo al prototipo.

Il file si apre in un browser (serve `support.js` accanto). È strutturato in 4 "turni" di esplorazione; conta solo il turno più recente per ogni variante — la direzione approvata è **2a** e le sue declinazioni adattive.

## Fidelity
**High-fidelity.** Colori, tipografia, spaziature, raggi e stati sono definitivi e vanno riprodotti fedelmente, ma **usando i token e le classi 7c del progetto** (i valori sotto corrispondono a quei token). Il layout mobile a 390px è quello da rispettare; su desktop la card segue il contenitore della dashboard.

## Direzione approvata: 2a
Card chiara (`--c7-surface`) con questa impalcatura fissa, uguale in tutte le casistiche:

1. **Titolo** "Come stai andando" (17px/800), a destra un badge opzionale di contesto.
2. **Due metriche** in griglia 1fr 1fr: numero grande mono 30px + etichetta 11px + delta 12px. Una delle due celle può essere una **torta** (anello) con legenda.
3. **Grafico dell'attività dominante** in un riquadro `--c7-bg` r18, altezza 66px, con due caption mono 11px agli estremi (valore iniziale / valore attuale).
4. **Striscia delle ultime attività**: 4–12 tessere `flex: 1`, h30 r9, con dentro il dato dell'attività (punteggio, piazzamento, nome drill); label 11px sopra a sinistra e nota a destra.
5. **Bottone di espansione** full-width h40 r12 su `--c7-bg`, con chevron che si gira (`fa-chevron-down` → `fa-chevron-up`).
6. **Espansione**: UNA card `--c7-bg` r22 con righe divise da `1px solid #D3D8D7` (pattern "elenco compatto = una card, N righe" già usato nel progetto), 3–4 righe con icona 15px, titolo 14px/800, sottotitolo 11px/700 grigio.

## Regola di adattività (il cuore dell'implementazione)
Il blocco si adatta a **quali attività il giocatore ha effettivamente svolto**. Nessuno slot vuoto, nessun placeholder: se una metrica non esiste, la griglia si stringe e il posto lo prende la metrica successiva disponibile.

Priorità della **metrica primaria** (cella 1) e del **grafico** (l'attività dominante = quella con più eventi nella finestra delle ultime 10 attività; a parità, la più recente):

| Profilo | Metrica 1 | Metrica 2 | Grafico | Striscia |
| --- | --- | --- | --- | --- |
| Ha match/gare con rack registrati (tutto attivo) | Elo + delta | TPA carriera + delta | Sparkline Elo + linea TPA tratteggiata, con legenda | Mista: punteggi, piazzamenti, icona bersaglio per i drill |
| Solo Elo (partite senza rack, nessun drill) | Elo + delta | Torta partite vinte (V/N/P) | Sparkline Elo con i punti visibili | Punteggi dei match, colorati per esito |
| Solo drill | Punteggio drill `78/100` | Torta drill superati | Barre delle sessioni | Nome del drill |
| Solo gare/campionato | Elo gara | Posizione in campionato | Sparkline Elo sulle gare | Piazzamento (`5°`, `1°`) |
| Direttore di gara | Gare organizzate | Torta riempimento medio | Barre iscritti per gara | Posti riempiti `22/24` |
| Super attivo (>30 attività/mese) | Elo (delta piccolo, dire "massimo") | TPA ("stabile") | Sparkline densa | 12 tessere **senza testo**, con legenda conteggi sotto |
| Rientro dopo pausa (>4 settimane) | Elo "invariato" | Match giocati | Sparkline che si ferma e prosegue **tratteggiata** fino a oggi, cerchio vuoto sull'ultimo punto | Ultime partite dell'ultimo periodo attivo |
| In calo | Elo con delta negativo **ambra** | La metrica vera in crescita (TPA) in verde | Linea grigia con gli **ultimi 3 segmenti** in scuro spesso 2.5 se sta risalendo | Punteggi, colorati per esito |
| Appena iscritto (0 attività) | — | — | — | — |

**Appena iscritto**: il blocco di feedback **non viene renderizzato**. Al suo posto una card di setup: anello `1/3`, titolo "Il tuo profilo è pronto", sottotitolo "Fai la prima attività e qui comparirà il tuo andamento", e la card-elenco con 3 step (fatto = `fa-check` verde, da fare = `far fa-circle` grigio). Sopra, sotto il saluto, una riga: "Il tuo Elo parte da 1200: si muove alla prima partita registrata."

**Direttore di gara**: titolo diverso, "Come vanno le tue gare", e badge rosso "N da chiudere" se ci sono gare/referti pendenti — l'operatività resta prioritaria sul feedback.

## Screens / Views
Tutte le viste sono la **stessa** dashboard giocatore; cambia solo il blocco. Riferimenti nel file di design (link `#id`):

- `#2a` — solo Elo, 5 partite giocate (**direzione approvata, caso base**)
- `#3a` solo drill · `#3b` solo gare · `#3c` tutto attivo · `#3d` rientro dopo pausa
- `#4a` direttore di gara · `#4b` super attivo · `#4c` appena iscritto · `#4d` in calo
- `#1b`, `#1c` — direzioni precedenti (card chiara con 3 metriche; riga sottile). Utili solo come storia; **non implementare**.
- il primo frame del turno 1 è la ricostruzione della home **attuale**, utile per confrontare prima/dopo.

### Blocco chiuso — misure esatte (caso `#2a`)
- Card: `background #F5F7F6`, `border-radius 26px`, `padding 20px`, larghezza piena della colonna dashboard (a 390px di viewport: 18px di padding laterale nel `main`).
- Titolo: Manrope 17px/800, `letter-spacing -.02em`, colore `#1B2124`.
- Badge di contesto (opzionale): h24, `padding 0 10px`, r999, 10px/800, `letter-spacing .04em`, uppercase, `white-space: nowrap`. Varianti: neutro `#E4E8E7`/`#6B7679`, positivo `#E4EDE9`/`#1D5F4A`, urgente `#F3E2E0`/`#8A2C2C`.
- Griglia metriche: `display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px`.
  - Numero: JetBrains Mono 30px/800, `letter-spacing -.035em`, `line-height 1`. Suffissi minori (`/100`) 18px in `#6B7679`.
  - Etichetta: 11px/700 `#6B7679`, `margin-top 5px`.
  - Delta: 12px/700, `margin-top 2px`; la cifra in mono. Verde `#2C8A6B` se positivo, ambra `#8A6A1F` se negativo, `#6B7679` se neutro/stabile.
  - Torta: `width/height 58px`, `border-radius 50%`, `background conic-gradient(#2C8A6B 0 60%, #C9CFCE 0 80%, #B23B3B 0)` (verde vinte, grigio pari, rosso perse), foro `position:absolute; inset:9px; border-radius:50%; background:#F5F7F6`, al centro mono 14px/800 (`3/5`). Legenda a destra: righe 11px/700 con quadratino 8×8 r2, `white-space: nowrap` (etichette corte: "3 vinte", "1 pari", "1 persa", "2 falliti").
- Riquadro grafico: `margin-top 18px`, `background #E4E8E7`, `border-radius 18px`, `padding 14px 14px 10px`.
  - Sparkline: `<svg viewBox="0 0 130 34" preserveAspectRatio="none">`, altezza 66px, `overflow: visible`. Area `fill rgba(44,74,82,.10)`, linea `stroke #2C4A52`, `stroke-width 2`, `stroke-linecap/linejoin round`, **`vector-effect="non-scaling-stroke"`** (obbligatorio: senza, `preserveAspectRatio="none"` deforma lo spessore). Punti intermedi `r 2.5 #8B979A` quando i campioni sono pochi (≤5); ultimo punto `r 3.5` in `#2C4A52` (o `#2C8A6B` se il trend è positivo).
  - Barre (drill, iscritti): `display:flex; align-items:flex-end; gap:5-6px; height:62px`, ogni barra `flex:1`, `border-radius 5px 5px 3px 3px`, altezza in %; gradazione `#C9CFCE` → `#A8B4B7` → `#2C4A52`, l'ultima `#2C8A6B`.
  - Caption: `display:flex; justify-content:space-between; margin-top:8px`, mono 11px/700 `#6B7679`.
  - Legenda multi-serie (caso Elo+TPA): riga `margin-top:8px`, 11px/700; campione linea `width:14px; height:2px; background:#2C4A52` per l'Elo, `border-top:2px dashed #8B979A` per il TPA (serie TPA disegnata con `stroke-dasharray="3 3"`, `stroke-width 1.5`, `#8B979A`).
- Striscia attività: contenitore `margin-top 14px`.
  - Label row: `display:flex; align-items:baseline; gap:8px`, 11px/700 `#6B7679`; testo a sinistra ("Le tue ultime partite" / "…gare" / "…attività" / "I tuoi ultimi drill"), nota a destra `margin-left:auto` ("dalla più vecchia" o un conteggio).
  - Tessere: `display:flex; gap:5px; margin-top:7px`; ogni tessera `flex:1; height:30px; border-radius:9px`, contenuto centrato mono 12px/700. Colori: vinta `#2C8A6B`/`#fff`, pari `#D3D8D7`/`#4C5659`, persa `#B23B3B`/`#fff`, intermedia `#A8B4B7`/`#1B2124`. Con >6 tessere: `gap:4px`, `height:26px`, **niente testo** + legenda conteggi sotto (`margin-top:8px`, 11px/700, quadratini 8×8).
- Bottone espansione: `width:100%; margin-top:16px; height:40px; border:0; border-radius:12px; background:#E4E8E7; color:#3D474A`, Manrope 13px/700, `display:flex; align-items:center; justify-content:center; gap:8px`, `cursor:pointer`; hover `background:#D3D8D7`. Chevron 11px. Etichetta chiusa = anteprima del contenuto ("Streak e classifica", "Tutti i tuoi numeri", "Cosa sta funzionando"); aperta = "Chiudi".

### Blocco aperto
- Contenitore: `margin-top:18px; background:#E4E8E7; border-radius:22px; overflow:hidden`.
- Righe: `padding:14px 16px; display:flex; align-items:center; gap:12px`; dalla seconda in poi `border-top:1px solid #D3D8D7`.
- Riga: icona FA 15px (`fa-fire` `#B23B3B`, `fa-bullseye`/`fa-trophy`/`fa-users`/`fa-clock`/`fa-euro-sign` `#2C4A52`, `fa-arrow-trend-up` `#2C8A6B`) · blocco testo `flex:1` (titolo 14px/800, sottotitolo `margin-top:2px` 11px/700 `#6B7679`) · valore opzionale a destra (20px/800 `letter-spacing -.03em`, o mono 12px/700 grigio).
- Anello livello/XP dentro una riga: 40px, `conic-gradient(#2C4A52 <pct>%, #D3D8D7 0)`, foro `inset:5px` su `#E4E8E7`, centro mono 11px/800 con la percentuale.

## Interactions & Behavior
- **Toggle espansione**: click sul bottone → mostra/nasconde il pannello, ruota il chevron. Nessuna animazione richiesta; se ne vuoi una, `max-height`/`opacity` 180ms `ease-out`, e va disattivata sotto `prefers-reduced-motion`.
- **Persistenza**: `sessionStorage['home_feedback_open'] = '1'`. Chiuso a ogni nuova sessione. **Non** usare `localStorage`.
- **Accessibilità**: il bottone è un vero `<button type="button">` con `aria-expanded` e `aria-controls` verso l'id del pannello; il pannello ha `hidden` quando chiuso. Il colore non è mai l'unico veicolo dell'informazione: ogni tessera porta anche il dato (punteggio/piazzamento), e dove il testo non c'è (super attivo) la legenda dà i conteggi. Aggiungere `title`/`aria-label` per tessera ("Gara 4, vinta 5–3").
- **Nessun link** dentro il blocco. Il tap sulla card non naviga.
- **Responsive**: a ≥768px la card resta nella colonna della dashboard; la griglia metriche può passare a 3 colonne solo se ci sono 3 metriche vere. Le tessere restano `flex:1` e si allargano.
- **Grafici**: SVG inline generato server-side (Jinja) o piccolo helper JS che riceve un array di numeri e produce i `points`. Non introdurre Chart.js: il progetto non ha librerie di grafici e ne bastano polyline e barre.

## State Management
Lato server, un unico dict `activity_feedback` passato al template dalla view della dashboard giocatore, o `None` se il giocatore non ha attività (→ card di setup). Campi:

- `profile`: `'full' | 'elo_only' | 'drill_only' | 'competition_only' | 'director' | 'hyperactive' | 'returning' | 'declining' | 'new'` — calcolato dal servizio, il template solo lo legge.
- `primary`: `{label, value, delta, delta_tone: 'up'|'down'|'flat', suffix?}`
- `secondary`: uno tra `{kind: 'metric', …}` e `{kind: 'donut', slices: [{label, count, color_role}], center}`
- `chart`: `{kind: 'line'|'bars', series: [[float]], labels: {start, end}, legend?, projected_from?}` (`projected_from` = indice da cui la linea va tratteggiata, per il caso rientro)
- `strip`: `{label, note, items: [{text?, icon?, outcome: 'win'|'draw'|'loss'|'neutral', title}]}`
- `context_badge`: `{text, tone}` opzionale
- `note`: stringa opzionale (usata nel caso "in calo")
- `expanded_rows`: lista di `{icon, color_role, title, subtitle, value?, ring_pct?}`

Dati da recuperare (già presenti nel dominio):
- **Elo**: storico dal rating dei match (Elo duale competitivo/amichevole già gestito nel progetto) — prendi gli ultimi 10 punti e il delta primo↔ultimo.
- **TPA**: dal servizio statistiche TPA; esiste solo se ci sono rack con dati registrati — se manca, `profile` non lo include.
- **Forma**: esito degli ultimi match (attenzione: **esiste il pareggio**, quindi tre stati, non due).
- **Drill/challenge**: sessioni completate, punteggio per sessione, soglia superata sì/no.
- **Gare/campionato**: piazzamenti per gara, posizione corrente in classifica.
- **Livello/XP/streak**: dal modulo gamification.
- **Direttore**: gare organizzate, iscritti/capienza per gara, quote incassate, referti pendenti.

Regole di calcolo: finestra **ultime 10 attività**; delta = valore corrente − valore alla prima delle 10; se le attività sono meno di 3 non mostrare la sparkline (mostra solo metriche + striscia); "massimo di sempre" solo se il valore corrente è davvero il massimo storico. Cache consigliata: il dict è calcolabile in una query per fonte, ma va memoizzato per richiesta (la home ne fa già diverse).

## Design Tokens
Corrispondono ai token 7c del progetto; usare le variabili CSS, non gli hex.

Colori
- `#1B2124` testo primario · `#3D474A` testo secondario · `#6B7679` testo tenue · `#4C5659` testo su grigio
- `#DADEDD` sfondo pagina · `#E4E8E7` sfondo card annidata / bottone · `#F5F7F6` superficie card · `#D3D8D7` bordo/divisore e stato "pari"
- `#2C4A52` accento (linee, anelli, badge) · `#8FCDE8` accento su scuro
- `#2C8A6B` positivo/vinta · `#1D5F4A` testo su positivo tenue · `#E4EDE9` sfondo positivo tenue
- `#B23B3B` negativo/persa · `#8A2C2C` testo su negativo tenue · `#F3E2E0` sfondo negativo tenue
- `#8A6A1F` ambra: delta negativo, scadenze
- `#C9CFCE` / `#A8B4B7` / `#8B979A` grigi dei grafici

Tipografia
- UI: Manrope 400/600/700/800. 24px/800 h1 · 17px/800 h2 · 14px/800 titolo riga · 13px/700 bottone e corpo · 12px/700 caption · 11px/700 etichetta · 10px/800 uppercase `letter-spacing .12em` kicker, `.04em` badge.
- Numeri: JetBrains Mono 700/800 (`--c7-font-mono`). 30px `-.035em` metrica principale · 26px `-.03em` metrica secondaria · 12px `-.02em` tessere · 11px caption.

Spaziature (multipli di 2): 2 · 4 · 5 · 6 · 7 · 8 · 10 · 12 · 14 · 16 · 18 · 20 · 24
Raggi: 999 pill · 26 card esterna · 22 card elenco · 18 riquadro grafico · 12 bottone · 9 tessera · 7 tessera piccola · 2 quadratino legenda
Ombre: nessuna dentro il blocco (la card è distinta dal fondo per luminosità, come nel resto della dashboard).

## Assets
Nessuna immagine. Solo icone **Font Awesome 6** (già caricato nel progetto): `fa-fire`, `fa-bullseye`, `fa-trophy`, `fa-users`, `fa-clock`, `fa-euro-sign`, `fa-arrow-trend-up`, `fa-chevron-down`, `fa-chevron-up`, `fa-check`, `far fa-circle`, `fa-clipboard-check`. Manrope e JetBrains Mono via Google Fonts, come nel design system 7c.

## Files
Nel bundle:
- `screens/` — screenshot 2x dei frame, tutti a blocco **chiuso**:
  - `00-home-attuale.png` home di oggi, prima dell'intervento
  - `2a-solo-elo.png` caso base approvato
  - `3a-solo-drill.png` · `3b-solo-gare.png` · `3c-tutto-attivo.png` · `3d-rientro.png`
  - `4a-direttore.png` · `4b-super-attivo.png` · `4c-appena-iscritto.png` · `4d-in-calo.png`
  (per vedere lo stato **aperto** apri il file HTML e clicca il bottone di espansione del frame)
- `Home Giocatore.dc.html` — tutti i frame di design (aprire in browser; i link `#2a`, `#3a`… puntano ai frame)
- `support.js` — runtime necessario al file di design
- `github.md` — repo di origine, branch e mappa schermata→file del repo

Nel repo, da toccare per implementare:
- `templates/dashboard/player.html` — punto di inserimento del blocco (dopo il saluto, prima di "I tuoi match")
- `templates/components/_player_dashboard_content.html`, `_separated_dashboard_content.html` — contenuto della dashboard giocatore
- `templates/components/_unified_dashboard_header.html` — header con pill livello
- nuovo: `templates/components/_player_activity_feedback.html` (+ eventuale `_player_activity_setup.html` per il caso "appena iscritto")
- `static/css/theme-7c.css` / `gamification.css` — classi esistenti da riusare; aggiungere solo quelle mancanti (tessere striscia, riquadro grafico) seguendo la nomenclatura `c7-`
- servizio nuovo lato Python che produce `activity_feedback` (es. `services/activity_feedback.py`), alimentato dai servizi rating/TPA/gamification esistenti
