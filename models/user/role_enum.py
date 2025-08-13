# models/user/role_enum.py
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    DIRECTOR = "director"
    PLAYER = "player"
