"""
Module: models/status_enum
Purpose: Definizione centralizzata degli *status* applicativi come Enum string-based.
Data Structures: GaraStatus, ProvaDerivedStatus, TournamentStatus, MatchStatus,
                 DirectorRequestStatus, PlayoffConfirmationStatus
Dependencies: Solo stdlib (enum, typing)

Note di migrazione (soft):
- Gli Enum ereditano da `str` per mantenere piena retrocompatibilità con il DB
  (colonne VARCHAR). Nessun DDL richiesto in questo sprint.
- Gli status "derived" di Gara NON sono persistiti: servono a UI/flow.
"""

from __future__ import annotations

from enum import Enum
from typing import Tuple, Type, TypeVar

from flask_babel import gettext as _

__all__ = [
    "GaraStatus",
    "ProvaDerivedStatus",
    "TournamentStatus",
    "MatchStatus",
    "DirectorRequestStatus",
    "VenueManagerRequestStatus",
    "RoleRequestStatus",
    "RoleRequestRecipientStatus",
    "ExamAttemptMode",
    "ExamAttemptStatus",
    "ExamRequestStatus",
    "ExamRequestRecipientStatus",
    "PlayoffConfirmationStatus",
    "Discipline",
    "WithdrawPolicy",
    "EntityType",
    "choices",
    "parse_enum",
]


class _StrEnum(str, Enum):
    """Enum di stringhe: compatibile con JSON, logging e confronti diretti."""

    def __str__(self) -> str:  # pragma: no cover – banale
        return str(self.value)


# ──────────────────────────────────────────────────────────────────────────────
# GARA
# Persistito: `gara.status` → {setup, inscription, playing, awaiting_ssr, completed}
# Derived/UI (non persistito):
#   {inscription_closed, ready_to_start, round_completed, campionato_completed}
# Fonte: models/competition/models.py
# ──────────────────────────────────────────────────────────────────────────────
class GaraStatus(_StrEnum):
    SETUP = "setup"
    INSCRIPTION = "inscription"
    PLAYING = "playing"
    AWAITING_SSR = "awaiting_ssr"  # Turni finiti, in attesa di spareggi SSR
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProvaDerivedStatus(_StrEnum):
    """Stati *derivati* (non persistiti) usati da UI/flow di Gara.

    Questi stati possono essere restituiti da funzioni di dominio (es. get_real_status)
    ma non vanno salvati nel DB.
    """

    INSCRIPTION_NOT_YET_OPEN = "inscription_not_yet_open"
    INSCRIPTION_CLOSED = "inscription_closed"
    READY_TO_START = "ready_to_start"
    ROUND_COMPLETED = "round_completed"
    TOURNAMENT_COMPLETED = "campionato_completed"


# ──────────────────────────────────────────────────────────────────────────────
# CAMPIONATO (derivato dalle Gare)
# Restituito da `Campionato.get_status()`:
#           {setup, registration_open, in_progress, completed}
# Fonte: models/campionato/models.py
# ──────────────────────────────────────────────────────────────────────────────
class TournamentStatus(_StrEnum):
    SETUP = "setup"
    REGISTRATION_OPEN = "registration_open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    TERMINATED = "terminated"


