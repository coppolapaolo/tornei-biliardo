# Individual Match Domain

## Purpose

Player-to-player casual match organization system outside formal tournaments.

**Key Features:**
- Match Proposals: Direct invitations or open community requests
- Player Availability: venue-based player discovery (`UserLocationAvailability`, ADR-033)
- Multi-Set Support: Single-set and multi-set configurations
- Match History: Track casual game statistics
- Bilateral Confirmation: `CONFIRMED_BY_BOTH` status (value "validated") after both players confirm result
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
from models.status_enum import Discipline

# Create direct proposal (invite specific players)
proposal = IndividualMatchService.create_direct_proposal(
    proposer_id=user.id,
    invited_user_ids=[player1.id, player2.id],
    location="Sala Biliardo",
    scheduled_at=datetime(2025, 10, 15, 19, 0),
    discipline=Discipline.EIGHT_BALL.value,
    distance=7,
    is_race_to=True
)

# Create open proposal (community-wide, notifies eligible players)
proposal = IndividualMatchService.create_open_proposal(
    proposer_id=user.id,
    location="Sala Biliardo",
    scheduled_at=datetime(2025, 10, 15, 19, 0),
    discipline=Discipline.NINE_BALL.value,
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
                                    CONFIRMED_BY_BOTH
```

**In attesa di conferma (2026-09-14)** — `pending_confirmation.py`:
- `match.awaiting_confirmation_from_id` / `awaiting_confirmation_since`: una
  firma c'è, l'altra manca (a distanza raggiunta chi vince firma d'ufficio).
  Senza nessuna firma la partita non aspetta nessuno.
- **Giocata, non in corso** (2026-10-18): `is_played_awaiting_confirmation`
  (anche la partita di un terzo dichiarata) / `is_being_played`. Esce
  **subito** dalle sfide in corso della dashboard e da «Stai già giocando»;
  stato «In attesa di conferma» (`status_text`, `st.pastiglia`), fra le
  giocate di «Le mie sfide» per chi aspetta. `DASHBOARD_GRACE` (24 h) non lo
  chiede più nessuno.
- `PendingConfirmationService.ensure_none_pending(user_id)` blocca proposte
  (dirette e aperte), accettazioni e avvio rapido di chi deve firmare
  (`PendingConfirmationError`, un `ConflictError`). Le route rispondono con
  `routes/individual_match/pending.py::pending_confirmation_response`: redirect
  alla pagina `individual_match.pending_confirmations` con `next`, o 409 in JSON.

**Key Points:**
- Match does NOT auto-complete when distance is reached
- `is_ready_for_validation()` returns True when score reaches distance
- Both players must call `confirm_result()` to finalize
- After bilateral confirmation, status becomes `CONFIRMED_BY_BOTH` (value "validated")
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
- `score_can_change` / `ensure_score_can_change()` - il punteggio si tocca
  solo a sfida in corso, o registrata da uno contro un non registrato ancora
  da riscattare; conclusa → `ConflictError` (2026-10-18). Lo chiedono
  segnapunti, referto TPA e `match_scoring_state` (`board.can_undo`)
- `reset_confirmations()` - azzera le firme **e ritira** gli avvisi
  `MATCH_RESULT_TO_CONFIRM` ancora da leggere (`ritira_gli_avvisi_in_sospeso`
  con `tipi=`): ogni strada che azzera passa di qui

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
- `withdraw_match(match_id, user_id)` - Ritira una sfida firmata solo da `user_id` (2026-10-17): `CANCELLED`, avviso all'avversario; l'avversario non può, dopo la doppia firma nessuno
- `send_match_reminders(hours_before, window_minutes)` - Send reminder notifications

### ScoredMatchService (ADR-084)
La partita di **altri due**, tenuta da un istruttore o da un direttore (mai
l'admin, dal 2026-10-18). `scorer_id` presente = partita di un terzo.

- `can_score(user)` - istruttore o direttore; l'admin no, nemmeno col ruolo di
  istruttore
- `start(scorer, player1_id, player2_id, config)` - nasce in corso col referto
  già aperto (compilatore lo scorer). I giocatori li sceglie `_giocatore`, il
  punto da estendere per i giocatori non registrati
- nessuna firma d'ufficio; chiudere il referto la **dichiara**
  (`is_declared_by_scorer`) e avvisa entrambi
- ogni giocatore `confirm_as_player` per sé, una volta;
  `awaits_decision_from(user_id)` è la domanda unica «tocca a lui?» per i due
  tipi di sfida. `awaiting_confirmation_from_id` resta `None`: non blocca
  nessuno e non si ritira
- `reject_as_player`: **un rifiuto basta** (2026-10-18) → `MatchStatus.REJECTED`
  per tutti e due, nessun livello né ELO, e `is_hidden_from(user_id)` la
  nasconde ai giocatori (`get_user_matches`, `match_detail`, `can_read` del
  referto). Avvisa l'altro e lo scorer, e fa scadere gli avvisi in sospeso
- lo scorer sulla rifiutata: `ScoredMatchService.reopen` →
  `reopen_by_scorer` (referto riaperto, decisioni azzerate; alla nuova
  chiusura la richiesta di conferma riparte) oppure `cancel_by_scorer`
- `cancel_by_scorer` finché nessuno ha confermato, o sempre se rifiutata
- livello per giocatore: `livello_di_sfida_per`, `sfide_della_vista(vista,
  user_id=…)` — le query sulle sfide di un giocatore passano **sempre** la
  persona

### QuickMatchService (ADR-051)
Avvio rapido: la partita fra due giocatori **già in sala**, senza proposta e
senza accettazione.

- `get_defaults(user_id)` - quando/dove/come precompilati: ultima partita
  giocata → sala in cui risulta disponibile (`UserLocationAvailability`) →
  default di sistema
- `find_open_match(user_id, opponent_id)` - la partita che i due stanno già
  giocando (guardia sul doppio avvio), **purché `user_id` non l'abbia già
  firmata**: chi ha firmato ha chiuso la sua parte e può aprirne un'altra con
  lo stesso avversario, anche se quello non firma mai (UC2 di
  `docs/usecases/sfide-e-certificazione.md`)
- `start(user_id, opponent_id, config=None)` - crea la partita **già
  `IN_PROGRESS`**; le chiavi assenti in `config` vengono dai default. Se una
  partita fra i due è in corso e `user_id` non l'ha firmata, restituisce quella.
  `opponent_id` può essere un `NuovoGiocatore` (nome e cognome): nasce lì un
  non registrato (ADR-085, emendamento 2026-10-18)
- `can_be_opponent(user)` - chi ha sbloccato le sfide **o** è non registrato;
  `can_create_opponent(user)` - direttori e istruttori, mai l'admin
- l'avversario non registrato non firma: `IndividualMatch.firma_d_ufficio`
  passa la firma alla distanza a chi ha aperto la sfida, e
  `IndividualMatch.confirm_result` (ridefinito) **chiude** la sfida alla
  prima firma contro un non registrato (`record_alone`, regola del
  2026-10-18 sera): `CLOSED_UNILATERALLY` + `recorded_by_id` =
  *registrata da uno* (`is_recorded_by_one`), livello *In attesa*, solo
  `ELO_ALL`. Il forfait sta nello stesso stato ma senza `recorded_by_id`.
  Un punteggio che cambia la riapre (`reset_confirmations` ridefinito); chi
  l'ha registrata la ritira (`can_withdraw`)

### RevisioneService (`revisione.py`, ADR-086 emendamento 2026-10-18)
Dopo il riscatto, chi l'ha riscattato rivede le partite registrate contro il
non registrato. `ClaimService.approve` manda **un** invito (`/match/revisione`).

- `da_rivedere(user_id, richiesta_id=None)` - sfide `awaits_review_from(user_id)`
  e partite di altri due che aspettano la sua decisione **e** che erano del
  non registrato: `ClaimService.approve` le annota prima dell'unione in
  `ClaimRequestMatch` (`riscattate`). Senza traccia (riscatti prima del
  2026-10-18 notte) solo le registrate da uno; mai le partite di gara
- `rivedi(user_id, rivedute, contestate)` - i tre esiti in una chiamata.
  Sfida normale: `recognize_by` (→ `CONFIRMED_BY_BOTH` + evento ELO globale)
  o `contest_by` (`contested_at`: resta al registrante, *In attesa*, sparisce
  per chi contesta via `is_hidden_from` / `non_contestate_da`). Partita di un
  terzo: `confirm_as_player` / `reject_as_player`
- facoltativa, senza scadenza, non blocca niente

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
| Prima firma del risultato | MATCH_RESULT_TO_CONFIRM | Chi deve ancora firmare (una sola finché non la legge; **scade** quando le firme si azzerano, 2026-10-18) |
| Sfida ritirata da chi l'aveva firmata | MATCH_CANCELLED | Avversario |
| Partita di altri due creata | MATCH_ACCEPTED | I due giocatori, con la descrizione |
| Referto della partita di altri due chiuso | MATCH_RESULT_TO_CONFIRM | Ciascuno dei due che non ha ancora deciso |
| Partita di altri due annullata da chi segna | MATCH_CANCELLED | I due giocatori |
| Partita di altri due rifiutata | MATCH_CANCELLED | L'altro giocatore e chi l'ha segnata |
| Riscatto approvato con partite da rivedere | MATCH_RESULT_TO_CONFIRM | Chi ha riscattato (uno solo, link `/match/revisione`) |
| Sfida registrata da uno contestata | MATCH_CANCELLED | Chi l'ha registrata |

---

## Scheduled Tasks

```bash
# Match reminders (run hourly: gli scheduled task di PythonAnywhere non
# scendono sotto l'ora, e la finestra di ricerca è allineata a quella cadenza)
venv/bin/python scripts/send_match_reminders.py

# Proposal expiration: ProposalService.expire_old_proposals(), called by scripts/daily_jobs.py
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
