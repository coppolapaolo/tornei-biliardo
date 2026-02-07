# HANDOFF: Technical Debt Refactoring

**Data**: 2026-02-07
**Stato**: ROUND 1 COMPLETO (Fasi 1-5), ROUND 2 COMPLETO (P1-P3), ROUND 3 COMPLETO (P1-P4), ROUND 4 COMPLETO (P1-P4)
**Valutazione complessiva architettura**: 7.5/10 → 9.1/10 (post-Round 2) → 9.3/10 (post-Round 3) → 9.5/10 (post-Round 4)

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
**Soluzione implementata (2026-02-07)**:
- **Phase 1**: Deleted ~190 lines of dead/duplicate code: `_check_and_complete_gara_if_needed` (no-op), `_apply_bonus_and_complete` (duplicated in TrioScoringService), `_update_current_players` (duplicated in TrioScoringService), `get_match_summary` (zero callers), `supports_multi_discipline`/`configure_set_disciplines`/`get_multi_discipline_summary` (only used in legacy tests), `confirm_result` (replaced by `confirm_result_by_admin`)
- **Phase 2**: Extracted `SetLifecycleService` (`set_lifecycle_service.py`) — `start_next_set`, `get_current_set`, `complete_set` moved from Match with 1-line proxy methods kept for backward compatibility
- **Phase 3**: Extracted `TrioStateSerializer` (`trio_state_serializer.py`) — `get_current_state` UI dict builder moved from TrioMatch with 1-line proxy
- **Result**: models.py reduced from 1138 LOC to 837 LOC (-26.4%). Match+TrioMatch focused on domain behavior; serialization and multi-set lifecycle in dedicated services.
**Stato**: DONE

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
| 4.3 | Estrarre da Match/TrioMatch | ALTO | ALTO | ~300 | DONE |
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

## Round 2 — Technical Debt Cleanup (2026-02-07)

Secondo ciclo di analisi post-Round 1. Identificate 3 aree residue.

### P1: Gamification Routes → Service Layer (39 manual commits → 0)

**Problema**: `routes/gamification/admin.py`, `config.py`, `features.py` usavano raw `db.session.commit()/rollback()` invece di delegare a servizi `@transactional`.

**Soluzione**:
- Aggiunti metodi admin a `QuestService` (+3), `AchievementService` (+2), `LevelService` (+1)
- Aggiunti 9 metodi write a `GamificationConfigService` (era read-only)
- Creato `FeatureConfigService` (nuovo file, 2 metodi)
- Refactored 21 route handler a `handle_service_action()` / `handle_ajax_service_action()`

**File modificati**: `quest_service.py`, `achievement_service.py`, `level_service.py`, `config_service.py`, `feature_config_service.py` (NEW), `routes/gamification/admin.py`, `config.py`, `features.py`
**Stato**: DONE

### P2: Remaining Route Manual Commits (5 → 0)

**Problema**: 5 route residue con `db.session.commit()` manuale fuori dal Round 1.

**Soluzione**:
- `routes/admin/user.py` — `process_director_request`: aggiunto param `admin_notes` a `DirectorRequestService.process_request()`
- `routes/admin/user.py` — `toggle_gamification_override`: nuovo `UserService.toggle_gamification_override()`
- `routes/challenge.py` — `edit_challenge`: refactored a `handle_ajax_service_action`
- `routes/admin/campionato.py` — `_create_playoff_config`: nuovo `TournamentService.create_playoff_config()`

**4 route mantenute as-is** (pattern corretti): `validate_match`, `assign_table`, `delete_account`, `_generate_gdpr_export`

**File modificati**: `director_request_service.py`, `services.py` (user), `challenge.py`, `campionato.py`, `services.py` (campionato)
**Stato**: DONE

### P3: Split Large Files (2 file → 7 moduli)

**Problema**: 2 file superavano i 1000 LOC ciascuno.

