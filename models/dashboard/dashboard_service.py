# models/dashboard/dashboard_service.py
"""DashboardService: Role-specific facades.

Query builders extracted to query_builders.py.
Item builders extracted to item_builders.py (with N+1 fix for DirectorAssignment).
"""

from __future__ import annotations

from typing import List, Optional

from flask_babel import gettext as _
from sqlalchemy.orm import joinedload

from models.base import db
from models.user.role_enum import UserRole
from models.campionato.models import Campionato
from models.user.models import DirectorAssignment
from models.competition.models import Gara, Inscription
from models.match.models import Match as TournamentMatch
from models.user.models import User
from models.status_enum import GaraStatus, MatchStatus

from .activity_feedback import ActivityFeedbackService, has_any_activity
from .gara_cards import build_gara_cards, enrich_with_progress
from .view_models import (
    _role_truthy,
    _user_is_match_participant,
    _compute_user_stats,
    CapabilityVM,
    DashboardVM,
)
from .section_builders import DashboardSectionBuilder
from .query_builders import (
    campionatos_q,
    managed_campionatos_q,
    standalone_q,
    annotate_garas_with_flags,
    standalone_available_for_user,
)
from .item_builders import (
    build_unified_items,
    build_selector_items,
    caps_for,
)
from models.status_enum import TournamentStatus


def _needs_setup_card(user_id: int, user) -> bool:
    """La card dei tre passi va solo a chi non ha ancora fatto niente."""
    return not has_any_activity(user_id, user)


# How many completed campionati to show in player/director dashboards.
# Older completed campionati are accessible via /campionatos archive page.
DASHBOARD_COMPLETED_LIMIT = 2

# How many completed standalone gare to surface as "recent tail" in the
# Gare section. Older completed gare live behind /garas archive.
DASHBOARD_STANDALONE_COMPLETED_LIMIT = 2

_TERMINAL_TOURNAMENT_STATUSES = frozenset(
    {
        TournamentStatus.COMPLETED.value,
        TournamentStatus.AWAITING_PLAYOFF.value,
    }
)


def _partition_campionato_items(unified_items):
    """Split unified_items into (active_items, completed_shown, completed_total).

    Operates on UnifiedDashboardItem so the template keeps access to
    can_manage / can_view_details / next_prova_date computed by
    build_unified_items. Order is preserved.
    """
    active: list = []
    completed: list = []
    for it in unified_items:
        if it.type != "campionato":
            continue
        if it.entity.get_status() in _TERMINAL_TOURNAMENT_STATUSES:
            completed.append(it)
        else:
            active.append(it)
    return active, completed[:DASHBOARD_COMPLETED_LIMIT], len(completed)


def _standalone_completed_tail(standalones):
    """Estrae le gare standalone COMPLETED come coda recente.

    Ordina per data decrescente (più recenti prima), date NULL in fondo,
    poi applica il cap. `standalones` arriva da `standalone_q` (date asc
    nulls last), qui ribaltiamo per la sezione "coda recente".
    """
    from datetime import date as _date_cls

    completed = [g for g in standalones if g.status == GaraStatus.COMPLETED.value]
    completed.sort(
        key=lambda g: g.date or _date_cls.min,
        reverse=True,
    )
    return (
        completed[:DASHBOARD_STANDALONE_COMPLETED_LIMIT],
        len(completed),
    )


