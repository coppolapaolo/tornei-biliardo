# models/dashboard/services.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Iterable, Tuple
from datetime import date as date_cls

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from models.base import db
from models.campionato.models import Campionato, TournamentDirector
from models.competition.models import Gara, Inscription
from models.match.models import Match as TournamentMatch
from models.user.models import User
from models.status_enum import GaraStatus


# -----------------------
# Helpers
# -----------------------
def _role_truthy(user: User, attr_name: str) -> bool:
    """
    True se l'attributo di ruolo è vero (supporta bool o callable).
    Evita TypeError: 'bool' object is not callable.
    """
    val = getattr(user, attr_name, None)
    if val is None:
        return False
    try:
        return bool(val() if callable(val) else val)
    except TypeError:
        return bool(val)


def _compute_user_stats(user_id: int) -> dict[str, Any]:
    total_matches = (
        db.session.query(TournamentMatch)
        .filter(
            or_(
                TournamentMatch.player1_id == user_id,
                TournamentMatch.player2_id == user_id,
            )
        )
        .count()
    )
    won_matches = (
        db.session.query(TournamentMatch)
        .filter(
            or_(
                TournamentMatch.player1_id == user_id,
                TournamentMatch.player2_id == user_id,
            ),
            TournamentMatch.winner_id == user_id,
        )
        .count()
    )
    win_percentage = (
        round((won_matches / total_matches) * 100, 2) if total_matches else 0.0
    )
    return {
        "total_matches": total_matches,
        "won_matches": won_matches,
        "win_percentage": win_percentage,
    }


# -----------------------
# View-models
# -----------------------
@dataclass
class CapabilityVM:
    can_create_campionato: bool = False
    can_create_standalone: bool = False
    can_register_self: bool = True  # gli admin in genere no


@dataclass
class DashboardVM:
    # comuni
    title: str
    campionati: List[Campionato]
    caps: CapabilityVM

    # selezione
    selected_campionato: Optional[Campionato] = None
    selected_gara: Optional[Gara] = None
    selector_items: Optional[
        List[dict]
    ] = None  # [{"kind":"t"|"p","id":int,"label":str,"selected":bool}]

    # sezioni admin/director
    standalone_garas: Optional[List[Gara]] = None  # standalone che GESTISCO

    # sezioni player-like
    available_garas: Optional[
        List[Gara]
    ] = None  # gare del campionato selezionato con iscrizioni aperte
    standalone_available: Optional[
        List[Gara]
    ] = None  # standalone aperte (come giocatore)
    my_inscriptions: Optional[List[Inscription]] = None
    my_standalone_inscriptions: Optional[List[Inscription]] = None
    current_matches: Optional[List[TournamentMatch]] = None
    recent_matches: Optional[List[TournamentMatch]] = None
    can_inscribe: bool = False

    # extra
    user_stats: Optional[dict[str, Any]] = None
    managed_campionatos: Optional[List[Campionato]] = None
    can_manage_directors: bool = False
    debug_mode: bool = False

    # Individual match proposals
    match_proposals: Optional[
        dict[str, Any]
    ] = None  # {"created": [], "received": [], "available": []}
    individual_matches: Optional[List[Any]] = None  # Recent individual matches
    match_opportunities: Optional[List[Any]] = None  # Available match opportunities


