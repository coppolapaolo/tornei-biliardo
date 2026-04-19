---
title: 'Random + OddNumberPolicy.NO: lock-in semantica parity waitlist'
type: 'doc + regression test (zero code change)'
created: '2026-04-19'
status: 'done'
baseline_commit: '38fc050'
parent_spec: '_bmad-output/implementation-artifacts/spec-random-anti-rematch.md'
context:
  - models/competition/inscription_service.py
  - models/matchmaking/configuration.py
  - models/matchmaking/CLAUDE.md
  - tests/new/unit/test_parity_waitlist.py
  - _bmad-output/handoffs/random-next-steps.md (sezione G2)
---

<frozen-after-approval reason="human-approved scope — minimal doc+test delta">

## Intent

**Problem:** `STRATEGY_CONSTRAINTS[RANDOM]` ammette `OddNumberPolicy.NO`, ma nello
spec parent `spec-random-anti-rematch.md` (row 17 della I/O matrix) il
comportamento era marcato "GAP G2 — fuori scope". Il rischio è che un futuro
refactor di `InscriptionService._demote_last_to_parity_waitlist` o di
`_promote_from_parity_waitlist` rompa silenziosamente la strategia Random,
senza che alcun test se ne accorga.

**Discovery:** La semantica `NO` **è già completamente implementata** —
a livello di `InscriptionService`, non di matchmaking strategy. Quando
`gara.odd_number_policy == "no"` e l'iscrizione porterebbe a numero attivi
dispari, l'ultimo iscritto è automaticamente marcato `is_waitlist=True`,
`waitlist_reason=WaitlistReason.PARITY`, `waitlist_position=1`. Al prossimo
iscritto pari, il sistema fa promozione automatica. Tutte le strategie
(Random incluso, via `RoundService.start_first_round` → `base.get_active_inscriptions`
→ filtro `is_waitlist=False`) ricevono un pool già pari per costruzione.

**Test coverage attuale:** `tests/new/unit/test_parity_waitlist.py` copre
inscription, uninscription, interazione PARITY+CAPACITY. **Ma tutti i test
usano `matchmaking_strategy="amalfi"`**. Nessuna evidenza empirica che Random
si comporti identicamente.

**UX decision (confermata 2026-04-19):** Non differenziare
`WaitlistReason.PARITY` da `WaitlistReason.CAPACITY` in UI. Il messaggio
unificato "in lista d'attesa" resta, dato che l'utente non deve agire
diversamente nei due casi.

**Approach:** Zero modifiche a code di produzione. Solo:
1. **Regression test** integration-level: gara `matchmaking_strategy="random"` +
   `odd_number_policy="no"` esibisce lo stesso comportamento PARITY dei test
   Amalfi esistenti (lock-in cross-strategy).
2. **Test end-to-end**: 5 iscritti (policy=NO) → `start_first_round` produce
   round con solo 4 active players (il 5° escluso perché in PARITY waitlist).
3. **Doc update** in `models/matchmaking/CLAUDE.md` sezione "Random Anti-Rematch":
   nota che `NO` è gestito a inscription level, non dalla strategy; link a
   `inscription_service.py:130-170` e a questo spec.

**Fuori scope:**
- UI differenziata PARITY vs CAPACITY (decisione UX esplicita: non farlo)
- Edge case withdraw mid-tournament Random: Random ha
  `creates_all_rounds_at_startup=True`, il ribilanciamento inscription-level
  è possibile solo in SETUP. Post-SETUP un withdraw lascia il pool dispari
  → walkover path esistente (gestito da `WithdrawPolicyService`, non da
  parity waitlist). Tocca G3 (reset/withdraw in Random), non G2.

## Boundaries & Constraints

**Always:**
- Lock-in attraverso regression test, **non** modifiche di codice
- Tutti i nuovi test devono passare `pyright` senza errori
- I test devono usare `matchmaking_strategy="random"` per essere realmente
  "Random-aware" (copia-incolla dei test Amalfi esistenti non è sufficiente
  come regression guard se la strategia non viene attivata)

**Ask First:**
- Se durante scrittura test si scopre che Random NON si comporta come Amalfi
  con policy=NO: non è un lock-in, è un bug vero. Stop e chiedi conferma
  utente prima di procedere.

**Never:**
- Non toccare `InscriptionService` (zero code change)
- Non toccare `random_anti_rematch.py` (zero code change)
- Non aggiungere logica di differenziazione PARITY/CAPACITY in template o
  component Jinja (UX decision esplicita)
- Non ridefinire `STRATEGY_CONSTRAINTS[RANDOM]["odd_policies"]` per escludere
  `"no"`: il supporto resta ammesso

## I/O & Edge-Case Matrix

