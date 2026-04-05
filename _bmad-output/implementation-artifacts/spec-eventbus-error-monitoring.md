---
title: 'EventBus error monitoring via Sentry'
type: 'feature'
created: '2026-04-05'
status: 'done'
baseline_commit: '26d97b0'
context: ['CLAUDE.md', 'models/events/base.py']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `EventBus.publish()` cattura le eccezioni degli handler e le logga con `logger.error(..., exc_info=True)` ma non le segnala al sistema di error tracking. Se un handler (es. gamification, notifiche) fallisce ripetutamente in produzione, nessun alert viene sollevato e il problema resta invisibile finché qualcuno non apre i log del server. La review AR-8 ha identificato questo come gap di osservabilità.

**Approach:** Riutilizzare l'infrastruttura Sentry/GlitchTip già configurata in `app.py` (via `GLITCHTIP_DSN`). Nell'`except` di `publish()` chiamare `sentry_sdk.capture_exception(e)` con contesto aggiuntivo (event type, handler name, event id). Aggiungere inoltre un `sentry_sdk.add_breadcrumb()` su ogni `publish()` di successo per dare visibilità al flusso eventi prima di un eventuale errore. Zero impatto quando il DSN non è configurato (dev/test) perché `sentry_sdk` è no-op senza init.

## Boundaries & Constraints

**Always:**
- Import di `sentry_sdk` lazy (solo al primo uso dentro `publish()`), con `try/except ImportError` per restare compatibili con ambienti che non installano la dipendenza.
- `capture_exception` deve includere `extra` context con chiavi: `event_type`, `event_id`, `handler_name`, `event_domain`.
- Il breadcrumb success usa `category="event_bus"`, `level="info"`, `data` con `event_type` + numero handler eseguiti.
- Il log `logger.error(..., exc_info=True)` esistente rimane invariato — Sentry è aggiunto, non sostituisce.
- La cattura Sentry non deve mai far fallire `publish()`: se `capture_exception` stesso solleva, swallow con `logger.warning`.
- I test esistenti di error isolation (`test_handler_error_isolation`) devono continuare a passare senza modifiche.

**Ask First:**
- Nessuna decisione umana attesa durante l'esecuzione — scope chiuso.

**Never:**
- Non introdurre counter in-memory, soglie hardcoded, o dedup custom (Sentry gestisce grouping nativamente).
- Non cambiare la semantica del flusso eventi: tutti gli handler continuano a eseguire anche se uno fallisce.
- Non fare `sentry_sdk.init()` qui — resta responsabilità esclusiva di `app.py`.
- Non aggiungere breadcrumb dentro il loop degli handler (un breadcrumb per `publish`, non per handler).
- Non usare `sentry_sdk.capture_message` — solo `capture_exception` per preservare stack trace.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Publish success, DSN configurato | Evento con N handler OK | Breadcrumb aggiunto, tutti handler eseguiti | N/A |
| Handler solleva, DSN configurato | 1 handler fallisce, 2 OK | 2 handler eseguono, `capture_exception` invocato 1x con `extra` context | log.error + Sentry capture |
| Handler solleva, DSN non configurato | sentry_sdk init mai chiamato | log.error normale, capture_exception no-op | Sentry internamente no-op |
| sentry_sdk non installato | `import sentry_sdk` fallisce | Fallback silent: solo log.error come oggi | ImportError catturato una volta |
| capture_exception stesso solleva | Bug nel client Sentry | Publish continua, log.warning del fallimento capture | Doppio try/except |
| EventBus disabilitato | `_enabled = False` | Nessun handler, nessun breadcrumb, nessun capture | Return early (già esistente) |
| Publish senza handler registrati | `handlers = []` | Breadcrumb emesso (success con 0 handlers) | N/A |

</frozen-after-approval>

## Code Map

