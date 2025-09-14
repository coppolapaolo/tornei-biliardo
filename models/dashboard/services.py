# models/dashboard/services.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Iterable, Tuple
from datetime import date as date_cls

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from models.base import db
from models.campionato.models import Campionato
from models.user.models import DirectorAssignment
from models.competition.models import Gara, Inscription
from models.match.models import Match as TournamentMatch
from models.user.models import User
from models.status_enum import GaraStatus, MatchStatus


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
    can_create_match_proposal: bool = False


@dataclass
class UnifiedDashboardItem:
    """Elemento unificato per dashboard (campionato o gara)"""

    type: str  # 'campionato' o 'gara'
    id: int
    name: str
    entity: Any  # Campionato o Gara
    next_prova_date: Optional[date_cls] = None
    sort_key: str = ""  # Per ordinamento alfabetico se no date
    can_manage: bool = False  # Se l'utente può gestire questo elemento
    can_view_details: bool = True  # Se l'utente può vedere i dettagli


@dataclass
class DashboardVM:
    # comuni
    title: str
    campionati: List[Campionato]
    caps: CapabilityVM

    # NUOVO: elementi unificati ordinati per data
    unified_items: Optional[List[UnifiedDashboardItem]] = None

    # selezione
    selected_campionato: Optional[Campionato] = None
    selected_gara: Optional[Gara] = None
    selector_items: Optional[List[dict]] = (
        None  # [{"kind":"t"|"p","id":int,"label":str,"selected":bool}]
    )

    # sezioni admin/director (DEPRECATE - mantenute per compatibilità)
    standalone_garas: Optional[List[Gara]] = None  # standalone che GESTISCO

    # sezioni player-like
    available_garas: Optional[List[Gara]] = (
        None  # gare del campionato selezionato con iscrizioni aperte
    )
    standalone_available: Optional[List[Gara]] = (
        None  # standalone aperte (come giocatore)
    )
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
    match_proposals: Optional[dict[str, Any]] = (
        None  # {"created": [], "received": [], "available": []}
    )
    individual_matches: Optional[List[Any]] = None  # Recent individual matches
    match_opportunities: Optional[List[Any]] = None  # Available match opportunities

    # Challenge system
    available_challenges: Optional[List[Any]] = (
        None  # Available challenges for the player
    )
    player_challenge_progress: Optional[dict[str, Any]] = (
        None  # Player progress on challenges
    )


