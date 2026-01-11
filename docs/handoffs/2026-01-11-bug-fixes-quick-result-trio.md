# Handoff: Bug Fixes - Quick Result e Trio + Refactoring TrioScoringService

**Data**: 2026-01-11
**Stato**: Completato (bug fix + refactoring architetturale)
**Test**: 669 pass, pyright 0 errors

## Sommario

Corretti 3 bug trovati durante test manuali della web app, poi eseguito refactoring architetturale:

| Attività | Descrizione | Stato |
|----------|-------------|-------|
| Bug 1 | Quick Result 5-2 non completa match (solo 5-0 funzionava) | ✅ Corretto |
| Bug 2 | "Rimuovi tavolo" su Trio mostra errore sbagliato | ✅ Corretto |
| Bug 3 | Trio Quick Result 5-0-0 fallisce silenziosamente | ✅ Corretto |
| Refactoring | Creato `TrioScoringService` (uniformità architetturale) | ✅ Completato |

## Bug 1: Quick Result 5-2 non completa match

### Root Cause
Gara 6 aveva `is_race_to=False` (modalità "Esatto Numero"), non "Al N" (race-to).

In modalità "Esatto Numero":
- Il totale rack giocati deve essere ESATTAMENTE uguale a `distance`
- 5-0 (totale 5) = valido per distance=5
- 5-2 (totale 7) = invalido per distance=5, ma NON veniva mostrato errore!

### Fix
Aggiunta validazione in `models/match/scoring_service.py` → `_validate_score_limits`:

```python
else:
    # In "exact number" mode, total racks must equal distance
    total_racks = player1_score + player2_score
    if total_racks != match.gara.distance:
        raise ValueError(
            f"In modalità 'esatto numero', il totale dei rack ({total_racks}) "
            f"deve essere esattamente {match.gara.distance}!"
        )
```

### Test di Regressione
- `tests/new/unit/test_quick_result_regression.py::TestExactModeValidation`
- `tests/new/unit/test_race_to_score_validation.py::test_exact_mode_*`

## Bug 2: Rimuovi tavolo su Trio

### Root Cause
`reset_match_complete` non gestiva i match Trio (solo Rack standard).

### Fix
`reset_match_complete` ora delega a `TrioScoringService.reset()` per match Trio.

### Test di Regressione
- `tests/new/unit/test_quick_result_regression.py::TestTrioResetOnTableRemoval`

## Bug 3: Trio Quick Result 5-0-0 fallisce silenziosamente

### Root Cause
`set_result_direct` restituiva `False` invece di sollevare eccezione.
Il chiamante ignorava il valore di ritorno.

### Fix
`set_result_direct` ora solleva `ValueError` con messaggio descrittivo.

### Test di Regressione
- `tests/new/unit/test_quick_result_regression.py::TestTrioQuickResultValidation`

## File Modificati

| File | Modifica |
|------|----------|
| `models/match/scoring_service.py` | Aggiunta validazione exact mode |
| `models/match/services.py` | Gestione Trio in reset_match_complete |
| `models/match/models.py` | `set_result_direct` solleva ValueError |
| `tests/new/unit/test_quick_result_regression.py` | Test di regressione (nuovo) |
| `tests/new/unit/test_race_to_score_validation.py` | Fix test esistente + nuovi test |

## Nota Importante per Gara 6

Se l'utente vuole che Gara 6 usi la modalità "Al 5" (race-to) invece di "Esatto 5":
1. Modificare le impostazioni della gara
2. Impostare `is_race_to=True`

Con `is_race_to=True`:
- 5-0, 5-1, 5-2, 5-3, 5-4 sono tutti risultati validi
- Il match si completa quando un giocatore raggiunge 5 rack

## Verifica

```bash
# Tutti i test passano
PYTHONPATH=. pytest tests/new/ -n auto

# Type check OK
pyright
```

---

## Refactoring Architetturale: TrioScoringService ✅ COMPLETATO

### Problema Risolto

Durante l'analisi dei bug era emersa un'inconsistenza architetturale:

