# Tests Directory - Community Platform Testing

This directory contains the comprehensive test suite for the American Pool community platform, covering both tournament features and community engagement functionality.

## Testing Architecture Overview

The test suite follows a modern pytest-based approach with clear separation between test types and comprehensive coverage of all application layers.

## Test Organization

### Directory Structure

#### `new/` - Modern Test Suite
**Purpose**: Current testing implementation using pytest best practices
- Organized by test type (unit, integration, e2e)
- Modern fixtures and test patterns
- Comprehensive coverage strategy

#### `legacy/` - Legacy Test Suite
**Purpose**: Existing tests being gradually migrated
- Contains historical test implementations
- Excluded from default test runs
- Referenced for migration purposes

### Test Configuration

#### `conftest.py` - Test Configuration
**Purpose**: Shared test configuration and fixtures
- Database setup and teardown
- Application factory configuration
- Common test utilities and fixtures
- Test environment configuration

## Test Categories

### Unit Tests (`new/unit/`)
**Purpose**: Test individual components in isolation

**Organization by Domain**:
- `test_user_authentication.py`: Community member authentication and profiles
- `test_user_services.py`: Community member services and social features
- `test_competition_models.py`: Tournament and event models
- `test_competition_services.py`: Tournament organization and community events
- `test_match_models.py`: Both tournament and casual match functionality
- `test_matchmaking_strategies.py`: All supported algorithms for tournaments
- `test_individual_match_services.py`: Community casual match system
- `test_classification_services.py`: Community rankings and statistics
- `test_notification_services.py`: Community communication system

**Testing Approach**:
- Isolated component testing
- Mock external dependencies
- Fast execution (< 1 second per test)
- High code coverage target (> 90%)

### Integration Tests (`new/integration/`)
**Purpose**: Test component interactions and data flow

**Focus Areas**:
- `test_database_integration.py`: Database operations and relationships
- `test_matchmaking_integration.py`: All matchmaking strategies with real data
- `test_competition_workflow.py`: End-to-end competition flow
- `test_match_execution.py`: Match lifecycle management
- `test_user_role_integration.py`: Role-based access control
- `test_notification_integration.py`: Notification delivery workflow

**Testing Approach**:
- Real database connections
- Component interaction validation
- Business workflow testing
- Data consistency verification

#### Use Case Integration Testing
**Purpose**: Specific test files for documented use case workflows

**Use Case Documentation Mapping**:
- **`docs/usecases/gare.md`** → Tournament creation and management workflows (8 use cases)
  - Use Case 1: `test_gare_usecase_1_amalfi_complete_workflow.py` - Complete Amalfi tournament workflow (admin/director creates 3-round tournament with inscriptions, anti-rematch, tiebreakers)
  - Use Case 2: `test_gare_usecase_2_random_strategy.py` - Random strategy tournaments with challenges and discipline changes
  - Use Case 3: `test_gare_usecase_3_round_robin.py` - Round-robin tournaments with multi-set matches
  - Use Case 4: `test_gare_usecase_4_campionato_workflow.py` - Championship tournaments with multiple competitions
  - Use Case 5: `test_gare_usecase_5_guest_access.py` - Guest access to ongoing championships and live results
  - Use Case 6: `test_gare_usecase_6_individual_matches.py` - Individual match proposals and validation
  - Use Case 7: `test_gare_usecase_7_player_availability.py` - Player availability system and match coordination
  - Use Case 8: `test_gare_usecase_8_match_modification.py` - Match modification and round management

- **`docs/usecases/UC01.md`** → Guest access and UI interaction workflows (7 use cases)
  - Use Cases 1-7: `test_UC01_usecase_1_to_7_guest_access_workflows.py` - Guest access, match modification, round ordering, table assignment, challenge integration, standalone challenges, profile export

**Naming Convention**:
- **Standard Pattern**: `test_nomefile_usecase_X_*.py` where `nomefile` is the source document name
- `test_gare_usecase_X_*.py` for use cases from `gare.md`
- `test_UC01_usecase_X_*.py` for use cases from `UC01.md`
- Clear distinction prevents confusion between different "Use Case 1" definitions
- Consistent naming enables easy identification of source documentation

### End-to-End Tests (`new/e2e/`)
**Purpose**: Test complete user workflows through the web interface

**Community Scenarios**:
- `test_member_onboarding_flow.py`: Complete community member registration
- `test_tournament_organization_flow.py`: Community leader event organization
- `test_casual_match_flow.py`: Social match proposal and coordination
- `test_community_interaction_flow.py`: Member-to-member social features
- `test_admin_community_management.py`: Platform moderation and administration

**Testing Approach**:
- Selenium WebDriver automation
- Real browser interaction
- Complete user workflow validation
- Cross-browser compatibility testing

## Test Markers and Categories

### Pytest Markers
Configuration in `pytest.ini`:

```ini
[tool:pytest]
markers =
    unit: Unit tests for isolated components
    integration: Integration tests for component interactions
    e2e: End-to-end tests for complete workflows
    legacy: Legacy tests (excluded by default)
    slow: Tests that take longer than 5 seconds
    requires_network: Tests requiring external network access
```

### Test Execution
- **Default**: `pytest` (runs unit + integration, excludes legacy)
- **Correct Path**: `PYTHONPATH=. pytest tests/new/` (REQUIRED for proper imports)
- **Unit only**: `PYTHONPATH=. pytest tests/new/unit/ -n auto`
- **Integration only**: `PYTHONPATH=. pytest tests/new/integration/ -n 4` ⚠️ **MUST use -n 4**
- **E2E only**: `PYTHONPATH=. pytest tests/new/e2e/`
- **Legacy tests**: `pytest tests/legacy/` (separate, not maintained)

