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

    #: Chi insegna: segue gli allievi sulle schede che gli aprono (ADR-069).
    #: Distinto dall'esaminatore, che certifica esami — due mestieri, due
    #: concessioni. Da solo **non apre niente**: rende trovabili, e ciò che si
    #: vede lo concede un allievo, una scheda per volta.
    INSTRUCTOR = "instructor"

    #: Chi prova in produzione le funzioni non ancora aperte al suo ruolo.
    #: Non e' un permesso in piu' — e' **visibilita'** in piu': un beta tester
    #: raggiunge le schermate che l'allowlist di ADR-028 terrebbe nascoste,
    #: ma una volta arrivato valgono gli stessi decoratori di tutti.
    BETA_TESTER = "beta_tester"
