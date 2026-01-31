# Transaction Domain

## Purpose

Advanced transaction management infrastructure ensuring data consistency across domain operations.

**Core Responsibilities:**
- `@transactional` decorator for automatic commit/rollback
- Nested transaction support with savepoints
- Read-only transaction optimization
- Domain service base class
- Transaction metrics and monitoring

---

## Quick Reference

```python
from models.transaction.manager import transactional, read_only, DomainService

# Basic usage - auto commit on success, rollback on exception
@transactional
def create_something():
    entity = MyEntity(name="test")
    db.session.add(entity)
    return entity  # Commit happens automatically

# With domain tracking
@transactional(domain="competition")
def update_gara(gara_id: int):
    gara = db.session.get(Gara, gara_id)
    gara.status = "playing"
    return gara

# Read-only optimization
@read_only
def get_statistics():
    return db.session.query(Match).filter_by(status="completed").count()

# Serializable isolation (for critical operations)
from models.transaction.manager import serializable

@serializable(domain="match")
def complete_match_atomically(match_id: int):
    # Runs with SERIALIZABLE isolation level
    pass
```

---

## Decorators

### @transactional
Main decorator for write operations.

```python
@transactional(
    isolation_level=None,  # Optional: TransactionIsolationLevel
    read_only=False,       # Optimize for reads
    domain=None            # Track domain access
)
```

**Behavior:**
- Opens transaction (or savepoint if nested)
- Commits on successful return
- Rolls back on exception
- Supports nested calls via savepoints

### @read_only
Shorthand for read-only transactions.

```python
@read_only(domain="classification")
def get_rankings():
    return Classification.query.all()
```

### @serializable
Shorthand for SERIALIZABLE isolation level.

```python
@serializable(domain="match")
def critical_update():
    pass
```

---

## DomainService Base Class

Base class for domain services with transaction support:

```python
from models.transaction.manager import DomainService, transactional

class GaraService(DomainService):
    def __init__(self):
        super().__init__("competition")

    @transactional(domain="competition")
    def create_gara(self, **kwargs):
        self._track_domain_access()  # Optional: explicit tracking
        gara = Gara(**kwargs)
        db.session.add(gara)
        return gara
```

---

## Nested Transactions

Nested `@transactional` calls use savepoints:

```python
@transactional(domain="match")
def outer_operation():
    # Opens transaction
    create_match()  # Uses savepoint
    update_scores()  # Uses savepoint
    # All committed together

@transactional(domain="match")
def create_match():
    # Creates savepoint, not new transaction
    pass
```

---

## Isolation Levels

```python
from models.transaction.manager import TransactionIsolationLevel

# Available levels (PostgreSQL only, ignored on SQLite)
TransactionIsolationLevel.READ_UNCOMMITTED
TransactionIsolationLevel.READ_COMMITTED
TransactionIsolationLevel.REPEATABLE_READ
TransactionIsolationLevel.SERIALIZABLE
```

---

## Import Pattern

**CRITICAL**: Always import from `models.transaction.manager`:

```python
# ✅ CORRECT
from models.transaction.manager import transactional

# ❌ WRONG - may cause circular import issues
from models.base import transactional
```

See `docs/adr/ADR-012-transactional-circular-import-fix.md` for details.

---

## Do Not

- **Do not call `db.session.commit()` manually** - `@transactional` handles it
- **Do not call `db.session.rollback()` manually** - Exception triggers automatic rollback
- **Do not import from `models.base`** - Import from `models.transaction.manager`
- **Do not use isolation levels on SQLite** - They're ignored (SQLite limitation)
- **Do not forget decorator on write methods** - Data won't persist without `@transactional`
- **Do not decorate facade methods that delegate to decorated services** - Double `@transactional` causes nested savepoints that silently rollback on SQLite

---

## Facade/Wrapper Pattern

When creating facade methods that delegate to other services, **only the innermost method should have `@transactional`**:

```python
# ❌ WRONG - Double decoration causes silent rollback on SQLite
class FacadeService:
    @transactional  # ← REMOVE THIS
    def wrapper_method(self, match_id: int):
        return InnerService.actual_method(match_id)  # Already has @transactional

class InnerService:
    @transactional
    def actual_method(self, match_id: int):
        # ... actual logic
        pass

# ✅ CORRECT - Only innermost has decorator
class FacadeService:
    def wrapper_method(self, match_id: int):
        # No decorator - delegates to decorated method
        return InnerService.actual_method(match_id)

class InnerService:
    @transactional
    def actual_method(self, match_id: int):
        # ... actual logic
        pass
```

**Why**: Nested `@transactional` creates savepoints. On SQLite, if the outer transaction commits but inner savepoint had issues, data may not persist. The symptom is: API returns success, but database shows no changes.

---

## Debugging

If data changes in memory but doesn't persist:

```python
# Check if decorator is actually applied
from models.competition.state_service import StateService
func = StateService.some_method
print(f'Has __wrapped__: {hasattr(func, "__wrapped__")}')  # False = no decorator!

# Verify correct import
from models.transaction.manager import transactional as manager_t
from models.base import transactional as base_t
print(f'Same object: {manager_t is base_t}')  # False = circular import issue!
```

---

## Cross-References

- **All Domains**: Use `@transactional` for write operations
- **ADR-012**: `docs/adr/ADR-012-transactional-circular-import-fix.md`
