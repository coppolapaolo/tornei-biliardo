---
title: 'Terminazione manuale Campionato'
type: 'feature'
created: '2026-04-05'
status: 'done'
baseline_commit: 'ca73084'
context:
  - 'CLAUDE.md (Campionato domain, computed status)'
  - 'models/campionato/CLAUDE.md'
  - 'docs/SPECIFICHE.md (playoff lifecycle)'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Non esiste un modo per chiudere manualmente un campionato con gare non completate. Lo status è solo computato dalle gare: un campionato "abbandonato" resta per sempre IN_PROGRESS. Inoltre, la terminazione deve essere consapevole dei playoff configurati: per specifica, i playoff si giocano _dopo_ la chiusura del campionato, e il campionato non è "completato" fino a playoff conclusi.

**Approach:** Aggiungere `terminated_at` persistito al Campionato. L'operazione soft-elimina le gare non-completed. Se il campionato ha playoff configurati lo status diventa `TERMINATED` (fase gare chiusa, playoff in attesa); altrimenti `COMPLETED`. Durante la terminazione, se `min_garas_played` è irraggiungibile, warning con possibilità di modifica.

## Boundaries & Constraints

**Always:**
- Nuovo valore enum `TournamentStatus.TERMINATED = "terminated"` — rappresenta "fase gare chiusa, playoff in attesa"
- `terminated_at` è naive-UTC (`utc_now()`), `nullable=True`, default `NULL`
- Status computato con `terminated_at` non-null: → `TERMINATED` se `has_playoff_configurations()`, → `COMPLETED` altrimenti
- Solo `campionato_manager_required` (admin o director assegnato) può terminare
- Idempotente: su campionato già terminato ritorna `False`, no-op
- Soft-delete SOLO gare con `status != GaraStatus.COMPLETED.value`; le completed restano intatte
- Una volta terminato, `can_create_gara()` → `False`
- Campionato soft-deleted → `ValueError`
- Tutto in singola transazione `@transactional(domain="campionato")`
- Se playoff configurati con `min_garas_played` irraggiungibile: la route mostra warning e chiede conferma; offre di modificare il valore

**Ask First:**
- Altre restrizioni post-terminazione oltre a "no nuove gare"

**Never:**
- NON modificare `soft_delete_campionato` (terminazione ≠ cancellazione)
- NON aggiungere `terminated_reason` / `terminated_by_id`
- NON implementare avvio playoff (feature separata, Spec 2)

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|---------------|----------------------------|----------------|
| Happy, no playoff | 3 gare (1 completed, 2 non), no playoff config | soft-delete 2 gare, status=COMPLETED | N/A |
| Happy, con playoff | 3 gare (1 completed, 2 non), playoff config presente | soft-delete 2 gare, status=TERMINATED | N/A |
| Zero completed | solo gare in setup/playing | tutte soft-deleted, `terminated_at` set | N/A |
| Tutte completed | tutte gare completed, playoff config | `terminated_at` set, nessuna gara toccata, status=TERMINATED | N/A |
| min_garas_played irraggiungibile | playoff con min=7, solo 4 gare completed | warning pre-conferma; se confermato → termina; se modifica min → aggiorna config poi termina | N/A |
| Già terminato | `terminated_at` non-null | no-op, `False` | flash warning |
| Soft-deleted | `is_deleted=True` | `ValueError` | flash error |
| Non autorizzato | player generico | 403 | decorator |

</frozen-after-approval>

## Code Map

- `models/status_enum.py` -- aggiungere `TERMINATED = "terminated"` a TournamentStatus
- `utils/status_ui.py` -- aggiungere mapping badge/testo per TERMINATED
- `models/campionato/models.py` -- colonna `terminated_at`, aggiornare `get_status()`, aggiungere `can_create_gara()`
- `models/campionato/statistics_service.py` -- aggiornare `compute_campionato_status()` short-circuit
- `models/campionato/tournament_service.py` -- nuovo `terminate_campionato()`, nuovo `check_playoff_feasibility()`
- `routes/admin/campionato.py` -- route POST `/<id>/terminate` con logica pre-check playoff
- `routes/admin/competition/crud.py` -- blocco creazione gara su terminato
- `templates/admin/campionato_detail.html` -- bottone "Termina", badge TERMINATED, bottone "Avvia Playoff" disabilitato
- `migrations/20260406_campionato_terminated_at.py` -- ADD COLUMN
- `tests/new/unit/test_terminate_campionato.py` -- scenari I/O Matrix
- `tests/new/integration/test_terminate_campionato_route.py` -- route + permessi + playoff warning

## Tasks & Acceptance

