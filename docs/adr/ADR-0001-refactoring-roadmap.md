# ADR-0001: Comprehensive Refactoring Roadmap

**Status**: Proposed  
**Date**: 2025-08-24  
**Deciders**: Senior Engineering Team  
**Technical Story**: Major refactoring to address technical debt and establish maintainable architecture

## Context

The tornei-biliardo Flask webapp has accumulated significant technical debt that impacts maintainability, testability, and developer velocity. The current architecture violates several clean code principles and makes it difficult to implement new features or maintain existing ones.

### Current State Problems

1. **Monolithic Route Files**: `routes/admin.py` contains 1,442 lines mixing multiple domain concerns
2. **Business Logic in Controllers**: Direct database operations and complex domain logic in route handlers
3. **Template Complexity**: Multiple templates exceed 400 lines with repeated patterns
4. **Code Duplication**: `InvalidTransitionError` defined in two different domains
5. **Inadequate Testing**: Only 2 test files covering a small portion of functionality
6. **Architecture Violations**: 39+ direct `db.session` calls in route files

### Business Impact

- **Developer Velocity**: New features take longer to implement due to code complexity
- **Bug Risk**: Large files and poor separation of concerns increase error probability  
- **Maintenance Cost**: Template and logic duplication requires multiple updates for single changes
- **Testing Difficulty**: Monolithic structure makes comprehensive testing challenging

## Decision

We will implement a comprehensive 5-milestone refactoring plan to establish a clean, maintainable architecture based on Domain-Driven Design principles with Flask Blueprints.

### Target Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Controller    │    │   Service       │
│   Templates/    │────│   Route         │────│   Business      │
│   Components    │    │   Handlers      │    │   Logic         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                       ┌─────────────────┐    ┌─────────────────┐
                       │   Core          │    │   Data          │
                       │   Shared        │    │   Models/       │
                       │   Utilities     │    │   Repository    │
                       └─────────────────┘    └─────────────────┘
