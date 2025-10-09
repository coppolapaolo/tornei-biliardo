# TODO: Unificare MatchStatus

## Problema

Attualmente esistono **DUE** definizioni di `MatchStatus` nel codebase:

### 1. `models/status_enum.py` - Per Match (tornei)
```python
class MatchStatus(_StrEnum):
    PENDING = "pending"
    PLAYING = "playing"
    COMPLETED = "completed"
    VALIDATED = "validated"
```

### 2. `models/individual_match/models.py` - Per IndividualMatch
```python
class MatchStatus(Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
```

## Conseguenze

1. **Confusione**: Due enum con lo stesso nome ma valori diversi
2. **Import conflicts**: Bisogna fare `from X import MatchStatus as YMatchStatus`
3. **Complessità in BaseMatchMixin**: Deve gestire entrambi i tipi
4. **Manutenzione difficile**: Cambio in uno non si riflette nell'altro
5. **Rischio errori**: Facile usare il wrong enum

## Soluzione Proposta

### Opzione A: Unificare in un solo enum (RACCOMANDATA)

Creare un unico `MatchStatus` in `models/status_enum.py` che copra entrambi i casi:

```python
class MatchStatus(_StrEnum):
    # Tournament matches
    PENDING = "pending"          # Match creato ma non ancora iniziato
    PLAYING = "playing"          # Match in corso (tournament)

    # Individual matches
    SCHEDULED = "scheduled"      # Match programmato
    IN_PROGRESS = "in_progress"  # Match in corso (individual)

    # Comuni
    COMPLETED = "completed"      # Match terminato
    VALIDATED = "validated"      # Match validato da admin
    CANCELLED = "cancelled"      # Match annullato
```

**Pro**:
- Un solo enum da mantenere
- Import semplice e chiaro
- BaseMatchMixin molto più semplice
- Meno codice duplicato

**Contro**:
- Più valori nell'enum (ma ben documentati)
- Miglior mappatura tipo→stato

### Opzione B: Rinominare gli enum

Mantenere due enum ma con nomi diversi:

```python
# In models/status_enum.py
class TournamentMatchStatus(_StrEnum):
    PENDING = "pending"
    PLAYING = "playing"
    COMPLETED = "completed"
    VALIDATED = "validated"

# In models/individual_match/models.py
class IndividualMatchStatus(Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
```

**Pro**:
- Separazione chiara
- Nessun cambio nei valori

**Contro**:
- Ancora due enum da mantenere
- BaseMatchMixin ancora complesso
- Più codice

## Impatto del Cambio

### File da modificare (Opzione A):

1. `models/status_enum.py` - Unire i valori
2. `models/individual_match/models.py` - Rimuovere MatchStatus locale, usare quello globale
3. `models/match/base_match.py` - Semplificare (usare solo un enum)
4. `models/match/models.py` - Verificare import
5. `models/individual_match/services.py` - Aggiornare import
6. `routes/individual_match.py` - Aggiornare import
7. `tests/**/*` - Aggiornare test

### Migration necessaria?

**NO** - È solo cambio di codice, il database usa già i valori stringa

## Piano di Implementazione (Opzione A)

### 1. Preparazione (5 min)
```bash
# Trova tutti gli usi di MatchStatus
grep -r "from.*MatchStatus" models/ routes/ tests/
grep -r "MatchStatus\." models/ routes/ tests/
```

### 2. Unifica enum (10 min)
```python
# In models/status_enum.py
class MatchStatus(_StrEnum):
    """
    Status for all match types (tournament and individual).

    Tournament matches: PENDING → PLAYING → COMPLETED → VALIDATED
    Individual matches: SCHEDULED → IN_PROGRESS → COMPLETED/CANCELLED
    """
    # Tournament match lifecycle
    PENDING = "pending"
    PLAYING = "playing"

    # Individual match lifecycle
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"

    # Common final states
    COMPLETED = "completed"
    VALIDATED = "validated"
    CANCELLED = "cancelled"
```

### 3. Rimuovi enum duplicato (2 min)
```python
# In models/individual_match/models.py
# REMOVE:
# class MatchStatus(Enum):
#     ...

# ADD at top:
from ..status_enum import MatchStatus
```

### 4. Semplifica BaseMatchMixin (15 min)
```python
# In models/match/base_match.py
from models.status_enum import MatchStatus

def is_ready_for_validation(self) -> bool:
    # Much simpler now!
    if isinstance(self.status, str):
        if self.status not in [MatchStatus.PLAYING.value, MatchStatus.IN_PROGRESS.value]:
            return False
    else:
        if self.status not in [MatchStatus.PLAYING, MatchStatus.IN_PROGRESS]:
            return False
    return self.rack_score.is_complete()
```

### 5. Test (20 min)
```bash
# Run all tests
PYTHONPATH=. pytest tests/new/unit/test_base_match_tdd.py -v -n auto
PYTHONPATH=. pytest tests/new/ -k "match" -v -n auto
```

### 6. Update docs (10 min)
Update CLAUDE.md and related docs

**Tempo totale stimato**: ~1 ora

## Priorità

🔴 **ALTA** - Questo dovrebbe essere fatto prima di continuare con l'implementazione della nuova UX per i match di gara, perché semplifica molto il codice.

## Note

- Il cambio è **backward compatible** perché i valori stringa nel database non cambiano
- BaseMatchMixin diventa molto più semplice
- Tutti gli import diventano `from models.status_enum import MatchStatus`
- Meno confusione per futuri sviluppatori
