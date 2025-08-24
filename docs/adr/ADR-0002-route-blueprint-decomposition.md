# ADR-0002: Route Blueprint Decomposition

**Status**: Implemented  
**Date**: 2025-08-24  
**Deciders**: Development Team  
**Technical Story**: Step 1 of comprehensive refactoring - decompose monolithic admin routes

## Context

The current `routes/admin.py` file contains 1,442 lines of code mixing multiple domain concerns in a single file. This violates the Single Responsibility Principle and makes the codebase difficult to maintain, test, and extend.

### Current Problems
- **Monolithic Structure**: Single file handles tournaments, competitions, matches, users, and dashboard functionality
- **Poor Maintainability**: Changes to one domain require understanding the entire file
- **Testing Difficulty**: Cannot test domains in isolation
- **Team Collaboration**: Multiple developers cannot work on different admin features simultaneously
- **Code Navigation**: Difficult to locate specific functionality within 1,400+ lines

### Analysis of Current Structure
Based on functional analysis of `routes/admin.py`, we identified these domain boundaries:

| Domain | Lines (approx) | Endpoints | Core Responsibility |
|--------|----------------|-----------|-------------------|
| Tournament | 50-250 | 7 endpoints | Tournament CRUD and director management |
| Competition | 250-800 | 15+ endpoints | Prova lifecycle, inscriptions, withdrawals |
| Match | 800-1200 | 10+ endpoints | Match results, rack management, assignments |
| User | 1200-1400 | 5 endpoints | User administration, director requests |
| Dashboard | 1-50 | 2 endpoints | Overview and navigation |

## Decision

We will split the monolithic `routes/admin.py` into domain-specific Flask Blueprints while maintaining complete URL compatibility and preserving all existing functionality.

### Target Architecture

```
routes/
├── admin/
│   ├── __init__.py           # Blueprint registration and URL mapping
│   ├── tournament.py         # Tournament management endpoints
│   ├── competition.py        # Prova/competition management  
│   ├── match.py             # Match and result management
│   ├── user.py              # User administration
│   └── dashboard.py         # Admin dashboard views
└── admin.py                 # Minimal redirect/compatibility layer
```

### URL Preservation Strategy

All existing URLs will be preserved through blueprint prefix mapping:

```python
# Before: /admin/tournament/create
# After:  /admin/tournament/create (unchanged)

admin_bp.register_blueprint(tournament_bp, url_prefix='/tournament')
admin_bp.register_blueprint(competition_bp, url_prefix='/prova')
admin_bp.register_blueprint(match_bp, url_prefix='/match')
admin_bp.register_blueprint(user_bp, url_prefix='/user')
admin_bp.register_blueprint(dashboard_bp)  # No prefix for root admin routes
```

### Domain Boundaries

#### Tournament Domain (`routes/admin/tournament.py`)
**Responsibility**: Tournament lifecycle management
**Endpoints**:
- `POST /tournament/create`
- `GET /tournament/<id>`
- `GET|POST /tournament/<id>/edit`
- `POST /tournament/<id>/delete`
- `POST /tournament/<id>/toggle_active`
- `POST /tournament/<id>/add_director`

#### Competition Domain (`routes/admin/competition.py`)
**Responsibility**: Prova (competition) management
**Endpoints**:
- `GET|POST /prova/create`
- `GET /prova/<id>`
- `GET|POST /prova/<id>/edit`
- `POST /prova/<id>/delete`
- `POST /prova/<id>/start`
- `POST /prova/<id>/inscribe`
- `POST /prova/<id>/withdraw`
- `POST /prova/<id>/generate_round`
- `GET /prova/<id>/amalfi_classification`

#### Match Domain (`routes/admin/match.py`)
**Responsibility**: Match and result management
**Endpoints**:
- `GET|POST /match/<id>/result`
- `GET|POST /match/<id>/edit`
- `POST /match/<id>/assign`
- `POST /match/<id>/delete_rack`
- `POST /match/<id>/add_rack`

#### User Domain (`routes/admin/user.py`)
**Responsibility**: User administration
**Endpoints**:
- `GET /users`
- `GET /user/<id>`
- `GET /director_requests`
- `POST /director_requests/<id>/approve`
- `POST /director_requests/<id>/reject`

#### Dashboard Domain (`routes/admin/dashboard.py`)
**Responsibility**: Admin overview and navigation
**Endpoints**:
- `GET /` (redirect to dashboard)
- `GET /overview` (if exists)