```

### Refactoring Principles

1. **Single Responsibility**: Each module has one clear purpose
2. **Domain Separation**: Business logic grouped by functional domain
3. **Layered Architecture**: Clear separation between routes, services, and data
4. **Component Reuse**: Template macros and shared utilities
5. **Test Coverage**: ≥90% coverage on all refactored components

## Implementation Plan

### Milestone 1: Route Blueprint Decomposition
**Objective**: Split monolithic route files into domain-specific blueprints

**Scope**:
- `routes/admin.py` (1,442 lines) → domain-specific modules
- Preserve all existing URLs and behavior
- Eliminate circular import risks

**Success Criteria**:
- [ ] All existing tests pass
- [ ] URL endpoint compatibility maintained (verified by smoke tests)
- [ ] No nested blueprint registrations
- [ ] Zero new `db.session` calls in routes (temporary exception for existing calls)

### Milestone 2: Dashboard Unification & Component System
**Objective**: Create unified template architecture with reusable components

**Scope**:
- Unify dashboard templates across roles
- Create macro system for common UI patterns
- Reduce template files >400 lines by componentization

**Success Criteria**:
- [ ] Single unified dashboard template
- [ ] Reusable macro library (`_badges.jinja`, `_cards.jinja`, etc.)
- [ ] All templates ≤400 lines
- [ ] Template rendering tests pass

### Milestone 3: Service Layer Implementation
**Objective**: Extract business logic from routes into dedicated service classes

**Scope**:
- Create domain-specific service classes
- Implement transaction management in services
- Eliminate all `db.session` usage from routes

**Success Criteria**:
- [ ] Zero `db.session` calls in route files
- [ ] All domain logic moved to services
- [ ] Transaction boundaries properly managed
- [ ] Service contract tests implemented

### Milestone 4: Scoring Strategy Pattern
**Objective**: Implement configurable scoring policies for tournaments

**Scope**:
- Define `ScoringPolicy` interface
- Implement multiple scoring strategies
- Enable per-tournament scoring configuration

**Success Criteria**:
- [ ] Strategy pattern implementation
- [ ] Backward compatibility maintained
- [ ] All scoring variations tested

### Milestone 5: Core Cleanup & Shared Utilities
**Objective**: Centralize shared concerns and eliminate code duplication

**Scope**:
- Unify exception handling (`InvalidTransitionError` duplication)
- Create shared utilities module
- Remove dead code and deprecated features

**Success Criteria**:
- [ ] Single source of truth for exceptions
- [ ] Dead code removed or marked `@deprecated`
- [ ] Shared utilities centralized in `core/`

## Alternatives Considered

### Alternative 1: Incremental Refactoring
**Approach**: Small, scattered improvements without comprehensive planning
**Rejected Because**: 
- Technical debt accumulation would continue
- Risk of inconsistent architecture across improvements
- Difficult to ensure comprehensive testing coverage

### Alternative 2: Complete Rewrite
**Approach**: Build new application from scratch
**Rejected Because**:
- High risk of introducing new bugs
- Significant downtime and migration complexity
- Loss of domain knowledge embedded in current code

### Alternative 3: Service Extraction Only
**Approach**: Focus only on extracting business logic from routes
**Rejected Because**:
- Would not address template complexity and duplication
- Monolithic route files would remain problematic
- Testing challenges would persist

## Quality Gates

Each milestone must meet strict quality criteria before proceeding:

### Code Quality
- [ ] **Coverage**: ≥90% test coverage on all modified files
- [ ] **Linting**: `flake8` and `black --check` pass without warnings
- [ ] **Performance**: p95 response times <2s for user-facing operations

### Architecture Quality  
- [ ] **Separation of Concerns**: No business logic in route handlers
- [ ] **Transaction Management**: Proper database transaction boundaries
- [ ] **Error Handling**: Consistent exception handling with user-friendly messages

### Compatibility
- [ ] **URL Preservation**: All existing endpoints maintain compatibility
- [ ] **Behavior Preservation**: No changes to user-visible functionality
- [ ] **Database**: No foreign key violations or data inconsistencies

## Migration Strategy

### Rollback Plan
Each milestone will be implemented in a separate branch with:
- Comprehensive smoke tests for critical functionality
- Database migration scripts (if applicable)
- Feature flags for gradual rollout where appropriate

### Risk Mitigation
1. **URL Compatibility Testing**: Automated endpoint verification before/after
2. **Transaction Safety**: Service-level transaction tests with rollback verification
3. **Template Compatibility**: Snapshot testing for template rendering

## Success Metrics

### Technical Metrics
- **File Complexity**: Reduce average file size by 60%
- **Code Duplication**: Eliminate identified duplications (`InvalidTransitionError`, template patterns)
- **Test Coverage**: Achieve ≥90% coverage on refactored components
- **Architecture Compliance**: Zero `db.session` calls in route files

### Development Velocity Metrics
- **Feature Implementation**: Reduce time for new feature implementation
- **Bug Detection**: Improved bug detection through comprehensive testing
- **Developer Onboarding**: Simplified codebase navigation for new developers

## Consequences

### Positive
- **Maintainability**: Clear separation of concerns simplifies future changes
- **Testability**: Service layer enables comprehensive unit testing
- **Scalability**: Domain-based architecture supports team scaling
- **Code Quality**: Elimination of technical debt reduces bug risk

### Negative
- **Short-term Velocity**: Initial development velocity reduction during refactoring
- **Complexity**: Additional abstraction layers require developer education
- **Risk**: Large-scale changes introduce potential for regression bugs

### Neutral
- **File Count**: Increased number of smaller, focused files
- **Import Complexity**: More explicit imports required but better dependency visibility

## Follow-up Actions

1. **Team Training**: Architecture pattern education for development team
2. **Documentation**: Comprehensive developer guide for new patterns
3. **Monitoring**: Performance and error monitoring for post-refactoring validation
4. **Continuous Improvement**: Regular architecture review and refinement

---

**Status**: Awaiting approval  
**Next Review**: 2025-08-25  
**Implementation Start**: Upon approval of this ADR