# -----------------------
# Service
# -----------------------
class DashboardService:
    """Orchestratore read-only per le tre dashboard."""

    # ---- query helpers ------------------------------------------------
    @staticmethod
    def _build_unified_items(
        campionati: List[Campionato],
        standalone_garas: List[Gara],
        user_role: str = "player",  # 'admin', 'director', 'player'
        user_id: Optional[int] = None,
    ) -> List[UnifiedDashboardItem]:
        """
        Crea lista unificata di campionati e gare standalone ordinata per data prossima prova.

        user_role determina quale tipo di elementi includere:
        - admin: tutti i campionati + tutte le standalone
        - director: campionati gestiti + standalone gestite + standalone disponibili
        - player: tutti i campionati + standalone disponibili
        """
        items = []

        # Aggiungi campionati
        for campionato in campionati:
            # Calcola la prossima data per i campionati
            next_date = None
            try:
                gare_list = (
                    list(campionato.gare.all()) if hasattr(campionato, "gare") else []
                )
                future_dates = [
                    p.date
                    for p in gare_list
                    if getattr(p, "date", None) and p.date >= date_cls.today()
                ]
                next_date = min(future_dates) if future_dates else None
            except (AttributeError, TypeError):
                next_date = None

            # Calcola permessi per campionato
            can_manage = False
            can_view_details = True

            if user_role == "admin":
                can_manage = True
            elif user_role == "director" and user_id:
                # Director può gestire se è co-direttore
                is_co_director = (
                    db.session.query(DirectorAssignment)
                    .filter(
                        DirectorAssignment.entity_type == "campionato",
                        DirectorAssignment.entity_id == campionato.id,
                        DirectorAssignment.user_id == user_id,
                    )
                    .first()
                    is not None
                )

                can_manage = is_co_director
                can_view_details = (
                    is_co_director  # Director può vedere dettagli solo se può gestire
                )
            elif user_role == "player":
                can_view_details = False  # Player non può vedere dettagli di gestione

            items.append(
                UnifiedDashboardItem(
                    type="campionato",
                    id=campionato.id,
                    name=campionato.name,
                    entity=campionato,
                    next_prova_date=next_date,
                    sort_key=campionato.name.lower(),
                    can_manage=can_manage,
                    can_view_details=can_view_details,
                )
            )

        # Aggiungi gare standalone
        for gara in standalone_garas:
            gara_name = gara.name or f'Gara {gara.number or ""}'

            # Calcola permessi per gara
            can_manage = False
            can_view_details = True

            if user_role == "admin":
                can_manage = True
            elif user_role == "director" and user_id:
                # Director può gestire se è direttore principale O co-direttore
                is_main_director = (
                    hasattr(gara, "director_id") and gara.director_id == user_id
                )
                is_co_director = (
                    db.session.query(DirectorAssignment)
                    .filter(
                        DirectorAssignment.entity_type == "gara",
                        DirectorAssignment.entity_id == gara.id,
                        DirectorAssignment.user_id == user_id,
                    )
                    .first()
                    is not None
                )

                can_manage = is_main_director or is_co_director
                can_view_details = (
                    True  # Director può sempre vedere tutte le gare standalone
                )
            elif user_role == "player":
                can_view_details = (
                    True  # Player può vedere gare standalone per iscriversi
                )

            items.append(
                UnifiedDashboardItem(
                    type="gara",
                    id=gara.id,
                    name=gara_name,
                    entity=gara,
                    next_prova_date=getattr(gara, "date", None),
                    sort_key=gara_name.lower(),
                    can_manage=can_manage,
                    can_view_details=can_view_details,
                )
            )

        # Ordina: prima per data (None alla fine), poi alfabetico
        items.sort(
            key=lambda x: (
                x.next_prova_date is None,  # None alla fine
                x.next_prova_date or date_cls.max,  # Per ordinamento date
                x.sort_key,  # Alfabetico per elementi senza data
            )
        )

        return items

    @staticmethod
    def _campionatos_q():
        # joinedload per poter calcolare la prima data utile nel selector
        return (
            db.session.query(Campionato)
            .options(joinedload(getattr(Campionato, "gare")))
            .order_by(Campionato.created_at.desc())
        )

    @staticmethod
    def _managed_campionatos_q(user_id: int):
        return (
            db.session.query(Campionato)
            .join(
                DirectorAssignment,
                (DirectorAssignment.entity_type == "campionato")
                & (DirectorAssignment.entity_id == Campionato.id)
                & (DirectorAssignment.user_id == user_id),
            )
            .options(joinedload(getattr(Campionato, "gare")))
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
                Gara.status == GaraStatus.SETUP.value,
            ),
            ~Gara.id.in_(subq_all_my_gara_ids),
        )

        if exclude_director_id is not None and hasattr(Gara, "director_id"):
            # Escludi gare dove l'utente è direttore principale
            q = q.filter(
                or_(
                    Gara.director_id.is_(None),
                    Gara.director_id != exclude_director_id,
                )
            )

            # Escludi anche gare dove l'utente è co-direttore
            co_director_gara_ids = (
                db.session.query(DirectorAssignment.entity_id)
                .filter(
                    DirectorAssignment.entity_type == "gara",
                    DirectorAssignment.user_id == exclude_director_id,
                )
                .scalar_subquery()
            )
            q = q.filter(~Gara.id.in_(co_director_gara_ids))

        gare = q.all()

        # Aggiungi il campo is_inscription_open (come in _available_garas_for_user)
        for p in gare:
            p.is_inscription_open = p.get_real_status() == GaraStatus.INSCRIPTION.value

        return gare

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
            # Safely access the gare relationship
            try:
                # Get the gare - either already loaded or load them
                gare_attr = getattr(t, "gare", None)
                if gare_attr is None:
                    return None

                # Convert to list to handle both collections and query objects
                gare_list = list(gare_attr) if hasattr(gare_attr, "__iter__") else []
                dates = [p.date for p in gare_list if getattr(p, "date", None)]
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
        is_player = _role_truthy(user, "is_player")
        return CapabilityVM(
            can_create_campionato=is_admin or is_director,
            can_create_standalone=is_admin or is_director,
            can_register_self=not is_admin,
            can_create_match_proposal=is_player and not is_admin,
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

        # DEBUG: Controlla TUTTI i match dell'utente per debug
        all_user_matches = (
            db.session.query(TournamentMatch)
            .join(Gara, Gara.id == TournamentMatch.gara_id)
            .filter(
                or_(
                    TournamentMatch.player1_id == user_id,
                    TournamentMatch.player2_id == user_id,
                ),
            )
            .all()
        )

        # Partite attive (in corso + recenti completate)
        my_upcoming = (
            db.session.query(TournamentMatch)
            .join(Gara, Gara.id == TournamentMatch.gara_id)
            .filter(
                TournamentMatch.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value, MatchStatus.COMPLETED.value]),  # type: ignore[attr-defined]
                or_(
                    TournamentMatch.player1_id == user_id,
                    TournamentMatch.player2_id == user_id,
                ),
            )
            .order_by(
                TournamentMatch.created_at.desc().nullslast(), TournamentMatch.id.desc()
            )
            .limit(10)  # Limita per non mostrare troppe partite vecchie
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

    @staticmethod
    def _build_challenge_sections(
        user_id: int, selected_campionato: Optional[Campionato]
    ) -> dict:
        """Build challenge sections for user."""
        from ..challenge.gara_challenge_service import GaraChallengeService
        from ..challenge.gara_challenge_models import GaraChallenge
        
        available_challenges = []
        player_challenge_progress = {}
        
        # Get all garas where the user is inscribed (both campionato and standalone)
        inscribed_garas = (
            db.session.query(Gara)
            .join(Inscription, Inscription.gara_id == Gara.id)
            .filter(
                Inscription.user_id == user_id,
                Inscription.is_withdrawn == False,
            )
            .all()
        )
        
        # If we have a selected campionato, prioritize its garas
        if selected_campionato:
            campionato_garas = [gara for gara in inscribed_garas if gara.campionato_id == selected_campionato.id]
            # If user is inscribed in campionato garas, use those; otherwise use all inscribed garas
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
                    GaraChallenge.is_active == True,
                )
                .options(joinedload(GaraChallenge.challenge))  # type: ignore[arg-type]
                .all()
            )
            available_challenges.extend(gara_challenges)
            
            # Get player progress for this gara
            progress = GaraChallengeService.get_user_gara_challenge_progress(
                gara.id, user_id
            )
            if progress:
                player_challenge_progress[user_id] = progress

        return {
            "available_challenges": available_challenges,
            "player_challenge_progress": player_challenge_progress,
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
            can_create_match_proposal=False,
        )

        # NUOVO: elementi unificati
        unified_items = DashboardService._build_unified_items(
            campionati, standalone, user_role="admin", user_id=None
        )

        return DashboardVM(
            title="Dashboard Amministratore",
            campionati=campionati,
            unified_items=unified_items,
            selected_campionato=None,
            selected_gara=None,
            selector_items=DashboardService._build_selector_items(
                campionati=campionati,
                standalones=standalone,
                selected_campionato_id=None,
                selected_gara_id=None,
            ),
            standalone_garas=standalone,  # mantenuto per compatibilità
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

        # Raccogli TUTTE le iscrizioni dell'utente (per tutte le gare)
        all_my_inscriptions = (
            db.session.query(Inscription)
            .join(Gara, Gara.id == Inscription.gara_id)
            .filter(Inscription.user_id == user_id)
            .options(joinedload(Inscription.gara))
            .order_by(Gara.date.asc().nullslast())
            .all()
        )

        # standalone gestite (director principale O co-direttore)
        standalone_owned: List[Gara] = []
        if has_director:
            for gara in standalones_all:
                # Director principale
                if gara.director_id == user_id:
                    standalone_owned.append(gara)
                else:
                    # Co-direttore via DirectorAssignment
                    is_co_director = (
                        db.session.query(DirectorAssignment)
                        .filter(
                            DirectorAssignment.entity_type == "gara",
                            DirectorAssignment.entity_id == gara.id,
                            DirectorAssignment.user_id == user_id,
                        )
                        .first()
                        is not None
                    )
                    if is_co_director:
                        standalone_owned.append(gara)
        standalone_owned = DashboardService._annotate_garas_with_flags(standalone_owned)

        # permesso gestione director nel campionato selezionato
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

        # NUOVO: elementi unificati per director (TUTTE le gare standalone)
        unified_items = DashboardService._build_unified_items(
            campionati, standalones_all, user_role="director", user_id=user_id
        )

        return DashboardVM(
            title="Dashboard Direttore",
            campionati=campionati,
            unified_items=unified_items,
            selected_campionato=selected,
            selected_gara=selected_gara,
            selector_items=DashboardService._build_selector_items(
                campionati=campionati,
                standalones=standalones_all,
                selected_campionato_id=selected.id if selected else None,
                selected_gara_id=selected_gara.id if selected_gara else None,
            ),
            standalone_garas=standalone_owned,  # mantenuto per compatibilità
            available_garas=player_sections["available_garas"],
            standalone_available=standalone_available,
            my_inscriptions=all_my_inscriptions,  # Tutte le iscrizioni
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

        # Per i player, mostriamo TUTTI i match correnti, non solo quelli del campionato selezionato
        all_current_matches = (
            db.session.query(TournamentMatch)
            .join(Gara, Gara.id == TournamentMatch.gara_id)
            .filter(
                TournamentMatch.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value, MatchStatus.COMPLETED.value]),  # type: ignore[attr-defined]
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

        # Raccogli TUTTE le iscrizioni dell'utente (per tutte le gare)
        all_my_inscriptions = (
            db.session.query(Inscription)
            .join(Gara, Gara.id == Inscription.gara_id)
            .filter(Inscription.user_id == user_id)
            .options(joinedload(Inscription.gara))
            .order_by(Gara.date.asc().nullslast())
            .all()
        )

        # Challenge sections for player
        challenge_sections = DashboardService._build_challenge_sections(
            user_id, selected
        )

        # NUOVO: elementi unificati per player (campionati + standalone disponibili)
        # Includiamo TUTTE le gare standalone per il player
        all_standalone_garas = DashboardService._standalone_q().all()
        unified_items = DashboardService._build_unified_items(
            campionati, all_standalone_garas, user_role="player", user_id=user_id
        )

        return DashboardVM(
            title="Dashboard Giocatore",
            campionati=campionati,
            unified_items=unified_items,
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
            my_inscriptions=all_my_inscriptions,  # Tutte le iscrizioni
            my_standalone_inscriptions=my_standalone_regs,
            current_matches=all_current_matches,  # TUTTI i match correnti dell'utente
            recent_matches=player_sections["recent_matches"],
            can_inscribe=True,  # i player possono iscriversi
            user_stats=_compute_user_stats(user_id),
            managed_campionatos=None,
            can_manage_directors=False,
            caps=caps,
            match_proposals=individual_sections["match_proposals"],
            individual_matches=individual_sections["individual_matches"],
            match_opportunities=individual_sections["match_opportunities"],
            available_challenges=challenge_sections["available_challenges"],
            player_challenge_progress=challenge_sections["player_challenge_progress"],
        )
