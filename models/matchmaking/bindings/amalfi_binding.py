from __future__ import annotations
from typing import Tuple, List, Any

# Import dal tuo sistema Amalfi già presente nel repo
from amalfi import validate_amalfi_configuration, create_amalfi_round_matches


def validate_prova(prova: Any) -> Tuple[bool, tuple[str, ...]]:
    """
    Adatta validate_amalfi_configuration(prova) -> (ok, messages)
    """
    data = validate_amalfi_configuration(prova)  # dict con is_valid, errors, warnings
    ok = bool(data.get("is_valid", False))
    # Prima gli errori (bloccanti), poi i warning (informativi)
    messages: list[str] = []
    messages.extend(data.get("errors", []))
    messages.extend(data.get("warnings", []))
    return ok, tuple(messages)


def propose_pairings(prova: Any, round_number: int) -> List[tuple[int, ...]]:
    """
    Genera gli abbinamenti *effettivi* del round invocando il tuo engine legacy,
    poi li traduce in tuple di ID giocatori (p1,p2) o (p1,) per bye o
    (p1,p2,p3) per trio.
    """
    # Crea davvero i match col legacy engine
    matches = create_amalfi_round_matches(prova, round_number)  #

    pairings: list[tuple[int, ...]] = []
    for m in matches:
        # Nel tuo codice i match hanno flag come is_bye / is_trio
        # usati anche nelle route.
        if getattr(m, "is_bye", False):
            pairings.append((int(m.player1_id),))
        elif getattr(m, "is_trio", False):
            # Alcune implementazioni usano TrioMatch con player3_id
            p3 = getattr(m, "player3_id", None)
            if p3 is None:
                # fallback: se non c'è un campo player3_id, prova a derivarlo
                # (lasciamo semplice per ora; verrà consolidato nello Sprint Policy)
                raise RuntimeError(
                    "Trio match senza player3_id non supportato dal binding"
                )
            pairings.append((int(m.player1_id), int(m.player2_id), int(p3)))
        else:
            pairings.append((int(m.player1_id), int(m.player2_id)))
    return pairings
