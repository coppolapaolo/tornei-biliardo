"""
Module: models/playoff/services.py
Purpose: Playoff domain services for business logic
Requirements: SPECIFICHE.md - Playoff management and qualification system
"""

from __future__ import annotations

import logging
from typing import Tuple, List, Optional, Dict, Any
from datetime import datetime, timedelta

from flask_babel import gettext as _

from ..base import db, utc_now
from ..exceptions import ConflictError, NotFoundError, ValidationError
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

#: Il minimo della gara di playoff: due giocatori bastano per una finale.
PLAYOFF_MIN_PARTICIPANTS = 2

#: I giorni per rispondere a un invito, quando non c'è una scadenza davanti.
PLAYOFF_RESPONSE_DAYS = 7


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

        if PlayoffService._gara_avviata(qualification.configuration):
            raise ConflictError(
                _(
                    "La gara di playoff è già cominciata: l'invito non si può "
                    "più accettare."
                )
            )

        qualification.confirm_participation(responded_by_id=responded_by_id)

        # Chi accetta dopo che la gara è nata ci entra, fino all'avvio: gli
        # inviti partono prima della gara e le risposte non arrivano tutte
        # insieme. Senza, il sì di un ritardatario — o del sostituto chiamato
        # da un rifiuto — restava confermato ma fuori dalla gara.
        PlayoffService._iscrivi_alla_gara(qualification)

        # Check if we can start the playoff campionato
        PlayoffService._check_playoff_readiness(qualification.configuration_id)

        return qualification

    @staticmethod
    def _gara_avviata(config: Optional[PlayoffConfiguration]) -> bool:
        """La gara di playoff esiste e il primo turno è partito."""
        from ..status_enum import GaraStatus

        gara = config.gara if config is not None else None
        if gara is None:
            return False
        in_attesa = (GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value)
        return (gara.current_round or 0) > 0 or (gara.status or "") not in in_attesa

    @staticmethod
    def _iscrivi_alla_gara(
        qualification: PlayoffQualification, *, d_ufficio: bool = False
    ) -> None:
        """Iscrive alla gara di playoff, se esiste già, un qualificato confermato.

        `d_ufficio` è l'aggiunta decisa dal direttore: entra anche oltre i
        posti. Chi arriva da un invito rispetta i posti, e trovandoli pieni va
        in lista d'attesa come in ogni gara.
        """
        from ..competition.inscription_service import InscriptionService

        gara = qualification.configuration.gara
        if gara is None:
            return
        InscriptionService.inscribe_user(
            user_id=qualification.user_id,
            gara_id=gara.id,
            _bypass_playoff_check=True,
            _d_ufficio=d_ufficio,
        )

    @staticmethod
    def chiudi_inviti_all_avvio(gara) -> int:
        """All'avvio della gara di playoff gli inviti senza risposta scadono.

        Nessun sostituto: la finale è cominciata e un posto non si riempie più.
        Chiamato dalla transizione `inscription → playing`, dentro la sua
        transazione. Restituisce quanti inviti ha chiuso.
        """
        if not getattr(gara, "playoff_config_id", None):
            return 0
        in_attesa = PlayoffQualification.query.filter_by(
            configuration_id=gara.playoff_config_id,
            status=QualificationStatus.PENDING,
        ).all()
        for qualification in in_attesa:
            qualification.expire_qualification()
        return len(in_attesa)

    @staticmethod
    def riapri_inviti_all_annullo(gara) -> int:
        """Annullato l'avvio della finale, gli inviti chiusi dall'avvio si riaprono.

        Tornano in attesa solo gli inviti che l'avvio aveva fatto scadere. Si
        riconoscono senza una colonna in più: **nessuno li ha sostituiti** e
        **la loro scadenza non è ancora passata**. Un invito scaduto per la sua
        scadenza la ha per forza già alle spalle — il job lo chiude solo
        allora — e uno sostituito ha già ceduto il posto: restano come sono.

        Chiamato da ogni strada che riporta la gara in iscrizione, dentro la
        sua transazione. Restituisce quanti inviti ha riaperto.
        """
        config_id = getattr(gara, "playoff_config_id", None)
        if not config_id:
            return 0
        config = db.session.get(PlayoffConfiguration, config_id)
        if config is None:
            return 0

        adesso = utc_now()
        scaduti = PlayoffQualification.query.filter_by(
            configuration_id=config_id,
            status=QualificationStatus.EXPIRED,
            replaced_by_id=None,
        ).all()
        riaperti = 0
        for qualification in scaduti:
            scadenza = qualification.expires_at or config.response_deadline
            if scadenza is not None and scadenza <= adesso:
                continue
            qualification.status = QualificationStatus.PENDING
            riaperti += 1
        return riaperti

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

        # Cerca e invita il sostituto a livello servizio (flusso documentato:
        # decline → invita il prossimo idoneo). Il modello non lo fa più:
        # prima decline_participation() chiamava un metodo inesistente su
        # PlayoffConfiguration via hasattr (sempre False) → nessun sostituto.
        return PlayoffService._invita_sostituto(
            qualification.configuration, qualification
        )

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
            modalita = PlayoffRankingMode.normalize(final_ranking_mode)
            # Si controlla il **passaggio** alla somma, non lo stato: il form
            # rimanda la modalità a ogni salvataggio del peso, e una finale
            # già incoerente — nata prima del 2026-09-14 — non deve impedire
            # al direttore di cambiare il peso.
            if (
                modalita is PlayoffRankingMode.CAMPIONATO_PLUS_PLAYOFF
                and config.decides_final_ranking
            ):
                PlayoffService._verifica_finale_sommabile(
                    config,
                    PlayoffService._sistema_della_finale(config).value,
                    somma=True,
                )
            config.final_ranking_mode = modalita.value

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
    def _sistema_della_finale(config: PlayoffConfiguration):
        """Il sistema di classifica che la finale ha, o avrebbe se la si creasse.

        Una finale già creata ha il suo. Altrimenti lo decide la strategia —
        esplicita o ereditata — con la stessa regola delle altre gare: il
        tabellone è POSITION, il resto segue il campionato.
        """
        from ..matchmaking.configuration import (
            MatchmakingStrategy,
            resolve_classification_system,
        )
        from ..status_enum import ClassificationSystem

        if config.gara is not None:
            return ClassificationSystem.resolve(config.gara.classification_system)
        strategia = (
            config.get_gara_params().get("matchmaking_strategy")
            or MatchmakingStrategy.AMALFI.value
        )
        return ClassificationSystem.resolve(
            resolve_classification_system(
                strategia, config.campionato.classification_system.value
            )
        )

    @staticmethod
    def _verifica_finale_sommabile(
        config: PlayoffConfiguration, sistema_finale: str, somma: bool = False
    ) -> None:
        """Una finale che si somma al campionato deve contare la stessa cosa.

        Vittorie e triangoli, o punti per posizione, non si sommano fra loro
        (SPECIFICHE.md riga 289). Con «solo playoff» il vincolo non c'è: della
        finale si legge solo l'ordine d'arrivo. `somma` dice che la modalità
        sommata sta per essere scelta ora, invece che letta dalla
        configurazione.
        """
        from flask_babel import gettext as _

        from ..exceptions import ValidationError

        if config.decides_final_ranking and not somma:
            return
        if sistema_finale == config.campionato.classification_system.value:
            return
        raise ValidationError(
            _(
                "Con «Campionato + gara di playoff» il punteggio della finale si "
                "somma a quello del campionato, quindi deve usare lo stesso "
                "sistema di classifica, e una finale a tabellone non si somma a "
                "un campionato che non lo è. Scegli «Solo i playoff», dove della "
                "finale conta solo l'ordine d'arrivo."
            )
        )

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
        adesso = utc_now()

        configurations = PlayoffConfiguration.query.filter(
            PlayoffConfiguration.response_deadline <= adesso,
            PlayoffConfiguration.is_active.is_(True),
        ).all()

        for config in configurations:
            expired_qualifications = PlayoffQualification.query.filter_by(
                configuration_id=config.id,
                status=QualificationStatus.PENDING,
            ).all()

            for qualification in expired_qualifications:
                # Un sostituto chiamato a scadenza generale già passata ha
                # una scadenza sua, più avanti: si rispetta quella.
                if (
                    qualification.expires_at is not None
                    and qualification.expires_at > adesso
                ):
                    continue
                qualification.expire_qualification()
                expired_count += 1
                PlayoffService._invita_sostituto(config, qualification)

        return expired_count

    @staticmethod
    def _scadenza_invito_sostituto(
        config: PlayoffConfiguration, adesso: datetime
    ) -> datetime:
        """La scadenza dell'invito a un sostituto.

        È la scadenza di tutti, `config.response_deadline`, finché è ancora
        davanti. Se è già passata o manca, il sostituto riceve gli stessi
        sette giorni che `start_playoff` dà quando la configurazione non ne
        fissa una: un invito nato scaduto non si potrebbe accettare, e il job
        delle scadenze lo chiuderebbe alla prima occasione, facendo scorrere
        la cascata senza che nessuno abbia potuto rispondere.
        """
        scadenza = config.response_deadline
        if scadenza is not None and scadenza > adesso:
            return scadenza
        return adesso + timedelta(days=PLAYOFF_RESPONSE_DAYS)

    @staticmethod
    def _invita_sostituto(
        config: PlayoffConfiguration, sostituisce: PlayoffQualification
    ) -> Optional[PlayoffQualification]:
        """Chiama il primo degli esclusi al posto di `sostituisce` e lo invita.

        Una sola strada per tutti i sostituti, dal rifiuto — del giocatore o
        detto al direttore — e dalla scadenza: il sostituto riceve data
        d'invito, scadenza e notifica come gli invitati iniziali
        (SPECIFICHE.md, sezione «Playoff»: «la notifica passa al primo degli
        esclusi»). Fino al 2026-09-13 il rifiuto creava la qualificazione
        senza avvisare nessuno e senza scadenza.
        """
        sostituto = PlayoffService.find_replacement_player(
            config.id, sostituisce=sostituisce
        )
        if sostituto is None:
            return None
        adesso = utc_now()
        sostituto.invited_at = adesso
        sostituto.expires_at = PlayoffService._scadenza_invito_sostituto(config, adesso)
        # L'id serve al link della notifica.
        db.session.flush()
        PlayoffService._send_playoff_invitations(config, [sostituto])
        return sostituto

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
    def _valida_calendario(
        scheduled_date: Optional[datetime], response_deadline: Optional[datetime]
    ) -> None:
        """Data dei playoff e scadenza degli inviti stanno nel futuro."""
        adesso = utc_now()
        if response_deadline is not None and response_deadline <= adesso:
            raise ValidationError(_("La scadenza degli inviti deve essere nel futuro."))
        if scheduled_date is not None and scheduled_date <= adesso:
            raise ValidationError(_("La data dei playoff deve essere nel futuro."))

    @staticmethod
    @transactional(domain="playoff")
    def aggiorna_calendario(
        config_id: int,
        *,
        scheduled_date: Optional[datetime] = None,
        response_deadline: Optional[datetime] = None,
    ) -> PlayoffConfiguration:
        """Il direttore sposta la data dei playoff o la scadenza degli inviti.

        Si può fino all'avvio della gara di playoff: dopo, la finale è
        cominciata e gli inviti sono chiusi. La scadenza nuova vale per gli
        inviti ancora senza risposta — chi ha risposto non ne ha più bisogno —
        e la data nuova va anche sulla gara, se il direttore l'ha già creata,
        con lo stesso controllo d'ordine delle gare del campionato (ADR-016).

        Un valore uguale a quello salvato non cambia niente: il foglio li
        rimanda tutti e due, e chi sposta solo la data non deve vedersi
        rifiutare una scadenza già passata che non ha toccato.
        """
        config = db.session.get(PlayoffConfiguration, config_id)
        if config is None:
            raise NotFoundError("Configurazione playoff non trovata")
        if PlayoffService._gara_avviata(config):
            raise ConflictError(
                _(
                    "La gara di playoff è già cominciata: data e scadenza non si "
                    "cambiano più."
                )
            )

        def _invariato(nuovo: Optional[datetime], attuale: Optional[datetime]) -> bool:
            return (
                nuovo is not None
                and attuale is not None
                and nuovo.replace(second=0, microsecond=0)
                == attuale.replace(second=0, microsecond=0)
            )

        if _invariato(response_deadline, config.response_deadline):
            response_deadline = None
        if _invariato(scheduled_date, config.scheduled_date):
            scheduled_date = None
        PlayoffService._valida_calendario(scheduled_date, response_deadline)

        if response_deadline is not None:
            config.response_deadline = response_deadline
            in_attesa = PlayoffQualification.query.filter_by(
                configuration_id=config.id, status=QualificationStatus.PENDING
            ).all()
            for qualification in in_attesa:
                qualification.expires_at = response_deadline

        if scheduled_date is not None:
            gara = config.gara
            if gara is not None:
                from ..competition.services import GaraService

                try:
                    GaraService._validate_sequential_date(
                        campionato_id=gara.campionato_id,
                        number=gara.number,
                        gara_date=scheduled_date.date(),
                        gara_time=scheduled_date.time(),
                    )
                except ValueError as errore:
                    raise ValidationError(str(errore)) from errore
                gara.date = scheduled_date.date()
                gara.time = scheduled_date.time()
            config.scheduled_date = scheduled_date

        return config

    @staticmethod
    @transactional(domain="playoff")
    def start_playoff(
        campionato_id: int,
        *,
        scheduled_date: Optional[datetime] = None,
        response_deadline: Optional[datetime] = None,
    ) -> Dict[str, List[PlayoffQualification]]:
        """Start playoffs: generate qualifications from classification.

        Iterates over all active configs of the campionato. Sets
        response_deadline (default 7 days) and sends notifications.
        Returns dict of config_name → list of new qualifications.

        `scheduled_date` e `response_deadline` li sceglie il direttore nel
        foglio «Avvia i playoff» e valgono per tutte le configurazioni attive;
        dopo si spostano con `aggiorna_calendario`. Senza valori resta la
        scadenza di configurazione o, se manca, sette giorni: la competizione
        di prova e gli altri chiamanti non cambiano.
        """
        PlayoffService._valida_calendario(scheduled_date, response_deadline)

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
            # Quel che il direttore ha scelto nel foglio vale per tutte.
            if scheduled_date is not None:
                config.scheduled_date = scheduled_date
            if response_deadline is not None:
                config.response_deadline = response_deadline
            # Set deadline if not explicitly configured
            if config.response_deadline is None:
                config.response_deadline = now + timedelta(days=PLAYOFF_RESPONSE_DAYS)

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
        from flask_babel import lazy_gettext as _l
        from ..notification.services import NotificationService
        from ..notification.models import NotificationType, NotificationPriority

        if not qualifications:
            return

        campionato_name = config.campionato.name if config.campionato else ""

        for qual in qualifications:
            try:
                # Ogni invitato legge l'invito nella sua lingua (ADR-062).
                NotificationService.create_notification(
                    user_id=qual.user_id,
                    notification_type=NotificationType.PLAYOFF_INVITATION,
                    title=_l("Invito Playoff — %(nome)s", nome=config.name),
                    message=_l(
                        "Sei stato qualificato per %(nome)s del campionato "
                        "%(campionato)s. Conferma o rifiuta la partecipazione.",
                        nome=config.name,
                        campionato=campionato_name,
                    ),
                    priority=NotificationPriority.HIGH,
                    action_url=f"/player/playoff/invitation/{qual.id}",
                    action_text=_l("Conferma o rifiuta"),
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

        # Il sistema della finale (SPECIFICHE.md riga 289). Fino al 2026-09-14
        # non veniva passato e la gara prendeva il default della colonna, WINS:
        # un campionato a triangoli totali si chiudeva con una finale a
        # vittorie. Quando il punteggio si somma dev'essere quello del
        # campionato; con «solo playoff» conta solo l'ordine d'arrivo, e un
        # tabellone porta il suo.
        classification_system = PlayoffService._sistema_della_finale(config).value
        PlayoffService._verifica_finale_sommabile(config, classification_system)

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
            # Il playoff si gioca con chi ha accettato, anche se sono meno dei
            # posti (SPECIFICHE.md, «Playoff»: «oppure sono finiti i
            # giocatori»). Senza, la gara prendeva il minimo di default delle
            # gare di serata, sei, e un playoff da quattro non partiva mai.
            min_participants=PLAYOFF_MIN_PARTICIPANTS,
            playoff_config_id=config.id,
            classification_system=classification_system,
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

        # D'ufficio, cioè senza lista d'attesa: gli inviti vivi non superano
        # mai i posti, perché la cascata chiama un sostituto solo per chi esce,
        # quindi un confermato oltre i posti può essere solo un giocatore
        # aggiunto dal direttore — ed entra comunque.
        for qual in confirmed:
            InscriptionService.inscribe_user(
                user_id=qual.user_id,
                gara_id=gara.id,
                _bypass_playoff_check=True,
                _d_ufficio=True,
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

        # La lista si chiude all'avvio, non alla creazione: fino ad allora chi
        # entra dall'invito entra anche in gara, e il direttore deve poter fare
        # lo stesso.
        if PlayoffService._gara_avviata(config):
            raise ConflictError(
                _("La gara di playoff è già cominciata: la lista non si modifica più.")
            )

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
        db.session.flush()
        # Una scelta esplicita del direttore: entra anche oltre i posti.
        PlayoffService._iscrivi_alla_gara(qual, d_ufficio=True)
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
        if PlayoffService._gara_avviata(config):
            raise ConflictError(
                _("La gara di playoff è già cominciata: la lista non si modifica più.")
            )

        # A gara creata e non ancora avviata chi esce dalla lista esce anche
        # dalla gara, come chi ci entra ci entra.
        if config.gara is not None:
            from ..competition.inscription_service import InscriptionService

            InscriptionService.uninscribe_user(qual.user_id, config.gara.id)

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
