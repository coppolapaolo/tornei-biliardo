# ADR-017: Type Safety e Input Validation nel Service Layer

## Status
Accepted

## Context
Durante lo Sprint 2 (Prova Standalone), abbiamo scoperto che `ProvaService.validate_prova_data()` falliva quando riceveva dati da form HTML (stringhe) invece di tipi nativi Python. 

Investigando, abbiamo scoperto che:
- Il metodo era stato scritto assumendo tipi già convertiti
- Le route esistenti NON usavano questo metodo di validazione
- La nuova route `create_prova_standalone` è stata la prima a usarlo con dati grezzi da form
- Non era un bug ma un contratto implicito mai documentato

## Decision
Implementiamo **Type Coercion Difensiva** nel service layer per renderlo veramente indipendente dalla fonte dati:

1. I metodi di validazione accettano sia stringhe che tipi nativi
2. Convertono internamente i tipi quando necessario
3. Validano DOPO la conversione
4. Forniscono messaggi di errore chiari per conversioni fallite
5. Non propagano eccezioni, ma le traducono in errori di validazione user-friendly

### Pattern Implementato
```python
try:
    value = int(raw_value) if isinstance(raw_value, str) else raw_value
    if value < minimum:
        errors[field] = "Valore troppo piccolo"
except (ValueError, TypeError):
    errors[field] = "Formato non valido"
```

## Consequences

### Positive
- **Single Responsibility**: Il validator gestisce TUTTA la logica di validazione
- **DRY**: Nessuna duplicazione di conversioni nelle route
- **Robustezza**: Service layer funziona con qualsiasi client (web form, API, test)
- **Liskov Substitution**: Il service può essere chiamato da qualsiasi fonte
- **User Experience**: Messaggi di errore chiari invece di 500 errors
- **Testabilità**: I test possono usare tipi nativi senza preprocessare

### Negative
- **Verbosità**: Codice più lungo nel validator
- **Performance**: Overhead minimo per type checking (trascurabile)
- **Complessità**: Logica aggiuntiva da mantenere nel service

## Alternatives Considered

1. **Conversione nelle Route** 
   - Pro: Service più semplice
   - Contro: Duplicazione logica, violazione DRY
   - Scartata: Anti-pattern architetturale

2. **Due metodi separati**
   - `validate_prova_data_strings()` e `validate_prova_data()`
   - Scartata: Complessità inutile, violazione DRY

3. **Pydantic/Marshmallow**
   - Pro: Validazione dichiarativa
   - Contro: Dipendenza esterna, overhead per progetto piccolo
   - Scartata: Overkill per questo caso

## Implementation Notes

1. Il pattern deve essere applicato a TUTTI i metodi di validazione nei service
2. I test devono coprire entrambi i casi (stringhe e tipi nativi)
3. La documentazione dei metodi deve specificare che accettano entrambi i tipi
4. Le route NON devono fare conversioni prima di chiamare i validator

## Related
- ADR-014: Sprint 1 - Supporto Prova Standalone
- ADR-015: Sprint 2 - Implementazione Prova Standalone
- ADR-016: Transaction-per-Test Pattern

## Learning
Questo caso evidenzia l'importanza di:
- Documentare contratti impliciti
- Testare con dati realistici (non solo unit test)
- Progettare service layer veramente indipendenti
- Non assumere il formato dei dati in input