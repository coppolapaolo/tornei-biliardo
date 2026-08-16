"""Ciclo di vita del referto TPA.

Il servizio fa tre cose e nessun'altra:

- decide **chi puo'** aprire un referto e su quali match;
- accetta i comandi del compilatore, uno alla volta, **validandoli contro il
  motore** — un comando che il tastierino non proponeva viene rifiutato, cosi'
  un client sbagliato non puo' sporcare il referto;
- tiene allineato il **punteggio del match** ai rack che il referto racconta.

Quest'ultimo punto e' la ragione per cui il referto non e' una schedina a
parte: chi lo compila non deve segnare i rack due volte, e punteggio e referto
non possono divergere.
"""

from __future__ import annotations

from typing import List, Optional

from flask_babel import gettext as _
from sqlalchemy import func

from models.base import db, utc_now
from models.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from models.individual_match.match_models import IndividualMatch, IndividualRack
from models.status_enum import Discipline, MatchStatus
from models.tpa.engine import GAME_TYPE_BY_DISCIPLINE, TpaButton, TpaState
from models.tpa.models import TpaComando, TpaReferto
from models.transaction.manager import transactional

#: Il codice feature che sblocca la funzione. Le regole vere stanno su
#: `feature_config` e le cambia l'admin dalla gestione gamification: qui c'e'
#: solo il nome con cui chiederle.
FEATURE_CODE = "tpa_scoresheet"


