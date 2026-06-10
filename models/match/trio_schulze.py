"""
Schulze/Condorcet method for determining trio match winner.

With 3 players, we extract pairwise rack wins from TrioRack records
and use the Condorcet criterion (beats both others) to find the winner.
If there's a cycle (A>B, B>C, C>A), the Schulze strongest-path method
resolves it. If completely tied, returns None.
"""

from typing import Optional, List, Tuple, Dict


def determine_trio_winner(active_racks: list, player_ids: List[int]) -> Optional[int]:
    """Determine trio winner using Condorcet/Schulze method.

    Args:
        active_racks: List of TrioRack objects (non-deleted).
            Each has player1_id, player2_id (the matchup) and winner_id.
        player_ids: The 3 player IDs in the trio [p1, p2, p3].

    Returns:
        Winner player_id, or None if completely tied.
    """
    if len(player_ids) < 2:
        return player_ids[0] if player_ids else None

    if len(player_ids) == 2:
        return _pairwise_winner(active_racks, player_ids[0], player_ids[1])

    # Build pairwise win matrix: wins[a][b] = racks a won against b
    wins = _build_pairwise_wins(active_racks, player_ids)

    # Check for Condorcet winner (beats both others in pairwise comparison)
    condorcet = _find_condorcet_winner(wins, player_ids)
    if condorcet is not None:
        return condorcet

    # Cycle detected — use Schulze strongest path
    return _schulze_resolve(wins, player_ids)


def _build_pairwise_wins(
    active_racks: list, player_ids: List[int]
) -> Dict[int, Dict[int, int]]:
    """Count rack wins for each pairwise matchup.

    Returns: wins[a][b] = number of racks a won when playing against b.
    """
    wins: Dict[int, Dict[int, int]] = {
        p: {q: 0 for q in player_ids if q != p} for p in player_ids
    }

    for rack in active_racks:
        matchup = {rack.player1_id, rack.player2_id}
        if rack.winner_id in matchup:
            loser = (matchup - {rack.winner_id}).pop()
            if rack.winner_id in wins and loser in wins[rack.winner_id]:
                wins[rack.winner_id][loser] += 1

    return wins


def _find_condorcet_winner(
    wins: Dict[int, Dict[int, int]], player_ids: List[int]
) -> Optional[int]:
    """Find player who beats all others in pairwise rack comparison.

    A beats B if A won more racks against B than B won against A.
    """
    for candidate in player_ids:
        beats_all = True
        for opponent in player_ids:
            if opponent == candidate:
                continue
            if wins[candidate][opponent] <= wins[opponent][candidate]:
                beats_all = False
                break
        if beats_all:
            return candidate
    return None


def _schulze_resolve(
    wins: Dict[int, Dict[int, int]], player_ids: List[int]
) -> Optional[int]:
    """Resolve a Condorcet cycle using Schulze strongest-path method.

    With 3 players and a cycle A>B, B>C, C>A, Schulze computes:
    - Strength of path A->B = margin(A,B)
    - Strength of path A->C via B = min(margin(A,B), margin(B,C))
    - Direct strength A->C = margin(A,C) (negative since C>A)
    - Strongest path A->C = max(direct, via B)

    The player with the strongest paths wins.
    """
    n = len(player_ids)
    idx = {p: i for i, p in enumerate(player_ids)}

    # Build margin matrix: d[i][j] = wins[i][j] - wins[j][i]
    d = [[0] * n for _ in range(n)]
    for i, pi in enumerate(player_ids):
        for j, pj in enumerate(player_ids):
            if i != j:
                d[i][j] = wins[pi][pj] - wins[pj][pi]

    # Floyd-Warshall for strongest paths
    # strength[i][j] = strength of strongest path from i to j
    strength = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                strength[i][j] = d[i][j]

    for k in range(n):
        for i in range(n):
            for j in range(n):
                if i != j and i != k and j != k:
                    via_k = min(strength[i][k], strength[k][j])
                    if via_k > strength[i][j]:
                        strength[i][j] = via_k

    # Find winner: player whose weakest strongest-path is the best
    best_player = None
    best_min_strength = None

    for i, pi in enumerate(player_ids):
        min_strength = min(strength[i][j] for j in range(n) if j != i)
        if best_min_strength is None or min_strength > best_min_strength:
            best_min_strength = min_strength
            best_player = pi
        elif min_strength == best_min_strength:
            # Complete tie even after Schulze — no winner
            best_player = None

    return best_player


def _pairwise_winner(active_racks: list, p1: int, p2: int) -> Optional[int]:
    """Direct pairwise comparison for 2-player case (forfeit scenario)."""
    p1_wins = 0
    p2_wins = 0
    for rack in active_racks:
        matchup = {rack.player1_id, rack.player2_id}
        if matchup == {p1, p2}:
            if rack.winner_id == p1:
                p1_wins += 1
            elif rack.winner_id == p2:
                p2_wins += 1

    if p1_wins > p2_wins:
        return p1
    elif p2_wins > p1_wins:
        return p2
    return None