# -----------------------
# Service
# -----------------------
class DashboardService:
    """Orchestratore read-only per le tre dashboard."""

    # ---- query helpers ------------------------------------------------
    @staticmethod
    def _campionatos_q():
        # joinedload per poter calcolare la prima data utile nel selector
        return (
            db.session.query(Campionato)
            .options(joinedload(getattr(Campionato, "provas")))
            .order_by(Campionato.created_at.desc())
        )

    @staticmethod
    def _managed_campionatos_q(user_id: int):
        return (
            db.session.query(Campionato)
            .join(TournamentDirector, TournamentDirector.campionato_id == Campionato.id)
            .filter(TournamentDirector.user_id == user_id)
            .options(joinedload(getattr(Campionato, "provas")))
            .order_by(Campionato.created_at.desc())
        )

    @staticmethod
    def _standalone_q():
        # NIENTE soft-delete su Gara (non previsto ad oggi)
        return (
            db.session.query(Gara)
            .filter(Gara.campionato_id.is_(None))
            .order_by(Gara.date.asc().nullslast(), Gara.name.asc())
        )

    @staticmethod
    def _annotate_garas_with_flags(provas: Optional[List[Gara]]) -> List[Gara]:
        """Arricchisce le Gare per la UI con flag derivati (no logica in Jinja)."""
        if not provas:
            return []
        for p in provas:
            # True se le iscrizioni sono aperte (enum centralizzato)
            p.is_inscription_open = p.get_real_status() == GaraStatus.INSCRIPTION.value
        return provas

    @staticmethod
    def _standalone_available_for_user(
        user_id: int, *, exclude_director_id: Optional[int] = None
    ) -> List[Gara]:
        """
        Standalone disponibili per iscrizione:
        - stato = INSCRIPTION o SETUP (mostra tutte le gare non ancora iniziate)
        - utente NON già iscritto
        - opzionale: escludi quelle gestite da exclude_director_id
            (evita duplicati su director)
        """
        subq_all_my_gara_ids = (
            select(Inscription.gara_id)
            .where(Inscription.user_id == user_id)
            .scalar_subquery()
        )

        q = DashboardService._standalone_q().filter(
            or_(
                Gara.status == GaraStatus.INSCRIPTION.value,
                Gara.status == GaraStatus.SETUP.value
            ),
            ~Gara.id.in_(subq_all_my_gara_ids),
        )

        if exclude_director_id is not None and hasattr(Gara, "director_id"):
            q = q.filter(
                or_(
                    Gara.director_id.is_(None),
                    Gara.director_id != exclude_director_id,
                )
            )

        provas = q.all()
        
        # Aggiungi il campo is_inscription_open (come in _available_garas_for_user)
        for p in provas:
            p.is_inscription_open = p.get_real_status() == GaraStatus.INSCRIPTION.value
        
        return provas

    # ---- selector unico (campionati + standalone) ------------------------
    @staticmethod
    def _build_selector_items(
        campionati: Iterable[Campionato],
        standalones: Iterable[Gara],
        *,
        selected_campionato_id: Optional[int],
        selected_gara_id: Optional[int],
    ) -> List[dict]:
        """
        Lista mista ordinata per data crescente:
        - Campionato: data = min(data delle sue Gare con data non nulla) se disponibile,
            altrimenti None (in coda).
        - Standalone: data = p.date (può essere None).
        """

        def _t_date(t: Campionato) -> Optional[date_cls]:
            # Safely access the provas relationship
            try:
                # Get the provas - either already loaded or load them
                provas_attr = getattr(t, "provas", None)
                if provas_attr is None:
                    return None

                # Convert to list to handle both collections and query objects
                provas_list = (
                    list(provas_attr) if hasattr(provas_attr, "__iter__") else []
                )
                dates = [p.date for p in provas_list if getattr(p, "date", None)]
            except (AttributeError, TypeError):
                # Fallback if relationship access fails
                dates = []
            return min(dates) if dates else None

        items: List[Tuple[Optional[date_cls], dict]] = []

        for t in campionati:
            items.append(
                (
                    _t_date(t),
                    {
                        "kind": "t",
                        "id": t.id,
                        "label": t.name,
                        "selected": (
                            selected_campionato_id == t.id and selected_gara_id is None
                        ),
                    },
                )
            )

        for p in standalones:
            items.append(
                (
                    getattr(p, "date", None),
                    {
                        "kind": "p",
                        "id": p.id,
                        "label": p.name,
                        "selected": (selected_gara_id == p.id),
                    },
                )
            )

        # ordina per data (None alla fine)
        items.sort(key=lambda tup: (tup[0] is None, tup[0]))
        return [d for _, d in items]

    @staticmethod
    def _caps_for(user: User) -> CapabilityVM:
        is_admin = _role_truthy(user, "is_admin")
        is_director = _role_truthy(user, "is_director")
        return CapabilityVM(
            can_create_campionato=is_admin or is_director,
            can_create_standalone=is_admin or is_director,
            can_register_self=not is_admin,
        )

    # ---- sezioni "player-like" riusabili ------------------------------
    @staticmethod
    def _build_player_sections(user_id: int, selected: Optional[Campionato]) -> dict:
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

        my_upcoming = (
            db.session.query(TournamentMatch)
            .join(Gara, Gara.id == TournamentMatch.gara_id)
            .filter(
                Gara.campionato_id == selected.id,
                TournamentMatch.status == "playing",  # type: ignore[operator]
                or_(
                    TournamentMatch.player1_id == user_id,
                    TournamentMatch.player2_id == user_id,
                ),
            )
            .order_by(
                TournamentMatch.created_at.desc().nullslast(), TournamentMatch.id.desc()
            )
            .all()
        )

        my_recent = (
            db.session.query(TournamentMatch)
            .join(Gara, Gara.id == TournamentMatch.gara_id)
            .filter(
                Gara.campionato_id == selected.id,
                TournamentMatch.status == "completed",  # type: ignore[operator]
                or_(
                    TournamentMatch.player1_id == user_id,
                    TournamentMatch.player2_id == user_id,
                ),
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
    def _build_individual_match_sections(user_id: int) -> dict:
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

        # Calculate match opportunities (open proposals in user's locations)
        from ..individual_match.models import PlayerAvailability

        user_locations = {
            av.location
            for av in db.session.query(PlayerAvailability)
            .filter_by(user_id=user_id, is_available=True)
            .all()
        }

        # Also include locations where user has played before
        played_locations = {match.location for match in recent_individual_matches}

        user_locations.union(played_locations)

        # Get opportunities - open proposals in eligible locations
        opportunities = proposals.get("available", [])

        return {
            "match_proposals": proposals,
            "individual_matches": recent_individual_matches,
            "match_opportunities": opportunities[:5],  # Limit to top 5 opportunities
        }

    # ---- ADMIN --------------------------------------------------------
    @staticmethod
    def for_admin() -> DashboardVM:
        campionati = DashboardService._campionatos_q().all()
        standalone = DashboardService._annotate_garas_with_flags(
            DashboardService._standalone_q().all()
        )
        caps = CapabilityVM(
            can_create_campionato=True,
            can_create_standalone=True,
            can_register_self=False,
        )

        # Note: Admin dashboard doesn't include individual match proposals
        # as it's focused on campionato/gara management

        return DashboardVM(
            title="Dashboard Amministratore",
            campionati=campionati,
            selected_campionato=None,
            selected_gara=None,
            selector_items=DashboardService._build_selector_items(
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
            individual_matches=None,
            match_opportunities=None,
        )

    # ---- DIRECTOR -----------------------------------------------------
    @staticmethod
    def for_director(
        user_id: int,
        selected_campionato_id: Optional[int] = None,
        selected_gara_id: Optional[int] = None,
    ) -> DashboardVM:
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("Utente non trovato")

        caps = DashboardService._caps_for(user)

        managed = DashboardService._managed_campionatos_q(user_id).all()
        campionati = DashboardService._campionatos_q().all()
        standalones_all: List[Gara] = DashboardService._standalone_q().all()
        has_director = hasattr(Gara, "director_id")

        # campionato selezionato: esplicito -> primo gestito -> primo globale
        selected = (
            db.session.get(Campionato, selected_campionato_id)
            if selected_campionato_id
            else None
        )
        if not selected and managed:
            selected = managed[0]
        if not selected:
            selected = campionati[0] if campionati else None

        # Gara standalone selezionata (solo se davvero standalone)
        selected_gara = (
            db.session.get(Gara, selected_gara_id) if selected_gara_id else None
        )
        if selected_gara and selected_gara.campionato_id is not None:
            selected_gara = None

        # sezioni player-like per campionato selezionato
        player_sections = DashboardService._build_player_sections(user_id, selected)

        # Individual match sections
        individual_sections = DashboardService._build_individual_match_sections(user_id)

        # standalone disponibili (come player) evitando duplicati con le "owned"
        standalone_available = DashboardService._standalone_available_for_user(
            user_id, exclude_director_id=user_id
        )

        # mie iscrizioni a standalone
        my_standalone_regs = (
            db.session.query(Inscription)
            .join(Gara, Gara.id == Inscription.gara_id)
            .filter(Inscription.user_id == user_id, Gara.campionato_id.is_(None))
            .options(joinedload(Inscription.gara))
            .order_by(Gara.date.desc().nullslast())
            .all()
        )

        # standalone gestite
        standalone_owned: List[Gara] = [
            p for p in standalones_all if has_director and p.director_id == user_id
        ]
        standalone_owned = DashboardService._annotate_garas_with_flags(
            standalone_owned
        )

        # permesso gestione director nel campionato selezionato
        can_manage_directors = False
        if selected:
            can_manage_directors = _role_truthy(user, "is_admin") or (
                db.session.query(TournamentDirector)
                .filter_by(user_id=user_id, campionato_id=selected.id)
                .first()
                is not None
            )

        return DashboardVM(
            title="Dashboard Direttore",
            campionati=campionati,
            selected_campionato=selected,
            selected_gara=selected_gara,
            selector_items=DashboardService._build_selector_items(
                campionati=campionati,
                standalones=standalones_all,
                selected_campionato_id=selected.id if selected else None,
                selected_gara_id=selected_gara.id if selected_gara else None,
            ),
            standalone_garas=standalone_owned,
            available_garas=player_sections["available_garas"],
            standalone_available=standalone_available,
            my_inscriptions=player_sections["my_inscriptions"],
            my_standalone_inscriptions=my_standalone_regs,
            current_matches=player_sections["current_matches"],
            recent_matches=player_sections["recent_matches"],
            can_inscribe=not _role_truthy(user, "is_admin"),
            user_stats=_compute_user_stats(user_id),
            managed_campionatos=managed,
            can_manage_directors=can_manage_directors,
            caps=caps,
            match_proposals=individual_sections["match_proposals"],
            individual_matches=individual_sections["individual_matches"],
            match_opportunities=individual_sections["match_opportunities"],
        )

    # ---- PLAYER -------------------------------------------------------
    @staticmethod
    def for_player(
        user_id: int,
        selected_campionato_id: Optional[int] = None,
        selected_gara_id: Optional[int] = None,
    ) -> DashboardVM:
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("Utente non trovato")

        caps = DashboardService._caps_for(user)

        campionati = DashboardService._campionatos_q().all()
        standalones_all: List[Gara] = DashboardService._standalone_q().all()

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

        player_sections = DashboardService._build_player_sections(user_id, selected)

        # Individual match sections
        individual_sections = DashboardService._build_individual_match_sections(user_id)

        standalone_available = DashboardService._standalone_available_for_user(user_id)

        my_standalone_regs = (
            db.session.query(Inscription)
            .join(Gara, Gara.id == Inscription.gara_id)
            .filter(Inscription.user_id == user_id, Gara.campionato_id.is_(None))
            .options(joinedload(Inscription.gara))
            .order_by(Gara.date.desc().nullslast())
            .all()
        )

        return DashboardVM(
            title="Dashboard Giocatore",
            campionati=campionati,
            selected_campionato=selected,
            selected_gara=selected_gara,
            selector_items=DashboardService._build_selector_items(
                campionati=campionati,
                standalones=standalones_all,
                selected_campionato_id=selected.id if selected else None,
                selected_gara_id=selected_gara.id if selected_gara else None,
            ),
            standalone_garas=None,  # non usata su player
            available_garas=player_sections["available_garas"],
            standalone_available=standalone_available,
            my_inscriptions=player_sections["my_inscriptions"],
            my_standalone_inscriptions=my_standalone_regs,
            current_matches=player_sections["current_matches"],
            recent_matches=player_sections["recent_matches"],
            can_inscribe=True,  # i player possono iscriversi
            user_stats=_compute_user_stats(user_id),
            managed_campionatos=None,
            can_manage_directors=False,
            caps=caps,
            match_proposals=individual_sections["match_proposals"],
            individual_matches=individual_sections["individual_matches"],
            match_opportunities=individual_sections["match_opportunities"],
        )