class TpaRefertoService:
    """Apertura, compilazione e chiusura di un referto TPA."""

    # ------------------------------------------------------------------
    # Ammissibilita'
    # ------------------------------------------------------------------

    @staticmethod
    def game_type_for(discipline: Optional[str]) -> Optional[int]:
        """Bilie del rack per una disciplina, o ``None`` se il TPA non la copre.

        Il referto Accu-Stats e' definito per le discipline a bilia designata
        con un rack di dimensione nota. One Pocket, Straight Pool e Bank Pool
        contano i punti in un altro modo: non e' che "non sono supportate", e'
        che il TPA li' non vuol dire niente.
        """
        if not discipline:
            return None
        normalized = Discipline.normalize(discipline)
        if normalized is None:
            return None
        return GAME_TYPE_BY_DISCIPLINE.get(normalized.value)

    @staticmethod
    def blocking_reason(match: IndividualMatch, user_id: int) -> Optional[str]:
        """Perche' il referto **non** si puo' aprire su questo match, se non si puo'.

        Restituisce una frase gia' tradotta e mostrabile: e' l'unico posto in
        cui vivono queste condizioni, cosi' il pulsante nascosto e la POST
        rifiutata dicono sempre la stessa cosa.
        """
        if user_id not in (match.player1_id, match.player2_id):
            return _("Il referto lo tiene uno dei due giocatori.")

        status = match.status.value if hasattr(match.status, "value") else match.status
        if status != MatchStatus.IN_PROGRESS.value:
            return _("Il referto si apre a match iniziato.")

        if TpaRefertoService.game_type_for(match.discipline) is None:
            return _(
                "Il referto TPA vale per palla 8, palla 9 e palla 10: "
                "in questa disciplina non si calcola."
            )

        if match.is_multi_set:
            return _("Il referto TPA non copre i match a set.")

        if (match.player1_score or 0) + (match.player2_score or 0) > 0:
            return _(
                "Questo match ha gia' dei rack segnati: il referto va aperto "
                "prima del primo rack."
            )

        return None

    @staticmethod
    def can_open(match: IndividualMatch, user_id: int) -> bool:
        return TpaRefertoService.blocking_reason(match, user_id) is None

    # ------------------------------------------------------------------
    # Lettura
    # ------------------------------------------------------------------

    @staticmethod
    def get_for_match(match_id: int) -> Optional[TpaReferto]:
        return TpaReferto.query.filter_by(individual_match_id=match_id).first()

    @staticmethod
    def build_state(referto: TpaReferto) -> TpaState:
        """Rigioca il registro dei comandi e restituisce lo stato del referto."""
        state = TpaState(referto.game_type)
        for comando in referto.comandi:
            TpaRefertoService._apply(state, comando.command)
        return state

    @staticmethod
    def _apply(state: TpaState, command: str) -> None:
        """Applica un comando allo stato. Non valida: valida chi scrive."""
        if command == TpaComando.END_TURN:
            state.toggle_player()
            return
        if command.startswith(TpaComando.SEAT_PREFIX):
            seat = int(command[len(TpaComando.SEAT_PREFIX) :])
            if state.current_player != seat:
                state.toggle_player()
            return
        state.annotate(command)

    # ------------------------------------------------------------------
    # Scrittura
    # ------------------------------------------------------------------

    @staticmethod
    @transactional(domain="tpa")
    def open_referto(match_id: int, user_id: int) -> TpaReferto:
        """Apre il referto e ne fa compilatore chi lo ha aperto."""
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise NotFoundError(_("Match non trovato"))

        if TpaRefertoService.get_for_match(match_id) is not None:
            raise ConflictError(_("Il referto di questo match e' gia' aperto."))

        reason = TpaRefertoService.blocking_reason(match, user_id)
        if reason:
            raise ValidationError(reason)

        game_type = TpaRefertoService.game_type_for(match.discipline)
        assert game_type is not None  # garantito da blocking_reason

        referto = TpaReferto(
            individual_match_id=match_id,
            compiler_id=user_id,
            game_type=game_type,
        )
        db.session.add(referto)
        return referto

    @staticmethod
    def _require_compiler(referto: TpaReferto, user_id: int) -> None:
        if referto.compiler_id != user_id:
            raise PermissionDeniedError(
                _("Il referto lo tiene %(name)s.", name=referto.compiler.username)
            )
        if referto.is_closed:
            raise ConflictError(_("Il referto e' chiuso."))

    @staticmethod
    @transactional(domain="tpa")
    def press(referto_id: int, user_id: int, command: str) -> TpaState:
        """Registra un comando del compilatore, dopo averlo validato.

        La validazione e' fatta **contro il motore**: si accetta solo cio' che
        il tastierino stava davvero proponendo in quel momento. Vale come
        difesa contro un client fuori sincrono e come rete per i doppi tocchi.
        """
        referto = db.session.get(TpaReferto, referto_id)
        if referto is None:
            raise NotFoundError(_("Referto non trovato"))
        TpaRefertoService._require_compiler(referto, user_id)

        state = TpaRefertoService.build_state(referto)
        TpaRefertoService._validate(state, command)
        TpaRefertoService._apply(state, command)

        next_sequence = (
            db.session.query(func.max(TpaComando.sequence))
            .filter_by(referto_id=referto.id)
            .scalar()
            or 0
        ) + 1
        db.session.add(
            TpaComando(
                referto_id=referto.id,
                sequence=next_sequence,
                command=command,
                pressed_at=utc_now(),
            )
        )

        TpaRefertoService._sync_match_score(referto, state)
        return state

    @staticmethod
    def _validate(state: TpaState, command: str) -> None:
        if command == TpaComando.END_TURN:
            if not state.can_switch_player():
                raise ValidationError(
                    _("Prima di passare il tavolo manca il perche' il turno e' finito.")
                )
            return

        if command.startswith(TpaComando.SEAT_PREFIX):
            seat = command[len(TpaComando.SEAT_PREFIX) :]
            if seat not in ("1", "2"):
                raise ValidationError(_("Giocatore non valido."))
            turn = state.turn()
            if turn.has_been_played() or not turn.is_break():
                raise ValidationError(
                    _("Chi spacca si sceglie prima di annotare la spaccata.")
                )
            return

        if not TpaButton.is_valid(command):
            raise ValidationError(_("Comando di referto sconosciuto."))
        if command not in state.available_buttons():
            raise ValidationError(_("Questo comando non e' possibile adesso."))

    @staticmethod
    @transactional(domain="tpa")
    def undo(referto_id: int, user_id: int) -> TpaState:
        """Annulla l'ultimo comando.

        Togliere l'ultimo comando e rigiocare il registro riporta allo stato
        esatto di un istante prima — comprese le bilie rimaste sul tavolo e i
        rack gia' assegnati, che tornano indietro da soli.
        """
        referto = db.session.get(TpaReferto, referto_id)
        if referto is None:
            raise NotFoundError(_("Referto non trovato"))
        TpaRefertoService._require_compiler(referto, user_id)

        comandi: List[TpaComando] = list(referto.comandi)
        if not comandi:
            raise ConflictError(_("Non c'e' niente da annullare."))

        last = comandi[-1]
        db.session.delete(last)
        referto.comandi.remove(last)

        state = TpaRefertoService.build_state(referto)
        TpaRefertoService._sync_match_score(referto, state)
        return state

    @staticmethod
    @transactional(domain="tpa")
    def close(referto_id: int, user_id: int) -> TpaReferto:
        """Chiude il referto: da qui in poi si legge e basta."""
        referto = db.session.get(TpaReferto, referto_id)
        if referto is None:
            raise NotFoundError(_("Referto non trovato"))
        if referto.compiler_id != user_id:
            raise PermissionDeniedError(
                _("Il referto lo tiene %(name)s.", name=referto.compiler.username)
            )
        if referto.is_closed:
            return referto
        referto.close()
        return referto

    # ------------------------------------------------------------------
    # Confezionamento per la pagina
    # ------------------------------------------------------------------

    @staticmethod
    def describe(
        referto: TpaReferto,
        state: Optional[TpaState] = None,
        viewer_id: Optional[int] = None,
    ) -> dict:
        """Lo stato del referto in forma mostrabile, dal punto di vista di chi guarda.

        Il motore ragiona per posti (1 e 2); qui i posti tornano ad avere un
        nome e un volto, e si dice a chi legge se puo' scrivere o solo guardare.
        """
        state = state or TpaRefertoService.build_state(referto)
        match = referto.match
        payload = state.to_dict()
        payload["referto_id"] = referto.id
        payload["match_id"] = referto.individual_match_id
        payload["closed"] = referto.is_closed
        payload["can_write"] = bool(
            viewer_id is not None
            and viewer_id == referto.compiler_id
            and not referto.is_closed
        )
        payload["compiler_id"] = referto.compiler_id
        payload["players"] = {
            1: {
                "user_id": match.player1_id if match else None,
                "name": match.player1.username if match and match.player1 else "",
            },
            2: {
                "user_id": match.player2_id if match else None,
                "name": match.player2.username if match and match.player2 else "",
            },
        }
        payload["commands"] = len(referto.comandi or [])
        return payload

    # ------------------------------------------------------------------
    # Allineamento col punteggio del match
    # ------------------------------------------------------------------

    @staticmethod
    def _sync_match_score(referto: TpaReferto, state: TpaState) -> None:
        """Porta i rack del match a coincidere con quelli che dice il referto.

        Si ragiona per differenza e non per incremento: cosi' l'annulla non ha
        bisogno di un percorso suo, e un referto e il suo match non possono
        raccontare due partite diverse.
        """
        match = referto.match
        if match is None:
            return

        changed = False
        for seat in (1, 2):
            user_id = referto.user_id_for(seat)
            if user_id is None:
                continue
            target = state.tally(seat).racks_won
            while TpaRefertoService._score_of(match, seat) < target:
                if not match.can_add_rack():
                    raise ConflictError(
                        _(
                            "Il match ha raggiunto la distanza: prima di continuare "
                            "il risultato va confermato o rifiutato."
                        )
                    )
                match.add_rack_result(user_id)
                changed = True
            while TpaRefertoService._score_of(match, seat) > target:
                TpaRefertoService._remove_last_rack(match, user_id)
                changed = True

        if not changed:
            return

        match.reset_confirmations()
        # Stessa regola del segnapunti normale: chi e' avanti conferma da solo
        # e l'avversario deve accettare. In parita' conferma chi tiene il referto.
        if match.is_ready_for_validation():
            if match.player1_score > match.player2_score:
                match.confirm_result(match.player1_id)
            elif match.player2_score > match.player1_score:
                match.confirm_result(match.player2_id)
            else:
                match.confirm_result(referto.compiler_id)

    @staticmethod
    def _score_of(match: IndividualMatch, seat: int) -> int:
        return (match.player1_score if seat == 1 else match.player2_score) or 0

    @staticmethod
    def _remove_last_rack(match: IndividualMatch, user_id: int) -> None:
        """Toglie l'ultimo rack vinto da un giocatore (cancellazione morbida)."""
        rack = (
            IndividualRack.query.filter_by(
                match_id=match.id, winner_id=user_id, is_deleted=False
            )
            .order_by(IndividualRack.rack_number.desc())
            .first()
        )
        if rack is not None:
            rack.is_deleted = True
            rack.removed_at = utc_now()
        if user_id == match.player1_id:
            match.player1_score = max(0, (match.player1_score or 0) - 1)
        else:
            match.player2_score = max(0, (match.player2_score or 0) - 1)


__all__ = ["FEATURE_CODE", "TpaRefertoService"]
