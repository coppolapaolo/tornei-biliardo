# Tornei-Biliardo Refactoring Inventory Report

**Date**: 2025-08-24  
**Branch**: `refactor/step-0-inventory`  
**Purpose**: Baseline metrics and technical debt assessment for comprehensive refactoring

## Executive Summary

This inventory establishes baseline metrics for the tornei-biliardo webapp refactoring project. Key findings indicate significant technical debt in monolithic route files, template complexity, code duplication, and insufficient separation of concerns.

### Critical Issues Identified

1. **Monolithic Route Files**: `routes/admin.py` (1,442 lines) contains mixed domain logic
2. **Large Templates**: Multiple templates >400 lines, with `admin/prova_detail.html` at 831 lines
3. **Direct Database Access**: 39+ `db.session` usages across route files violate layered architecture
4. **Code Duplication**: `InvalidTransitionError` duplicated across domains
5. **Limited Test Coverage**: Only 2 test files covering user CRUD operations

## Detailed Metrics

### 1. File Size Analysis

#### Python Source Files >400 Lines
| File | Lines | Domain | Priority |
|------|-------|---------|----------|
| `routes/admin.py` | 1,442 | Admin Management | **Critical** |
| `models/user/services.py` | 1,017 | User Domain | High |
| `models/user/permissions.py` | 751 | Authorization | High |
| `models/dashboard/services.py` | 599 | Dashboard | Medium |
| `export_repo.py` | 578 | Utilities | Low |
| `amalfi/engine.py` | 544 | Core Algorithm | Medium |
| `routes/player.py` | 537 | Player Management | High |
| `models/match/models.py` | 523 | Match Domain | Medium |

#### Template Files >400 Lines
| Template | Lines | Usage | Priority |
|----------|-------|-------|----------|
| `admin/prova_detail.html` | 831 | Competition Detail | **Critical** |
| `player/dashboard.html` | 521 | Player Dashboard | High |
| `admin/tournament_detail.html` | 476 | Tournament Detail | High |
| `match_detail.html` | 459 | Match Detail | High |
| `dashboard/player.html` | 448 | Dashboard Widget | High |

### 2. Database Session Usage in Routes

**Total Direct `db.session` Usage**: 39 occurrences across route files

#### Breakdown by File
- `routes/admin.py`: 25 occurrences (17 commits, 8 deletes)
- `routes/player.py`: 12 occurrences (7 commits, 3 deletes, 2 rollbacks)
- `routes/auth.py`: 2 occurrences (1 add, 1 commit)

#### Most Problematic Areas
1. **Tournament Management**: Lines 72-73, 84-85, 145, 175 in `admin.py`
2. **Competition Lifecycle**: Lines 379, 418, 440-441, 494, 539, 573, 657 in `admin.py`
3. **Match Result Processing**: Lines 725, 750, 778, 786, 812, 833, 863 in `admin.py`
4. **User Registration/Deletion**: Lines 45-46 in `auth.py`, 385-398 in `player.py`

### 3. Code Duplication Analysis

#### Confirmed Duplications

**Exception Classes**:
- `InvalidTransitionError(ValueError)` 
  - Defined in: `models/competition/services.py:23`
  - Duplicated in: `models/match/services.py:20`
  - **Impact**: Inconsistent error handling across domains

**Template Patterns** (Manual analysis required):
- Dashboard widgets duplicated across `admin/dashboard.html`, `player/dashboard.html`
- Status badge rendering logic repeated in multiple templates
- Empty state messages not componentized

#### Potential Dead Code

**Low-Utility Files** (identified for review):
- `export_script.py` (229 lines) - Export functionality
- `export_zip_md.py` (349 lines) - Archive utilities  
- `export_repo.py` (578 lines) - Repository export

### 4. Architecture Violations

#### Service Layer Issues
- **Business Logic in Routes**: Complex domain operations directly in route handlers
- **Transaction Management**: Manual `db.session.commit()` calls throughout routes
- **Error Handling**: Inconsistent exception handling and user feedback

#### Template Architecture Issues
- **Mixed Concerns**: Business logic calculations in Jinja2 templates
- **Component Reuse**: No macro system for common UI patterns
- **Size Complexity**: Templates exceeding maintainability thresholds

### 5. Test Coverage Assessment

#### Current Test Suite
- **Total Test Files**: 2
- **Primary Coverage**: User CRUD operations (`test_user_crud.py` - 451 lines)
- **Configuration**: Basic test setup in `conftest.py` (193 lines)

#### Coverage Gaps (Critical)
1. **Admin Routes**: No testing for 1,442-line admin route file
2. **Competition Management**: No tests for Prova lifecycle
3. **Match Processing**: No tests for match result handling
4. **Amalfi Algorithm**: No tests for core pairing logic
5. **Template Rendering**: No integration tests for UI components

### 6. Complexity Analysis

#### Domain Distribution
| Domain | Files | Total Lines | Complexity |
|--------|-------|-------------|------------|
| User Management | 6 | 2,154 | High |
| Tournament/Competition | 4 | 1,155 | High |
| Match Management | 5 | 1,335 | Medium |
| Classification | 3 | 628 | Medium |
| Matchmaking | 8 | 1,066 | Medium |
| Routes (All) | 5 | 2,174 | **Critical** |
| Templates | 31 | 6,462 | High |

## Refactoring Priorities

### Milestone 1: Route Decomposition (Critical)
- **Target**: Split `routes/admin.py` (1,442 lines) into domain blueprints
- **Benefit**: Immediate separation of concerns, reduced file complexity
- **Risk**: URL compatibility, circular import management

### Milestone 2: Template Componentization (High)
- **Target**: Break down templates >400 lines, create macro system
- **Benefit**: Reusable UI components, reduced duplication
- **Risk**: Template inheritance complexity

### Milestone 3: Service Layer Implementation (High)
- **Target**: Extract business logic from routes, eliminate direct `db.session` usage
- **Benefit**: Clean architecture, testable business logic
- **Risk**: Transaction boundary management

### Milestone 4: Error Handling Unification (Medium)
- **Target**: Centralize exception handling, eliminate `InvalidTransitionError` duplication
- **Benefit**: Consistent error experience, simplified debugging
- **Risk**: Cross-domain exception compatibility

### Milestone 5: Test Coverage Expansion (High)
- **Target**: Achieve ≥90% coverage on refactored components
- **Benefit**: Regression prevention, confidence in changes
- **Risk**: Test maintenance overhead

## Risk Assessment

### High-Risk Areas
1. **URL Compatibility**: 39 admin endpoints risk breaking during blueprint split
2. **Transaction Boundaries**: 39 direct `db.session` calls need careful migration
3. **Template Dependencies**: Complex template inheritance may break during componentization

### Mitigation Strategies
1. **Smoke Testing**: Endpoint response validation before/after each milestone
2. **Incremental Migration**: Preserve existing patterns during mechanical splits
3. **Rollback Planning**: Feature flag system for gradual transition

## Recommended Implementation Sequence

1. **Step 0** (Current): Inventory and baseline establishment ✓
2. **Step 1**: Mechanical route splitting with URL preservation
3. **Step 2**: Template unification and component system
4. **Step 3**: Service layer implementation with transaction management
5. **Step 4**: Error handling unification and cleanup
6. **Step 5**: Comprehensive test coverage implementation

---

**Report Generated**: 2025-08-24  
**Next Action**: Create ADR-0001 for refactoring roadmap approval