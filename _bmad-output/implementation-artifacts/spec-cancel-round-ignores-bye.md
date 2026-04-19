---
title: 'cancel_round ignora i bye nel check matches_with_results'
type: 'bugfix'
created: '2026-04-19'
status: 'done'
baseline_commit: 'ee4c6b7a9eec011b257ad8f418d3d15db585dac5'
context:
  - 'docs/adr/ADR-026-reset-match-preserves-pair-semantics.md'
  - 'CLAUDE.md' # regola 3, 7, transazioni
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `AdvancedRoundManager.cancel_round` tratta ogni match con `score > 0` come "risultato parziale" e blocca la cancellazione del round. I bye vengono creati con `player1_score = round_distance` (convenzione di persistenza per la classification), quindi **ogni round con almeno un bye è un-cancellabile**. `reset_match_complete` su un bye rifiuta esplicitamente con `ValueError` → il director è senza via d'uscita.

**Approach:** Escludere `is_bye=True` dal predicato `matches_with_results` in `cancel_round`. Il bye è artefatto algoritmico (non input utente) → non conta come "risultato parziale". I walkover 2-player e trio (azioni umane: forfeit) restano inclusi nel predicato e continuano a bloccare — vanno resettati deliberatamente come i match con rack giocati.

## Boundaries & Constraints

**Always:**
- Mantenere tutte le altre precondizioni di `cancel_round`: tiebreaker attivo, round lock status, `round_number >= gara.current_round`, gara status.
- `reset_match_complete` continua a rifiutare i bye (status quo, coerente con "bye è sempre in stato iniziale").
- Nessun cambio alla creation logic dei bye (`player1_score = bye_score` in `round_creation.py`).
- `PlayerEncounter` per il round cancellato viene cancellato come oggi (il bye non ne crea comunque).

**Ask First:**
- Se emergono match non-bye con score persistito ma senza rack che NON sono walkover (caso non noto) → HALT.
- Se si presenta un bisogno di estendere il filtro ai walkover → HALT (scope-creep vs S1 deciso).

**Never:**
- Estendere l'esclusione ai walkover (2-player forfeit o trio walkover) — scope S1.
- Aggiungere force flag, bottoni UI nuovi, nuove stringhe i18n.
- Modificare la semantica di `reset_match_complete`.
- Cancellare un round con match che hanno rack reali giocati o walkover — continua a richiedere reset prima.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Round con solo bye + pending | 1 bye (score=5), 3 match pending (score=None/0) | `cancel_round` ritorna `(True, "Turno X cancellato...")`, round e matches eliminati | N/A |
| Round all-bye (teorico) | Solo match con `is_bye=True` | `cancel_round` ritorna `(True, ...)`, tutti i bye eliminati | N/A |
| Round con bye + match reale giocato | 1 bye + 1 match 5-3 | `cancel_round` ritorna `(False, "Alcuni match hanno già risultati parziali...")` | Messaggio esistente |
| Round con bye + walkover 2-player | 1 bye + 1 match forfeit (score=5-0, is_bye=False) | `cancel_round` ritorna `(False, "Alcuni match hanno già risultati parziali...")` | Messaggio esistente |
| Round con bye + trio walkover | 1 bye + 1 trio walkover (score=5-0, is_bye=False, is_trio=True) | `cancel_round` ritorna `(False, "Alcuni match hanno già risultati parziali...")` | Messaggio esistente |
| Tiebreaker attivo + round con bye | `Tiebreaker.status != CANCELLED` esiste per gara | `cancel_round` ritorna `(False, "Gara certificata da spareggio...")` | Check precedente, invariato |
| Reset single-match su bye | `match.is_bye=True` | `reset_match_complete` raisa `ValueError("Non puoi resettare una partita bye!")` | Status quo |

</frozen-after-approval>

## Code Map

- `models/competition/round_manager.py` -- `AdvancedRoundManager.cancel_round`, linee ~273-277 (predicato `matches_with_results`). File da modificare.
- `models/match/rack_service.py` -- `MatchRackService.reset_match_complete` linee 115-116. File NON modificato (riferimento per invariante).
- `models/competition/round_creation.py` -- creation logic bye (linee 36-45). File NON modificato (riferimento).
- `models/match/models.py` -- `Match.is_bye` boolean column. Flag letto dal predicato.
- `tests/new/unit/test_cancel_round_bye.py` -- nuovo file unit test (6 test).

## Tasks & Acceptance

**Execution:**
- [x] `tests/new/unit/test_cancel_round_bye.py` -- crea 6 unit test TDD-red-first (vedi AC) -- establish expected behavior prima del fix
- [x] `models/competition/round_manager.py` -- aggiungi `and not m.is_bye` al list comprehension `matches_with_results` -- esclude i bye dal check "risultato parziale"
- [x] `models/competition/round_manager.py` -- aggiorna il commento del blocco `matches_with_results` per spiegare l'esclusione bye -- coerenza con ADR-026 semantics
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- sposta l'item "All-bye round è un-cancellabile" sotto `~~DONE~~` con riferimento a questa spec -- chiudere il tracker

**Acceptance Criteria:**
- Given un round con 1 bye e 3 match pending, when `cancel_round(gara_id, round_number)`, then il round viene cancellato e ritorna `(True, ...)`.
- Given un round all-bye, when `cancel_round(...)`, then il round viene cancellato.
- Given un round con 1 bye e 1 match con `score > 0` (reale o walkover), when `cancel_round(...)`, then ritorna `(False, "Alcuni match hanno già risultati parziali...")`.
- Given un match bye, when `reset_match_complete(match.id)`, then raisa `ValueError("Non puoi resettare una partita bye!")` (regression).
- Given gara con tiebreaker attivo + round con bye, when `cancel_round(...)`, then blocca per tiebreaker (check precedente invariato).
- Tutti i test esistenti in `tests/new/unit/` e `tests/new/integration/` passano invariati.
- `pyright` ritorna 0 errori. `flake8` pulito sul file modificato (fix pre-esistenti se necessari).

## Verification

**Commands:**
- `pytest tests/new/unit/test_cancel_round_bye.py -v -n auto 2>&1 | tail -1` -- expected: `6 passed`
- `pytest tests/new/unit/ -n auto 2>&1 | tail -1` -- expected: tutti pass, nessuna regressione
- `pytest tests/new/integration/ -n 4 2>&1 | tail -1` -- expected: tutti pass
- `pyright models/competition/round_manager.py 2>&1 | tail -5` -- expected: 0 errors
- `flake8 models/competition/round_manager.py tests/new/unit/test_cancel_round_bye.py` -- expected: nessun output

## Suggested Review Order

- Il fix è una singola riga nella list comprehension della precondition `matches_with_results`: esclude `is_bye=True` dal predicato "match con risultati parziali"
  [`round_manager.py:285`](../../models/competition/round_manager.py#L285)

- Il commento esteso documenta il razionale semantico (bye = artefatto algoritmico, walkover = azione umana) e la coerenza con ADR-026
  [`round_manager.py:273`](../../models/competition/round_manager.py#L273)

- 6 unit test TDD-first coprono ogni riga dell'I/O Matrix: succeed con bye+pending, succeed all-bye, blocked con real score, blocked con 2-player walkover, blocked con trio walkover, regression reset bye
  [`test_cancel_round_bye.py`](../../tests/new/unit/test_cancel_round_bye.py)