# ──────────────────────────────────────────────────────────────────────────────
# MATCH
# Persistito: `match.status` → {pending, playing, completed, validated}
#   NB: i due valori finali si chiamano CLOSED_UNILATERALLY ("completed") e
#   CONFIRMED_BY_BOTH ("validated"). Il perché di quel divario fra nome e
#   valore sta nella docstring della classe.
# Fonte: models/match/models.py
# ──────────────────────────────────────────────────────────────────────────────
class MatchStatus(_StrEnum):
    """Status for all match types (tournament and individual).

    Tournament matches: PENDING → PLAYING → uno dei due stati finali
    Individual matches: SCHEDULED → IN_PROGRESS → uno dei due stati finali
                        (oppure CANCELLED)

    I DUE STATI FINALI, E PERCHÉ SI CHIAMAVANO AL CONTRARIO
    ------------------------------------------------------
    Si chiamavano ``COMPLETED`` e ``VALIDATED``, e nessuno dei due significava
    quello che sembrava:

    * ``VALIDATED`` non era la validazione del direttore — era la chiusura
      fatta dai **due giocatori**, che confermano entrambi il punteggio;
    * ``COMPLETED`` non era il generico "finita" — era la chiusura fatta
      **senza** quella doppia firma: il direttore che valida, un forfait, un
      bye, un risultato inserito a mano, un turno importato già deciso.

    L'inversione non era un dettaglio di lessico. I due stati hanno poteri
    diversi, e il più forte è quello che si chiamava col nome più debole:
    ``ScoringService.remove_rack_for_player`` lascia annullare l'ultimo rack a
    una partita chiusa dai giocatori (è il loro accordo, possono ripensarci) e
    lo vieta a una chiusa d'ufficio (è agli atti, ci vuole il direttore). Chi
    leggeva "validated" e credeva di avere in mano lo stato più autorevole
    concludeva l'esatto contrario del vero.

    I nomi dicono ora la sola cosa che davvero distingue i due stati: **con
    quante firme** la partita è stata chiusa. Non *chi* l'ha chiusa, perché
    questo enum lo condividono anche le partite casual
    (``models/individual_match/``), dove un direttore non esiste e a chiudere
    sono un forfait o il sistema.

    I VALORI PERSISTITI RESTANO ``"completed"`` E ``"validated"``
    -------------------------------------------------------------
    Sono su ``match.status`` e ``individual_match.status`` di ogni riga già
    scritta, viaggiano nei payload JSON verso il frontend e compaiono nel
    JavaScript. Rinominare i valori è un secondo passo — migration più
    allineamento di JS e API — deliberatamente separato da questo, che è solo
    lessicale e non tocca un byte di database.

    Finché quel passo non si fa, il divario fra nome e valore resta: chi
    scrive query SQL a mano cerca ancora ``'completed'`` e ``'validated'``.
    """

    # Tournament match lifecycle
    PENDING = "pending"
    PLAYING = "playing"

    # Individual match lifecycle
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"

    # ── Stati finali ────────────────────────────────────────────────────────
    #: Chiusa **senza** la doppia conferma dei giocatori: validazione del
    #: direttore, forfait, bye, risultato inserito a mano, turno già deciso.
    #: È lo stato più forte dei due — i giocatori non possono più annullare.
    CLOSED_UNILATERALLY = "completed"

    #: Chiusa dall'accordo dei due giocatori, che hanno confermato entrambi.
    #: Resta annullabile da loro: quel che hanno concordato possono disfarlo.
    CONFIRMED_BY_BOTH = "validated"

    CANCELLED = "cancelled"

    @classmethod
    def finished_values(cls) -> Tuple[str, ...]:
        """Status values that count as 'finished' (entrambi gli stati finali)."""
        return (cls.CLOSED_UNILATERALLY.value, cls.CONFIRMED_BY_BOTH.value)

    @classmethod
    def is_finished(cls, status: str) -> bool:
        """True if the status string represents a finished match.

        Prefer this over raw ``status in ["completed", "validated"]`` checks:
        a typo'd enum member raises at import, a typo'd string fails silently.
        """
        return status in cls.finished_values()

    @classmethod
    def active_values(cls) -> Tuple[str, ...]:
        """Status values that count as 'in progress' (playing or in_progress)."""
        return (cls.PLAYING.value, cls.IN_PROGRESS.value)

    @classmethod
    def is_active(cls, status: str) -> bool:
        """True if the status string represents a match in progress."""
        return status in cls.active_values()


