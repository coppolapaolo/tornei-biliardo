# Report test manuali — Gamification V3 (pre-apertura ai player)

> **Scopo**: registrare l'esito dei test **manuali in browser** richiesti prima
> di promuovere la gamification ai player (maturity-gate ADR-028). Copre ciò che
> i test automatici **non** verificano: animazioni badge, scala d'intensità dei
> toast, cap di sessione, `prefers-reduced-motion`, policy un-solo-canale.
> Checklist sorgente: `GAMIFICATION_V3_MANUAL_TESTS.md`.
>
> **Come compilare**: per ogni riga metti l'esito (`PASS` / `FAIL` / `N/A`) e una
> nota se serve. In fondo, l'esito complessivo e la firma.

---

> ## ⚙️ Pre-verifica automatica (headless) — 2026-06-07
>
> Una parte di questa checklist è stata **pre-verificata in automazione headless**
> caricando il vero `static/js/gamification.js` in un DOM jsdom e asserendo la
> logica deterministica (scala d'intensità, cap anti-invasività, reduced-motion,
> confetti, helper console). **26/26 controlli verdi.**
>
> - Harness: `tests/frontend/test_gamification_badge.cjs` (esecuzione:
>   `cd tests/frontend && npm install && npm test`).
> - Le righe coperte sono marcate **`✅ auto`** nella colonna Esito, con il
>   riferimento nelle Note.
> - **Resta il gate umano**: le righe marcate **`☐`** richiedono conferma
>   visiva nel browser (animazioni reali, rendering, layout responsive,
>   cross-tab, toggle reduced-motion del SO, centro notifiche). Compilale tu,
>   poi firma in fondo.

---

## Intestazione esecuzione

| Campo | Valore |
|---|---|
| Data esecuzione | ________ |
| Esecutore | ________ |
| Build / commit | branch `claude/gamification-system-review-beIB0` (pre-verifica auto 2026-06-07) |
| Browser + versione | ________ |
| OS | ________ |
| Ruolo di test | ☐ director  ☐ player (promosso)  ☐ entrambi |
| Ambiente | ☐ locale (`DEBUG_MODE=true`)  ☐ staging  ☐ prod |

> Innesco eventi senza giocare: console browser →
> `testGamificationEffects()` (sequenza completa) oppure
> `showGamificationEvent(type, data)` (singolo evento).

---

## 1. Badge navbar — anello di progresso (§11-quater)

| # | Verifica | Esito | Note |
|---|---|---|---|
| 1.1 | Badge (trofeo+livello+XP) visibile per player/director; **assente** per admin | ☐ | Gate server-side `base.html:177` (`not is_admin and feature_visible('gamification.dashboard')`); coperto anche da `tests/new/integration/gamification/test_navbar_badge_render.py`. Conferma visiva nel browser. |
| 1.2 | Anello di progresso proporzionale al progresso verso il livello successivo | ☐ | Anello `--gami-progress` da `progress_percentage` (`gamification.css:574-588`, `_refreshRing` in gamification.js). Conferma visiva. |
| 1.3 | Valore anello = `progress_percentage` reale (confronta con `/gamification/dashboard`) | ☐ | Stesso `progress_percentage` di `LevelService.get_level_progress` su badge e dashboard. Conferma visiva. |
| 1.4 | 0% → anello vuoto; non "trabocca" mai oltre il cerchio | ☐ | Doppia garanzia: `award_xp` mantiene `current_xp < xp_for_next` (`level_service.py:115-138`, reset a ogni level-up) **e** la `conic-gradient` clampa i color-stop <0%/>100%. Conferma visiva a 0% e ~100%. |

## 2. Scala d'intensità — guadagno XP → solo badge (niente toast)

| # | Verifica | Esito | Note |
|---|---|---|---|
| 2.1 | Azione con solo XP (es. partita persa +20) → **nessun toast** | ✅ auto | Headless: `showGamificationEvent('xp')` non richiede alcun toast (`case 'xp'` → solo `badge.addXP`). |
| 2.2 | Badge fa un breve *pulse* al caricamento dopo il guadagno | ✅ auto | Headless: classe `badge-pulse` aggiunta (motion on). Fluidità reale = conferma visiva. |
| 2.3 | Numero XP nel badge anima in *count-up* (non salta) | ✅ auto | Headless: reduced-motion → valore istantaneo; motion on → `_countUp` via rAF. |
| 2.4 | Console `showGamificationEvent('xp', {amount: 50})` → solo pulse+count-up | ✅ auto | Headless: nessun toast, solo badge. |

## 3. Scala d'intensità — level-up → glow + UN toast

