"""
Module: models/dashboard/item_builders.py
Purpose: Dashboard item builders (unified items, selector items, capabilities)
"""

from __future__ import annotations

from typing import List, Optional, Iterable, Tuple
from datetime import date as date_cls

from models.base import db
from models.campionato.models import Campionato
from models.user.models import DirectorAssignment, User
from models.competition.models import Gara
from models.status_enum import GaraStatus
from models.user.role_enum import UserRole

from .view_models import (
    _role_truthy,
    CapabilityVM,
    UnifiedDashboardItem,
)


def build_unified_items(
    campionati: List[Campionato],
    standalone_garas: List[Gara],
    user_role: str = UserRole.PLAYER.value,
    user_id: Optional[int] = None,
) -> List[UnifiedDashboardItem]:
    """
    Crea lista unificata di campionati e gare standalone, ordinata per
    data prossima prova.

    N+1 fix: batch-loads DirectorAssignment for the user upfront instead of
    querying per-entity inside the loop.
    """
    items = []

    # Batch-load director assignments for this user to avoid N+1 queries
    user_assignments: dict[str, set[int]] = {"campionato": set(), "gara": set()}
    if user_role == UserRole.DIRECTOR.value and user_id:
        assignments = (
            db.session.query(
                DirectorAssignment.entity_type, DirectorAssignment.entity_id
            )
            .filter(DirectorAssignment.user_id == user_id)
            .all()
        )
        for entity_type, entity_id in assignments:
            if entity_type in user_assignments:
                user_assignments[entity_type].add(entity_id)

    # Aggiungi campionati
    for campionato in campionati:
        next_date = None
        try:
            # N+1 fix: usa la relationship già eager-loaded (joinedload(gare) in
            # campionatos_q/managed_campionatos_q) invece di ri-interrogare Gara
            # per ogni campionato. Il filtro soft-delete unificato
            # (models/soft_delete/filter.py) usa include_aliases=True, quindi
            # esclude le soft-deleted sia dalla query esplicita sia dalla
            # relationship joinedload → stesso set, behavior-preserving.
            gare_list = campionato.gare or []
            future_dates = [
                g.date for g in gare_list if g.date and g.date >= date_cls.today()
            ]
            next_date = min(future_dates) if future_dates else None
        except (AttributeError, TypeError):
            next_date = None

        can_manage = False
        # La pagina del campionato e quelle delle sue gare sono aperte a
        # chiunque, anonimo compreso (ADR-028): il flag qui è sempre vero.
        # Fino al 14/09/2026 il direttore che **non** dirigeva il campionato
        # aveva `can_view_details = is_co_director`, cioè falso: la tessera
        # della gara a cui era iscritto mostrava solo «Disiscriviti», senza
        # via per arrivare all'elenco degli iscritti, e quella del campionato
        # un pulsante «Classifica» spento. Un giocatore nello stesso posto
        # vedeva entrambi. Regola nata col refactor del 07/02/2026, prima che
        # la pagina della gara fosse unificata.
        can_view_details = True

        if user_role == UserRole.ADMIN.value:
            can_manage = True
        elif user_role == UserRole.DIRECTOR.value and user_id:
            can_manage = campionato.id in user_assignments["campionato"]

        if next_date:
            sort_key = f"{next_date.strftime('%Y-%m-%d')}_campionato_{campionato.id}"
        else:
            sort_key = f"9999-99-99_campionato_{campionato.id}"

        items.append(
            UnifiedDashboardItem(
                type="campionato",
                id=campionato.id,
                name=campionato.name,
                entity=campionato,
                next_prova_date=next_date,
                sort_key=sort_key,
                can_manage=can_manage,
                can_view_details=can_view_details,
            )
        )

    # Aggiungi gare standalone
    today = date_cls.today()
    for gara in standalone_garas:
        gara_name = gara.name or f'Gara {gara.number or ""}'

        can_manage = False
        can_view_details = True

        if user_role == UserRole.ADMIN.value:
            can_manage = True
        elif user_role == UserRole.DIRECTOR.value and user_id:
            is_main_director = (
                hasattr(gara, "director_id") and gara.director_id == user_id
            )
            is_co_director = gara.id in user_assignments["gara"]
            can_manage = is_main_director or is_co_director
            can_view_details = True
        elif user_role == UserRole.PLAYER.value:
            can_view_details = True
        elif user_role == UserRole.GUEST.value:
            can_view_details = gara.status == GaraStatus.INSCRIPTION.value

        gara_date = getattr(gara, "date", None)

        # Skip gare SETUP con data passata (zombie/dimenticate) per chi
        # NON le gestisce. Director/admin proprietari le vedono comunque
        # per poterle gestire/cancellare.
        if (
            gara.status == GaraStatus.SETUP.value
            and gara_date is not None
            and gara_date < today
            and not can_manage
        ):
            continue
        if gara_date:
            sort_key = f"{gara_date.strftime('%Y-%m-%d')}_gara_{gara.id}"
        else:
            sort_key = f"9999-99-99_gara_{gara.id}"

        items.append(
            UnifiedDashboardItem(
                type="gara",
                id=gara.id,
                name=gara_name,
                entity=gara,
                next_prova_date=gara_date,
                sort_key=sort_key,
                can_manage=can_manage,
                can_view_details=can_view_details,
            )
        )

    items.sort(
        key=lambda x: (
            x.next_prova_date is None,
            x.next_prova_date or date_cls.max,
            x.sort_key,
        )
    )

    return items


def build_selector_items(
    campionati: Iterable[Campionato],
    standalones: Iterable[Gara],
    *,
    selected_campionato_id: Optional[int],
    selected_gara_id: Optional[int],
) -> List[dict]:
    """
    Lista mista ordinata per data crescente per il selector UI.
    """

    def _t_date(t: Campionato) -> Optional[date_cls]:
        try:
            gare_attr = getattr(t, "gare", None)
            if gare_attr is None:
                return None
            gare_list = list(gare_attr) if hasattr(gare_attr, "__iter__") else []
            dates = [p.date for p in gare_list if getattr(p, "date", None)]
        except (AttributeError, TypeError):
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

    items.sort(key=lambda tup: (tup[0] is None, tup[0]))
    return [d for _, d in items]


def caps_for(user: User) -> CapabilityVM:
    """Build capability view model for a user."""
    is_admin = _role_truthy(user, "is_admin")
    is_director = _role_truthy(user, "is_director")
    is_player = _role_truthy(user, "is_player")
    can_create_campionato = False
    if hasattr(user, "can_access"):
        can_create_campionato = user.can_access("create_campionato")
    else:
        can_create_campionato = is_admin or is_director

    return CapabilityVM(
        can_create_campionato=can_create_campionato,
        can_create_standalone=is_admin or is_director,
        can_register_self=not is_admin,
        can_create_match_proposal=is_player and not is_admin,
    )
