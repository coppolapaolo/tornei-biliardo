# ADR-018: SQLAlchemy 2.0 Migration Technical Debt

## Status
Acknowledged

## Context
Durante i test dello Sprint 2, abbiamo identificato 10 deprecation warning di SQLAlchemy:
- `Query.get()` è deprecato in favore di `Session.get()`
- Questi warning non causano errori ma indicano che il codice dovrà essere aggiornato per SQLAlchemy 2.0

## Decision
**Postponiamo** la migrazione a SQLAlchemy 2.0 patterns per ora perché:
1. I warning non impattano la funzionalità
2. Siamo in fase di delivery di features critiche
3. La migrazione richiede modifiche in molti file

## Technical Debt Identificato

### Locations da Aggiornare
1. `models/user/permissions.py`:
   - Linea ~93: `Prova.query.get(competition_id)`
   - Linea ~208: `Match.query.get(match_id)`

2. Routes con pattern `Model.query.get_or_404()`:
   - Multipli file in `routes/`
   - Fixture di test

### Pattern di Migrazione
```python
# OLD (deprecato)
obj = Model.query.get(id)
obj = Model.query.get_or_404(id)

# NEW (SQLAlchemy 2.0)
obj = db.session.get(Model, id)
obj = db.session.get(Model, id) or abort(404)
```

## Consequences
### Positive
- Focus su feature delivery
- Nessun impatto immediato su funzionalità
- Tempo per pianificare migrazione completa

### Negative
- Accumulo di technical debt
- Warning nei test output
- Futura migrazione più complessa se rimandata troppo

## Action Plan
1. **Sprint 3**: Creare utility functions per centralizzare i pattern
2. **Sprint 4**: Migrazione graduale file per file
3. **Sprint 5**: Completare migrazione e aggiornare documentazione

## Notes
- SQLAlchemy 1.x continuerà a funzionare per diverso tempo
- La migrazione può essere fatta incrementalmente
- Priorità: BASSA (non bloccante)