---
title: 'Deduplica Sentry events su EventBus handler failures'
type: 'bugfix'
created: '2026-04-05'
status: 'done'
baseline_commit: '00382c8'
context: ['CLAUDE.md', 'models/events/base.py']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Emerso dalla review di `spec-eventbus-error-monitoring`. Sentry SDK ha `LoggingIntegration` abilitata di default con `event_level=ERROR`, che cattura automaticamente ogni `logger.error()` come evento Sentry. In `EventBus.publish()` il flusso è: (1) `EventHandler.__call__` logga error+raise; (2) `publish()` cattura e logga error; (3) il nuovo `_capture_handler_exception()` chiama `capture_exception()` esplicito. Risultato: 1 singola failure di handler → 3 event Sentry (stessa issue via fingerprint, ma event count 3x → billing/rate-limit inflation su GlitchTip).

**Approach:** Usare l'API ufficiale `sentry_sdk.integrations.logging.ignore_logger("models.events.base")` per istruire `LoggingIntegration` a NON auto-catturare i log provenienti dal logger EventBus. Il nostro `_capture_handler_exception()` esplicito resta l'unica fonte di event Sentry per gli handler failures, con tutto il suo rich `extra` context (event_type, event_id, handler_name, domain). I `logger.error` restano integri per il log locale (file/stream handlers Python standard funzionano normalmente).

## Boundaries & Constraints

**Always:**
- Chiamata a `ignore_logger("models.events.base")` a livello di modulo, gated da `_sentry_available`, eseguita una sola volta all'import di `models.events.base`.
- Import di `ignore_logger` dentro lo stesso try/except ImportError già esistente, così il fallback no-op è identico.
- Il log locale (`logger.error(exc_info=True)`) rimane invariato per visibilità in file/stdout/journald.
- Il nostro explicit `_capture_handler_exception()` e `add_breadcrumb()` restano l'unica fonte di dati Sentry per EventBus.

**Ask First:**
- Nessuna — scope chiuso.

**Never:**
- Non disabilitare `LoggingIntegration` globalmente in `app.py` (impatto fuori scope).
- Non alzare `event_level` di LoggingIntegration a CRITICAL (impatto fuori scope).
- Non toccare `app.py` — la fix è locale al modulo EventBus.
- Non rimuovere/modificare i `logger.error` esistenti.
- Non introdurre `before_send` hooks Sentry (over-engineering).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Sentry installed + init, handler failure | DSN attivo, handler solleva | 1 solo event Sentry (explicit capture), log locale regolare | N/A |
| Sentry installed + no init (dev) | sentry_sdk imported, no DSN | ignore_logger chiamato ma inerte, log locale regolare | N/A |
| Sentry not installed | ImportError all'import | ignore_logger mai chiamato, fallback no-op | ImportError catturato |
| Logger diverso logga ERROR | `routes/app.py` usa `logger.error` | Comportamento invariato, LoggingIntegration cattura normalmente | N/A |
| Future contributor aggiunge log a EventBus | nuovo `logger.error` in models/events/* | Se è `models.events.base`, silenziato; altrimenti auto-capture normale | N/A (limite noto) |

</frozen-after-approval>

## Code Map

- `models/events/base.py` -- modulo-level import guard (L20-29) — aggiungere `ignore_logger(__name__)` dentro il try
- `models/events/base.py` -- `EventHandler.__call__` (L99-107) — log.error preesistente, NON modificare
- `models/events/base.py` -- `EventBus.publish` (L249-255) — log.error preesistente, NON modificare
- `tests/new/unit/test_event_system.py` -- aggiungere test che verifica `ignore_logger` viene chiamato con il namespace corretto

## Tasks & Acceptance

**Execution:**
- [x] `models/events/base.py` -- dentro il `try: import sentry_sdk as _sentry_sdk` esistente, importare anche `from sentry_sdk.integrations.logging import ignore_logger` e chiamarlo con `ignore_logger(__name__)` prima del `_sentry_available = True` -- taglia duplicati event Sentry
- [x] `tests/new/unit/test_event_system.py` -- nuovo test `test_eventbus_logger_is_ignored_by_sentry_logging_integration`: verifica che `"models.events.base"` è presente in `sentry_sdk.integrations.logging._IGNORED_LOGGERS` dopo l'import del modulo -- garantisce la dedup attiva

**Acceptance Criteria:**
- Given il modulo `models.events.base` importato con `sentry_sdk` disponibile, when si ispeziona `sentry_sdk.integrations.logging._IGNORED_LOGGERS`, then contiene `"models.events.base"`.
- Given `sentry_sdk` non installato, when `models.events.base` viene importato, then nessun `ImportError` propaga e il modulo resta funzionante (fallback esistente invariato).
- Given un handler EventBus fallisce, when Sentry è configurato, then viene generato esattamente 1 event Sentry (quello di `_capture_handler_exception`), non 3.

## Verification

**Commands:**
- `pyright` -- expected: 0 errors
- `pytest tests/new/unit/test_event_system.py -v -n auto 2>&1 | tail -1` -- expected: all passed
- `pytest tests/new/ -n 4 2>&1 | tail -1` -- expected: nessuna regressione
- `black . && flake8 models/events/base.py` -- expected: clean
