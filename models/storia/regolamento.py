"""Il «Regolamento di gara»: cosa vale adesso, turno per turno, e la storia.

La pagina pubblica dell'ADR-075, visibile a tutti, per eventuali
contestazioni:

1. **In vigore**: ogni impostazione, e se è stata cambiata, quando e da quale
   turno vale;
2. **Per turno**, solo se i turni non hanno tutti le stesse regole: «Turni
   1–3: al 5 · dal turno 4: al 7 (cambiato il 29/09 alle 21:40)»;
3. la **storia delle modifiche**, dalla più recente;
4. in fondo, se c'è, **«Regolamento completo»**: il documento del
   regolamento, che segue il campionato in diretta come la locandina.

I turni già nati leggono le regole fissate sulle loro partite; quelli ancora
da giocare le regole di adesso, con i cambi per turno.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .models import SettingsChange
from .service import StoriaModificheService, serializza

#: Le impostazioni che la pagina mostra, nell'ordine in cui si leggono.
CAMPI_IN_VIGORE: Tuple[str, ...] = (
    "date",
    "time",
    "location",
    "entry_fee",
    "discipline",
    "distance",
    "is_race_to",
    "start_rule",
    "break_rule",
    "has_handicap",
    "matchmaking_strategy",
    "rounds_count",
    "classification_system",
    "odd_number_policy",
    "anti_rematch_enabled",
    "withdraw_policy",
    "min_participants",
    "max_participants",
    "tiebreaker_enabled",
    "tiebreaker_until_position",
)


@dataclass
class Impostazione:
    campo: str
    valore: str
    #: L'ultima voce della storia che l'ha cambiata, se c'è.
    cambiata: Optional[SettingsChange] = None


@dataclass
class GruppoDiTurni:
    dal: int
    al: int
    regole: Tuple[str, ...]
    cambiata: Optional[SettingsChange] = None


@dataclass
class Regolamento:
    gara: Any
    in_vigore: List[Impostazione] = field(default_factory=list)
    per_turno: List[GruppoDiTurni] = field(default_factory=list)
    storia: List[SettingsChange] = field(default_factory=list)
    link_regolamento: Optional[str] = None


def _ultima_modifica(storia: List[SettingsChange]) -> Dict[str, SettingsChange]:
    ultima: Dict[str, SettingsChange] = {}
    for voce in storia:  # dalla più recente
        for riga in voce.fields:
            ultima.setdefault(riga.field, voce)
    return ultima


def _in_vigore(gara: Any, storia: List[SettingsChange]) -> List[Impostazione]:
    from ..competition.services import GaraService

    valori = GaraService._valori_per_la_storia(gara, list(CAMPI_IN_VIGORE))
    ultima = _ultima_modifica(storia)
    risultato = []
    for campo in CAMPI_IN_VIGORE:
        valore = serializza(valori.get(campo))
        if valore == "":
            continue
        if campo == "tiebreaker_until_position" and not gara.tiebreaker_enabled:
            continue
        risultato.append(Impostazione(campo, valore, ultima.get(campo)))
    return risultato


def _regole_del_turno(gara: Any, numero: int) -> Tuple[str, ...]:
    """Disciplina, distanza, «al N», chi apre, chi spacca di un turno."""
    from ..competition.round_creation import resolve_round_overrides
    from ..match.models import Match

    partita = (
        Match.query.filter_by(gara_id=gara.id, round_number=numero, is_bye=False)
        .order_by(Match.id)
        .first()
    )
    if partita is not None:
        return (
            serializza(partita.get_effective_discipline()),
            serializza(partita.effective_distance),
            serializza(partita.effective_is_race_to),
            serializza(partita.effective_start_rule),
            serializza(partita.effective_break_rule),
        )
    turno = resolve_round_overrides(gara, numero)
    return (
        serializza(turno["round_discipline"] or gara.discipline),
        serializza(turno["round_distance"]),
        serializza(turno["round_is_race_to"]),
        serializza(gara.effective_start_rule),
        serializza(gara.effective_break_rule),
    )


def _per_turno(gara: Any, storia: List[SettingsChange]) -> List[GruppoDiTurni]:
    turni = gara.rounds_count or 0
    if turni < 2:
        return []
    gruppi: List[GruppoDiTurni] = []
    for numero in range(1, turni + 1):
        regole = _regole_del_turno(gara, numero)
        if gruppi and gruppi[-1].regole == regole:
            gruppi[-1].al = numero
        else:
            gruppi.append(GruppoDiTurni(dal=numero, al=numero, regole=regole))
    if len(gruppi) < 2:
        return []
    # Il cambio che ha fatto partire un gruppo: una voce «dal turno N», o un
    # cambio sulle regole di quel turno.
    for gruppo in gruppi[1:]:
        for voce in storia:
            dal_turno = voce.from_round == gruppo.dal
            del_turno = any(
                r.field.startswith(f"turno_{gruppo.dal}.") for r in voce.fields
            )
            if dal_turno or del_turno:
                gruppo.cambiata = voce
                break
    return gruppi


def regolamento(gara: Any) -> Regolamento:
    storia = StoriaModificheService.voci_della_gara(gara.id)
    return Regolamento(
        gara=gara,
        in_vigore=_in_vigore(gara, storia),
        per_turno=_per_turno(gara, storia),
        storia=storia,
        link_regolamento=gara.effective_rules_url,
    )


__all__ = ["Regolamento", "regolamento", "CAMPI_IN_VIGORE"]
