# Match Start/End Times Design

**Data:** 2026-01-23
**Stato:** Approvato

## Obiettivo

Aggiungere campi `started_at` e `ended_at` ai match per tracciare la durata effettiva delle partite a fini statistici.

## Requisiti

### Funzionali
1. **Auto-popolamento**:
   - `started_at`: quando il match passa a stato "playing"
   - `ended_at`: quando il match passa a stato "completed"
   - Se già impostato manualmente, il valore viene preservato

2. **Editabilità**:
   - **Match tornei**: Admin e Director possono modificare
   - **Match individuali**: Proposer e Admin possono modificare

3. **UI**:
   - Tutti vedono gli orari (read-only)
   - Chi può editare vede input di tipo `time` (solo ora, non data)
   - Hint visivo "(giorno +1)" quando l'orario implica il giorno successivo

4. **Quick Result**: campi time precompilati
   - `start_time`: precompilato con `match.started_at` se esiste
   - `end_time`: precompilato con ora corrente

### Logica Inferenza Giorno

Poiché l'UI mostra solo l'ora (non la data), il sistema inferisce il giorno:

**Per `started_at`:**
- Base = `gara.date`
- Se `start_time < gara.time` → giorno successivo
- Es: gara alle 20:00, match inizia alle 00:15 → `gara.date + 1`

**Per `ended_at`:**
- Base = `started_at.date()` (o `gara.date` se started_at non esiste)
- Se `end_time <= start_time` → giorno successivo rispetto a started_at

## Modifiche

### 1. Database Schema

**Migration: `add_match_times.py`**

```python
# Match (tornei) - nuovi campi
op.add_column('match', sa.Column('started_at', sa.DateTime(), nullable=True))
op.add_column('match', sa.Column('ended_at', sa.DateTime(), nullable=True))

# IndividualMatch - rename per consistenza
op.alter_column('individual_match', 'completed_at', new_column_name='ended_at')
```

### 2. Models

**`models/match/models.py`**
```python
class Match(db.Model, ...):
    started_at = db.Column(db.DateTime, nullable=True)
    ended_at = db.Column(db.DateTime, nullable=True)
```

**`models/individual_match/models.py`**
```python
class IndividualMatch(...):
    # Rename: completed_at → ended_at
    ended_at = db.Column(db.DateTime, nullable=True)
```

### 3. Services

**`models/match/state_service.py`**
```python
def to_playing(match_id: int) -> Match:
    match.status = MatchStatus.PLAYING.value
    if match.started_at is None:
        match.started_at = datetime.utcnow()

def to_completed(match_id: int) -> Match:
    match.status = MatchStatus.COMPLETED.value
    if match.ended_at is None:
        match.ended_at = datetime.utcnow()
```

**`models/match/services.py`** - Nuovo metodo
```python
@transactional
def update_times(match_id: int, start_time_str: str, end_time_str: str) -> Match:
    # Logica inferenza giorno (vedi sopra)
```

### 4. Routes

**`routes/admin/match.py`**
```python
@bp.route("/match/<int:match_id>/times", methods=["POST"])
@match_manager_required
def update_match_times(match_id):
    # Per admin/director
```

**`routes/individual_match.py`**
```python
@bp.route("/match/<int:match_id>/times", methods=["POST"])
@login_required
def update_individual_match_times(match_id):
    # Per proposer/admin
```

### 5. Templates

| Template | Modifica |
|----------|----------|
| `_match_info.html` | +visualizzazione orari (read-only) |
| `_match_rack_input.html` | +sezione edit orari (se `user_can_manage`) |
| `_match_admin_controls.html` | +sezione edit orari |
| `gara_detail.html` | +campi time in Quick Result modal |
| `individual_match/match_detail.html` | +orari view/edit |

### 6. Filtri Template

Nuovo filtro `time_local` per formattare orari:
```python
@app.template_filter('time_local')
def time_local_filter(dt):
    if dt is None:
        return ''
    return dt.strftime('%H:%M')
```

## UI Mockups

### Match Info (sidebar) - Read Only
```
┌─────────────────────────────┐
│ Info Partita                │
│ ...                         │
│ Inizio: 21:35               │
│ Fine: 22:48                 │
└─────────────────────────────┘
```

### Director/Admin Edit (in _match_rack_input o _match_admin_controls)
```
┌─────────────────────────────────────┐
│ ⏱️ Orari partita                    │
│ Inizio: [21:35]   Fine: [22:48]     │
│          [Salva orari]              │
└─────────────────────────────────────┘
```

### Quick Result Modal
```
┌─────────────────────────────────────┐
│ Imposta Risultato Rapido            │
│                                     │
│ Mario: [3]        Luigi: [5]        │
│                                     │
│ ⏱️ Orari (opzionale)                │
│ Inizio: [21:35]   Fine: [22:48]     │
│                                     │
│        [Annulla] [Imposta]          │
└─────────────────────────────────────┘
```

## Test Plan

1. **Unit tests**:
   - Logica inferenza giorno
   - Auto-popolamento in state transitions
   - Permessi update (admin, director, proposer)

2. **Integration tests**:
   - Workflow completo match torneo con times
   - Workflow completo match individuale con times
   - Quick Result con times

## File Coinvolti

- `models/match/models.py`
- `models/match/state_service.py`
- `models/match/services.py`
- `models/individual_match/models.py`
- `models/individual_match/match_lifecycle_service.py`
- `routes/admin/match.py`
- `routes/individual_match.py`
- `templates/components/_match_info.html`
- `templates/components/_match_rack_input.html`
- `templates/components/_match_admin_controls.html`
- `templates/gara_detail.html`
- `templates/individual_match/match_detail.html`
- `migrations/versions/xxx_add_match_times.py`
