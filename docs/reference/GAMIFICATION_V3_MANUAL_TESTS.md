# Gamification V3 — Test manuali (da eseguire in browser)

**Scopo**: checklist dei comportamenti **non coperti da test automatici** —
soprattutto il frontend JS/CSS (animazioni badge, scala d'intensità toast,
cap di sessione, `prefers-reduced-motion`) e la verifica end-to-end della
policy anti-invasività. I test Python coprono il *wiring* (markup del badge,
assenza di notifiche persistenti), non il comportamento runtime nel browser.

**Cohorte di test**: la gamification è **director-only** in produzione
(maturity-gate ADR-028). In locale (`DEBUG_MODE=true`) tutto è visibile; per
riprodurre la prod, testare con un utente **director** (e un **player** dove
indicato, una volta promosso). Gli **admin** sono esclusi dalla gamification.

**Come innescare gli eventi**: in console del browser è disponibile
`testGamificationEffects()` (sequenza demo di tutti i toast) e
`showGamificationEvent(type, data)` per innescare singoli eventi senza dover
giocare partite reali. Per il flusso reale: completare una partita / iscriversi
a una gara / completare una quest da utente non-admin.

---

## Legenda esito
- [ ] da fare · ✅ ok · ❌ problema (annotare sotto)

---

## 1. Badge navbar — anello di progresso (§11-quater)

- [ ] **Render del badge**: da player/director non-admin il badge (trofeo +
  livello + XP) è visibile in navbar; da admin **non** appare.
- [ ] **Anello di progresso**: attorno al trofeo c'è un anello parzialmente
  pieno proporzionale al progresso verso il livello successivo. A livello
  appena raggiunto l'anello è quasi vuoto; vicino al level-up è quasi pieno.
- [ ] **Valore corretto**: l'anello riflette `progress_percentage` reale
  (confrontare con la dashboard gamification `/gamification/dashboard`).
- [ ] **0%/100%**: con 0 XP nel livello l'anello è vuoto; non deve mai
  "traboccare" oltre il cerchio.

## 2. Scala d'intensità — guadagno XP → solo badge (niente toast)

- [ ] **Nessun toast su XP**: completando un'azione che dà solo XP (es. una
  partita persa, +20 XP) **non** compare alcun toast.
- [ ] **Pulse del badge**: al caricamento della pagina dopo il guadagno, il
  badge fa un breve *pulse*.
- [ ] **Count-up del numero XP**: il valore XP nel badge si anima salendo dal
  valore precedente a quello nuovo (non "salta" di colpo).
- [ ] Console: `showGamificationEvent('xp', {amount: 50})` → solo pulse +
  count-up, nessun toast.

## 3. Scala d'intensità — level-up → glow + UN solo toast

- [ ] **Glow del badge**: al level-up il badge emette un bagliore dorato breve.
- [ ] **Livello aggiornato**: il numero di livello nel badge passa al nuovo.
- [ ] **Un solo toast**: compare **un** toast di level-up (con mascotte/confetti
  ammessi — è un momento forte). Non compaiono toast duplicati.
- [ ] **Esenzione dal cap**: il toast di level-up appare **anche se** in questa
  sessione era già stato mostrato un altro toast celebrativo (vedi §5).
- [ ] Console: `showGamificationEvent('levelup', {level: 5, title: 'Test'})`.

## 4. Scala d'intensità — achievement / streak / quest → pulse + toast

- [ ] **Achievement**: sblocco achievement → toast + pulse del badge.
- [ ] **Streak milestone**: raggiunto un milestone (4/12/52 settimane) → toast +
  pulse.
- [ ] **Quest completata**: completamento quest → toast + pulse.
- [ ] Console: `showGamificationEvent('achievement', {name:'X', description:'Y',
  rarity:'rare'})`, idem `streak`/`quest`.

## 5. Cap anti-invasività — max 1 toast "capped" per sessione (§11)

- [ ] **Primo toast mostrato**: in una nuova sessione del browser, il primo tra
  achievement/streak/quest mostra il toast.
- [ ] **Secondo soppresso**: un successivo achievement/streak/quest nella stessa
  sessione **non** mostra il toast (solo pulse del badge). Verificare innescando
  due eventi capped di fila in console.
- [ ] **Level-up sempre visibile**: dopo aver "consumato" il cap, un level-up
  mostra comunque il suo toast (esente dal cap).
- [ ] **Reset per sessione**: aprire una **nuova scheda/sessione** del browser
  (o chiudere e riaprire) → il primo toast capped torna a mostrarsi.
  (Il cap usa `sessionStorage`, chiave `gamiCappedToastShown`.)
- [ ] **Privacy mode**: con `sessionStorage` non disponibile il cap non deve
  bloccare nulla (degrada mostrando i toast).

## 6. Accessibilità — `prefers-reduced-motion`

- [ ] Abilitare "riduci movimento" nel SO/browser. Poi:
  - [ ] **Nessuna animazione**: pulse/glow del badge non si animano.
  - [ ] **Nessun count-up**: il numero XP si aggiorna istantaneamente al valore
    finale (niente conteggio animato).
  - [ ] **Anello statico**: l'anello mostra il valore corretto senza transizione.
- [ ] Disabilitare "riduci movimento" → le animazioni tornano.

## 7. Policy un-solo-canale — niente notifiche persistenti celebrative (§11)

- [ ] **Centro notifiche pulito**: dopo level-up / achievement / streak / quest,
  aprire il centro notifiche → **non** devono comparire notifiche persistenti
  per questi eventi (solo i toast transitori già visti).
- [ ] **Eventi azionabili intatti**: le notifiche per eventi azionabili (invito
  a match individuale, ecc.) continuano ad arrivare regolarmente.
- [ ] **Contatore badge notifiche**: il pallino "non lette" non si incrementa
  per gli eventi celebrativi.

## 8. Mascotte / confetti — solo momenti forti

- [ ] La mascotte "Chalky" e i confetti compaiono **solo** sui toast forti
  (level-up, achievement, streak), **non** sui micro-guadagni XP (che non hanno
  più toast).

## 9. Responsive / layout

- [ ] **Desktop**: badge completo (trofeo + livello + "N XP").
- [ ] **Mobile** (viewport stretto): il badge resta leggibile; la parte "N XP"
  può nascondersi (`d-none d-sm-inline`) ma livello + anello restano visibili.
- [ ] **Toast su mobile**: i toast restano centrati e dentro il viewport.

## 10. Regressione rapida

- [ ] Login/logout normale, navigazione tra pagine: nessun errore JS in console.
- [ ] `welcome` toast al login continua a funzionare.
- [ ] Nudge/unlock di funzioni (scoperta) continuano a mostrare il toast.

---

## Note esecuzione

Data: __________  ·  Browser/OS: __________  ·  Ruolo: __________

Problemi rilevati:

-
