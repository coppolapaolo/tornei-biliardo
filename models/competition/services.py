"""
Module: models/competition/services
Purpose: Service layer per il dominio Competition (Prova, Inscription) +
         state machine per le transizioni di stato di Prova.
Data Structures: ProvaService, ProvaStateMachine, InscriptionService
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
from models.status_enum import ProvaStatus
from .models import Prova, Inscription


class InvalidTransitionError(ValueError):
    """Errore per transizioni di stato non ammesse."""


class ProvaStateMachine:
    """Regole di transizione per `Prova.status`.

    Stati persistiti ammessi: setup → inscription ↔ setup → playing → completed.
    - setup → inscription: apertura iscrizioni
    - inscription → setup: riapertura setup (es. modifica date/config)
    - inscription → playing: inizio partite
    - playing → completed: chiusura prova
    """

    @staticmethod
    def _require(prova: Prova, expected: ProvaStatus) -> None:
        if (prova.status or ProvaStatus.SETUP) != expected.value:
            raise InvalidTransitionError(
                f"Transizione non ammessa: {prova.status!r} → "
                f"{expected.name.lower()} richiesta come stato corrente."
            )

    @staticmethod
    def to_inscription(prova: Prova) -> Prova:
        """setup → inscription"""
        ProvaStateMachine._require(prova, ProvaStatus.SETUP)
        prova.status = ProvaStatus.INSCRIPTION.value
        prova.updated_at = getattr(prova, "updated_at", None) or None  # compat
        db.session.add(prova)
        db.session.commit()
        return prova

    @staticmethod
    def reopen_setup(prova: Prova) -> Prova:
        """inscription → setup"""
        ProvaStateMachine._require(prova, ProvaStatus.INSCRIPTION)
        prova.status = ProvaStatus.SETUP.value
        db.session.add(prova)
        db.session.commit()
        return prova

    @staticmethod
    def start_playing(prova: Prova) -> Prova:
        """inscription → playing.
        Esegue controlli minimi: se disponibile, verifica numero iscritti >= 2.
        """
        ProvaStateMachine._require(prova, ProvaStatus.INSCRIPTION)

        # Controllo soft sul numero di iscritti (se relazione disponibile)
        min_required = 2
        try:
            count = len(prova.inscriptions)  # type: ignore[attr-defined]
        except Exception:
            count = None
        if count is not None and count < min_required:
            raise InvalidTransitionError(
                "Numero iscritti insufficiente per iniziare (min 2)."
            )

        prova.status = ProvaStatus.PLAYING.value
        # Se il modello espone current_round/rounds_count, inizializza con cautela
        if hasattr(prova, "current_round") and getattr(prova, "current_round") in (
            None,
            0,
        ):
            try:
                setattr(prova, "current_round", 1)
            except Exception:
                pass
        db.session.add(prova)
        db.session.commit()
        return prova

    @staticmethod
    def complete(prova: Prova) -> Prova:
        """playing → completed"""
        ProvaStateMachine._require(prova, ProvaStatus.PLAYING)
        prova.status = ProvaStatus.COMPLETED.value
        db.session.add(prova)
        db.session.commit()
        return prova


class ProvaService:
    """Operazioni di business su Prova (creazione, query, validazione, transizioni)."""

    # -----------------------------
    # CREAZIONE / QUERY DI SUPPORTO
    # -----------------------------
    @staticmethod
    def create_prova(
        number: int,
        name: str,
        date,
        discipline: str,
        distance: int,
        tournament_id: Optional[int] = None,
        director_id: Optional[int] = None,
        **kwargs,
    ) -> Prova:
        # Guard: una Prova deve appartenere a un torneo o avere un direttore esplicito
        if not tournament_id and not director_id:
            raise ValueError(
                "Una Prova deve avere un tournament_id o un director_id (standalone)."
            )

        """Crea una Prova (anche standalone se `tournament_id` è None)."""
        prova = Prova(
            number=number,
            name=name,
            date=date,
            discipline=discipline,
            distance=distance,
            tournament_id=tournament_id,
            director_id=director_id,
            **kwargs,
        )
        db.session.add(prova)
        db.session.commit()
        return prova

    @staticmethod
    def get_director_provas(director_id: int):
        """
        Restituisce le Prove dove l'utente è:
        - direttore esplicito (Prova.director_id)
        - oppure Tournament Director del torneo (via TournamentDirector)
        """
        # import locale per evitare cicli
        from models.user.models import TournamentDirector

        # Subquery degli id torneo in cui l'utente è Tournament Director
        td_subq = (
            db.session.query(TournamentDirector.tournament_id)
            .filter(TournamentDirector.user_id == director_id)
            .subquery()
        )

        q = Prova.query.filter(
            (Prova.director_id == director_id)
            | (Prova.tournament_id.in_(select(td_subq)))
        ).order_by(Prova.date.desc(), Prova.number.asc())
        return q.all()

    # -----------------------------
    # VALIDAZIONE DATI (type-safe)
    # -----------------------------
    @staticmethod
    def validate_prova_data(data: dict) -> dict:
        """
        Valida i campi della Prova e restituisce un dict di errori {campo: messaggio}.
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
                    errors["number"] = "Numero prova deve essere almeno 1"
            except (TypeError, ValueError):
                errors["number"] = "Numero prova non valido"

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
        prova_id: int,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> Prova:
        prova = db.session.get(Prova, prova_id)
        if not prova:
            raise ValueError(f"Prova {prova_id} non trovata")

        prova = ProvaStateMachine.to_inscription(prova)

        # Validazione finestra (se entrambe presenti)
        if start is not None and end is not None and start > end:
            raise ValueError(
                "La data di inizio deve essere precedente alla data di fine!"
            )

        # Imposta campi data se forniti (parte della stessa transazione)
        if start is not None:
            prova.inscription_start = start
        if end is not None:
            prova.inscription_end = end

        return prova

    @staticmethod
    def reopen_setup(prova_id: int) -> Prova:
        prova = db.session.get(Prova, prova_id)
        if not prova:
            raise ValueError(f"Prova {prova_id} non trovata")
        return ProvaStateMachine.reopen_setup(prova)

    @staticmethod
    def start_playing(prova_id: int) -> Prova:
        prova = db.session.get(Prova, prova_id)
        if not prova:
            raise ValueError(f"Prova {prova_id} non trovata")
        return ProvaStateMachine.start_playing(prova)

    @staticmethod
    def complete(prova_id: int) -> Prova:
        prova = db.session.get(Prova, prova_id)
        if not prova:
            raise ValueError(f"Prova {prova_id} non trovata")
        return ProvaStateMachine.complete(prova)


class InscriptionService:
    """Operazioni di business su Inscription."""

    @staticmethod
    def inscribe_user(user_id: int, prova_id: int) -> Optional[Inscription]:
        """Registra un utente a una prova se non già iscritto."""
        existing = Inscription.query.filter_by(
            user_id=user_id, prova_id=prova_id
        ).first()
        if existing:
            return existing
        ins = Inscription(user_id=user_id, prova_id=prova_id)
        db.session.add(ins)
        db.session.commit()
        return ins

    @staticmethod
    def uninscribe_user(user_id: int, prova_id: int) -> bool:
        """Cancella l'iscrizione di un utente dalla prova.

        Returns: True se rimossa, False se non trovata.
        """
        inscription = Inscription.query.filter_by(
            user_id=user_id, prova_id=prova_id
        ).first()
        if inscription:
            db.session.delete(inscription)
            db.session.commit()
            return True
        return False


__all__ = [
    "ProvaService",
    "InscriptionService",
    "ProvaStateMachine",
    "InvalidTransitionError",
]
