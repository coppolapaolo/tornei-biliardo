# Competition Domain

## Purpose

Manages individual competition rounds (Gara) within tournaments or as standalone events.

**Core Responsibilities:**
- Gara lifecycle management (setup → inscription → playing → completed)
- Player inscription and waitlist management
- Round creation and progression
- Advanced round management with locking mechanisms

**Related Domains:** [matchmaking/](../matchmaking/) for pairing, [match/](../match/) for scoring, [campionato/](../campionato/) for multi-gara tournaments.

---

## Quick Reference

```python
from models.competition.models import Gara, Inscription
from models.competition.services import GaraService
from models.competition.inscription_service import InscriptionService
from models.competition.round_service import RoundService
from models.competition.state_service import StateService
from models.competition.round_manager import AdvancedRoundManager
from models.status_enum import GaraStatus

# Create gara
gara = GaraService.create_gara(
    number=1, name="Prova 1", date=date(2025, 10, 15),
    discipline="palla_8", distance=5,
    campionato_id=campionato.id,  # or None + director_id for standalone
    time=time(18, 0), rounds_count=3, min_participants=6
)

# Open inscriptions
gara = InscriptionService.open_inscriptions(
    gara_id=gara.id,
    inscription_start=datetime.now(),
    inscription_end=datetime.now() + timedelta(days=7)
)

# Inscribe player (auto-waitlist if full)
inscription = InscriptionService.inscribe_user(user_id=user.id, gara_id=gara.id)

# Start first round
gara = RoundService.start_first_round(gara_id=gara.id)

# Create next round
counts = RoundService.create_round_with_strategy(gara_id=gara.id, round_number=2)
# Returns: (total, normal, bye, trio)

# Check round lock status
from models.competition.round_manager import RoundLockStatus
lock = AdvancedRoundManager.get_round_lock_status(gara.id, round_number=2)
if lock == RoundLockStatus.LOCKED:
    # Cannot modify - subsequent round exists
```

---

## Key Models

### Gara
**Key Fields:** `campionato_id` (nullable for standalone), `director_id`, `status`, `date`, `time`, `discipline`, `distance`, `best_of`, `rounds_count`, `current_round`, `min_participants`, `max_participants`, `matchmaking_strategy`, `withdraw_policy`

**Status Values:** `setup`, `inscription`, `playing`, `completed`

**Key Methods:**
- `get_real_status()` - Actual status (considers round completion, inscription expiry)
- `can_start_new_round()` - All current matches completed?
- `can_inscribe()` - In inscription period?
- `is_full()` / `has_waitlist()` - Capacity checks
- `validate_strategy_configuration()` - Validate matchmaking config

### Inscription
**Key Fields:** `user_id`, `gara_id`, `is_withdrawn`, `is_forfeit`, `is_waitlist`, `waitlist_position`, `initial_order`

---

## Services

### GaraService (Facade)
- `create_gara(...)`, `update_gara(...)`, `delete_gara(...)`
- `soft_delete_gara(gara_id, cascade_option)` - "delete_all" or "keep_matches"
- `add_director(...)`, `remove_director(...)`

### InscriptionService
- `inscribe_user(...)` - Auto-waitlist if full
- `uninscribe_user(...)` - Promotes first waitlist
- `admin_uninscribe_user(...)` - With notification
- `open_inscriptions(...)`, `modify_inscription_dates(...)`

### RoundService
- `start_first_round(...)` - Shuffles inscriptions, creates first round
- `create_round_with_strategy(...)` - Idempotent, locks previous round
- `cancel_first_round_startup(...)` - Return to inscription state

### StateService
- `to_inscription(gara)` - setup → inscription
- `reopen_setup(gara)` - inscription → setup
- `start_playing(gara)` - inscription → playing
- `complete(gara)` - playing → completed

### AdvancedRoundManager
- `get_round_lock_status(gara_id, round_number)` - LOCKED/UNLOCKED
- `can_modify_match(match_id)` - Returns (bool, reason)
- `reset_match_with_validation(match_id)` - Respects locking
- `cancel_round(gara_id, round_number)` - Delete round matches

---

## Do Not

- **Do not use `status` directly for UI** - Use `get_real_status()` which considers round completion
- **Do not forget director requirement** - Standalone gara needs `director_id`, campionato gara inherits directors
- **Do not assume idempotency fails** - `create_round_with_strategy()` returns counts if round exists
- **Do not call `db.session.commit()`** - All services use `@transactional`
- **Do not hard-delete inscriptions** - Use soft delete/withdraw mechanisms
- **Do not modify locked rounds** - Check `get_round_lock_status()` first
- **Do not confuse Random strategy** - Creates ALL rounds at startup, others create one at a time
- **Do not create gare with non-sequential dates** - Gara N must have date/time >= gara N-1 (ADR-016)

