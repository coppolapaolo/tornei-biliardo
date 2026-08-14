"""
Module: models/classification/bracket_standings.py
Purpose: posizioni finali ricavate dal tabellone (sistema POSITION)
Requirements: piano "Eliminazione diretta e doppio KO", Step 9 (US-16)

Nel tabellone la classifica **non** si costruisce sommando vittorie: si legge
da dove ciascuno è uscito. Chi esce allo stesso turno ha fatto lo stesso
percorso e non va separato, quindi le posizioni vengono a **bande a pari
merito**: i due semifinalisti sono entrambi 3°, i quattro quartifinalisti tutti
5°, gli otto ottavofinalisti tutti 9°. La banda vale la sua posizione più alta,
e la banda successiva riparte da "quanti giocatori ci sono davanti + 1".

Due eccezioni, entrambe volute:

- la **finalina 3°/4°** (US-7) scioglie la banda dei semifinalisti: il suo
  vincitore è 3°, il perdente 4°;
- nel **doppio KO** il terzo posto lo assegna già il tabellone — è chi perde
  l'ultimo turno del losers bracket — quindi quella banda non si presenta e la
  finalina non esiste.

Il calcolo è isolato in una funzione pura (`elimination_bands`) che lavora su
dati già estratti: serve a poterlo verificare senza DB, ma soprattutto perché
lo usano tre chiamanti diversi (la strategia di classifica per turno, quella
finale di gara e `SpareggioService.apply_final_positions`) e una seconda
implementazione divergerebbe in silenzio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..matchmaking.bracket import BRACKET_THIRD_PLACE

# Formati che eliminano alla seconda sconfitta invece che alla prima.
DOUBLE_ELIMINATION_STRATEGIES = frozenset({"double_knockout"})


@dataclass(frozen=True)
class BracketMatch:
    """Un nodo di tabellone concluso, ridotto a ciò che serve alla classifica."""

    bracket_type: str
    round_number: int
    players: Tuple[int, ...]
    winner_id: Optional[int] = None
    loser_id: Optional[int] = None
    order: int = 0  # tie-break stabile fra nodi dello stesso turno


def elimination_bands(
    matches: Iterable[BracketMatch], *, double_elimination: bool = False
) -> List[List[int]]:
    """Bande di pari merito, dalla migliore alla peggiore.

    Ogni banda è la lista dei giocatori usciti allo stesso punto del tabellone.
    La prima banda è chi non è (ancora) eliminato: a gara conclusa è il solo
    campione, a gara in corso sono tutti quelli ancora in gioco — che è la
    risposta giusta, perché finché non esci il tabellone non ti ha ancora
    ordinato.

    `double_elimination` cambia una cosa sola: quante sconfitte servono per
    essere fuori. Il turno in cui cade **quella** sconfitta è la banda.
    """
    ordered = sorted(matches, key=lambda m: (m.round_number, m.order))

    participants: set = set()
    losses: Dict[int, List[BracketMatch]] = {}
    third_place: Optional[BracketMatch] = None

    for match in ordered:
        participants.update(player for player in match.players if player)
        if match.bracket_type == BRACKET_THIRD_PLACE:
            third_place = match
        if match.loser_id is not None:
            losses.setdefault(match.loser_id, []).append(match)

    required_losses = 2 if double_elimination else 1
    eliminated_at: Dict[int, int] = {
        player: player_losses[required_losses - 1].round_number
        for player, player_losses in losses.items()
        if len(player_losses) >= required_losses
    }

    # La finalina toglie i due semifinalisti dalla loro banda e li ordina fra
    # loro: è esattamente il motivo per cui il director l'ha chiesta.
    third_pair: Tuple[int, ...] = ()
    if third_place and third_place.winner_id and third_place.loser_id:
        third_pair = (third_place.winner_id, third_place.loser_id)
        for player in third_pair:
            eliminated_at.pop(player, None)

    bands: List[List[int]] = []
    alive = sorted(
        player
        for player in participants
        if player not in eliminated_at and player not in third_pair
    )
    if alive:
        bands.append(alive)

    by_round: Dict[int, List[int]] = {}
    for player, round_number in eliminated_at.items():
        by_round.setdefault(round_number, []).append(player)

    third_inserted = False
    for round_number in sorted(by_round, reverse=True):
        bands.append(sorted(by_round[round_number]))
        # I due della finalina valgono 3° e 4°, quindi entrano subito dopo la
        # banda del turno in cui la finalina si è giocata (quello della finale).
        if (
            third_pair
            and not third_inserted
            and third_place is not None
            and round_number <= third_place.round_number
        ):
            bands.extend([[third_pair[0]], [third_pair[1]]])
            third_inserted = True

    if third_pair and not third_inserted:
        bands.extend([[third_pair[0]], [third_pair[1]]])

    return bands


def positions_from_bands(bands: Sequence[Sequence[int]]) -> Dict[int, int]:
    """Banda → posizione: la banda vale la sua posizione più alta.

    Quattro quartifinalisti sono tutti 5° e la banda successiva riparte da 9,
    non da 6: i pari merito occupano comunque il loro posto in classifica.
    """
    positions: Dict[int, int] = {}
    next_position = 1
    for band in bands:
        for player in band:
            positions[player] = next_position
        next_position += len(band)
    return positions


def bracket_positions(gara) -> Dict[int, int]:
    """Posizione di ciascun giocatore secondo il tabellone persistito.

    Dizionario vuoto se la gara non ha un tabellone (nessuna coordinata): il
    chiamante deve poter distinguere "nessuno è ancora uscito" da "questa gara
    non è a tabellone", e ricadere sul comportamento precedente nel secondo
    caso.
    """
    from models.match.models import Match
    from models.status_enum import MatchStatus

    rows = (
        Match.query.filter(Match.gara_id == gara.id, Match.bracket_type.isnot(None))
        .order_by(Match.round_number, Match.id)
        .all()
    )
    if not rows:
        return {}

    matches: List[BracketMatch] = []
    for row in rows:
        winner_id = row.winner_id
        loser_id = None
        if winner_id and not row.is_bye and MatchStatus.is_finished(row.status):
            loser_id = row.player1_id if winner_id == row.player2_id else row.player2_id
        matches.append(
            BracketMatch(
                bracket_type=row.bracket_type,
                round_number=row.round_number,
                players=tuple(
                    player
                    for player in (row.player1_id, row.player2_id)
                    if player is not None
                ),
                winner_id=winner_id if MatchStatus.is_finished(row.status) else None,
                loser_id=loser_id,
                order=row.id or 0,
            )
        )

    double = (
        getattr(gara, "matchmaking_strategy", None) in DOUBLE_ELIMINATION_STRATEGIES
    )
    return positions_from_bands(elimination_bands(matches, double_elimination=double))


__all__ = [
    "BracketMatch",
    "DOUBLE_ELIMINATION_STRATEGIES",
    "bracket_positions",
    "elimination_bands",
    "positions_from_bands",
]
