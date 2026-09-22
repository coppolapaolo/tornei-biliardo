"""La seduta: aprirla, segnare le caselle, chiuderla (ADR-067).

La seduta è un'entità (D7) e questo servizio è l'unico posto che la scrive. Il
gesto che conta è uno: **un tocco per casella**. Sul foglio di carta si scrive
una cifra per colonna e si passa alla successiva; se qui costasse «scegli,
conferma, registra» l'app perderebbe contro una penna, e questo è il metro con
cui va letto tutto il file.

Ogni casella si porta dietro la misura e il «quanto farne» che aveva quella
sera: si copiano qui, una volta, e non si rileggono più dalla voce — che
intanto può essere cambiata o essere stata ritirata.

Dall'ADR-072 le caselle «riusciti» e «punteggio» sono fatte di **prove del
catalogo**, e nascono qui: un «4 su 5» sono cinque prove a esito netto, una
voce a punteggio si segna prova per prova (`record_score`), e una prova colpo
per colpo giocata nella schermata del catalogo torna nella casella
(`attach_attempt`). Le prove portano l'origine «scheda», e l'XP non lo pagano
loro: lo paga la seduta chiusa.
"""

from __future__ import annotations

import logging
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
from .measure import ScoreAggregation, SheetMeasure
from .models import TrainingEntry, TrainingSession, TrainingSheet, TrainingSheetItem

logger = logging.getLogger(__name__)

#: Quanti minuti può durare una voce a tempo: una giornata, e non di più. Un
#: numero digitato male non deve entrare in un totale.
MAX_MINUTES = 1440


