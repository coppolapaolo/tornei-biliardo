"""Il preset di configurazione di un direttore (ADR-082).

Una riga sola, e nessuna tabella di condivisione: condividere un preset vuol
dire **copiarlo** nella casa di un altro direttore, che ne diventa
proprietario a tutti gli effetti. La copia ricorda da chi arriva e quando
(`received_from_user_id`, `received_at`), e basta: niente la lega più
all'originale.

Il preset **precompila** un modulo e poi è dimenticato: nessuna gara e nessun
campionato tengono un riferimento al preset da cui sono partiti.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict

from models.base import BaseModel, db


class TipoPreset(str, Enum):
    """Che modulo precompila: quello della gara o quello del campionato."""

    GARA = "gara"
    CAMPIONATO = "campionato"


class ConfigPreset(BaseModel):
    """Le impostazioni di un modulo, salvate col nome che il direttore sceglie."""

    __tablename__ = "config_preset"
    __table_args__ = (
        # Il nome è unico per proprietario: è così che il direttore lo
        # ritrova nell'elenco, e che una copia ricevuta prende il suffisso.
        db.UniqueConstraint("owner_id", "name", name="uq_config_preset_owner_name"),
    )

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    #: `TipoPreset`: il modulo che il preset precompila.
    kind = db.Column(db.String(20), nullable=False)
    #: I valori, in JSON: ``{"campi": {...}, "listino": [...]}``. Solo i campi
    #: della whitelist (`models.preset.payload`), mai nome, date, sala, iscritti.
    payload = db.Column(db.Text, nullable=False, default="{}")
    #: La forma del payload quando è stato scritto: chi lo legge domani sa da
    #: dove parte (`payload.leggi`).
    schema_version = db.Column(db.Integer, nullable=False, default=1)

    #: Da chi arriva la copia, se è una copia. NULL se l'autore viene
    #: cancellato: la copia resta, perde solo la provenienza.
    received_from_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    received_at = db.Column(db.DateTime, nullable=True)

    owner = db.relationship("User", foreign_keys=[owner_id])
    received_from = db.relationship("User", foreign_keys=[received_from_user_id])

    @property
    def dati(self) -> Dict[str, Any]:
        """Il payload come dizionario; vuoto se illeggibile."""
        try:
            valore = json.loads(self.payload or "{}")
        except (TypeError, ValueError):
            return {}
        return valore if isinstance(valore, dict) else {}

    @dati.setter
    def dati(self, valore: Dict[str, Any]) -> None:
        self.payload = json.dumps(valore, ensure_ascii=False, sort_keys=True)

    def __repr__(self) -> str:  # pragma: no cover - solo diagnostica
        return f"<ConfigPreset {self.id} {self.kind} {self.name!r}>"
