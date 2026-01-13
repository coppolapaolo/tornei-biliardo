# Individual Match Domain

## Purpose

Player-to-player casual match organization system outside formal tournaments.

**Key Features:**
- Match Proposals: Direct invitations or open community requests
- Player Availability: Location-based player discovery
- Multi-Set Support: Single-set and multi-set configurations
- Match History: Track casual game statistics

**Distinct from Competition/Match domains** - these are standalone casual games, not tournament matches.

---

## Quick Reference

```python
from models.individual_match.models import (
    MatchProposal, ProposalInvitation, IndividualMatch, IndividualRack,
    PlayerAvailability, ProposalType, ProposalStatus, InvitationStatus,
)
from models.individual_match.services import IndividualMatchService
from models.individual_match.availability_service import AvailabilityService

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

# Create open proposal (community-wide)
proposal = IndividualMatchService.create_open_proposal(
    proposer_id=user.id,
    location="Sala Biliardo",
    scheduled_at=datetime(2025, 10, 15, 19, 0),
    discipline="palla_9",
    distance=9
)

# Accept proposal
match = IndividualMatchService.accept_proposal(user_id=invitee.id, proposal_id=proposal.id)

# Set venue availability
AvailabilityService.set_venue_availability(
    user_id=user.id,
    billiard_hall_id=venue.id,
    is_available=True,
    available_days=[1, 2, 3, 4, 5],
    preferred_times="18:00-22:00"
)
```

---

## Key Models

### MatchProposal
Match invitation (direct to specific players or open to community).

**Key Fields:** `proposer_id`, `proposal_type` (DIRECT|OPEN), `status`, `location`, `scheduled_at`, `expires_at`, `discipline`, `distance`, `best_of`, `is_multi_set`, `match_distance`

**Key Methods:**
- `can_be_accepted_by(user_id)` - Check if user can accept
- `accept(user_id)` - Accept and create IndividualMatch
- `cancel()` / `expire()` - Update status and invitations

### ProposalInvitation
Individual invitation within a direct proposal.

**Key Fields:** `proposal_id`, `invited_user_id`, `status` (PENDING|ACCEPTED|REJECTED|EXPIRED|CANCELLED)

### IndividualMatch
Actual match created when proposal is accepted.

**Key Fields:** `player1_id`, `player2_id`, `location`, `scheduled_at`, `status`, `discipline`, `distance`, `player1_score`, `player2_score`, `winner_id`

**Key Methods:**
- `start_match()` - Set status=IN_PROGRESS
- `add_rack_result(winner_id)` - Add rack, auto-complete if won
- `complete_match(winner_id)` - Set winner and status=COMPLETED

### IndividualRack
Single rack result within a match.

**Key Fields:** `match_id`, `rack_number`, `winner_id`, `break_player_id`

---

## Services

### IndividualMatchService
- `create_direct_proposal(...)` - Invite specific players, sends notifications
- `create_open_proposal(...)` - Open to all eligible players
- `get_user_proposals(user_id)` - Returns `{created, received, available}`
- `accept_proposal(user_id, proposal_id)` - Accept and create match
- `start_match(match_id, user_id)` - Start playing
- `submit_rack_result(...)` - Record rack winner
- `get_user_statistics(user_id)` - Match/rack statistics

### AvailabilityService
- `set_venue_availability(...)` - Set player availability at venue
- `get_available_players_at_venue(...)` - Find opponents
- `notify_players_of_availability(...)` - Broadcast availability

---

## Do Not

- **Do not confuse with tournament matches** - IndividualMatch has no `gara_id`, uses proposal system not matchmaking strategies
- **Do not use legacy `PlayerAvailability`** - Prefer venue-based `UserLocationAvailability` via `set_venue_availability()`
- **Do not interpret scores without checking `is_multi_set`** - Scores are racks (single-set) or sets (multi-set)
- **Do not call `db.session.commit()`** - All service methods use `@transactional`
- **Do not forget expiration** - Run `MatchProposalService.expire_proposals()` periodically

---

## Cross-References

- **Notification Domain**: `NotificationFactory` for invitation notifications
- **Location Domain**: `BilliardHall`, `UserLocationAvailability`
- **Match Domain**: `Distance`, `RackScore` value objects
