---
title: 'ADR-026 Reset Match Preserves Pair Semantics — Implementation'
type: 'bugfix'
created: '2026-04-19'
status: 'done'
baseline_commit: '2b6feb4'
context:
  - 'docs/adr/ADR-026-reset-match-preserves-pair-semantics.md'
  - 'docs/adr/ADR-002-fix-anti-rematch-encounter-cleanup.md'
  - 'CLAUDE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `RackService.reset_match_complete` cancella il `PlayerEncounter` del pair resettato, causando una finestra di inconsistenza con `Match.query` (che preserva il pair). La semantica reale del reset, confermata dal product owner, è "correzione score, pair preservato" — l'encounter deve restare. ADR-002 aveva codificato il comportamento opposto trattando erroneamente reset e cancel_round come la stessa operazione.

**Approach:** Rimuovere la cancellazione di `PlayerEncounter` dal reset (e rimuovere il metodo `delete_encounter` come dead code). Invertire il test di regressione che enforza la semantica sbagliata. Annotare ADR-002 come superseded-in-part. Estrarre le definizioni canoniche delle operazioni di lifecycle (reset/bulk-reset/cancel) in `models/competition/CLAUDE.md` come riferimento unico, causa prima della confusione originale.

## Boundaries & Constraints

**Always:**
- Mantenere invariata la cleanup dentro `AdvancedRoundManager.cancel_round` (via `delete_round_encounters`) — è corretta e necessaria
- Mantenere invariato `PlayerEncounter.record_encounter` (già idempotente, non va toccato)
- Seguire le convenzioni progetto: `utc_now()` da `models.base`, nessun `datetime.now()`
- Pyright 0 errori, `black`+`flake8` puliti, unit test `-n auto`, integration test `-n 4`
- Invertire test rinominandolo `test_contract_reset_preserves_encounter` (prefisso `test_contract_` segnala contratto vs regressione)

**Ask First:**
- Se emergono caller sconosciuti di `PlayerEncounter.delete_encounter` (oltre a `RackService.reset_match_complete`): grep ha confermato 1 solo caller, ma ri-verificare prima di rimuovere il metodo
- Se modifiche a `models/competition/CLAUDE.md` richiedono ristrutturare altre sezioni oltre ad aggiungere "Match Lifecycle Operations"

**Never:**
- NON modificare `cancel_round`, `delete_round_encounters`, `bulk_reset_round_matches` logic
- NON modificare `record_encounter`, `have_played`, `record_match_encounters`
- NON toccare `tiebreaker`, `gara_bye_challenge`, `TrioMatch`, `RackService.reset` trio path
- NON alterare il naming degli altri test esistenti di `test_anti_rematch_regression.py`
- NON aggiungere nuovi schema/migrazioni

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Reset match completed (2-player) | Match P1 vs P2, `PlayerEncounter(P1,P2)` esistente | Match → PENDING/PLAYING, scores=0, winner=None, `PlayerEncounter(P1,P2)` **preservato** | N/A |
| Ri-complete dopo reset | Match P1 vs P2 in PLAYING, encounter già esiste | `_record_encounter` invocato → `record_encounter` ritorna l'esistente (idempotenza), nessun duplicato, nessuna eccezione UNIQUE | N/A |
| Reset match trio | Match trio A,B,C completato, 3 encounter (A,B)(A,C)(B,C) | TrioScoringService.reset invocato, tutti e 3 encounter **preservati** | N/A |
| Reset match bye | `match.is_bye=True` | `ValueError("Non puoi resettare una partita bye!")` come oggi | ValueError preservato |
| Cancel round dopo reset | Match resettati → status PENDING, encounter preservati; cancel_round su quel round | Match eliminati, encounter eliminati via `delete_round_encounters` (flow invariato) | N/A |
| bulk_reset_round_matches | Round con N match completed | Ciascun match resettato via `reset_match_with_validation` → `reset_match_complete` (senza cleanup encounter), progressione aggiornata | Errore per-match raccolto, continua |

</frozen-after-approval>

## Code Map

- `models/match/rack_service.py` — rimuovere blocco `delete_encounter` righe 127-135; aggiornare docstring righe 102-104
- `models/classification/models.py` — rimuovere metodo `PlayerEncounter.delete_encounter` (righe 521-546 circa)
- `tests/new/unit/test_anti_rematch_regression.py` — rinominare e invertire `test_encounter_cleanup_on_match_reset` (righe 549-655); linkare ADR-026 nel docstring
- `docs/adr/ADR-002-fix-anti-rematch-encounter-cleanup.md` — aggiornare banner Stato
- `_bmad-output/handoffs/random-next-steps.md` — marcare G3 come resolved (misdiagnosis)
- `_bmad-output/implementation-artifacts/spec-random-anti-rematch.md` — rimuovere nota "Limitation documentata: reset match + Random"
- `models/competition/CLAUDE.md` — aggiungere sezione "Match Lifecycle Operations" (glossario canonico + tabella riassuntiva)

