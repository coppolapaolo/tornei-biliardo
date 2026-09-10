# models/dashboard/view_models.py
"""Dashboard view models and query helpers.

Extracted from services.py for maintainability (Round 4 P3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List, Optional
from datetime import date as date_cls

if TYPE_CHECKING:  # pragma: no cover
    from .campionato_cards import ElenchiCampionati
    from .gara_cards import ElenchiGare

from sqlalchemy import or_, and_

from models.base import db
from models.match.models import Match as TournamentMatch, TrioMatch
from models.user.models import User
from models.competition.models import Gara, Inscription
from models.campionato.models import Campionato


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


def _user_is_match_participant(user_id: int):
    """Filter condition for matches where user is a participant.

    Handles both regular matches (player1 or player2) and trio matches
    (player1, player2, or player3 via TrioMatch).

    Returns SQLAlchemy OR condition for use in filter().
    """
    return or_(
        TournamentMatch.player1_id == user_id,
        TournamentMatch.player2_id == user_id,
        # Trio matches: also check player3 in TrioMatch
        and_(
            TournamentMatch.is_trio == True,  # noqa: E712
            TournamentMatch.trio_match.has(TrioMatch.player3_id == user_id),
        ),
    )


def _compute_user_stats(user_id: int) -> dict[str, Any]:
    total_matches = (
        db.session.query(TournamentMatch)
        .filter(_user_is_match_participant(user_id))
        .count()
    )
    won_matches = (
        db.session.query(TournamentMatch)
        .filter(
            _user_is_match_participant(user_id),
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
    #: Le sfide a due **da giocare**: fissate o gia' iniziate. Era
    #: `individual_matches` — le ultime dieci di qualunque stato — e non la
    #: disegnava nessun template: una sfida in corso non compariva in nessuna
    #: dashboard, mentre la partita di gara si'.
    sfide_in_corso: Optional[List[Any]] = None
    match_opportunities: Optional[List[Any]] = None  # Available match opportunities

    # Inviti ai playoff ancora senza risposta (PlayoffQualification PENDING):
    # una cosa da fare, con scadenza, quindi sta fra le schede della dashboard
    # e non solo dietro una notifica.
    playoff_invitations: Optional[List[Any]] = None

    # Challenge system
    available_challenges: Optional[List[Any]] = (
        None  # Available challenges for the player
    )
    player_challenge_progress: Optional[dict[str, Any]] = (
        None  # Player progress on challenges
    )

    # La X da sostituire con una prova: chi resta senza avversario in un turno
    # di una gara con `odd_number_policy = bye_with_challenge` ha qualcosa da
    # fare, ma il suo match nasce gia' concluso e quindi non compare fra le
    # partite in corso. Senza una voce sua, la prova non e' annunciata da
    # nessuna parte (issue #221).
    bye_challenges: Optional[List[Any]] = None

    # Gamification: {level, xp, next_level_xp, streaks}
    gamification_stats: Optional[dict[str, Any]] = None

    # Blocco «Come stai andando» in cima alla home: feedback sull'attivita'
    # gia' svolta, calcolato da ActivityFeedbackService. Esattamente uno dei
    # due e' valorizzato — `activity_setup` e' il caso «appena iscritto», dove
    # non c'e' nessun numero vero da mostrare e si disegna la card dei tre
    # passi invece di un blocco pieno di trattini.
    activity_feedback: Optional[dict[str, Any]] = None
    activity_setup: Optional[dict[str, Any]] = None

    # Partizione campionati per presentazione: liste di
    # UnifiedDashboardItem (non Campionato puri) per preservare i flag
    # can_manage/can_view_details/next_prova_date già calcolati da
    # build_unified_items. Il template separa attivi vs completati e
    # mostra "Vedi tutti" quando completed_total > len(completed_shown).
    campionati_active_items: Optional[List["UnifiedDashboardItem"]] = None
    campionati_completed_shown_items: Optional[List["UnifiedDashboardItem"]] = None
    campionati_completed_total: int = 0

    # Le gare della dashboard, divise per quello che chiedono
    # (`models/dashboard/gara_cards.py`): le mie, in diretta, aperte, in
    # arrivo, concluse. Sono `GaraCardVM`, cioè la gara più il posto che ci
    # occupa chi guarda — iscrizione, partite aperte, direzione — e la tessera
    # si disegna da quei fatti: senza, è quella dell'ospite (regola 1 del
    # 2026-09-10). Le concluse sono di tutti, l'ultima più l'ultimo mese.
    gare: Optional["ElenchiGare"] = None
    # I campionati con la testa della classifica e la riga di chi guarda
    # (`models/dashboard/campionato_cards.py`): attivi e conclusi, questi
    # ultimi con la stessa finestra delle gare.
    campionati_tessere: Optional["ElenchiCampionati"] = None
