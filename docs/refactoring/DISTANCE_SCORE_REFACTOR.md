# Distance e Score Refactoring - Execution Tracker

**Status**: 🟡 IN PROGRESS
**Start Date**: 2025-10-07
**Target Completion**: 2025-10-14 (7 giorni)
**Branch**: refactor/distance-score-complete-migration

## Quick Stats
- **Total Files**: 94
- **Total Occurrences**: 470 (327 Python + 143 HTML)
- **Tests to Write**: 143
- **Current Progress**: 0%

## Phase Status

| Phase | Status | Files | Tests | Completato |
|-------|--------|-------|-------|------------|
| PRE-EXEC: Setup | 🟡 IN PROGRESS | - | - | 50% |
| 1. Value Objects | 🔴 TODO | 0/2 | 0/57 | 0% |
| 2.1 Backend Models | 🔴 TODO | 0/5 | 0/28 | 0% |
| 2.2 Backend Services | 🔴 TODO | 0/8 | 0/23 | 0% |
| 2.3 Backend Routes/Utils | 🔴 TODO | 0/12 | 0/13 | 0% |
| 3. Frontend | 🔴 TODO | 0/42 | 0/30 | 0% |
| 4. Cleanup | 🔴 TODO | - | - | 0% |
| 5. PR & Review | 🔴 TODO | - | - | 0% |

## Daily Log

### 2025-10-07 - Day 1: PRE-EXECUTION SETUP

#### Completed
- [x] Created branch: `refactor/distance-score-complete-migration`
- [x] Created tracking document: `DISTANCE_SCORE_REFACTOR.md`
- [ ] Create checklist document: `DISTANCE_SCORE_CHECKLIST.md`
- [ ] Create template tracker: `TEMPLATE_MIGRATION_TRACKER.csv`
- [ ] Push branch to remote
- [ ] Start FASE 1.1: Distance Value Object

#### Status
- Branch: ✅ Created
- Tracking Docs: 🟡 In Progress (1/3 created)
- Ready to Code: 🔴 Waiting for docs

---

### [FUTURE] - Day 2: FASE 1 - Value Objects
TBD

---

## Blockers
(Nessuno al momento)

## Notes
- Tutti i commit devono passare CI prima del push
- Ogni fase ha gate con 100% test pass richiesto
- Backward compatibility MANDATORY - no breaking changes
- Use `PYTHONPATH=. pytest tests/new/ -n auto` per tutti i test

## Files Tracking

### Python Backend (52 files, 327 occurrenze)

#### Models (5 files, 58 occ)
- [ ] models/competition/models.py (11 occ)
- [ ] models/match/models.py (17 occ)
- [ ] models/match/set_models.py (6 occ)
- [ ] models/individual_match/models.py (14 occ)
- [ ] models/classification/models.py (6 occ)
- [ ] models/tiebreaker/models.py (2 occ)
- [ ] models/user/models.py (3 occ)

#### Services (8 files, 59 occ)
- [ ] models/match/services.py (37 occ) - **CRITICAL**
- [ ] models/competition/services.py (2 occ)
- [ ] models/competition/round_service.py (5 occ)
- [ ] models/competition/round_manager.py (5 occ)
- [ ] models/individual_match/services.py (6 occ)
- [ ] models/classification/services.py (2 occ)
- [ ] models/challenge/services.py (2 occ)
- [ ] models/tiebreaker/services.py (2 occ)

#### Routes (4 files, 20 occ)
- [ ] routes/main.py (11 occ)
- [ ] routes/player.py (7 occ)
- [ ] routes/admin/competition.py (2 occ)
- [ ] routes/individual_match.py (1 occ)

#### Utils (4 files, 19 occ)
- [ ] utils/__init__.py (9 occ)
- [ ] models/matchmaking/amalfi_challenge_bye_service.py (3 occ)
- [ ] models/campionato/services.py (1 occ)
- [ ] models/competition/round_configuration.py (6 occ)

#### Tests (28 files, 196 occ)
- tests/new/ (11 files, 86 occ)
- tests/legacy/ (17 files, 110 occ)

### Frontend Templates (42 files, 143 occorrenze)

#### High Priority - Score Display (22 files, 61 occ)
- [ ] components/_match_score.html (6 occ) - **CRITICAL**
- [ ] components/_match_rack_input.html (6 occ) - **CRITICAL**
- [ ] components/_match_admin_controls.html (10 occ)
- [ ] components/_match_result_row.html (5 occ)
- [ ] components/_gara_matches.html (6 occ)
- [ ] player/gara_detail.html (8 occ)
- [ ] admin/gara_result_overview.html (10 occ)
- [ ] individual_match/match_detail.html (12 occ)
- [ ] Altri 14 files (1-4 occ ciascuno)

#### Medium Priority - Distance Config (17 files, 45 occ)
- [ ] components/_gara_header.html (3 occ)
- [ ] components/_gara_edit_form.html (3 occ)
- [ ] components/_gara_cards.html (1 occ)
- [ ] Altri 14 files

#### Low Priority - Forms (3 files, 10 occ)
- [ ] components/_gara_edit_form.html
- [ ] admin/gara_create_standalone.html
- [ ] player/create_match_proposal.html

## Test Coverage Target

### Unit Tests (57)
- Distance: 30 tests
- RackScore: 15 tests
- MatchScore: 12 tests

### Characterization Tests (15)
- Gara: 5 tests
- Match: 8 tests
- Set: 2 tests

### Integration Tests (41)
- Models: 28 tests
- Services: 15 tests
- Routes: 8 tests
- Utils: 5 tests
- Template rendering: 10 tests

### E2E Tests (30)
- Gara creation UI: 2 tests
- Match scoring UI: 5 tests
- Multi-set UI: 3 tests
- Forms: 5 tests
- Dashboards: 5 tests
- Template filters: 5 tests
- Public access: 2 tests
- Individual matches: 3 tests

**Total New Tests**: 143

## Progress Calculation

```
Phase 1 (Value Objects): 20% of total
Phase 2 (Backend): 50% of total
Phase 3 (Frontend): 25% of total
Phase 4 (Cleanup): 5% of total

Current: PRE-EXEC complete = 2%
```

## Success Criteria

- [ ] All 470 occurrences migrated
- [ ] 143 new tests written and passing
- [ ] 0 pyright errors
- [ ] 0 flake8 errors
- [ ] 0 TODOs remaining
- [ ] All documentation updated
- [ ] Manual smoke tests pass
- [ ] PR approved and merged

## Contact

**Lead Developer**: Paolo
**Branch**: refactor/distance-score-complete-migration
**Tracking**: docs/refactoring/DISTANCE_SCORE_REFACTOR.md
**Checklist**: docs/refactoring/DISTANCE_SCORE_CHECKLIST.md
