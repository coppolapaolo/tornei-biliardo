# ADR-016: Transaction-per-Test Pattern for SQLAlchemy Testing

## Status
Accepted

## Context
I test stavano fallendo con `DetachedInstanceError` perché le fixtures creavano oggetti SQLAlchemy dentro un context ma li restituivano fuori, violando il lifecycle management delle sessioni.

## Decision
Implementare il Transaction-per-Test pattern con:
- Session scope appropriato per fixtures
- Transactional rollback per isolamento dei test
- Centralizzazione delle fixtures utente in conftest.py
- Uso di `session.refresh()` per mantenere oggetti attached

## Consequences
### Positive
- Test isolati e deterministici
- Performance migliore (rollback vs drop/create)
- Fixtures riutilizzabili
- Allineamento con best practices SQLAlchemy

### Negative
- Maggiore complessità iniziale del setup
- Richiede comprensione del session lifecycle

## Trade-offs
Scegliamo robustezza e manutenibilità a lungo termine rispetto alla semplicità immediata.