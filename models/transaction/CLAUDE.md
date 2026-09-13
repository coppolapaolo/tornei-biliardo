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
from models.transaction.manager import transactional, read_only

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

## Domain Services (plain classes)

> **Nota (2026-06):** la base `DomainService` (con `_track_domain_access`/
> `_execute_with_tracking`) è stata **rimossa**: alimentava solo le metriche di
> tracking del manager, che non hanno consumatori in produzione (cfr. F1.3/F1.4
> del technical-debt review). I servizi sono ora classi semplici; il tracking di
> dominio si dichiara col solo argomento `domain=` del decoratore.

```python
from models.transaction.manager import transactional

class GaraService:
    @transactional(domain="competition")
    def create_gara(self, **kwargs):
        gara = Gara(**kwargs)
        db.session.add(gara)
        return gara
```

---

## Nested Transactions

Nested `@transactional` calls use savepoints, and **only the outermost
decorator saves** (ADR-061, 2026-09-13):

```python
@transactional(domain="match")
def outer_operation():
    # Opens transaction
    create_match()  # Uses savepoint
    try:
        update_scores()  # Uses savepoint
    except ValueError:
        pass  # only update_scores' work is undone; create_match's stays
    # All committed together, here and nowhere else

@transactional(domain="match")
def create_match():
    # Creates savepoint, not new transaction
    pass
```

Le regole, verificate sul database da `tests/new/unit/test_transazioni_annidate.py`:

- **l'esterna fallisce** dopo l'interna: si annulla tutto, interna compresa;
- **l'interna fallisce** e l'esterna cattura e prosegue: si annulla solo il
  savepoint dell'interna, il lavoro dell'esterna fatto prima resta.

Fino al 2026-09-13 era il contrario in entrambi i casi. Il ramo annidato
chiudeva il savepoint con `db.session.commit()` e lo annullava con
`db.session.rollback()`, che da SQLAlchemy 1.4 agiscono sulla transazione **più
esterna**. E con SQLite serviva un secondo accorgimento: il driver `sqlite3`
apre la transazione solo davanti a una scrittura, quindi se l'esterna aveva
soltanto letto, il `SAVEPOINT` dell'interna era il primo comando e il suo
`RELEASE` valeva un commit. Il gestore ora apre la transazione con `BEGIN`
prima del savepoint (`_apri_transazione_sqlite`).

**Non vale per i `with db.session.begin_nested()` scritti a mano** dentro i
servizi (ADR-025): chiudono il savepoint giusto, ma se prima non c'è stata
nessuna scrittura il loro `RELEASE` resta un commit su SQLite.

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
- **Do not count on an inner `@transactional` to save** - only the outermost one commits (ADR-061)

---

## Facade/Wrapper Pattern

A facade that only delegates does not need its own `@transactional`: the inner
service already has one. Adding it is no longer harmful (ADR-061): the inner
call becomes a savepoint and the facade commits. Decorate the facade when it
**composes** several writes that must succeed or fail together.

```python
class FacadeService:
    @transactional()  # composes two writes: both or neither
    def wrapper_method(self, match_id: int):
        InnerService.actual_method(match_id)   # savepoint
        OtherService.follow_up(match_id)       # savepoint

class InnerService:
    @transactional()
    def actual_method(self, match_id: int):
        # ... actual logic
        pass
```

**Storia**: fino al 2026-09-13 questa sezione vietava il doppio decoratore
perché «su SQLite i savepoint annidati annullano in silenzio». Il sintomo era
vero, la causa era il gestore: vedi «Nested Transactions» sopra e ADR-061.

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
