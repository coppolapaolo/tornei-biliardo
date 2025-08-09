from __future__ import annotations
from enum import Enum

from models import PlayerEncounter


class OddResolution(Enum):
    BYE = "bye"
    TRIO = "trio"


def decide_trio_or_bye(*, tournament_without_x: bool, can_trio: bool) -> OddResolution:
    """Regola minimale: se il torneo consente il trio e c'è almeno un 1v1
    già costruito, scegli TRIO; altrimenti BYE.
    Nessun side-effect.
    """
    return (
        OddResolution.TRIO if (tournament_without_x and can_trio) else OddResolution.BYE
    )


def anti_rematch_allowed(prova_id: int, a_id: int, b_id: int) -> bool:
    """True se A e B non hanno mai giocato tra loro in questa prova.
    Usa sola lettura sul dominio PlayerEncounter.
    """
    return not PlayerEncounter.have_played(prova_id, a_id, b_id)
