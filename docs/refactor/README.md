# Refactoring Documentation

This directory contains all documentation related to the comprehensive refactoring of the tornei-biliardo webapp.

## Structure

### `/docs/adr/` - Architectural Decision Records
Contains architectural decisions and their rationale:
- `ADR-0001-refactoring-roadmap.md` - Overall refactoring strategy and plan
- `ADR-0002-route-blueprint-decomposition.md` - Blueprint architecture decisions (future)
- `ADR-0003-dashboard-unification.md` - Template unification strategy (future)
- `ADR-0004-service-layer.md` - Service layer implementation decisions (future)
- `ADR-0005-scoring-strategy.md` - Scoring policy pattern decisions (future)
- `ADR-0006-state-machine.md` - State management decisions (future)
- `ADR-0007-core-cleanup.md` - Shared utilities and cleanup decisions (future)

### `/docs/refactor/` - Implementation Reports
Contains detailed reports for each milestone:
- `INVENTORY.md` - Baseline metrics and technical debt assessment ✓
- `STEP-1.md` - Route blueprint decomposition report (future)
- `STEP-2.md` - Dashboard unification and components report (future)
- `STEP-3.md` - Service layer implementation report (future)
- `STEP-4.md` - Scoring strategy implementation report (future)
- `STEP-5.md` - Core cleanup and finalization report (future)

## Implementation Guidelines

### Quality Gates (Required for each milestone)
- [ ] **Coverage**: ≥90% test coverage on modified files
- [ ] **Linting**: `flake8` and `black --check` pass
- [ ] **Performance**: p95 response times <2s for user operations
- [ ] **Architecture**: No business logic in route handlers
- [ ] **Compatibility**: All existing URLs preserved

### Branch Naming Convention
- `refactor/step-N-<description>`
- Example: `refactor/step-1-admin-routes-split`

### Commit Message Convention
- `refactor(step-N): <action>`
- Example: `refactor(step-1): split admin routes into domain blueprints`

### PR Requirements
- Link to relevant ADR
- Include excerpt from `STEP-N.md` report
- Demonstrate all quality gates are met
- Include before/after metrics

## Current Status

**Milestone 0 - Inventory & Planning**: ✅ **COMPLETE**
- Baseline metrics established
- Technical debt quantified
- Implementation roadmap approved

**Next Milestone**: Step 1 - Route Blueprint Decomposition
- Target: Split `routes/admin.py` (1,442 lines) into domain blueprints
- Branch: `refactor/step-1-admin-routes-split`
- ADR: `ADR-0002-route-blueprint-decomposition.md`

## Key Metrics Tracked

### File Complexity
- Files >400 lines identified and targeted for reduction
- Cyclomatic complexity monitoring
- Code duplication elimination tracking

### Architecture Compliance
- Direct `db.session` usage in routes (target: 0)
- Business logic in templates (target: 0)
- Exception handling consistency

### Test Coverage
- Baseline: Minimal (2 test files)
- Target: ≥90% on all refactored components
- Integration test coverage for critical paths

---

**Last Updated**: 2025-08-24  
**Current Phase**: Milestone 0 Complete - Ready for Milestone 1