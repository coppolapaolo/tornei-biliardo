# Matchmaking Domain

## Purpose

Tournament pairing algorithms with unified strategy pattern.

**Core Responsibilities:**
- Player pairing generation for tournament rounds
- Strategy pattern (Amalfi, Round-Robin, Elimination, Random)
- First round policies (random, classification, rating)
- Odd number handling (byes, trio matches)
- Anti-rematch logic across rounds

---

## Quick Reference

```python
from models.matchmaking.bootstrap import get_registry
from models.matchmaking.configuration import (
    MatchmakingStrategy, FirstRoundPolicy, OddNumberPolicy
)

# Get strategy and generate pairings
registry = get_registry()
strategy = registry.get(MatchmakingStrategy.AMALFI.value)
pairings = strategy.create_round(gara, round_number=1)

# Process pairings
for pairing in pairings:
    if pairing.is_bye:
        # Single player, automatic win
        pass
    elif pairing.is_trio:
        # 3-player match (pairing.players has 3 IDs)
        pass
    else:
        # Regular match
        player1, player2 = pairing.player1_id, pairing.player2_id
```

---

## Key Classes

### Pairing (Value Object)
Immutable dataclass representing a match pairing.

**Fields:** `players` (tuple of IDs), `is_bye`, `round_number`, `notes`

**Properties:** `player1_id`, `player2_id`, `is_trio`, `is_valid_pairing`

### BaseStrategy (Abstract)
Base class for all strategies. Implement `_generate_pairings()` and `_validate_strategy_specific()`.

**Class Attributes:** `name`, `display_name`, `min_players`, `max_players`, `supports_byes`, `requires_classification`

### EngineRegistry
Strategy registry with factory capabilities.

```python
registry.get(MatchmakingStrategy.AMALFI.value)  # Get strategy
registry.available()  # List strategy names
registry.create_strategy(name, seed=42)  # Deterministic for testing
```

---

## Strategies

| Strategy | Description | Min Players |
|----------|-------------|-------------|
| `amalfi` | Classification-based with anti-rematch | 3 |
| `round_robin` | All-play-all | 3 |
| `direct_elimination` | Single knockout | 4 |
| `double_knockout` | Winners + losers brackets | 8 |
| `random` | Random with anti-rematch | 2 |

### Amalfi Algorithm
- **Round 1**: Configurable (random, classification, rating)
- **Round 2+**: Classification-based "salto" algorithm
- **Odd players**: Last-place gets bye

### Random Anti-Rematch
- Uses NetworkX `max_weight_matching(G, maxcardinality=True)` with edge weights (100 non-rematch, 1 rematch) — prefers non-rematch pairings when possible, minimizes rematches when forced.
- Multi-objective trio selection: `(max(trio_count), rematch_penalty, sum(trio_count))` — protects the player with highest trio exposure first.
- Data source: `PlayerEncounterService.get_encounter_matrix(gara_id)` + `get_trio_counts(gara_id, exclude_walkover=True)` — cached 10 min, invalidated on match completion. Coherent with ADR-002 cleanup (reset match frees the pair).
- Bye history: `Match.query filter_by(is_bye=True)` (bye does not create `PlayerEncounter`).
- Forced rematches: `logger.warning` emitted with gara_id/round_number/n_rematches for audit trail.
- Determinism: `set_context(PairingContext(seed))` enables reproducible pairing generation for testing/replay.
- Odd player handling with `OddNumberPolicy.NO`: enforced at **inscription level**, not in the strategy. `InscriptionService` keeps `active_count` even by moving the last inscription to a parity waitlist (`is_waitlist=True`, `waitlist_reason=WaitlistReason.PARITY`); the strategy filters `is_waitlist=False` inscriptions like all others. See [`inscription_service.py:130-170`](../competition/inscription_service.py) and [`spec-random-odd-policy-no.md`](../../_bmad-output/implementation-artifacts/spec-random-odd-policy-no.md).
- Full spec: [`_bmad-output/implementation-artifacts/spec-random-anti-rematch.md`](../../_bmad-output/implementation-artifacts/spec-random-anti-rematch.md)

---

## Configuration Enums

> ⚠️ **Due enum omonimi.** `models/matchmaking/configuration.py` usa
> `direct_elimination` / `double_knockout`;
> `models/competition/validators.py` ne ha un altro, con gli stessi nomi di
> classe ma valori `elimination` / `double_ko`. Il ponte fra i due è
> `_MATCHMAKING_MAP` in `validators.py`, e un test
> (`test_matchmaking_enum_bridge.py`) verifica che copra **tutti** i valori
> dell'enum canonico: senza, una strategia nuova cadrebbe in silenzio sul
> default Amalfi e verrebbe validata con le regole sbagliate.
>
> In colonna (`Gara.matchmaking_strategy`, `Campionato.campionato_type`) c'è
> **sempre** quello canonico. Citare l'altro non solleva niente: è solo un
> confronto sempre falso. È successo in `models/match/trio_config.py`, dove
> `== "elimination"` doveva escludere le gare a tabellone e non ne ha escluso
> nessuna — per questo il guard oggi passa da `BRACKET_STRATEGIES`, che copre
> anche il doppio KO.
>
> Da agosto 2026 l'enum canonico è iniettato nei template (`app.py`,
> `inject_enums`) e i letterali sono presidiati staticamente da
> `tests/new/unit/test_match_status_no_raw_literals.py`, che controlla
> **entrambi** i vocabolari: quello giusto perché è fragile scriverlo a mano,
> quello sbagliato perché è già rotto.


```python
class MatchmakingStrategy(str, Enum):
    AMALFI = "amalfi"
    ROUND_ROBIN = "round_robin"
    DIRECT_ELIMINATION = "direct_elimination"
    DOUBLE_KNOCKOUT = "double_knockout"
    RANDOM = "random"

class FirstRoundPolicy(str, Enum):
    RANDOM = "random"
    CLASSIFICATION = "classification"
    RATING = "rating"

class OddNumberPolicy(str, Enum):
    NO = "no"                                # Parity waitlist — odd player moved to waitlist
    BYE = "bye"                              # Odd player sits out (automatic win)
    BYE_WITH_CHALLENGE = "bye_with_challenge"  # Bye + challenge completion for XP
    TRIO = "trio"                            # 3-player match (requires distance 2-7, ADR-005)
```

---

## Do Not

- **Do not use string literals** - Use `MatchmakingStrategy.AMALFI.value` not `"amalfi"`
- **Do not use round_number=0** - Round numbers are 1-based
- **Do not modify Pairing after creation** - Frozen dataclass
- **Do not skip validation** - Call `strategy.validate()` before `create_round()`
- **Do not forget classification for Amalfi** - Rounds 2+ need `RoundClassification` from previous round
- **Do not call strategy directly from routes** - Use `RoundService.create_round_with_strategy()`

---

## Cross-References

- **Competition**: [../competition/CLAUDE.md](../competition/CLAUDE.md) - Round management
- **Match**: [../match/CLAUDE.md](../match/CLAUDE.md) - Match execution
- **Classification**: [../classification/](../classification/) - Rankings for Amalfi