## Tasks & Acceptance

**Execution:**

- [x] `models/match/rack_service.py` -- Rimuovere righe 127-135 (import locale PlayerEncounter + chiamata `delete_encounter`). Aggiornare docstring di `reset_match_complete` per eliminare il paragrafo "IMPORTANT: Also deletes the PlayerEncounter..." e sostituirlo con nota che l'encounter è preservato by design (link ADR-026) -- Core change: allinea la semantica runtime alla decisione.
- [x] `models/classification/models.py` -- Rimuovere il metodo `PlayerEncounter.delete_encounter` (signature, decoratori `@staticmethod`/`@transactional`, docstring, body). Non toccare `record_encounter`, `have_played`, `delete_round_encounters` -- Dead code elimination dopo rimozione dell'unico caller.
- [x] `tests/new/unit/test_anti_rematch_regression.py` -- Rinominare `test_encounter_cleanup_on_match_reset` → `test_contract_reset_preserves_encounter`. Invertire l'assertion finale: da `assert not PlayerEncounter.have_played(...)` a `assert PlayerEncounter.have_played(...)`. Aggiornare docstring per esprimere il contratto (reset preserva pair) e linkare `docs/adr/ADR-026-reset-match-preserves-pair-semantics.md` -- Enforce il nuovo contratto, rimuovi enforcement semantica sbagliata.
- [x] `docs/adr/ADR-002-fix-anti-rematch-encounter-cleanup.md` -- Aggiornare riga "**Stato**: Accepted" → "**Stato**: Accepted (superseded in part by [ADR-026](ADR-026-reset-match-preserves-pair-semantics.md) per la parte `reset_match_complete`; la parte `cancel_round` resta valida)" -- Bidirectional link ADR.
- [x] `_bmad-output/handoffs/random-next-steps.md` -- Sezione G3: cambiare status in "resolved (misdiagnosis)" con link a ADR-026; aggiornare frontmatter `status` se riflette G3 open -- Handoff coerente con stato reale.
- [x] `_bmad-output/implementation-artifacts/spec-random-anti-rematch.md` -- Rimuovere la nota "Limitation documentata: reset match + Random" (circa righe 192-196) e l'acceptance criterion riga 137 (che asseriva "encounter_matrix non lo contiene") va aggiornato per riflettere il nuovo contratto o rimosso -- Spec coerente con ADR-026.
- [x] `models/competition/CLAUDE.md` -- Aggiungere sezione "## Match Lifecycle Operations" con definizioni canoniche di `reset_match_complete`, `bulk_reset_round_matches`, `cancel_round` + tabella riassuntiva (estratta dall'Operations Glossary dell'ADR-026). Linkare ADR-026 come razionale -- Unico punto di riferimento canonico.
- [x] `models/competition/round_manager.py` (scope esteso, Change Log entry #1) -- Aggiornare precondition di `cancel_round` (righe ~195-200): `(score or 0) > 0` invece di `score is not None`. Aggiungere commento inline che cita ADR-026 -- Fix bug latente scoperto durante verify; cancel_round falliva silenziosamente dopo reset.
- [x] `docs/adr/ADR-026-reset-match-preserves-pair-semantics.md` (scope esteso) -- Aggiungere sezioni "Bug latente in cancel_round esposto dal fix" + decisione #7 + conseguenza positiva + nota implementativa #8 -- Documentazione dello scope esteso.
- [x] Pre-existing flake8 fixes nei file toccati (feedback utente durante verify) -- Riparare import non usati (F401), line-too-long (E501) e redefinition (F811) in `models/classification/models.py` e `tests/new/unit/test_anti_rematch_regression.py` -- Policy progetto: flake8 errors pre-esistenti vanno comunque riparati.
- [x] Eseguire pipeline verifica: `black .`, `flake8`, `pyright`, unit `-n auto`, integration `-n 4` -- Gate di qualità.

**Acceptance Criteria:**

- **AC1 (core behavior):** Given match completato con `PlayerEncounter(P1,P2)`, when `RackService.reset_match_complete(match.id)` invocato, then `PlayerEncounter.have_played(gara_id, P1, P2)` ritorna `True`.
- **AC2 (idempotenza):** Given match resettato, when il match viene ri-completato tramite `MatchService.to_completed`, then nessun duplicato `PlayerEncounter` creato e nessuna eccezione UNIQUE constraint.
- **AC3 (cancel_round invariato):** Given round con match completati, when `AdvancedRoundManager.cancel_round(gara_id, round_number)` invocato, then tutti gli encounter del round sono eliminati (`test_encounter_cleanup_on_round_cancel` pass senza modifiche).
- **AC4 (trio collaterale):** Given match trio completato con 3 encounter, when reset invocato, then tutti e 3 encounter preservati (oggi solo 1/3 veniva erroneamente cancellato; fix collaterale).
- **AC5 (dead code rimosso):** `grep -rn "delete_encounter" models/ routes/ tests/` ritorna 0 riferimenti runtime al metodo singolo (possono restare `delete_round_encounters` che è diverso).
- **AC6 (test invertito):** `test_contract_reset_preserves_encounter` pass con il nuovo assert; `test_encounter_cleanup_on_match_reset` non esiste più.
- **AC7 (CI gate):** `pyright` 0 errori, `black`+`flake8` puliti, `pytest tests/new/unit/ -n auto` pass, `pytest tests/new/integration/ -n 4` pass.
- **AC8 (doc consistency):** `docs/adr/ADR-002` ha banner superseded-in-part; `models/competition/CLAUDE.md` include sezione "Match Lifecycle Operations"; handoff e spec Random coerenti.

## Spec Change Log

### Entry #1 — 2026-04-19 — cancel_round precondition bug (scope extension)

**Trigger:** durante la verify finale, `test_encounter_cleanup_on_round_cancel` (non toccato da questo spec) ha fallito con `"Encounter should NOT exist after round cancel"`.

**Finding:** il test passava silenziosamente prima del fix perché la cleanup di `PlayerEncounter` dentro `reset_match_complete` (rimossa da questo ADR) faceva da workaround per un bug latente in `cancel_round`. Precondition errata: `m.player1_score is not None or m.player2_score is not None`. Dopo reset score = 0 (non None) → `0 is not None == True` → cancel_round blocca con "Alcuni match hanno già risultati parziali". Il test non asseriva `success=True` del ritorno di cancel_round, quindi il fallimento passava inosservato.

**Amendment:** aggiunti 3 task (cancel_round precondition fix, ADR update per documentare extension, pre-existing flake8 fix richiesto da policy utente). ADR-026 esteso con sezione "Bug latente in cancel_round esposto dal fix" + decisione #7 + conseguenza positiva + nota implementativa #8. Scope extension approvata dall'utente ("scelgo di estendere lo scope di ADR-026").

**Known-bad state avoided:** cancel_round che fallisce silenziosamente dopo reset, con encounter non puliti. Senza questo fix, ADR-026 avrebbe corretto solo una metà del problema, rendendo l'altra metà visibile al prossimo run (test fallisce invece di passare accidentalmente).

**KEEP:** naming `test_contract_*` (distinto da `test_regression_*`) — ha dimostrato valore esplicitando che enforza comportamento user-facing. La precondition fix `(score or 0) > 0` è semanticamente più corretta: mantiene supporto sia per match mai giocati (None) sia per match resettati (0); "risultato parziale" = score > 0 (almeno un rack vinto).

## Design Notes

**Ordine di esecuzione (importante):** il codice runtime prima (tasks 1-2), poi test (task 3), poi docs (tasks 4-7), poi verifica (task 8). Motivo: se il test viene invertito prima della rimozione del metodo `delete_encounter`, la rimozione farebbe fallire il test originale invece del nuovo — ambiguità di segnale.

**`have_played` asimmetria di chiamata:** il test di contratto deve invocare `have_played` con entrambe le direzioni `(p1,p2)` e `(p2,p1)` come già fa il test originale — l'implementazione gestisce simmetria via `min/max` ma il test di contratto deve continuare a proteggere la proprietà.

**Nota importante sui file handoff/spec:** sono artifact di processo sotto `_bmad-output/` — le modifiche a questi file non impattano runtime o test. Possono essere aggiornati in qualsiasi momento prima del commit finale.

## Verification

**Commands:**
- `pyright` -- expected: 0 errors
- `black --check . && flake8` -- expected: no issues
- `pytest tests/new/unit/test_anti_rematch_regression.py -v -n auto` -- expected: all pass, including renamed `test_contract_reset_preserves_encounter`
- `pytest tests/new/unit/ -n auto` -- expected: all pass (~870 tests)
- `pytest tests/new/integration/ -n 4` -- expected: all pass (~225 tests)
- `grep -rn "PlayerEncounter\.delete_encounter\b" models/ routes/ tests/new/` -- expected: 0 matches (method removed)
- `grep -rn "delete_round_encounters" models/` -- expected: still present in cancel_round (round_manager.py) and models.py (definition)

**Manual checks (if no CLI):**
- Ispezionare docstring aggiornato di `RackService.reset_match_complete` — deve menzionare esplicitamente "PlayerEncounter preserved by design" con riferimento ad ADR-026
- Ispezionare `models/competition/CLAUDE.md` sezione "Match Lifecycle Operations" — deve contenere le 3 operazioni con intent, semantica, caller, e la tabella riassuntiva
