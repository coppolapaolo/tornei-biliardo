---
title: 'Trio+forfeit handling in create_matches_from_pairings'
type: 'bugfix'
created: '2026-04-19'
status: 'done'
baseline_commit: '864b47803209308e3983ca8b50e819200eb30db3'
context:
  - 'docs/adr/ADR-005-trio-match-logic.md'
  - 'CLAUDE.md (transactional, soft-delete conventions)'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** In `models/competition/round_creation.py`, the branch handling trio pairings (`len(pairing.players) == 3`) ignores `forfeit_user_ids`. When matchmaking produces a trio that contains players already marked `is_forfeit=True`, the match is created as a normal pending `TrioMatch`, letting forfeit players appear to be playing. The 2-player branch already handles 1/2 and 2/2 forfeits; the trio branch has no equivalent.

**Approach:** Dispatch on the number of forfeiting players in the trio. For **1/3**, convert the pairing into a pending 2-player `Match` between the non-forfeit players (skip `TrioMatch` creation). For **2/3**, create a completed `TrioMatch` as walkover for the surviving player. For **3/3**, create a completed `TrioMatch` with a deterministic winner (first player, mirroring the 2-player `[0]` convention). No schema changes.

## Boundaries & Constraints

**Always:**
- Preserve existing behavior for 0/3 forfeits (create normal pending `TrioMatch` with `initialize_matchup`).
- The 2-player fallback for 1/3 uses the same `Match` completion invariants as the existing 2-player branch would if no one were in forfeit: `is_bye=False`, `is_trio=False`, `player1_id/player2_id` set, `match_distance=round_distance`, `discipline=round_discipline`, `is_multi_set=gara.is_multi_set`, `status="pending"`, no `winner_id`, no scores.
- For walkover completions (2/3 and 3/3): set `Match.winner_id`, `Match.player1_score=round_distance`, `Match.player2_score=0`, `Match.status="completed"`, `Match.is_trio=True`; set `TrioMatch.winner_id`, `TrioMatch.is_completed=True`; do **not** create any `TrioRack` rows; do not call `initialize_matchup`; do not touch `awaiting_confirmation` or `player1/2/3_confirmed`.
- The parent `Match` fields `player1_id` and `player2_id` for a walkover trio follow the current convention on line 99-100: the trio's first two players (irrespective of forfeit status); `player3_id` lives only on `TrioMatch`.
- Function signature of `create_matches_from_pairings` stays unchanged; no new parameters.
- Idempotency guard at the call site (`_create_round_impl`, counting existing matches) must keep working — new walkover matches count as already-created on re-entry.

**Ask First:**
- If the implementation discovers that existing trio strategies (e.g. Amalfi) proactively exclude forfeit players from trios, so the 1/3 and 2/3 cases are unreachable in practice: HALT and ask the human whether to keep the defensive branch or drop it.

**Never:**
- Do not modify the `TrioMatch` model (no new columns, no multiple `forfeit_player_id`).
- Do not change `WithdrawPolicyService`, `handle_forfeit`, or any strategy code.
- Do not alter the 2-player branch behavior or the 1-player bye branch.
- Do not emit `MatchCompleted` SSE events manually inside `create_matches_from_pairings` — this function only builds rows; downstream code handles events when the round state transitions.

## I/O & Edge-Case Matrix

All scenarios assume `len(pairing.players) == 3`, `pairing.is_bye == False`, `round_distance = D`, and `forfeit_user_ids` provided. Players are identified by position in `pairing.players`: `P0`, `P1`, `P2`.

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 0/3 forfeit (baseline) | None of `P0,P1,P2` in forfeit set | Create `Match(is_trio=True, pending)` + `TrioMatch` + `initialize_matchup()`. Unchanged from today. | N/A |
| 1/3 forfeit | Exactly one of `P0,P1,P2` in forfeit set | Create a 2-player pending `Match` between the two non-forfeit players (preserving their relative order from `pairing.players`). No `TrioMatch` row. `is_trio=False`. | N/A |
| 2/3 forfeit | Exactly two of `P0,P1,P2` in forfeit set | Create `Match(is_trio=True, completed)` with `winner_id` = the non-forfeit player, `player1_score=D`, `player2_score=0`; create `TrioMatch(player1=P0, player2=P1, player3=P2, winner_id=<non-forfeit>, is_completed=True)`; no racks, no `initialize_matchup`. | N/A |
| 3/3 forfeit | All of `P0,P1,P2` in forfeit set | Same as 2/3 but `winner_id = P0` (deterministic, mirrors 2-player `[0]` fallback). `player1_score=D`, `player2_score=0`. | N/A |

</frozen-after-approval>

## Code Map

- `models/competition/round_creation.py` -- owns the buggy branch; the fix lives here.
- `models/match/models.py` -- `Match` and `TrioMatch` field definitions (read-only reference for the walkover wiring).
- `models/matchmaking/strategies/base.py` -- `Pairing` dataclass (frozen, `players: Tuple[int, ...]`) — just confirms shape.
- `models/competition/withdraw_policy_service.py` -- source of truth for how forfeit players are computed (`get_forfeit_inscriptions`) and how mid-match forfeit is handled (`handle_forfeit`) — reference only; not modified.
- `tests/new/unit/test_trio_forfeit_player3.py` -- existing trio-forfeit test; check for fixture patterns to reuse.