## Implementation Approach

### Phase 1: Mechanical Extraction
1. Create domain-specific blueprint files
2. Copy-paste route functions with minimal changes
3. Update import statements for each domain
4. Preserve all existing functionality exactly

### Phase 2: Blueprint Registration
1. Create `routes/admin/__init__.py` with blueprint registration
2. Configure URL prefixes to maintain existing URLs
3. Update main application to register new blueprint structure

### Phase 3: Validation
1. Run comprehensive smoke tests on all admin endpoints
2. Verify import resolution and circular dependency absence
3. Confirm no new `db.session` calls introduced

### Migration Safety Measures

#### URL Compatibility Testing
```python
# Critical endpoints to test during migration
CRITICAL_ENDPOINTS = [
    '/admin/',
    '/admin/tournament/create',
    '/admin/prova/create', 
    '/admin/match/123/result',
    '/admin/users',
    '/admin/director_requests'
]
```

#### Rollback Strategy
- Keep original `admin.py` as `admin_backup.py` during transition
- Implement migration in feature branch with comprehensive testing
- Use feature flags for gradual rollout if needed

## Alternatives Considered

### Alternative 1: Functional Decomposition
**Approach**: Split by function type (CRUD operations, views, etc.)
**Rejected Because**: Would spread domain logic across multiple files, making feature changes more complex

### Alternative 2: Gradual Extraction
**Approach**: Extract one domain at a time over multiple iterations
**Rejected Because**: Would create temporary inconsistency and require multiple deployment cycles

### Alternative 3: Keep Monolithic Structure
**Approach**: Accept current structure and focus on other refactoring areas
**Rejected Because**: Route complexity is the highest priority technical debt item

## Quality Gates

### Functional Requirements
- [ ] All 39 existing admin endpoints remain functional
- [ ] URL compatibility maintained (verified by automated tests)
- [ ] No changes to user-visible behavior
- [ ] All existing Flask-Login decorators preserved

### Technical Requirements  
- [ ] No new `db.session` calls introduced in routes
- [ ] Zero circular import issues
- [ ] All imports resolve correctly
- [ ] Blueprint registration works correctly
- [ ] Performance characteristics unchanged

### Testing Requirements
- [ ] All existing tests continue to pass
- [ ] Smoke tests implemented for critical endpoints
- [ ] Import validation tests created
- [ ] Blueprint registration tests implemented

## Success Metrics

### File Complexity Reduction
- **Before**: 1 file with 1,442 lines
- **After**: 6 files with average ~240 lines each
- **Improvement**: 6x reduction in file complexity

### Maintainability Improvements
- **Domain Isolation**: Changes to tournament logic only affect `tournament.py`
- **Parallel Development**: Multiple developers can work on different domains
- **Code Navigation**: Specific functionality easy to locate
- **Testing**: Each domain can be tested in isolation

### Technical Debt Reduction
- **Single Responsibility**: Each file has one clear domain responsibility
- **Blueprint Architecture**: Proper Flask application structure established
- **Foundation for Step 2**: Clean route structure enables template refactoring

## Risks and Mitigation

### Risk: URL Breaking Changes
**Mitigation**: Comprehensive endpoint testing before and after migration

### Risk: Import Circular Dependencies  
**Mitigation**: Careful import analysis and dependency mapping

### Risk: Performance Degradation
**Mitigation**: Blueprint registration performance testing

### Risk: Missing Functionality
**Mitigation**: Side-by-side functional comparison of old vs new structure

## Implementation Timeline

- **Day 1**: Create blueprint structure and registration
- **Day 2**: Extract tournament and competition domains
- **Day 3**: Extract match and user domains, dashboard cleanup
- **Day 4**: Comprehensive testing and validation
- **Day 5**: Documentation and deployment preparation

**Total Effort**: 5 days for complete Step 1 implementation

## Next Steps

After successful completion of Step 1:
1. **Step 2**: Template unification and component system
2. **Step 3**: Service layer implementation to eliminate `db.session` calls from routes
3. **Step 4**: Scoring strategy pattern implementation
4. **Step 5**: Core cleanup and shared utilities

---

**Dependencies**: None (Step 1 is foundational)  
**Blocks**: Steps 2-5 depend on completion of Step 1  
**Related ADRs**: ADR-0001 (Comprehensive Refactoring Roadmap)