| # | Verifica | Esito | Note |
|---|---|---|---|
| 3.1 | Bagliore (glow) dorato del badge al level-up | ✅ auto | Headless: classe `badge-levelup` aggiunta. Glow reale = conferma visiva. |
| 3.2 | Numero livello aggiornato nel badge | ✅ auto | Headless: `#gami-badge-level` e `data-level` → nuovo livello. |
| 3.3 | **Un solo** toast di level-up (mascotte/confetti ammessi); nessun duplicato | ✅ auto | Headless: esattamente 1 richiesta `showLevelUp`. |
| 3.4 | Toast di level-up appare **anche** se il cap di sessione è già stato consumato (§5) | ✅ auto | Headless: dopo aver consumato il cap, level-up mostra comunque il toast (esente). |
| 3.5 | Console `showGamificationEvent('levelup', {level: 5, title: 'Test'})` | ✅ auto | Headless: helper esposto e funzionante. |

## 4. Scala d'intensità — achievement / streak / quest → pulse + toast

| # | Verifica | Esito | Note |
|---|---|---|---|
| 4.1 | Sblocco achievement → toast + pulse del badge | ✅ auto | Headless: `badge.pulse()` sempre + toast (slot cap libero). Animazione pulse = conferma visiva. |
| 4.2 | Streak milestone (4/12/52) → toast + pulse | ✅ auto | Headless: toast streak quando lo slot cap è libero. La *soglia* milestone è lato backend (StreakService). |
| 4.3 | Quest completata → toast + pulse | ✅ auto | Headless: toast quest quando lo slot cap è libero. |
| 4.4 | Console: `achievement`/`streak`/`quest` via `showGamificationEvent(...)` | ✅ auto | Headless: tutti gli helper funzionano. |

## 5. Cap anti-invasività — max 1 toast "capped" per sessione (§11)

| # | Verifica | Esito | Note |
|---|---|---|---|
| 5.1 | In nuova sessione, il **primo** tra achievement/streak/quest mostra il toast | ✅ auto | Headless: primo evento capped → 1 toast. |
| 5.2 | Il **secondo** evento capped nella stessa sessione → solo pulse, niente toast | ✅ auto | Headless: 1 solo toast su achievement+streak+quest consecutivi. |
| 5.3 | Dopo il cap, un **level-up** mostra comunque il suo toast (esente) | ✅ auto | Headless: vedi 3.4. |
| 5.4 | Nuova scheda/sessione → il primo toast capped torna a comparire (`sessionStorage`) | ✅ auto | Headless: dopo `sessionStorage.removeItem('gamiCappedToastShown')` il toast riappare. Cross-tab reale = conferma visiva. |
| 5.5 | Con `sessionStorage` non disponibile (privacy) → degrada mostrando i toast | ✅ auto | Headless: con `sessionStorage` che lancia eccezione, entrambi i toast capped vengono mostrati. |

## 6. Accessibilità — `prefers-reduced-motion`

| # | Verifica | Esito | Note |
|---|---|---|---|
| 6.1 | "Riduci movimento" ON → nessuna animazione pulse/glow | ✅ auto | Headless: con `matchMedia(reduce)=true` nessuna classe `badge-pulse`. CSS `@media` (gamification.css:635-644). Toggle SO reale = conferma visiva. |
| 6.2 | "Riduci movimento" ON → niente count-up (valore istantaneo) | ✅ auto | Headless: `_countUp` imposta il valore finale subito. |
| 6.3 | "Riduci movimento" ON → anello statico col valore corretto | ☐ | CSS `@media` disabilita la `transition` dell'anello; `_refreshRing` imposta comunque il valore. Conferma visiva. |
| 6.4 | "Riduci movimento" OFF → le animazioni tornano | ✅ auto | Headless: con motion ON la classe `badge-pulse` viene riaggiunta. |

## 7. Policy un-solo-canale — niente notifiche persistenti celebrative (§11)

| # | Verifica | Esito | Note |
|---|---|---|---|
| 7.1 | Dopo level-up/achievement/streak/quest, il centro notifiche **non** mostra notifiche persistenti per questi eventi | ☐ | Coperto backend (`notification_handlers` no-op) + `test_anti_invasivita_notifications.py`. Conferma visiva nel centro notifiche. |
| 7.2 | Le notifiche **azionabili** (invito a match, gara in zona) arrivano regolarmente | ☐ | Conferma nel browser (richiede flusso applicativo reale). |
| 7.3 | Il contatore "non lette" **non** si incrementa per gli eventi celebrativi | ☐ | Coperto backend; conferma visiva del contatore. |