## Tasks & Acceptance

**Execution:**
- [x] `tests/new/unit/test_round_creation_trio_forfeit.py` -- NEW file with regression tests covering the four rows of the I/O Matrix (0/3, 1/3, 2/3, 3/3). Each test builds a gara, three players, a single-pairing list, invokes `create_matches_from_pairings` directly, and asserts DB state (Match flags, TrioMatch existence, winner_id, scores). 0/3 is a baseline-guard test. Tests must fail against current code for the 1/3, 2/3, 3/3 cases.
- [x] `models/competition/round_creation.py` -- refactor the `len(pairing.players) == 3` branch into a small dispatch: compute `forfeit_in_trio = [p for p in pairing.players if p in forfeit_user_ids]`; based on its length (0/1/2/3) take the corresponding action. Extract helpers if readability demands it, but keep everything inside the same module. No changes to `_create_round_impl` or the service class.

**Acceptance Criteria:**
- Given a 3-player pairing with zero forfeits, when `create_matches_from_pairings` runs, then a pending trio `Match`+`TrioMatch` pair is created with `initialize_matchup` side effects (unchanged baseline).
- Given a 3-player pairing with exactly one forfeit player, when the function runs, then exactly one `Match` row is created with `is_trio=False`, `is_bye=False`, `status="pending"`, `player1_id` and `player2_id` equal to the two non-forfeit players (in their original order), no `TrioMatch` row exists for that match.
- Given a 3-player pairing with two forfeits, when the function runs, then a `Match(is_trio=True, status="completed")` and a `TrioMatch(is_completed=True)` exist, `Match.winner_id == TrioMatch.winner_id == <non-forfeit player>`, `Match.player1_score == round_distance`, `Match.player2_score == 0`, and no `TrioRack` rows exist for that trio.
- Given a 3-player pairing with three forfeits, same outcome as 2/3 but `winner_id == pairing.players[0]`.
- `pytest tests/new/unit/test_round_creation_trio_forfeit.py -n auto` passes after implementation.
- `pyright` reports 0 errors.
- No other test file regresses (full unit + integration suite green).

## Design Notes

**Why convert 1/3 to a 2-player Match instead of using `handle_forfeit`:** Pre-round forfeit of a trio player collapses the pairing to a two-player contest. Calling `handle_forfeit` would keep the trio shape, auto-fill some racks, and still require the two survivors to play the remaining "real" racks between them — a convoluted UX for what is effectively a 2-player match. Treating it as a 2-player match matches player intuition and stays consistent with how the 2-player branch handles the symmetric 1/2 case (one player missing → the other plays).

**Walkover semantics for 2/3 and 3/3 (no racks):** `TrioMatch.player_racks` are computed from `TrioRack` rows, so skipping rack creation means all three `playerN_racks` read as 0. That is correct: nobody played. The Match-level score (`player1_score=D`, `player2_score=0`) preserves compatibility with existing Match-based reporting and mirrors the 2-player forfeit convention. `winner_id` on the trio is set directly; no Schulze/Condorcet needed because there is no tournament to rank.

**Sketch for the dispatch:**

```python
elif len(pairing.players) == 3:
    p0, p1, p2 = pairing.players
    forfeit_in_trio = [p for p in pairing.players if p in forfeit_user_ids]
    n = len(forfeit_in_trio)

    if n == 0:
        # existing code: pending TrioMatch + initialize_matchup
        ...
    elif n == 1:
        survivors = [p for p in pairing.players if p not in forfeit_user_ids]
        match = Match(..., player1_id=survivors[0], player2_id=survivors[1], is_trio=False, ...)
        db.session.add(match)
    else:  # n in (2, 3)
        winner_id = (
            next(p for p in pairing.players if p not in forfeit_user_ids)
            if n == 2 else p0
        )
        match = Match(..., is_trio=True, status="completed",
                      winner_id=winner_id,
                      player1_score=round_distance, player2_score=0, ...)
        db.session.add(match); db.session.flush()
        trio = TrioMatch(match_id=match.id, player1_id=p0, player2_id=p1, player3_id=p2,
                         winner_id=winner_id, is_completed=True)
        db.session.add(trio)
```

## Verification

**Commands:**
- `pytest tests/new/unit/test_round_creation_trio_forfeit.py -n auto 2>&1 | tail -1` -- expected: `N passed` (N = 4 or more).
- `pytest tests/new/ -n 4 2>&1 | tail -1` -- expected: `N passed` with no regressions vs. baseline.
- `pyright 2>&1 | tail -1` -- expected: `0 errors, 0 warnings, 0 informations`.
- `black models/competition/round_creation.py tests/new/unit/test_round_creation_trio_forfeit.py && flake8 models/competition/round_creation.py tests/new/unit/test_round_creation_trio_forfeit.py` -- expected: no output.
