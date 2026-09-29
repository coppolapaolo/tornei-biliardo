"""Il campionato propone, la gara decide (ADR-075).

I valori del campionato sono i **valori di partenza** delle sue gare: si
copiano sulla gara quando nasce, e da lì la gara ha i suoi. Quando il
direttore cambia un valore del campionato, l'app non lo spinge sulle gare da
sola: propone di applicarlo a quelle già create e **non ancora avviate**, gara
per gara e campo per campo. Sono già spuntate le gare che avevano il valore
vecchio del campionato; quelle con un valore proprio no, perché lì il direttore
aveva già fatto una scelta sua.

Due eccezioni non passano di qui: il sistema di classifica, che vale per tutto
il campionato (`TournamentService._propaga_sistema`), e locandina e link, che
sono presentazione e seguono il campionato in diretta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional

from models.base import db
from models.storia.service import serializza

#: Il valore del campionato → il campo della gara che lo riceve.
CAMPI_PROPOSTI: Dict[str, str] = {
    "default_venue_id": "billiard_hall_id",
    "default_entry_fee": "entry_fee",
    "default_rounds_count": "rounds_count",
    "default_odd_policy": "odd_number_policy",
    "default_anti_rematch": "anti_rematch_enabled",
    "default_start_rule": "start_rule",
    "default_break_rule": "break_rule",
    "has_handicap": "has_handicap",
}


@dataclass
class CampoProposto:
    campo_gara: str
    attuale: Any
    nuovo: Any
    spuntato: bool


@dataclass
class GaraProposta:
    gara: Any
    campi: List[CampoProposto] = field(default_factory=list)


def gare_proponibili(campionato: Any) -> List[Any]:
    """Le gare a cui un valore nuovo del campionato si può ancora proporre."""
    from models.competition.campi_modificabili import e_avviata, e_chiusa

    return [
        gara
        for gara in sorted(campionato.gare, key=lambda g: g.number or 0)
        if not gara.is_deleted and not e_avviata(gara) and not e_chiusa(gara)
        # La finale ha i suoi valori, proposti dalla configurazione dei playoff.
        and not gara.is_playoff
    ]


def valore_della_gara(gara: Any, campo_gara: str) -> Any:
    return getattr(gara, campo_gara, None)


def proposta(campionato: Any, cambi: Mapping[str, Iterable[Any]]) -> List[GaraProposta]:
    """Per ogni gara proponibile, i campi cambiati nel campionato.

    `cambi` è `{campo del campionato: (vecchio, nuovo)}`: di solito le righe
    della voce della storia del campionato appena scritta.
    """
    righe: List[GaraProposta] = []
    for gara in gare_proponibili(campionato):
        voce = GaraProposta(gara=gara)
        for campo_camp, (vecchio, nuovo) in cambi.items():
            campo_gara = CAMPI_PROPOSTI.get(campo_camp)
            if campo_gara is None:
                continue
            attuale = valore_della_gara(gara, campo_gara)
            if serializza(attuale) == serializza(nuovo):
                continue  # la gara ha già il valore nuovo
            voce.campi.append(
                CampoProposto(
                    campo_gara=campo_gara,
                    attuale=attuale,
                    nuovo=nuovo,
                    spuntato=serializza(attuale) == serializza(vecchio),
                )
            )
        if voce.campi:
            righe.append(voce)
    return righe


def _valore_da_scrivere(campo_gara: str, grezzo: Any) -> Dict[str, Any]:
    """Il valore salvato nella storia (testo) → i campi della gara da scrivere."""
    if campo_gara == "billiard_hall_id":
        from models.location.models import BilliardHall

        sala = db.session.get(BilliardHall, int(grezzo)) if grezzo else None
        return {
            "billiard_hall_id": sala.id if sala else None,
            "location": sala.name if sala else None,
        }
    if campo_gara in ("has_handicap", "anti_rematch_enabled"):
        return {campo_gara: str(grezzo).lower() in ("true", "1")}
    if campo_gara == "rounds_count":
        return {campo_gara: int(grezzo)}
    if campo_gara == "entry_fee":
        return {campo_gara: float(grezzo) if grezzo not in (None, "") else None}
    return {campo_gara: grezzo if grezzo not in ("",) else None}


def applica(
    campionato: Any,
    scelte: Mapping[int, Iterable[str]],
    nuovi: Mapping[str, Any],
    autore: Any = None,
    motivo: Optional[str] = None,
) -> int:
    """Applica i valori nuovi alle gare scelte. Ogni gara ha la sua voce.

    `scelte` è `{gara_id: [campo della gara, ...]}`, `nuovi` `{campo della
    gara: valore come nella storia}`. Restituisce quante gare ha toccato.
    """
    from models.competition.services import GaraService
    from models.storia.models import SettingsChangeSource

    ammesse = {gara.id for gara in gare_proponibili(campionato)}
    toccate = 0
    for gara_id, campi in scelte.items():
        if gara_id not in ammesse:
            continue
        valori: Dict[str, Any] = {}
        for campo_gara in campi:
            if campo_gara in nuovi:
                valori.update(_valore_da_scrivere(campo_gara, nuovi[campo_gara]))
        if not valori:
            continue
        GaraService.update_gara(
            gara_id,
            autore=autore,
            motivo=motivo,
            provenienza=SettingsChangeSource.CAMPIONATO,
            **valori,
        )
        toccate += 1
    return toccate
