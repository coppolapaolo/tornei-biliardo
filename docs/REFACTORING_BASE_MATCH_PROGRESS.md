# Refactoring BaseMatch - Progresso Implementazione

## Data: Ottobre 2025

## Obiettivo
Unificare la UX semplificata per la gestione rack tra Match (tornei) e IndividualMatch (match casuali) attraverso una classe base condivisa.

## ✅ Completato

### 1. Analisi Architetturale
- **Decisione**: NON unificare Match e IndividualMatch in una classe unica
- **Motivo**: Contesti troppo diversi (tornei vs match casuali)
- **Soluzione**: Creare BaseMatchMixin per condividere logica comune

### 2. Creazione BaseMatchMixin
- **File**: `models/match/base_match.py`
- **Pattern**: Mixin class (non abstract class) per evitare conflitti di metaclass con SQLAlchemy
- **Funzionalità**:
  - `is_ready_for_validation()`: Verifica se match ha raggiunto la distanza
  - `confirm_result(user_id)`: Conferma risultato da parte di un giocatore
  - `reject_result(user_id)`: Rifiuta risultato e rimuove ultimo rack
  - `reset_confirmations()`: Reset conferme quando cambia il punteggio
  - `_remove_last_rack(user_id)`: Template method (da implementare nelle sottoclassi)

### 3. Migrazione Database
- **Script IndividualMatch**: `utils/migrations/add_individual_match_validation_fields.py` ✅ ESEGUITO
- **Script Match**: `utils/migrations/add_match_validation_fields.py` ✅ ESEGUITO
- **Campi aggiunti**:
  - `player1_confirmed`, `player2_confirmed` (Boolean)
  - `player1_confirmed_at`, `player2_confirmed_at` (DateTime)
  - `added_by_id`, `added_at`, `removed_by_id`, `removed_at`, `is_deleted` (per log rack)

### 4. Refactoring Modelli
- ✅ `Match` ora eredita da `BaseMatchMixin`
- ✅ `IndividualMatch` ora eredita da `BaseMatchMixin`
- ✅ Entrambi implementano `_remove_last_rack()` specifico per il loro tipo di Rack
- ✅ Rimossi metodi duplicati da `IndividualMatch` (erano già in BaseMatchMixin)
- ✅ Formattazione con black completata

### 5. Test TDD
- **File**: `tests/new/unit/test_base_match_tdd.py`
- **Stato**: Creato con 10 test case
- **Problema rilevato**: Fixture usa `GaraStatus.OPEN_INSCRIPTION` che non esiste
- **Fix necessario**: Usare `GaraStatus.INSCRIPTION`

## 📋 Prossimi Passi

### 1. Fix Test TDD (IMMEDIATO)
```python
# In tests/new/unit/test_base_match_tdd.py linea 189
status=GaraStatus.INSCRIPTION.value,  # Fix: era OPEN_INSCRIPTION
```

### 2. Implementare Servizi per Match
Creare in `models/match/services.py`:
```python
@transactional(domain="match")
def add_rack_for_player(match_id: int, user_id: int, winner_id: int) -> Rack:
    """Add rack won by player (new simplified UX)."""
    # Similar to IndividualMatchService.add_rack_for_player

@transactional(domain="match")
def remove_rack_for_player(match_id: int, user_id: int, player_id: int) -> None:
    """Remove last rack for player (new simplified UX)."""
    # Similar to IndividualMatchService.remove_rack_for_player

@transactional(domain="match")
def confirm_match_result(match_id: int, user_id: int) -> Match:
    """Confirm match result."""
    # Uses BaseMatchMixin.confirm_result()

@transactional(domain="match")
def reject_match_result(match_id: int, user_id: int) -> Match:
    """Reject match result."""
    # Uses BaseMatchMixin.reject_result()
```

