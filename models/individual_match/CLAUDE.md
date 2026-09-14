# Individual Match Domain

## Purpose

Player-to-player casual match organization system outside formal tournaments.

**Key Features:**
- Match Proposals: Direct invitations or open community requests
- Player Availability: venue-based player discovery (`UserLocationAvailability`, ADR-033)
- Multi-Set Support: Single-set and multi-set configurations
- Match History: Track casual game statistics
- Bilateral Confirmation: VALIDATED status after both players confirm result
- Rematch: Quick "play another" with same opponent and pre-filled settings
- Quick Start: match aperto **già in corso** per chi è in sala adesso, senza proposta né accettazione (ADR-051)
- Notifications: Proposal expiration, open proposals, match reminders

**Distinct from Competition/Match domains** - these are standalone casual games, not tournament matches.

---

## Quick Reference

```python
from models.individual_match.models import (
    MatchProposal, ProposalInvitation, IndividualMatch, IndividualRack,
    ProposalType, ProposalStatus, InvitationStatus,
)
from models.individual_match.services import IndividualMatchService
from models.individual_match.availability_service import AvailabilityService
from models.individual_match.statistics_service import IndividualMatchStatisticsService

# Create direct proposal (invite specific players)
proposal = IndividualMatchService.create_direct_proposal(
    proposer_id=user.id,
    invited_user_ids=[player1.id, player2.id],
    location="Sala Biliardo",
    scheduled_at=datetime(2025, 10, 15, 19, 0),
    discipline="palla_8",
    distance=7,
    best_of=True
)

# Create open proposal (community-wide, notifies eligible players)
proposal = IndividualMatchService.create_open_proposal(
    proposer_id=user.id,
    location="Sala Biliardo",
    scheduled_at=datetime(2025, 10, 15, 19, 0),
    discipline="palla_9",
    distance=9
)

# Accept proposal
match = IndividualMatchService.accept_proposal(user_id=invitee.id, proposal_id=proposal.id)

# Get frequent opponents for suggestions
opponents = IndividualMatchStatisticsService.get_frequent_opponents(user_id, limit=5)

# Send reminders for upcoming matches (call via scheduled task, hourly)
from models.individual_match.match_lifecycle_service import MatchLifecycleService
reminded_ids = MatchLifecycleService.send_match_reminders(hours_before=2, window_minutes=60)
```

---

## Match Lifecycle (VALIDATED Flow)

```
SCHEDULED → IN_PROGRESS → (distance reached) → is_ready_for_validation() = True
                                             ↓
                              Both players call confirm_result()
                                             ↓
                                         VALIDATED
```

