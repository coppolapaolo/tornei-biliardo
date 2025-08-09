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


def _extract_pairing_from_match(m: Any) -> tuple[int, ...]:
    """Estrae la tupla (p1,), (p1,p2) o (p1,p2,p3) da un oggetto match legacy.

    Supporta trio sia quando il 3° giocatore è su `m.player3_id` sia quando è
    presente come relazione `m.trio_match.player3_id`.
    """
    if getattr(m, "is_bye", False):
        return (int(m.player1_id),)

    if getattr(m, "is_trio", False):
        p3 = getattr(m, "player3_id", None)
        if p3 is None:
            trio = getattr(m, "trio_match", None)
            if trio is not None:
                p3 = getattr(trio, "player3_id", None)
        if p3 is None:
            raise RuntimeError(
                "Trio match senza player3_id non supportato dal binding"
            )
        return (int(m.player1_id), int(m.player2_id), int(p3))

    # Match standard 1v1
    return (int(m.player1_id), int(m.player2_id))


def propose_pairings(prova: Any, round_number: int) -> List[tuple[int, ...]]:
    """
    Genera gli abbinamenti *effettivi* del round invocando il tuo engine legacy,
    poi li traduce in tuple di ID giocatori (p1,p2) o (p1,) per bye o
    (p1,p2,p3) per trio.
    """
    matches = create_amalfi_round_matches(prova, round_number)
    return [_extract_pairing_from_match(m) for m in matches]
