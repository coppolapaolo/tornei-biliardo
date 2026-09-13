"""
Module: models/playoff/services.py
Purpose: Playoff domain services for business logic
Requirements: SPECIFICHE.md - Playoff management and qualification system
"""

from __future__ import annotations

import logging
from typing import Tuple, List, Optional, Dict, Any
from datetime import datetime, timedelta

from ..base import db, utc_now
from ..exceptions import NotFoundError
from .models import (
    PlayoffConfiguration,
    PlayoffQualification,
    PlayoffRankingMode,
    PlayoffTournament,
    PlayoffType,
    QualificationStatus,
)
from ..transaction.manager import transactional

logger = logging.getLogger(__name__)


class PlayoffService:
    """Service for playoff management and business logic."""

    @staticmethod
    @transactional(domain="playoff")
    def create_playoff_configuration(
        campionato_id: int,
        name: str,
        playoff_type: PlayoffType,
        max_participants: int,
        qualification_criteria: Dict[str, Any],
        description: Optional[str] = None,
        min_garas_played: Optional[int] = None,
        location: Optional[str] = None,
        scheduled_date: Optional[datetime] = None,
        entry_fee: Optional[float] = None,
        response_deadline: Optional[datetime] = None,
    ) -> PlayoffConfiguration:
        """Create a new playoff configuration."""

        configuration = PlayoffConfiguration(
            campionato_id=campionato_id,
            name=name,
            playoff_type=playoff_type,
            max_participants=max_participants,
            description=description,
            min_garas_played=min_garas_played,
            location=location,
            scheduled_date=scheduled_date,
            entry_fee=entry_fee,
            response_deadline=response_deadline,
        )

        configuration.set_qualification_criteria(qualification_criteria)

        db.session.add(configuration)
        return configuration

    @staticmethod
    def create_standard_playoff_configurations(
        campionato_id: int,
    ) -> List[PlayoffConfiguration]:
        """Create standard playoff configurations for a campionato."""
        configurations = []

        # Elite Playoff (Top 6)
        elite_config = PlayoffService.create_playoff_configuration(
            campionato_id=campionato_id,
            name="Elite Playoff",
            playoff_type=PlayoffType.ELITE_ACADEMY,
            max_participants=6,
            qualification_criteria={
                "category": "elite",
                "elite_positions": 6,
                "academy_positions": 6,
            },
            description="Playoff for top 6 classified players",
            min_garas_played=3,
        )
        configurations.append(elite_config)

        # Academy Playoff (Positions 7-12)
        academy_config = PlayoffService.create_playoff_configuration(
            campionato_id=campionato_id,
            name="Academy Playoff",
            playoff_type=PlayoffType.ELITE_ACADEMY,
            max_participants=6,
            qualification_criteria={
                "category": "academy",
                "elite_positions": 6,
                "academy_positions": 6,
            },
            description="Playoff for players in positions 7-12",
            min_garas_played=3,
        )
        configurations.append(academy_config)

        return configurations

    @staticmethod
    def generate_all_qualifications(
        campionato_id: int,
    ) -> Dict[str, List[PlayoffQualification]]:
        """Generate qualifications for all playoff configurations of a campionato."""
        configurations = PlayoffConfiguration.query.filter_by(
            campionato_id=campionato_id, is_active=True, auto_generate=True
        ).all()

        results = {}
        for config in configurations:
            qualifications = config.generate_qualifications()
            results[config.name] = qualifications

        return results

    @staticmethod
    @transactional(domain="playoff")
    def notify_qualified_players(configuration_id: int) -> int:
        """Send notifications to qualified players non ancora invitati.

        Usa invited_at (campo attivo) come marcatore: notified_at e' deprecato
        e non viene mai popolato dal flusso di invito (start_playoff /
        _send_playoff_invitations usano invited_at). Filtrando su notified_at
        questo metodo ri-processava TUTTI i pending — anche i gia' invitati —
        ad ogni chiamata (es. dopo un decline+replacement).
        """
        qualifications = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id,
            status=QualificationStatus.PENDING,
            invited_at=None,
        ).all()

        # In a real implementation, this would send actual notifications.
        # For now, just mark as invited.
        count = 0
        for qualification in qualifications:
            qualification.invited_at = utc_now()
            count += 1

        return count

    @staticmethod
    @transactional(domain="playoff")
    def confirm_qualification(
        qualification_id: int,
        user_id: int,
        responded_by_id: Optional[int] = None,
    ) -> PlayoffQualification:
        """Confirm a user's playoff qualification.

        `responded_by_id` è chi registra la risposta: assente vuol dire «l'ha
        fatto il giocatore stesso». Il direttore lo passa quando gliel'hanno
        detta a voce (vedi `respond_on_behalf`).
        """
        qualification = PlayoffQualification.query.filter_by(
            id=qualification_id, user_id=user_id
        ).first_or_404()

        qualification.confirm_participation(responded_by_id=responded_by_id)

        # Check if we can start the playoff campionato
        PlayoffService._check_playoff_readiness(qualification.configuration_id)

        return qualification

    @staticmethod
    @transactional(domain="playoff")
    def decline_qualification(
        qualification_id: int,
        user_id: int,
        responded_by_id: Optional[int] = None,
    ) -> Optional[PlayoffQualification]:
        """Decline a user's playoff qualification and find replacement."""
        qualification = PlayoffQualification.query.filter_by(
            id=qualification_id, user_id=user_id
        ).first_or_404()

        qualification.decline_participation(responded_by_id=responded_by_id)

        # Cerca il sostituto a livello servizio (flusso documentato:
        # decline → invita il prossimo idoneo). Il modello non lo fa più:
        # prima decline_participation() chiamava un metodo inesistente su
        # PlayoffConfiguration via hasattr (sempre False) → nessun sostituto.
        replacement = PlayoffService.find_replacement_player(
            qualification.configuration_id, sostituisce=qualification
        )

        # Notify replacement if found
        if replacement:
            PlayoffService.notify_qualified_players(qualification.configuration_id)

        return replacement

    @staticmethod
    @transactional(domain="playoff")
    def respond_on_behalf(
        qualification_id: int, accept: bool, responded_by_id: int
    ) -> Optional[PlayoffQualification]:
        """Il direttore registra la risposta che il giocatore gli ha dato.

        I giocatori qualificati spesso rispondono a voce, in sala: senza
        questa strada l'invito resterebbe `PENDING` fino alla scadenza, e la
        cascata dei rifiuti (SPECIFICHE.md riga 188) non partirebbe mai per
        chi ha detto no al telefono.

        È la stessa transizione che fa il giocatore — stessi controlli, stesso
        sostituto cercato sul rifiuto — con l'unica differenza che resta
        scritto chi ha risposto (`responded_by_id`).

        Ritorna l'eventuale sostituto trovato (solo sul rifiuto), come
        `decline_qualification`.
        """
        qualification = db.session.get(PlayoffQualification, qualification_id)
        if qualification is None:
            raise NotFoundError("Qualificazione non trovata")
        if qualification.status != QualificationStatus.PENDING:
            raise ValueError("Questa qualificazione ha già una risposta")

        if accept:
            PlayoffService.confirm_qualification(
                qualification_id,
                qualification.user_id,
                responded_by_id=responded_by_id,
            )
            return None

        return PlayoffService.decline_qualification(
            qualification_id,
            qualification.user_id,
            responded_by_id=responded_by_id,
        )

    @staticmethod
    @transactional(domain="playoff")
    def update_scoring(
        config_id: int,
        final_ranking_mode: Optional[str] = None,
        playoff_weight: Optional[int] = None,
    ) -> PlayoffConfiguration:
        """Cambia come il playoff entra nella classifica finale.

        A differenza di `update_configuration` **non** è bloccata dall'avvio:
        i criteri di qualificazione non si toccano più dopo gli inviti (chi è
        dentro è dentro), ma quanto pesa la gara e chi decide la classifica
        sono decisioni di punteggio, e restano del direttore fino a quando il
        campionato non è archiviato. Al cambio la classifica generale si
        ricalcola: un peso modificato che non muove la classifica sarebbe un
        peso che non fa niente.
        """
        config = db.session.get(PlayoffConfiguration, config_id)
        if config is None:
            raise NotFoundError("Configurazione playoff non trovata")

        if final_ranking_mode is not None:
            config.final_ranking_mode = PlayoffRankingMode.normalize(
                final_ranking_mode
            ).value

        if playoff_weight is not None:
            weight = int(playoff_weight)
            if weight < 1:
                raise ValueError("Il peso deve essere un intero maggiore di zero")
            config.playoff_weight = weight
            # `Gara.weight` è la fonte letta dall'aggregatore: se la gara
            # esiste già, la configurazione da sola non sposterebbe niente.
            if config.gara is not None:
                config.gara.weight = weight

        db.session.flush()
        PlayoffService._recalculate_campionato_classification(config.campionato_id)
        return config

    @staticmethod
    def _recalculate_campionato_classification(campionato_id: Optional[int]) -> None:
        """Ricalcola la classifica generale dopo un cambio di punteggio."""
        if not campionato_id:
            return
        from ..classification.campionato_classification import ClassificationService

        ClassificationService.invalidate_campionato_cache(campionato_id)
        ClassificationService.update_campionato_classification(campionato_id)

    @staticmethod
    @transactional(domain="playoff")
    def find_replacement_player(
        configuration_id: int,
        sostituisce: Optional[PlayoffQualification] = None,
    ) -> Optional[PlayoffQualification]:
        """Find the next eligible player for playoff replacement.

        `sostituisce` e' la qualificazione rifiutata o scaduta che il
        sostituto va a coprire: quando c'e', le si scrive chi e' subentrato e
        in che posizione (`replaced_by_id`, `replacement_position`). Le due
        colonne esistevano dall'inizio ma nessuno le scriveva, quindi la
        pagina del campionato non poteva dire «al suo posto X» (canvas 7.2).
        """
        configuration = db.session.get(PlayoffConfiguration, configuration_id)
        if configuration is None:
            raise NotFoundError("Configurazione playoff non trovata")

        # Giocatori che hanno GIÀ una qualificazione per questo playoff (qualsiasi
        # status): un sostituto è per definizione un giocatore SENZA
        # qualificazione esistente. Così non duplichiamo chi è già
        # pending/confirmed né re-invitiamo chi ha declinato/è scaduto/sostituito.
        #
        # NB: le query precedenti filtravano lo status con `.value`
        # ('confirmed'/'pending'), ma la colonna db.Enum(QualificationStatus)
        # persiste il NOME del membro ('CONFIRMED'/'PENDING') → non matchavano
        # mai → current_players vuoto → veniva creato un duplicato del primo
        # qualificato invece del vero sostituto in coda.
        existing_qualifications = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id
        ).all()
        current_players = {q.user_id for q in existing_qualifications}

        # Re-evaluate qualifications to find next eligible.
        #
        # La finestra va allargata **oltre** i posti, altrimenti si guarda
        # esattamente l'insieme di chi ha già una qualificazione — declinante
        # compreso, che resta in elenco con status DECLINED — e il sostituto
        # non si trova mai (SPECIFICHE.md riga 188: l'invito «passa al primo
        # degli esclusi e così via»). Quante posizioni in più: una per ogni
        # qualificazione già emessa, perché nel caso peggiore hanno rifiutato
        # tutti e la cascata deve poter scorrere fino in fondo alla classifica.
        posti_da_guardare = configuration.max_participants + len(
            existing_qualifications
        )
        all_qualified = configuration.evaluate_qualifications(posti=posti_da_guardare)

        for player_data in all_qualified:
            if player_data["user_id"] not in current_players:
                # Found a replacement
                replacement = PlayoffQualification(
                    configuration_id=configuration_id,
                    user_id=player_data["user_id"],
                    qualifying_position=player_data["position"],
                    qualification_reason=(
                        f"Replacement - {player_data['qualification_reason']}"
                    ),
                )
                db.session.add(replacement)
                if sostituisce is not None:
                    sostituisce.replaced_by_id = player_data["user_id"]
                    sostituisce.replacement_position = player_data["position"]
                return replacement

        return None

    @staticmethod
    @transactional(domain="playoff")
    def expire_old_qualifications() -> int:
        """Expire qualifications that have passed their deadline."""
        expired_count = 0

        configurations = PlayoffConfiguration.query.filter(
            PlayoffConfiguration.response_deadline <= utc_now(),
            PlayoffConfiguration.is_active.is_(True),
        ).all()

        for config in configurations:
            expired_qualifications = PlayoffQualification.query.filter_by(
                configuration_id=config.id,
                status=QualificationStatus.PENDING,
            ).all()

            for qualification in expired_qualifications:
                qualification.expire_qualification()
                expired_count += 1

                # Find replacement and notify
                replacement = PlayoffService.find_replacement_player(
                    config.id, sostituisce=qualification
                )
                if replacement:
                    replacement.invited_at = utc_now()
                    replacement.expires_at = config.response_deadline
                    PlayoffService._send_playoff_invitations(config, [replacement])

        return expired_count

    @staticmethod
    @transactional(domain="playoff")
    def create_playoff_campionato(configuration_id: int) -> PlayoffTournament:
        """Create the actual playoff campionato."""
        configuration = db.session.get(PlayoffConfiguration, configuration_id)
        if configuration is None:
            raise NotFoundError("Configurazione playoff non trovata")

        # Check if campionato already exists
        if configuration.playoff_campionato is not None:
            # Explicitly query for the playoff campionato to avoid type issues
            playoff_campionato = PlayoffTournament.query.filter_by(
                configuration_id=configuration_id
            ).first()
            if playoff_campionato:
                return playoff_campionato

        campionato = PlayoffTournament(
            configuration_id=configuration_id,
            name=configuration.name,
            campionato_date=configuration.scheduled_date,
            location=configuration.location,
            entry_fee=configuration.entry_fee,
            max_participants=configuration.max_participants,
        )

        db.session.add(campionato)

        return campionato

    @staticmethod
    @transactional(domain="playoff")
    def start_playoff_registration(campionato_id: int) -> PlayoffTournament:
        """Start registration for a playoff campionato."""
        campionato = db.session.get(PlayoffTournament, campionato_id)
        if campionato is None:
            raise NotFoundError("Campionato playoff non trovato")
        campionato.start_registration()

        return campionato

    @staticmethod
    def get_campionato_playoff_status(campionato_id: int) -> Dict[str, Any]:
        """Get comprehensive playoff status for a campionato."""
        configurations = PlayoffConfiguration.query.filter_by(
            campionato_id=campionato_id, is_active=True
        ).all()

        status = {
            "has_playoffs": len(configurations) > 0,
            "configurations": [],
            "total_qualified": 0,
            "total_confirmed": 0,
            "ready_to_start": [],
        }

        for config in configurations:
            total_q = PlayoffQualification.query.filter_by(
                configuration_id=config.id
            ).count()
            confirmed_q = PlayoffQualification.query.filter_by(
                configuration_id=config.id, status=QualificationStatus.CONFIRMED
            ).count()
            pending_q = PlayoffQualification.query.filter_by(
                configuration_id=config.id, status=QualificationStatus.PENDING
            ).count()
            declined_q = PlayoffQualification.query.filter_by(
                configuration_id=config.id, status=QualificationStatus.DECLINED
            ).count()
            config_status = {
                "configuration": config,
                "total_qualified": total_q,
                "confirmed": confirmed_q,
                "pending": pending_q,
                "declined": declined_q,
                "has_campionato": config.playoff_campionato is not None,
                "campionato_status": (
                    config.playoff_campionato.status
                    if config.playoff_campionato
                    else None
                ),
            }

            status["configurations"].append(config_status)
            status["total_qualified"] += config_status["total_qualified"]
            status["total_confirmed"] += config_status["confirmed"]

            # Check if ready to start
            if (
                config_status["confirmed"] >= config.max_participants * 0.8
                and config_status["pending"] == 0  # At least 80% confirmed
            ):  # No pending responses
                status["ready_to_start"].append(config.name)

        return status

    @staticmethod
    def _check_playoff_readiness(configuration_id: int) -> None:
        """Check if playoff is ready to start and create campionato if needed."""
        configuration = db.session.get(PlayoffConfiguration, configuration_id)
        if configuration is None:
            raise NotFoundError("Configurazione playoff non trovata")

        confirmed_count = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id,
            status=QualificationStatus.CONFIRMED,
        ).count()

        pending_count = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id,
            status=QualificationStatus.PENDING,
        ).count()

        # If we have enough confirmed players and no pending responses
        if (
            confirmed_count >= configuration.max_participants * 0.8
            and pending_count == 0
            and not configuration.playoff_campionato
        ):

            # Auto-create playoff campionato
            PlayoffService.create_playoff_campionato(configuration_id)

    @staticmethod
    @transactional(domain="playoff")
    def complete_playoff_campionato(
        campionato_id: int, winner_id: Optional[int] = None
    ) -> PlayoffTournament:
        """Complete a playoff campionato."""
        campionato = db.session.get(PlayoffTournament, campionato_id)
        if campionato is None:
            raise NotFoundError("Campionato playoff non trovato")
        campionato.complete_campionato(winner_id)

        return campionato

    # ── Config management (pre-avvio) ──────────────────────────────

    @staticmethod
    @transactional(domain="playoff")
    def update_configuration(config_id: int, **fields: Any) -> PlayoffConfiguration:
        """Update a playoff configuration. Blocked if qualifications exist."""
        config = db.session.get(PlayoffConfiguration, config_id)
        if config is None:
            raise NotFoundError("Configurazione playoff non trovata")
        if config.has_qualifications():
            raise ValueError("Non modificabile dopo avvio playoff")

        allowed = {
            "name",
            "positions_from",
            "positions_to",
            "max_participants",
            "min_garas_played",
            "location",
            "scheduled_date",
            "entry_fee",
            "response_deadline",
            "discipline",
            "distance",
            "rounds_count",
            "strategy_type",
            "odd_number_policy",
        }
        for key, value in fields.items():
            if key in allowed:
                setattr(config, key, value)

        return config

    @staticmethod
    @transactional(domain="playoff")
    def add_configuration(
        campionato_id: int,
        name: str,
        positions_from: int,
        positions_to: int,
        max_participants: int,
        min_garas_played: Optional[int] = None,
        **kwargs: Any,
    ) -> PlayoffConfiguration:
        """Add a new playoff configuration.

        Blocked if any config already has qualifications.
        """
        existing_configs = PlayoffConfiguration.query.filter_by(
            campionato_id=campionato_id, is_active=True
        ).all()
        for c in existing_configs:
            if c.has_qualifications():
                raise ValueError("Non modificabile dopo avvio playoff")

        config = PlayoffConfiguration(
            campionato_id=campionato_id,
            name=name,
            playoff_type=PlayoffType.TOP_N,
            max_participants=max_participants,
            min_garas_played=min_garas_played,
            positions_from=positions_from,
            positions_to=positions_to,
        )
        # Optional gara params
        for key in (
            "discipline",
            "distance",
            "rounds_count",
            "strategy_type",
            "odd_number_policy",
            "location",
            "scheduled_date",
            "entry_fee",
        ):
            if key in kwargs:
                setattr(config, key, kwargs[key])

        db.session.add(config)
        return config

    @staticmethod
    @transactional(domain="playoff")
    def deactivate_configuration(config_id: int) -> PlayoffConfiguration:
        """Deactivate a playoff configuration. Blocked if qualifications exist."""
        config = db.session.get(PlayoffConfiguration, config_id)
        if config is None:
            raise NotFoundError("Configurazione playoff non trovata")
        if config.has_qualifications():
            raise ValueError("Non modificabile dopo avvio playoff")

        config.is_active = False
        return config

    # ── Avvio playoff ────────────────────────────────────────────

    @staticmethod
    def candidati_per_posizione(
        config: PlayoffConfiguration, classifications: List[Any]
    ) -> List[Tuple[int, int, str]]:
        """Chi invita una configurazione a posizioni: (utente, posizione, motivo).

        La fascia `positions_from`–`positions_to`, fino a `max_participants`;
        chi non ha il minimo di gare giocate resta fuori, e i posti rimasti si
        coprono con chi viene **dopo** la fascia. E' la scelta di
        `start_playoff`, messa qui perche' la zona playoff della classifica
        generale (`models/playoff/zona.py`) segni esattamente chi verra'
        invitato: prima leggeva `evaluate_qualifications`, che ignora la
        fascia, e l'Academy 7–12 avrebbe segnato i primi sei (rilievo della
        revisione automatica sulla PR #358).

        Le gare giocate si leggono dalle righe `Classification` gia' in mano:
        `_meets_minimum_requirements` rifaceva la stessa query per ogni
        candidato.
        """

        def idoneo(riga: Any) -> bool:
            if not config.min_garas_played:
                return True
            return (riga.gare_played or 0) >= config.min_garas_played

        scelti: List[Tuple[int, int, str]] = []
        for riga in classifications:
            if riga.position is None:
                continue
            if config.positions_from <= riga.position <= config.positions_to:
                if not idoneo(riga):
                    logger.info(
                        "Player %d excluded: min_garas_played not met", riga.user_id
                    )
                    continue
                if len(scelti) < config.max_participants:
                    scelti.append(
                        (
                            riga.user_id,
                            riga.position,
                            f"Posizione {riga.position} in classifica",
                        )
                    )
        if len(scelti) < config.max_participants:
            dentro = {user_id for user_id, _pos, _motivo in scelti}
            for riga in classifications:
                if riga.position is None or riga.position <= config.positions_to:
                    continue
                if riga.user_id in dentro or not idoneo(riga):
                    continue
                scelti.append(
                    (
                        riga.user_id,
                        riga.position,
                        f"Rimpiazzo — posizione {riga.position}",
                    )
                )
                if len(scelti) >= config.max_participants:
                    break
        return scelti

    @staticmethod
    @transactional(domain="playoff")
    def start_playoff(
        campionato_id: int,
    ) -> Dict[str, List[PlayoffQualification]]:
        """Start playoffs: generate qualifications from classification.

        Iterates over all active configs of the campionato. Sets
        response_deadline (default 7 days) and sends notifications.
        Returns dict of config_name → list of new qualifications.
        """
        from ..campionato.models import Campionato
        from ..status_enum import TournamentStatus
        from ..classification.models import Classification

        campionato = db.session.get(Campionato, campionato_id)
        if campionato is None:
            raise NotFoundError("Campionato non trovato")

        if campionato.get_status() != TournamentStatus.AWAITING_PLAYOFF.value:
            raise ValueError(
                "Il campionato deve essere terminato per avviare i playoff"
            )

        configs = PlayoffConfiguration.query.filter_by(
            campionato_id=campionato_id, is_active=True
        ).all()

        if not configs:
            raise ValueError("Nessuna configurazione playoff attiva")

        # Pre-flight: check ALL configs before any creation
        if any(c.has_qualifications() for c in configs):
            raise ValueError("Playoff già avviati per questo campionato")

        # Make sure Classification records are up-to-date: la UI calcola la
        # classifica on-the-fly via calculate_general_classification, ma
        # qui leggiamo dai Classification persistiti per congelare i dati.
        try:
            from ..classification.campionato_classification import (
                ClassificationService,
            )

            ClassificationService.update_campionato_classification(campionato_id)
        except Exception:
            logger.warning(
                "Impossibile aggiornare la classifica campionato %d "
                "prima di start_playoff",
                campionato_id,
            )

        # Get the frozen classification
        classifications = (
            Classification.query.filter_by(campionato_id=campionato_id)
            .order_by(Classification.position)
            .all()
        )

        results: Dict[str, List[PlayoffQualification]] = {}
        now = utc_now()

        for config in configs:
            # Set deadline if not explicitly configured
            if config.response_deadline is None:
                config.response_deadline = now + timedelta(days=7)

            qualifications: List[PlayoffQualification] = []

            if config.positions_from is not None and config.positions_to is not None:
                # Position-based qualification: la scelta sta in
                # `candidati_per_posizione`, che usa anche la zona playoff
                # della classifica generale (canvas 7.1).
                for (
                    user_id,
                    posizione,
                    motivo,
                ) in PlayoffService.candidati_per_posizione(config, classifications):
                    qual = PlayoffQualification(
                        configuration_id=config.id,
                        user_id=user_id,
                        qualifying_position=posizione,
                        qualification_reason=motivo,
                        invited_at=now,
                        expires_at=config.response_deadline,
                    )
                    db.session.add(qual)
                    qualifications.append(qual)
            else:
                # Fallback to evaluate_qualifications (legacy JSON criteria)
                qualifications = list(config.generate_qualifications())
                for q in qualifications:
                    q.invited_at = now
                    q.expires_at = config.response_deadline

            results[config.name] = qualifications

        # Notify all qualified players via NotificationFactory
        db.session.flush()
        for config in configs:
            PlayoffService._send_playoff_invitations(
                config, results.get(config.name, [])
            )

        return results

    @staticmethod
    def _send_playoff_invitations(
        config: PlayoffConfiguration,
        qualifications: List[PlayoffQualification],
    ) -> None:
        """Send in-app notifications to qualified players.

        Una notifica PER qualifica, con deep-link alla pagina di invito
        (`/player/playoff/invitation/<id>`) dove il giocatore conferma o
        rifiuta la partecipazione (bug 15). Non si può usare una bulk
        notification: l'`action_url` deve contenere la qualification_id
        specifica di ciascun giocatore.
        """
        import logging
        from ..notification.services import NotificationService
        from ..notification.models import NotificationType, NotificationPriority

        if not qualifications:
            return

        campionato_name = config.campionato.name if config.campionato else ""

        for qual in qualifications:
            try:
                NotificationService.create_notification(
                    user_id=qual.user_id,
                    notification_type=NotificationType.PLAYOFF_INVITATION,
                    title=f"Invito Playoff — {config.name}",
                    message=(
                        f"Sei stato qualificato per {config.name} "
                        f"del campionato {campionato_name}. "
                        f"Conferma o rifiuta la partecipazione."
                    ),
                    priority=NotificationPriority.HIGH,
                    action_url=f"/player/playoff/invitation/{qual.id}",
                    action_text="Conferma o rifiuta",
                    related_entities={
                        "campionato_id": config.campionato_id,
                        "configuration_id": config.id,
                        "configuration_name": config.name,
                        "qualification_id": qual.id,
                    },
                    expires_at=getattr(qual, "expires_at", None),
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Invio invito playoff fallito per qualification %s", qual.id
                )

    # ── Creazione gara playoff ───────────────────────────────────

    @staticmethod
    @transactional(domain="playoff")
    def create_playoff_gara(configuration_id: int):
        """Create the playoff Gara for a config and inscribe confirmed players.

        Returns the created Gara instance.
        """
        from ..competition.services import GaraService
        from ..competition.inscription_service import InscriptionService
        from datetime import date as date_type, time as time_type

        config = db.session.get(PlayoffConfiguration, configuration_id)
        if config is None:
            raise NotFoundError("Configurazione playoff non trovata")

        # Already has gara?
        if config.gara is not None:
            return config.gara

        # Get gara params (explicit or inherited from campionato)
        params = config.get_gara_params()

        # Next gara number: after all existing gare in campionato
        from ..competition.models import Gara as GaraModel

        last_gara = (
            GaraModel.query.filter_by(campionato_id=config.campionato_id)
            .order_by(GaraModel.number.desc())
            .first()
        )
        max_number = last_gara.number if last_gara else 0

        # Determine date — always use today or later to avoid past-date rejection
        gara_date: Any
        gara_time: Any
        if config.scheduled_date:
            sched = config.scheduled_date
            is_dt = isinstance(sched, datetime)
            candidate = sched.date() if is_dt else sched
            gara_date = max(candidate, date_type.today())
            gara_time = sched.time() if is_dt else time_type(20, 0)
        else:
            gara_date = date_type.today()
            gara_time = time_type(20, 0)

        # La gara di playoff è per costruzione l'**ultima** del campionato, e
        # `GaraService` pretende che le gare numerate siano in ordine
        # cronologico (ADR-016): una data anteriore all'ultima in calendario
        # viene rifiutata, la route trasforma il rifiuto in un messaggio e i
        # playoff restano semplicemente irraggiungibili. Succede ogni volta
        # che il campionato viene terminato *prima* della data dell'ultima
        # gara — comprese quelle mai giocate, che la terminazione
        # soft-elimina ma che il controllo di sequenza continua a vedere.
        # Non si sceglie una data qualsiasi: si sceglie la prima ammissibile.
        if last_gara is not None:
            ultima = datetime.combine(
                last_gara.date, last_gara.time or time_type(20, 0)
            )
            if datetime.combine(gara_date, gara_time) < ultima:
                gara_date, gara_time = ultima.date(), ultima.time()

        gara = GaraService.create_gara(
            number=max_number + 1,
            name=config.name,
            date=gara_date,
            discipline=params["discipline"],
            distance=params["distance"],
            campionato_id=config.campionato_id,
            time=gara_time,
            rounds_count=params.get("rounds_count", 1),
            max_participants=config.max_participants,
            playoff_config_id=config.id,
            # Il peso vive sulla gara, che è ciò che l'aggregatore legge; la
            # configurazione è il valore scelto dal direttore prima che la
            # gara esistesse.
            weight=config.playoff_weight or 1,
            **{
                k: v
                for k, v in params.items()
                if v is not None
                and k
                in (
                    "location",
                    "entry_fee",
                    "matchmaking_strategy",
                    "odd_number_policy",
                )
            },
        )

        # Inscribe all confirmed players
        confirmed = (
            PlayoffQualification.query.filter_by(
                configuration_id=configuration_id,
                status=QualificationStatus.CONFIRMED,
            )
            .order_by(PlayoffQualification.qualifying_position)
            .all()
        )

        for qual in confirmed:
            InscriptionService.inscribe_user(
                user_id=qual.user_id,
                gara_id=gara.id,
                _bypass_playoff_check=True,
            )

        # Update PlayoffTournament if exists, or create one
        tournament = PlayoffTournament.query.filter_by(
            configuration_id=configuration_id
        ).first()
        if not tournament:
            tournament = PlayoffTournament(
                configuration_id=configuration_id,
                name=config.name,
                campionato_date=config.scheduled_date,
                location=config.location,
                entry_fee=config.entry_fee,
                max_participants=config.max_participants,
            )
            db.session.add(tournament)

        tournament.gara_id = gara.id
        tournament.status = "registration"
        tournament.registration_start = utc_now()
        tournament.confirmed_participants = len(confirmed)

        return gara

    # ── Admin player management ──────────────────────────────────

    @staticmethod
    @transactional(domain="playoff")
    def admin_add_player(
        configuration_id: int, user_id: int, admin_username: str
    ) -> PlayoffQualification:
        """Manually add a player to a playoff config.

        Admin override — bypasses position and min_garas checks.
        """
        from ..competition.models import Inscription, Gara

        config = db.session.get(PlayoffConfiguration, configuration_id)
        if config is None:
            raise NotFoundError("Configurazione playoff non trovata")

        # Block if gara already created
        if config.gara is not None:
            raise ValueError("Non modificabile dopo creazione gara playoff")

        # Check player already present
        existing = PlayoffQualification.query.filter_by(
            configuration_id=configuration_id, user_id=user_id
        ).first()
        if existing:
            raise ValueError("Giocatore già presente nella lista playoff")

        # Validate: player must have participated in at least one gara of the campionato
        participation = (
            Inscription.query.join(Gara)
            .filter(
                Inscription.user_id == user_id,
                Gara.campionato_id == config.campionato_id,
            )
            .first()
        )
        if not participation:
            raise ValueError("Il giocatore non ha partecipato al campionato")

        # Determine position from classification if available
        from ..classification.models import Classification

        cls = Classification.query.filter_by(
            campionato_id=config.campionato_id, user_id=user_id
        ).first()
        position = cls.position if cls else 0

        qual = PlayoffQualification(
            configuration_id=configuration_id,
            user_id=user_id,
            qualifying_position=position or 0,
            qualification_reason=f"Aggiunto manualmente da {admin_username}",
            status=QualificationStatus.CONFIRMED,
            responded_at=utc_now(),
        )
        db.session.add(qual)
        return qual

    @staticmethod
    @transactional(domain="playoff")
    def admin_remove_player(
        qualification_id: int, admin_username: str
    ) -> PlayoffQualification:
        """Remove a player from a playoff config. Sets status to DECLINED."""
        qual = db.session.get(PlayoffQualification, qualification_id)
        if qual is None:
            raise NotFoundError("Qualificazione non trovata")

        config = qual.configuration
        if config.gara is not None:
            raise ValueError("Non modificabile dopo creazione gara playoff")

        qual.status = QualificationStatus.DECLINED
        original_reason = qual.qualification_reason
        qual.qualification_reason = (
            f"Rimosso da {admin_username} (era: {original_reason})"
        )
        qual.responded_at = utc_now()
        return qual

    @staticmethod
    def get_user_playoff_history(user_id: int) -> List[Dict[str, Any]]:
        """Get user's playoff participation history."""
        from sqlalchemy.orm import joinedload

        # Eager-load configuration + campionato per evitare 2 lazy-load per riga
        # (N+1) sull'accesso a configuration.campionato.name / .name.
        qualifications = (
            PlayoffQualification.query.filter_by(user_id=user_id)
            .options(
                joinedload(PlayoffQualification.configuration).joinedload(
                    PlayoffConfiguration.campionato
                )
            )
            .all()
        )

        history = []
        for qualification in qualifications:
            config = qualification.configuration
            # campionato puo' essere None (record orfano / campionato rimosso):
            # non far esplodere l'intera pagina history su un None-deref.
            campionato = config.campionato if config else None
            history.append(
                {
                    "campionato_name": campionato.name if campionato else None,
                    "playoff_name": config.name if config else None,
                    "qualifying_position": qualification.qualifying_position,
                    "status": qualification.status.value,
                    "qualified_at": qualification.created_at,
                    "responded_at": qualification.responded_at,
                }
            )

        return sorted(history, key=lambda x: x["qualified_at"], reverse=True)