---

## State Machine

```
setup ──→ inscription ──→ playing ──→ completed
         ↑           ↓
         └───────────┘
```

---

## Match Lifecycle Operations

Definizioni canoniche delle operazioni che agiscono sui `Match` di una gara.
Razionale completo in [ADR-026](../../docs/adr/ADR-026-reset-match-preserves-pair-semantics.md)
(sezione "Operations Glossary").

**Regola generale:** `reset` corregge, `cancel_round` annulla. Sono operazioni
semanticamente distinte — confonderle è stata la causa di ADR-002 parzialmente
sbagliato (vedi "Previous Assumption Debunked" in ADR-026).

### `RackService.reset_match_complete(match_id)` — score correction

- **Intent del director**: "Ho sbagliato a inserire lo score, lo correggo
  rigiocando gli stessi rack con gli stessi giocatori."
- **Match preservato** (stesso id/round/pair), rack eliminati, scores azzerati,
  status → PLAYING/PENDING (in base al `table_assignment`)
- **`PlayerEncounter` PRESERVATO** — il pair resta "incontrato" per l'anti-rematch
- Per trio match delega a `TrioScoringService.reset` (azzera trio rack e stato)
- Bloccato per match bye; bloccato da `RoundLockStatus.LOCKED` quando passato
  attraverso `AdvancedRoundManager.reset_match_with_validation`
- **Bloccato se la gara ha un `Tiebreaker` attivo** (stato != `CANCELLED`):
  lo spareggio certifica implicitamente i risultati della gara. Il director
  deve prima annullare lo spareggio (o attendere che ne venga creato uno
  nuovo) per riabilitare il reset. Vedi spec
  `_bmad-output/implementation-artifacts/spec-reset-blocked-by-tiebreaker.md`.

### `AdvancedRoundManager.bulk_reset_round_matches(gara_id, round_number)` — mass reset

- **Intent del director**: "Voglio resettare tutti i match di un turno,
  tipicamente per poi annullarlo (`cancel_round` richiede match senza risultati)."
- Delega a `reset_match_with_validation` per ciascun match completato del round
- Ogni singolo reset segue la semantica di `reset_match_complete` (pair preservato)
- Errori per-match raccolti (savepoint rollback), continua sui rimanenti
- Aggiorna la progressione del round dopo il reset massivo

### `AdvancedRoundManager.cancel_round(gara_id, round_number)` — round cancellation

- **Intent del director**: "Voglio annullare l'intero turno. I pair potranno
  essere ri-generati diversamente al prossimo avvio."
- **Precondizione**: nessun match del round può avere risultati parziali
  (usare `bulk_reset_round_matches` prima se necessario). **I match bye
  (`is_bye=True`) sono esclusi dal check**: il loro `player1_score =
  round_distance` è convenzione di persistenza per la classification
  machinery, non risultato utente. Semanticamente il bye è "sempre in
  stato iniziale". Walkover (`is_bye=False` + forfeit → `score > 0`)
  invece bloccano — rappresentano azioni umane e vanno resettati.
  Spec: `spec-cancel-round-ignores-bye.md`.
- **Bloccato se la gara ha un `Tiebreaker` attivo** (stato != `CANCELLED`) —
  stessa semantica del reset (vedi sopra).
- Solo round corrente o successivi sono cancellabili
- **`Match` eliminati**, `Rack` eliminati, `RoundClassification` eliminate.
  `TrioMatch` associati cascano via `cascade="all, delete-orphan"` sulla
  backref `Match.trio_match`.
- **`PlayerEncounter` del round ELIMINATI** via `delete_round_encounters` —
  pair liberati per ri-generazione diversa
- `gara.current_round` decrementato (torna a INSCRIPTION se era il primo round)

### Tabella riassuntiva

| Operazione | `Match` | `Rack` | `PlayerEncounter` | Pair semantics |
|---|---|---|---|---|
| `reset_match_complete` | preservato | eliminato | **preservato** | stessi due rigiocano |
| `bulk_reset_round_matches` | preservati (tutti) | eliminati (tutti) | **preservati** (tutti) | stessi pair del round rigiocano |
| `cancel_round` | **eliminati** | eliminati | **eliminati** | pair liberati, ri-generabili |

---

## Cross-References

- **Matchmaking**: [../matchmaking/](../matchmaking/) - Pairing strategies (Amalfi, Round-Robin, Elimination)
- **Match Execution**: [../match/](../match/) - Match and scoring
- **Classification**: [../classification/](../classification/) - Rankings
