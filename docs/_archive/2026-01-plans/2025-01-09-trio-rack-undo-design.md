# Design: Trio Rack Undo Feature

**Data**: 2025-01-09
**Stato**: Approvato

## Problema

L'interfaccia trio non permette di annullare un rack inserito per errore. Nel match normale esiste il pulsante "-" per rimuovere rack, ma nel trio manca perché non c'è tracciamento dei singoli rack.

## Requisito

Tutte le azioni devono essere undoable. Questo è un principio fondamentale dell'applicazione.

## Soluzione

### 1. Nuovo Model: `TrioRack`

Seguendo il pattern OO esistente di `Rack` per i match normali:

```python
class TrioRack(db.Model):
    __tablename__ = "trio_rack"

    id = db.Column(db.Integer, primary_key=True)
    trio_match_id = db.Column(db.Integer, db.ForeignKey("trio_match.id", ondelete="CASCADE"), nullable=False)
    rack_number = db.Column(db.Integer, nullable=False)

    # Chi ha vinto questo rack
    winner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Matchup al momento del rack (audit)
    player1_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    player2_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    waiting_player_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    # Audit trail
    added_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Soft delete per undo
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    removed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    removed_at = db.Column(db.DateTime, nullable=True)
```

### 2. Modifiche a `TrioMatch`

I contatori diventano **computed properties** basate sui `TrioRack` attivi:

```python
@property
def active_racks(self):
    return [r for r in self.racks if not r.is_deleted]

@property
def total_racks_played(self) -> int:
    return len(self.active_racks)

@property
def player1_racks(self) -> int:
    return sum(1 for r in self.active_racks if r.winner_id == self.player1_id)

# Analogamente per player2_racks, player3_racks
```

Campi da rimuovere (diventano computed):
- `player1_racks`, `player2_racks`, `player3_racks`
- `total_racks_played`, `current_rack_in_round`, `current_round`

Campi da mantenere:
- `is_completed`, `winner_id`, `bonus_applied` (stato finale)
- `current_player1_id`, `current_player2_id`, `waiting_player_id` (UI state)

### 3. Metodi Modificati

**`add_rack_win()`**: Crea `TrioRack` invece di incrementare contatori.

**`remove_last_rack()`** (nuovo): Soft-delete dell'ultimo rack attivo.

### 4. UI

Due colonne (i 2 giocatori correnti), ognuna con + e -:
- Il **+** è sempre abilitato (se non completato e tavolo assegnato)
- Il **-** è abilitato **solo per chi ha vinto l'ultimo rack**
- Entrambi i "-" chiamano `removeTrioLastRack()` (stessa funzione)

### 5. Endpoint

- Player: `POST /player/match/<id>/trio/remove_rack`
- Admin: `POST /admin/gara/trio/<id>/remove_rack`

### 6. Migrazione DB

- Crea tabella `trio_rack`
- Rimuovi colonne obsolete da `trio_match`

## File da Modificare

| File | Modifica |
|------|----------|
| `models/match/models.py` | Aggiungere `TrioRack`, modificare `TrioMatch` |
| `models/competition/services.py` | Aggiungere `remove_trio_rack()` |
| `routes/player/matches.py` | Aggiungere endpoint |
| `routes/admin/gara.py` | Aggiungere endpoint |
| `templates/components/_trio_rack_input.html` | Aggiungere pulsanti - |
| `templates/match_detail.html` | Aggiungere JS `removeTrioLastRack()` |
| `migrations/` | Nuova migrazione |

## Note Implementative

- Il bonus rack usa solo il flag `bonus_applied`, non crea rack virtuali
- Soft delete permette audit trail completo
- La sequenza round-robin è fissa, quindi si può rimuovere solo l'ultimo rack
