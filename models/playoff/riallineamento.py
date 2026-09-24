"""Riallinea gli inviti ai playoff già partiti alla classifica in pagina.

Serve quando gli inviti sono partiti da una classifica sbagliata. È successo
al campionato 5 il 24/09/2026: `start_playoff` legge le righe `Classification`,
che non contavano la X come vittoria (PR #550), e l'ottavo posto è andato a
RIZA invece che a serpico67, ottavo in pagina.

La classifica di riferimento è quella **in pagina**
(`righe_della_classifica_in_pagina`): è quella che vedono tutti, e quella da
cui la zona playoff segnava chi sarebbe stato invitato. Chi invitare lo decide
la stessa funzione di `start_playoff`, `PlayoffService.candidati_per_posizione`,
con le stesse fasce, gare minime e rimpiazzi.

Quello che è già successo dopo l'avvio si rispetta:

* chi ha **rifiutato** o ha lasciato **scadere** l'invito resta fuori, e il suo
  posto va al primo degli esclusi, come nella cascata dei rifiuti;
* chi è stato **aggiunto a mano** dal direttore resta com'è: è una sua
  decisione, e sta fuori dal conto dei posti anche in `admin_add_player`.

Per chi entra: un invito normale, con la stessa scadenza degli altri e la
notifica di sempre. Per chi esce: l'invito passa a `REPLACED`, con accanto chi
l'ha preso (`replaced_by_id`), il vecchio avviso scade e ne arriva uno che
spiega perché. Se la gara di playoff esiste già ed era iscritto, ne esce.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..base import db, utc_now
from ..exceptions import ConflictError, NotFoundError
from ..transaction.manager import transactional
from .models import PlayoffConfiguration, PlayoffQualification, QualificationStatus

#: Chi è uscito per conto suo: il suo posto è già passato ad altri.
_USCITI = (QualificationStatus.DECLINED, QualificationStatus.EXPIRED)
#: Un invito che conta ancora.
_VIVI = (QualificationStatus.PENDING, QualificationStatus.CONFIRMED)
_MANUALE = "Aggiunto manualmente"


@dataclass
class Ritiro:
    qualification_id: int
    user_id: int
    username: str
    posizione_invito: int
    posizione_in_pagina: Optional[int]
    stato: str
    al_suo_posto: Optional[str] = None


@dataclass
class NuovoInvito:
    user_id: int
    username: str
    posizione: int
    motivo: str


@dataclass
class Riallineamento:
    config_id: int
    config_nome: str
    campionato_id: int
    scadenza: Any
    attesi: List[NuovoInvito] = field(default_factory=list)
    da_ritirare: List[Ritiro] = field(default_factory=list)
    da_invitare: List[NuovoInvito] = field(default_factory=list)
    eseguito: bool = False

    @property
    def niente_da_fare(self) -> bool:
        return not self.da_ritirare and not self.da_invitare

    def as_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict

        dati = asdict(self)
        dati["niente_da_fare"] = self.niente_da_fare
        return dati


def _manuale(q: PlayoffQualification) -> bool:
    return (q.qualification_reason or "").startswith(_MANUALE)


def _username(user_id: int) -> str:
    from ..user.models import User

    utente = db.session.get(User, user_id)
    return utente.username if utente else f"#{user_id}"


def pianifica(config_id: int) -> Riallineamento:
    """Cosa cambierebbe, senza scrivere niente."""
    from .services import PlayoffService
    from .zona import righe_della_classifica_in_pagina

    config = db.session.get(PlayoffConfiguration, config_id)
    if config is None:
        raise NotFoundError(f"Configurazione playoff {config_id} non trovata")
    # Il filtro della soft delete nasconde il campionato eliminato anche qui.
    if config.campionato is None:
        raise NotFoundError(
            f"Il campionato {config.campionato_id} di questo playoff è stato eliminato"
        )
    if PlayoffService._gara_avviata(config):
        raise ConflictError(
            "La gara di playoff è già cominciata: gli inviti non si toccano più"
        )

    qualifiche = PlayoffQualification.query.filter_by(configuration_id=config.id).all()
    if not any(q.invited_at is not None for q in qualifiche):
        raise ConflictError(
            "Gli inviti di questo playoff non sono ancora partiti: "
            "li sceglierà l'avvio dei playoff"
        )

    righe = righe_della_classifica_in_pagina(config.campionato)
    posizione_in_pagina = {r.user_id: r.position for r in righe}
    usciti = {q.user_id for q in qualifiche if q.status in _USCITI}
    righe_utili = [r for r in righe if r.user_id not in usciti]

    if config.positions_from is not None and config.positions_to is not None:
        scelti = PlayoffService.candidati_per_posizione(config, righe_utili)
    else:
        scelti = [
            (d["user_id"], d["position"], d["qualification_reason"])
            for d in config.evaluate_qualifications(classifications=righe_utili)
        ]
    attesi = [
        NuovoInvito(user_id=u, username=_username(u), posizione=p, motivo=m)
        for u, p, m in scelti
    ]
    id_attesi = {a.user_id for a in attesi}
    con_qualifica = {q.user_id for q in qualifiche}

    piano = Riallineamento(
        config_id=config.id,
        config_nome=config.name,
        campionato_id=config.campionato_id,
        scadenza=config.response_deadline,
        attesi=attesi,
    )
    piano.da_invitare = [a for a in attesi if a.user_id not in con_qualifica]
    piano.da_ritirare = [
        Ritiro(
            qualification_id=q.id,
            user_id=q.user_id,
            username=_username(q.user_id),
            posizione_invito=q.qualifying_position,
            posizione_in_pagina=posizione_in_pagina.get(q.user_id),
            stato=q.status.value,
        )
        for q in sorted(qualifiche, key=lambda q: q.qualifying_position or 0)
        if q.status in _VIVI
        and q.invited_at is not None
        and not _manuale(q)
        and q.user_id not in id_attesi
    ]
    # Chi entra prende il posto di chi esce, nell'ordine: serve solo a
    # scrivere «al suo posto» nella pagina del direttore.
    for ritiro, invito in zip(piano.da_ritirare, piano.da_invitare):
        ritiro.al_suo_posto = invito.username
    return piano


@transactional(domain="playoff")
def esegui(config_id: int) -> Riallineamento:
    """Ritira gli inviti sbagliati e manda quelli mancanti."""
    from .services import PlayoffService

    piano = pianifica(config_id)
    if piano.niente_da_fare:
        return piano

    config = db.session.get(PlayoffConfiguration, config_id)
    assert config is not None  # verificato da pianifica
    adesso = utc_now()

    nuovi: List[PlayoffQualification] = []
    for invito in piano.da_invitare:
        qual = PlayoffQualification(
            configuration_id=config.id,
            user_id=invito.user_id,
            qualifying_position=invito.posizione,
            qualification_reason=invito.motivo,
            invited_at=adesso,
            expires_at=config.response_deadline,
        )
        db.session.add(qual)
        nuovi.append(qual)

    for indice, ritiro in enumerate(piano.da_ritirare):
        qual = db.session.get(PlayoffQualification, ritiro.qualification_id)
        assert qual is not None
        if config.gara is not None and qual.status == QualificationStatus.CONFIRMED:
            from ..competition.inscription_service import InscriptionService

            InscriptionService.uninscribe_user(qual.user_id, config.gara.id)
        qual.status = QualificationStatus.REPLACED
        qual.responded_at = adesso
        qual.qualification_reason = (
            "Invito ritirato: era partito da una classifica calcolata male "
            f"(era: {qual.qualification_reason})"
        )
        if indice < len(piano.da_invitare):
            subentra = piano.da_invitare[indice]
            qual.replaced_by_id = subentra.user_id
            qual.replacement_position = subentra.posizione

    db.session.flush()
    for ritiro in piano.da_ritirare:
        _avvisa_del_ritiro(config, ritiro, adesso)
    PlayoffService._send_playoff_invitations(config, nuovi)

    piano.eseguito = True
    return piano


def _avvisa_del_ritiro(
    config: PlayoffConfiguration, ritiro: Ritiro, adesso: Any
) -> None:
    """Fa scadere il vecchio avviso d'invito e ne manda uno che spiega."""
    from flask_babel import lazy_gettext as _l

    from ..notification.models import (
        Notification,
        NotificationPriority,
        NotificationType,
    )
    from ..notification.services import NotificationService

    vecchi = Notification.query.filter_by(
        user_id=ritiro.user_id, notification_type=NotificationType.PLAYOFF_INVITATION
    ).all()
    for avviso in vecchi:
        if avviso.get_related_entities().get("qualification_id") == (
            ritiro.qualification_id
        ):
            avviso.expires_at = adesso

    campionato = config.campionato.name if config.campionato else ""
    # Ogni destinatario lo legge nella sua lingua (ADR-062).
    NotificationService.create_notification(
        user_id=ritiro.user_id,
        notification_type=NotificationType.PLAYOFF_INVITATION,
        title=_l("Invito ai playoff ritirato — %(nome)s", nome=config.name),
        message=_l(
            "L'invito a %(nome)s del campionato %(campionato)s è partito da una "
            "classifica calcolata male e non è più valido. Ci scusiamo per "
            "l'errore.",
            nome=config.name,
            campionato=campionato,
        ),
        priority=NotificationPriority.HIGH,
        action_url=f"/player/playoff/invitation/{ritiro.qualification_id}",
        action_text=_l("Vedi l'invito"),
        related_entities={
            "campionato_id": config.campionato_id,
            "configuration_id": config.id,
            "qualification_id": ritiro.qualification_id,
        },
    )


__all__ = ["Riallineamento", "Ritiro", "NuovoInvito", "pianifica", "esegui"]