- `models/events/base.py` -- `EventBus.publish` (L173-200) — punto unico di integrazione; aggiungere capture + breadcrumb
- `models/events/base.py` -- `EventHandler.__call__` (L88-94) — NON toccare: già logga ma rilancia verso `publish()`
- `app.py` -- L40-50 — pattern esistente di init Sentry/GlitchTip (solo riferimento, no modifiche)
- `tests/new/unit/test_event_system.py` -- `test_handler_error_isolation` (L190) — pattern esistente per test handler fallimento; aggiungere test per capture/breadcrumb

## Tasks & Acceptance

**Execution:**
- [x] `models/events/base.py` -- aggiungere modulo-level import guard: `try: import sentry_sdk; _sentry_available = True; except ImportError: _sentry_available = False` -- fallback pulito se dipendenza assente
- [x] `models/events/base.py` -- in `EventBus.publish`, prima del loop handler aggiungere breadcrumb `sentry_sdk.add_breadcrumb(category="event_bus", level="info", message=f"publish {event.get_event_type()}", data={"event_type": ..., "event_id": ..., "handler_count": len(handlers)})` gated da `_sentry_available` -- visibilità flusso
- [x] `models/events/base.py` -- nell'`except Exception as e` di `publish`, dopo `logger.error(...)` aggiungere chiamata a helper `_capture_handler_exception(e, event, handler)` che invoca `sentry_sdk.capture_exception(e)` con `sentry_sdk.push_scope()` + `scope.set_extra(...)` per `event_type`, `event_id`, `handler_name`, `event_domain` -- alerting produzione
- [x] `models/events/base.py` -- il helper `_capture_handler_exception` deve wrappare la chiamata Sentry in try/except che logga con `logger.warning("Sentry capture failed: %s", e)` senza rilanciare -- safety net
- [x] `tests/new/unit/test_event_system.py` -- nuovo test `test_handler_error_captured_by_sentry`: mock `sentry_sdk.capture_exception`, registra handler fallimento, publish evento, assert mock chiamato 1x e assert `set_extra` chiamato con chiavi attese -- copre capture path
- [x] `tests/new/unit/test_event_system.py` -- nuovo test `test_publish_adds_breadcrumb`: mock `sentry_sdk.add_breadcrumb`, publish evento con 2 handler, assert breadcrumb 1x con `data["handler_count"]==2` e `category=="event_bus"` -- copre breadcrumb path
- [x] `tests/new/unit/test_event_system.py` -- nuovo test `test_capture_failure_does_not_break_publish`: mock `capture_exception` che solleva `RuntimeError`, registra handler che fallisce + handler OK, publish, assert handler OK eseguito e nessuna eccezione propagata -- safety net

**Acceptance Criteria:**
- Given un handler registrato che solleva `RuntimeError`, when `EventBus.publish(event)` viene chiamato con Sentry mock attivo, then `sentry_sdk.capture_exception` è invocato esattamente una volta con extra context contenente `event_type`, `event_id`, `handler_name`, `event_domain`.
- Given 3 handler registrati (1 fallisce, 2 OK), when publish viene chiamato, then tutti i 3 handler vengono invocati, il flusso non solleva, e capture_exception è chiamato 1 sola volta.
- Given `sentry_sdk` non installato (simulato con `_sentry_available=False`), when publish con handler fallimento viene chiamato, then il comportamento è identico a oggi (solo `logger.error`) e nessun `ImportError` propaga.
- Given capture_exception solleva internamente, when un handler fallisce, then publish completa senza propagare e viene loggato un warning.
- Given EventBus publish di successo con 2 handler OK, when Sentry mock è attivo, then `add_breadcrumb` è invocato 1 volta con `category="event_bus"` e `data["handler_count"]==2`.

## Verification

**Commands:**
- `pyright` -- expected: 0 errors
- `pytest tests/new/unit/test_event_system.py -v -n auto 2>&1 | tail -1` -- expected: all passed (3 nuovi + esistenti invariati)
- `pytest tests/new/ -n 4 2>&1 | tail -1` -- expected: nessuna regressione
- `black . && flake8` -- expected: clean
