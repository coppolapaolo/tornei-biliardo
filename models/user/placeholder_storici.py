"""Gli utenti storici che sono giocatori non registrati senza saperlo (ADR-086).

Prima dell'ADR-085 chi arrivava in sala senza account se lo vedeva creare dal
direttore, con un'email e una password che poi nessuno usava. In produzione
restano utenti che hanno giocato ma non sono **mai entrati**: sono non
registrati a tutti gli effetti, e senza creatore. Segnarli ``is_placeholder``
li rende riscattabili.

I criteri sono quelli del piano, tutti insieme (``CRITERI``):

- nessuna riga in ``user_session``: non ha mai aperto una sessione;
- ``last_active_at`` NULL: nessuna richiesta autenticata registrata;
- ``onboarding_completed`` falso: l'onboarding si fa al primo accesso;
- almeno un'iscrizione: ha giocato, quindi c'è qualcosa da riscattare;
- non admin, non fittizio di una prova, non già non registrato, non cancellato.

**Chi l'ha creato** (emendamento del 2026-10-19). Il creatore non è mai stato
scritto, ma si ricostruisce dalla **prima gara** a cui il giocatore ha
partecipato (``ricostruisci_creatore``):

1. chi l'ha iscritto a quella gara, se il dato c'è (``inscribed_by_id``, dal
   2026-09-16) ed è un direttore o l'admin;
2. altrimenti, se la gara ha **un solo** direttore, quello;
3. con più direttori un creatore unico non c'è: il riscatto lo confermano
   tutti i direttori di quella gara, e lo calcola ``ClaimService.destinatari``
   al momento, senza scrivere niente;
4. senza nessuno dei tre, conferma l'admin.

Nei casi 1 e 2 il creatore va in ``created_by_id`` (``completa_creatore``),
come per i non registrati di oggi.

Lo usa ``scripts/mark_placeholder_users.py``; la scelta si rivede prima di
scrivere, perché segnato non registrato un utente non entra più (il login lo
rifiuta) finché qualcuno non lo riscatta o l'admin non toglie il segno.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from enum import Enum
from typing import Any, Callable, List, Optional, Tuple

from sqlalchemy import exists, select

from models.base import db

from .models import User
from .role_enum import UserRole
from .session_models import UserSession


def _ha_sessioni(utente: User) -> bool:
    return (
        db.session.query(UserSession.id).filter_by(user_id=utente.id).first()
        is not None
    )


def _ha_iscrizioni(utente: User) -> bool:
    from models.competition.models import Inscription

    return (
        db.session.query(Inscription.id).filter_by(user_id=utente.id).first()
        is not None
    )


#: I criteri, uno per uno: che cosa deve valere e come si dice quando non vale.
#: ``candidati_storici`` li applica tutti in SQL; ``criteri_mancanti`` li
#: rilegge per un utente solo, per dire **quale** manca.
CRITERI: List[Tuple[str, Callable[[User], bool]]] = [
    ("è l'amministratore", lambda u: u.role != UserRole.ADMIN.value),
    ("è un giocatore fittizio di una prova", lambda u: not u.is_fittizio),
    ("è già segnato non registrato", lambda u: not u.is_placeholder),
    ("è cancellato", lambda u: u.deleted_at is None),
    ("ha completato l'onboarding", lambda u: not u.onboarding_completed),
    (
        "ha un'attività registrata (last_active_at non è vuoto)",
        lambda u: u.last_active_at is None,
    ),
    ("ha aperto almeno una sessione (user_session)", lambda u: not _ha_sessioni(u)),
    ("non è iscritto a nessuna gara", _ha_iscrizioni),
]


def candidati_storici() -> List[User]:
    """Gli utenti da segnare non registrati, in ordine di id."""
    from models.competition.models import Inscription

    ha_sessioni = exists().where(UserSession.user_id == User.id)
    ha_iscrizioni = exists().where(Inscription.user_id == User.id)
    query = (
        select(User)
        .where(
            User.role != UserRole.ADMIN.value,
            User.is_fittizio.is_(False),
            User.is_placeholder.is_(False),
            User.deleted_at.is_(None),
            User.onboarding_completed.is_(False),
            User.last_active_at.is_(None),
            ~ha_sessioni,
            ha_iscrizioni,
        )
        .order_by(User.id.asc())
    )
    return list(db.session.execute(query).scalars().all())


def criteri_mancanti(utente: User) -> List[str]:
    """Perché ``utente`` non si segna: i criteri che non rispetta, in ordine.

    Vuota se li rispetta tutti, cioè se ``candidati_storici`` lo troverebbe.
    """
    return [motivo for motivo, rispettato in CRITERI if not rispettato(utente)]


def da_completare(utente: User) -> bool:
    """Vero per un non registrato storico a cui manca ancora il creatore.

    È chi lo script ha segnato prima che sapesse ricostruirlo: rilanciandolo,
    il creatore si aggiunge senza toccare altro.
    """
    return bool(
        utente.is_placeholder
        and utente.created_by_id is None
        and utente.claimed_at is None
        and utente.deleted_at is None
        and not utente.is_fittizio
    )


def storici_da_completare() -> List[User]:
    """I non registrati senza creatore e ancora da riscattare, in ordine di id."""
    from models.competition.models import Inscription

    query = (
        select(User)
        .where(
            User.is_placeholder.is_(True),
            User.created_by_id.is_(None),
            User.claimed_at.is_(None),
            User.deleted_at.is_(None),
            User.is_fittizio.is_(False),
            exists().where(Inscription.user_id == User.id),
        )
        .order_by(User.id.asc())
    )
    return list(db.session.execute(query).scalars().all())


def segna(utenti: List[User]) -> int:
    """Segna non registrati gli utenti dati. Non fa commit: decide chi chiama."""
    for utente in utenti:
        utente.is_placeholder = True
    db.session.flush()
    return len(utenti)


# ─────────────────────────────────────────────────────── chi l'ha creato


class ModoRicostruzione(str, Enum):
    """Come si è risaliti a chi conferma il riscatto di uno storico."""

    #: Chi l'ha iscritto alla prima gara, direttore o admin.
    ISCRIZIONE = "iscrizione"
    #: L'unico direttore della prima gara.
    DIRETTORE_UNICO = "direttore_unico"
    #: Più direttori: nessun creatore, confermano tutti.
    DIRETTORI = "direttori"
    #: Nessun dato utile: conferma l'admin.
    NESSUNO = "nessuno"


@dataclass(frozen=True)
class Ricostruzione:
    modo: ModoRicostruzione
    #: La prima gara a cui ha partecipato, se c'è.
    gara: Optional[Any] = None
    #: Chi conferma il riscatto: il creatore, o i direttori della prima gara.
    confermatori: List[User] = field(default_factory=list)

    @property
    def creatore(self) -> Optional[User]:
        """Il creatore unico, da scrivere in ``created_by_id``; None se non c'è."""
        if self.modo in (
            ModoRicostruzione.ISCRIZIONE,
            ModoRicostruzione.DIRETTORE_UNICO,
        ):
            return self.confermatori[0]
        return None


