# models/campionato/tournament_service.py
"""CRUD and lifecycle operations for Campionato.

Extracted from services.py for maintainability (Round 4 P4).
Inherits statistics methods from TournamentStatisticsService.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any
from models.user.models import User
from models.match.models import Match
from models.match.break_rules import DEFAULT_BREAK_RULE, DEFAULT_START_RULE
from sqlalchemy.exc import IntegrityError

from models.base import db, utc_now
from models.exceptions import NotFoundError, ValidationError
from .models import Campionato
from ..user.role_enum import UserRole
from ..transaction.manager import (
    transactional,
    read_only,
)
from models.events.base import EventBus
from models.events.competition_events import (
    DirectorAssignmentAddedEvent,
    DirectorAssignmentRemovedEvent,
    CampionatoCreatedEvent,
)
from .statistics_service import TournamentStatisticsService, compute_campionato_status


class TournamentService(TournamentStatisticsService):
    """Operazioni di business sui Campionati (API di base conservate).

    Inherits statistics/classification methods from TournamentStatisticsService.
    """

    @transactional(domain="campionato")
    def create_campionato(self, name: str, **kwargs: Any) -> Campionato:
        """Crea e persiste un campionato (API compatibile con test esistenti)."""

        # Filter valid kwargs for Campionato model
        valid_campionato_fields = {
            # Core configuration
            "campionato_type",
            "challenge_mode",
            "is_active",
            "planned_gare_count",
            # Default values for gare
            "default_venue_id",
            "default_entry_fee",
            "default_rounds_count",
            "default_odd_policy",
            "default_anti_rematch",
            "has_handicap",
            "default_time_limit_minutes",
            "default_max_groups",
            "default_group_seeding",
            "default_final_phase_mode",
            "default_qualifiers_per_group",
            "default_third_place_match",
            "default_final_phase_time_limit_minutes",
            "default_final_phase_distance",
            "default_final_time_limit_minutes",
            "default_final_distance",
            "default_gara_classification_system",
            "default_catena_turno",
            "default_catena_gara",
            "catena_generale",
            # Deprecated but kept for compatibility
            "without_x",
            "final_playoffs",
            "scoring_policy",
        }
        filtered_kwargs = {
            k: v for k, v in kwargs.items() if k in valid_campionato_fields
        }

        # Extract director_id if present for separate handling
        director_id = kwargs.get("director_id")

        campionato = Campionato(name=name, **filtered_kwargs)
        self._verifica_gironi_del_campionato(campionato)
        db.session.add(campionato)
        db.session.flush()  # Flush to ensure ID is assigned

        # Handle director assignment if director_id provided
        if director_id:
            from ..user.models import DirectorAssignment

            director_assignment = DirectorAssignment(
                user_id=director_id,
                entity_type="campionato",
                entity_id=campionato.id,
                assigned_by_id=director_id,  # Self-assignment for now
            )
            db.session.add(director_assignment)

        # Publish creation event
        if director_id:
            event = CampionatoCreatedEvent(
                campionato_id=campionato.id,
                name=campionato.name,
                creator_id=director_id,
                campionato_type=campionato.campionato_type or "amalfi",
            )
            EventBus.publish(event)

        return campionato

    @transactional(domain="campionato")
    def create_campionato_with_director(
        self,
        name: str,
        creator_user_id: int,
        campionato_type: str = "amalfi",
        challenge_mode: bool = False,
        is_active: bool = True,
        # New fields - wizard step 1
        planned_gare_count: int = 10,
        # New fields - wizard step 2 (defaults for gare)
        default_venue_id: Optional[int] = None,
        default_entry_fee: Optional[float] = None,
        default_rounds_count: int = 3,
        default_odd_policy: str = "bye",
        default_anti_rematch: bool = True,
        default_classification_system: str = "WINS",
        # Nei campionati a piazzamenti, il sistema proposto alle serate
        # (ADR-080). None = vittorie.
        default_gara_classification_system: Optional[str] = None,
        has_handicap: bool = False,
        # Limite di tempo per partita proposto alle gare (ADR-077). 0 = nessuno.
        default_time_limit_minutes: int = 0,
        # I gironi del girone all'italiana proposti alle gare (ADR-076).
        default_max_groups: int = 1,
        default_group_seeding: str = "sorteggio",
        # La fase finale dopo i gironi proposta alle gare (ADR-081).
        default_final_phase_mode: str = "nessuna",
        default_qualifiers_per_group: int = 2,
        default_third_place_match: bool = False,
        default_final_phase_time_limit_minutes: Optional[int] = None,
        # Le regole del tabellone per fase (emendamento del 2026-10-12).
        default_final_phase_distance: Optional[int] = None,
        default_final_time_limit_minutes: Optional[int] = None,
        default_final_distance: Optional[int] = None,
        # Le catene degli spareggi (ADR-078): None = il default dell'app.
        default_catena_turno: Optional[str] = None,
        default_catena_gara: Optional[str] = None,
        catena_generale: Optional[str] = None,
        # I punti della classifica a punti proposti alle gare (ADR-078).
        default_points_win: int = 3,
        default_points_draw: int = 1,
        default_points_loss: int = 0,
        # Come si comincia, e chi apre poi (ADR-056). I default sono il
        # comportamento storico: apre il primo giocatore, tiri di apertura
        # alternati.
        default_start_rule: str = DEFAULT_START_RULE.value,
        default_break_rule: str = DEFAULT_BREAK_RULE.value,
        # Punti per posizione delle gare a tabellone (US-17). None = usa i
        # valori di default della spec, che restano quelli anche se un domani
        # cambiano: un campionato non configurato li **segue**, non ne
        # conserva una copia.
        position_points: Optional[str] = None,
        # Deprecated but kept for compatibility
        without_x: bool = False,
        final_playoffs: bool = False,
        scoring_policy: str = "classic",
        # Competizione di prova (ADR-058): i due campi arrivano insieme da
        # `ProvaService.campi_di_creazione()`. Le gare del campionato
        # erediteranno il flag alla nascita (`GaraService.create_gara`).
        is_prova: bool = False,
        prova_expires_at: Optional[Any] = None,
    ) -> Campionato:
        """Crea campionato e assegna automaticamente il direttore se necessario."""

        # Import locale per evitare import circolari
        from models.user.models import User, DirectorAssignment

        user = db.session.get(User, creator_user_id)
        if not user:
            raise NotFoundError("User not found")

        campionato = Campionato(
            name=name,
            campionato_type=campionato_type,
            challenge_mode=challenge_mode,
            is_active=is_active,
            planned_gare_count=planned_gare_count,
            default_venue_id=default_venue_id,
            default_entry_fee=default_entry_fee,
            default_rounds_count=default_rounds_count,
            default_odd_policy=default_odd_policy,
            default_anti_rematch=default_anti_rematch,
            default_classification_system=default_classification_system,
            default_gara_classification_system=default_gara_classification_system,
            has_handicap=has_handicap,
            default_time_limit_minutes=default_time_limit_minutes,
            default_max_groups=default_max_groups,
            default_group_seeding=default_group_seeding,
            default_final_phase_mode=default_final_phase_mode,
            default_qualifiers_per_group=default_qualifiers_per_group,
            default_third_place_match=default_third_place_match,
            default_final_phase_time_limit_minutes=(
                default_final_phase_time_limit_minutes
            ),
            default_final_phase_distance=default_final_phase_distance,
            default_final_time_limit_minutes=default_final_time_limit_minutes,
            default_final_distance=default_final_distance,
            default_catena_turno=default_catena_turno,
            default_catena_gara=default_catena_gara,
            catena_generale=catena_generale,
            default_points_win=default_points_win,
            default_points_draw=default_points_draw,
            default_points_loss=default_points_loss,
            default_start_rule=default_start_rule,
            default_break_rule=default_break_rule,
            position_points=position_points,
            is_prova=is_prova,
            prova_expires_at=prova_expires_at,
            # Deprecated fields
            without_x=without_x,
            final_playoffs=final_playoffs,
            scoring_policy=scoring_policy,
        )
        self._verifica_gironi_del_campionato(campionato)
        db.session.add(campionato)
        db.session.flush()  # Per ottenere l'ID senza commit completo

        # Se l'utente è un direttore (non admin), assegnalo automaticamente
        if user.is_director and not user.is_admin:
            assignment = DirectorAssignment(
                entity_type="campionato",
                entity_id=campionato.id,
                user_id=creator_user_id,
                assigned_by_id=creator_user_id,
            )
            db.session.add(assignment)

        # Publish creation event
        event = CampionatoCreatedEvent(
            campionato_id=campionato.id,
            name=campionato.name,
            creator_id=creator_user_id,
            campionato_type=campionato.campionato_type or "amalfi",
        )
        EventBus.publish(event)

        return campionato

    @transactional(domain="campionato")
    def update_campionato(
        self,
        campionato_id: int,
        autore: Any = None,
        motivo: Optional[str] = None,
        **kwargs: Any,
    ) -> Campionato:
        """Aggiorna un campionato con i campi forniti, e lo scrive nella storia.

        Fino al 2026-09-29 bastava una gara con iscrizioni aperte, in corso o
        conclusa per bloccare tutto il campionato. Ora (ADR-075) si modifica
        sempre: i suoi valori sono quelli **proposti** alle gare, e cambiarli
        non tocca le gare già create — a quelle l'app li propone
        (`models/campionato/proposte.py`). Il sistema di classifica fa
        eccezione: vale per tutto il campionato e si blocca al primo avvio.
        """
        from models.storia.models import SettingsChangeSource
        from models.storia.service import StoriaModificheService

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise NotFoundError("Campionato not found")
        self._gironi_alla_somma(campionato, kwargs)
        prima = {
            campo: getattr(campionato, campo)
            for campo in kwargs
            if hasattr(campionato, campo)
        }

        # Il form rimanda sempre il sistema: conta solo se cambia davvero.
        from models.status_enum import ClassificationSystem

        nuovo_sistema = kwargs.get("default_classification_system")
        cambia_sistema = nuovo_sistema is not None and ClassificationSystem.normalize(
            nuovo_sistema
        ) != ClassificationSystem.normalize(campionato.default_classification_system)
        if cambia_sistema:
            self._verifica_cambio_sistema(campionato)
        from models.campionato.piazzamenti import sistema_delle_gare

        gare_prima = sistema_delle_gare(campionato)

        # Aggiorna solo i campi forniti
        for field, value in kwargs.items():
            if hasattr(campionato, field):
                setattr(campionato, field, value)
        if {"default_max_groups", "default_final_phase_mode"} & set(kwargs):
            self._verifica_piazzamento_proposto(campionato)

        if cambia_sistema or sistema_delle_gare(campionato) != gare_prima:
            self._adegua_catene_del_campionato(campionato, gare_prima, prima, kwargs)
        if cambia_sistema:
            self._propaga_sistema(campionato, autore=autore, motivo=motivo)

        cambi = {campo: (prima[campo], getattr(campionato, campo)) for campo in prima}
        # I punti per posizione cambiano quanto contano gare già giocate:
        # con una gara conclusa sono un ricalcolo, in una voce a sé, e la
        # classifica lo segnala (ADR-075).
        from models.storia.models import SettingsChangeAction
        from models.storia.ricalcolo import (
            gara_finita_nel_campionato,
            ricalcola_campionato,
        )
        from models.storia.service import serializza

        # Lo stesso vale per la catena della classifica generale (ADR-078):
        # riordina i pari merito di gare già giocate.
        ricalcolo = {
            campo: cambi.pop(campo)
            for campo in ("position_points", "catena_generale")
            if campo in cambi
            and serializza(cambi[campo][0]) != serializza(cambi[campo][1])
        }
        for campo in ("position_points", "catena_generale"):
            cambi.pop(campo, None)
        StoriaModificheService.registra(
            cambi=cambi,
            campionato_id=campionato.id,
            autore=autore,
            motivo=motivo,
            provenienza=SettingsChangeSource.CAMPIONATO,
        )
        if ricalcolo:
            StoriaModificheService.registra(
                cambi=ricalcolo,
                campionato_id=campionato.id,
                autore=autore,
                motivo=motivo,
                provenienza=SettingsChangeSource.CAMPIONATO,
                azione=(
                    SettingsChangeAction.RICALCOLO
                    if gara_finita_nel_campionato(campionato)
                    else SettingsChangeAction.MODIFICA
                ),
            )
            ricalcola_campionato(campionato.id)

        campionato.updated_at = utc_now()
        return campionato

    @staticmethod
    def _adegua_catene_del_campionato(
        campionato: Campionato, gare_prima: Any, prima: Dict, kwargs: Dict
    ) -> None:
        """Cambiato il sistema, le catene di default del campionato lo seguono.

        Solo quelle che il modulo non ha mandato: le altre le ha già decise
        il direttore. Il cambio finisce nella storia con gli altri. Le due
        catene proposte alle gare seguono il sistema **delle gare** — in un
        campionato a piazzamenti, quello delle serate (ADR-080) —, quella
        della classifica generale il sistema del campionato.
        """
        from models.campionato.piazzamenti import sistema_delle_gare
        from models.classification.catene import adegua_al_sistema
        from models.classification.ordinamento import Livello
        from models.status_enum import ClassificationSystem

        vecchio_generale = ClassificationSystem.resolve(
            prima.get(
                "default_classification_system",
                campionato.default_classification_system,
            )
        )
        nuovo_generale = ClassificationSystem.resolve(
            campionato.default_classification_system
        )
        vecchio_gare = ClassificationSystem.resolve(gare_prima)
        nuovo_gare = ClassificationSystem.resolve(sistema_delle_gare(campionato))
        for campo, livello in (
            ("default_catena_turno", Livello.TURNO),
            ("default_catena_gara", Livello.GARA),
            ("catena_generale", Livello.CAMPIONATO),
        ):
            if campo in kwargs:
                continue
            if livello is Livello.CAMPIONATO:
                vecchio, nuovo = vecchio_generale, nuovo_generale
            else:
                vecchio, nuovo = vecchio_gare, nuovo_gare
            if vecchio == nuovo:
                continue
            attuale = getattr(campionato, campo)
            adeguata = adegua_al_sistema(attuale, livello, vecchio, nuovo)
            if adeguata is not None and adeguata != attuale:
                prima[campo] = attuale
                setattr(campionato, campo, adeguata)

    @staticmethod
    def _messaggio_girone_unico() -> str:
        from flask_babel import gettext as _

        return _(
            "Un campionato che somma vittorie, triangoli o punti propone gare a "
            "girone unico: chi capita nel girone più numeroso giocherebbe una "
            "partita in più. Per i gironi scegli la classifica a piazzamenti."
        )

    @classmethod
    def _verifica_gironi_del_campionato(cls, campionato: Campionato) -> None:
        """Un campionato che somma i totali non propone più gironi (ADR-080)."""
        from models.campionato.piazzamenti import somma_i_totali
        from models.matchmaking.gironi import tetto_di_gironi

        if (
            somma_i_totali(campionato)
            and tetto_di_gironi(campionato.default_max_groups) > 1
        ):
            raise ValidationError(cls._messaggio_girone_unico())
        cls._verifica_piazzamento_proposto(campionato)

    @staticmethod
    def _verifica_piazzamento_proposto(campionato: Campionato) -> None:
        """Le finali per piazzamento si propongono solo con «Gironi: fino a 2».

        Con più gironi la formula non è definita (ADR-081, emendamento del
        2026-10-12); col girone unico la proposta non arriva alle gare e non
        si rifiuta, come il tabellone.
        """
        from flask_babel import gettext as _

        from models.matchmaking.fase_finale import FaseFinale, verifica_piazzamento
        from models.matchmaking.gironi import tetto_di_gironi

        tetto = tetto_di_gironi(campionato.default_max_groups)
        if (
            FaseFinale.resolve(campionato.default_final_phase_mode)
            is FaseFinale.PIAZZAMENTO
            and tetto > 1
            and verifica_piazzamento(tetto) is not None
        ):
            raise ValidationError(
                _(
                    "Le finali per piazzamento si giocano fra due gironi: "
                    "scegli «Gironi: fino a 2», oppure un'altra fase finale."
                )
            )

    @classmethod
    def _gironi_alla_somma(cls, campionato: Campionato, kwargs: Dict) -> None:
        """I gironi proposti, quando il campionato somma (o passa a sommare).

        Il modulo non mostra il campo a chi somma i totali, quindi non lo
        manda: un tetto rimasto da quando il campionato era a piazzamenti
        torna al girone unico, e il cambio finisce nella storia. Un tetto
        chiesto esplicitamente si rifiuta.
        """
        from types import SimpleNamespace

        from models.campionato.piazzamenti import somma_i_totali
        from models.matchmaking.gironi import tetto_di_gironi

        dopo = SimpleNamespace(
            campionato_type=kwargs.get("campionato_type", campionato.campionato_type),
            default_classification_system=kwargs.get(
                "default_classification_system",
                campionato.default_classification_system,
            ),
        )
        if not somma_i_totali(dopo):
            return
        # Senza gironi non c'è fase finale (ADR-081): si toglie insieme.
        from models.matchmaking.fase_finale import FaseFinale

        if campionato.default_final_phase_mode != FaseFinale.NESSUNA.value:
            kwargs["default_final_phase_mode"] = FaseFinale.NESSUNA.value
        if "default_max_groups" in kwargs:
            if tetto_di_gironi(kwargs["default_max_groups"]) > 1:
                raise ValidationError(cls._messaggio_girone_unico())
            return
        if tetto_di_gironi(campionato.default_max_groups) > 1:
            kwargs["default_max_groups"] = 1

    @staticmethod
    def _gare_col_sistema_del_campionato(campionato: Campionato) -> list:
        """Le gare che devono avere il sistema del campionato.

        Fuori le eliminate e le annullate: nessuno le giocherà, e nessuna
        classifica le somma.
        """
        from models.status_enum import GaraStatus

        return [
            gara
            for gara in campionato.gare
            if not gara.is_deleted and gara.status != GaraStatus.CANCELLED.value
        ]

    @classmethod
    def _verifica_cambio_sistema(cls, campionato: Campionato) -> None:
        """Il sistema di classifica si cambia finché nessuna gara è avviata.

        È l'unico valore del campionato che vale per **tutte** le sue gare: la
        classifica generale somma le classifiche delle gare, e devono essere
        dello stesso tipo (SPECIFICHE.md, «Tutte le gare di un campionato
        devono usare lo stesso sistema»). Fino al 2026-09-29 si bloccava alla
        prima gara con le iscrizioni aperte; ora (ADR-075) al primo avvio,
        anche se le gare hanno già iscritti: il cambio arriva a tutte, e resta
        nella storia di ciascuna.
        """
        from flask_babel import gettext as _
        from models.competition.campi_modificabili import e_avviata

        for gara in cls._gare_col_sistema_del_campionato(campionato):
            if e_avviata(gara):
                raise ValidationError(
                    _(
                        "Il sistema di classifica non si può più cambiare: la "
                        "gara «%(gara)s» è già avviata.",
                        gara=gara.name,
                    )
                )

    @classmethod
    def _propaga_sistema(
        cls, campionato: Campionato, autore: Any = None, motivo: Any = None
    ) -> None:
        """Porta il sistema nuovo del campionato a tutte le sue gare.

        Arrivati qui sono tutte da aprire. Una gara che col sistema nuovo non
        sarebbe valida — a triangoli totali la X semplice è vietata — ferma il
        cambio intero: la transazione si annulla e il campionato non resta a
        metà.
        """
        from flask_babel import gettext as _
        from models.competition.validators import validate_gara
        from models.matchmaking.configuration import resolve_classification_system

        from models.storia.models import SettingsChangeSource
        from models.storia.service import StoriaModificheService

        from models.classification.catene import COLONNA_DELLA_GARA, adegua_al_sistema
        from models.status_enum import ClassificationSystem

        from models.campionato.piazzamenti import (
            TIPI_A_TABELLONE,
            e_a_piazzamenti,
            sistema_della_serata,
            sistema_delle_gare,
        )
        from models.matchmaking.fase_finale import FaseFinale
        from models.matchmaking.gironi import tetto_di_gironi

        a_piazzamenti = e_a_piazzamenti(campionato)
        sistema = campionato.classification_system.value
        for gara in cls._gare_col_sistema_del_campionato(campionato):
            vecchio = gara.classification_system
            if a_piazzamenti:
                # Le serate tengono il loro sistema: ordina solo la serata, e
                # nel campionato conta il piazzamento (ADR-080).
                richiesto = (
                    sistema_della_serata(vecchio)
                    if ClassificationSystem.normalize(vecchio)
                    != ClassificationSystem.POSITION
                    else None
                ) or sistema_delle_gare(campionato)
                gara.classification_system = resolve_classification_system(
                    gara.matchmaking_strategy, richiesto
                )
            else:
                # Sommando i totali le gare contano tutte la stessa cosa: un
                # tabellone non ha totali da sommare, e i gironi tornano uno.
                if gara.matchmaking_strategy in TIPI_A_TABELLONE:
                    raise ValidationError(
                        _(
                            "La gara «%(gara)s» è a tabellone: in un campionato "
                            "che somma vittorie, triangoli o punti non avrebbe "
                            "totali da sommare. Cambiale formato, o resta a "
                            "piazzamenti.",
                            gara=gara.name,
                        )
                    )
                gara.classification_system = resolve_classification_system(
                    gara.matchmaking_strategy, sistema
                )
            cambi: Dict[str, Any] = {
                "classification_system": (vecchio, gara.classification_system)
            }
            if not a_piazzamenti and tetto_di_gironi(gara.max_groups) > 1:
                cambi["max_groups"] = (gara.max_groups, 1)
                gara.max_groups = 1
            # Sommando i totali non c'è fase finale (ADR-081).
            if (
                not a_piazzamenti
                and gara.final_phase_mode
                and gara.final_phase_mode != FaseFinale.NESSUNA.value
            ):
                cambi["final_phase_mode"] = (
                    gara.final_phase_mode,
                    FaseFinale.NESSUNA.value,
                )
                gara.final_phase_mode = FaseFinale.NESSUNA.value
            # Le catene di default seguono il sistema; quelle scelte restano.
            for livello, campo in COLONNA_DELLA_GARA.items():
                prima = getattr(gara, campo)
                nuova = adegua_al_sistema(
                    prima,
                    livello,
                    ClassificationSystem.resolve(vecchio),
                    ClassificationSystem.resolve(gara.classification_system),
                )
                if nuova is not None and nuova != prima:
                    setattr(gara, campo, nuova)
                    cambi[campo] = (prima, nuova)
            StoriaModificheService.registra(
                cambi=cambi,
                gara_id=gara.id,
                autore=autore,
                motivo=motivo,
                provenienza=SettingsChangeSource.CAMPIONATO,
            )
            errori, _avvisi = validate_gara(gara)
            if errori:
                raise ValidationError(
                    _(
                        "Con il nuovo sistema di classifica la gara «%(gara)s» "
                        "non sarebbe valida: %(errori)s",
                        gara=gara.name,
                        errori="; ".join(errori),
                    )
                )

    @transactional(domain="campionato")
    def toggle_active_status(self, campionato_id: int) -> Campionato:
        """Attiva/disattiva un campionato."""

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise NotFoundError("Campionato not found")

        campionato.is_active = not campionato.is_active
        campionato.updated_at = utc_now()
        return campionato

    @transactional(domain="campionato")
    def add_director(
        self, campionato_id: int, user_id: int, assigned_by_id: int
    ) -> bool:
        """Aggiunge un co-direttore al campionato.

        Returns:
            True se aggiunto con successo, False se già esistente

        Raises:
            ValueError se l'utente è admin
        """

        # Import locale per evitare import circolari
        from models.user.models import User, DirectorAssignment

        user = db.session.get(User, user_id)
        if not user:
            raise NotFoundError("User not found")

        if user.role == UserRole.ADMIN.value:
            raise ValidationError("Gli admin non vanno assegnati come direttori.")

        # Solo utenti con ruolo director (stessa regola di GaraService: la UI
        # offre solo direttori, il service deve imporlo).
        if user.role != UserRole.DIRECTOR.value:
            raise ValidationError(
                "Solo gli utenti con ruolo direttore possono essere co-direttori"
            )

        existing = DirectorAssignment.query.filter_by(
            entity_type="campionato", entity_id=campionato_id, user_id=user_id
        ).first()

        if existing:
            return False  # Già esistente

        assignment = DirectorAssignment(
            entity_type="campionato",
            entity_id=campionato_id,
            user_id=user_id,
            assigned_by_id=assigned_by_id,
        )
        db.session.add(assignment)

        # Pubblica evento per notifica (pattern event-driven)
        campionato = db.session.get(Campionato, campionato_id)
        event = DirectorAssignmentAddedEvent(
            entity_type="campionato",
            entity_id=campionato_id,
            entity_name=campionato.name,
            user_id=user_id,
            username=user.username,
            assigned_by_id=assigned_by_id,
        )
        EventBus.publish(event)

        return True

    @transactional(domain="campionato")
    def remove_director(self, campionato_id: int, user_id: int) -> bool:
        """Rimuove un co-direttore dal campionato.

        Returns:
            True se rimosso con successo, False se non trovato
        """

        # Import locale per evitare import circolari
        from models.user.models import DirectorAssignment, User

        assignment = DirectorAssignment.query.filter_by(
            entity_type="campionato", entity_id=campionato_id, user_id=user_id
        ).first()

        if not assignment:
            return False

        # Recupera dati per evento prima di eliminare
        user = db.session.get(User, user_id)
        campionato = db.session.get(Campionato, campionato_id)

        # Elimina associazione
        db.session.delete(assignment)

        # Pubblica evento per notifica (pattern event-driven)
        event = DirectorAssignmentRemovedEvent(
            entity_type="campionato",
            entity_id=campionato_id,
            entity_name=campionato.name,
            user_id=user_id,
            username=user.username,
            removed_by_id=assignment.assigned_by_id,
        )
        EventBus.publish(event)

        return True

    @read_only(domain="campionato")
    def get_active_campionatos(self) -> List[Campionato]:
        """Restituisce i campionati attivi (non soft-deleted)."""

        return Campionato.get_active_campionatos().all()

    @staticmethod
    def data_proposta_gara(campionato_id: int) -> Any:
        """La data con cui precompilare il modulo della prossima gara.

        SPECIFICHE.md: «oggi per la prima gara o una settimana più avanti
        rispetto all'ultima gara aggiunta al campionato». In una competizione
        di prova (ADR-058) le gare stanno nei prossimi giorni — domani la
        prima, il giorno dopo l'ultima le altre — perché il direttore le
        gioca tutte in una sessione e non deve inventarsi un calendario.

        Si guarda anche fra le gare soft-eliminate: il controllo di ordine
        cronologico (ADR-016) non le salta, e una data più vecchia della loro
        verrebbe rifiutata.
        """
        from datetime import date, timedelta

        from sqlalchemy import func, select

        from models.competition.models import Gara

        campionato = db.session.execute(
            select(Campionato.is_prova)
            .where(Campionato.id == campionato_id)
            .execution_options(include_prova=True, include_deleted=True)
        ).scalar()
        if campionato is None:
            # `False` è un campionato vero, `None` un campionato che non c'è:
            # la data di una gara per un campionato inesistente non ha senso.
            raise NotFoundError("Campionato not found")
        ultima = db.session.execute(
            select(func.max(Gara.date))
            .where(Gara.campionato_id == campionato_id)
            .execution_options(include_prova=True, include_deleted=True)
        ).scalar()
        if campionato:
            base = ultima or date.today()
            return base + timedelta(days=1)
        if ultima is None:
            return date.today()
        return ultima + timedelta(days=7)

    @transactional(domain="campionato")
    def delete_campionato(self, campionato_id: int) -> None:
        """
        Cancella un campionato rispettando le regole di dominio e garantendo atomicità.
        """

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise NotFoundError("Campionato not found")

        if not campionato.can_be_deleted():
            raise ValueError("Campionato non cancellabile: esistono iscrizioni.")

        # Clean up director assignments manually since it's a polymorphic relationship
        from models.user.models import DirectorAssignment

        assignments = (
            db.session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == campionato_id,
            )
            .all()
        )
        for assignment in assignments:
            db.session.delete(assignment)

        db.session.delete(campionato)
        try:
            # Transaction will be committed by decorator
            pass
        except IntegrityError:
            # Transaction will be rolled back by decorator
            raise

    @transactional(domain="campionato")
    def soft_delete_campionato(
        self,
        campionato_id: int,
        deleted_by_id: int,
        cascade_option: str = "delete_all",
        reason: Optional[str] = None,
    ) -> bool:
        """Soft delete campionato with cascade options."""

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise NotFoundError("Campionato not found")

        if campionato.is_deleted:
            return False

        # Handle cascade option for all garas in the campionato
        if cascade_option == "keep_matches":
            # Detach all matches from garas in this campionato
            gara_ids = [g.id for g in campionato.gare]
            if gara_ids:
                Match.query.filter(Match.gara_id.in_(gara_ids)).update(
                    {"gara_id": None}, synchronize_session="fetch"
                )

        # Soft delete all garas in the campionato
        for gara in campionato.gare:
            if not gara.is_deleted:
                gara.deleted_at = utc_now()
                gara.deleted_reason = reason or ""
                db.session.add(gara)

        # Soft delete the campionato itself
        success = campionato.soft_delete(reason or "")
        return success

    @transactional(domain="campionato")
    def permanently_delete_campionato(self, campionato_id: int) -> None:
        """
        Permanently delete a campionato (hard delete).
        Only allowed if no matches have been played.
        """

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise NotFoundError("Campionato not found")

        if not campionato.can_be_hard_deleted():
            raise ValueError("Cannot permanently delete campionato with played matches")

        db.session.delete(campionato)
        try:
            # Transaction will be committed by decorator
            pass
        except IntegrityError:
            # Transaction will be rolled back by decorator
            raise

    @read_only(domain="campionato")
    def get_campionato_detail_data(self, campionato_id: int) -> Dict[str, Any]:
        """
        Get all data needed for the campionato detail page.
        """
        from models.competition.models import Gara
        from models.user.models import User
        from sqlalchemy import not_

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise NotFoundError("Campionato not found")

        gare = (
            Gara.query.filter_by(campionato_id=campionato_id)
            .order_by(Gara.number)
            .all()
        )

        # ID dei direttori già assegnati a questo campionato
        from models.user.models import DirectorAssignment

        assigned_ids = [
            da.user_id
            for da in db.session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == campionato_id,
            )
            .all()
        ]

        # Solo utenti role='director' che non sono già assegnati
        candidate_directors = (
            User.query.filter_by(role="director")
            .filter(not_(User.id.in_(assigned_ids)))
            .order_by(User.username)
            .all()
        )

        return {
            "campionato": campionato,
            "gare": gare,
            "candidate_directors": candidate_directors,
        }

    @read_only(domain="campionato")
    def get_candidate_directors(self, campionato_id: int) -> List[User]:
        """
        Get directors not already assigned to this campionato.
        """
        from models.user.models import User
        from sqlalchemy import not_

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise NotFoundError("Campionato not found")

        # ID dei direttori già assegnati a questo campionato
        from models.user.models import DirectorAssignment

        assigned_ids = [
            da.user_id
            for da in db.session.query(DirectorAssignment)
            .filter(
                DirectorAssignment.entity_type == "campionato",
                DirectorAssignment.entity_id == campionato_id,
            )
            .all()
        ]

        # Solo utenti role='director' che non sono già assegnati
        candidate_directors = (
            User.query.filter_by(role="director")
            .filter(not_(User.id.in_(assigned_ids)))
            .order_by(User.username)
            .all()
        )

        return candidate_directors

    @read_only(domain="campionato")
    def calculate_campionato_status(self, campionato_id: int) -> str:
        """
        Calculate derived status information for a campionato.
        """

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise NotFoundError("Campionato not found")

        return compute_campionato_status(campionato)

    @staticmethod
    @transactional(domain="campionato")
    def create_playoff_config(
        campionato_id: int,
        name: str,
        max_participants: int,
        positions_from: int,
        positions_to: int,
        **configurazione: Any,
    ) -> Any:
        """Crea una configurazione dei playoff del campionato (wizard).

        ``configurazione`` sono gli altri campi che un preset porta con sé
        (`models.preset.payload.CAMPI_DEL_PLAYOFF`): passano dagli stessi
        controlli della correzione (`PlayoffService.update_configuration`),
        così un preset non fa nascere una finale che la pagina del campionato
        rifiuterebbe. Un campo fuori dalla whitelist si ignora.
        """
        from flask_babel import gettext as _

        from models.playoff.models import (
            PlayoffConfiguration,
            PlayoffRankingMode,
            PlayoffType,
        )
        from models.playoff.services import PlayoffService
        from models.preset.payload import CAMPI_DEL_PLAYOFF

        extra = {
            campo: valore
            for campo, valore in configurazione.items()
            if campo in CAMPI_DEL_PLAYOFF
            and campo
            not in ("name", "max_participants", "positions_from", "positions_to")
        }
        PlayoffService._verifica_valori_della_finale(extra)
        if extra.get("final_ranking_mode") is not None:
            extra["final_ranking_mode"] = PlayoffRankingMode.normalize(
                extra["final_ranking_mode"]
            ).value
        if extra.get("playoff_weight") is not None:
            if int(extra["playoff_weight"]) < 1:
                raise ValueError(_("Il peso del playoff è un intero maggiore di zero."))
        else:
            extra.pop("playoff_weight", None)

        config = PlayoffConfiguration(
            campionato_id=campionato_id,
            name=name,
            playoff_type=PlayoffType.TOP_N,
            max_participants=max_participants,
            positions_from=positions_from,
            positions_to=positions_to,
            is_active=True,
            auto_generate=True,
            **extra,
        )
        db.session.add(config)
        db.session.flush()
        if extra:
            # Una finale che si somma al campionato deve contare la stessa
            # cosa (SPECIFICHE.md, «Playoff»): lo stesso controllo della
            # pagina del campionato.
            PlayoffService._verifica_finale_sommabile(
                config, PlayoffService._sistema_della_finale(config).value
            )
        return config

    @transactional(domain="campionato")
    def terminate_campionato(self, campionato_id: int) -> bool:
        """Termina manualmente un campionato.

        Soft-elimina tutte le gare non-completed e marca il campionato
        come terminato. Idempotente: ritorna False se già terminato.

        Raises:
            ValueError: se campionato non trovato o soft-deleted
        """

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise NotFoundError("Campionato not found")
        if campionato.is_deleted:
            raise ValueError("Campionato già eliminato")
        if campionato.terminated_at:
            return False

        from models.status_enum import GaraStatus, MatchStatus
        from models.competition.state_service import StateService

        for gara in campionato.gare:
            if gara.is_deleted or gara.status == GaraStatus.COMPLETED.value:
                continue
            # Una gara con risultati reali (almeno un match concluso) NON va
            # MAI soft-eliminata alla terminazione: perderemmo i dati di
            # classifica già giocati. La completiamo per consolidarli; se non è
            # completabile (match ancora attivi) la lasciamo nello stato
            # corrente, ma mai eliminata. Solo le gare mai giocate (setup/
            # iscrizione/playing senza risultati) vengono soft-eliminate.
            #
            # NB: decidiamo su un fatto oggettivo (esiste un match concluso?),
            # non sullo stato derivato: una gara PLAYING a metà round o
            # AWAITING_SSR ha risultati reali pur non essendo "terminale".
            has_played_matches = (
                db.session.query(Match.id)
                .filter(
                    Match.gara_id == gara.id,
                    Match.status.in_(MatchStatus.finished_values()),
                )
                .first()
                is not None
            )
            if has_played_matches:
                # Una gara con la prova della X o gli esercizi dell'ultimo
                # turno ancora da registrare non si chiude: resta com'e', coi
                # suoi dati. Si controlla prima invece di lasciar sollevare
                # `complete`, perche' un rifiuto dentro questa transazione ne
                # annullerebbe anche il lavoro fatto sulle gare prima.
                from models.competition.pendenze_turno import (
                    pendenze_della_chiusura,
                )

                if pendenze_della_chiusura(gara).bloccano:
                    continue
                try:
                    StateService.complete(gara)
                except Exception:
                    # Match ancora attivi → non completabile, ma i dati restano.
                    pass
                continue
            gara.soft_delete("Campionato terminato")

        # Aggiorna la classifica del campionato in modo che start_playoff
        # trovi i Classification records popolati.
        try:
            from models.classification.campionato_classification import (
                ClassificationService,
            )

            ClassificationService.update_campionato_classification(campionato_id)
        except Exception:
            pass

        campionato.terminated_at = utc_now()
        campionato.updated_at = utc_now()
        campionato.is_active = False
        return True

    @read_only(domain="campionato")
    def check_playoff_feasibility(self, campionato_id: int) -> Dict[str, Any]:
        """Verifica se i playoff configurati sono fattibili.

        Confronta min_garas_played di ogni PlayoffConfiguration
        con il numero di gare completed del campionato.

        Returns:
            {"feasible": bool, "configs": [...], "completed_count": int}
        """

        campionato = db.session.get(Campionato, campionato_id)
        if not campionato:
            raise NotFoundError("Campionato not found")

        from models.status_enum import GaraStatus

        completed_count = sum(
            1
            for g in campionato.gare
            if not g.is_deleted and g.status == GaraStatus.COMPLETED.value
        )

        configs_info: List[Dict[str, Any]] = []
        all_feasible = True

        for config in campionato.playoff_configurations:
            if not config.is_active:
                continue
            min_req = config.min_garas_played or 0
            feasible = completed_count >= min_req
            if not feasible:
                all_feasible = False
            configs_info.append(
                {
                    "id": config.id,
                    "name": config.name,
                    "min_garas_played": min_req,
                    "feasible": feasible,
                }
            )

        return {
            "feasible": all_feasible,
            "configs": configs_info,
            "completed_count": completed_count,
        }

    @transactional(domain="campionato")
    def update_playoff_min_garas(
        self,
        campionato_id: int,
        config_id: int,
        new_min: int,
        autore: Any = None,
        motivo: Optional[str] = None,
    ) -> None:
        """Aggiorna min_garas_played di una PlayoffConfiguration.

        È un criterio di qualificazione: dal 2026-09-29 passa dagli stessi
        controlli della configurazione (bloccato a inviti partiti) e resta
        nella storia dei playoff (ADR-075).
        """

        from models.playoff.models import PlayoffConfiguration
        from models.playoff.services import PlayoffService

        config = db.session.get(PlayoffConfiguration, config_id)
        if not config:
            raise NotFoundError("PlayoffConfiguration not found")
        if config.campionato_id != campionato_id:
            raise ValueError("Configurazione non appartiene a questo campionato")
        PlayoffService.update_min_garas(
            config_id, new_min, autore=autore, motivo=motivo
        )

    def start_playoff(
        self,
        campionato_id: int,
        *,
        scheduled_date: Optional[datetime] = None,
        response_deadline: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Facade: start playoffs for a terminated campionato.

        Delegates to PlayoffService.start_playoff(), con la data dei playoff e
        la scadenza degli inviti scelte dal direttore.
        """
        from models.playoff.services import PlayoffService

        return PlayoffService.start_playoff(
            campionato_id,
            scheduled_date=scheduled_date,
            response_deadline=response_deadline,
        )
