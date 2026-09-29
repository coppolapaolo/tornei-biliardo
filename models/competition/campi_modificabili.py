"""Cosa si può ancora cambiare di una gara, e perché no (ADR-075).

Una sola risposta per il servizio, la pagina e i test: `campi_bloccati(gara)`
restituisce i campi che **non** si possono cambiare adesso, ciascuno col
motivo da mostrare. Tutto il resto si cambia, e resta nella storia.

Le fasce:

* **logistica** (nome, sala, data, ora, tavoli, quota, descrizione): sempre,
  fino alla fine della gara;
* **regole di gioco** (distanza, modalità, disciplina, chi apre, chi spacca,
  handicap, dispari, esercizio della X, ritiri): a gara avviata si cambiano e
  valgono dal turno successivo — le partite già nate hanno le loro regole
  fissate (`models/match/regole_fissate.py`). Non con la strategia casuale,
  dove tutti i turni esistono già, né quando non restano turni da giocare;
* **spareggio**: finché lo spareggio non è cominciato;
* **struttura** (strategia, sistema di classifica, numero di turni, primo
  turno, set, anti-reincontro, opzioni del tabellone, minimo e capienza): solo
  prima dell'avvio; dopo, si cambia annullando l'avvio;
* **peso** nel campionato: sempre (conta quanto vale la gara, non come si
  gioca).

Sul tabellone alcune regole non sono una scelta ma una conseguenza del formato
(`bracket_derived_fields`): restano bloccate come nel modulo di creazione.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet

from flask_babel import lazy_gettext as _l

from models.status_enum import GaraStatus

LOGISTICA: FrozenSet[str] = frozenset(
    {
        "name",
        "location",
        "billiard_hall_id",
        "date",
        "time",
        "available_tables",
        "entry_fee",
        "description",
    }
)

REGOLE: FrozenSet[str] = frozenset(
    {
        "distance",
        "is_race_to",
        "discipline",
        "start_rule",
        "break_rule",
        "has_handicap",
        "odd_number_policy",
        "x_challenge_id",
        "withdraw_policy",
    }
)

SPAREGGIO: FrozenSet[str] = frozenset(
    {"tiebreaker_enabled", "tiebreaker_until_position"}
)

STRUTTURA: FrozenSet[str] = frozenset(
    {
        "matchmaking_strategy",
        "classification_system",
        "rounds_count",
        "first_round_policy",
        "is_multi_set",
        "match_distance",
        "is_race_to_sets",
        "anti_rematch_enabled",
        "separate_teammates",
        "third_place_match",
        "seeding_rating",
        "double_ko_rounds",
        "min_participants",
        "max_participants",
    }
)

PESO: FrozenSet[str] = frozenset({"weight"})

#: Le regole che sul tabellone discendono dal formato (`bracket_derived_fields`).
REGOLE_DEL_TABELLONE: FrozenSet[str] = frozenset(
    {"odd_number_policy", "withdraw_policy", "is_race_to", "x_challenge_id"}
)


def e_avviata(gara: Any) -> bool:
    """Il primo turno è partito (e non è stato annullato)."""
    return bool(gara.current_round or 0) or gara.status in (
        GaraStatus.PLAYING.value,
        GaraStatus.AWAITING_SSR.value,
        # Una gara conclusa è stata avviata, anche se un dato vecchio ha
        # lasciato il contatore dei turni a zero.
        GaraStatus.COMPLETED.value,
    )


def e_chiusa(gara: Any) -> bool:
    return gara.status in (GaraStatus.COMPLETED.value, GaraStatus.CANCELLED.value)


def spareggio_cominciato(gara: Any) -> bool:
    if gara.status == GaraStatus.AWAITING_SSR.value:
        return True
    from models.tiebreaker.models import Tiebreaker, TiebreakerStatus

    return (
        Tiebreaker.query.filter(
            Tiebreaker.gara_id == gara.id,
            Tiebreaker.status != TiebreakerStatus.CANCELLED.value,
        ).first()
        is not None
    )


def restano_turni(gara: Any) -> bool:
    """C'è ancora un turno da avviare a cui un cambio di regola può arrivare."""
    from models.matchmaking.configuration import BRACKET_STRATEGIES

    if gara.matchmaking_strategy in BRACKET_STRATEGIES:
        # Il tabellone sa da sé se c'è un turno dopo (la bella del doppio KO
        # arriva solo se serve): qui basta che la gara sia in corso.
        return gara.status == GaraStatus.PLAYING.value
    return (gara.current_round or 0) < (gara.rounds_count or 0)


def campi_bloccati(gara: Any) -> Dict[str, Any]:
    """I campi che adesso non si cambiano, ciascuno col motivo."""
    from models.matchmaking.configuration import BRACKET_STRATEGIES

    if e_chiusa(gara):
        motivo = _l("La gara è chiusa.")
        return {
            campo: motivo for campo in LOGISTICA | REGOLE | SPAREGGIO | STRUTTURA | PESO
        }

    bloccati: Dict[str, Any] = {}
    # Prima dell'avvio si cambia tutto, strategia compresa: le conseguenze del
    # tabellone le impone già il modulo (`bracket_derived_fields`).
    if not e_avviata(gara):
        return bloccati

    if gara.matchmaking_strategy in BRACKET_STRATEGIES:
        for campo in REGOLE_DEL_TABELLONE | SPAREGGIO:
            bloccati[campo] = _l("Sul tabellone lo decide il formato.")

    for campo in STRUTTURA:
        bloccati[campo] = _l(
            "La gara è avviata: la struttura si cambia annullando l'avvio."
        )
    if gara.creates_all_rounds_at_startup():
        for campo in REGOLE:
            bloccati[campo] = _l(
                "Con la strategia casuale tutti i turni esistono già: le regole "
                "di gioco non si cambiano dopo l'avvio."
            )
    elif not restano_turni(gara):
        for campo in REGOLE:
            bloccati[campo] = _l(
                "Non restano turni da avviare: un cambio di regola non avrebbe "
                "partite a cui arrivare."
            )
    if spareggio_cominciato(gara):
        for campo in SPAREGGIO:
            bloccati[campo] = _l("Lo spareggio è già cominciato.")
    return bloccati


def dal_turno(gara: Any) -> int | None:
    """Il primo turno a cui arriva un cambio di regola fatto adesso."""
    if not e_avviata(gara):
        return None
    return (gara.current_round or 0) + 1


def motivo_turno_non_modificabile(gara: Any, round_number: int) -> Any:
    """Perché le regole di questo turno non si cambiano più, o None se si può.

    Prima dell'avvio si cambiano tutti i turni. A gara avviata solo quelli non
    ancora avviati, e mai con la strategia casuale, dove esistono già tutti.
    Fino al 2026-09-29 si cambiavano solo in preparazione: nemmeno a
    iscrizioni aperte.
    """
    if e_chiusa(gara):
        return _l("La gara è chiusa.")
    if not e_avviata(gara):
        return None
    if gara.creates_all_rounds_at_startup():
        return _l(
            "Con la strategia casuale tutti i turni esistono già: le regole dei "
            "turni non si cambiano dopo l'avvio."
        )
    if round_number <= (gara.current_round or 0):
        return _l(
            "Il turno %(n)s è già avviato: le sue partite hanno le regole con "
            "cui sono cominciate.",
            n=round_number,
        )
    return None