class DashboardService:
    """Orchestratore read-only per le dashboard (admin, director, player, guest)."""

    # Backward-compatible static method aliases
    _campionatos_q = staticmethod(campionatos_q)
    _managed_campionatos_q = staticmethod(managed_campionatos_q)
    _standalone_q = staticmethod(standalone_q)
    _annotate_garas_with_flags = staticmethod(annotate_garas_with_flags)
    _standalone_available_for_user = staticmethod(standalone_available_for_user)
    _build_unified_items = staticmethod(build_unified_items)
    _build_selector_items = staticmethod(build_selector_items)
    _caps_for = staticmethod(caps_for)

    # ---- ADMIN --------------------------------------------------------
    @staticmethod
    def for_admin() -> DashboardVM:
        campionati = campionatos_q().all()
        standalone = annotate_garas_with_flags(standalone_q().all())
        caps = CapabilityVM(
            can_create_campionato=True,
            can_create_standalone=True,
            can_register_self=False,
            can_create_match_proposal=False,
        )

        unified_items = build_unified_items(
            campionati, standalone, user_role="admin", user_id=None
        )

        return DashboardVM(
            title=_("Dashboard Amministratore"),
            campionati=campionati,
            unified_items=unified_items,
            selected_campionato=None,
            selected_gara=None,
            selector_items=build_selector_items(
                campionati=campionati,
                standalones=standalone,
                selected_campionato_id=None,
                selected_gara_id=None,
            ),
            standalone_garas=standalone,
            available_garas=None,
            standalone_available=None,
            my_inscriptions=None,
            my_standalone_inscriptions=None,
            current_matches=None,
            recent_matches=None,
            can_inscribe=False,
            user_stats=None,
            managed_campionatos=None,
            can_manage_directors=True,
            caps=caps,
            debug_mode=False,
            match_proposals=None,
            sfide_in_corso=None,
            match_opportunities=None,
        )

    # ---- DIRECTOR -----------------------------------------------------
    @staticmethod
    def for_director(
        user_id: int,
        selected_campionato_id: Optional[int] = None,
        selected_gara_id: Optional[int] = None,
        with_activity_feedback: bool = True,
    ) -> DashboardVM:
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("Utente non trovato")

        caps = caps_for(user)

        managed = managed_campionatos_q(user_id).all()
        campionati = campionatos_q().all()
        standalones_all: List[Gara] = standalone_q().all()
        has_director = hasattr(Gara, "director_id")

        selected = (
            db.session.get(Campionato, selected_campionato_id)
            if selected_campionato_id
            else None
        )
        if not selected and managed:
            selected = managed[0]
        if not selected:
            selected = campionati[0] if campionati else None

        selected_gara = (
            db.session.get(Gara, selected_gara_id) if selected_gara_id else None
        )
        if selected_gara and selected_gara.campionato_id is not None:
            selected_gara = None

        player_sections = DashboardSectionBuilder.build_player_sections(
            user_id, selected
        )

        all_current_matches = (
            db.session.query(TournamentMatch)
            .join(Gara, Gara.id == TournamentMatch.gara_id)
            .filter(
                TournamentMatch.status.in_(  # type: ignore[attr-defined]
                    [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
                ),
                _user_is_match_participant(user_id),
            )
            .order_by(
                TournamentMatch.created_at.desc().nullslast(),
                TournamentMatch.id.desc(),
            )
            .limit(10)
            .all()
        )

        individual_sections = DashboardSectionBuilder.build_individual_match_sections(
            user_id
        )

        sa_available = standalone_available_for_user(
            user_id, exclude_director_id=user_id
        )

        my_standalone_regs = (
            db.session.query(Inscription)
            .join(Gara, Gara.id == Inscription.gara_id)
            .filter(Inscription.user_id == user_id, Gara.campionato_id.is_(None))
            .options(joinedload(Inscription.gara))
            .order_by(Gara.date.desc().nullslast())
            .all()
        )

        all_my_inscriptions = (
            db.session.query(Inscription)
            .join(Gara, Gara.id == Inscription.gara_id)
            .filter(Inscription.user_id == user_id)
            .options(joinedload(Inscription.gara))
            .order_by(Gara.date.asc().nullslast())
            .all()
        )

        standalone_owned: List[Gara] = []
        if has_director:
            # Batch-load gara-level assignments for this director
            co_directed_gara_ids = {
                a.entity_id
                for a in db.session.query(DirectorAssignment)
                .filter(
                    DirectorAssignment.entity_type == "gara",
                    DirectorAssignment.user_id == user_id,
                )
                .all()
            }
            for gara in standalones_all:
                if gara.director_id == user_id or gara.id in co_directed_gara_ids:
                    standalone_owned.append(gara)
        standalone_owned = annotate_garas_with_flags(standalone_owned)

        can_manage_directors = False
        if selected:
            can_manage_directors = _role_truthy(user, "is_admin") or (
                db.session.query(DirectorAssignment)
                .filter(
                    DirectorAssignment.entity_type == "campionato",
                    DirectorAssignment.entity_id == selected.id,
                    DirectorAssignment.user_id == user_id,
                )
                .first()
                is not None
            )

        unified_items = build_unified_items(
            campionati, standalones_all, user_role="director", user_id=user_id
        )

        active_items, completed_shown_items, completed_total = (
            _partition_campionato_items(unified_items)
        )

        standalone_completed_recent, standalone_completed_total = (
            _standalone_completed_tail(standalones_all)
        )

        # Le gare divise fra «le tue» e «aperte»: la divisione e' una regola
        # di dominio (chi vede cosa) e sta in `gara_cards`, non in Jinja.
        # Tutti e tre gli argomenti sono gia' in memoria: nessuna query nuova.
        gare_mie, gare_aperte, gare_concluse_total = build_gara_cards(
            unified_items,
            all_my_inscriptions,
            all_current_matches,
            can_inscribe=not _role_truthy(user, "is_admin"),
        )
        # «Come sta andando»: posizione provvisoria e partite del turno. Sta
        # in una chiamata a parte perche' e' l'unica che tocca il database.
        enrich_with_progress(gare_mie, user_id)

        # Il blocco di feedback vale anche qui: chi ha il ruolo di direttore
        # non passa mai da `dashboard/player.html` (la rotta smista per ruolo
        # piu' alto), quindi la variante «Come vanno le tue gare» del design
        # senza questa riga non si vedrebbe da nessuna parte.
        director_feedback = (
            ActivityFeedbackService.for_player(user_id, user=user)
            if with_activity_feedback
            else None
        )

        return DashboardVM(
            title=_("Dashboard Direttore"),
            activity_feedback=director_feedback,
            activity_setup=(
                ActivityFeedbackService.setup_card(user_id, user=user)
                if with_activity_feedback and _needs_setup_card(user_id, user)
                else None
            ),
            campionati=campionati,
            campionati_active_items=active_items,
            campionati_completed_shown_items=completed_shown_items,
            campionati_completed_total=completed_total,
            standalone_completed_recent=standalone_completed_recent,
            standalone_completed_total=standalone_completed_total,
            gare_mie=gare_mie,
            gare_aperte=gare_aperte,
            gare_concluse_total=gare_concluse_total,
            unified_items=unified_items,
            selected_campionato=selected,
            selected_gara=selected_gara,
            selector_items=build_selector_items(
                campionati=campionati,
                standalones=standalones_all,
                selected_campionato_id=selected.id if selected else None,
                selected_gara_id=selected_gara.id if selected_gara else None,
            ),
            standalone_garas=standalone_owned,
            available_garas=player_sections["available_garas"],
            standalone_available=sa_available,
            my_inscriptions=all_my_inscriptions,
            my_standalone_inscriptions=my_standalone_regs,
            current_matches=all_current_matches,
            recent_matches=player_sections["recent_matches"],
            can_inscribe=not _role_truthy(user, "is_admin"),
            user_stats=_compute_user_stats(user_id),
            managed_campionatos=managed,
            can_manage_directors=can_manage_directors,
            caps=caps,
            match_proposals=individual_sections["match_proposals"],
            sfide_in_corso=individual_sections["sfide_in_corso"],
            match_opportunities=individual_sections["match_opportunities"],
            playoff_invitations=DashboardSectionBuilder.build_playoff_invitations(
                user_id
            ),
            bye_challenges=DashboardSectionBuilder.build_bye_challenges(user_id),
            gamification_stats=DashboardSectionBuilder.build_gamification_stats(
                user_id
            ),
        )

    # ---- PLAYER -------------------------------------------------------
    @staticmethod
    def for_player(
        user_id: int,
        selected_campionato_id: Optional[int] = None,
        selected_gara_id: Optional[int] = None,
        with_activity_feedback: bool = True,
    ) -> DashboardVM:
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("Utente non trovato")

        caps = caps_for(user)

        campionati = campionatos_q().all()
        standalones_all: List[Gara] = standalone_q().all()

        selected = (
            db.session.get(Campionato, selected_campionato_id)
            if selected_campionato_id
            else None
        )
        if not selected:
            selected = campionati[0] if campionati else None

        selected_gara = (
            db.session.get(Gara, selected_gara_id) if selected_gara_id else None
        )
        if selected_gara and selected_gara.campionato_id is not None:
            selected_gara = None

        player_sections = DashboardSectionBuilder.build_player_sections(
            user_id, selected
        )

        all_current_matches = (
            db.session.query(TournamentMatch)
            .join(Gara, Gara.id == TournamentMatch.gara_id)
            .filter(
                TournamentMatch.status.in_(  # type: ignore[attr-defined]
                    [MatchStatus.PENDING.value, MatchStatus.PLAYING.value]
                ),
                _user_is_match_participant(user_id),
            )
            .order_by(
                TournamentMatch.created_at.desc().nullslast(),
                TournamentMatch.id.desc(),
            )
            .limit(10)
            .all()
        )

        individual_sections = DashboardSectionBuilder.build_individual_match_sections(
            user_id
        )

        sa_available = standalone_available_for_user(user_id)

        my_standalone_regs = (
            db.session.query(Inscription)
            .join(Gara, Gara.id == Inscription.gara_id)
            .filter(Inscription.user_id == user_id, Gara.campionato_id.is_(None))
            .options(joinedload(Inscription.gara))
            .order_by(Gara.date.desc().nullslast())
            .all()
        )

        all_my_inscriptions = (
            db.session.query(Inscription)
            .join(Gara, Gara.id == Inscription.gara_id)
            .filter(Inscription.user_id == user_id)
            .options(joinedload(Inscription.gara))
            .order_by(Gara.date.asc().nullslast())
            .all()
        )

        challenge_sections = DashboardSectionBuilder.build_challenge_sections(
            user_id, selected
        )

        # Riusa standalones_all (riga ~332): standalone_q() e' deterministica
        # (filtro/ordine fissi) ed eseguita sulla stessa session nello stesso
        # request, quindi un secondo .all() restituirebbe dati identici.
        all_standalone_garas = standalones_all
        unified_items = build_unified_items(
            campionati, all_standalone_garas, user_role="player", user_id=user_id
        )

        active_items, completed_shown_items, completed_total = (
            _partition_campionato_items(unified_items)
        )

        standalone_completed_recent, standalone_completed_total = (
            _standalone_completed_tail(all_standalone_garas)
        )

        # Le gare divise fra «le tue» e «aperte»: la divisione e' una regola
        # di dominio (chi vede cosa) e sta in `gara_cards`, non in Jinja.
        # Tutti e tre gli argomenti sono gia' in memoria: nessuna query nuova.
        gare_mie, gare_aperte, gare_concluse_total = build_gara_cards(
            unified_items,
            all_my_inscriptions,
            all_current_matches,
            can_inscribe=not _role_truthy(user, "is_admin"),
        )
        # «Come sta andando»: posizione provvisoria e partite del turno. Sta
        # in una chiamata a parte perche' e' l'unica che tocca il database.
        enrich_with_progress(gare_mie, user_id)

        # Il blocco si mostra una volta per sessione: quando il turno e' gia'
        # stato consumato non lo si calcola nemmeno — sarebbero cinque query
        # per qualcosa che non finisce in pagina.
        activity_feedback = (
            ActivityFeedbackService.for_player(user_id, user=user)
            if with_activity_feedback
            else None
        )

        return DashboardVM(
            title=_("Dashboard Giocatore"),
            activity_feedback=activity_feedback,
            activity_setup=(
                # Stesso turno del blocco: la card di setup ne e' la variante
                # per chi non ha ancora fatto niente, occupa lo stesso posto e
                # sparisce insieme a lui. Chi rientra in dashboard dieci volte
                # non ha bisogno di rileggere dieci volte i tre passi.
                ActivityFeedbackService.setup_card(user_id, user=user)
                if with_activity_feedback and _needs_setup_card(user_id, user)
                else None
            ),
            campionati=campionati,
            campionati_active_items=active_items,
            campionati_completed_shown_items=completed_shown_items,
            campionati_completed_total=completed_total,
            standalone_completed_recent=standalone_completed_recent,
            standalone_completed_total=standalone_completed_total,
            gare_mie=gare_mie,
            gare_aperte=gare_aperte,
            gare_concluse_total=gare_concluse_total,
            unified_items=unified_items,
            selected_campionato=selected,
            selected_gara=selected_gara,
            selector_items=build_selector_items(
                campionati=campionati,
                standalones=standalones_all,
                selected_campionato_id=selected.id if selected else None,
                selected_gara_id=selected_gara.id if selected_gara else None,
            ),
            standalone_garas=None,
            available_garas=player_sections["available_garas"],
            standalone_available=sa_available,
            my_inscriptions=all_my_inscriptions,
            my_standalone_inscriptions=my_standalone_regs,
            current_matches=all_current_matches,
            recent_matches=player_sections["recent_matches"],
            can_inscribe=True,
            user_stats=_compute_user_stats(user_id),
            managed_campionatos=None,
            can_manage_directors=False,
            caps=caps,
            match_proposals=individual_sections["match_proposals"],
            sfide_in_corso=individual_sections["sfide_in_corso"],
            match_opportunities=individual_sections["match_opportunities"],
            playoff_invitations=DashboardSectionBuilder.build_playoff_invitations(
                user_id
            ),
            bye_challenges=DashboardSectionBuilder.build_bye_challenges(user_id),
            available_challenges=challenge_sections["available_challenges"],
            player_challenge_progress=challenge_sections["player_challenge_progress"],
            gamification_stats=DashboardSectionBuilder.build_gamification_stats(
                user_id
            ),
        )

    @staticmethod
    def for_guest() -> DashboardVM:
        """Dashboard view model for guest (non-authenticated) users."""
        campionati = campionatos_q().all()

        standalone_garas = (
            Gara.query.filter_by(campionato_id=None)
            .filter(Gara.status != GaraStatus.SETUP.value)
            .order_by(Gara.date.desc())
            .all()
        )

        unified_items = build_unified_items(
            campionati, standalone_garas, user_role=UserRole.GUEST.value, user_id=None
        )

        guest_caps = CapabilityVM(
            can_create_campionato=False,
            can_create_standalone=False,
            can_register_self=False,
            can_create_match_proposal=False,
        )

        return DashboardVM(
            title=_("Vista Pubblica"),
            campionati=campionati,
            unified_items=unified_items,
            selected_campionato=None,
            selected_gara=None,
            selector_items=[],
            standalone_garas=standalone_garas,
            available_garas=[],
            standalone_available=[],
            my_inscriptions=[],
            my_standalone_inscriptions=[],
            current_matches=[],
            recent_matches=[],
            can_inscribe=False,
            user_stats=None,
            managed_campionatos=None,
            can_manage_directors=False,
            caps=guest_caps,
            match_proposals=None,
            sfide_in_corso=None,
            match_opportunities=None,
            available_challenges=None,
            player_challenge_progress=None,
        )