> Nota: il punto 7.1/7.3 è coperto anche dai test automatici
> (`test_anti_invasivita_notifications.py`,
> `test_xp_workflow.py::...no_persistent_notification`,
> `test_achievement_workflow.py::test_first_blood...`): qui si verifica
> l'esperienza reale nel browser.

## 8. Mascotte / confetti — solo momenti forti

| # | Verifica | Esito | Note |
|---|---|---|---|
| 8.1 | Mascotte "Chalky"/confetti solo su toast forti (level-up/achievement/streak), **non** sui micro-XP | ✅ auto | Headless: confetti solo su level-up (`'level'`) e achievement rare+; XP e achievement common → nessun confetti. Resa visiva mascotte = conferma a occhio. |

## 9. Responsive / layout

| # | Verifica | Esito | Note |
|---|---|---|---|
| 9.1 | Desktop: badge completo (trofeo+livello+"N XP") | ☐ | Conferma visiva (desktop). |
| 9.2 | Mobile: badge leggibile; "N XP" può nascondersi, livello+anello restano | ☐ | `d-none d-sm-inline` su "N XP" (`base.html:196`). Conferma visiva su viewport stretto. |
| 9.3 | Toast su mobile centrati e dentro il viewport | ☐ | `width: min(420px, 100vw-32px)` (`gamification.css:50`). Conferma visiva. |

## 10. Regressione rapida

| # | Verifica | Esito | Note |
|---|---|---|---|
| 10.1 | Login/logout e navigazione: nessun errore JS in console | ☐ | Conferma nel browser (richiede app reale). |
| 10.2 | Toast `welcome` al login funziona | ✅ auto | Headless: `showGamificationEvent('welcome')` → toast. Resa al login = conferma visiva. |
| 10.3 | Nudge/unlock di funzioni mostrano il toast | ✅ auto | Headless: nudge e unlock → toast (azionabili, non soggetti al cap). |

---

## Copertura automazione headless (dettaglio)

26 controlli verdi in `tests/frontend/test_gamification_badge.cjs` (jsdom su
`static/js/gamification.js`). Riesecuzione:

```bash
cd tests/frontend
npm install   # jsdom (node_modules è gitignored)
npm test      # node test_gamification_badge.cjs
```

Raggruppamento controlli → righe report:

- **§2** XP→solo badge / count-up / pulse → 2.1, 2.2, 2.3, 2.4
- **§3** level-up: 1 toast, glow, livello, esente dal cap → 3.1, 3.2, 3.3, 3.4, 3.5
- **§4** achievement/streak/quest: toast + pulse → 4.1, 4.2, 4.3, 4.4
- **§5** cap 1-toast/sessione, reset, privacy → 5.1, 5.2, 5.3, 5.4, 5.5
- **§6** reduced-motion: no-op + valore istantaneo → 6.1, 6.2, 6.4
- **§8** confetti solo eventi forti → 8.1
- **§10** welcome / nudge / unlock → 10.2, 10.3

**Non automatizzato (gate umano residuo, 12 righe `☐`)**: 1.1–1.4 (badge/anello
reali), 6.3 (anello statico reduced-motion), 7.1–7.3 (centro notifiche reale),
9.1–9.3 (responsive), 10.1 (assenza errori JS end-to-end).

---

## Copertura automatica già presente (contesto)

Questi test automatici **verdi** coprono il *wiring* (non sostituiscono i
controlli runtime sopra):

- `tests/frontend/test_gamification_badge.cjs` — **logica frontend** (jsdom):
  scala d'intensità, cap di sessione, reduced-motion, confetti (questo report).
- `tests/new/integration/gamification/test_navbar_badge_render.py` — markup badge.
- `.../test_anti_invasivita_notifications.py` — assenza notifiche persistenti.
- `.../test_xp_workflow.py` — catena evento→XP→level-up + niente notifica LEVEL_UP.
- `.../test_achievement_workflow.py` — sblocco achievement metric-driven.
- `.../test_quest_workflow.py`, `.../test_streak_workflow.py`,
  `.../test_gamification_e2e.py`.

---

## Esito complessivo

| Campo | Valore |
|---|---|
| Righe `✅ auto` (pre-verificate headless) | 24 / 36 |
| Righe `☐` da confermare a occhio (gate umano) | 12 / 36 |
| Righe PASS / totali (dopo conferma umana) | ____ / 36 |
| Problemi bloccanti (FAIL) | ________ |
| **Pronto per apertura ai player?** | ☐ SÌ  ☐ NO  ☐ con riserve |
| Firma esecutore | ________ |

### Problemi rilevati (dettaglio)

| Rif. (#) | Descrizione | Severità | Azione |
|---|---|---|---|
| | | | |
