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
- almeno un'iscrizione a una **gara viva**: ha giocato, quindi c'è qualcosa
  da riscattare;
- non admin, non fittizio di una prova, non già non registrato, non cancellato.

**Gara viva** (emendamento del 2026-10-25, ``gara_viva``): non eliminata
(``Gara.deleted_at`` NULL), non di prova, e — se fa parte di un campionato —
con il campionato anch'esso non eliminato e non di prova. È ciò che l'app
mostra ancora: una gara eliminata sparisce ovunque, e la gara di un campionato
eliminato non ha più una pagina da cui arrivarci. Le prove (ADR-058) si
escludono per coerenza: un giocatore vero non vi si può iscrivere, e i
fittizi sono già fuori per ``is_fittizio``. Il 25/10/2026 la prova generale in
produzione elencava otto account di prova iscritti **solo** a gare eliminate:
segnati, sarebbero diventati riscattabili senza niente da riscattare.

La condizione è scritta per esteso, senza contare sui filtri di sessione
(soft delete, prove): quei filtri sono ``with_loader_criteria`` e valgono solo
per le entità **presenti nella query**. La ``exists()`` sulle sole iscrizioni
non nominava ``Gara`` e contava tutto, mentre ``prima_iscrizione``, che fa la
join, le gare eliminate le perdeva: per quegli utenti lo script segnava e poi
diceva «nessun creatore ricostruibile».

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
from typing import Any, Callable, List, Optional, Tuple, Union

from sqlalchemy import and_, exists, or_, select

from models.base import db

from .models import User
from .role_enum import UserRole
from .session_models import UserSession


def _ha_sessioni(utente: User) -> bool:
    return (
        db.session.query(UserSession.id).filter_by(user_id=utente.id).first()
        is not None
    )


def gara_viva() -> Any:
    """La condizione SQL su ``Gara`` di una gara che l'app mostra ancora.

    Non eliminata, non di prova, e fuori da un campionato oppure dentro uno
    non eliminato e non di prova. Vedi la docstring del modulo.
    """
    from models.campionato.models import Campionato
    from models.competition.models import Gara

    campionato_vivo = exists().where(
        Campionato.id == Gara.campionato_id,
        Campionato.deleted_at.is_(None),
        Campionato.is_prova.is_(False),
    )
    return and_(
        Gara.deleted_at.is_(None),
        Gara.is_prova.is_(False),
        or_(Gara.campionato_id.is_(None), campionato_vivo),
    )


def ha_iscrizioni_vive(user_id: Any) -> Any:
    """``exists()`` di un'iscrizione di ``user_id`` a una gara viva.

    ``user_id`` è una colonna (``User.id``, nella query dei candidati) o un
    valore: la stessa espressione serve alla query e al controllo per utente.
    """
    from models.competition.models import Gara, Inscription

    return exists().where(
        Inscription.user_id == user_id,
        Gara.id == Inscription.gara_id,
        gara_viva(),
    )


def _ha_iscrizioni(utente: User) -> bool:
    return bool(db.session.scalar(select(ha_iscrizioni_vive(utente.id))))


def iscrizioni_vive(utente: User) -> int:
    """Quante iscrizioni di ``utente`` sono a gare vive: per l'elenco."""
    from sqlalchemy import func

    from models.competition.models import Gara, Inscription

    return int(
        db.session.scalar(
            select(func.count(Inscription.id))
            .join(Gara, Gara.id == Inscription.gara_id)
            .where(Inscription.user_id == utente.id, gara_viva())
        )
        or 0
    )


def _motivo_iscrizioni(utente: User) -> str:
    from models.competition.models import Inscription

    ne_ha = db.session.scalar(select(exists().where(Inscription.user_id == utente.id)))
    return SOLO_GARE_ELIMINATE if ne_ha else "non è iscritto a nessuna gara"


#: Il motivo di chi ha iscrizioni, ma nessuna a una gara viva.
SOLO_GARE_ELIMINATE = (
    "è iscritto solo a gare eliminate (o di un campionato eliminato, o di prova)"
)

Motivo = Union[str, Callable[[User], str]]

#: I criteri, uno per uno: che cosa deve valere e come si dice quando non vale
#: (una frase, o una funzione che la sceglie guardando l'utente).
#: ``candidati_storici`` li applica tutti in SQL; ``criteri_mancanti`` li
#: rilegge per un utente solo, per dire **quale** manca.
CRITERI: List[Tuple[Motivo, Callable[[User], bool]]] = [
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
    (_motivo_iscrizioni, _ha_iscrizioni),
]


def candidati_storici() -> List[User]:
    """Gli utenti da segnare non registrati, in ordine di id."""
    ha_sessioni = exists().where(UserSession.user_id == User.id)
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
            ha_iscrizioni_vive(User.id),
        )
        .order_by(User.id.asc())
    )
    return list(db.session.execute(query).scalars().all())


def criteri_mancanti(utente: User) -> List[str]:
    """Perché ``utente`` non si segna: i criteri che non rispetta, in ordine.

    Vuota se li rispetta tutti, cioè se ``candidati_storici`` lo troverebbe.
    """
    return [
        motivo(utente) if callable(motivo) else motivo
        for motivo, rispettato in CRITERI
        if not rispettato(utente)
    ]


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
    """I non registrati senza creatore e ancora da riscattare, in ordine di id.

    Solo chi ha una gara viva: senza, non c'è una prima gara da cui
    ricostruire il creatore.
    """
    query = (
        select(User)
        .where(
            User.is_placeholder.is_(True),
            User.created_by_id.is_(None),
            User.claimed_at.is_(None),
            User.deleted_at.is_(None),
            User.is_fittizio.is_(False),
            ha_iscrizioni_vive(User.id),
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

    Solo fra le gare vive (``gara_viva``), le stesse che fanno di un utente
    un candidato. Le iscrizioni ritirate valgono solo se non ce ne sono altre:
    «la prima gara a cui ha partecipato» è una a cui ha giocato, se ce n'è una.
    """
    from models.competition.models import Gara, Inscription

    righe = db.session.execute(
        select(Inscription, Gara)
        .join(Gara, Gara.id == Inscription.gara_id)
        .where(Inscription.user_id == utente.id, gara_viva())
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
