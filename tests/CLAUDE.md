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

### Test Configuration

#### `conftest.py` - Test Configuration
**Purpose**: Shared test configuration and fixtures
- Database setup and teardown
- Application factory configuration
- Common test utilities and fixtures
- Test environment configuration

**Key fixture behaviors** (tests/new/conftest.py):
- **StaticPool**: `SQLALCHEMY_ENGINE_OPTIONS` uses `StaticPool` so all DB connections share the same SQLite in-memory database. Without this, `db.drop_all()` and the Flask test client would get different connections (= different databases), breaking test isolation.
- **Rate limiter disabled**: `limiter.enabled = False` in setup — prevents `429 Too Many Requests` from test scenarios that log in repeatedly (e.g. e2e tests).
- **Cache cleared per test**: `cache_manager.clear_all()` runs in the `db_session` fixture. Services like `ClassificationService.update_campionato_classification` are `@cached` for 5 minutes — without clearing, stale data from previous tests leaks into subsequent ones.
- **Session close vs remove**: Uses `db.session.close()` + explicit commit/rollback before `drop_all()` to ensure no pending transaction blocks DROP TABLE on the StaticPool connection.

**E2E fixture override** (tests/new/e2e/conftest.py):
- E2E tests have their own session-scoped `app` fixture that also sets `StaticPool`. The Flask test client would otherwise create its own DB connection (different from the fixture's), causing all E2E tests after the first to fail with empty databases.

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

**Current Test Files** (20 files, ~124 tests):

| File | Description | Tests |
|------|-------------|-------|
| `test_admin.py` | Admin panel functionality | 4 passed, 1 skipped |
| `test_auth.py` | Authentication workflows | 4 passed |
| `test_challenge_image_paths_fix.py` | Challenge image path handling | 6 passed |
| `test_challenge_routes.py` | Challenge CRUD routes | 22 passed |
| `test_classification_display.py` | Classification/ranking display | 1 passed, 3 skipped |
| `test_gare_usecase_1_amalfi.py` | UC1: Amalfi strategy workflow | 5 passed |
| `test_gare_usecase_2_random.py` | UC2: Random strategy workflow | 4 passed |
| `test_gare_usecase_3_round_robin.py` | UC3: Round-robin strategy | 3 passed |
| `test_gare_usecase_4_campionato_workflow.py` | UC4: Championship tournaments | 3 passed, 1 skipped |
| `test_gare_usecase_5_guest.py` | UC5: Guest access | 6 passed |
| `test_gare_usecase_6_individual.py` | UC6: Individual match proposals | 8 passed |
| `test_gare_usecase_7_player_availability.py` | UC7: Player availability | 3 passed |
| `test_gare_usecase_8_modification.py` | UC8: Match modification | 5 passed |
| `test_guest_card_to_details_workflow.py` | Guest card navigation | 6 passed |
| `test_matchmaking_anti_rematch.py` | Anti-rematch logic | 2 passed |
| `test_random_anti_rematch_tournament_flow.py` | Random strategy anti-rematch | 12 passed |
| `test_random_strategy_challenge_images.py` | Random strategy challenges | 6 passed |
| `test_ui_frontend_behaviors.py` | Frontend UI behaviors | 4 passed |
| `test_user_profile.py` | User profile operations | 3 passed |
| `test_venue_manager_notifications.py` | Venue manager notifications | 3 passed |

**Gamification Tests** (`gamification/` subdirectory):

| File | Description | Tests |
|------|-------------|-------|
| `test_achievement_workflow.py` | Achievement system | 2 passed, 6 skipped |
| `test_gamification_e2e.py` | Gamification end-to-end | 12 passed |
| `test_quest_workflow.py` | Quest system | 13 passed |
| `test_streak_workflow.py` | Streak tracking | 7 passed |
| `test_xp_workflow.py` | XP and leveling | 5 passed, 3 skipped |

**Testing Approach**:
- Real database connections (SQLite)
- Component interaction validation
- Business workflow testing
- Data consistency verification

**⚠️ Note**: Many integration tests were removed due to SQLite concurrency issues and session isolation problems with `@transactional`. The remaining tests are reliable with `-n 4`.

#### Use Case Integration Testing
**Purpose**: Test files mapped to documented use case workflows from `docs/usecases/gare.md`

**All 8 Use Cases Covered** (31 tests total):

| Use Case | File | Tests | Description |
|----------|------|-------|-------------|
| UC 1 | `test_gare_usecase_1_amalfi.py` | 5 | Amalfi strategy: rounds, anti-rematch, classification |
| UC 2 | `test_gare_usecase_2_random.py` | 4 | Random strategy: all rounds at once, classification |
| UC 3 | `test_gare_usecase_3_round_robin.py` | 3 | Round-robin: all vs all pairing, live classification |
| UC 4 | `test_gare_usecase_4_campionato_workflow.py` | 4 | Championship with multiple competitions |
| UC 5 | `test_gare_usecase_5_guest.py` | 6 | Guest access: view campionato, results, live scores |
| UC 6 | `test_gare_usecase_6_individual.py` | 8 | Individual match proposals and cancellation |
| UC 7 | `test_gare_usecase_7_player_availability.py` | 3 | Player availability and match coordination |
| UC 8 | `test_gare_usecase_8_modification.py` | 5 | Match reset, modification, round management |

**Testing Patterns Used** (January 2026 rewrite):
- Short focused tests (30-50 lines) instead of long workflows
- Explicit `db_session.commit()` in fixtures
- Unique identifiers via `uuid.uuid4()[:8]`
- Interleaved rack scoring for race-to-N matches
- Avoid complex cross-service workflows that cause session isolation issues

**Naming Convention**:
- **Pattern**: `test_<source>_usecase_<N>_<description>.py`
- `test_gare_usecase_X_*.py` for use cases from `gare.md`
- Clear naming enables traceability to source documentation

### End-to-End Tests (`new/e2e/`)
**Purpose**: percorrere i flussi utente **attraverso le route**, con il test
client di Flask. Niente browser, niente Selenium (mai stato usato: la voce in
questo file lo dichiarava, ma nessun test lo importava).

| File | Cosa copre |
|------|-----------|
| `gara_driver.py` | Il driver HTTP condiviso: login, form di creazione, iscrizioni, avvio turni, segnatura, lettura della pagina |
| `test_gara_e2e_amalfi.py` | Gara Amalfi intera + sequenza dei turni + configurazioni rifiutate |
| `test_gara_e2e_random.py` | Gara Random intera + turni tutti insieme + classifica complessiva |
| `test_gara_e2e_interazioni.py` | Percorsi di segnatura, annullamenti, permessi, iscrizioni, dispari |
| `campionato_driver.py` | Il driver del livello **sopra** la gara: wizard, gare numerate, terminazione, playoff |
| `test_campionato_e2e_playoff.py` | Campionato con quattro gare Amalfi (tre turni, «esattamente N rack») → classifica generale → playoff, sia con le conferme dei giocatori sia con la lista composta dal direttore |
| `stagione.py` | La **specifica** della stagione 2026-27 (quattro gare, discipline, distanze esatte, override per turno, X sui dispari, min 6 / max 15, spareggio fino al terzo, playoff a 8) — unica copia, i test la importano |
| `test_stagione_e2e_configurazione.py` | Il campionato e le quattro gare nascono come da specifica, override per turno compresi. Nessuna partita giocata: pochi secondi |
| `test_stagione_e2e_iscrizioni.py` | Finestra, lista d'attesa oltre il massimo, disiscrizioni, iscrizione e cancellazione dal direttore, gara sotto il minimo |
| `test_stagione_e2e_risultati.py` | Le cinque strade che chiudono una partita, i tre modi di tornare indietro, il pareggio a distanza pari, i tavoli e lo swap |
| `test_stagione_e2e_stagione.py` | La stagione giocata con quindici iscritti: la X a ogni turno, gli override sulle partite vere, lo spareggio SSR, i playoff a 8 e la finale a tre turni diversi |
| `test_stagione_e2e_handicap.py` | L'handicap: categorie create assegnandole, riporto da una gara all'altra, finestra chiusa all'avvio, Elo che si muove solo fra pari categoria |
| `test_complete_workflows.py` | Promozione a direttore, workflow storici |

**Perché il livello campionato ha il suo file.** Le gare sono coperte una per
una e i playoff hanno i loro test di route, ma ciascuno parte dallo stato
dell'altro *costruito a mano*: `test_avvio_playoff_route.py` scrive
`terminated_at` e le righe di classifica direttamente sul DB. Il giunto fra le
due metà non lo percorreva nessuno — ed è dove è nato il bug 8 di
`docs/debug20260528.md`, e dove è stato trovato il secondo (data della gara di
playoff, `tests/new/unit/test_playoff_gara_date_sequence.py`). L'allestimento
costa: si usa `campionato_terminato` (quattro gare, ~14 s) solo dove le quattro
gare contano, e `campionato_breve` (una gara) per permessi e vincoli.

**I test `stagione_*`** rispondono a una domanda diversa dalle altre: non «il
prodotto funziona?» ma «*questa* stagione, configurata così, funziona?». Sono
scritti attorno alla configurazione reale di un campionato in programma, e
tengono i costi separati per livello: la configurazione non gioca partite
(secondi), le iscrizioni nemmeno, i risultati usano sei giocatori, e solo
`test_stagione_e2e_stagione.py` gioca le quattro gare con quindici iscritti
(~27 s per la fixture piena, ~7 s per quella a una gara sola).

**Il margine dei punteggi varia di proposito.** `GaraDriver._sequenza_rack`
deriva dall'id della partita quanti rack prende il perdente. Non è un vezzo: se
ogni partita finisse col margine minimo, la differenza triangoli diventerebbe
`vittorie − sconfitte` e il secondo criterio della classifica WINS — la chiave
di pari merito è `(matches_won, rack_difference)` — smetterebbe di
discriminare. La suite girerebbe in un mondo in cui gli spareggi scattano
sempre e il secondo criterio non è mai messo alla prova. Chi vuole i pari
merito *garantiti* usa `pareggia_turno`, che è dichiarato. Gli user journey
corrispondenti sono descritti in
[`docs/usecases/stagione-amalfi-playoff.md`](../docs/usecases/stagione-amalfi-playoff.md).

**Cosa cerca questo livello** — e cosa no. Le regole di dominio (trio, bye,
lista d'attesa, anti-reincontro, spareggi) hanno i loro test di unità, dove si
decidono: rifarle qui costa tempo e non aggiunge fiducia. Un caso merita un e2e
solo se può rompersi **nel passaggio interfaccia↔server**: un permesso applicato
al ruolo globale invece che ai permessi sulla gara (issue #66), un pulsante che
punta all'endpoint sbagliato, un rifiuto del dominio che diventa 500 invece che
messaggio, uno stato che la pagina non mostra.

**Regole di scrittura**:
- **Azioni solo via HTTP.** Nessun service chiamato a mano: se una cosa non si
  può fare da una route, il test non la fa — ed è un'informazione.
- **Il sorteggio è casuale** (`draw_seed`): si asserisce sulla *forma* del turno
  (quante partite, chi compare quante volte), mai su chi incontra chi.
- **`start_round/<n>` risponde sempre 200**, anche quando rifiuta: l'esito sta in
  `success` del JSON. Asserire sullo status code lì non verifica nulla.
- **Un rilievo trovato ma non ancora corretto** si scrive come test
  `@pytest.mark.xfail(strict=True)` con la spiegazione in `reason`: descrive il
  comportamento voluto, ed è già il test di regressione pronto per il giorno del
  fix (con `strict` pytest avvisa se passa).

### Frontend Headless Tests (`frontend/` — jsdom, Node)
**Purpose**: Test the deterministic **client-side JS logic** that the Python
suite cannot reach (no browser). Currently covers the gamification badge /
anti-invasiveness intensity scale (§11/§11-quater).

- **File**: `tests/frontend/test_gamification_badge.cjs` — loads the *real*
  `static/js/gamification.js` in a jsdom window and asserts: XP → no toast
  (badge-only), level-up → one toast exempt from the session cap + glow + level
  update, cap = 1 capped toast/session (with reset + privacy degrade),
  `prefers-reduced-motion` no-op, confetti only on strong events,
  welcome/nudge/unlock toasts. **26 checks**.
- **Run**: `cd tests/frontend && npm install && npm test`
  (jsdom is the only dependency; `node_modules` is gitignored).
- **Standalone toolchain**: intentionally decoupled from pytest and not in CI
  yet. Run it manually after touching `static/js/gamification.js` or the badge
  markup in `templates/base.html`.
- **Scope**: covers the *automatable* subset of
  `docs/reference/GAMIFICATION_V3_MANUAL_TEST_REPORT.md` (24/36 rows `✅ auto`);
  the remaining 12 rows are visual and stay a human browser gate.

## Test Markers and Categories

### Pytest Markers
Configuration in `pytest.ini`:

```ini
[tool:pytest]
markers =
    unit: Unit tests for isolated components
    integration: Integration tests for component interactions
    e2e: End-to-end tests for complete workflows
    slow: Tests that take longer than 5 seconds
    requires_network: Tests requiring external network access
```

### Test Execution
- **Default**: `pytest` (runs unit + integration)
- **Correct Path**: `PYTHONPATH=. pytest tests/new/` (REQUIRED for proper imports)
- **Unit only**: `PYTHONPATH=. pytest tests/new/unit/ -n auto`
- **Integration only**: `PYTHONPATH=. pytest tests/new/integration/ -n 4` ⚠️ **MUST use -n 4**
- **E2E only**: `PYTHONPATH=. pytest tests/new/e2e/`

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
- **Performance**: Query optimization (caching via `optimized_query`, eager loading via `bulk_load_relationships`)

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
- **Flask test client**: richieste HTTP vere in-process, sulle route vere. È
  tutto ciò che serve al livello e2e (vedi `new/e2e/gara_driver.py`)
- **jsdom + Node** (`tests/frontend/`): il JavaScript deterministico, che il
  test client non esegue
- **Playwright**: installato nel venv ma **non** usato dai test — lo usa
  `scripts/help_docs/capture_screenshots.py` per generare le schermate della
  guida. È la strada già pronta se un giorno servisse un livello con browser
  vero (il JS inline, il polling live, i modali)

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
5. **Tutti i test stanno in `tests/new/`**: la vecchia `tests/legacy/` è stata
   cancellata (non si importava più: nessuno di quei test girava)

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

---

## Do Not

- **Do not use `-n auto` for integration tests** - Use `-n 4` to avoid SQLite deadlocks
- **Do not use `db.session.refresh()`** - Use `db.session.get()` for test isolation
- **Do not create long workflow tests** - Keep tests 30-50 lines, focused on one behavior
- **Do not share state between tests** - Each test must be independent
- **Do not clear `EventBus._handlers = {}`** - This removes ALL handlers (notification, gamification, etc.) and breaks other tests running in parallel. Instead, save handlers before test and restore after:
  ```python
  @pytest.fixture(autouse=True)
  def preserve_handlers():
      original = {k: list(v) for k, v in EventBus._handlers.items()}
      yield
      EventBus._handlers = original
  ```