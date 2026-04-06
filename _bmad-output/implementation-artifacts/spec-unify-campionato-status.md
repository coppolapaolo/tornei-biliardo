---
title: 'Unificare get_status e compute_campionato_status'
type: 'refactor'
created: '2026-04-06'
status: 'done'
baseline_commit: '28973f6'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `Campionato.get_status()` e `compute_campionato_status()` implementano la stessa logica di derivazione stato indipendentemente. Qualsiasi modifica futura a uno rischia divergenza silenziosa dall'altro (già successo con `terminated_at`).

**Approach:** Rendere `get_status()` un thin wrapper che delega a `compute_campionato_status()`, mantenendo quest'ultima come single source of truth (è già una pure function testabile indipendentemente).

## Boundaries & Constraints

**Always:** Tutti i caller esistenti (11 per `get_status`, 4 per `compute_campionato_status`) devono continuare a funzionare identicamente. Zero cambi di firma o tipo di ritorno.

**Ask First:** Se i test esistenti per `get_status` dovessero risultare fragili dopo la delega (mock diversi, etc.).

**Never:** Cambiare la logica di derivazione stato. Rinominare metodi o funzioni. Toccare caller.

</frozen-after-approval>

## Code Map

- `models/campionato/models.py:132-172` -- `get_status()`: instance method, 11 caller. Diventa thin wrapper.
- `models/campionato/statistics_service.py:349-394` -- `compute_campionato_status()`: pure function, source of truth. Resta invariata.

## Tasks & Acceptance

**Execution:**
- [x] `models/campionato/models.py` -- Sostituire il body di `get_status()` con `return compute_campionato_status(self)` -- Elimina duplicazione
- [x] `tests/new/unit/` -- Verificare che i test esistenti per entrambi i metodi passino senza modifiche -- Conferma equivalenza comportamentale (1152 passed)

**Acceptance Criteria:**
- Given qualsiasi stato di campionato (SETUP, REGISTRATION_OPEN, IN_PROGRESS, COMPLETED, TERMINATED), when chiamo `campionato.get_status()`, then il risultato è identico a `compute_campionato_status(campionato)`
- Given tutti i test della suite, when eseguo `pytest tests/new/ -n 4`, then 0 failure

## Verification

**Commands:**
- `pyright` -- expected: 0 errors
- `pytest tests/new/ -n 4` -- expected: all pass

## Suggested Review Order

- Thin wrapper: 33 righe di logica inline sostituite con una singola delega
  [`models.py:132`](../../models/campionato/models.py#L132)

- Source of truth invariata — la pure function che ora serve entrambi i path
  [`statistics_service.py:349`](../../models/campionato/statistics_service.py#L349)
