"""I preset di un direttore: salvarli, ritrovarli, usarli (ADR-082).

Ogni preset ha **un solo proprietario**, l'unico che lo vede, lo usa, lo
cambia e lo cancella. Per tutti gli altri non esiste: chiederlo dà «non
trovato», non «vietato», così l'elenco dei preset di qualcuno non si scopre
provando gli id.

I preset li salva chi prepara le gare: un direttore o un admin.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flask_babel import gettext as _

from models.base import db
from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from models.preset import payload as formato
from models.preset.models import ConfigPreset, TipoPreset
from models.transaction.manager import transactional

#: Il nome più lungo, lo stesso della colonna.
LUNGHEZZA_MASSIMA_DEL_NOME = 100


def _puo_avere_preset(utente: Any) -> bool:
    return bool(
        utente is not None
        and (
            getattr(utente, "is_director", False) or getattr(utente, "is_admin", False)
        )
    )


def _tipo(kind: Any) -> str:
    valore = getattr(kind, "value", kind)
    if valore not in {t.value for t in TipoPreset}:
        raise ValidationError(_("Tipo di preset sconosciuto: %(v)s", v=valore))
    return str(valore)


def _nome(nome: Any) -> str:
    pulito = " ".join(str(nome or "").split())
    if not pulito:
        raise ValidationError(_("Dai un nome al preset."))
    if len(pulito) > LUNGHEZZA_MASSIMA_DEL_NOME:
        raise ValidationError(
            _(
                "Il nome del preset è lungo al massimo %(n)s caratteri.",
                n=LUNGHEZZA_MASSIMA_DEL_NOME,
            )
        )
    return pulito


class ConfigPresetService:
    """Le operazioni sui preset di un direttore."""

    # ── Letture ────────────────────────────────────────────────────────────
    @staticmethod
    def preset_di(owner_id: int, kind: Optional[Any] = None) -> List[ConfigPreset]:
        """I preset di un direttore, in ordine di nome; di un tipo, se chiesto."""
        query = ConfigPreset.query.filter(ConfigPreset.owner_id == owner_id)
        if kind is not None:
            query = query.filter(ConfigPreset.kind == _tipo(kind))
        return query.order_by(db.func.lower(ConfigPreset.name)).all()

    @staticmethod
    def get_mio(preset_id: int, utente: Any) -> ConfigPreset:
        """Il preset, se è dell'utente; altrimenti per lui non esiste."""
        if not _puo_avere_preset(utente):
            raise PermissionDeniedError(_("I preset sono dei direttori di gara."))
        preset = db.session.get(ConfigPreset, preset_id)
        if preset is None or preset.owner_id != utente.id:
            raise NotFoundError(_("Questo preset non esiste."))
        return preset

    @staticmethod
    def per_il_modulo(preset_id: int, utente: Any) -> Dict[str, Any]:
        """I valori da scrivere nel modulo, letti con la tolleranza di oggi."""
        preset = ConfigPresetService.get_mio(preset_id, utente)
        lettura = formato.leggi(preset.kind, preset.dati, preset.schema_version)
        return {
            "id": preset.id,
            "nome": preset.name,
            "kind": preset.kind,
            **formato.per_il_modulo(lettura),
        }

    # ── Scritture ──────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="preset")
    def salva(
        utente: Any,
        nome: Any,
        kind: Any,
        campi: Dict[str, Any],
        listino: Optional[List[Any]] = None,
        *,
        sostituisci: bool = False,
    ) -> ConfigPreset:
        """Salva un preset col nome scelto; con lo stesso nome, solo se si sostituisce.

        ``campi`` può arrivare da un modulo intero: la whitelist tiene solo la
        configurazione (`payload.componi`).
        """
        if not _puo_avere_preset(utente):
            raise PermissionDeniedError(_("I preset sono dei direttori di gara."))
        tipo = _tipo(kind)
        pulito = _nome(nome)
        dati = formato.componi(tipo, campi, listino)

        esistente = ConfigPreset.query.filter(
            ConfigPreset.owner_id == utente.id, ConfigPreset.name == pulito
        ).first()
        if esistente is not None:
            if not sostituisci:
                raise ConflictError(
                    _(
                        "Hai già un preset che si chiama «%(nome)s»: sostituiscilo "
                        "o scegli un altro nome.",
                        nome=pulito,
                    )
                )
            if esistente.kind != tipo:
                raise ConflictError(
                    _(
                        "«%(nome)s» è un preset di un altro tipo: scegli un altro "
                        "nome.",
                        nome=pulito,
                    )
                )
            esistente.dati = dati
            esistente.schema_version = formato.SCHEMA_VERSION
            db.session.flush()
            return esistente

        preset = ConfigPreset(
            owner_id=utente.id,
            name=pulito,
            kind=tipo,
            schema_version=formato.SCHEMA_VERSION,
        )
        preset.dati = dati
        db.session.add(preset)
        db.session.flush()
        return preset

    @staticmethod
    def salva_dalla_gara(
        utente: Any, nome: Any, gara: Any, *, sostituisci: bool = False
    ) -> ConfigPreset:
        """«Salva come preset» dalla pagina di una gara che esiste già."""
        return ConfigPresetService.salva(
            utente,
            nome,
            TipoPreset.GARA,
            formato.dalla_gara(gara),
            formato.listino_della_gara(gara),
            sostituisci=sostituisci,
        )


def preset_dell_utente(kind: Any) -> List[ConfigPreset]:
    """I preset di chi guarda la pagina, per il selettore «Parti da un preset».

    Vuoto per chi non è collegato o non è un direttore: il selettore non
    compare nemmeno (`components/_preset_modulo.html`).
    """
    from flask_login import current_user

    if not getattr(current_user, "is_authenticated", False):
        return []
    if not _puo_avere_preset(current_user):
        return []
    return ConfigPresetService.preset_di(current_user.id, kind)
