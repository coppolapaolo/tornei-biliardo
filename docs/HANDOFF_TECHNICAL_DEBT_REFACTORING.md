# HANDOFF: Technical Debt Refactoring

**Data**: 2026-02-06
**Stato**: FASI 1-3 COMPLETATE, FASE 4 PARZIALE, FASE 5 (anti-pattern @transactional) COMPLETATA
**Valutazione complessiva architettura**: 7.5/10 → 8.8/10 (post-refactoring)

---

## Contesto

Analisi completa della struttura delle classi del progetto su tre dimensioni:
1. Gerarchia classi e pattern architetturali
2. Duplicazioni di codice
3. Aderenza ai principi SOLID

L'architettura e' solida (DDD, Strategy Pattern, Event-Driven, Service Layer con `@transactional`).
Il debito tecnico e' gestibile (~750 righe duplicate) e ben documentato (20+ ADR).

---

## Task di Refactoring

### FASE 1 - Quick Wins (basso rischio, alto impatto)

#### TASK 1.1: Consolidare permessi duplicati in `gara_manager_required`
**File**: `utils/permissions.py`
**Problema**: `gara_manager_required` (righe 57-105) reimplementa la logica di `PermissionChecker.can_manage_competition()` (gia' in `models/user/permissions.py`). Stessa cosa per `rack_manager_required` (righe 145-196).
**Soluzione**: Riscrivere entrambi i decoratori per delegare a `PermissionChecker.can_manage_competition()`, eliminando ~80 righe di logica duplicata.
**Verifica**: `pytest tests/new/ -n 4` + controllare che le route protette funzionino.
**Rischio**: BASSO - la logica nel PermissionChecker e' gia' testata e usata altrove.

```python
# PRIMA (57-105): reimplementa la logica
def gara_manager_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        gara_id = kwargs.get("gara_id") or ...
        gara = db.session.get(Gara, gara_id)
        if getattr(current_user, "is_admin", False):
            return fn(*args, **kwargs)
        if gara and getattr(gara, "campionato_id", None) is None:
            # ... 30 righe di logica duplicata ...
        return fn(*args, **kwargs)
    return wrapper

# DOPO: delega al PermissionChecker
def gara_manager_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        gara_id = kwargs.get("gara_id") or (
            request.view_args.get("gara_id") if request.view_args else None
        )
        if not PermissionChecker.can_manage_competition(current_user, gara_id):
            abort(403)
        return fn(*args, **kwargs)
    return wrapper
```

#### TASK 1.2: Eliminare `parse_date` locale duplicata
**File**: `routes/admin/competition/inscriptions.py` (righe 45-51)
**Problema**: Funzione `parse_date()` locale che duplica `parse_date_string()` di `models/shared/utils.py`. I formati sono anche leggermente diversi (mancano ISO con T).
**Soluzione**:
1. Aggiungere i formati ISO mancanti (`%Y-%m-%dT%H:%M:%S`, `%Y-%m-%dT%H:%M`) a `parse_date_string()` in `models/shared/utils.py`
2. Sostituire la funzione locale con `parse_date_string()` in `inscriptions.py`
3. La differenza: `parse_date_string` ritorna `None` se fallisce, la locale lancia `ValueError`. Mantenere il `ValueError` con un wrapper o un check esplicito.
**Verifica**: `pytest tests/new/unit/ -n auto && pytest tests/new/integration/ -n 4`

```python
# DOPO in inscriptions.py:
from models.shared.utils import parse_date_string

inscription_start = parse_date_string(start_str)
if not inscription_start:
    raise ValueError(f"Formato data non valido: {start_str}")
```

#### TASK 1.3: Centralizzare filtro "iscrizioni attive"
**File coinvolti**:
- `models/competition/models.py:693` - `Gara.get_active_inscriptions_count()`
- `models/competition/withdraw_policy_service.py:146` - `get_active_inscriptions(gara_id)`
- `models/matchmaking/strategies/base.py:355` - `_get_active_inscriptions(gara)`
- `models/matchmaking/strategies/amalfi.py:377` - `_get_active_inscriptions(gara)` (override)

**Problema**: Lo stesso filtro `is_withdrawn=False AND is_waitlist=False` e' implementato in 3-4 modi diversi.

**Soluzione**: Aggiungere class method `Inscription.active_for_gara(gara_id)` come singola fonte di verita':

```python
# models/competition/models.py (Inscription class)
@classmethod
def active_for_gara(cls, gara_id: int) -> list["Inscription"]:
    """Return active (non-withdrawn, non-waitlist) inscriptions for a gara."""
    return cls.query.filter_by(
        gara_id=gara_id, is_withdrawn=False, is_waitlist=False
    ).all()

@classmethod
def active_count_for_gara(cls, gara_id: int) -> int:
    """Count active inscriptions for a gara."""
    return cls.query.filter_by(
        gara_id=gara_id, is_withdrawn=False, is_waitlist=False
    ).count()
```

**ATTENZIONE**: `Gara.get_active_inscriptions_count()` e' usato in 20+ template Jinja2. Non rimuoverlo ma farlo delegare al nuovo metodo. Le strategy di matchmaking usano `_get_active_inscriptions()` passando l'oggetto gara (non l'id) per testabilita' con mock - mantenere il metodo nella base strategy ma farlo delegare.

**Verifica**: `pytest tests/new/ -n 4` + `pyright`

---

### FASE 2 - Error Handling (medio rischio, alto impatto)

#### TASK 2.1: Creare helper per risposte route
**File da creare**: `utils/route_helpers.py`
**Problema**: ~300 righe di error handling copy-paste in 19 file route. Due pattern ripetuti:
1. try/except con flash + redirect (196 occorrenze di `flash(..., "error")`)
2. Check AJAX con `X-Requested-With` + `jsonify` (8+ file)

**Soluzione**: Creare utility functions:

```python
# utils/route_helpers.py
from flask import request, jsonify, flash, redirect
from functools import wraps

def handle_service_action(
    action_fn,
    success_message: str,
    redirect_url: str,
    error_prefix: str = "Errore"
):
    """Execute a service action with standard error handling.

    Returns redirect response with flash message on success/error.
    """
    try:
        result = action_fn()
        flash(success_message, "success")
        return result if result else redirect(redirect_url)
    except ValueError as ve:
        flash(f"{error_prefix}: {str(ve)}", "error")
    except Exception as e:
        flash(f"Errore imprevisto: {str(e)}", "error")
    return redirect(redirect_url)


def ajax_or_redirect(success_data=None, error_msg=None, status=200, redirect_url=None):
    """Return JSON for AJAX requests or flash+redirect for regular requests."""
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    if error_msg:
        if is_ajax:
            return jsonify({"success": False, "error": error_msg}), 400
        flash(error_msg, "error")
        return redirect(redirect_url)

    if is_ajax:
        data = {"success": True}
        if success_data:
            data.update(success_data)
        return jsonify(data), status

    if redirect_url:
        return redirect(redirect_url)
```

**Approccio**: Creare le utility, applicarle a 2-3 route come proof-of-concept, poi applicare gradualmente.
**NON fare**: Refactoring di massa di tutti i 19 file in un colpo — troppo rischioso. Applicare progressivamente.
**Verifica**: `pytest tests/new/ -n 4`

---

### FASE 3 - God Class Decomposition (alto impatto, medio rischio)

#### TASK 3.1: Estrarre `GaraStatusResolver` da `Gara`
**File**: `models/competition/models.py`
**Problema**: `Gara.get_real_status()` (48 righe, 26+ branch condizionali) e `get_status_badge_info()` (logica di presentazione con classi CSS Bootstrap) mescolano business logic e UI nel modello.

**Soluzione**:
1. Creare `models/competition/status_resolver.py` con classe `GaraStatusResolver`
2. Spostare `get_real_status()` come metodo statico: `GaraStatusResolver.resolve(gara)`
3. Spostare `get_status_badge_info()` in un template helper o presenter
4. Mantenere property proxy su `Gara` per backward compatibility:
   ```python
   @property
   def real_status(self):
       return GaraStatusResolver.resolve(self)
   ```

**ATTENZIONE**:
- `get_real_status()` e' usato nei template e in vari servizi — non rimuoverlo
- `get_status_badge_info()` e' usato nei template Jinja2
- Mantenere backward compatibility totale con metodi proxy

**Verifica**: `pytest tests/new/ -n 4` + `pyright` + controllare template manualmente

#### TASK 3.2: Estrarre logica di configurazione tabelle da `Gara`
**File**: `models/competition/models.py`
**Problema**: `Gara.parse_tables_input()` e' un metodo statico di parsing stringhe che non appartiene all'entita'.

**Soluzione**: Spostare in `models/shared/utils.py` o in un nuovo `models/competition/table_config.py`.
**Rischio**: BASSO - metodo statico, nessuna dipendenza dallo stato dell'oggetto.
**Verifica**: `pyright` + `pytest tests/new/ -n 4`

---

### FASE 4 - Architetturale (lungo termine)

#### TASK 4.1: Definire Protocol interfaces per servizi cross-domain
**Problema originale**: `MatchmakingOrchestrator` dipende da concrete `MatchService`, `RatingService`, `ChallengeService`.
**Analisi (2026-02-06)**: Sia `MatchmakingOrchestrator` che `DomainOrchestrator` sono **codice morto** — usati solo in test legacy, mai in route/servizi di produzione. `create_round_with_handicaps()` ha un bug (passa kwargs non accettati da `MatchService.create_match()`). Aggiungere Protocol a codice morto non ha valore.
**Stato**: CANCELLATO — codice morto, nessun beneficio in produzione.

#### TASK 4.2: Separare UtilityMixin in mixin focalizzati
**Problema originale**: `UtilityMixin` ha 6 metodi (save, delete, to_dict, find_by_id, find_all, refresh).
**Analisi (2026-02-06)**: TUTTI i metodi di `UtilityMixin` sono usati **solo nei test legacy**. Zero utilizzo in codice di produzione (i servizi usano `@transactional` e query dirette). Inoltre `BaseModel` duplica gia' 5 dei 6 metodi (manca solo `refresh()`). Splittare un mixin inutilizzato in produzione non ha valore.
**Stato**: CANCELLATO — nessun utilizzo in produzione.

#### TASK 4.3: Estrarre responsabilita' da Match/TrioMatch god classes
**Problema**: `Match` (586 LOC, 37 metodi tra propri+ereditati, 8 gruppi di responsabilita') e `TrioMatch` (487 LOC, 31 tra metodi+property, 7 gruppi) sono god classes confermate.
**Analisi (2026-02-06)**: Gruppi di responsabilita' identificati in Match:
1. State Queries (4 metodi read-only)
2. Distance/Scoring Config (4 property, gia' delegano a value objects)
3. Handicap Management (3 metodi)
4. Discipline Management (4 metodi)
5. Multi-Set Management (4 metodi)
6. Tiebreaker Support (4 metodi)
7. Match Completion/State Transitions (5 metodi)
8. Result Validation (4 metodi, da BaseMatchMixin)

Per TrioMatch: round-robin logic (2), bonus/completion (2), 3-player confirmation (4), forfeit (1, 71 LOC), 14 computed properties.
**Stato**: DA PIANIFICARE — unico task con impatto reale, ma alto rischio. Approccio suggerito: estrarre un gruppo alla volta (es. Multi-Set → servizio, Tiebreaker → servizio).

---

## Riepilogo Priorita'

| # | Task | Rischio | Impatto | Righe Risparmiate | Stato |
|---|------|---------|---------|-------------------|-------|
| 1.1 | Consolidare permessi duplicati | BASSO | ALTO (sicurezza) | ~80 | DONE |
| 1.2 | Eliminare parse_date duplicata | BASSO | MEDIO | ~10 | DONE |
| 1.3 | Centralizzare filtro iscrizioni | BASSO | MEDIO | ~30 | DONE |
| 2.1 | Creare route_helpers.py | MEDIO | ALTO | ~300 (graduale) | DONE (utility + 20 route convertite) |
| 3.1 | Estrarre GaraStatusResolver | MEDIO | ALTO (manutenibilita') | ~60 | DONE |
| 3.2 | Estrarre parse_tables_input | BASSO | BASSO | ~10 | DONE |
| 4.1 | Protocol interfaces | — | — | — | CANCELLATO (orchestrators = codice morto) |
| 4.2 | Split UtilityMixin | — | — | — | CANCELLATO (zero uso in produzione) |
| 4.3 | Estrarre da Match/TrioMatch | ALTO | ALTO | ~200+ | DA PIANIFICARE |
| 4.4 | Rimozione dead code Match | BASSO | MEDIO | ~68 | DONE |
| 5.1 | Rimuovere @transactional da route (Type B) | BASSO | ALTO (architettura) | ~20 | DONE (2 route) |
| 5.2 | Estrarre DB ops da route a service (Type A) | MEDIO | ALTO | ~150 | DONE (10 route) |
| 5.3 | Spostare mutazioni extra in service (Type C) | MEDIO | MEDIO | ~50 | DONE (7 route) |

---

## Findings Aggiuntivi (2026-02-06)

### Dead Code su Match Model
7 metodi mai chiamati dall'esterno — **RIMOSSI** (~68 LOC):
- **Tiebreaker** (4 metodi, ~48 LOC): `needs_tiebreaker()`, `has_active_tiebreaker()`, `get_active_tiebreaker()`, `can_start_tiebreaker()` — solo auto-referenziati. Esiste `TiebreakerService` che gestisce la logica a livello gara.
- **Handicap** (3 metodi, ~20 LOC): `apply_handicap()`, `get_effective_score()`, `get_handicap_info()` — scritti per `MatchmakingOrchestrator` che e' codice morto.

### Dead Code: MatchmakingOrchestrator e DomainOrchestrator
Entrambi usati solo in test legacy. `create_round_with_handicaps()` ha un bug (passa kwargs non accettati da `MatchService.create_match()`).

### Anti-pattern: `@transactional` su Route Handlers
Originariamente 20+ route con `@transactional` diretto. **Tutte 19 risolte** (0 rimaste).

**RISOLTE — Fase 1 (12 route, Type A/B)**:
- `routes/admin/venue.py`: 5 route (delete, activate, toggle, verify, update_table) — nuovi metodi in `LocationService`
- `routes/admin/competition/rounds.py`: 1 route (start_first_round) — gia' delegava a service
- `routes/admin/competition/inscriptions.py`: 1 route (close_inscriptions) — gia' delegava a service, fix ordine decoratori
- `routes/player/notifications.py`: 3 route (notifications, mark_read, mark_all_read) — nuovi metodi in `NotificationService`
- `routes/player/proposals.py`: 2 route (accept/reject) — `MatchProposalService.reject_proposal()` creato

**RISOLTE — Fase 2 (7 route, Type C — mixed service + direct DB ops)**:
- `routes/admin/venue.py`: 2 route (create_venue, upload_photo) — `business_hours` param aggiunto a `create_billiard_hall()`, nuovo `LocationService.update_venue_photo()`
- `routes/admin/competition/crud.py`: 3 route (create_gara_standalone, create_gara, edit_gara) — `available_tables` gestito dentro `GaraService.create_gara()` e `update_gara()`
- `routes/admin/competition/rounds.py`: 2 route (amalfi_start_round, start_round_generic) — nuovo `RoundService.start_next_round()` combina creazione turno + state transition + current_round + table assignment

---

## Regole per il Refactoring

1. **Ogni task**: scrivere/aggiornare test PRIMA, poi implementare, poi verificare
2. **Backward compatibility**: non rompere API pubbliche - usare delegazione/proxy
3. **Un commit per task**: messaggi di commit chiari con `refactor:` prefix
4. **Verifica obbligatoria**: `pyright` + `pytest tests/new/ -n 4` dopo ogni task
5. **Template check**: se il refactoring tocca metodi usati nei template, controllare anche quelli

---

## File Critici da Non Modificare senza Attenzione

- `models/base.py` - Base classes per tutti i modelli
- `models/transaction/manager.py` - Infrastruttura transazionale
- `models/events/base.py` - Event bus per gamification/notifiche
- `app.py` - Factory pattern e registrazione handler