### 3. Creare Route per Match
In `routes/gare.py` o file dedicato:
```python
@gare_bp.route("/matches/<int:match_id>/racks/add", methods=["POST"])
@RoleRequirement.player_or_director_required
def add_rack(match_id):
    """Add rack for player."""

@gare_bp.route("/matches/<int:match_id>/racks/remove", methods=["POST"])
@RoleRequirement.player_or_director_required
def remove_rack(match_id):
    """Remove last rack for player."""

@gare_bp.route("/matches/<int:match_id>/confirm", methods=["POST"])
@RoleRequirement.player_or_director_required
def confirm_result(match_id):
    """Confirm match result."""

@gare_bp.route("/matches/<int:match_id>/reject", methods=["POST"])
@RoleRequirement.player_or_director_required
def reject_result(match_id):
    """Reject match result."""
```

### 4. Aggiornare Template Match
Cercare il template usato per visualizzare i match di gara e aggiornar lo stesso modo di `templates/individual_match/match_detail.html`:
- Pulsanti +/- per ogni giocatore
- Sezione validazione quando ready
- Storico rack attivi
- Log rack rimossi

### 5. Correggere Errori Flake8
Eseguire e correggere:
```bash
flake8 models/match/models.py models/match/base_match.py models/individual_match/models.py
```

### 6. Documentazione Finale
Creare `docs/BASE_MATCH_ARCHITECTURE.md` con:
- Decisione di usare Mixin vs Abstract Class
- Diagramma UML delle relazioni
- Pattern Template Method per `_remove_last_rack()`
- Esempi d'uso per entrambi i tipi di match

## 🏗️ Architettura Finale

```
BaseMatchMixin (mixin class)
    ├── Match (db.Model, TimestampMixin, BaseMatchMixin)
    │   └── _remove_last_rack() → usa Rack
    └── IndividualMatch (BaseModel, TimestampMixin, BaseMatchMixin)
        └── _remove_last_rack() → usa IndividualRack
```

## 🔧 Comandi Utili

```bash
# Test TDD
PYTHONPATH=. pytest tests/new/unit/test_base_match_tdd.py -v -n auto

# Format code
black models/match/models.py models/match/base_match.py models/individual_match/models.py

# Type check
pyright models/match/models.py models/match/base_match.py models/individual_match/models.py

# Flake8
flake8 models/match/models.py models/match/base_match.py models/individual_match/models.py
```

## 📊 Metriche

- **Files modificati**: 6
  - `models/match/base_match.py` (NEW - 173 lines)
  - `models/match/models.py` (MODIFIED - +30 lines)
  - `models/individual_match/models.py` (MODIFIED - -60 lines, refactored)
  - `tests/new/unit/test_base_match_tdd.py` (NEW - 250 lines)
  - 2 migration scripts (EXECUTED)

- **Test coverage**: 10 test cases per BaseMatchMixin
- **Type safety**: 0 pyright errors (mantenuto)
- **Code quality**: Formattato con black

## ⚠️ Note Importanti

1. **Metaclass Conflict Risolto**: Inizialmente usato `ABC` (abstract base class) che causava conflitto con SQLAlchemy's metaclass. Risolto usando mixin pattern.

2. **Template Method Pattern**: `_remove_last_rack()` è un template method che deve essere implementato dalle sottoclassi perché Match usa `Rack` mentre IndividualMatch usa `IndividualRack`.

3. **Backward Compatibility**: Metodi legacy mantenuti in `IndividualMatchService` per compatibilità.

4. **Migration Status**: Entrambe le migrazioni database eseguite con successo.

## 📝 Prossimi Sviluppatori

Quando riprenderai il lavoro:
1. Correggi il fixture del test (GaraStatus.INSCRIPTION)
2. Esegui i test TDD fino a farli passare tutti
3. Implementa i servizi per Match seguendo il pattern di IndividualMatch
4. Crea le route
5. Aggiorna il template
6. Documenta le scelte architetturali

Il grosso del lavoro di refactoring è fatto. Manca "solo" applicare la nuova UX ai match di gara.
