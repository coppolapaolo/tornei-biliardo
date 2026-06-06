"""Achievement metrics — fonte di verità unica per i requisiti "conta N".

Ogni achievement del tipo "raggiungi N di qualcosa" deriva il proprio valore
corrente da una query sul dominio, NON da un contatore incrementale fragile
(`UserAchievement.current_progress`). Conseguenze:

- **idempotenza / auto-correzione**: un re-check è sempre corretto, anche se un
  evento è stato perso o un achievement viene riattivato a posteriori;
- **nessun backfill**: i dati storici contano retroattivamente;
- **handler più semplici**: non incrementano contatori, si limitano a
  "riconciliare" (vedi `AchievementService.reconcile_metric_achievements`).

I tipi NON conteggiabili (win_rate, level_reached, weekly_streak,
gaming_data_shared, director_eligibility) hanno logica booleana propria in
`AchievementService._check_requirements` e qui ritornano `None`. Anche gli stub
privi di tracking (win_streak, category_reached, challenges_completed,
perfect_challenges, strategies_tried) ritornano `None` → restano non
ottenibili finché non esiste la sorgente dati.
"""

from __future__ import annotations

from typing import Optional, Dict, Any

from models.base import db

# Stati che indicano una partita effettivamente giocata (non solo programmata).
_PLAYED_MATCH_STATUSES = ("completed", "validated")


class AchievementMetrics:
    """Calcola il valore corrente delle metriche conteggiabili degli achievement."""

    #: Requirement type i cui achievement sono "conta N >= target".
    COUNTABLE_TYPES = frozenset(
        {
            "match_wins",
            "tournament_participation",
            "tournament_wins",
            "tournament_podium",
            "unique_opponents",
            "match_proposals_created",
            "match_proposals_accepted",
        }
    )

    @staticmethod
    def current_value(
        user_id: int, requirement_type: str, requirements: Dict[str, Any]
    ) -> Optional[int]:
        """Valore corrente della metrica, o None se il tipo non è conteggiabile.

        `requirements` è accettato per simmetria/estensibilità (alcune metriche
        future potrebbero parametrizzarsi su di esso) ma le metriche attuali
        dipendono solo da `user_id`.
        """
        resolver = _RESOLVERS.get(requirement_type)
        return resolver(user_id) if resolver else None

    # ------------------------------------------------------------------
    # Resolver per metrica (uno per requirement type conteggiabile)
    # ------------------------------------------------------------------

    @staticmethod
    def _match_wins(user_id: int) -> int:
        from models.user.services import UserStatsService

        return int(UserStatsService.get_user_stats(user_id).get("won_matches", 0))

    @staticmethod
    def _tournament_participation(user_id: int) -> int:
        from models.user.services import UserStatsService

        return int(UserStatsService.get_user_stats(user_id).get("inscription_count", 0))

    @staticmethod
    def _tournament_wins(user_id: int) -> int:
        return AchievementMetrics._count_placement_awards(user_id, include_podium=False)

    @staticmethod
    def _tournament_podium(user_id: int) -> int:
        # Il vincitore è anche sul podio: conta sia i premi vittoria sia podio.
        return AchievementMetrics._count_placement_awards(user_id, include_podium=True)

    @staticmethod
    def _count_placement_awards(user_id: int, include_podium: bool) -> int:
        """Piazzamenti in gara derivati dal libro mastro XP della gamification.

        Il segnale autorevole e *sempre presente al momento del check* per
        "ho vinto/sono andato a podio in una gara" è il premio XP assegnato
        dall'handler di completamento gara (TOURNAMENT_WIN / TOURNAMENT_PODIUM):
        è interno al dominio gamification e persistito nella stessa transazione
        prima del check achievement. `GaraClassification` non è garantita
        popolata al completamento (è calcolata altrove), quindi non è una
        sorgente affidabile qui.
        """
        from models.gamification.models import XPTransaction, XPTransactionType

        types = [XPTransactionType.TOURNAMENT_WIN]
        if include_podium:
            types.append(XPTransactionType.TOURNAMENT_PODIUM)

        return int(
            db.session.query(XPTransaction)
            .filter(
                XPTransaction.user_id == user_id,
                XPTransaction.transaction_type.in_(types),
            )
            .count()
        )

    @staticmethod
    def _unique_opponents(user_id: int) -> int:
        """Avversari distinti affrontati in partite giocate (gara + casual)."""
        from models.match.models import Match, TrioMatch
        from models.individual_match.match_models import IndividualMatch
        from models.status_enum import MatchStatus

        opponents: set[int] = set()

        # Partite di gara 1v1
        regular = (
            db.session.query(Match.player1_id, Match.player2_id)
            .filter(
                Match.is_trio.is_(False),
                Match.status.in_(_PLAYED_MATCH_STATUSES),
                db.or_(Match.player1_id == user_id, Match.player2_id == user_id),
            )
            .all()
        )
        for p1, p2 in regular:
            opponents.add(p1 if p2 == user_id else p2)

        # Partite trio: gli altri due giocatori sono avversari
        trios = (
            db.session.query(
                TrioMatch.player1_id, TrioMatch.player2_id, TrioMatch.player3_id
            )
            .join(Match, Match.id == TrioMatch.match_id)
            .filter(
                Match.status.in_(_PLAYED_MATCH_STATUSES),
                db.or_(
                    TrioMatch.player1_id == user_id,
                    TrioMatch.player2_id == user_id,
                    TrioMatch.player3_id == user_id,
                ),
            )
            .all()
        )
        for trio in trios:
            opponents.update(trio)

        # Partite casual (individual match)
        casual = (
            db.session.query(IndividualMatch.player1_id, IndividualMatch.player2_id)
            .filter(
                IndividualMatch.status.in_(
                    [MatchStatus.COMPLETED, MatchStatus.VALIDATED]
                ),
                db.or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                ),
            )
            .all()
        )
        for p1, p2 in casual:
            opponents.add(p1 if p2 == user_id else p2)

        opponents.discard(user_id)
        opponents.discard(None)  # type: ignore[arg-type]
        return len(opponents)

    @staticmethod
    def _proposals_created(user_id: int) -> int:
        """Proposte di partita create (escluse quelle annullate)."""
        from models.individual_match.proposal_models import (
            MatchProposal,
            ProposalStatus,
        )

        return int(
            MatchProposal.query.filter(
                MatchProposal.proposer_id == user_id,
                MatchProposal.status != ProposalStatus.CANCELLED,
            ).count()
        )

    @staticmethod
    def _proposals_accepted(user_id: int) -> int:
        """Inviti/proposte accettati dall'utente."""
        from models.individual_match.proposal_models import MatchProposal

        return int(MatchProposal.query.filter_by(accepted_by_id=user_id).count())


_RESOLVERS = {
    "match_wins": AchievementMetrics._match_wins,
    "tournament_participation": AchievementMetrics._tournament_participation,
    "tournament_wins": AchievementMetrics._tournament_wins,
    "tournament_podium": AchievementMetrics._tournament_podium,
    "unique_opponents": AchievementMetrics._unique_opponents,
    "match_proposals_created": AchievementMetrics._proposals_created,
    "match_proposals_accepted": AchievementMetrics._proposals_accepted,
}
