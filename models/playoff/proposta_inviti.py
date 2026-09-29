"""Una correzione sposta la classifica dopo gli inviti: la proposta (ADR-075).

Quando il direttore corregge quanto conta una gara a inviti partiti — il
peso, i punti per posizione — la classifica cambia e può cambiare chi rientra
nei posti dei playoff. L'app non tocca gli inviti da sola: prepara una
proposta («ritirare l'invito a Bianchi, ora 10°; invitare Rossi, ora 7°») che
il direttore accetta, rifiuta, o sistema a mano con gli strumenti di sempre.

Il calcolo è quello del riallineamento (`riallineamento.pianifica`): stesse
fasce, stesse gare minime, chi ha rifiutato resta fuori e chi è stato aggiunto
a mano resta dentro. Accettare è `riallineamento.esegui`, con le notifiche.
La scelta va nella storia dei playoff; una proposta rifiutata non si ripresenta
finché la classifica non cambia di nuovo. Dopo l'avvio della finale non
compare più.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..exceptions import ConflictError, NotFoundError
from ..storia.models import SettingsChange, SettingsChangeAction
from ..transaction.manager import transactional
from .riallineamento import Riallineamento, esegui, pianifica


def _righe(piano: Riallineamento) -> Dict[str, Tuple[Any, Any]]:
    """La proposta come righe della storia: chi esce e chi entra, per nome."""
    ritirati = ", ".join(sorted(r.username for r in piano.da_ritirare))
    nuovi = ", ".join(sorted(i.username for i in piano.da_invitare))
    return {"inviti_ritirati": (None, ritirati), "inviti_nuovi": (None, nuovi)}


def _gia_rifiutata(config_id: int, piano: Riallineamento) -> bool:
    ultima = (
        SettingsChange.query.filter_by(
            playoff_config_id=config_id,
            action=SettingsChangeAction.PROPOSTA_RIFIUTATA,
        )
        .order_by(SettingsChange.created_at.desc(), SettingsChange.id.desc())
        .first()
    )
    if ultima is None:
        return False
    rifiutata = {r.field: r.new_value or "" for r in ultima.fields}
    attesa = {campo: dopo for campo, (_prima, dopo) in _righe(piano).items()}
    return rifiutata == attesa


def proposta_inviti(config_id: int) -> Optional[Riallineamento]:
    """La proposta da mostrare, o `None` se non c'è niente da proporre."""
    try:
        piano = pianifica(config_id)
    except (ConflictError, NotFoundError):
        # Inviti non ancora partiti, finale cominciata, campionato sparito.
        return None
    if piano.niente_da_fare or _gia_rifiutata(config_id, piano):
        return None
    return piano


def _scrivi(config_id: int, piano, azione, autore, motivo) -> None:
    from ..storia.models import SettingsChangeSource
    from ..storia.service import StoriaModificheService

    StoriaModificheService.registra(
        cambi=_righe(piano),
        playoff_config_id=config_id,
        autore=autore,
        motivo=motivo,
        provenienza=SettingsChangeSource.PLAYOFF,
        azione=azione,
    )


@transactional(domain="playoff")
def accetta(
    config_id: int, autore: Any = None, motivo: Optional[str] = None
) -> Riallineamento:
    """Ritira e manda gli inviti come proposto, con le notifiche."""
    piano = pianifica(config_id)
    _scrivi(config_id, piano, SettingsChangeAction.PROPOSTA_ACCETTATA, autore, motivo)
    return esegui(config_id, classifica_corretta=True)


@transactional(domain="playoff")
def rifiuta(
    config_id: int, autore: Any = None, motivo: Optional[str] = None
) -> Riallineamento:
    """Gli inviti restano come sono; la scelta resta scritta."""
    piano = pianifica(config_id)
    _scrivi(config_id, piano, SettingsChangeAction.PROPOSTA_RIFIUTATA, autore, motivo)
    return piano


__all__ = ["proposta_inviti", "accetta", "rifiuta"]
