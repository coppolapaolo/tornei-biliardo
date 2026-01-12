# ADR-012: Fix Circular Import in @transactional Decorator

## Status
Resolved (2026-01-12)

## Context

Il pulsante "Avvia Spareggio (SSR)" non funzionava: l'API ritornava `success: true` ma lo stato della gara non persisteva nel database.

## Il Bug

### Sintomi Osservati
1. Click su "Avvia Spareggio (SSR)" → modal conferma appare → click "Conferma"
2. API `/admin/gara/7/start_ssr` ritorna `{"success": true, "ssr_groups": [...]}`
3. Pagina si ricarica ma lo stato è ancora "playing" invece di "awaiting_ssr"
4. **Nessun errore nei log**

### Diagnosi Iniziale (Fuorviante)
- Controllato il JavaScript → funzionava correttamente
- Controllato `showConfirm()` modal → funzionava
- Controllato la route Flask → sembrava corretta
- Controllato `StateService.start_ssr()` → sembrava corretto
- Controllato `@transactional` decorator → sembrava corretto

### Il Problema Reale: Circular Import Silenzioso

In `models/base.py`:

```python
# ORDINE SBAGLIATO!
try:
    from .transaction.manager import transactional  # Linea 20
except ImportError:
    # Fallback silenzioso - PERICOLOSISSIMO!
    def transactional(domain=None):
        def decorator(func):
            return func  # ← NO-OP: ritorna la funzione originale!
        return decorator

db = SQLAlchemy()  # Linea 29 - DOPO l'import!
```

In `models/transaction/manager.py`:

```python
from ..base import db  # Linea 18 - Richiede db!
```

### Sequenza di Import
1. Python carica `models/base.py`
2. Linea 20: tenta `from .transaction.manager import transactional`
3. Python inizia a caricare `models/transaction/manager.py`
4. Linea 18: tenta `from ..base import db`
5. `models/base.py` è già in caricamento (incompleto), `db` non esiste ancora!
6. `ImportError` → fallback no-op decorator attivato
7. **TUTTI i servizi che usano `@transactional` da `models.base` ottengono il no-op!**

### Come Trovare Bug Simili

#### 1. Verificare che il Decorator sia Realmente Applicato
```python
from models.competition.state_service import StateService

func = StateService.start_ssr
print(f'Has __wrapped__: {hasattr(func, "__wrapped__")}')  # False = no decorator!
print(f'Closure: {func.__closure__}')  # None = no decorator!
```

#### 2. Tracciare lo Stato della Sessione
```python
print(f'dirty before: {bool(db.session.dirty)}')
gara.status = 'new_status'
print(f'dirty after: {bool(db.session.dirty)}')  # True = tracked
db.session.commit()
# Se dirty era True prima del commit ma i dati non persistono → commit non funziona
```

#### 3. Confrontare Import Diversi
```python
from models.base import transactional as base_transactional
from models.transaction.manager import transactional as manager_transactional

print(f'Same: {base_transactional is manager_transactional}')  # False = problema!
```

## Decision

Spostare la definizione di `db` PRIMA dell'import di `transactional`:

```python
# models/base.py - ORDINE CORRETTO

from flask_sqlalchemy import SQLAlchemy
# ... altri import ...

# 1. Definire db PRIMA (richiesto da transaction/manager.py)
db = SQLAlchemy()

# 2. Importare transactional DOPO (ora db esiste quando manager.py lo importa)
try:
    from .transaction.manager import transactional
except ImportError:
    def transactional(domain=None):
        def decorator(func):
            return func
        return decorator
```

## Consequences

### Positive
- `@transactional` funziona correttamente
- SSR e tutti gli altri servizi con `@transactional` ora persistono i dati
- Nessun breaking change per il codice esistente

### Negative
- Il fallback silenzioso rimane un pattern pericoloso

## Lezioni Apprese

### 1. Fallback Silenziosi sono Pericolosi
Se un import fallisce e c'è un fallback, **deve loggare un warning**:
```python
except ImportError as e:
    import logging
    logging.warning(f"Failed to import transactional, using no-op fallback: {e}")
    def transactional(domain=None):
        ...
```

### 2. Ordine di Definizione nei Moduli è Critico
Quando si hanno circular import, l'ordine delle definizioni determina cosa è disponibile al momento dell'import.

### 3. "Funziona in Memoria ma non Persiste" = Sospettare Transaction/Commit
Se i dati cambiano in memoria ma non nel DB:
- Verificare che `@transactional` sia realmente applicato
- Verificare che `db.session.commit()` venga chiamato
- Verificare che non ci siano rollback nascosti

### 4. Decorator Inspection
```python
# Quick check per verificare se un decorator è applicato:
import inspect
func = SomeClass.some_method
print(inspect.signature(func))  # Firma
print(func.__closure__)         # None = probabilmente non decorato
print(func.__wrapped__)         # AttributeError = non decorato con @wraps
```

## Related
- `models/base.py` - Fix applicato
- `models/transaction/manager.py` - Transaction manager
- `models/competition/state_service.py` - Servizio che usa @transactional

---

## Correzioni Correlate (Stessa Sessione)

### Bootstrap Upgrade 5.1.3 → 5.3.3

**Problema**: I toast di errore avevano sfondo chiaro invece che rosso, e il bottone X era invisibile.

**Causa**: La classe `text-bg-danger` è stata introdotta in Bootstrap 5.2. Con Bootstrap 5.1.3, la classe non esisteva.

**Fix**: Aggiornato Bootstrap a 5.3.3 in `templates/base.html`. Anche aggiunto fallback compatibile in `notifications.js` usando `bg-danger text-white`.

### SSR Score Validation (Punteggio 0 non accettato)

**Problema**: Inserendo `0` come punteggio SSR, la validazione falliva con "I punteggi devono essere numeri interi positivi".

**Causa**: La validazione usava `score > 0` invece di `score >= 0`. Il valore `0` è un punteggio SSR valido.

**Fix**:
1. Frontend (`gara_detail.html`): Cambiato `input.min = '1'` → `'0'` e `value <= 0` → `value < 0`
2. Backend (`spareggio_service.py`): Cambiato `score <= 0` → `score < 0`
3. Logica risoluzione: Rimosso check `all(s > 0)`, usa solo uniqueness check

### Toast Persistenti

**Problema**: I toast di errore non scomparivano anche dopo aver corretto l'errore.

**Causa**: `showError()` creava toast con `autohide: false` senza rimuovere i precedenti.

**Fix**: Aggiunta funzione `clearErrorToasts()` che viene chiamata prima di mostrare un nuovo errore.