#### P3a: `models/individual_match/models.py` (1218 LOC → 3 moduli + re-export shim)
- `proposal_models.py` (~310 LOC): ProposalType, ProposalStatus, InvitationStatus, MatchProposal, ProposalInvitation
- `match_models.py` (~660 LOC): IndividualMatch, IndividualSetStatus, IndividualSet, IndividualRack
- `availability_models.py` (~50 LOC): PlayerAvailability (deprecated)
- `models.py` ridotto a re-export shim (~46 LOC) — zero importers da aggiornare

#### P3b: `routes/player/profile.py` (1133 LOC → 4 moduli)
- `profile.py` (~440 LOC): display + editing profilo
- `privacy.py` (~115 LOC): 7 route privacy settings e hide/show
- `account.py` (~55 LOC): cancellazione account
- `exports.py` (~480 LOC): CSV + GDPR export

**Stato**: DONE

### Riepilogo Round 2

| # | Task | Rischio | Impatto | Stato |
|---|------|---------|---------|-------|
| P1 | Gamification routes → service layer | BASSO | ALTO (39 commit manuali eliminati) | DONE |
| P2 | Remaining route manual commits | BASSO | MEDIO (5 commit manuali eliminati) | DONE |
| P3a | Split individual_match/models.py | BASSO | MEDIO (manutenibilita') | DONE |
| P3b | Split player/profile.py | BASSO | MEDIO (manutenibilita') | DONE |

---

## Round 3 — Structural Decomposition (2026-02-07)

Terzo ciclo di refactoring. Focus su SRP violations e file di grandi dimensioni residui.

### P1: Extract TrioMatchService from GaraService

**Problema**: `GaraService` (1400 LOC, 34 metodi) conteneva 7 metodi trio match (~370 LOC) che violavano SRP — logica di scoring trio non correlata al lifecycle della gara.

**Soluzione**:
- Creato `models/competition/trio_service.py` con `TrioMatchService` (7 metodi)
- Sostituiti i 7 method body in `GaraService` con delegation shim (1 riga ciascuno, senza `@transactional`)
- GaraService ridotto da ~1400 a ~1065 LOC

**File**: `trio_service.py` (NEW), `services.py` (MODIFIED)
**Stato**: DONE

### P2: Standardize Entity Fetch Pattern

**Problema**: 25+ istanze di `db.session.get() + abort(404)` vs 15+ gia' con `get_or_404()`. Inconsistenza tra route AJAX (JSON 404) e non-AJAX (HTML 404).

**Soluzione**:
- Aggiunto `get_or_ajax_404()` helper a `utils/route_helpers.py`
- Convertite 23 istanze non-AJAX a `db.get_or_404()`
- Convertite 9 istanze AJAX a `get_or_ajax_404()`
- 13 file route modificati

**File**: `route_helpers.py` (MODIFIED) + 13 route files
**Stato**: DONE

### P3: Split Large Route Files (2 file → 2 package)

**Problema**: 2 route file da ~950 LOC ciascuno.

#### P3a: `routes/individual_match.py` (951 LOC → package)
- `__init__.py` (~25 LOC): Blueprint + imports
- `proposals.py` (~350 LOC): 8 route — proposal CRUD/lifecycle
- `matches.py` (~450 LOC): 12 route — match scoring/lifecycle
- `views.py` (~100 LOC): 4 route + 2 error handler — dashboard, stats, availability, admin

#### P3b: `routes/admin/match.py` (923 LOC → package)
- `__init__.py` (~25 LOC): Blueprint + imports
- `detail.py` (~320 LOC): 3 route — match_detail, assign_table, update_match_times
- `scoring.py` (~300 LOC): 6 route — add_rack, set_result, validate, reset, rack ops
- `multi_set.py` (~155 LOC): 3 route — start_next_set, add/remove set rack
- `challenges.py` (~155 LOC): 2 route — record challenge attempt(s)

Tutte le 57 URL route preservate, zero modifiche ai caller.

**Stato**: DONE

### P4: Split models/match/services.py (3 classi → 3 file)

**Problema**: 1039 LOC con 3 classi distinte gia' ben separate nello stesso file.

**Soluzione**:
- `match_service.py` (~560 LOC): MatchService — state machine, multi-set, admin ops
- `rack_service.py` (~240 LOC): RackService — rack scoring, validation, reset
- `result_service.py` (~60 LOC): MatchResultService — result validation/submission
- `services.py` ridotto a re-export shim (~65 LOC) — zero importers da aggiornare

**Stato**: DONE

### Riepilogo Round 3

| # | Task | Rischio | Impatto | Stato |
|---|------|---------|---------|-------|
| P1 | Extract TrioMatchService | BASSO | ALTO (SRP, -335 LOC da GaraService) | DONE |
| P2 | Standardize entity fetch | BASSO | MEDIO (consistenza, 33 istanze) | DONE |
| P3a | Split individual_match.py | BASSO | MEDIO (manutenibilita') | DONE |
| P3b | Split admin/match.py | BASSO | MEDIO (manutenibilita') | DONE |
| P4 | Split match/services.py | BASSO | MEDIO (manutenibilita') | DONE |

---

## Round 4 — Final Cleanup (2026-02-07)

### P1: Eliminate Manual Commits/Rollbacks in Routes

6 instances of `db.session.commit()` / `db.session.rollback()` remained in route handlers, violating the `@transactional` convention.

**Approach**: Created `MatchValidationService.validate_and_complete()` in `models/match/validation_service.py` (~95 LOC) wrapping all 6 operations of match validation in a single `@transactional`. Removed redundant commit/rollback from `detail.py`, `account.py`, `exports.py`.

**Files modified**: `models/match/validation_service.py` (NEW), `models/match/services.py`, `routes/admin/match/scoring.py`, `routes/admin/match/detail.py`, `routes/player/account.py`, `routes/player/exports.py`

### P2: Remove Trio Wrapper Methods from GaraService

7 thin wrapper methods in `GaraService` delegated directly to `TrioMatchService` with no added logic.

**Approach**: Updated 2 route files to import `TrioMatchService` directly. Removed 7 wrappers (~37 LOC) from `GaraService`.

**Files modified**: `models/competition/services.py`, `routes/player/matches.py`, `routes/admin/competition/matches.py`

### P3: Split models/dashboard/services.py (1100 LOC)

Single file mixed queries, section builders, role facades, and dataclasses.

**Approach**: Split into 3 focused modules with re-export shim:
- `view_models.py` (~160 LOC): Dataclasses (`CapabilityVM`, `UnifiedDashboardItem`, `DashboardVM`) + query helpers
- `section_builders.py` (~230 LOC): `DashboardSectionBuilder` (player, individual match, challenge, gamification sections)
- `dashboard_service.py` (~760 LOC): `DashboardService` role facades + query builders
- `services.py`: Re-export shim

### P4: Split models/campionato/services.py (1025 LOC)

`TournamentService` mixed CRUD lifecycle with complex statistics/ranking logic.

**Approach**: Split into 2 focused modules with re-export shim. Used inheritance (`TournamentService extends TournamentStatisticsService`) so all callers continue to work without changes:
- `statistics_service.py` (~290 LOC): `TournamentStatisticsService` + `compute_campionato_status`
- `tournament_service.py` (~600 LOC): `TournamentService` CRUD + lifecycle
- `services.py`: Re-export shim

### Riepilogo Round 4

| # | Task | Rischio | Impatto | Stato |
|---|------|---------|---------|-------|
| P1 | Eliminate manual commits/rollbacks | BASSO | ALTO (transaction safety) | DONE |
| P2 | Remove trio wrappers from GaraService | BASSO | MEDIO (clarity) | DONE |
| P3 | Split dashboard/services.py | BASSO | MEDIO (maintainability) | DONE |
| P4 | Split campionato/services.py | BASSO | MEDIO (maintainability) | DONE |

---

## File Critici da Non Modificare senza Attenzione

- `models/base.py` - Base classes per tutti i modelli
- `models/transaction/manager.py` - Infrastruttura transazionale
- `models/events/base.py` - Event bus per gamification/notifiche
- `app.py` - Factory pattern e registrazione handler
