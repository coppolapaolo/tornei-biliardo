"""
Module: models/competition/services
Purpose: Service layer per il dominio Competition (Gara, Inscription) +
         state machine per le transizioni di stato di Gara.
Data Structures: GaraService, ProvaStateMachine, InscriptionService
Dependencies: models.base.db, models.competition.models, models.status_enum

Nota sprint 4 (migrazione soft):
- Le colonne DB restano VARCHAR; gli Enum sono string-based (compatibili).
- Le route non devono più assegnare .status direttamente: usare le API qui esposte.
"""

from __future__ import annotations

from typing import Optional
from datetime import date, datetime
from sqlalchemy import select

from models.base import db
from models.status_enum import GaraStatus
from .models import Gara, Inscription


from models.exceptions import InvalidTransitionError


class ProvaStateMachine:
    """Regole di transizione per `Gara.status`.

    Stati persistiti ammessi: setup → inscription ↔ setup → playing → completed.
    - setup → inscription: apertura iscrizioni
    - inscription → setup: riapertura setup (es. modifica date/config)
    - inscription → playing: inizio partite
    - playing → completed: chiusura gara
    """

    @staticmethod
    def _require(gara: Gara, expected: GaraStatus) -> None:
        if (gara.status or GaraStatus.SETUP) != expected.value:
            raise InvalidTransitionError(
                f"Transizione non ammessa: {gara.status!r} → "
                f"{expected.name.lower()} richiesta come stato corrente."
            )

    @staticmethod
    def to_inscription(gara: Gara) -> Gara:
        """setup → inscription"""
        ProvaStateMachine._require(gara, GaraStatus.SETUP)
        gara.status = GaraStatus.INSCRIPTION.value
        gara.updated_at = getattr(gara, "updated_at", None) or None  # compat
        db.session.add(gara)
        db.session.commit()
        return gara

    @staticmethod
    def reopen_setup(gara: Gara) -> Gara:
        """inscription → setup"""
        ProvaStateMachine._require(gara, GaraStatus.INSCRIPTION)
        gara.status = GaraStatus.SETUP.value
        db.session.add(gara)
        db.session.commit()
        return gara

    @staticmethod
    def start_playing(gara: Gara) -> Gara:
        """inscription → playing.
        Esegue controlli minimi: se disponibile, verifica numero iscritti >= 2.
        """
        ProvaStateMachine._require(gara, GaraStatus.INSCRIPTION)

        # Controllo soft sul numero di iscritti (se relazione disponibile)
        min_required = 2
        try:
            count = len(gara.inscriptions)  # type: ignore[attr-defined]
        except Exception:
            count = None
        if count is not None and count < min_required:
            raise InvalidTransitionError(
                "Numero iscritti insufficiente per iniziare (min 2)."
            )

        gara.status = GaraStatus.PLAYING.value
        # Se il modello espone current_round/rounds_count, inizializza con cautela
        if hasattr(gara, "current_round") and getattr(gara, "current_round") in (
            None,
            0,
        ):
            try:
                setattr(gara, "current_round", 1)
            except Exception:
                pass
        db.session.add(gara)
        db.session.commit()
        return gara

    @staticmethod
    def complete(gara: Gara) -> Gara:
        """playing → completed"""
        ProvaStateMachine._require(gara, GaraStatus.PLAYING)
        gara.status = GaraStatus.COMPLETED.value
        db.session.add(gara)
        db.session.commit()
        return gara


