"""
Module: models/individual_match/quick_match_service.py
Purpose: avvio rapido di una sfida individuale fra due giocatori già in sala.

Il percorso normale (proposta → accettazione → avvio) è pensato per **fissare
un appuntamento**: chiede quando, dove e come, e aspetta che l'altro dica di
sì. Chi ha già la stecca in mano non ha niente da fissare, e alla domanda
«quando?» può solo rispondere «adesso» (issue #176).

Qui la partita nasce **già iniziata**: si sceglie l'avversario e si è al
segnapunti. Il resto si precompila dall'ultima partita giocata, o dalla sala in
cui il giocatore risulta disponibile, o da un default di sistema.

Perché si può fare senza che l'avversario accetti: per le sfide individuali
l'ELO si muove **solo** sulla validazione bilaterale
(``RatingEventHandlers.handle_individual_match_completed`` ascolta
``IndividualMatchCompletedEvent``, emesso da ``IndividualMatch`` solo dopo che
entrambi hanno confermato). Una partita aperta contro qualcuno che non ha mai
giocato resta quindi senza effetti sul rating finché quel qualcuno non la
riconosce: l'accettazione non sparisce, si sposta alla fine, dove la domanda
ha una risposta che l'avversario conosce davvero — il punteggio.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from flask_babel import gettext as _

from ..base import db, utc_now
from ..exceptions import ConflictError, NotFoundError, ValidationError
from ..status_enum import Discipline, MatchStatus
from ..transaction.manager import transactional
from .models import IndividualMatch

logger = logging.getLogger(__name__)


class QuickMatchService:
    """Avvio rapido di una sfida individuale (issue #176)."""

    #: Configurazione di ripiego quando il giocatore non ha uno storico da cui
    #: dedurre le sue abitudini. Stessi valori del modulo di proposta.
    SYSTEM_DEFAULTS: Dict[str, Any] = {
        "billiard_hall_id": None,
        "location": "",
        "discipline": Discipline.EIGHT_BALL.value,
        "match_format": "single",
        "distance": 5,
        "is_race_to": True,
        "match_distance": None,
        "break_rule": "alternate",
    }

    # ------------------------------------------------------------------
    # Precompilazioni
    # ------------------------------------------------------------------
    @staticmethod
    def get_defaults(user_id: int) -> Dict[str, Any]:
        """Come si giocherà, salvo diverso avviso.

        Nell'ordine: l'ultima sfida individuale di questo giocatore (che è
        anche l'ultima sala in cui ha giocato), poi la sala in cui risulta
        disponibile, poi i default di sistema. La sala si cerca anche quando
        l'ultima sfida c'è ma non aveva un luogo: sono due domande diverse.
        """
        defaults = dict(QuickMatchService.SYSTEM_DEFAULTS)

        last = (
            IndividualMatch.query.filter(
                db.or_(
                    IndividualMatch.player1_id == user_id,
                    IndividualMatch.player2_id == user_id,
                )
            )
            .order_by(IndividualMatch.created_at.desc())
            .first()
        )

        if last is not None:
            defaults.update(
                {
                    "billiard_hall_id": last.billiard_hall_id,
                    "location": last.location or "",
                    "discipline": last.discipline or defaults["discipline"],
                    "break_rule": last.break_rule or defaults["break_rule"],
                }
            )
            if last.distance is None:
                defaults["match_format"] = "free"
                defaults["distance"] = None
            elif last.is_multi_set:
                defaults["match_format"] = "multi"
                defaults["distance"] = last.distance
                defaults["match_distance"] = last.match_distance or 3
            else:
                defaults["match_format"] = "single"
                defaults["distance"] = last.distance
                defaults["is_race_to"] = bool(last.is_race_to)

        if not defaults["billiard_hall_id"] and not defaults["location"]:
            venue = QuickMatchService._available_venue(user_id)
            if venue is not None:
                defaults["billiard_hall_id"] = venue.id
                defaults["location"] = venue.name

        return defaults

    @staticmethod
    def _available_venue(user_id: int):
        """La sala in cui il giocatore si è dichiarato disponibile.

        Se ne ha più d'una vince quella dove ha giocato più di recente
        (``last_played_at``); a parità, l'ultima toccata. Restituisce la
        ``BilliardHall``, non la disponibilità: al chiamante serve il nome.
        """
        from ..location.models import BilliardHall, UserLocationAvailability

        availability = (
            UserLocationAvailability.query.filter_by(user_id=user_id, is_available=True)
            .order_by(
                UserLocationAvailability.last_played_at.desc().nullslast(),
                UserLocationAvailability.updated_at.desc(),
            )
            .first()
        )
        if availability is None:
            return None
        return db.session.get(BilliardHall, availability.billiard_hall_id)

    # ------------------------------------------------------------------
    # Avvio
    # ------------------------------------------------------------------
    @staticmethod
    def find_open_match(user_id: int, opponent_id: int) -> Optional[IndividualMatch]:
        """La sfida che questi due stanno già giocando, se c'è.

        Serve contro il doppio tocco: due partite in corso fra le stesse due
        persone non esistono al biliardo, e la seconda resterebbe lì a sporcare
        lo storico di entrambi.
        """
        return (
            IndividualMatch.query.filter(
                IndividualMatch.status == MatchStatus.IN_PROGRESS,
                db.or_(
                    db.and_(
                        IndividualMatch.player1_id == user_id,
                        IndividualMatch.player2_id == opponent_id,
                    ),
                    db.and_(
                        IndividualMatch.player1_id == opponent_id,
                        IndividualMatch.player2_id == user_id,
                    ),
                ),
            )
            .order_by(IndividualMatch.created_at.desc())
            .first()
        )

    @staticmethod
    @transactional(domain="individual_match")
    def start(
        user_id: int,
        opponent_id: int,
        config: Optional[Dict[str, Any]] = None,
    ) -> IndividualMatch:
        """Crea una sfida **già in corso** fra i due giocatori.

        ``config`` accetta le stesse chiavi di :meth:`get_defaults`; quelle
        assenti (o ``None``) si prendono da lì. Con ``config`` vuoto la
        chiamata è quella dell'avvio rapido puro: chi gioca, e basta.

        Se una sfida fra i due è già in corso, restituisce quella invece di
        aprirne un'altra.
        """
        from ..user.models import User

        if opponent_id == user_id:
            raise ValidationError(_("Non puoi giocare contro te stesso."))

        opponent = db.session.get(User, opponent_id)
        if opponent is None or opponent.deleted_at is not None:
            raise NotFoundError(_("Giocatore non trovato."))

        # Stesso filtro dell'elenco avversari e della ricerca giocatori: chi non
        # ha sbloccato le sfide individuali non le vedrebbe nemmeno arrivare.
        if not opponent.can_access("create_match_direct"):
            raise ConflictError(
                _(
                    "%(name)s non ha ancora sbloccato le sfide individuali.",
                    name=opponent.username,
                )
            )

        existing = QuickMatchService.find_open_match(user_id, opponent_id)
        if existing is not None:
            return existing

        settings = QuickMatchService._resolve_config(user_id, config)

        match = IndividualMatch(
            proposal_id=None,
            player1_id=user_id,
            player2_id=opponent_id,
            billiard_hall_id=settings["billiard_hall_id"],
            location=settings["location"] or None,
            # "Adesso" è la risposta che l'issue voleva smettere di chiedere.
            scheduled_at=utc_now(),
            status=MatchStatus.SCHEDULED,
            discipline=settings["discipline"],
            distance=settings["distance"],
            is_race_to=settings["is_race_to"],
            break_rule=settings["break_rule"],
            is_multi_set=settings["is_multi_set"],
            match_distance=settings["match_distance"],
            is_race_to_sets=True if settings["is_multi_set"] else None,
        )
        db.session.add(match)
        # flush prima di `start_match()`: nel multi-set quello crea il primo set,
        # che ha bisogno dell'id della partita.
        db.session.flush()

        # Nasce SCHEDULED e parte subito: la transizione è quella di sempre, non
        # una scorciatoia che scrive lo stato a mano (nel multi-set apre il set).
        match.start_match()

        QuickMatchService._notify_opponent(match, user_id, opponent_id)
        return match

    # ------------------------------------------------------------------
    # Interni
    # ------------------------------------------------------------------
    @staticmethod
    def settings_of(match: "IndividualMatch") -> Dict[str, Any]:
        """Come si gioca una sfida che esiste già, nella forma del modulo.

        Serve alla correzione: lì la base non sono le abitudini del giocatore
        ma **questa** partita, e i campi che il modulo non manda devono restare
        quelli che sono, non tornare all'ultima partita giocata.
        """
        if match.distance is None:
            match_format = "free"
        elif match.is_multi_set:
            match_format = "multi"
        else:
            match_format = "single"

        return {
            "billiard_hall_id": match.billiard_hall_id,
            "location": match.location or "",
            "discipline": match.discipline,
            "match_format": match_format,
            "distance": match.distance,
            "match_distance": match.match_distance,
            "break_rule": match.break_rule,
            "is_race_to": match.is_race_to,
        }

    @staticmethod
    def _resolve_config(
        user_id: int, config: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Fonde quello che è stato scelto con quello che si dà per scontato."""
        return QuickMatchService.resolve_settings(
            QuickMatchService.get_defaults(user_id), config
        )

    @staticmethod
    def resolve_settings(
        base: Dict[str, Any], config: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Normalizza «come si gioca» a partire da una base qualunque.

        Unico posto in cui un modulo diventa configurazione di partita: lo
        usano l'avvio rapido (base = le abitudini del giocatore) e la
        correzione di una sfida già aperta (base = la partita stessa). Due
        moduli che chiedono le stesse cose devono validarle allo stesso modo,
        o divergono al primo caso limite — è la stessa ragione per cui gare e
        campionati hanno un solo `FormParser`.
        """
        settings = dict(base)
        for key, value in (config or {}).items():
            if value is not None:
                settings[key] = value

        # `.value` e non il membro: la colonna `discipline` è una `db.String`.
        discipline = Discipline.normalize(settings["discipline"])
        if discipline is None:
            raise ValidationError(_("Disciplina non riconosciuta."))
        settings["discipline"] = discipline.value

        match_format = settings.get("match_format") or "single"
        if match_format not in ("single", "multi", "free"):
            raise ValidationError(_("Formato di gioco non riconosciuto."))

        if match_format == "free":
            settings["distance"] = None
            settings["is_multi_set"] = False
            settings["match_distance"] = None
            settings["is_race_to"] = True
        elif match_format == "multi":
            settings["distance"] = QuickMatchService._positive(
                settings.get("distance"), 5, _("triangoli per set")
            )
            settings["is_multi_set"] = True
            settings["match_distance"] = QuickMatchService._positive(
                settings.get("match_distance"), 3, _("set da vincere")
            )
            settings["is_race_to"] = True
        else:
            settings["distance"] = QuickMatchService._positive(
                settings.get("distance"), 5, _("triangoli")
            )
            settings["is_multi_set"] = False
            settings["match_distance"] = None
            settings["is_race_to"] = bool(settings.get("is_race_to", True))

        settings["location"] = (settings.get("location") or "").strip()
        settings["billiard_hall_id"] = QuickMatchService._resolve_venue(settings)
        settings["break_rule"] = settings.get("break_rule") or "alternate"
        return settings

    @staticmethod
    def _resolve_venue(settings: Dict[str, Any]) -> Optional[int]:
        """La sala scritta a mano diventa una FK se una sala con quel nome c'è.

        Stessa regola del modulo di proposta: il testo libero resta comunque
        (`location`), la FK è un di più quando la sala è già in anagrafica.
        """
        from ..location.models import BilliardHall

        location = settings.get("location") or ""
        hall_id = settings.get("billiard_hall_id")

        if hall_id:
            hall = db.session.get(BilliardHall, int(hall_id))
            if hall is not None:
                # Il nome della sala vince sul testo: se il giocatore ne ha
                # scelta una dall'elenco, `location` deve dire la stessa cosa.
                if not location or location != hall.name:
                    settings["location"] = hall.name
                return hall.id
            return None

        if location:
            venue = BilliardHall.query.filter_by(name=location).first()
            if venue is not None:
                return venue.id
        return None

    @staticmethod
    def _positive(value: Any, fallback: int, label: str) -> int:
        try:
            number = int(value) if value is not None else fallback
        except (TypeError, ValueError):
            raise ValidationError(_("Valore non valido per %(field)s.", field=label))
        if number < 1:
            raise ValidationError(
                _("Il numero di %(field)s deve essere almeno 1.", field=label)
            )
        return number

    @staticmethod
    def _notify_opponent(
        match: IndividualMatch, user_id: int, opponent_id: int
    ) -> None:
        """Avvisa l'avversario che una partita con lui è aperta.

        Tipo ``MATCH_ACCEPTED`` e non un tipo nuovo: la colonna
        ``Notification.notification_type`` è una ``db.Enum`` senza
        ``values_callable`` (quindi persiste i **nomi**) e ogni tipo si porta
        dietro preferenze e template. Il senso è comunque quello: una sfida che
        vi riguarda entrambi è appena partita.

        Un errore qui non deve impedire di giocare: la notifica è un di più, la
        partita è il fatto.
        """
        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationPriority, NotificationType
        from ..user.models import User

        try:
            starter = db.session.get(User, user_id)
            starter_name = starter.username if starter else _("Un giocatore")
            location_text = match.location_display or ""
            loc_suffix = (
                " " + _("a %(loc)s", loc=location_text) if location_text else ""
            )

            NotificationFactory.create_bulk_notification(
                user_ids=[opponent_id],
                notification_type=NotificationType.MATCH_ACCEPTED,
                title=_("Partita iniziata!"),
                message=_(
                    "%(player)s ha aperto una partita con te%(location)s. "
                    "A fine partita dovrai confermare il risultato.",
                    player=starter_name,
                    location=loc_suffix,
                ),
                priority=NotificationPriority.HIGH,
                action_url=f"/match/matches/{match.id}",
                action_text=_("Vai alla partita"),
            )
        except Exception:  # pragma: no cover - la notifica non blocca il gioco
            logger.warning(
                "Notifica di avvio rapido non inviata per il match %s", match.id
            )