def _attivo(utente: Optional[User]) -> bool:
    """Una persona vera che può ancora decidere."""
    return bool(
        utente is not None
        and utente.deleted_at is None
        and not utente.is_placeholder
        and not utente.is_fittizio
    )


def prima_iscrizione(utente: User) -> Optional[Any]:
    """L'iscrizione alla prima gara giocata: per data e ora della gara.

    Le iscrizioni ritirate valgono solo se non ce ne sono altre: «la prima
    gara a cui ha partecipato» è una a cui ha giocato, se ce n'è una.
    """
    from models.competition.models import Gara, Inscription

    righe = db.session.execute(
        select(Inscription, Gara)
        .join(Gara, Gara.id == Inscription.gara_id)
        .where(Inscription.user_id == utente.id)
    ).all()
    if not righe:
        return None
    giocate = [r for r in righe if not r[0].is_withdrawn] or list(righe)
    giocate.sort(key=lambda r: (r[1].date, r[1].time or time.min, r[0].id))
    return giocate[0][0]


def ricostruisci_creatore(utente: User) -> Ricostruzione:
    """Chi conferma il riscatto di uno storico, dalla sua prima gara."""
    from models.competition.direzione import direzione_della_gara

    iscrizione = prima_iscrizione(utente)
    if iscrizione is None:
        return Ricostruzione(ModoRicostruzione.NESSUNO)
    gara = iscrizione.gara
    direttori = [
        d.utente
        for d in direzione_della_gara(gara)
        if _attivo(d.utente) and not d.utente.is_admin and d.utente.id != utente.id
    ]

    chi_ha_iscritto = (
        db.session.get(User, iscrizione.inscribed_by_id)
        if iscrizione.inscribed_by_id and iscrizione.inscribed_by_id != utente.id
        else None
    )
    if (
        chi_ha_iscritto is not None
        and _attivo(chi_ha_iscritto)
        and (
            chi_ha_iscritto.is_admin
            or chi_ha_iscritto.is_director
            or chi_ha_iscritto.id in {d.id for d in direttori}
        )
    ):
        return Ricostruzione(ModoRicostruzione.ISCRIZIONE, gara, [chi_ha_iscritto])
    if len(direttori) == 1:
        return Ricostruzione(ModoRicostruzione.DIRETTORE_UNICO, gara, direttori)
    if direttori:
        return Ricostruzione(ModoRicostruzione.DIRETTORI, gara, direttori)
    return Ricostruzione(ModoRicostruzione.NESSUNO, gara)


def completa_creatore(utente: User) -> Ricostruzione:
    """Scrive il creatore ricostruito, se è unico. Non fa commit.

    Idempotente: un utente che il creatore ce l'ha già non si tocca.
    """
    ricostruzione = ricostruisci_creatore(utente)
    creatore = ricostruzione.creatore
    if utente.created_by_id is None and creatore is not None:
        utente.created_by_id = creatore.id
        db.session.flush()
    return ricostruzione
