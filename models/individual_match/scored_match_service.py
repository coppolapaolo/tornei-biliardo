"""La partita di altri due, tenuta da un istruttore o da un direttore (ADR-084).

Una sera da spettatore: due giocatori in finale, un istruttore a bordo tavolo
che vuole il referto Accu-Stats della partita. Qui la partita nasce **già in
corso e col referto già aperto**, compilatore chi la segna: una partita di un
terzo senza referto non esiste, perché è il referto il motivo per cui c'è.

Chi segna non firma per nessuno. Quando chiude il referto la partita è
*dichiarata* e i due giocatori decidono
(`IndividualMatch.confirm_as_player` / `reject_as_player`). Le conferme sono
per sé, il rifiuto no: ne basta uno e la partita è rifiutata per tutti e due
(emendamento del 2026-10-18). Chi l'ha segnata la riapre per correggerla
(`reopen`) o la cancella.

I giocatori sono utenti che esistono, registrati o no, oppure nascono dal
modulo come giocatori non ancora registrati (`NuovoGiocatore`, ADR-085): la
scelta passa da `ScoredMatchService._giocatore`. Per un non registrato la
decisione resta assente — non ha un account con cui confermare — quindi per
lui la partita è *in attesa* (livello per giocatore, ADR-084).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from flask_babel import gettext as _

from ..base import db, utc_now
from ..exceptions import NotFoundError, PermissionDeniedError, ValidationError
from ..status_enum import MatchStatus
from ..transaction.manager import transactional
from .match_models import IndividualMatch

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NuovoGiocatore:
    """Un giocatore da creare dal modulo, perché non ha un account (ADR-085)."""

    first_name: str
    last_name: str


class ScoredMatchService:
    """Creazione della partita di altri due."""

    @staticmethod
    def can_score(user) -> bool:
        """Chi può segnare la partita di altri due: istruttori e direttori.

        **Non l'admin**, nemmeno se ha il ruolo di istruttore (decisione
        dell'utente del 2026-10-18: «admin non dovrebbe segnare partite»).
        L'admin non gioca e non segna: è la regola «l'admin non è un player»,
        e segnare per altri due è stare al tavolo come loro. Fino a quella
        data l'admin poteva, «con i poteri del direttore».

        Il ruolo si guarda qui, quando la partita nasce; dopo il permesso è
        `scorer_id` (`TpaRefertoService.can_compile`).
        """
        if user is None or not getattr(user, "is_authenticated", True):
            return False
        if user.is_admin:
            return False
        return bool(user.is_director or user.is_instructor)

    @staticmethod
    def _giocatore(user_id: Any, etichetta: str, scorer=None):
        """Il giocatore scelto nel modulo.

        Un utente che esiste — registrato, o non registrato già creato da
        qualcuno — oppure uno da creare adesso: chi segna scrive nome e
        cognome di chi ha davanti e senza account (``NuovoGiocatore``,
        ADR-085). Il resto del servizio riceve un ``User`` e non sa da dove
        viene.
        """
        from ..user.models import User

        if isinstance(user_id, NuovoGiocatore):
            from ..user.profile_service import UserProfileService

            return UserProfileService.create_placeholder(
                user_id.first_name, user_id.last_name, scorer
            )

        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            raise ValidationError(
                _("Scegli il %(giocatore)s.", giocatore=etichetta)
            ) from None
        giocatore = db.session.get(User, uid)
        if giocatore is None or giocatore.deleted_at is not None:
            raise NotFoundError(_("Giocatore non trovato."))
        return giocatore

    @staticmethod
    def find_open(scorer_id: int, player1_id: int, player2_id: int):
        """La partita fra questi due che ``scorer_id`` sta già segnando.

        Contro il doppio tocco: due referti aperti della stessa partita
        sarebbero due verità diverse.
        """
        from ..tpa.models import TpaReferto

        candidate = IndividualMatch.query.filter(
            IndividualMatch.scorer_id == scorer_id,
            IndividualMatch.status == MatchStatus.IN_PROGRESS,
            db.or_(
                db.and_(
                    IndividualMatch.player1_id == player1_id,
                    IndividualMatch.player2_id == player2_id,
                ),
                db.and_(
                    IndividualMatch.player1_id == player2_id,
                    IndividualMatch.player2_id == player1_id,
                ),
            ),
        ).all()
        for match in candidate:
            referto: Optional[TpaReferto] = getattr(match, "tpa_referto", None)
            if referto is not None and referto.closed_at is None:
                return match
        return None

    @staticmethod
    @transactional(domain="individual_match")
    def start(
        scorer,
        player1_id: Any,
        player2_id: Any,
        config: Optional[Dict[str, Any]] = None,
    ) -> IndividualMatch:
        """Crea la partita fra ``player1_id`` e ``player2_id`` e ne apre il referto.

        ``config`` ha le chiavi dell'avvio rapido (disciplina, formato,
        distanza, regole di apertura, descrizione). La partita nasce in corso,
        senza blocchi per i giocatori: non l'hanno chiesta loro.
        """
        from ..match.match_info_service import normalize_description
        from ..tpa.services import TpaRefertoService
        from .quick_match_service import QuickMatchService

        if not ScoredMatchService.can_score(scorer):
            raise PermissionDeniedError(
                _("La partita di altri due la segnano istruttori e direttori.")
            )

        primo = ScoredMatchService._giocatore(player1_id, _("giocatore A"), scorer)
        secondo = ScoredMatchService._giocatore(player2_id, _("giocatore B"), scorer)
        if primo.id == secondo.id:
            raise ValidationError(_("I due giocatori devono essere diversi."))
        if scorer.id in (primo.id, secondo.id):
            raise ValidationError(
                _("Chi segna non gioca: per le tue partite c'è l'avvio rapido.")
            )

        config = dict(config or {})
        description = normalize_description(config.pop("description", None))

        if config.get("match_format") == "multi":
            raise ValidationError(_("Il referto TPA non copre le partite a set."))

        existing = ScoredMatchService.find_open(scorer.id, primo.id, secondo.id)
        if existing is not None:
            return existing

        settings = QuickMatchService.resolve_settings(
            dict(QuickMatchService.SYSTEM_DEFAULTS), config
        )
        if TpaRefertoService.game_type_for(settings["discipline"]) is None:
            raise ValidationError(
                _(
                    "Il referto TPA vale per palla 8, palla 9 e palla 10: "
                    "in questa disciplina non si calcola."
                )
            )

        match = IndividualMatch(
            proposal_id=None,
            player1_id=primo.id,
            player2_id=secondo.id,
            scorer_id=scorer.id,
            billiard_hall_id=settings["billiard_hall_id"],
            location=settings["location"] or None,
            scheduled_at=utc_now(),
            status=MatchStatus.SCHEDULED,
            discipline=settings["discipline"],
            distance=settings["distance"],
            is_race_to=settings["is_race_to"],
            break_rule=settings["break_rule"],
            start_rule=settings["start_rule"],
            is_multi_set=False,
            match_distance=None,
            description=description,
        )
        db.session.add(match)
        db.session.flush()
        match.start_match()

        # Annidato è sicuro (ADR-061): se l'apertura fallisse, non nascerebbe
        # nemmeno la partita — ed è giusto, senza referto non ha senso.
        TpaRefertoService.open_referto(match.id, scorer.id)

        ScoredMatchService._avvisa_i_giocatori(match, scorer)
        return match

    @staticmethod
    @transactional(domain="individual_match")
    def reopen(match_id: int, user_id: int) -> IndividualMatch:
        """Chi l'ha segnata riapre la partita rifiutata, per correggerla.

        La regola sta in `IndividualMatch.reopen_by_scorer`. Gli avvisi «da
        confermare» della dichiarazione di prima sono già stati ritirati dal
        rifiuto: quando il referto si richiude, i due ne ricevono uno nuovo.
        """
        match = db.session.get(IndividualMatch, match_id)
        if match is None:
            raise NotFoundError(_("Partita non trovata"))
        match.reopen_by_scorer(user_id)
        return match

    @staticmethod
    def _avvisa_i_giocatori(match: IndividualMatch, scorer) -> None:
        """Ai due giocatori: chi segna la vostra partita, e quale partita è.

        Stesso tipo dell'avvio rapido (``MATCH_ACCEPTED``): una partita che vi
        riguarda è appena partita. Il testo si compone nella lingua di chi
        riceve (ADR-062). Un errore qui non ferma la partita.
        """
        from flask_babel import lazy_gettext as _l

        from ..notification.factory import NotificationFactory
        from ..notification.models import NotificationPriority, NotificationType

        nome = scorer.username
        descrizione = match.description or ""

        def messaggio() -> str:
            if descrizione:
                return _(
                    "%(scorer)s tiene il referto TPA della tua partita "
                    "«%(descrizione)s». A fine partita potrai confermarla o "
                    "rifiutarla.",
                    scorer=nome,
                    descrizione=descrizione,
                )
            return _(
                "%(scorer)s tiene il referto TPA della tua partita. A fine "
                "partita potrai confermarla o rifiutarla.",
                scorer=nome,
            )

        try:
            NotificationFactory.create_bulk_notification(
                user_ids=[match.player1_id, match.player2_id],
                notification_type=NotificationType.MATCH_ACCEPTED,
                title=_l("Qualcuno segna la tua partita"),
                message=messaggio,
                priority=NotificationPriority.HIGH,
                related_entities={"individual_match_id": match.id},
                action_url=f"/match/matches/{match.id}",
                action_text=_l("Apri la partita"),
            )
        except Exception:  # pragma: no cover - la notifica non blocca il gioco
            logger.warning(
                "Avviso della partita di altri due non inviato: %s", match.id
            )


__all__ = ["NuovoGiocatore", "ScoredMatchService"]