class GaraService:
    """Operazioni di business su Gara (creazione, query, validazione, transizioni)."""

    # -----------------------------
    # CREAZIONE / QUERY DI SUPPORTO
    # -----------------------------
    @staticmethod
    def create_gara(
        number: int,
        name: str,
        date,
        discipline: str,
        distance: int,
        campionato_id: Optional[int] = None,
        director_id: Optional[int] = None,
        **kwargs,
    ) -> Gara:
        """Crea una Gara (anche standalone se `campionato_id` è None)."""
        # Guard: una Gara deve appartenere a un campionato o avere un direttore esplicito
        if not campionato_id and not director_id:
            raise ValueError(
                "Una Gara deve avere un campionato_id o un director_id (standalone)."
            )

        gara = Gara(
            number=number,
            name=name,
            date=date,
            discipline=discipline,
            distance=distance,
            campionato_id=campionato_id,
            director_id=director_id,
            **kwargs,
        )
        db.session.add(gara)
        db.session.commit()
        return gara

    @staticmethod
    def get_gara_by_id(gara_id: int) -> Optional[Gara]:
        """Retrieve a Gara by ID using service layer.

        Args:
            gara_id: ID of the gara to retrieve

        Returns:
            Gara: The gara instance if found, None otherwise
        """
        return db.session.get(Gara, gara_id)

    @staticmethod
    def update_gara(gara_id: int, **kwargs) -> Gara:
        """Aggiorna una gara con i campi forniti."""
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        if not gara.can_be_modified():
            raise ValueError(
                "Impossibile modificare la gara: ci sono già delle iscrizioni!"
            )

        # Aggiorna solo i campi forniti
        for field, value in kwargs.items():
            if hasattr(gara, field):
                setattr(gara, field, value)

        # Gestione speciale per date
        if "date_str" in kwargs:
            from datetime import datetime

            gara.date = datetime.strptime(kwargs["date_str"], "%Y-%m-%d").date()

        db.session.commit()
        return gara

    @staticmethod
    def delete_gara(gara_id: int) -> None:
        """Cancella una gara se possibile."""
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        if not gara.can_be_deleted():
            raise ValueError(
                "Impossibile cancellare la gara: ci sono già delle iscrizioni!"
            )

        db.session.delete(gara)
        db.session.commit()

    @staticmethod
    def cancel_gara_with_notifications(gara_id: int, cancelled_by_id: int) -> None:
        """Cancella una gara inviando notifiche a tutti i partecipanti iscritti."""
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")
        
        # Verifica che la gara possa essere cancellata
        if gara.status not in ['setup', 'inscription']:
            raise ValueError("La gara non può essere cancellata in questo stato!")
            
        # Ottieni tutti gli iscritti prima di cancellare
        inscriptions = db.session.query(Inscription).filter_by(gara_id=gara_id).all()
        participant_ids = [inscription.user_id for inscription in inscriptions]
        
        # Prepara le informazioni per le notifiche
        gara_name = f"Gara {gara.number}"
        campionato_name = gara.campionato.name if gara.campionato else "Standalone"
        
        try:
            # Cancella la gara
            db.session.delete(gara)
            
            # Invia notifiche a tutti i partecipanti
            if participant_ids:
                from models.notification.services import NotificationService
                from models.notification.models import NotificationPriority
                
                message = f"La {gara_name}"
                if gara.campionato:
                    message += f" del campionato '{campionato_name}'"
                message += f" del {gara.date.strftime('%d/%m/%Y')} è stata cancellata."
                
                for participant_id in participant_ids:
                    NotificationService.create_notification(
                        user_id=participant_id,
                        title="Gara Cancellata",
                        message=message,
                        priority=NotificationPriority.HIGH,
                        created_by_id=cancelled_by_id
                    )
            
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Errore durante la cancellazione della gara: {str(e)}")

    @staticmethod
    def open_inscriptions(
        gara_id: int, inscription_start: datetime, inscription_end: datetime
    ) -> Gara:
        """Apre le iscrizioni per una gara con validazione delle date."""
        if inscription_start > inscription_end:
            raise ValueError(
                "La data di inizio deve essere precedente alla data di fine!"
            )

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        gara.inscription_start = inscription_start
        gara.inscription_end = inscription_end
        gara = ProvaStateMachine.to_inscription(gara)

        return gara

    @staticmethod
    def modify_inscription_dates(
        gara_id: int, inscription_start: datetime, inscription_end: datetime
    ) -> Gara:
        """Modifica le date di iscrizione per una gara."""
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        if not gara.can_modify_inscription_dates():
            raise ValueError(
                "Impossibile modificare le date: il primo turno è già stato avviato!"
            )

        if inscription_start > inscription_end:
            raise ValueError(
                "La data di inizio deve essere precedente alla data di fine!"
            )

        gara.inscription_start = inscription_start
        gara.inscription_end = inscription_end

        # Gestione automatica dello stato in base alle date
        now = datetime.utcnow()
        if inscription_start > now:
            gara = ProvaStateMachine.reopen_setup(gara)
        elif inscription_start <= now <= inscription_end:
            gara = ProvaStateMachine.to_inscription(gara)

        return gara

    @staticmethod
    def start_first_round(gara_id: int) -> Gara:
        """Avvia il primo turno della gara con controlli e sorteggio."""
        from models.competition.models import Inscription
        import random

        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        if gara.current_round != 0:
            raise ValueError("La gara è già iniziata!")

        # Verifica numero minimo partecipanti
        inscriptions = db.session.query(Inscription).filter_by(gara_id=gara_id).all()
        if len(inscriptions) < gara.min_participants:
            raise ValueError(
                f"Servono almeno {gara.min_participants} iscritti per avviare la gara!"
            )

        # Genera il sorteggio iniziale
        random.shuffle(inscriptions)

        # Assegna ordine sorteggio
        for i, inscription in enumerate(inscriptions, 1):
            inscription.initial_order = i

        # Crea abbinamenti primo turno
        from utils import create_round_matches  # Import locale

        create_round_matches(gara, inscriptions, 1)

        gara.current_round = 1
        gara = ProvaStateMachine.start_playing(gara)

        return gara

    @staticmethod
    def create_amalfi_round(
        gara_id: int, round_number: int
    ) -> tuple[int, int, int, int]:
        """Crea un turno Amalfi con gestione degli errori.

        Returns:
            Tuple con (total_matches, normal_matches, bye_matches, trio_matches)
        """
        from models.match.models import Match, TrioMatch
        from amalfi import create_amalfi_round_matches

        try:
            gara = db.session.get(Gara, gara_id)
            if not gara:
                raise ValueError(f"Gara {gara_id} non trovata")

            # Usa il binding Amalfi esistente
            create_amalfi_round_matches(gara, round_number)

            # Conta i risultati
            matches = (
                db.session.query(Match)
                .filter_by(gara_id=gara_id, round_number=round_number)
                .all()
            )
            normal_matches = sum(1 for m in matches if not m.is_bye and not m.is_trio)
            bye_matches = sum(1 for m in matches if m.is_bye)
            trio_matches = (
                db.session.query(TrioMatch)
                .join(Match)
                .filter(Match.gara_id == gara_id, Match.round_number == round_number)
                .count()
            )
            total_matches = len(matches)

            db.session.commit()
            return (total_matches, normal_matches, bye_matches, trio_matches)

        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Errore durante la creazione del turno: {str(e)}")

    @staticmethod
    def add_trio_rack(trio_id: int, winner_id: int) -> dict:
        """Aggiunge un rack a una partita trio con validazione.

        Returns:
            Dict con stato aggiornato del trio
        """
        from models.match.models import TrioMatch

        trio = db.session.get(TrioMatch, trio_id)
        if not trio:
            from flask import abort

            abort(404)

        # Verifica che il vincitore sia tra i giocatori del trio
        if winner_id not in [trio.player1_id, trio.player2_id, trio.player3_id]:
            raise ValueError("Vincitore non valido per questo trio")

        try:
            # Aggiungi rack e gestisci rotazione
            trio.add_rack_win(winner_id)
            db.session.commit()

            # Prepara risposta con nuovo stato
            state = trio.get_current_state()

            return {
                "success": True,
                "trio_completed": trio.is_completed,
                "winner_id": trio.winner_id,
                "current_state": {
                    "current_players": [
                        {"id": p.id, "username": p.username}
                        for p in state["current_players"]
                    ],
                    "waiting_player": {
                        "id": state["waiting_player"].id,
                        "username": state["waiting_player"].username,
                    }
                    if state["waiting_player"]
                    else None,
                    "scores": state["scores"],
                },
            }
        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Errore durante aggiunta rack: {str(e)}")

    @staticmethod
    def reset_trio(trio_id: int) -> None:
        """Reset completo di una partita trio."""
        from models.match.models import TrioMatch, Match
        from models.match.services import MatchService

        trio = db.session.get(TrioMatch, trio_id)
        if not trio:
            from flask import abort

            abort(404)

        try:
            # Reset scores
            trio.player1_racks = 0
            trio.player2_racks = 0
            trio.player3_racks = 0

            # Reset state
            trio.current_player1_id = trio.player1_id
            trio.current_player2_id = trio.player2_id
            trio.waiting_player_id = trio.player3_id
            trio.is_completed = False
            trio.winner_id = None

            # Reset match associato
            MatchService.reset_to_pending(trio.match.id, clear_validation=True)
            # Access the match object directly using db.session.get to avoid relationship property issues
            match_obj = db.session.get(Match, trio.match_id)
            if match_obj:
                match_obj.winner_id = None

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Errore durante reset trio: {str(e)}")

    @staticmethod
    def get_director_garas(director_id: int):
        """
        Restituisce le Gare dove l'utente è:
        - direttore esplicito (Gara.director_id)
        - oppure Campionato Director del campionato (via TournamentDirector)
        """
        # import locale per evitare cicli
        from models.user.models import TournamentDirector

        # Subquery degli id campionato in cui l'utente è Campionato Director
        td_subq = (
            db.session.query(TournamentDirector.campionato_id)
            .filter(TournamentDirector.user_id == director_id)
            .subquery()
        )

        q = (
            db.session.query(Gara)
            .filter(
                (Gara.director_id == director_id)
                | (Gara.campionato_id.in_(select(td_subq)))
            )
            .order_by(Gara.date.desc(), Gara.number.asc())
        )
        return q.all()

    # -----------------------------
    # VALIDAZIONE DATI (type-safe)
    # -----------------------------
    @staticmethod
    def validate_gara_data(data: dict) -> dict:
        """
        Valida i campi della Gara e restituisce un dict di errori {campo: messaggio}.
        Requisiti chiesti dai test storici:
        - max_participants < min_participants -> messaggio contiene '>= min'
        - entry_fee < 0 -> messaggio contiene 'negativa'
        - inscription_end < inscription_start -> errors['inscription_end']
        - rounds_count presente e < 1 -> errors['rounds_count']
        """
        errors: dict = {}

        # name
        name = (data.get("name") or "").strip()
        if not name:
            errors["name"] = "Nome obbligatorio"

        # discipline
        discipline = (data.get("discipline") or "").strip()
        if not discipline:
            errors["discipline"] = "Disciplina obbligatoria"

        # distance
        dist_raw = data.get("distance")
        if dist_raw in (None, ""):
            errors["distance"] = "Distanza obbligatoria"
        else:
            try:
                distance = int(dist_raw)
                if distance < 1:
                    errors["distance"] = "Distanza deve essere almeno 1"
            except (TypeError, ValueError):
                errors["distance"] = "Distanza non valida"

        # entry_fee (opzionale)
        fee_raw = data.get("entry_fee")
        if fee_raw not in (None, ""):
            try:
                fee = float(fee_raw)
                if fee < 0:
                    # test richiede la parola 'negativa'
                    errors["entry_fee"] = "Quota non può essere negativa (>= 0)"
            except (TypeError, ValueError):
                errors["entry_fee"] = "Quota deve essere un numero valido"

        # number (opzionale)
        number_raw = data.get("number")
        if number_raw not in (None, ""):
            try:
                number = int(number_raw)
                if number < 1:
                    errors["number"] = "Numero gara deve essere almeno 1"
            except (TypeError, ValueError):
                errors["number"] = "Numero gara non valido"

        # min_participants (default 2)
        min_p_raw = data.get("min_participants")
        try:
            min_p = 2 if min_p_raw in (None, "") else int(min_p_raw)
            if min_p < 2:
                errors["min_participants"] = "Minimo 2 partecipanti"
        except (TypeError, ValueError):
            errors["min_participants"] = "Numero partecipanti minimo non valido"
            min_p = None  # type: ignore[assignment]

        # max_participants (opzionale, >= min)
        max_p_raw = data.get("max_participants")
        if max_p_raw not in (None, ""):
            try:
                max_p = int(max_p_raw)
                if isinstance(min_p, int) and max_p < min_p:
                    # test richiede la sottostringa '>= min'
                    errors["max_participants"] = "Max participants deve essere >= min"
            except (TypeError, ValueError):
                errors["max_participants"] = "Numero partecipanti massimo non valido"

        # inscription dates (opzionali): end deve essere >= start
        start_raw = data.get("inscription_start")
        end_raw = data.get("inscription_end")

        def _parse_date(v):
            if not v:
                return None
            if isinstance(v, date):
                return v
            try:
                return date.fromisoformat(str(v))
            except Exception:
                return None

        # Valida formato data di inizio
        if start_raw:  # Se è fornita, deve essere valida
            start_dt = _parse_date(start_raw)
            if start_dt is None:
                errors["inscription_start"] = "Formato data non valido (usa YYYY-MM-DD)"
        else:
            start_dt = None

        # Valida formato data di fine
        if end_raw:  # Se è fornita, deve essere valida
            end_dt = _parse_date(end_raw)
            if end_dt is None:
                errors["inscription_end"] = "Formato data non valido (usa YYYY-MM-DD)"
        else:
            end_dt = None

        if start_dt and end_dt and end_dt < start_dt:
            # test verifica presenza della chiave 'inscription_end'
            errors[
                "inscription_end"
            ] = "La data di fine iscrizioni deve essere >= della data di inizio"

        # rounds_count (opzionale): >= 1
        rounds_raw = data.get("rounds_count")
        if rounds_raw not in (None, ""):
            try:
                rounds = int(rounds_raw)
                if rounds < 1:
                    errors["rounds_count"] = "Il numero di turni deve essere almeno 1"
            except (TypeError, ValueError):
                errors["rounds_count"] = "Numero di turni non valido"

        return errors

    # -----------------------------
    # STATE MACHINE FACADE
    # -----------------------------
    @staticmethod
    def to_inscription(
        gara_id: int, start: Optional[datetime] = None, end: Optional[datetime] = None
    ) -> Gara:
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")

        gara = ProvaStateMachine.to_inscription(gara)

        # Validazione finestra (se entrambe presenti)
        if start is not None and end is not None and start > end:
            raise ValueError(
                "La data di inizio deve essere precedente alla data di fine!"
            )

        # Imposta campi data se forniti (parte della stessa transazione)
        if start is not None:
            gara.inscription_start = start
        if end is not None:
            gara.inscription_end = end

        return gara

    @staticmethod
    def reopen_setup(gara_id: int) -> Gara:
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")
        return ProvaStateMachine.reopen_setup(gara)

    @staticmethod
    def start_playing(gara_id: int) -> Gara:
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")
        return ProvaStateMachine.start_playing(gara)

    @staticmethod
    def complete(gara_id: int) -> Gara:
        gara = db.session.get(Gara, gara_id)
        if not gara:
            raise ValueError(f"Gara {gara_id} non trovata")
        return ProvaStateMachine.complete(gara)


class InscriptionService:
    """Operazioni di business su Inscription."""

    @staticmethod
    def inscribe_user(user_id: int, gara_id: int) -> Optional[Inscription]:
        """Registra un utente a una gara se non già iscritto."""
        existing = (
            db.session.query(Inscription)
            .filter_by(user_id=user_id, gara_id=gara_id)
            .first()
        )
        if existing:
            return existing
        ins = Inscription(user_id=user_id, gara_id=gara_id)
        db.session.add(ins)
        db.session.commit()
        return ins

    @staticmethod
    def uninscribe_user(user_id: int, gara_id: int) -> bool:
        """Cancella l'iscrizione di un utente dalla gara.

        Returns: True se rimossa, False se non trovata.
        """
        inscription = (
            db.session.query(Inscription)
            .filter_by(user_id=user_id, gara_id=gara_id)
            .first()
        )
        if inscription:
            db.session.delete(inscription)
            db.session.commit()
            return True
        return False


__all__ = [
    "GaraService",
    "InscriptionService",
    "ProvaStateMachine",
    "InvalidTransitionError",
]
