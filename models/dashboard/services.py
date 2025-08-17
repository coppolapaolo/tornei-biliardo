from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from models.base import db
from models.tournament.models import Tournament, TournamentDirector
from models.competition.models import Prova, Inscription
from models.match.models import Match
from models.user.models import User
from models.status_enum import ProvaStatus, MatchStatus


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
        db.session.query(Match)
        .filter(or_(Match.player1_id == user_id, Match.player2_id == user_id))
        .count()
    )
    won_matches = (
        db.session.query(Match)
        .filter(
            or_(Match.player1_id == user_id, Match.player2_id == user_id),
            Match.winner_id == user_id,
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
    can_create_tournament: bool = False
    can_create_standalone: bool = False
    can_register_self: bool = True  # gli admin in genere no


@dataclass
class DashboardVM:
    # comuni
    title: str
    tournaments: List[Tournament]
    caps: CapabilityVM

    # selezione
    selected_tournament: Optional[Tournament] = None

    # sezioni admin/director
    standalone_provas: Optional[
        List[Prova]
    ] = None  # standalone che GESTISCO (admin=tutte, director=solo le sue)

    # sezioni player-like
    available_provas: Optional[
        List[Prova]
    ] = None  # prove del torneo selezionato con iscrizioni aperte
    standalone_available: Optional[
        List[Prova]
    ] = None  # standalone aperte (come giocatore)
    my_inscriptions: Optional[List[Inscription]] = None
    my_standalone_inscriptions: Optional[List[Inscription]] = None
    current_matches: Optional[List[Match]] = None
    recent_matches: Optional[List[Match]] = None
    can_inscribe: bool = False

    # extra
    user_stats: Optional[dict[str, Any]] = None
    managed_tournaments: Optional[List[Tournament]] = None
    can_manage_directors: bool = False
    debug_mode: bool = False


# -----------------------
# Service
# -----------------------
class DashboardService:
    """Orchestratore read-only per le tre dashboard."""

    # ---- query helpers ------------------------------------------------
    @staticmethod
    def _tournaments_q():
        return (
            db.session.query(Tournament)
            .options(joinedload(Tournament.provas))
            .order_by(Tournament.created_at.desc())
        )

    @staticmethod
    def _managed_tournaments_q(user_id: int):
        return (
            db.session.query(Tournament)
            .join(TournamentDirector, TournamentDirector.tournament_id == Tournament.id)
            .filter(TournamentDirector.user_id == user_id)
            .options(joinedload(Tournament.provas))
            .order_by(Tournament.created_at.desc())
        )

    @staticmethod
    def _standalone_q():
        return (
            db.session.query(Prova)
            .filter(Prova.tournament_id.is_(None))
            .order_by(Prova.date.desc().nullslast(), Prova.date.desc())
        )

    @staticmethod
    def _caps_for(user: User) -> CapabilityVM:
        is_admin = _role_truthy(user, "is_admin")
        is_director = _role_truthy(user, "is_director")
        return CapabilityVM(
            can_create_tournament=is_admin or is_director,
            can_create_standalone=is_admin or is_director,
            can_register_self=not is_admin,
        )

    # ---- ADMIN --------------------------------------------------------
    @staticmethod
    def for_admin() -> DashboardVM:
        tournaments = DashboardService._tournaments_q().all()
        standalone = DashboardService._standalone_q().all()
        caps = CapabilityVM(
            can_create_tournament=True,
            can_create_standalone=True,
            can_register_self=False,
        )
        return DashboardVM(
            title="Dashboard Amministratore",
            tournaments=tournaments,
            selected_tournament=None,
            standalone_provas=standalone,
            available_provas=None,
            standalone_available=None,
            my_inscriptions=None,
            my_standalone_inscriptions=None,
            current_matches=None,
            recent_matches=None,
            can_inscribe=False,
            user_stats=None,
            managed_tournaments=None,
            can_manage_directors=True,
            caps=caps,
            debug_mode=False,
        )

    # ---- DIRECTOR -----------------------------------------------------
    @staticmethod
    def for_director(
        user_id: int, selected_tournament_id: Optional[int] = None
    ) -> DashboardVM:
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("Utente non trovato")

        caps = DashboardService._caps_for(user)

        managed = DashboardService._managed_tournaments_q(user_id).all()
        tournaments = DashboardService._tournaments_q().all()

        # torneo selezionato: esplicito -> primo gestito -> primo globale
        selected = (
            db.session.get(Tournament, selected_tournament_id)
            if selected_tournament_id
            else None
        )
        if not selected and managed:
            selected = managed[0]
        if not selected:
            selected = DashboardService._tournaments_q().first()

        # --- sezioni player-like ---------------------------------------
        available_provas: List[Prova] = []
        my_regs: List[Inscription] = []
        my_upcoming: List[Match] = []
        my_recent: List[Match] = []
        standalone_available: List[Prova] = []
        my_standalone_regs: List[Inscription] = []

        if selected:
            # prove con iscrizioni aperte nel torneo selezionato e non già iscritto
            subq_my_prova_ids = select(
                Inscription.prova_id
            ).where(Inscription.user_id == user_id)

            available_provas = (
                db.session.query(Prova)
                .filter(
                    Prova.tournament_id == selected.id,
                    Prova.status == ProvaStatus.INSCRIPTION.value,
                    Prova.id.notin_(subq_my_prova_ids),
                )
                .order_by(Prova.date.asc().nullslast(), Prova.number.asc())
                .all()
            )

            # mie iscrizioni nel torneo selezionato
            my_regs = (
                db.session.query(Inscription)
                .join(Prova, Prova.id == Inscription.prova_id)
                .filter(
                    Inscription.user_id == user_id, Prova.tournament_id == selected.id
                )
                .options(joinedload(Inscription.prova))
                .order_by(Prova.date.desc().nullslast(), Prova.number.desc())
                .all()
            )

            # partite in corso nel torneo selezionato
            my_upcoming = (
                db.session.query(Match)
                .join(Prova, Prova.id == Match.prova_id)
                .filter(
                    Prova.tournament_id == selected.id,
                    Match.status == MatchStatus.PLAYING.value,
                    or_(Match.player1_id == user_id, Match.player2_id == user_id),
                )
                .order_by(Match.created_at.desc().nullslast(), Match.id.desc())
                .all()
            )

            # ultime partite completate (limite 10)
            my_recent = (
                db.session.query(Match)
                .join(Prova, Prova.id == Match.prova_id)
                .filter(
                    Prova.tournament_id == selected.id,
                    Match.status == MatchStatus.COMPLETED.value,
                    or_(Match.player1_id == user_id, Match.player2_id == user_id),
                )
                .order_by(Match.created_at.desc().nullslast(), Match.id.desc())
                .limit(10)
                .all()
            )

        # standalone disponibili (come giocatore), non ancora iscritto
        subq_all_my_prova_ids = db.session.query(Inscription.prova_id).filter(
            Inscription.user_id == user_id
        )
        standalone_available = (
            DashboardService._standalone_q()
            .filter(
                Prova.status == ProvaStatus.INSCRIPTION.value,
                ~Prova.id.in_(subq_all_my_prova_ids),
            )
            .all()
        )

        # mie iscrizioni a standalone (come giocatore)
        my_standalone_regs = (
            db.session.query(Inscription)
            .join(Prova, Prova.id == Inscription.prova_id)
            .filter(Inscription.user_id == user_id, Prova.tournament_id.is_(None))
            .options(joinedload(Inscription.prova))
            .order_by(Prova.date.desc().nullslast())
            .all()
        )

        # standalone che GESTISCO: se esiste la colonna director_id filtra,
        # altrimenti nessuna (compatibilità)
        if hasattr(Prova, "director_id"):
            standalone_owned = (
                DashboardService._standalone_q()
                .filter(Prova.director_id == user_id)
                .all()
            )
        else:
            standalone_owned = []

        # permesso gestione director nel torneo selezionato
        can_manage_directors = False
        if selected:
            can_manage_directors = _role_truthy(user, "is_admin") or (
                db.session.query(TournamentDirector)
                .filter_by(user_id=user_id, tournament_id=selected.id)
                .first()
                is not None
            )

        return DashboardVM(
            title="Dashboard Direttore",
            tournaments=tournaments,
            selected_tournament=selected,
            standalone_provas=standalone_owned,
            available_provas=available_provas,
            standalone_available=standalone_available,
            my_inscriptions=my_regs,
            my_standalone_inscriptions=my_standalone_regs,
            current_matches=my_upcoming,
            recent_matches=my_recent,
            can_inscribe=not _role_truthy(user, "is_admin"),
            user_stats=_compute_user_stats(user_id),
            managed_tournaments=managed,
            can_manage_directors=can_manage_directors,
            caps=caps,
        )

    # ---- PLAYER -------------------------------------------------------
    @staticmethod
    def for_player(
        user_id: int, selected_tournament_id: Optional[int] = None
    ) -> DashboardVM:
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("Utente non trovato")

        caps = DashboardService._caps_for(user)

        tournaments = DashboardService._tournaments_q().all()
        selected = (
            db.session.get(Tournament, selected_tournament_id)
            if selected_tournament_id
            else None
        )
        if not selected:
            selected = tournaments[0] if tournaments else None

        # ri-uso della logica director per costruire le sezioni "player-like"
        tmp = DashboardService.for_director(
            user_id, selected_tournament_id=selected.id if selected else None
        )

        return DashboardVM(
            title="Dashboard Giocatore",
            tournaments=tournaments,
            selected_tournament=tmp.selected_tournament,
            standalone_provas=None,  # non usata su player
            available_provas=tmp.available_provas,
            standalone_available=tmp.standalone_available,
            my_inscriptions=tmp.my_inscriptions,
            my_standalone_inscriptions=tmp.my_standalone_inscriptions,
            current_matches=tmp.current_matches,
            recent_matches=tmp.recent_matches,
            can_inscribe=True,  # i player possono iscriversi
            user_stats=tmp.user_stats,
            managed_tournaments=tmp.managed_tournaments,
            can_manage_directors=False,
            caps=caps,
        )
