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


#: I valori del campionato: quelli che propone alle sue gare (ADR-075).
CAMPI_DEL_CAMPIONATO: Tuple[str, ...] = (
    "campionato_type",
    "default_classification_system",
    "planned_gare_count",
    "default_venue_id",
    "default_entry_fee",
    "default_rounds_count",
    "default_odd_policy",
    "default_anti_rematch",
    "default_start_rule",
    "default_break_rule",
    "has_handicap",
    "position_points",
)

#: Chi si qualifica ai playoff e come si gioca la finale.
CAMPI_DEI_PLAYOFF: Tuple[str, ...] = (
    "positions_from",
    "positions_to",
    "max_participants",
    "min_garas_played",
    "scheduled_date",
    "location",
    "discipline",
    "distance",
    "rounds_count",
    "strategy_type",
    "odd_number_policy",
    "final_ranking_mode",
    "playoff_weight",
)


@dataclass
class PlayoffDelRegolamento:
    config: Any
    impostazioni: List[Impostazione] = field(default_factory=list)


@dataclass
class RegolamentoCampionato:
    campionato: Any
    in_vigore: List[Impostazione] = field(default_factory=list)
    gare: List[Any] = field(default_factory=list)
    playoff: List[PlayoffDelRegolamento] = field(default_factory=list)
    storia: List[SettingsChange] = field(default_factory=list)
    link_regolamento: Optional[str] = None


def _impostazioni(
    oggetto: Any, campi: Tuple[str, ...], storia: List[SettingsChange]
) -> List[Impostazione]:
    ultima = _ultima_modifica(storia)
    risultato = []
    for campo in campi:
        valore = serializza(getattr(oggetto, campo, None))
        if valore != "":
            risultato.append(Impostazione(campo, valore, ultima.get(campo)))
    return risultato


def regolamento_campionato(campionato: Any) -> RegolamentoCampionato:
    """Il regolamento di un campionato: i valori che propone, le gare, i playoff.

    Le regole di ogni gara stanno nella sua pagina: qui ci sono i valori
    proposti dal campionato, il peso di ogni gara, i criteri dei playoff e la
    storia del campionato e dei playoff insieme.
    """
    from ..playoff.models import PlayoffConfiguration

    storia_campionato = StoriaModificheService.voci_del_campionato(campionato.id)
    configurazioni = (
        PlayoffConfiguration.query.filter_by(
            campionato_id=campionato.id, is_active=True
        )
        .order_by(PlayoffConfiguration.positions_from, PlayoffConfiguration.id)
        .all()
    )
    tutte = PlayoffConfiguration.query.filter_by(campionato_id=campionato.id).all()
    storia_playoff = StoriaModificheService.voci_dei_playoff([c.id for c in tutte])
    playoff = []
    for config in configurazioni:
        sue = [v for v in storia_playoff if v.playoff_config_id == config.id]
        playoff.append(
            PlayoffDelRegolamento(
                config=config,
                impostazioni=_impostazioni(config, CAMPI_DEI_PLAYOFF, sue),
            )
        )
    storia = sorted(
        storia_campionato + storia_playoff,
        key=lambda v: (v.created_at, v.id),
        reverse=True,
    )
    return RegolamentoCampionato(
        campionato=campionato,
        in_vigore=_impostazioni(campionato, CAMPI_DEL_CAMPIONATO, storia_campionato),
        gare=sorted(
            (g for g in campionato.gare if not g.is_deleted),
            key=lambda g: g.number or 0,
        ),
        playoff=playoff,
        storia=storia,
        link_regolamento=campionato.rules_url or None,
    )


__all__ = [
    "Regolamento",
    "RegolamentoCampionato",
    "regolamento",
    "regolamento_campionato",
    "CAMPI_IN_VIGORE",
    "CAMPI_DEL_CAMPIONATO",
    "CAMPI_DEI_PLAYOFF",
]
