"""La configurazione dei playoff propone, la finale decide (ADR-075).

È lo stesso meccanismo del campionato (`models/campionato/proposte.py`): la
configurazione dice come si giocherà la finale, e quando la finale nasce ne
copia i valori. Da lì la finale ha i suoi. Se il direttore corregge la
configurazione dopo aver creato la finale, l'app non la tocca da sola: gli
propone di applicare il cambio, campo per campo, finché la finale non è
avviata.

La formula e il sistema di classifica non passano di qui: cambiano la forma
della gara, e si decidono sulla pagina della finale.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional

from ..campionato.proposte import CampoProposto
from ..storia.service import serializza

#: Il campo della configurazione → il campo della finale che lo riceve.
CAMPI_ALLA_FINALE = {
    "name": "name",
    "discipline": "discipline",
    "distance": "distance",
    "rounds_count": "rounds_count",
    "odd_number_policy": "odd_number_policy",
    "location": "location",
    "entry_fee": "entry_fee",
}


def finale_proponibile(config: Any) -> Optional[Any]:
    """La finale, se esiste e non è ancora avviata; altrimenti `None`."""
    from ..competition.campi_modificabili import e_avviata, e_chiusa

    gara = getattr(config, "gara", None)
    if gara is None or gara.is_deleted or e_avviata(gara) or e_chiusa(gara):
        return None
    return gara


def _valore_della_configurazione(config: Any, campo: str) -> Any:
    """Il valore con cui la finale nascerebbe oggi, ereditati compresi."""
    if campo == "name":
        return config.name
    return config.get_gara_params().get(campo)


def proposta_alla_finale(
    config: Any, cambi: Mapping[str, Iterable[Any]]
) -> List[CampoProposto]:
    """I campi della finale che la configurazione corretta cambierebbe.

    `cambi` è `{campo della configurazione: (vecchio, nuovo)}`, di solito le
    righe della voce della storia appena scritta. Sono spuntati i campi in cui
    la finale aveva il valore di prima, o lo ereditava; quelli in cui il
    direttore aveva scelto altro per la finale, no.
    """
    gara = finale_proponibile(config)
    if gara is None:
        return []
    campi: List[CampoProposto] = []
    for campo_cfg, (vecchio, _nuovo) in cambi.items():
        campo_gara = CAMPI_ALLA_FINALE.get(campo_cfg)
        if campo_gara is None:
            continue
        nuovo = _valore_della_configurazione(config, campo_cfg)
        if nuovo is None:
            continue
        attuale = getattr(gara, campo_gara, None)
        if serializza(attuale) == serializza(nuovo):
            continue
        campi.append(
            CampoProposto(
                campo_gara=campo_gara,
                attuale=attuale,
                nuovo=serializza(nuovo),
                spuntato=serializza(vecchio) in ("", serializza(attuale)),
            )
        )
    return campi


def applica_alla_finale(
    config: Any,
    campi: Iterable[str],
    autore: Any = None,
    motivo: Optional[str] = None,
) -> bool:
    """Applica alla finale i campi scelti. Restituisce se l'ha cambiata."""
    from ..competition.services import GaraService
    from ..storia.models import SettingsChangeSource

    gara = finale_proponibile(config)
    if gara is None:
        return False
    per_campo_gara = {v: k for k, v in CAMPI_ALLA_FINALE.items()}
    valori = {}
    for campo_gara in campi:
        campo_cfg = per_campo_gara.get(campo_gara)
        if campo_cfg is None:
            continue
        valore = _valore_della_configurazione(config, campo_cfg)
        if valore is not None:
            valori[campo_gara] = valore
    if not valori:
        return False
    GaraService.update_gara(
        gara.id,
        autore=autore,
        motivo=motivo,
        provenienza=SettingsChangeSource.PLAYOFF,
        **valori,
    )
    return True
