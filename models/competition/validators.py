"""
Validatore di configurazioni gara.

Implementa le regole di validazione da docs/CLASSIFICATION_SYSTEM.md sezione 9.
"""

from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models.competition.models import Gara


class ClassificationSystem(Enum):
    """Sistemi di classifica disponibili."""

    RACK = "RACK"
    WINS = "WINS"
    POSITION = "POSITION"


class DistanceType(Enum):
    """Tipi di distanza."""

    RACE_TO = "race_to"
    EXACTLY = "exactly"


class OddHandling(Enum):
    """Gestione numero dispari di giocatori."""

    NO = "NO"  # Lista attesa
    TRIO = "TRIO"  # Trio (distanza 2-5)
    BYE = "BYE"  # Bye semplice (solo WINS)
    BYE_CHALLENGE = "BYE_CHALLENGE"  # Bye con challenge
    BYE_N_RACK = "BYE_N_RACK"  # Bye con N rack (solo RACK)
    BRACKET_BYE = "BRACKET_BYE"  # Bye gestito dal bracket (solo POSITION)


class ForfeitPolicy(Enum):
    """Policy per forfait."""

    EXCLUDE = "EXCLUDE"  # Giocatore rimosso dagli abbinamenti futuri
    FORFEIT = "FORFEIT"  # Giocatore resta, avversari vincono automaticamente


class MatchmakingStrategy(Enum):
    """Strategie di matchmaking."""

    RANDOM = "random"
    AMALFI = "amalfi"
    ROUND_ROBIN = "round_robin"
    ELIMINATION = "elimination"
    DOUBLE_KO = "double_ko"


def validate_gara_configuration(
    classification_system: ClassificationSystem,
    distance_type: DistanceType,
    distance: int,
    multi_set: bool,
    odd_handling: OddHandling,
    forfeit_policy: ForfeitPolicy,
    matchmaking: MatchmakingStrategy,
) -> tuple[list[str], list[str]]:
    """
    Valida la configurazione di una gara.

    Args:
        classification_system: Sistema di classifica (RACK/WINS/POSITION)
        distance_type: Tipo distanza (race_to/exactly)
        distance: Valore distanza
        multi_set: Se abilitato multi-set
        odd_handling: Gestione dispari
        forfeit_policy: Policy forfait
        matchmaking: Strategia matchmaking

    Returns:
        Tupla (errors, warnings) dove:
        - errors: lista di errori (configurazione invalida)
        - warnings: lista di warning (configurazione permessa ma problematica)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Validazione distanza base
    if distance <= 0:
        errors.append("La distanza deve essere maggiore di 0")
        return errors, warnings  # Non proseguiamo se distanza invalida

    # Validazione Trio (indipendente dal sistema)
    if odd_handling == OddHandling.TRIO:
        if distance < 2 or distance > 5:
            errors.append(
                f"Trio richiede distanza tra 2 e 5, specificata: {distance}"
            )

    # Validazioni per sistema
    if classification_system == ClassificationSystem.RACK:
        _validate_rack_system(
            distance_type, multi_set, odd_handling, matchmaking, errors, warnings
        )
    elif classification_system == ClassificationSystem.WINS:
        _validate_wins_system(
            distance_type, distance, multi_set, odd_handling, matchmaking, errors, warnings
        )
    elif classification_system == ClassificationSystem.POSITION:
        _validate_position_system(
            distance_type, distance, odd_handling, forfeit_policy, matchmaking, errors, warnings
        )

    return errors, warnings


def _validate_rack_system(
    distance_type: DistanceType,
    multi_set: bool,
    odd_handling: OddHandling,
    matchmaking: MatchmakingStrategy,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validazione per sistema RACK."""
    # Race to N genera warning
    if distance_type == DistanceType.RACE_TO:
        warnings.append(
            "Sistema RACK con Race to N può distorcere la classifica: "
            "chi perde di misura accumula più rack"
        )

    # Multi-set non permesso
    if multi_set:
        errors.append(
            "Sistema RACK non supporta multi-set: "
            "match più lunghi darebbero più opportunità di rack"
        )

    # Bye semplice non permesso (0 rack = penalizzato)
    if odd_handling == OddHandling.BYE:
        errors.append(
            "Sistema RACK non supporta Bye semplice: "
            "il giocatore con bye riceverebbe 0 rack"
        )

    # Matchmaking: solo Random, Amalfi, Round Robin
    if matchmaking in (MatchmakingStrategy.ELIMINATION, MatchmakingStrategy.DOUBLE_KO):
        errors.append(
            f"Sistema RACK non supporta matchmaking {matchmaking.value}: "
            "usare Random, Amalfi o Round Robin"
        )


