# models/user/role_enum.py
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    DIRECTOR = "director"
    PLAYER = "player"
    # Pseudo-ruolo di sola vista (visitatore anonimo): mai salvato in
    # user.role, usato dalla dashboard per il rendering guest.
    GUEST = "guest"


class GrantableRole(str, Enum):
    """Ruoli **ortogonali** a ``user.role``, concessi tramite ``RoleGrant``.

    Enum separato di proposito: ``user.role`` resta il ruolo *primario*
    mono-valore (admin|director|player), mentre i ruoli concedibili si
    **sommano** ad esso e sono cumulabili. Un player che diventa esaminatore
    resta player: continua a iscriversi alle gare, a fare drill e a sostenere
    esami altrui.

    Il precedente architetturale è ``User.is_venue_manager``, che già oggi non
    guarda ``user.role`` ma la tabella di assegnazione ``venue_management``.

    Vedi ADR-041.
    """

    EXAMINER = "examiner"