| # | Scenario | Input / State | Expected Output / Behavior | Note |
|---|----------|--------------|---------------------------|------|
| 1 | Random + NO, 1° iscritto | gara vuota | accettato, `is_waitlist=False` | 0→1 dispari ma il primo va sempre accettato |
| 2 | Random + NO, 2° iscritto | 1 attivo | accettato, `is_waitlist=False` | 1→2 pari |
| 3 | Random + NO, 3° iscritto | 2 attivi | waitlist, `reason=PARITY`, `position=1` | 2→3 dispari |
| 4 | Random + NO, 4° iscritto | 2 attivi + 1 parity | nuovo attivo + 3° promosso | 3→4 pari |
| 5 | Random + NO, 5° iscritto | 4 attivi | waitlist, `reason=PARITY`, `position=1` | 4→5 dispari |
| 6 | Random + NO, uninscribe 1° con 4 attivi | 4 attivi | 2 attivi + 1 parity + 1 deleted | 4→3 dispari → demote ultimo |
| 7 | Random + NO, `start_first_round` con 5 iscritti (4 attivi + 1 parity) | gara in SETUP, 5 iscritti | round creati con soli 4 active_players | Verifica che strategia ignori parity waitlist |
| 8 | Random + NO, `start_first_round` con 4 iscritti (pari) | 4 attivi, 0 waitlist | round creati, 2 pair generati | Smoke test baseline |
| 9 | Random + NO + max_participants=4, 5° iscritto | 4 attivi | waitlist, `reason=CAPACITY` (non PARITY) | Coerente con test_parity_waitlist.py::test_parity_check_before_capacity_check ma con strategy=random |

## Code Map

- `tests/new/integration/test_random_odd_policy_no.py` — **NUOVO**, copre scenari 1-9
- `models/matchmaking/CLAUDE.md` — aggiornare sezione "Random Anti-Rematch" con
  nota su `OddNumberPolicy.NO` + link a questo spec e a `inscription_service.py`
- `_bmad-output/implementation-artifacts/deferred-work.md` — chiudere G2 come
  ✅ DONE con data 2026-04-19
- `_bmad-output/handoffs/random-next-steps.md` — aggiornare sezione G2 come risolta

## Tasks & Acceptance

**Execution:**
- [ ] `tests/new/integration/test_random_odd_policy_no.py` — scrivere test per
      scenari 1-9. Riutilizzare pattern fixture da `test_parity_waitlist.py`
      ma con `matchmaking_strategy="random"` e `first_round_policy="random"`.
- [ ] `models/matchmaking/CLAUDE.md` — aggiungere paragrafo su `NO` in sezione
      "Random Anti-Rematch"
- [ ] `_bmad-output/implementation-artifacts/deferred-work.md` — chiusura G2
- [ ] `_bmad-output/handoffs/random-next-steps.md` — aggiornamento G2

**Acceptance Criteria:**
- Given gara Random + policy NO + 5 iscritti, when tutti si iscrivono in
  sequenza, then il 3° è in PARITY waitlist dopo la sua inscription, il 3° è
  promosso quando arriva il 4°, il 5° è in PARITY waitlist
- Given gara Random + policy NO + 4 attivi, when `start_first_round` viene
  chiamato, then i round sono creati con esattamente 4 active_players (2 pair)
- Given gara Random + policy NO + 4 attivi + 1 in PARITY waitlist, when
  `start_first_round` viene chiamato, then il parity waitlist NON compare in
  nessun match del primo round
- Given gara Random + policy NO + max_participants=4 + 5° iscritto, when si
  iscrive, then `waitlist_reason == CAPACITY` (non PARITY). Mirror del test
  esistente per Amalfi
- Given `models/matchmaking/CLAUDE.md`, when si legge "Random Anti-Rematch",
  then esiste paragrafo "Odd Player Handling: NO policy" con link a
  `inscription_service.py` e a questo spec
- `pytest tests/new/integration/test_random_odd_policy_no.py -v -n 4` passa
- `pyright` zero errori
- `black . && flake8` clean

## Design Notes

### Perché integration-level, non unit

I test unit di `test_parity_waitlist.py` già verificano che `InscriptionService`
fa il suo lavoro correttamente. Duplicarli con `strategy="random"` sarebbe
ridondante al livello inscription (il service legge `gara.odd_number_policy`,
non `gara.matchmaking_strategy`, quindi il comportamento è identico per
costruzione). Il valore aggiunto dei nuovi test è al livello
**`start_first_round` + strategy** — verificare che il pool passato alla
strategia sia correttamente filtrato e che la strategia Random (con le sue
peculiarità: `creates_all_rounds_at_startup=True`, data source ibrido
`Match.query` + `PlayerEncounterService`) non rompa l'invariante "solo
non-waitlist partecipano".

### Perché 5 iscritti è un buon boundary

- 4 attivi + 1 parity waitlist è il minimo per esibire il filtro
- 4 è divisibile per 2 ma anche per trio (1 coppia + 1 trio in config alternativa):
  basta verificare che l'exclude del parity waitlist funzioni, le varianti
  trio sono già coperte da `test_random_anti_rematch_strategy.py`

### Why no UI differentiation

Decisione UX 2026-04-19: l'utente in parity waitlist non deve agire
diversamente da uno in capacity waitlist. In entrambi i casi aspetta un
evento automatico (promozione) senza sua azione. Il messaggio "in lista
d'attesa" è semanticamente corretto per entrambi. Differenziare UI
aggiungerebbe complessità percepita senza beneficio pratico.

## Verification

**Commands:**
- `pytest tests/new/integration/test_random_odd_policy_no.py -v -n 4 2>&1 | tail -1` — tutti i test passano
- `pytest tests/new/unit/test_parity_waitlist.py -v -n auto 2>&1 | tail -1` — nessuna regressione sui test esistenti
- `pyright` — 0 errori
- `black . && flake8` — clean

</frozen-after-approval>
