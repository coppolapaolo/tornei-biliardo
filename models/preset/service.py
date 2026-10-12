"""I preset di un direttore: salvarli, ritrovarli, usarli (ADR-082).

Ogni preset ha **un solo proprietario**, l'unico che lo vede, lo usa, lo
cambia e lo cancella. Per tutti gli altri non esiste: chiederlo dà «non
trovato», non «vietato», così l'elenco dei preset di qualcuno non si scopre
provando gli id.

I preset li salva chi prepara le gare: un direttore o un admin.

**Condividere vuol dire copiare.** Chi riceve ha un preset suo, che ricorda
solo da chi arriva e quando; da lì in poi i due non si toccano più. Non c'è
modo di «togliere la condivisione»: per aggiornare qualcuno si condivide di
nuovo, e arriva una copia nuova.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from flask_babel import gettext as _

from models.base import db, utc_now
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
            **formato.per_il_modulo(lettura, preset.kind),
        }

    @staticmethod
    def cerca_direttori(testo: Any, utente: Any, limite: int = 10) -> List[Any]:
        """I direttori (e gli admin) con cui si può condividere, per nome.

        Come per i co-direttori, si condivide solo con chi prepara gare. Servono
        almeno due lettere: l'elenco di tutti i direttori non si sfoglia.
        """
        from models.user.models import User
        from models.user.role_enum import UserRole

        if not _puo_avere_preset(utente):
            raise PermissionDeniedError(_("I preset sono dei direttori di gara."))
        cercato = " ".join(str(testo or "").split())
        if len(cercato) < 2:
            return []
        modello = "%" + cercato.replace("%", "").replace("_", "\\_") + "%"
        return (
            User.query.filter(
                User.role.in_([UserRole.DIRECTOR.value, UserRole.ADMIN.value]),
                User.id != utente.id,
                User.username.ilike(modello, escape="\\"),
            )
            .order_by(db.func.lower(User.username))
            .limit(limite)
            .all()
        )

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
    def salva_dal_campionato(
        utente: Any, nome: Any, campionato: Any, *, sostituisci: bool = False
    ) -> ConfigPreset:
        """«Salva come preset» dalla pagina di un campionato che esiste già."""
        return ConfigPresetService.salva(
            utente,
            nome,
            TipoPreset.CAMPIONATO,
            formato.dal_campionato(campionato),
            formato.listino_del_campionato(campionato),
            sostituisci=sostituisci,
        )

    @staticmethod
    @transactional(domain="preset")
    def rinomina(preset_id: int, utente: Any, nome: Any) -> ConfigPreset:
        """Un nome nuovo, purché libero fra i preset dell'utente."""
        preset = ConfigPresetService.get_mio(preset_id, utente)
        pulito = _nome(nome)
        if pulito != preset.name and _nome_usato(utente.id, pulito):
            raise ConflictError(
                _("Hai già un preset che si chiama «%(nome)s».", nome=pulito)
            )
        preset.name = pulito
        db.session.flush()
        return preset

    @staticmethod
    @transactional(domain="preset")
    def duplica(preset_id: int, utente: Any) -> ConfigPreset:
        """Una copia accanto all'originale, col primo nome libero.

        La copia è dell'utente e basta: non ricorda la provenienza
        dell'originale, perché non arriva da nessuno.
        """
        preset = ConfigPresetService.get_mio(preset_id, utente)
        nome = _nome_libero(utente.id, preset.name, _("(copia)"), primo_numerato=True)
        copia = _copia(preset, utente.id, nome)
        db.session.add(copia)
        db.session.flush()
        return copia

    @staticmethod
    @transactional(domain="preset")
    def cancella(preset_id: int, utente: Any) -> None:
        """Cancella il preset. Le gare nate da lì non lo sanno nemmeno."""
        preset = ConfigPresetService.get_mio(preset_id, utente)
        db.session.delete(preset)
        db.session.flush()

    @staticmethod
    @transactional(domain="preset")
    def condividi(
        preset_id: int, utente: Any, destinatari: Iterable[Any]
    ) -> List[ConfigPreset]:
        """Una copia del preset per ogni destinatario, e una notifica a ognuno.

        Solo verso direttori o admin, e mai verso sé stessi. Se il destinatario
        ha già un preset con quel nome, la copia prende il suffisso «(da X)»,
        e un numero se anche quello è preso.
        """
        from models.user.models import User

        preset = ConfigPresetService.get_mio(preset_id, utente)
        ids: List[int] = []
        for grezzo in destinatari:
            try:
                uid = int(grezzo)
            except (TypeError, ValueError):
                raise ValidationError(_("Destinatario non valido."))
            if uid not in ids:
                ids.append(uid)
        if not ids:
            raise ValidationError(_("Scegli almeno un direttore."))

        persone = []
        for uid in ids:
            if uid == utente.id:
                raise ValidationError(
                    _("Il preset è già tuo: scegli un altro direttore.")
                )
            persona = db.session.get(User, uid)
            if persona is None or getattr(persona, "is_deleted", False):
                raise NotFoundError(_("Questo utente non esiste."))
            if not _puo_avere_preset(persona):
                raise ValidationError(
                    _(
                        "%(nome)s non è un direttore: i preset si condividono "
                        "solo fra direttori.",
                        nome=persona.username,
                    )
                )
            persone.append(persona)

        adesso = utc_now()
        copie = []
        for persona in persone:
            nome = _nome_per_chi_riceve(persona.id, preset.name, utente.username)
            copia = _copia(preset, persona.id, nome)
            copia.received_from_user_id = utente.id
            copia.received_at = adesso
            db.session.add(copia)
            db.session.flush()
            _avvisa(persona.id, utente.username, nome)
            copie.append(copia)
        return copie

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


