from __future__ import annotations
from typing import Tuple, List, Any

# Integration with existing Amalfi engine - preserves all legacy functionality
# while enabling new strategy pattern architecture
from amalfi import validate_amalfi_configuration, create_amalfi_round_matches


def validate_gara(gara: Any) -> Tuple[bool, tuple[str, ...]]:
    """Adapter function bridging new strategy interface with legacy Amalfi validation.

    Translates between the legacy Amalfi engine's validation format (dict with is_valid,
    errors, warnings) and the new strategy system's tuple format (ok, messages).
    This adapter enables the legacy Amalfi algorithm to work seamlessly within the
    new strategy framework without requiring engine modifications.

    Args:
        gara: Tournament/competition object to validate

    Returns:
        Tuple of (validation_success, error_and_warning_messages)

    Integration Pattern:
        Adapter pattern enabling legacy code integration without modification
    """
    data = validate_amalfi_configuration(gara)  # dict con is_valid, errors, warnings
    ok = bool(data.get("is_valid", False))
    # Prima gli errori (bloccanti), poi i warning (informativi)
    messages: list[str] = []
    errors = data.get("errors", [])
    warnings = data.get("warnings", [])

    # Se ci sono errori, la validazione fallisce
    if errors:
        ok = False
        messages.extend(errors)

    # Aggiungi sempre i warnings
    messages.extend(warnings)

    return ok, tuple(messages)


def _extract_pairing_from_match(m: Any) -> tuple[int, ...]:
    """Extract player pairing tuple from legacy Match object with trio support.

    Translates legacy Match objects into standardized player ID tuples that work
    with the new strategy system. Handles multiple trio match representations
    for backward compatibility with different database schema versions.

    Supported Match Types:
    - Bye matches: (player_id,) - single player sits out the round
    - Regular matches: (player1_id, player2_id) - standard 1v1 pool match
    - Trio matches: (player1_id, player2_id, player3_id) - three-player format

    Trio Resolution Logic:
        1. Check direct player3_id attribute (newer schema)
        2. Check trio_match relationship (legacy schema)
        3. Query database for TrioMatch record (fallback)
        4. Raise error if trio match lacks third player

    Args:
        m: Legacy Match object from Amalfi engine

    Returns:
        Tuple of player IDs representing the match pairing

    Raises:
        RuntimeError: If trio match is missing required third player
    """
    if getattr(m, "is_bye", False):
        return (int(m.player1_id),)

    if getattr(m, "is_trio", False):
        p3 = getattr(m, "player3_id", None)
        if p3 is None:
            trio = getattr(m, "trio_match", None)
            if trio is None:
                # Carica esplicitamente il TrioMatch dal database
                from models.match.models import TrioMatch
                from models import db
                trio = db.session.query(TrioMatch).filter_by(match_id=m.id).first()
            if trio is not None:
                p3 = getattr(trio, "player3_id", None)
        if p3 is None:
            raise RuntimeError(
                "Trio match missing third player - database integrity issue or unsupported trio format"
            )
        return (int(m.player1_id), int(m.player2_id), int(p3))

    # Match standard 1v1
    return (int(m.player1_id), int(m.player2_id))


def propose_pairings(gara: Any, round_number: int) -> List[tuple[int, ...]]:
    """Generate tournament round pairings by delegating to legacy Amalfi engine.

    This function serves as the bridge between the new strategy pattern system
    and the existing Amalfi pairing algorithm. It invokes the legacy engine's
    round creation logic and translates the resulting Match objects into
    standardized player ID tuples that work with the new architecture.

    Process Flow:
    1. Delegate to legacy create_amalfi_round_matches() function
    2. Extract player pairings from created Match objects
    3. Return standardized tuple format for strategy system

    Args:
        gara: Tournament/competition object with player inscriptions and history
        round_number: Sequential round number (1-based)

    Returns:
        List of player ID tuples representing this round's match pairings:
        - (player_id,) for bye matches
        - (player1_id, player2_id) for regular matches
        - (player1_id, player2_id, player3_id) for trio matches

    Side Effects:
        The legacy engine creates Match objects with all associated database updates
        (PlayerEncounter records, classification updates, etc.)

    Integration Note:
        This adapter allows the sophisticated Amalfi algorithm to work within
        the new strategy framework without requiring engine rewriting.
    """
    matches = create_amalfi_round_matches(gara, round_number)
    return [_extract_pairing_from_match(m) for m in matches]