def streak_above_threshold(sheet: TrainingSheet, sedute: List[TrainingSession]) -> int:
    """Quante delle ``sedute`` in testa stanno sopra la soglia della scheda.

    Una funzione, e non un metodo, perché ha **due** chiamanti che partono da
    punti diversi: la fine seduta, che le sedute se le va a prendere, e la
    pagina «I miei allievi», che le ha già in mano per venti schede insieme e
    non può permettersi una query a testa. La regola del gradino deve restare
    una sola: due copie che divergono direbbero a un istruttore che l'allievo
    è pronto e all'allievo di no.

    ``sedute`` arriva **dalla più recente**, come la dà ``closed_sessions``.
    """
    if sheet.threshold is None:
        return 0
    streak = 0
    for session in sedute:
        if session.total >= sheet.threshold:
            streak += 1
        else:
            break
    return streak


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
    def can_read(session: TrainingSession, actor) -> bool:
        """Chi può guardare questa seduta: chi l'ha fatta, e chi legge la scheda.

        Aggiunto con gli istruttori (ADR-069). Prima il permesso di leggere una
        scheda si fermava al registro: le sue righe portavano a una pagina che
        rispondeva 404, e un permesso che non si può esercitare non è un
        permesso — è un elenco.
        """
        if actor is None or not getattr(actor, "id", None):
            return False
        if session.user_id == actor.id:
            return True
        from .services import TrainingSheetService

        return TrainingSheetService.can_read(session.sheet, actor)

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
        if misura is SheetMeasure.SCORE and item.makes_attempts:
            # Il numero discende dalle prove (ADR-072): un totale scritto a
            # mano sarebbe un secondo segnapunti, come per il referto TPA.
            raise ValidationError(
                _("Questa voce si segna una prova alla volta, non col totale")
            )
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
        if item.makes_attempts:
            # «4 su 5» sono cinque prove: quattro riuscite e una no, tutte
            # adesso. Riscrivere la casella le rifà — sono la stessa cosa
            # detta due volte.
            TrainingSessionService._rifai_le_prove(session, entry, item, variante)
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

        if item.makes_attempts:
            # Il primo tiro dopo un totale ricomincia: le prove del totale
            # non hanno più niente da dire.
            if not striscia:
                entry.attempts.clear()
            TrainingSessionService._nuova_prova(
                session, entry, item, variante, passed=made
            )
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
        if entry.attempts:
            entry.attempts.remove(list(entry.attempts)[-1])
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
    # Le prove a punteggio (ADR-072)
    # ────────────────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="training_sheet")
    def record_score(
        session_id: int,
        item_id: int,
        actor: User,
        *,
        score: Optional[int],
        variant_id: Optional[int] = None,
    ) -> TrainingEntry:
        """Una prova a punteggio in più sulla voce: il numero della casella
        è l'aggregazione delle prove fatte finora.

        Fino a «quante prove» dice la voce. Colpo per colpo non si passa di
        qui: la prova si gioca nella schermata del catalogo e torna nella
        casella con `attach_attempt`.
        """
        from ..challenge.recording import RecordingMode

        session, item = TrainingSessionService._resolve(session_id, item_id, actor)
        TrainingSessionService._require_score_with_attempts(item)
        if RecordingMode.parse(item.challenge.recording_mode).is_sequence:
            raise ValidationError(
                _("Questo esercizio si registra colpo per colpo: aprilo dalla seduta")
            )
        variante = TrainingSessionService._check_variant(item, variant_id)
        entry = TrainingSessionService._entry(session, item, variante)
        TrainingSessionService._check_room(entry)

        punteggio = TrainingSessionService._check_score(item, score)
        TrainingSessionService._nuova_prova(
            session, entry, item, variante, score=punteggio
        )
        TrainingSessionService._aggiorna_dalle_prove(entry)
        db.session.flush()
        return entry

    @staticmethod
    @transactional(domain="training_sheet")
    def undo_score(
        session_id: int,
        item_id: int,
        actor: User,
        *,
        variant_id: Optional[int] = None,
    ) -> Optional[TrainingEntry]:
        """Toglie l'ultima prova a punteggio. Tolta l'ultima, la casella si svuota."""
        session, item = TrainingSessionService._resolve(session_id, item_id, actor)
        TrainingSessionService._require_score_with_attempts(item)
        variante = TrainingSessionService._check_variant(item, variant_id)
        entry = TrainingSessionService._find_entry(session, item, variante)
        if entry is None or not entry.attempts:
            raise ConflictError(_("Non c'è nessuna prova da togliere"))

        entry.attempts.remove(list(entry.attempts)[-1])
        if entry.attempts:
            TrainingSessionService._aggiorna_dalle_prove(entry)
            db.session.flush()
            return entry
        session.entries.remove(entry)
        db.session.flush()
        return None

    @staticmethod
    @transactional(domain="training_sheet")
    def attach_attempt(
        session_id: int,
        item_id: int,
        actor: User,
        *,
        attempt_id: int,
        variant_id: Optional[int] = None,
    ) -> TrainingEntry:
        """Aggancia alla casella una prova giocata nella schermata del catalogo.

        Serve agli esercizi colpo per colpo (ADR-066): la scheda non rifà il
        loro modo di registrare. Si aggancia **prima** della chiusura, così
        l'evento della prova completata nasce già con l'origine «scheda»; una
        prova ancora aperta non fa numero finché non si chiude
        (`refresh_from_attempts`).
        """
        from ..challenge.models import ChallengeAttempt

        session, item = TrainingSessionService._resolve(session_id, item_id, actor)
        TrainingSessionService._require_score_with_attempts(item)
        attempt = db.session.get(ChallengeAttempt, attempt_id)
        if attempt is None or attempt.user_id != actor.id:
            raise NotFoundError(_("Prova non trovata"))
        if attempt.challenge_id != item.challenge_id:
            raise ValidationError(_("Questa prova è di un altro esercizio"))
        variante = TrainingSessionService._check_variant(item, variant_id)
        entry = TrainingSessionService._entry(session, item, variante)
        if attempt.training_entry_id not in (None, entry.id):
            raise ConflictError(_("Questa prova è già di un'altra casella"))
        if attempt.training_entry_id is None:
            TrainingSessionService._check_room(entry)
            entry.attempts.append(attempt)
        TrainingSessionService._aggiorna_dalle_prove(entry)
        db.session.flush()
        return entry

    @staticmethod
    @transactional(domain="training_sheet")
    def refresh_from_attempts(
        session_id: int,
        item_id: int,
        actor: User,
        *,
        variant_id: Optional[int] = None,
    ) -> TrainingEntry:
        """Rilegge il numero della casella dalle sue prove chiuse."""
        session, item = TrainingSessionService._resolve(session_id, item_id, actor)
        variante = TrainingSessionService._check_variant(item, variant_id)
        entry = TrainingSessionService._find_entry(session, item, variante)
        if entry is None:
            raise NotFoundError(_("Questa casella non è ancora stata segnata"))
        TrainingSessionService._aggiorna_dalle_prove(entry)
        db.session.flush()
        return entry

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
        TrainingSessionService._timbra_il_gradino(session)
        TrainingSessionService._publish_closed(session)
        return session

    @staticmethod
    def _timbra_il_gradino(session: TrainingSession) -> None:
        """Se la scheda si promuove da sé, la seduta appena chiusa la promuove.

        Qui dentro e non dopo, perché il gradino discende **da questa seduta**:
        se la chiusura si annulla deve annullarsi anche il livello superato.
        L'import è locale, che `gradino` importa questo modulo.
        """
        from .gradino import GradinoService

        if session.sheet is not None:
            GradinoService.timbra_alla_soglia(session.sheet)

    @staticmethod
    def _publish_closed(session: TrainingSession) -> None:
        """Annuncia la seduta chiusa (XP, serie, traguardi — ADR-067 punto 6).

        Best-effort come per il drill: un ascoltatore che esplode non deve far
        perdere la seduta appena chiusa, che è il dato importante.
        """
        from models.events.base import EventBus

        from .events import TrainingSessionClosedEvent

        try:
            sheet = session.sheet
            soglia = sheet.threshold if sheet is not None else None
            EventBus.publish(
                TrainingSessionClosedEvent(
                    session_id=session.id,
                    sheet_id=session.sheet_id,
                    sheet_name=(sheet.name if sheet is not None else ""),
                    user_id=session.user_id,
                    filled=sum(1 for entry in session.entries if entry.is_filled),
                    total=session.total,
                    max_total=session.max_total,
                    above_threshold=(
                        None if soglia is None else session.total >= soglia
                    ),
                )
            )
        except Exception:  # pragma: no cover - la gamification non blocca mai
            logger.warning("Evento di seduta chiusa non pubblicato", exc_info=True)

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
        return streak_above_threshold(
            sheet, TrainingSessionService.closed_sessions(sheet.id, user_id)
        )

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
            aggregation=item.aggregation,
        )
        session.entries.append(entry)
        db.session.flush()
        return entry

    # ── Le prove dietro la casella (ADR-072) ──────────────────────────
    @staticmethod
    def _require_score_with_attempts(item: TrainingSheetItem) -> None:
        if item.measure_kind is not SheetMeasure.SCORE or not item.makes_attempts:
            raise ValidationError(_("Questa voce non si segna a punteggio"))

    @staticmethod
    def _check_room(entry: TrainingEntry) -> None:
        tetto = entry.target_amount
        if tetto is not None and len(entry.attempts) >= tetto:
            raise ConflictError(_("Hai già fatto tutte le prove di questa voce"))

    @staticmethod
    def _check_score(item: TrainingSheetItem, score: Optional[int]) -> int:
        if score is None:
            raise ValidationError(_("Serve il punteggio"))
        if score < 0:
            raise ValidationError(_("Il numero non può essere negativo"))
        massimo = getattr(item.challenge, "max_score", None)
        if massimo is not None and score > massimo:
            raise ValidationError(_("Questo esercizio arriva a %(n)s.", n=massimo))
        return score

    @staticmethod
    def _nuova_prova(
        session: TrainingSession,
        entry: TrainingEntry,
        item: TrainingSheetItem,
        variante,
        *,
        passed: Optional[bool] = None,
        score: Optional[int] = None,
    ):
        """Una prova del catalogo nata in questa casella, già chiusa.

        Passa da `complete_challenge_attempt` come ogni altra prova: è lì che
        si pubblica l'evento — con l'origine «scheda», perché il rimando alla
        casella c'è già — e si riconciliano i traguardi.
        """
        from ..challenge.models import ChallengeAttempt
        from ..challenge.services import ChallengeService

        attempt = ChallengeAttempt(
            user_id=session.user_id,
            challenge_id=item.challenge_id,
            variant_id=variante.id if variante is not None else None,
        )
        entry.attempts.append(attempt)
        db.session.flush()
        ChallengeService.complete_challenge_attempt(
            attempt_id=attempt.id, score=score, passed=passed
        )
        return attempt

    @staticmethod
    def _rifai_le_prove(
        session: TrainingSession,
        entry: TrainingEntry,
        item: TrainingSheetItem,
        variante,
    ) -> None:
        """Le N prove di un «k su N» scritto come totale: k riuscite, N−k no."""
        entry.attempts.clear()
        db.session.flush()
        riuscite = int(entry.value or 0)
        quante = entry.target_amount if entry.target_amount is not None else riuscite
        for indice in range(quante):
            TrainingSessionService._nuova_prova(
                session, entry, item, variante, passed=indice < riuscite
            )

    @staticmethod
    def _aggiorna_dalle_prove(entry: TrainingEntry) -> None:
        """Il numero della casella dalle prove chiuse, con l'aggregazione copiata."""
        entry.value = ScoreAggregation.parse(entry.aggregation).apply(entry.scores)
        entry.done = None
        entry.marks = None

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
