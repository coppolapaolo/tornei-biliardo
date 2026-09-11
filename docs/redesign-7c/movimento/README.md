# Movimento 7c — la decisione

Il prototipo (`../Redesign Mobile.dc.html`) è statico: fissa colori, raggi e
gerarchia, non può fissare come una card si apre. Il movimento è la parte del
design system che il prototipo non poteva mostrare, e si è deciso guardando
invece che leggendo: `confronto.html` mette cinque gesti dell'app a tre durate
affiancate, con i token veri di `tokens-7c.css` e i componenti come sono
(segnapunti, rackpad, tessera della gara, pastiglie). Si apre servendola in
locale (`python3 -m http.server 8899` da `docs/redesign-7c`, poi
`/movimento/confronto.html`): il browser pilotato non apre `file://`.

## Scelte (11 settembre 2026)

| Gesto | Scelta |
|---|---|
| Curva | **standard** (`ease-out` del browser), per tutto |
| Cifra del punteggio che cambia | 250 ms |
| Tocco sul rackpad | schiacciamento a **.94**, istantaneo; ritorno a 150 ms |
| Pastiglia che compare sulla tessera | entra a 250 ms, esce a 150 |
| Sezione che si apre | apre a 250 ms, chiude a 150 |
| Cambio pagina | dissolvenza a 250 ms, testata ferma |

Da qui la scala in `static/css/tokens-7c.css`: `--c7-dur-base` (250 ms) per
ciò che entra, si apre, cambia sotto gli occhi; `--c7-dur-quick` (150 ms) per
ciò che esce, si chiude, torna dal tocco; `--c7-ease`; `--c7-press`. Con
`prefers-reduced-motion: reduce` le due durate vanno a zero alla fonte.

## Perché così

- **Il movimento è informazione, non decorazione**: spiega un cambio di stato,
  dà riscontro al tocco, toglie i salti. Niente hover (l'app è touch), niente
  blur, niente effetti che si ripetono da soli, salvo i battiti del pallino
  live.
- **Non rallenta**: si animano solo `transform` e `opacity`, che stanno sul
  compositore; lo schiacciamento è a 0 ms e l'azione parte al tocco, la cifra
  si anima *mentre* il server risponde. L'unica eccezione è l'altezza di una
  sezione che si apre, un elemento solo.
- **Il cambio pagina** aggiunge davvero 250 ms in cui non si tocca, e in cambio
  toglie il lampo bianco: la pagina vecchia resta visibile durante i 350 ms
  che costa una richiesta in produzione. Il tempo totale cresce di poco, il
  tempo percepito cala.

## Cosa resta fuori

`static/css/gamification.css` ha un lessico suo (glow, shine, wobble): è la
parte giocosa, voluta, e non segue la scala. `main.css` e `drill-builder.css`
sono mondi precedenti al tema, con guard propri.

## Passi successivi

1. ~~Token e allineamento dei timing esistenti~~ (PR #338).
2. ~~Cambio pagina~~: `@view-transition { navigation: auto }` nel tema, nomi
   su `.c7-head`, `.c7-side`, `.c7-mobilenav`, durata dai token, spento con
   «riduci movimento». Verificato con Chromium headless ascoltando
   `pageswap`: link e `location.replace` transitano, `location.reload()` no.
   Dal browser pilotato non si vede: la scheda risulta `hidden` e ogni
   transizione viene saltata.
3. La cifra del segnapunti che si anima quando cambia, al tocco e all'arrivo
   di un evento live. Sulla card verticale il cambio passa da un
   ricaricamento: per farlo transitare va sostituito `location.reload()` con
   `location.replace(location.href)`.

I tre fogli rimasti fuori scala (`gamification.css`, `main.css`,
`drill-builder.css`) sono nella issue #340.
