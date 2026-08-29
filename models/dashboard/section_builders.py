# models/dashboard/section_builders.py
"""Dashboard section builder methods.

Extracted from services.py for maintainability (Round 4 P3).
Builds player, individual match, challenge, and gamification sections.
"""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from models.base import db
from models.campionato.models import Campionato
from models.competition.models import Gara, Inscription
from models.match.models import Match as TournamentMatch
from models.status_enum import GaraStatus, MatchStatus

from .view_models import _user_is_match_participant


class DashboardSectionBuilder:
    """Builds dashboard sections for player-like views."""

    @staticmethod
    def build_player_sections(user_id: int, selected: Optional[Campionato]) -> dict:
        """Costruisce available_garas, my_inscriptions, current_matches,
        recent_matches per il campionato selezionato."""
        available_garas: List[Gara] = []
        my_regs: List[Inscription] = []
        my_upcoming: List[TournamentMatch] = []
        my_recent: List[TournamentMatch] = []

        if not selected:
            return {
                "available_garas": available_garas,
                "my_inscriptions": my_regs,
                "current_matches": my_upcoming,
                "recent_matches": my_recent,
            }

        subq_my_gara_ids = (
            select(Inscription.gara_id)
            .where(Inscription.user_id == user_id)
            .scalar_subquery()
        )

        available_garas = (
            db.session.query(Gara)
            .filter(
                Gara.campionato_id == selected.id,
                Gara.status == GaraStatus.INSCRIPTION.value,
                ~Gara.id.in_(subq_my_gara_ids),
            )
            .order_by(Gara.date.asc().nullslast(), Gara.number.asc())
            .all()
        )

        my_regs = (
            db.session.query(Inscription)
            .join(Gara, Gara.id == Inscription.gara_id)
            .filter(Inscription.user_id == user_id, Gara.campionato_id == selected.id)
            .options(joinedload(Inscription.gara))
            .order_by(Gara.date.desc().nullslast(), Gara.number.desc())
            .all()
        )

        # Partite attive (solo in attesa e in corso, NO completate - quelle
        # vanno nello storico)
        my_upcoming = (
            db.session.query(TournamentMatch)
            .join(Gara, Gara.id == TournamentMatch.gara_id)
            .filter(
                TournamentMatch.status.in_(  # type: ignore[attr-defined]
                    [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
                ),
                _user_is_match_participant(user_id),
            )
            .order_by(
                TournamentMatch.created_at.desc().nullslast(), TournamentMatch.id.desc()
            )
            .limit(10)
            .all()
        )

        my_recent = (
            db.session.query(TournamentMatch)
            .join(Gara, Gara.id == TournamentMatch.gara_id)
            .filter(
                Gara.campionato_id == selected.id,
                TournamentMatch.status == MatchStatus.CLOSED_UNILATERALLY.value,
                _user_is_match_participant(user_id),
            )
            .order_by(
                TournamentMatch.created_at.desc().nullslast(), TournamentMatch.id.desc()
            )
            .limit(10)
            .all()
        )

        return {
            "available_garas": available_garas,
            "my_inscriptions": my_regs,
            "current_matches": my_upcoming,
            "recent_matches": my_recent,
        }

    @staticmethod
    def build_individual_match_sections(user_id: int) -> dict:
        """Build individual match proposal sections for user."""
        from ..individual_match.services import IndividualMatchService
        from ..individual_match.models import IndividualMatch

        # Get user's match proposals
        proposals = IndividualMatchService.get_user_proposals(
            user_id, include_expired=False
        )

        # Get recent individual matches
        recent_individual_matches = (
            db.session.query(IndividualMatch)
            .filter(
                or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                )
            )
            .order_by(IndividualMatch.created_at.desc())
            .limit(10)
            .all()
        )

        # Match opportunities: open proposals already filtered by eligibility
        # in ProposalService.get_user_proposals (venue/played-based, ADR-033).
        opportunities = proposals.get("available", [])

        return {
            "match_proposals": proposals,
            "individual_matches": recent_individual_matches,
            "match_opportunities": opportunities[:5],  # Limit to top 5 opportunities
        }

    @staticmethod
    def build_playoff_invitations(user_id: int) -> List[Any]:
        """Gli inviti ai playoff ancora senza risposta per questo giocatore.

        Sono una cosa da fare, non una notizia: finché restano `PENDING` il
        posto in finale è appeso, e alla scadenza la cascata dei rifiuti lo
        passa a qualcun altro (SPECIFICHE.md riga 188). Vanno quindi in
        dashboard accanto alle gare e ai match, non solo nella pagina
        dell'invito che si raggiunge da una notifica.
        """
        from models.playoff.models import (
            PlayoffConfiguration,
            PlayoffQualification,
            QualificationStatus,
        )

        # Il join su `Campionato` non serve a leggere niente: serve a far
        # scattare il filtro soft-delete, che e' un `with_loader_criteria`
        # (models/soft_delete/filter.py) e quindi si applica solo alle entita'
        # che **compaiono nella query**. Interrogando la sola
        # `PlayoffQualification` una qualificazione rimasta `PENDING` su un
        # campionato eliminato continuerebbe a comparire in dashboard, con due
        # pulsanti che scrivono su dati orfani — trovato sul DB di sviluppo,
        # che ne aveva sette. Il predicato esplicito qui sotto e' ridondante e
        # sta per dirlo a chi legge. Stessa ragione per `is_active`: una
        # configurazione disattivata non e' piu' un invito.
        return (
            db.session.query(PlayoffQualification)
            .join(
                PlayoffConfiguration,
                PlayoffConfiguration.id == PlayoffQualification.configuration_id,
            )
            .join(Campionato, Campionato.id == PlayoffConfiguration.campionato_id)
            .filter(
                PlayoffQualification.user_id == user_id,
                PlayoffQualification.status == QualificationStatus.PENDING,
                PlayoffConfiguration.is_active.is_(True),
                Campionato.is_deleted.is_(False),
            )
            .options(joinedload(PlayoffQualification.configuration))
            .order_by(PlayoffQualification.qualifying_position)
            .all()
        )

    @staticmethod
    def build_bye_challenges(user_id: int) -> List[Any]:
        """Le X che questo giocatore puo' ancora sostituire con una prova.

        Chi resta senza avversario in una gara con
        `odd_number_policy = "bye_with_challenge"` non sta fermo: gioca un
        esercizio, e il punteggio diventa la sua differenza triangoli in quel
        turno (SPECIFICHE.md riga 65). E' una cosa **da fare**, con una
        scadenza implicita — il turno finisce — quindi va in dashboard accanto
        ai match e agli inviti ai playoff.

        Perche' non basta la sezione «I tuoi match»: il match con la X nasce
        `pending` e viene chiuso subito da `round_creation`, mentre quella
        sezione mostra solo `pending`/`playing`. Il giocatore quindi non vede
        niente — ed e' esattamente il motivo per cui la prova non la giocava
        nessuno (issue #221). Lasciare il match aperto lo farebbe comparire li'
        gratis, ma un turno e' completo quando **tutte** le sue partite sono
        concluse: chi non gioca mai l'esercizio bloccherebbe l'avanzamento per
        tutti gli altri.

        Restituisce dizionari e non entita': la scheda ha bisogno della gara,
        del turno e del punteggio massimo ammesso, che vengono da tre posti
        diversi e che il template non deve ricomporre.
        """
        from models.competition.gara_bye_challenge import GaraByeChallenge
        from models.matchmaking.configuration import OddNumberPolicy

        # Il join su `Gara` non e' decorativo: serve a limitare alle gare in
        # corso e a far scattare il filtro soft-delete, che e' un
        # `with_loader_criteria` e quindi si applica solo alle entita' presenti
        # nella query. Senza, una X su una gara eliminata resterebbe in
        # dashboard con un pulsante che scrive su dati orfani — stessa trappola
        # gia' documentata in `build_playoff_invitations`.
        match_con_x = (
            db.session.query(TournamentMatch)
            .join(Gara, Gara.id == TournamentMatch.gara_id)
            .filter(
                TournamentMatch.player1_id == user_id,
                TournamentMatch.is_bye.is_(True),
                Gara.status == GaraStatus.PLAYING.value,
                Gara.odd_number_policy == OddNumberPolicy.BYE_WITH_CHALLENGE.value,
            )
            .options(joinedload(TournamentMatch.gara))
            .order_by(TournamentMatch.round_number)
            .all()
        )
        if not match_con_x:
            return []

        # Una sola query per i ponti gia' aperti, invece di una per match.
        ponti = {
            (p.gara_id, p.round_number): p
            for p in db.session.query(GaraByeChallenge)
            .filter(
                GaraByeChallenge.user_id == user_id,
                GaraByeChallenge.gara_id.in_({m.gara_id for m in match_con_x}),
            )
            .all()
        }

        schede: List[Any] = []
        for match in match_con_x:
            ponte = ponti.get((match.gara_id, match.round_number))
            if ponte is not None and ponte.is_completed:
                continue  # gia' giocata: non e' piu' una cosa da fare
            schede.append(
                {
                    "gara": match.gara,
                    "round_number": match.round_number,
                    "match": match,
                    # Il massimo ammesso e' quello del **turno**, non della
                    # gara: in un turno «al 3» dentro una gara «al 5» un 4
                    # sarebbe un punteggio che giocando nessuno puo' ottenere
                    # (ADR-027). E' lo stesso limite che
                    # `complete_x_replacement_attempt` applica in scrittura.
                    "punteggio_massimo": match.effective_distance,
                    "iniziata": ponte is not None,
                }
            )
        return schede

    @staticmethod
    def build_challenge_sections(
        user_id: int, selected_campionato: Optional[Campionato]
    ) -> dict:
        """Build challenge sections for user."""
        from ..competition.gara_challenge_service import GaraChallengeService
        from ..competition.gara_challenge import GaraChallenge

        available_challenges = []
        player_challenge_progress = {}

        # Get all garas where the user is inscribed (both campionato and standalone)
        inscribed_garas = (
            db.session.query(Gara)
            .join(Inscription, Inscription.gara_id == Gara.id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,  # noqa: E712
            )
            .all()
        )

        # If we have a selected campionato, prioritize its garas
        if selected_campionato:
            campionato_garas = [
                gara
                for gara in inscribed_garas
                if gara.campionato_id == selected_campionato.id
            ]
            # If user is inscribed in campionato garas, use those; otherwise
            # use all inscribed garas
            target_garas = campionato_garas if campionato_garas else inscribed_garas
        else:
            # No selected campionato, use all inscribed garas
            target_garas = inscribed_garas

        # Get available challenges for target garas
        for gara in target_garas:
            gara_challenges = (
                db.session.query(GaraChallenge)
                .filter(
                    GaraChallenge.gara_id == gara.id,
                    GaraChallenge.is_active == True,  # noqa: E712
                )
                .options(joinedload(GaraChallenge.challenge))  # type: ignore[arg-type]
                .all()
            )
            available_challenges.extend(gara_challenges)

            # Get player progress for this gara. NON sovrascrivere la chiave
            # user_id ad ogni iterazione (così sopravviveva solo l'ultima gara
            # mentre available_challenges aggrega TUTTE): unisci le liste
            # `challenges` e somma gli aggregati su tutte le gare target.
            progress = GaraChallengeService.get_user_gara_challenge_progress(
                gara.id, user_id
            )
            if progress and progress.get("challenges"):
                merged = player_challenge_progress.setdefault(
                    user_id,
                    {
                        "challenges": [],
                        "total_best_score": 0,
                        "total_all_attempts": 0,
                        "challenges_attempted": 0,
                    },
                )
                merged["challenges"].extend(progress["challenges"])
                merged["total_best_score"] += progress.get("total_best_score", 0)
                merged["total_all_attempts"] += progress.get("total_all_attempts", 0)
                merged["challenges_attempted"] += progress.get(
                    "challenges_attempted", 0
                )

        return {
            "available_challenges": available_challenges,
            "player_challenge_progress": player_challenge_progress,
        }

    @staticmethod
    def build_gamification_stats(user_id: int) -> dict[str, Any]:
        """Build gamification stats for dashboard widget."""
        from ..gamification.level_service import LevelService
        from ..gamification.streak_service import StreakService

        try:
            progress = LevelService.get_level_progress(user_id)
            streaks = StreakService.get_all_streaks(user_id)

            return {"progress": progress, "streaks": streaks}
        except Exception:
            return {}