**⚠️ SQLite Concurrency Warning**: Integration tests MUST use `-n 4` (not `-n auto`).
With more workers, SQLite creates deadlocks causing infinite loops.

## Testing Strategies

### Community-Focused Testing
Tests organized by platform domains supporting community growth:
- **User Domain**: Member authentication, profiles, and social features
- **Competition Domain**: Tournament organization and community events
- **Match Domain**: Both formal competition and casual social matches
- **Matchmaking Domain**: Fair pairing algorithms for all skill levels
- **Individual Match Domain**: Community-driven casual game coordination
- **Notification Domain**: Community communication and social interaction
- **Location Domain**: Venue management and community space coordination

### Data Testing Strategies
- **Model Validation**: Field constraints and relationships
- **Business Rules**: Domain-specific validation logic
- **Data Integrity**: Foreign key relationships and cascades
- **Performance**: Query optimization and N+1 detection

### Service Layer Testing
- **Transaction Management**: Rollback and commit behavior
- **Error Handling**: Exception propagation and recovery
- **Cross-Domain Operations**: Multi-service coordination
- **Cache Integration**: Cache invalidation and consistency

## Test Data Management

### Fixtures and Factories
- **User Factories**: Various user roles and states
- **Competition Factories**: Different tournament configurations
- **Match Factories**: Various match states and outcomes
- **Database Fixtures**: Clean database state per test

### Test Data Isolation
- **Database Transactions**: Rollback after each test
- **Independent Test Data**: No shared state between tests
- **Predictable Scenarios**: Consistent test data setup
- **Edge Case Coverage**: Boundary condition testing

## Coverage and Quality Metrics

### Coverage Targets
- **Unit Tests**: > 90% line coverage
- **Integration Tests**: > 80% business logic coverage
- **E2E Tests**: > 70% user workflow coverage
- **Overall**: > 85% total application coverage

### Quality Metrics
- **Test Execution Time**: Unit tests < 30 seconds total
- **Reliability**: < 1% flaky test rate
- **Maintainability**: Clear test naming and structure
- **Documentation**: Each test file has purpose and scope

## Performance Testing

### Load Testing Scenarios
- **Competition Creation**: Multiple simultaneous tournaments
- **Match Scoring**: Concurrent match updates
- **User Registration**: High-volume user signup
- **Matchmaking Algorithms**: Large tournament pairing for all strategies

### Performance Benchmarks
- **Database Queries**: < 100ms for standard operations
- **Page Load Times**: < 2 seconds for standard pages
- **API Responses**: < 500ms for API endpoints
- **Algorithm Performance**: All strategy pairing < 5 seconds for 100 players

## Security Testing

### Authentication Testing
- **Login Security**: Password validation and session management
- **Role Enforcement**: Access control across all endpoints
- **Data Protection**: Personal data encryption/decryption
- **CSRF Protection**: Form submission security

### Data Security
- **Input Validation**: SQL injection and XSS prevention
- **Permission Boundaries**: Role-based data access
- **Audit Trail**: Security event logging
- **Encryption**: Personal data protection compliance

## Development Workflow

### Test-Driven Development
1. **Write Test**: Define expected behavior
2. **Implement Feature**: Make test pass
3. **Refactor**: Improve code quality
4. **Validate**: Ensure all tests pass

### Continuous Integration
- **Pre-commit Hooks**: Run unit tests before commit
- **CI Pipeline**: Full test suite on pull requests
- **Coverage Reporting**: Track coverage trends
- **Quality Gates**: Minimum coverage and test pass rates

### Test Maintenance
- **Regular Review**: Update tests with feature changes
- **Legacy Migration**: Gradually move legacy tests to new structure
- **Performance Monitoring**: Track test execution time
- **Flaky Test Management**: Identify and fix unreliable tests

## Testing Tools and Libraries

### Core Testing Framework
- **pytest**: Primary testing framework
- **pytest-flask**: Flask application testing utilities
- **pytest-cov**: Coverage reporting
- **factory-boy**: Test data factories

### Database Testing
- **SQLAlchemy**: ORM testing utilities
- **pytest-postgresql**: Isolated database testing
- **alembic**: Migration testing

### Web Testing
- **Selenium**: Browser automation
- **pytest-selenium**: Selenium integration
- **WebDriverManager**: Browser driver management

### Mock and Fixtures
- **pytest-mock**: Mocking utilities
- **responses**: HTTP request mocking
- **freezegun**: Time-based testing

## Best Practices

### Test Writing Guidelines
1. **Clear Naming**: Test names describe behavior being tested
2. **Single Responsibility**: Each test validates one specific behavior
3. **Arrange-Act-Assert**: Clear test structure pattern
4. **Independent Tests**: No dependencies between tests
5. **Meaningful Assertions**: Clear validation of expected outcomes

### Development Workflow Integration
**MANDATORY for all code changes:**
1. **Run tests with correct path**: `PYTHONPATH=. pytest tests/new/`
2. **Individual test isolation**: Each test must pass independently
3. **Type safety**: Ensure all new test code passes `pyright` checks
4. **Test data isolation**: Fix database state issues, not test logic
5. **Focus on new tests**: Legacy tests (`tests/legacy/`) are not maintained

### Performance Guidelines
- **Fast Unit Tests**: Optimize for quick feedback
- **Isolated Integration Tests**: Minimize external dependencies
- **Efficient E2E Tests**: Focus on critical user paths
- **Parallel Execution**: Run tests concurrently where possible

### Maintenance Guidelines
- **Regular Updates**: Keep tests current with features
- **Documentation**: Clear test purpose and setup
- **Code Review**: Test code quality standards
- **Monitoring**: Track test health and performance