"""La seduta: aprirla, segnare le caselle, chiuderla (ADR-067).

La seduta è un'entità (D7) e questo servizio è l'unico posto che la scrive. Il
gesto che conta è uno: **un tocco per casella**. Sul foglio di carta si scrive
una cifra per colonna e si passa alla successiva; se qui costasse «scegli,
conferma, registra» l'app perderebbe contro una penna, e questo è il metro con
cui va letto tutto il file.

Ogni casella si porta dietro la misura e il «quanto farne» che aveva quella
sera: si copiano qui, una volta, e non si rileggono più dalla voce — che
intanto può essere cambiata o essere stata ritirata.
"""

from __future__ import annotations

from typing import List, Optional

from flask_babel import gettext as _

from ..base import db, utc_now
from ..exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from ..transaction.manager import transactional
from ..user.models import User
from .measure import SheetMeasure
from .models import TrainingEntry, TrainingSession, TrainingSheet, TrainingSheetItem

#: Quanti minuti può durare una voce a tempo: una giornata, e non di più. Un
#: numero digitato male non deve entrare in un totale.
MAX_MINUTES = 1440


class TrainingSessionService:
    """Le sedute di una scheda: una alla volta, e sempre di chi le fa."""

    # ────────────────────────────────────────────────────────────────────
    # Aprire e ritrovare
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def open_session(sheet_id: int, user_id: int) -> Optional[TrainingSession]:
        """La seduta aperta su questa scheda, se c'è.

        Una sola per volta: due sedute aperte sulla stessa scheda sarebbero due
        righe del foglio compilate insieme, e nessuno si allena due volte nello
        stesso momento.
        """
        return (
            TrainingSession.query.filter_by(
                sheet_id=sheet_id, user_id=user_id, ended_at=None
            )
            .order_by(TrainingSession.started_at.desc())
            .first()
        )

    @staticmethod
    def get_session(session_id: int) -> TrainingSession:
        session = db.session.get(TrainingSession, session_id)
        if session is None:
            raise NotFoundError(_("Seduta non trovata"))
        return session

    @staticmethod
    @transactional(domain="training_sheet")
    def start(sheet_id: int, actor: User, day: Optional[str] = None) -> TrainingSession:
        """Comincia una seduta — o riprende quella lasciata aperta.

        Riprendere non è un caso particolare: è il caso normale. Il telefono si
        spegne, la sala chiude, si torna il giorno dopo. Aprirne una seconda
        spezzerebbe in due la riga del foglio.
        """
        sheet = db.session.get(TrainingSheet, sheet_id)
        if sheet is None:
            raise NotFoundError(_("Scheda non trovata"))
        if sheet.owner_id != actor.id:
            raise PermissionDeniedError(_("Questa scheda non è tua"))

        aperta = TrainingSessionService.open_session(sheet_id, actor.id)
        if aperta is not None:
            return aperta

        giorno = (day or "").strip() or None
        if giorno is not None and giorno not in sheet.days:
            raise ValidationError(_("Questo giorno non è nella scheda"))
        if sheet.uses_days and giorno is None and sheet.days:
            giorno = sheet.days[0]

        session = TrainingSession(
            sheet_id=sheet.id,
            user_id=actor.id,
            sheet_version=sheet.version or 1,
            day=giorno,
        )
        db.session.add(session)
        db.session.flush()
        return session

    # ────────────────────────────────────────────────────────────────────
    # Segnare una casella
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="training_sheet")
    def record(
        session_id: int,
        item_id: int,
        actor: User,
        *,
        variant_id: Optional[int] = None,
        value: Optional[int] = None,
        done: Optional[bool] = None,
    ) -> TrainingEntry:
        """Scrive una casella: il numero, o la spunta. Riscrivere corregge.

        Non c'è un «registra» a parte: il tocco sul numero **è** la
        registrazione, e a proteggere dall'errore c'è il tocco dopo, che
        sovrascrive. La stessa scelta dell'allenamento libero, per la stessa
        ragione — il telefono è appoggiato alla sponda.
        """
        session, item = TrainingSessionService._resolve(session_id, item_id, actor)
        misura = item.measure_kind
        variante = TrainingSessionService._check_variant(item, variant_id)

        entry = TrainingSessionService._entry(session, item, variante)
        if misura is SheetMeasure.DONE:
            if done is None:
                raise ValidationError(_("Serve dire se l'hai fatto"))
            entry.done = bool(done)
            entry.value = None
        else:
            entry.value = TrainingSessionService._check_value(item, misura, value)
            entry.done = None
        # Un numero scritto a mano azzera il conto tiro per tiro: le due
        # strade dicono la stessa cosa, e tenerne una vecchia accanto a un
        # totale nuovo darebbe una striscia che non somma al numero accanto.
        entry.marks = None
        db.session.flush()
        return entry

    @staticmethod
    @transactional(domain="training_sheet")
    def mark(
        session_id: int,
        item_id: int,
        actor: User,
        *,
        made: bool,
        variant_id: Optional[int] = None,
    ) -> TrainingEntry:
        """Segna un tiro alla volta: riuscito o sbagliato.

        Serve alle voci lunghe — trenta tiri non si contano a mente — e vale
        solo dove un tetto c'è: riusciti e partite vinte. Il numero resta
        ``value``; la striscia dice **come** ci si è arrivati.
        """
        session, item = TrainingSessionService._resolve(session_id, item_id, actor)
        misura = item.measure_kind
        if not misura.caps_value:
            raise ValidationError(
                _("Questa voce si segna con un numero, non tiro per tiro")
            )
        variante = TrainingSessionService._check_variant(item, variant_id)
        entry = TrainingSessionService._entry(session, item, variante)

        tetto = entry.target_amount
        striscia = entry.marks or ""
        if tetto is not None and len(striscia) >= tetto:
            raise ConflictError(_("Hai già segnato tutti i tiri di questa voce"))

        entry.marks = striscia + ("1" if made else "0")
        entry.value = entry.marks.count("1")
        entry.done = None
        db.session.flush()
        return entry

    @staticmethod
    @transactional(domain="training_sheet")
    def undo_mark(
        session_id: int,
        item_id: int,
        actor: User,
        *,
        variant_id: Optional[int] = None,
    ) -> Optional[TrainingEntry]:
        """Toglie l'ultimo tiro segnato. Tolto l'ultimo, la casella si svuota."""
        session, item = TrainingSessionService._resolve(session_id, item_id, actor)
        variante = TrainingSessionService._check_variant(item, variant_id)
        entry = TrainingSessionService._find_entry(session, item, variante)
        if entry is None or not entry.marks:
            raise ConflictError(_("Non c'è nessun tiro da togliere"))

        entry.marks = entry.marks[:-1]
        if entry.marks:
            entry.value = entry.marks.count("1")
            db.session.flush()
            return entry

        session.entries.remove(entry)
        db.session.flush()
        return None

    @staticmethod
    @transactional(domain="training_sheet")
    def clear(
        session_id: int,
        item_id: int,
        actor: User,
        *,
        variant_id: Optional[int] = None,
    ) -> None:
        """Svuota una casella: torna a non compilata, non a zero.

        Sono due cose diverse — uno zero è un risultato, e nel totale pesa; una
        casella vuota è una voce che non si è fatta.
        """
        session, item = TrainingSessionService._resolve(session_id, item_id, actor)
        variante = TrainingSessionService._check_variant(item, variant_id)
        entry = TrainingSessionService._find_entry(session, item, variante)
        if entry is not None:
            session.entries.remove(entry)
            db.session.flush()

    # ────────────────────────────────────────────────────────────────────
    # Chiudere
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="training_sheet")
    def close(
        session_id: int, actor: User, notes: Optional[str] = None
    ) -> TrainingSession:
        """Chiude la seduta. Da qui entra nel registro e fa media."""
        session = TrainingSessionService.get_session(session_id)
        TrainingSessionService._require_owner(session, actor)
        if not session.is_open:
            raise ConflictError(_("Questa seduta è già chiusa"))

        if notes is not None:
            session.notes = notes.strip() or None
        session.ended_at = utc_now()
        db.session.flush()
        return session

    @staticmethod
    @transactional(domain="training_sheet")
    def discard(session_id: int, actor: User) -> None:
        """Butta via una seduta in cui non si è segnato niente.

        Con delle caselle compilate non si butta: si chiude. Un allenamento
        fatto male è comunque un allenamento fatto, e cancellarlo falserebbe la
        serie di chi ci tiene.
        """
        session = TrainingSessionService.get_session(session_id)
        TrainingSessionService._require_owner(session, actor)
        if any(entry.is_filled for entry in session.entries):
            raise ConflictError(
                _("Questa seduta ha già qualcosa segnato: chiudila, non buttarla")
            )
        db.session.delete(session)

    @staticmethod
    @transactional(domain="training_sheet")
    def set_notes(
        session_id: int, actor: User, notes: Optional[str]
    ) -> TrainingSession:
        """Le note della seduta: si scrivono anche dopo averla chiusa."""
        session = TrainingSessionService.get_session(session_id)
        TrainingSessionService._require_owner(session, actor)
        session.notes = (notes or "").strip() or None
        return session

    # ────────────────────────────────────────────────────────────────────
    # Letture che servono a chiudere: soglia e serie
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def closed_sessions(
        sheet_id: int, user_id: int, limit: Optional[int] = None
    ) -> List[TrainingSession]:
        """Le sedute chiuse, la più recente per prima."""
        query = TrainingSession.query.filter(
            TrainingSession.sheet_id == sheet_id,
            TrainingSession.user_id == user_id,
            TrainingSession.ended_at.isnot(None),
        ).order_by(TrainingSession.ended_at.desc())
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    @staticmethod
    def above_threshold_streak(sheet: TrainingSheet, user_id: int) -> int:
        """Quante sedute **di fila**, a partire dall'ultima, sono sopra la soglia.

        Zero se la soglia non c'è o se l'ultima è sotto: è il numero che la
        fine seduta confronta con ``sheet.threshold_streak`` per dire se il
        gradino è superato.
        """
        if sheet.threshold is None:
            return 0
        streak = 0
        for session in TrainingSessionService.closed_sessions(sheet.id, user_id):
            if session.total >= sheet.threshold:
                streak += 1
            else:
                break
        return streak

    # ────────────────────────────────────────────────────────────────────
    # Dentro
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    def _require_owner(session: TrainingSession, actor: User) -> None:
        if actor is None or getattr(actor, "id", None) != session.user_id:
            raise PermissionDeniedError(_("Questa seduta non è tua"))

    @staticmethod
    def _resolve(session_id: int, item_id: int, actor: User):
        session = TrainingSessionService.get_session(session_id)
        TrainingSessionService._require_owner(session, actor)
        if not session.is_open:
            raise ConflictError(_("Questa seduta è chiusa"))

        item = db.session.get(TrainingSheetItem, item_id)
        if item is None or item.sheet_id != session.sheet_id:
            raise NotFoundError(_("Questa voce non è di questa scheda"))
        if not item.is_active:
            raise ConflictError(_("Questa voce non fa più parte della scheda"))
        return session, item

    @staticmethod
    def _check_variant(item: TrainingSheetItem, variant_id: Optional[int]):
        """La variante deve essere di questo esercizio, e la voce deve volerla.

        Come per `record_attempt` (ADR-065): una variante di un altro esercizio
        non darebbe errore da nessuna parte — la chiave esterna è soddisfatta —
        e il numero finirebbe nella colonna sbagliata.
        """
        if variant_id is None:
            if item.per_variant and item.variants:
                raise ValidationError(_("Serve dire da che parte"))
            return None
        if not item.per_variant:
            raise ValidationError(_("Questa voce si segna in una casella sola"))
        variante = next((v for v in item.variants if v.id == variant_id), None)
        if variante is None:
            raise ValidationError(_("Questa variante non è di questo esercizio"))
        return variante

    @staticmethod
    def _find_entry(session, item, variante) -> Optional[TrainingEntry]:
        variant_id = variante.id if variante is not None else None
        return next(
            (
                entry
                for entry in session.entries
                if entry.item_id == item.id and entry.variant_id == variant_id
            ),
            None,
        )

    @staticmethod
    def _entry(session, item, variante) -> TrainingEntry:
        """La casella, creandola la prima volta con misura e «su quanto» di oggi."""
        entry = TrainingSessionService._find_entry(session, item, variante)
        if entry is not None:
            return entry
        entry = TrainingEntry(
            item_id=item.id,
            variant_id=variante.id if variante is not None else None,
            measure=item.measure,
            target_amount=item.amount,
        )
        session.entries.append(entry)
        db.session.flush()
        return entry

    @staticmethod
    def _check_value(
        item: TrainingSheetItem, misura: SheetMeasure, value: Optional[int]
    ) -> int:
        if value is None:
            raise ValidationError(_("Serve il numero"))
        if value < 0:
            raise ValidationError(_("Il numero non può essere negativo"))

        if misura.caps_value:
            tetto = item.amount
            if tetto is not None and value > tetto:
                raise ValidationError(
                    _("Al massimo %(n)s su questa voce.", n=tetto),
                )
        elif misura is SheetMeasure.MINUTES:
            if value > MAX_MINUTES:
                raise ValidationError(_("Una seduta non dura più di un giorno"))
        elif misura is SheetMeasure.SCORE:
            # Il tetto è quello dell'esercizio, l'unico che sa quanto vale al
            # massimo quella prova (ADR-042).
            massimo = getattr(item.challenge, "max_score", None)
            if massimo is not None and value > massimo:
                raise ValidationError(
                    _("Questo esercizio arriva a %(n)s.", n=massimo),
                )
        return value


__all__ = ["TrainingSessionService", "MAX_MINUTES"]