| Tipo Match | Prima | Dopo |
|------------|-------|------|
| **Match Regolari** | `ScoringService` (service layer) ✓ | Invariato |
| **Trio** | `TrioMatch` model (logica nel model) ✗ | `TrioScoringService` ✓ |

### Implementazione

Creato `TrioScoringService` seguendo il pattern di `ScoringService`:

```python
# models/match/trio_scoring_service.py
class TrioScoringService:
    @staticmethod
    @transactional(domain="match")
    def add_rack_win(trio_id: int, winner_id: int, added_by_id: int = None) -> TrioRack

    @staticmethod
    @transactional(domain="match")
    def remove_last_rack(trio_id: int, removed_by_id: int) -> TrioRack

    @staticmethod
    @transactional(domain="match")
    def set_result_direct(trio_id: int, p1_racks: int, p2_racks: int, p3_racks: int) -> bool

    @staticmethod
    @transactional(domain="match")
    def reset(trio_id: int) -> None
```

### File Modificati

| File | Modifica |
|------|----------|
| `models/match/trio_scoring_service.py` | **Nuovo** - Service per scoring Trio |
| `models/match/models.py` | Rimossi metodi: `add_rack_win`, `remove_last_rack`, `set_result_direct`, `reset` |
| `models/competition/services.py` | Usa `TrioScoringService` invece di metodi model |
| `models/match/services.py` | `reset_match_complete` delega a `TrioScoringService.reset()` |
| `tests/new/unit/test_trio_completion_bug.py` | Aggiornato per usare service |
| `tests/new/unit/test_quick_result_regression.py` | Aggiornato per usare service |

### Verifica

```bash
# 25 test passano
PYTHONPATH=. pytest tests/new/unit/test_trio_*.py tests/new/unit/test_quick_result_regression.py -v

# Pyright OK
pyright  # 0 errors
```

**Stato**: ✅ Completato

---

## Bug 4: Modal Assegnazione Tavoli Non Funzionante

### Sintomi
- Cliccando su "Assegna" o "Tavolo X" il modal si apriva ma la griglia tavoli era vuota
- Console JavaScript mostrava: `SyntaxError: Unexpected end of input`

### Root Cause (Due Problemi)

**Problema 1: Route usa metodo deprecato**
```python
# routes/admin/competition/detail.py (PRIMA)
available_tables = TableAssignmentService.get_table_names(gara.location)  # ❌ DEPRECATO

# (DOPO)
available_tables = TableAssignmentService.get_table_names_for_gara(gara.id)  # ✅ CORRETTO
```

`get_table_names_for_gara()` rispetta la priorità:
1. `gara.available_tables` (se configurato)
2. Tavoli della venue
3. Lista vuota

**Problema 2: Virgolette annidate in onclick**
```html
<!-- PRIMA - virgolette doppie annidate -->
onclick="openTableAssignment(46, null, "player3 • player4 • mario", '')"
                                       ↑ ERRORE: chiude l'attributo!

<!-- DOPO - single quotes per attributo -->
onclick='openTableAssignment(46, null, "player3 \u2022 player4 \u2022 mario", "")'
```

Il filtro `|tojson` produce stringhe con virgolette doppie. Usando single quotes per l'attributo HTML si evita il conflitto.

### Fix

| File | Modifica |
|------|----------|
| `routes/admin/competition/detail.py` | Usa `get_table_names_for_gara(gara.id)` |
| `templates/components/_match_result_row.html` | Attributo onclick con single quotes |

### Lezione Appresa

**CLAUDE.md già documentava questo pattern**, ma per le stringhe tradotte:
```javascript
// ❌ WRONG
alert('{{ _("l'errore") }}');

// ✅ CORRECT
alert({{ _("l'errore")|tojson }});
```

Lo stesso principio si applica a QUALSIASI stringa Jinja2 in attributi HTML onclick:
- Usare single quotes per l'attributo onclick
- `|tojson` produce stringhe JSON valide con double quotes

**Stato**: ✅ Completato