def _nome_usato(owner_id: int, nome: str) -> bool:
    return (
        ConfigPreset.query.filter(
            ConfigPreset.owner_id == owner_id, ConfigPreset.name == nome
        ).first()
        is not None
    )


def _con_coda(base: str, coda: str) -> str:
    """``base`` seguito da ``coda``, accorciando la base se serve."""
    spazio = LUNGHEZZA_MASSIMA_DEL_NOME - len(coda) - 1
    return f"{base[:max(spazio, 1)].rstrip()} {coda}"


def _nome_libero(
    owner_id: int, base: str, suffisso: str, *, primo_numerato: bool = False
) -> str:
    """Il primo nome libero: ``base suffisso``, poi ``base suffisso 2``, ``3``…

    Con ``primo_numerato`` falso si prova prima ``base`` così com'è.
    """
    if not primo_numerato and not _nome_usato(owner_id, base):
        return base
    numero = 1
    while True:
        coda = suffisso if numero == 1 else f"{suffisso} {numero}"
        candidato = _con_coda(base, coda)
        if not _nome_usato(owner_id, candidato):
            return candidato
        numero += 1


def _nome_per_chi_riceve(owner_id: int, nome: str, mittente: str) -> str:
    """Il nome della copia: lo stesso, o «(da X)» se chi riceve l'ha già.

    Il suffisso si scrive nella lingua di chi riceve: il preset è suo.
    """
    from utils.lingua import nella_lingua_di

    if not _nome_usato(owner_id, nome):
        return nome
    with nella_lingua_di(owner_id):
        suffisso = _("(da %(nome)s)", nome=mittente)
    if not _nome_usato(owner_id, _con_coda(nome, suffisso)):
        return _con_coda(nome, suffisso)
    return _nome_libero(owner_id, nome, suffisso, primo_numerato=True)


def _copia(preset: ConfigPreset, owner_id: int, nome: str) -> ConfigPreset:
    """Un preset nuovo con lo stesso contenuto: niente lo lega all'originale."""
    return ConfigPreset(
        owner_id=owner_id,
        name=nome,
        kind=preset.kind,
        payload=preset.payload,
        schema_version=preset.schema_version,
    )


def _avvisa(destinatario_id: int, mittente: str, nome: str) -> None:
    """La notifica a chi riceve, composta nella sua lingua (ADR-062)."""
    from flask_babel import lazy_gettext as _l

    from models.notification.models import NotificationPriority, NotificationType
    from models.notification.services import NotificationService

    NotificationService.create_notification(
        user_id=destinatario_id,
        notification_type=NotificationType.PRESET_SHARED,
        title=_l("Hai ricevuto un preset"),
        message=_l(
            "%(mittente)s ti ha mandato il preset «%(nome)s»: è una copia tua, "
            "la trovi fra i tuoi preset.",
            mittente=mittente,
            nome=nome,
        ),
        priority=NotificationPriority.NORMAL,
        action_url=PAGINA_DEI_PRESET,
        action_text=_l("Apri i miei preset"),
    )


#: La pagina «I miei preset»: il link della notifica. Scritto per esteso
#: perché la notifica può nascere fuori da una richiesta.
PAGINA_DEI_PRESET = "/admin/preset/"


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