**In attesa di conferma (2026-09-14)** — `pending_confirmation.py`:
- `match.awaiting_confirmation_from_id` / `awaiting_confirmation_since`: una
  firma c'è, l'altra manca (a distanza raggiunta chi vince firma d'ufficio).
  Senza nessuna firma la partita non aspetta nessuno.
- Dopo `DASHBOARD_GRACE` (24 h dalla prima firma) esce dalla dashboard di
  entrambi; resta in «Le mie sfide» con lo stato «In attesa di conferma».
- `PendingConfirmationService.ensure_none_pending(user_id)` blocca proposte
  (dirette e aperte), accettazioni e avvio rapido di chi deve firmare
  (`PendingConfirmationError`, un `ConflictError`). Le route rispondono con
  `routes/individual_match/pending.py::pending_confirmation_response`: redirect
  alla pagina `individual_match.pending_confirmations` con `next`, o 409 in JSON.

**Key Points:**
- Match does NOT auto-complete when distance is reached
- `is_ready_for_validation()` returns True when score reaches distance
- Both players must call `confirm_result()` to finalize
- After bilateral confirmation, status becomes `VALIDATED`
- Use `reject_result()` to undo last rack and reset confirmations

---

## Key Models

### MatchProposal
Match invitation (direct to specific players or open to community).

**Key Fields:** `proposer_id`, `proposal_type` (DIRECT|OPEN), `status`, `billiard_hall_id`, `location`, `scheduled_at`, `expires_at`, `discipline`, `distance`, `is_race_to`, `is_multi_set`, `match_distance`

**Key Properties:**
- `location_display` - Returns venue name (prefers FK over legacy string)

**Key Methods:**
- `can_be_accepted_by(user_id)` - Check if user can accept
- `accept(user_id)` - Accept and create IndividualMatch
- `cancel()` / `expire()` - Update status and invitations

### IndividualMatch
Actual match created when proposal is accepted.

**Key Fields:** `player1_id`, `player2_id`, `billiard_hall_id`, `location`, `scheduled_at`, `status`, `discipline`, `distance`, `player1_score`, `player2_score`, `winner_id`, `player1_confirmed`, `player2_confirmed`

**Key Properties:**
- `location_display` - Returns venue name (prefers FK over legacy string)

**Key Methods:**
- `start_match()` - Set status=IN_PROGRESS
- `add_rack_result(winner_id)` - Add rack (does NOT auto-complete)
- `is_ready_for_validation()` - True when distance reached
- `confirm_result(user_id)` - Confirm result (returns True if both confirmed)
- `reject_result(user_id)` - Undo last rack, reset confirmations

### IndividualRack
Single rack result within a match.

**Key Fields:** `match_id`, `rack_number`, `winner_id`, `break_player_id`

---

## Services

### IndividualMatchService
- `create_direct_proposal(...)` - Invite specific players, sends notifications
- `create_open_proposal(...)` - Open to all, notifies eligible players in location
- `get_user_proposals(user_id)` - Returns `{created, received, available}`
- `accept_proposal(user_id, proposal_id)` - Accept and create match

### MatchLifecycleService
- `start_match(match_id, user_id)` - Start playing
- `confirm_match_result(match_id, user_id)` - Confirm result
- `reject_match_result(match_id, user_id)` - Reject and undo last rack
- `send_match_reminders(hours_before, window_minutes)` - Send reminder notifications

### QuickMatchService (ADR-051)
Avvio rapido: la partita fra due giocatori **già in sala**, senza proposta e
senza accettazione.

- `get_defaults(user_id)` - quando/dove/come precompilati: ultima partita
  giocata → sala in cui risulta disponibile (`UserLocationAvailability`) →
  default di sistema
- `find_open_match(user_id, opponent_id)` - la partita che i due stanno già
  giocando (guardia sul doppio avvio)
- `start(user_id, opponent_id, config=None)` - crea la partita **già
  `IN_PROGRESS`**; le chiavi assenti in `config` vengono dai default. Se una
  partita fra i due è in corso, restituisce quella.

L'accettazione non è saltata: è la doppia conferma di fine partita
(`CONFIRMED_BY_BOTH`), che è anche l'unica condizione che muove l'ELO globale.
Vedi `docs/adr/ADR-051-quick-start-moves-the-acceptance-to-the-end.md`.

### IndividualMatchStatisticsService
- `get_user_statistics(user_id)` - Match/rack statistics
- `get_frequent_opponents(user_id, limit)` - Users played most matches against
- `get_user_dashboard_data(user_id)` - Comprehensive dashboard data

### ProposalService
- `expire_old_proposals()` - Expire and notify proposers
- `get_user_proposals(user_id)` - Proposals by category

---

## Notifications

| Event | Type | Recipients |
|-------|------|------------|
| Proposal expired | MATCH_DECLINED | Proposer |
| Open proposal created | MATCH_PROPOSAL | Eligible players in location |
| Match imminente (2-3 ore prima) | MATCH_REMINDER | Both players |
| Direct invitation | MATCH_PROPOSAL | Invited player |
| Proposal accepted | MATCH_ACCEPTED | Proposer |
| Avvio rapido: partita aperta con te | MATCH_ACCEPTED | Avversario |

---

## Scheduled Tasks

```bash
# Match reminders (run hourly: gli scheduled task di PythonAnywhere non
# scendono sotto l'ora, e la finestra di ricerca è allineata a quella cadenza)
python scripts/send_match_reminders.py

# Proposal expiration (run hourly)
# Called via ProposalService.expire_old_proposals()
```

---

## Do Not

- **Do not confuse with tournament matches** - IndividualMatch has no `gara_id`
- **Do not expect auto-complete** - Match requires bilateral confirmation
- **Do not use `location` directly** - Use `location_display` property
- **Do not interpret scores without checking `is_multi_set`** - Scores are racks (single-set) or sets (multi-set)
- **Do not call `db.session.commit()`** - All service methods use `@transactional`
- **Do not forget scheduled tasks** - Configure reminders and expiration

---

## Cross-References

- **Notification Domain**: `NotificationFactory` for all notifications
- **Location Domain**: `BilliardHall`, `UserLocationAvailability`
- **Match Domain**: `Distance`, `RackScore`, `BaseMatchMixin` value objects
