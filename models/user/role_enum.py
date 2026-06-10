# models/user/role_enum.py
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    DIRECTOR = "director"
    PLAYER = "player"
    # Pseudo-ruolo di sola vista (visitatore anonimo): mai salvato in
    # user.role, usato dalla dashboard per il rendering guest.
    GUEST = "guest"
