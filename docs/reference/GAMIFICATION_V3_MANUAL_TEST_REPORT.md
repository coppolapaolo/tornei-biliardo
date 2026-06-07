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

## Intestazione esecuzione

| Campo | Valore |
|---|---|
| Data esecuzione | ________ |
| Esecutore | ________ |
| Build / commit | ________ |
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
| 1.1 | Badge (trofeo+livello+XP) visibile per player/director; **assente** per admin | ☐ | |
| 1.2 | Anello di progresso proporzionale al progresso verso il livello successivo | ☐ | |
| 1.3 | Valore anello = `progress_percentage` reale (confronta con `/gamification/dashboard`) | ☐ | |
| 1.4 | 0% → anello vuoto; non "trabocca" mai oltre il cerchio | ☐ | |

## 2. Scala d'intensità — guadagno XP → solo badge (niente toast)

| # | Verifica | Esito | Note |
|---|---|---|---|
| 2.1 | Azione con solo XP (es. partita persa +20) → **nessun toast** | ☐ | |
| 2.2 | Badge fa un breve *pulse* al caricamento dopo il guadagno | ☐ | |
| 2.3 | Numero XP nel badge anima in *count-up* (non salta) | ☐ | |
| 2.4 | Console `showGamificationEvent('xp', {amount: 50})` → solo pulse+count-up | ☐ | |

## 3. Scala d'intensità — level-up → glow + UN toast

| # | Verifica | Esito | Note |
|---|---|---|---|
| 3.1 | Bagliore (glow) dorato del badge al level-up | ☐ | |
| 3.2 | Numero livello aggiornato nel badge | ☐ | |
| 3.3 | **Un solo** toast di level-up (mascotte/confetti ammessi); nessun duplicato | ☐ | |
| 3.4 | Toast di level-up appare **anche** se il cap di sessione è già stato consumato (§5) | ☐ | |
| 3.5 | Console `showGamificationEvent('levelup', {level: 5, title: 'Test'})` | ☐ | |

## 4. Scala d'intensità — achievement / streak / quest → pulse + toast

| # | Verifica | Esito | Note |
|---|---|---|---|
| 4.1 | Sblocco achievement → toast + pulse del badge | ☐ | |
| 4.2 | Streak milestone (4/12/52) → toast + pulse | ☐ | |
| 4.3 | Quest completata → toast + pulse | ☐ | |
| 4.4 | Console: `achievement`/`streak`/`quest` via `showGamificationEvent(...)` | ☐ | |

## 5. Cap anti-invasività — max 1 toast "capped" per sessione (§11)

| # | Verifica | Esito | Note |
|---|---|---|---|
| 5.1 | In nuova sessione, il **primo** tra achievement/streak/quest mostra il toast | ☐ | |
| 5.2 | Il **secondo** evento capped nella stessa sessione → solo pulse, niente toast | ☐ | |
| 5.3 | Dopo il cap, un **level-up** mostra comunque il suo toast (esente) | ☐ | |
| 5.4 | Nuova scheda/sessione → il primo toast capped torna a comparire (`sessionStorage`) | ☐ | |
| 5.5 | Con `sessionStorage` non disponibile (privacy) → degrada mostrando i toast | ☐ | |

## 6. Accessibilità — `prefers-reduced-motion`

| # | Verifica | Esito | Note |
|---|---|---|---|
| 6.1 | "Riduci movimento" ON → nessuna animazione pulse/glow | ☐ | |
| 6.2 | "Riduci movimento" ON → niente count-up (valore istantaneo) | ☐ | |
| 6.3 | "Riduci movimento" ON → anello statico col valore corretto | ☐ | |
| 6.4 | "Riduci movimento" OFF → le animazioni tornano | ☐ | |

## 7. Policy un-solo-canale — niente notifiche persistenti celebrative (§11)

| # | Verifica | Esito | Note |
|---|---|---|---|
| 7.1 | Dopo level-up/achievement/streak/quest, il centro notifiche **non** mostra notifiche persistenti per questi eventi | ☐ | |
| 7.2 | Le notifiche **azionabili** (invito a match, gara in zona) arrivano regolarmente | ☐ | |
| 7.3 | Il contatore "non lette" **non** si incrementa per gli eventi celebrativi | ☐ | |

> Nota: il punto 7.1/7.3 è coperto anche dai test automatici
> (`test_anti_invasivita_notifications.py`,
> `test_xp_workflow.py::...no_persistent_notification`,
> `test_achievement_workflow.py::test_first_blood...`): qui si verifica
> l'esperienza reale nel browser.

## 8. Mascotte / confetti — solo momenti forti

| # | Verifica | Esito | Note |
|---|---|---|---|
| 8.1 | Mascotte "Chalky"/confetti solo su toast forti (level-up/achievement/streak), **non** sui micro-XP | ☐ | |

## 9. Responsive / layout

| # | Verifica | Esito | Note |
|---|---|---|---|
| 9.1 | Desktop: badge completo (trofeo+livello+"N XP") | ☐ | |
| 9.2 | Mobile: badge leggibile; "N XP" può nascondersi, livello+anello restano | ☐ | |
| 9.3 | Toast su mobile centrati e dentro il viewport | ☐ | |

## 10. Regressione rapida

| # | Verifica | Esito | Note |
|---|---|---|---|
| 10.1 | Login/logout e navigazione: nessun errore JS in console | ☐ | |
| 10.2 | Toast `welcome` al login funziona | ☐ | |
| 10.3 | Nudge/unlock di funzioni mostrano il toast | ☐ | |

---

## Copertura automatica già presente (contesto)

Questi test automatici **verdi** coprono il *wiring* (non sostituiscono i
controlli runtime sopra):

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
| Righe PASS / totali | ____ / 34 |
| Problemi bloccanti (FAIL) | ________ |
| **Pronto per apertura ai player?** | ☐ SÌ  ☐ NO  ☐ con riserve |
| Firma esecutore | ________ |

### Problemi rilevati (dettaglio)

| Rif. (#) | Descrizione | Severità | Azione |
|---|---|---|---|
| | | | |