def _validate_wins_system(
    distance_type: DistanceType,
    distance: int,
    multi_set: bool,
    odd_handling: OddHandling,
    matchmaking: MatchmakingStrategy,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validazione per sistema WINS."""
    # Exactly N pari = warning opzionale per pareggi
    if distance_type == DistanceType.EXACTLY and distance % 2 == 0:
        warnings.append(
            f"Sistema WINS con Exactly {distance} (pari) ammette pareggi: "
            "entrambi i giocatori riceverebbero 0 vittorie e 0 diff rack"
        )

    # Bye+N rack non supportato (è N/A per WINS)
    if odd_handling == OddHandling.BYE_N_RACK:
        errors.append(
            "Sistema WINS non supporta Bye+N rack: "
            "usare Bye semplice o Bye+Challenge"
        )

    # Matchmaking: solo Random, Amalfi, Round Robin
    if matchmaking in (MatchmakingStrategy.ELIMINATION, MatchmakingStrategy.DOUBLE_KO):
        errors.append(
            f"Sistema WINS non supporta matchmaking {matchmaking.value}: "
            "usare Random, Amalfi o Round Robin"
        )


def _validate_position_system(
    distance_type: DistanceType,
    distance: int,
    odd_handling: OddHandling,
    forfeit_policy: ForfeitPolicy,
    matchmaking: MatchmakingStrategy,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validazione per sistema POSITION."""
    # Exactly N pari non permesso (pareggi non ammessi nel bracket)
    if distance_type == DistanceType.EXACTLY and distance % 2 == 0:
        errors.append(
            f"Sistema POSITION non supporta Exactly {distance} (pari): "
            "il bracket richiede sempre un vincitore"
        )

    # Solo FORFEIT policy (EXCLUDE non permesso)
    if forfeit_policy == ForfeitPolicy.EXCLUDE:
        errors.append(
            "Sistema POSITION richiede policy FORFEIT: "
            "EXCLUDE non è permesso nel bracket"
        )

    # Matchmaking: solo Eliminazione, Doppio KO
    if matchmaking in (
        MatchmakingStrategy.RANDOM,
        MatchmakingStrategy.AMALFI,
        MatchmakingStrategy.ROUND_ROBIN,
    ):
        errors.append(
            f"Sistema POSITION non supporta matchmaking {matchmaking.value}: "
            "usare Eliminazione o Doppio KO"
        )


# =============================================================================
# Mapping da modello Gara esistente ai nuovi enum di validazione
# =============================================================================

# Mapping matchmaking_strategy esistente -> MatchmakingStrategy
_MATCHMAKING_MAP = {
    "amalfi": MatchmakingStrategy.AMALFI,
    "round_robin": MatchmakingStrategy.ROUND_ROBIN,
    "random": MatchmakingStrategy.RANDOM,
    "direct_elimination": MatchmakingStrategy.ELIMINATION,
    "double_knockout": MatchmakingStrategy.DOUBLE_KO,
}

# Mapping odd_number_policy esistente -> OddHandling
_ODD_HANDLING_MAP = {
    "bye": OddHandling.BYE,
    "bye_with_challenge": OddHandling.BYE_CHALLENGE,
    "trio": OddHandling.TRIO,
}

# Mapping classification_system string -> ClassificationSystem enum
_CLASSIFICATION_SYSTEM_MAP = {
    "RACK": ClassificationSystem.RACK,
    "WINS": ClassificationSystem.WINS,
    "POSITION": ClassificationSystem.POSITION,
}


def _infer_classification_system(matchmaking: MatchmakingStrategy) -> ClassificationSystem:
    """
    Inferisce il sistema di classificazione dal matchmaking.

    Usato come fallback quando gara.classification_system non è impostato:
    - Eliminazione/Doppio KO → POSITION
    - Altri → WINS (default più comune)
    """
    if matchmaking in (MatchmakingStrategy.ELIMINATION, MatchmakingStrategy.DOUBLE_KO):
        return ClassificationSystem.POSITION
    return ClassificationSystem.WINS


def validate_gara(
    gara: "Gara",
    classification_system: Optional[ClassificationSystem] = None,
) -> tuple[list[str], list[str]]:
    """
    Valida la configurazione di una Gara esistente.

    Questa funzione funge da bridge tra il modello Gara attuale
    e il nuovo sistema di validazione.

    Args:
        gara: Istanza Gara da validare
        classification_system: Sistema di classifica (se None, inferito dal matchmaking)

    Returns:
        Tupla (errors, warnings)
    """
    # Mappa matchmaking
    matchmaking_value = getattr(gara, "matchmaking_strategy", "amalfi")
    matchmaking = _MATCHMAKING_MAP.get(matchmaking_value, MatchmakingStrategy.AMALFI)

    # Mappa odd_handling
    odd_value = getattr(gara, "odd_number_policy", "bye")
    odd_handling = _ODD_HANDLING_MAP.get(odd_value, OddHandling.BYE)

    # Per POSITION usa sempre BRACKET_BYE
    if matchmaking in (MatchmakingStrategy.ELIMINATION, MatchmakingStrategy.DOUBLE_KO):
        odd_handling = OddHandling.BRACKET_BYE

    # Determina distance_type
    is_race_to = getattr(gara, "is_race_to", False)
    distance_type = DistanceType.RACE_TO if is_race_to else DistanceType.EXACTLY

    # Multi-set
    multi_set = getattr(gara, "is_multi_set", False)

    # Distance
    distance = getattr(gara, "distance", 5)

    # Forfeit policy: per ora usiamo FORFEIT come default
    # (withdraw_policy è diverso da forfeit_policy nel nuovo sistema)
    forfeit_policy = ForfeitPolicy.FORFEIT

    # Sistema di classificazione
    # Priorità: 1) parametro esplicito, 2) campo gara, 3) inferenza da matchmaking
    if classification_system is None:
        gara_class_system = getattr(gara, "classification_system", None)
        if gara_class_system and gara_class_system in _CLASSIFICATION_SYSTEM_MAP:
            classification_system = _CLASSIFICATION_SYSTEM_MAP[gara_class_system]
        else:
            classification_system = _infer_classification_system(matchmaking)

    return validate_gara_configuration(
        classification_system=classification_system,
        distance_type=distance_type,
        distance=distance,
        multi_set=multi_set,
        odd_handling=odd_handling,
        forfeit_policy=forfeit_policy,
        matchmaking=matchmaking,
    )
