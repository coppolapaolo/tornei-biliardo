# [016] Validazione Sequenziale Date Gare

**Data**: 2026-01-21
**Stato**: Accepted
**Decisori**: Sistema, Utente

## Contesto

Durante la creazione di gare all'interno di un campionato, non esisteva alcuna validazione sulla coerenza temporale tra gare. Era possibile creare:

1. Una gara con data nel passato (già parzialmente gestito ma con exception non catturata)
2. Una gara N con data/ora precedente alla gara N-1
3. Una gara N con data/ora successiva alla gara N+1 (quando esistente)

Questo causava:
- Confusione nella visualizzazione delle gare ordinate per numero
- Potenziali problemi nella logica di business che assume ordinamento temporale
- Bug UX: l'app crashava con ValueError non gestito per date nel passato

## Decisione

1. **Validazione sequenziale per gare di campionato**: La gara N deve avere data/ora:
   - `>=` della gara con numero più alto `< N` (se esiste)
   - `<=` della gara con numero più basso `> N` (se esiste)

2. **Nessuna validazione sequenziale per gare standalone**: Le gare standalone hanno sempre `number=1` e non appartengono a una sequenza.

3. **Gestione eccezioni nella route**: I `ValueError` sollevati dalla validazione vengono catturati e mostrati come flash message invece di crashare l'app.

4. **UI con campi separati**: Data e ora sono ora campi separati invece di un unico `datetime-local`. L'ora viene pre-compilata dalla gara precedente (dalla gara 2 in poi).

## Alternative Considerate

### Alternativa 1: Validazione solo lato frontend

**Descrizione**: Implementare la validazione solo con JavaScript nel form.

- **Pro**:
  - Feedback immediato all'utente
  - Nessuna modifica al backend
- **Contro**:
  - Bypassabile facilmente
  - Non protegge chiamate API dirette
  - Duplicazione logica se servono entrambe

### Alternativa 2: Validazione solo nella route

**Descrizione**: Validare solo nel controller Flask, prima di chiamare il service.

- **Pro**:
  - Centralizzato nel punto di ingresso HTTP
- **Contro**:
  - Non protegge chiamate dirette al service (test, script, altre route)
  - Il service layer dovrebbe essere il garante delle business rules

### Alternativa 3: Validazione in entrambi (SCELTA)

**Descrizione**: Validazione nel service layer (safety net) + nella route (feedback immediato).

- **Pro**:
  - Service layer garantisce sempre la validità dei dati
  - Route fornisce feedback user-friendly
  - Protegge tutte le entry point
- **Contro**:
  - Leggera duplicazione di logica

## Conseguenze

### Positive

- Impossibile creare gare con date incoerenti rispetto alla sequenza
- Messaggi di errore user-friendly invece di crash dell'app
- UI migliorata con campi data/ora separati e pre-compilazione intelligente

### Negative

- Vincolo aggiuntivo che potrebbe risultare restrittivo in casi edge (es. gara posticipata)

### Rischi

- Gare esistenti con date incoerenti non vengono corrette automaticamente
- La validazione assume che `number` rappresenti l'ordine cronologico inteso

## Note Implementative

### Service Layer (`models/competition/services.py`)

```python
@staticmethod
def _validate_sequential_date(
    campionato_id: int,
    number: int,
    gara_date,
    gara_time,
) -> None:
    """Valida che data/ora siano coerenti con le gare adiacenti."""
    gara_datetime = datetime.combine(gara_date, gara_time or time(20, 0))

    # Trova gara precedente (max number < N)
    prev_gara = Gara.query.filter(
        Gara.campionato_id == campionato_id,
        Gara.number < number,
    ).order_by(Gara.number.desc()).first()

    if prev_gara:
        prev_datetime = datetime.combine(prev_gara.date, prev_gara.time or time(20, 0))
        if gara_datetime < prev_datetime:
            raise ValueError(f"La data/ora della gara {number} deve essere successiva...")

    # Trova gara successiva (min number > N)
    next_gara = Gara.query.filter(
        Gara.campionato_id == campionato_id,
        Gara.number > number,
    ).order_by(Gara.number.asc()).first()

    if next_gara:
        next_datetime = datetime.combine(next_gara.date, next_gara.time or time(20, 0))
        if gara_datetime > next_datetime:
            raise ValueError(f"La data/ora della gara {number} deve essere precedente...")
```

### Route Layer (`routes/admin/competition/crud.py`)

```python
try:
    gara = GaraService.create_gara(...)
    flash(f"Gara {number} creata con successo!")
    return redirect(...)
except ValueError as e:
    flash(str(e), "error")
    return redirect(...)
```

### UI Template (`templates/components/_new_gara_modal.html`)

- Campi separati: `<input type="date">` + `<input type="time">`
- JavaScript pre-compila l'ora dalla gara precedente quando `number > 1`

## Riferimenti

- File modificati:
  - `models/competition/services.py` - Validazione sequenziale
  - `routes/admin/competition/crud.py` - Exception handling + parsing time
  - `templates/components/_new_gara_modal.html` - UI campi separati
- Test: `tests/new/unit/test_gara_date_validation.py`
