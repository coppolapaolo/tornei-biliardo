"""Scrivere e leggere la storia delle modifiche (ADR-075).

Un solo punto di scrittura, `StoriaModificheService.registra`, che ogni
servizio di modifica chiama **dopo** aver deciso cosa cambia: così la voce
nasce nella stessa transazione del cambiamento, e se il cambiamento fallisce
non resta una voce che racconta una modifica mai avvenuta.

I valori si confrontano e si salvano con `serializza`, una sola forma per
tutti: date ISO, ore «HH:MM», liste separate da virgola, booleani `true` /
`false`, niente per `None`. È la stessa forma che il modulo di modifica
conserva come «stato iniziale», e che serve a capire quali campi il direttore
ha cambiato davvero (vedi `routes/admin/competition/crud.py`, `edit_gara`).
"""

from __future__ import annotations

from datetime import date, datetime, time
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from ..base import db
from ..transaction.manager import transactional
from .models import (
    SettingsChange,
    SettingsChangeAction,
    SettingsChangeField,
    SettingsChangeSource,
)


def serializza(valore: Any) -> str:
    """La forma testuale unica con cui un valore si confronta e si salva."""
    if valore is None:
        return ""
    if isinstance(valore, Enum):
        valore = valore.value
    if isinstance(valore, bool):
        return "true" if valore else "false"
    if isinstance(valore, datetime):
        return valore.isoformat(timespec="minutes")
    if isinstance(valore, date):
        return valore.isoformat()
    if isinstance(valore, time):
        return valore.strftime("%H:%M")
    if isinstance(valore, float) and valore.is_integer():
        return str(int(valore))
    if isinstance(valore, (list, tuple)):
        return ",".join(serializza(v) for v in valore)
    return str(valore).strip()


def ruolo_di(utente: Any) -> Optional[str]:
    """Con che titolo agisce chi modifica. Salvato sulla voce, non ricalcolato."""
    if utente is None:
        return None
    if getattr(utente, "is_admin", False):
        return "admin"
    return "direttore"


class StoriaModificheService:
    """La storia delle modifiche: scrittura unica, letture per oggetto."""

    @staticmethod
    def differenze(
        prima: Mapping[str, Any], dopo: Mapping[str, Any]
    ) -> Dict[str, Tuple[str, str]]:
        """I campi il cui valore serializzato cambia, con prima e dopo."""
        cambi: Dict[str, Tuple[str, str]] = {}
        for campo, nuovo in dopo.items():
            vecchio = serializza(prima.get(campo))
            nuovo_s = serializza(nuovo)
            if vecchio != nuovo_s:
                cambi[campo] = (vecchio, nuovo_s)
        return cambi

    @staticmethod
    @transactional(domain="storia")
    def registra(
        *,
        cambi: Mapping[str, Tuple[Any, Any]],
        gara_id: Optional[int] = None,
        campionato_id: Optional[int] = None,
        playoff_config_id: Optional[int] = None,
        autore: Any = None,
        motivo: Optional[str] = None,
        provenienza: str = SettingsChangeSource.GARA,
        azione: str = SettingsChangeAction.MODIFICA,
        dal_turno: Optional[int] = None,
    ) -> Optional[SettingsChange]:
        """Scrive una voce. Una modifica senza campi cambiati non lascia traccia.

        Fanno eccezione le azioni che *sono* il fatto (annullare l'avvio,
        riconfermare per conto di qualcuno, una nota): quelle si scrivono anche
        senza righe.
        """
        righe = [
            (campo, serializza(vecchio), serializza(nuovo))
            for campo, (vecchio, nuovo) in cambi.items()
            if serializza(vecchio) != serializza(nuovo)
        ]
        if not righe and azione == SettingsChangeAction.MODIFICA:
            return None
        if gara_id is None and campionato_id is None and playoff_config_id is None:
            raise ValueError("Una voce della storia deve dire di cosa parla")

        motivo_pulito = (motivo or "").strip() or None
        voce = SettingsChange(
            gara_id=gara_id,
            campionato_id=campionato_id,
            playoff_config_id=playoff_config_id,
            author_id=getattr(autore, "id", None),
            author_role=ruolo_di(autore),
            source=provenienza,
            action=azione,
            reason=motivo_pulito,
            from_round=dal_turno,
        )
        for campo, vecchio_s, nuovo_s in righe:
            voce.fields.append(
                SettingsChangeField(field=campo, old_value=vecchio_s, new_value=nuovo_s)
            )
        db.session.add(voce)
        db.session.flush()
        return voce

    @staticmethod
    def voci_della_gara(gara_id: int) -> List[SettingsChange]:
        """La storia di una gara, dalla voce più recente."""
        return (
            SettingsChange.query.filter_by(gara_id=gara_id)
            .order_by(SettingsChange.created_at.desc(), SettingsChange.id.desc())
            .all()
        )

    @staticmethod
    def voci_del_campionato(campionato_id: int) -> List[SettingsChange]:
        """La storia dei valori del campionato, dalla voce più recente."""
        return (
            SettingsChange.query.filter_by(campionato_id=campionato_id)
            .order_by(SettingsChange.created_at.desc(), SettingsChange.id.desc())
            .all()
        )

    @staticmethod
    def campi(voci: Iterable[SettingsChange]) -> List[str]:
        """I nomi dei campi toccati da un insieme di voci, senza ripetizioni."""
        visti: List[str] = []
        for voce in voci:
            for riga in voce.fields:
                if riga.field not in visti:
                    visti.append(riga.field)
        return visti