**Execution:**
- [x] `migrations/20260406_campionato_terminated_at.py` -- ADD COLUMN `terminated_at DATETIME NULL` a `campionato`
- [x] `models/status_enum.py` -- aggiungere `TERMINATED = "terminated"` a `TournamentStatus`
- [x] `utils/status_ui.py` -- aggiungere `TournamentStatus.TERMINATED.value: ("bg-dark", _("Terminato"))` nel mapping campionato
- [x] `models/campionato/models.py` -- aggiungere `terminated_at`; `get_status()`: se `terminated_at` → ritorna TERMINATED se `has_playoff_configurations()` else COMPLETED; `get_status_badge_class()`/`get_status_text()`: aggiungere TERMINATED; `can_create_gara()`: False se `terminated_at` o `is_deleted`
- [x] `models/campionato/statistics_service.py` -- `compute_campionato_status()`: PRIMA di tutto, se `terminated_at` → TERMINATED/COMPLETED (stessa logica di `get_status()`)
- [x] `models/campionato/tournament_service.py` -- `terminate_campionato(campionato_id) -> bool`: valida, soft-delete gare non-completed, set `terminated_at`, `is_active=False`; `check_playoff_feasibility(campionato_id) -> dict`: ritorna `{"feasible": bool, "configs": [...], "max_completed": int}` per ogni playoff config confronta `min_garas_played` con gare completed; `update_playoff_min_garas(config_id, new_min) -> None`
- [x] `routes/admin/campionato.py` -- POST `/<id>/terminate`: chiama `terminate_campionato()`; POST `/<id>/update-playoff-min` per modificare min_garas_played; playoff_feasibility passato al template per warning JS
- [x] `routes/admin/competition/crud.py` -- guardia `campionato.can_create_gara()` prima di creare gara
- [x] `templates/admin/campionato_detail.html` -- bottone "Termina Campionato" (`btn-danger`, `showConfirm`); banner terminazione; sezione Playoff con bottone disabilitato + tooltip; warning JS per playoff infeasibili
- [x] `tests/new/unit/test_terminate_campionato.py` -- 17 test: tutti scenari I/O Matrix + idempotenza + status TERMINATED vs COMPLETED + feasibility + update min
- [x] `tests/new/integration/test_terminate_campionato_route.py` -- 6 test: happy path + already terminated + forbidden + status TERMINATED + can_create_gara + update-playoff-min

**Acceptance Criteria:**
- Given campionato con gare miste + playoff config, when `terminate_campionato(id)`, then gare non-completed soft-deleted e `compute_campionato_status()` ritorna `TERMINATED`
- Given campionato terminato senza playoff config, then status = `COMPLETED`
- Given playoff con `min_garas_played=7` e solo 4 gare completed, when POST terminate, then response include warning; se utente conferma con modifica min=4, config aggiornata e campionato terminato
- Given campionato terminato con playoff config, then UI mostra badge "Terminato" e bottone "Avvia Playoff" disabilitato
- Given campionato terminato, when si tenta creare gara, then bloccato con flash error
- `pytest tests/new/ -n 4` → tutti verdi; `pyright` → 0 errori

## Design Notes

**Status TERMINATED vs COMPLETED:** per specifica, "i playoff si giocano alla fine del campionato" e il campionato non è davvero finito fino a playoff conclusi. `TERMINATED` segnala "fase gare chiusa, in attesa playoff". Quando i playoff saranno implementati (Spec 2), la transizione TERMINATED→COMPLETED avverrà a playoff conclusi.

**Perché `terminated_at` persistito:** dopo soft-delete cascata, `campionato.gare` potrebbe essere `[]` → status computato sarebbe `SETUP` senza il campo persistito.

**Flusso pre-conferma playoff:** il check `min_garas_played` è nel route (non nel service) per consentire all'utente di decidere prima della terminazione. Se l'utente conferma senza modificare → termina comunque (nessun player qualificabile, ma non è un errore).

## Verification

**Commands:**
- `python migrations/runner.py` -- expected: migrazione eseguita
- `pytest tests/new/unit/test_terminate_campionato.py -n auto 2>&1 | tail -1` -- expected: "N passed"
- `pytest tests/new/integration/test_terminate_campionato_route.py -n 4 2>&1 | tail -1` -- expected: "N passed"
- `pytest tests/new/ -n 4 2>&1 | tail -1` -- expected: tutti verdi (no regressioni)
- `pyright` -- expected: 0 errors
- `black . && flake8` -- expected: no errors

## Suggested Review Order

**Domain logic**

- Short-circuit su `terminated_at` — entry point del design. Playoff-aware branching TERMINATED vs COMPLETED
  [`models.py:134`](../../models/campionato/models.py#L134)

- Stessa logica in `compute_campionato_status` — usata da status_ui filter
  [`statistics_service.py:362`](../../models/campionato/statistics_service.py#L362)

- Nuovo enum value TERMINATED aggiunto a TournamentStatus
  [`status_enum.py:82`](../../models/status_enum.py#L82)

**Service layer**

- `terminate_campionato` — soft-delete cascade + `is_deleted` guard (da review)
  [`tournament_service.py:614`](../../models/campionato/tournament_service.py#L614)

- `check_playoff_feasibility` — confronto min_garas_played vs completed_count
  [`tournament_service.py:647`](../../models/campionato/tournament_service.py#L647)

- `update_playoff_min_garas` — con IDOR guard `campionato_id` (da review)
  [`tournament_service.py:697`](../../models/campionato/tournament_service.py#L697)

**Route + template**

- Route `POST /terminate` — fetch nome prima del service call
  [`campionato.py:590`](../../routes/admin/campionato.py#L590)

- Guard `can_create_gara()` in creazione gara — con flash tradotto
  [`crud.py:173`](../../routes/admin/competition/crud.py#L173)

- Template: bottone terminate, banner, playoff card disabilitata, JS confirm con warning playoff
  [`campionato_detail.html:24`](../../templates/admin/campionato_detail.html#L24)

**UI support**

- Badge e testo per TERMINATED in status presenter
  [`status_ui.py:121`](../../utils/status_ui.py#L121)

**Schema**

- Migrazione additiva `terminated_at DATETIME NULL`
  [`20260406_campionato_terminated_at.py:1`](../../migrations/20260406_campionato_terminated_at.py#L1)

**Test**

- Unit: 19 test — happy path, edge cases, idempotenza, IDOR guard, playoff feasibility
  [`test_terminate_campionato.py:1`](../../tests/new/unit/test_terminate_campionato.py#L1)

- Integration: 7 test — route + permessi + full flow update-min→terminate
  [`test_terminate_campionato_route.py:1`](../../tests/new/integration/test_terminate_campionato_route.py#L1)