# ──────────────────────────────────────────────────────────────────────────────
# DIRECTOR REQUEST
# Persistito: `director_request.status` → {pending, approved, rejected}
# Fonte: models/user/models.py (DirectorRequest)
# ──────────────────────────────────────────────────────────────────────────────
class DirectorRequestStatus(_StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ──────────────────────────────────────────────────────────────────────────────
# VENUE MANAGER REQUEST
# Persistito: `venue_manager_request.status` → {pending, approved, rejected, cancelled}
# Fonte: models/user/models.py (VenueManagerRequest)
# ──────────────────────────────────────────────────────────────────────────────
class VenueManagerRequestStatus(_StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# ──────────────────────────────────────────────────────────────────────────────
# ROLE REQUEST (meccanismo generico di delega dei ruoli concedibili, ADR-041)
# Persistito: `role_request.status` → {pending, approved, rejected}
# Fonte: models/user/role_grant.py (RoleRequest)
# ──────────────────────────────────────────────────────────────────────────────
class RoleRequestStatus(_StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ──────────────────────────────────────────────────────────────────────────────
# ROLE REQUEST RECIPIENT
# Persistito: `role_request_recipient.status`
# → {pending, approved, rejected, closed}
# `closed` = un altro destinatario ha approvato per primo: la richiesta si
# chiude senza che questo destinatario si sia espresso (US-A2).
# Fonte: models/user/role_grant.py (RoleRequestRecipient)
# ──────────────────────────────────────────────────────────────────────────────
class RoleRequestRecipientStatus(_StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CLOSED = "closed"


# ──────────────────────────────────────────────────────────────────────────────
# EXAM ATTEMPT — modalità (ADR-042)
# Persistito: `exam_attempt.mode` → {self_practice, certified}
# Le due nature convivono in un solo modello, ma **solo `certified` certifica**:
# un tentativo in autonomia resta allenamento e non diventa certificato mai,
# nemmeno a posteriori.
# Fonte: models/exam/models.py (ExamAttempt)
# ──────────────────────────────────────────────────────────────────────────────
class ExamAttemptMode(_StrEnum):
    SELF_PRACTICE = "self_practice"
    CERTIFIED = "certified"


# ──────────────────────────────────────────────────────────────────────────────
# EXAM ATTEMPT — stato (ADR-042)
# Persistito: `exam_attempt.status`
# → {awaiting_player_start, in_progress, completed, abandoned}
# `awaiting_player_start` esiste **solo** in modalità certificata: nessuno può
# essere valutato a sua insaputa, quindi l'esaminatore apre la sessione ma non
# registra nulla finché il candidato non accetta l'inizio. Un tentativo in
# autonomia nasce già `in_progress`.
# `abandoned` non è una bocciatura: `passed` resta NULL.
# Fonte: models/exam/models.py (ExamAttempt)
# ──────────────────────────────────────────────────────────────────────────────
class ExamAttemptStatus(_StrEnum):
    AWAITING_PLAYER_START = "awaiting_player_start"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"

    @classmethod
    def is_open(cls, status: str) -> bool:
        """True se il tentativo è ancora aperto (non concluso né abbandonato)."""
        return status in (cls.AWAITING_PLAYER_START.value, cls.IN_PROGRESS.value)


# ──────────────────────────────────────────────────────────────────────────────
# EXAM REQUEST — appuntamento d'esame (ADR-042)
# Persistito: `exam_request.status` → {negotiating, accepted, expired, cancelled}
# Quattro stati e non cinque: «programmato» e «accettato» sono lo stesso fatto,
# perché accettare *è* fissare l'appuntamento.
# `negotiating` copre l'intero ciclo di controproposte: la richiesta resta lì
# finché uno accetta (`accepted`), il richiedente ritira (`cancelled`) o il
# tempo finisce senza accordo (`expired`).
# Fonte: models/exam/request_models.py (ExamRequest)
# ──────────────────────────────────────────────────────────────────────────────
class ExamRequestStatus(_StrEnum):
    NEGOTIATING = "negotiating"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

    @classmethod
    def is_open(cls, status: str) -> bool:
        """True se la richiesta è ancora trattabile."""
        return status == cls.NEGOTIATING.value


# ──────────────────────────────────────────────────────────────────────────────
# EXAM REQUEST RECIPIENT
# Persistito: `exam_request_recipient.status`
# → {pending, accepted, rejected, closed}
# `closed` = un altro esaminatore ha accettato per primo, quindi la richiesta si
# chiude senza che questo destinatario si sia espresso (US-E4b): è lo stato che
# distingue «ha detto di no» da «non ha fatto in tempo», e la differenza si
# vede — al secondo arriva una notifica, al primo no.
# Fonte: models/exam/request_models.py (ExamRequestRecipient)
# ──────────────────────────────────────────────────────────────────────────────
class ExamRequestRecipientStatus(_StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CLOSED = "closed"


# ──────────────────────────────────────────────────────────────────────────────
# PLAYOFF (legacy)
# Persistito: `legacy_models.Playoff.confirmation_status`
# → {pending, confirmed, declined}
# Fonte: models/legacy_models.py (Playoff)
# ──────────────────────────────────────────────────────────────────────────────
class PlayoffConfirmationStatus(_StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"


# ──────────────────────────────────────────────────────────────────────────────
# Utility generiche
# ──────────────────────────────────────────────────────────────────────────────
E = TypeVar("E", bound=_StrEnum)


class EntityType(_StrEnum):
    """Entity types for DirectorAssignment and similar relationships."""

    CAMPIONATO = "campionato"
    GARA = "gara"


# Vocabolario storico → valore canonico. Sta fuori dalla classe di proposito:
# dentro un Enum, un nome che non sia dunder o sunder diventa un **membro**, e
# comparirebbe iterando `Discipline` (rompendo `get_choices` e i menu a tendina).
_DISCIPLINE_LEGACY_ALIASES = {
    "palla_8": "8_ball",
    "palla_9": "9_ball",
    "palla_10": "10_ball",
}


class Discipline(_StrEnum):
    """Discipline di biliardo americano supportate.

    **Unico vocabolario delle discipline.** Il valore qui sotto è ciò che finisce
    su DB; il nome mostrato è una stringa tradotta, non il valore ripulito.

    Fino al 2026-08 è convissuto un vocabolario parallelo mai dichiarato
    (`palla_8`, `palla_9`, `palla_10`), nato dall'aver usato il nome italiano
    come valore persistito. Non essendo un enum, niente lo validava: le colonne
    sono `String(50)`. `normalize` è il ponte per i dati storici e per gli input
    esterni; il codice nuovo usa direttamente i membri.
    """

    EIGHT_BALL = "8_ball"
    NINE_BALL = "9_ball"
    TEN_BALL = "10_ball"
    ONE_POCKET = "one_pocket"
    STRAIGHT_POOL = "straight_pool"
    BANK_POOL = "bank_pool"
    ROTATION = "rotation"

    @property
    def display_name(self) -> str:
        """Nome mostrato, tradotto nella lingua dell'utente.

        Come nel resto del progetto il msgid è l'italiano ("Palla 8") e
        l'inglese è la traduzione ("8-Ball"). I nomi che in italiano si usano
        già in inglese (One Pocket, Straight Pool) restano identici nei due
        cataloghi: passano comunque da `gettext`, così una terza lingua non
        dovrà toccare il codice.
        """
        display_map = {
            self.EIGHT_BALL: _("Palla 8"),
            self.NINE_BALL: _("Palla 9"),
            self.TEN_BALL: _("Palla 10"),
            self.ONE_POCKET: _("One Pocket"),
            self.STRAIGHT_POOL: _("Straight Pool"),
            self.BANK_POOL: _("Bank Pool"),
            self.ROTATION: _("Rotation"),
        }
        return display_map.get(self, self.value.replace("_", " ").title())

    @classmethod
    def normalize(cls, value) -> "Discipline | None":
        """Converte un valore qualunque nel membro corrispondente.

        Accetta un membro dell'enum (idempotente), un valore canonico o un
        valore del vocabolario storico. **Restituisce `None` su valore ignoto**:
        la scelta di un ripiego spetta al chiamante e non va nascosta qui — era
        proprio il fallback silenzioso a mascherare il disallineamento.
        """
        if isinstance(value, cls):
            return value
        if not value:
            return None

        raw = str(value).strip()
        raw = _DISCIPLINE_LEGACY_ALIASES.get(raw, raw)
        try:
            return cls(raw)
        except ValueError:
            return None

    @classmethod
    def get_choices(cls) -> list[tuple[str, str]]:
        """Restituisce le scelte form/template come lista di tuple (value, label)."""
        return [(discipline.value, discipline.display_name) for discipline in cls]

    @classmethod
    def get_common_disciplines(cls) -> list["Discipline"]:
        """Restituisce le discipline più comuni."""
        return [
            cls.EIGHT_BALL,
            cls.NINE_BALL,
            cls.TEN_BALL,
            cls.ONE_POCKET,
            cls.STRAIGHT_POOL,
        ]


class WithdrawPolicy(_StrEnum):
    """Policy for handling player withdrawals/forfeits."""

    FORFEIT = "Forfeit"
    EXCLUDE = "Exclude"


def choices(enum_cls: Type[E]) -> Tuple[str, ...]:
    """Restituisce la tupla delle stringhe ammesse dall'enum.

    Utile per validazioni e (in futuro) CHECK constraint DB.
    """

    return tuple(member.value for member in enum_cls)  # type: ignore[return-value]


def parse_enum(enum_cls: Type[E], value: str) -> E:
    """Parsa una stringa verso l'enum indicato, sollevando
    ValueError su valore invalido."""

    try:
        # Accesso diretto per value esatto
        return enum_cls(value)  # type: ignore[call-arg]
    except ValueError as exc:
        valid = ", ".join(choices(enum_cls))
        raise ValueError(
            f"Valore '{value}' non valido per {enum_cls.__name__}. Ammessi: {valid}."
        ) from exc
