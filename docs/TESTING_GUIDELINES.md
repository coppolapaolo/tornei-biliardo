# Testing Guidelines

## Pattern: Transaction-per-Test

Utilizziamo il pattern Transaction-per-Test per garantire isolamento tra test:

1. **Session Scope**: Una transazione per test con rollback automatico
2. **Fixtures Centralized**: Tutte le fixtures utente in `conftest.py`
3. **Session Management**: Uso di `db_session` fixture per accesso alla sessione

## Best Practices

1. **Non duplicare fixtures** - Usa quelle in conftest.py
2. **Usa db_session** per operazioni database nei test
3. **Refresh objects** dopo commit per mantenerli attached
4. **Type coercion** - Ricorda che i form HTML inviano stringhe

## Esempio

```python
def test_example(client, director_user, db_session):
    # director_user è già attached alla sessione
    prova = Prova(director_id=director_user.id, ...)
    db_session.add(prova)
    db_session.commit()
    db_session.refresh(prova)  # Mantieni attached
    
    # Test logic here
```