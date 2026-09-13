"""
Module: models/user/models.py
Purpose: User domain models (User, TournamentDirector, DirectorRequest) –
    Task 1.4 completo.
Data Structures: User, TournamentDirector, DirectorRequest
Dependencies: models.base.db, flask_login, werkzeug.security
Updated: Added encryption for personal data (email, phone) per SPECIFICHE.md
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from flask import current_app
from flask_login import UserMixin
from sqlalchemy.orm import validates
from werkzeug.security import generate_password_hash, check_password_hash

from ..base import db, BaseModel  # BaseModel for timestamps, utc_now
from ..fields import EncryptedString  # Encrypted field types
from utils.encryption import compute_email_hash

if TYPE_CHECKING:
    from ..location.models import BilliardHall
from .role_enum import UserRole

if TYPE_CHECKING:  # Avoid runtime circular imports
    from ..match.models import Match
    from ..campionato.models import Campionato

from models.base import SoftDeleteMixin, utc_now


# ────────────────────────────────────────────────────────────────────────────────
# USER
# ────────────────────────────────────────────────────────────────────────────────
class User(UserMixin, BaseModel, SoftDeleteMixin):
    """Core user entity with role-based permissions and rich statistics."""

    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(
        EncryptedString(200), unique=True, nullable=True
    )  # Encrypted personal data
    # HMAC deterministico dell'email normalizzata: l'email cifrata (Fernet, non
    # deterministica) non e' filtrabile in SQL, quindi la lookup per email
    # passava per un O(N) che decifrava tutti gli utenti. email_hash permette un
    # lookup indicizzato O(1). Tenuto in sync da @validates("email"). Vedi #8.
    email_hash = db.Column(db.String(64), nullable=True, index=True)
    password_hash = db.Column(db.String(120), nullable=False)

    # Verification status
    is_verified = db.Column(db.Boolean, default=False, nullable=False)

    role = db.Column(db.String(20), nullable=False, default="player")
    # admin|director|player
    phone = db.Column(EncryptedString(100), nullable=True)  # Encrypted personal data

    # ── Anagrafica: chi è, oltre a come si chiama qui dentro ──────────────
    # Lo username è un soprannome, e in una sala dove tre persone si chiamano
    # `marco`, `marco_b` e `marcob` il direttore che iscrive qualcuno non ha
    # modo di sapere quale sia quello giusto (issue #156). L'email lo
    # direbbe, ma non si mostra a nessuno: nome e cognome sono il dato che
    # l'interessato sceglie di dare per farsi riconoscere.
    #
    # Cifrati come il telefono: sono dati personali, e la chiave sta fuori
    # dal database. Entrambi **facoltativi** — l'app funziona senza, e chi
    # non li vuole dare resta il suo username.
    first_name = db.Column(EncryptedString(100), nullable=True)
    last_name = db.Column(EncryptedString(100), nullable=True)

    # Rating systems (player skill metrics)
    elo_rating = db.Column(db.Integer, nullable=True)  # Elo rating

    # per utenti cancellati
    previous_username = db.Column(db.String(80), nullable=True)

    # Città "home" auto-dichiarata (livello città) usata come fallback per la
    # discovery di prossimità quando il GPS del browser non è disponibile
    # (ADR-034). Opt-in; mai coordinate precise dell'utente.
    home_city = db.Column(db.String(100), nullable=True)

    # Squadra dichiarata dal giocatore: **testo libero**, non una FK. Serve
    # solo a precompilare l'iscrizione alle gare che hanno attivato le
    # squadre; l'appartenenza che conta per il sorteggio è quella registrata
    # su Inscription.squadra_id, dentro la singola competizione.
    # Scrivibile solo dal giocatore stesso: né director né admin lo toccano.
    squadra = db.Column(db.String(100), nullable=True)

    # Fuso orario del giocatore, nome IANA (es. "Europe/Rome",
    # "America/New_York"). Non lo si chiede: lo si **deduce dal browser** al
    # login e a ogni pagina in cui risulta cambiato, perché è l'unico dato che
    # l'utente non sa di avere e che sbagliato rovina ogni orario che legge.
    #
    # Va salvato e non solo dedotto al volo: promemoria e notifiche nascono in
    # uno scheduled task, senza nessun browser da interrogare, e le caselle di
    # posta non eseguono JavaScript. Quello che non è scritto qui, fuori da una
    # pagina non esiste. Vedi ADR-043.
    #
    # NULL = mai dedotto: si ripiega sull'ora italiana, che è dove sta la
    # maggioranza dei giocatori e che era il comportamento di prima.
    timezone = db.Column(db.String(64), nullable=True)

    # Lingua in cui scrivere a questo utente: codice che l'app parla ("it",
    # "en"). Gemella del fuso, per la stessa ragione (ADR-062): una notifica
    # composta mentre un direttore preme un pulsante, o da uno scheduled task,
    # va scritta nella lingua di chi la **riceve**, e fuori da una pagina quella
    # lingua esiste solo se è scritta qui.
    #
    # La scrive il selettore della lingua, che è una scelta; oppure la deduzione
    # dal browser, che riempie solo un vuoto e non scavalca mai una scelta.
    # NULL = mai dedotta: si ripiega sull'italiano, il comportamento di prima.
    language = db.Column(db.String(8), nullable=True)

    # Onboarding obbligatorio (una volta sola) — ADR-035. Default False per
    # tutti, inclusi gli account esistenti (backfill): ognuno esegue
    # l'onboarding al primo login successivo al rilascio.
    onboarding_completed = db.Column(db.Boolean, default=False, nullable=False)
    # Interessi dichiarati nell'onboarding: CSV di token da un set chiuso
    # ("drill", "match", "tornei"). Opt-in, usato per personalizzare landing.
    onboarding_interests = db.Column(db.String(100), nullable=True)

    # Segnale-domanda → director (ADR-036). Raggio (km) della zona del director
    # per il conteggio delle richieste di domanda; regolabile dal director.
    signal_radius_km = db.Column(db.Integer, default=30, nullable=False)
    # Cooldown anti-nag: ultimo invio di notifica "soglia domanda raggiunta".
    signal_notified_at = db.Column(db.DateTime, nullable=True)
    # Ultimo accesso "attivo" (touch throttled per richiesta autenticata) —
    # usato per l'auto-refresh dei segnali-domanda (ADR-036). Opt-out di privacy
    # non necessario: è un timestamp grezzo, non una posizione.
    last_active_at = db.Column(db.DateTime, nullable=True)

    # Gamification Override
    gamification_override = db.Column(db.Boolean, default=False, nullable=False)

    # Giocatore fittizio di una competizione di prova (ADR-058). Nasce con la
    # prova e muore con lei: e' l'unico `User` che si cancella fisicamente.
    # Non ha login, non compare in nessun elenco fuori dalla sua prova
    # (filtro di sessione in `models/prova/visibility.py`), e il motore di
    # rating lo ignora. Le due FK dicono a quale radice appartiene: una sola
    # delle due e' valorizzata.
    #
    # Senza `ForeignKey`, di proposito: `gara.director_id` riferisce gia'
    # `user`, e una FK qui chiuderebbe un ciclo user ↔ gara / campionato che
    # SQLAlchemy non sa piu' ordinare — `drop_all` butta giu' `gara` con i
    # fittizi ancora dentro e, con `foreign_keys=ON`, SQLite rifiuta. Il
    # legame lo garantisce il servizio: un fittizio nasce dalla sua prova e
    # muore con lei (`ProvaService._elimina` li toglie prima della radice).
    is_fittizio = db.Column(db.Boolean, default=False, nullable=False, index=True)
    prova_gara_id = db.Column(db.Integer, nullable=True, index=True)
    prova_campionato_id = db.Column(db.Integer, nullable=True, index=True)

    # Relationships (string names to postpone model imports)
    inscriptions = db.relationship("Inscription", back_populates="user", lazy=True)
    match_results = db.relationship(
        "MatchResult", foreign_keys="MatchResult.user_id", lazy=True
    )
    classifications = db.relationship(
        "Classification", back_populates="user", lazy=True
    )
    # Additional relationships for classification domain
    round_classifications = db.relationship(
        "RoundClassification", back_populates="user", lazy=True
    )
    gara_classifications = db.relationship(
        "GaraClassification", back_populates="user", lazy=True
    )

    # Player encounter relationships
    player1_encounters = db.relationship(
        "PlayerEncounter",
        foreign_keys="PlayerEncounter.player1_id",
        back_populates="player1",
        lazy=True,
    )

    player2_encounters = db.relationship(
        "PlayerEncounter",
        foreign_keys="PlayerEncounter.player2_id",
        back_populates="player2",
        lazy=True,
    )

    # Director request relationship
    director_request = db.relationship(
        "DirectorRequest",
        foreign_keys="DirectorRequest.user_id",
        uselist=False,
        viewonly=True,
        primaryjoin=(
            "and_(User.id==DirectorRequest.user_id, "
            "DirectorRequest.status=='pending')"
        ),
    )

    # ───────────────────
    # Auth helpers
    # ───────────────────
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def auth_fingerprint(self) -> str:
        """Impronta breve della credenziale attuale, per legarci la sessione.

        Cambia ogni volta che cambia `password_hash`, ed e' questo che rende
        efficace un cambio password: chi ha in mano un cookie emesso prima
        porta un'impronta che non torna piu'.

        E' un HMAC con `SECRET_KEY` e non un pezzo di `password_hash` grezzo:
        il valore finisce dentro un cookie, e da un frammento di hash si puo'
        montare un attacco offline sulla password. Da un HMAC no, senza il
        segreto del server.
        """
        segreto = (current_app.config.get("SECRET_KEY") or "").encode()
        materiale = (self.password_hash or "").encode()
        return hmac.new(segreto, materiale, hashlib.sha256).hexdigest()[:16]

    def get_id(self) -> str:
        """Identificatore di sessione: id **piu'** impronta della credenziale.

        `UserMixin` restituirebbe il solo `id`, e una sessione aperta con la
        vecchia password resterebbe valida per sempre — anche dopo un reset
        fatto proprio perche' qualcun altro era entrato. Vedi
        `load_user()` in `app.py`, che e' la meta' che verifica.
        """
        return f"{self.id}.{self.auth_fingerprint()}"

    @classmethod
    def from_session_id(cls, raw_id: str) -> "User | None":
        """Ricarica l'utente da cio' che sta nel cookie, verificando l'impronta.

        Restituisce `None` — cioe' «non autenticato» — quando l'impronta non
        corrisponde piu' (password cambiata) o quando manca del tutto (cookie
        emesso prima di questa modifica: si rifa' il login, una volta sola).
        """
        id_str, _, impronta = str(raw_id).partition(".")
        if not impronta or not id_str.isdigit():
            return None

        user = db.session.get(cls, int(id_str))
        if user is None or user.is_deleted:
            return None

        # `compare_digest` e non `==`: il confronto non deve dire, col tempo
        # che impiega, quanti caratteri iniziali erano giusti.
        if not hmac.compare_digest(user.auth_fingerprint(), impronta):
            return None

        return user

    @validates("email")
    def _sync_email_hash(self, key: str, value: Any) -> Any:
        """Mantiene email_hash sincronizzato a ogni assegnazione di email.

        Scatta su costruttore, update e anonymize() (email=None → hash=None).
        I validator NON scattano al load dall' DB, quindi le righe esistenti
        conservano l'hash gia' persistito (popolato dalla migration).
        """
        self.email_hash = compute_email_hash(value)
        return value

    # ───────────────────
    # Role shortcuts
    # ───────────────────
    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value

    @property
    def is_director(self) -> bool:
        return self.role == UserRole.DIRECTOR.value

    @property
    def is_venue_manager(self) -> bool:
        """Check if user is assigned as manager for any venue."""
        if self.is_admin:
            return True
        assignment = VenueManagement.query.filter_by(
            user_id=self.id, is_active=True
        ).first()
        return assignment is not None

    @property
    def is_examiner(self) -> bool:
        """True se l'utente può creare esami e certificarli (ADR-041).

        Ruolo **ortogonale**: non guarda ``role`` ma la tabella ``role_grant``,
        esattamente come ``is_venue_manager`` guarda ``venue_management``. Un
        player che diventa esaminatore resta player.
        """
        if self.is_admin:
            return True
        from .role_enum import GrantableRole
        from .role_grant_service import RoleGrantService

        return RoleGrantService.has_role(self.id, GrantableRole.EXAMINER)

    @property
    def is_beta_tester(self) -> bool:
        """True se l'utente prova in produzione le funzioni non ancora aperte.

        A differenza di ``is_examiner`` **non** e' vero d'ufficio per l'admin.
        L'admin vede gia' tutto per bypass, quindi il grant non gli
        aggiungerebbe niente; dirlo lo stesso falserebbe l'unica cosa che
        questa property serve a leggere — l'elenco di chi sta provando.
        """
        from .role_enum import GrantableRole
        from .role_grant_service import RoleGrantService

        return RoleGrantService.has_role(self.id, GrantableRole.BETA_TESTER)

    @property
    def is_player(self) -> bool:
        return self.role == UserRole.PLAYER.value

    @property
    def elo_global_rating(self):
        """ELO globale (tornei + casual, dual ELO) — SOLO display.

        A differenza di `elo_rating` (competitivo, colonna sincronizzata e fonte
        autorevole per categoria/handicap), il pool globale vive solo in
        PlayerRating(ELO_GLOBAL). Query on-demand: ok per il profilo singolo;
        per liste/leaderboard caricare in bulk lato route.
        """
        from models.rating.models import PlayerRating, RatingSystem

        obj = PlayerRating.get_user_rating(self.id, RatingSystem.ELO_GLOBAL)
        if obj is None:
            return None
        # `rating_value` è in virgola mobile per il pool a rack (ADR-052), ma
        # questo pool scrive interi per costruzione: senza l'arrotondamento
        # l'interfaccia mostrerebbe «1184.0».
        return int(round(obj.rating_value))

    # Flask-Login integration: utente attivo solo se non soft-deleted
    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return not self.is_deleted

    # ───────────────────
    # Onboarding (ADR-035)
    # ───────────────────
    @property
    def full_name(self) -> Optional[str]:
        """Nome e cognome, se dati; `None` se non ne è stato scritto nessuno.

        Restituire `None` invece di stringa vuota permette al template di
        scrivere `user.full_name or user.username` senza doppioni.
        """
        parti = [p for p in (self.first_name, self.last_name) if p and p.strip()]
        return " ".join(parti) if parti else None

    @property
    def interests_list(self) -> list[str]:
        """Interessi dichiarati nell'onboarding come lista (CSV → list)."""
        if not self.onboarding_interests:
            return []
        return [t for t in self.onboarding_interests.split(",") if t]

    # Operazioni di anonimizzazione (PII → NULL, username tecnico)
    def anonymize(self) -> None:
        if not self.is_deleted:
            self.deleted_at = utc_now()
        if not self.previous_username:
            self.previous_username = self.username
        # Username tecnico e univoco; UI mostrerà una versione "accattivante"
        stamp = (
            self.deleted_at.strftime("%Y%m%d")
            if self.deleted_at
            else utc_now().strftime("%Y%m%d")
        )
        self.username = f"deleted-{self.id}-{stamp}"
        self.email = None
        self.phone = None
        # L'anagrafica se ne va con la persona: e' il dato piu' identificante
        # che questa applicazione conservi.
        self.first_name = None
        self.last_name = None
        # opzionale: invalidare la password
        self.password_hash = "!deleted!"

        # La traccia degli accessi se ne va con la persona. Il `CASCADE` sulla
        # FK non basta: qui non si cancella nessuna riga `user`, si svuota —
        # e senza questa riga il registro di quando quell'account si collegava
        # sopravviverebbe alla richiesta di cancellazione che doveva
        # soddisfare. E' l'unico punto che lo tocca, perche' e' l'unico modo
        # in cui un utente sparisce davvero da questa applicazione.
        from .session_models import UserSession

        UserSession.query.filter_by(user_id=self.id).delete(synchronize_session=False)

    # ───────────────────
    # Permission helpers
    # ───────────────────
    def can_manage_campionato(self, campionato_id: int) -> bool:
        from .permissions import PermissionChecker

        return PermissionChecker.can_manage_campionato(self, campionato_id)

    def can_manage_competition(self, competition_id: int) -> bool:
        from .permissions import PermissionChecker

        return PermissionChecker.can_manage_competition(self, competition_id)

    def can_view_admin_panel(self) -> bool:
        return self.is_admin

    def can_inscribe_to_competition(self, competition_id: int) -> bool:
        if self.is_admin:
            return False
        from .permissions import PermissionChecker

        return not PermissionChecker.can_manage_competition(self, competition_id)

    def can_manage_venue(self, venue_id: int) -> bool:
        """Check if user can manage a specific venue."""
        if self.is_admin:
            return True
        if not self.is_venue_manager:
            return False

        # Check if user is assigned as manager for this venue
        assignment = VenueManagement.query.filter_by(
            user_id=self.id, venue_id=venue_id, is_active=True
        ).first()
        return assignment is not None

    def get_managed_venues(self) -> List["BilliardHall"]:
        """Get list of venues this user can manage."""
        if self.is_admin:
            # Admin can manage all venues
            from ..location.models import BilliardHall

            return BilliardHall.query.filter_by(is_active=True).all()

        if not self.is_venue_manager:
            return []

        # Get venues assigned to this user
        from ..location.models import BilliardHall

        venue_assignments = VenueManagement.query.filter_by(
            user_id=self.id, is_active=True
        ).all()

        venue_ids = [assignment.venue_id for assignment in venue_assignments]
        if not venue_ids:
            return []

        return BilliardHall.query.filter(
            BilliardHall.id.in_(venue_ids), BilliardHall.is_active.is_(True)
        ).all()

    # ───────────────────
    # Task 1.4 – implementations
    # ───────────────────
    def get_managed_campionatos(self) -> List["Campionato"]:
        """Campionati che l’utente può gestire."""
        if self.is_admin:
            from ..campionato.models import Campionato

            return Campionato.query.all()
        if self.is_director:
            return [
                assoc.campionato
                for assoc in self.director_assignments
                if assoc.entity_type == "campionato" and assoc.campionato
            ]
        return []

    def get_statistics(self) -> Dict[str, Any]:
        """Statistiche complete usate da dashboard & analytics."""
        # import locale, evita circolari
        from ..competition.models import (
            Inscription,
            Gara,
        )
        from ..match.models import Match
        from ..status_enum import GaraStatus, MatchStatus

        total_inscriptions = Inscription.query.filter_by(user_id=self.id).count()

        matches: List["Match"] = Match.query.filter(
            db.or_(Match.player1_id == self.id, Match.player2_id == self.id),
            Match.status == MatchStatus.CLOSED_UNILATERALLY.value,
        ).all()

        total_matches = len(matches)
        won_matches = sum(m.winner_id == self.id for m in matches)
        lost_matches = total_matches - won_matches
        win_percentage = (won_matches / total_matches * 100) if total_matches else 0

        # Conta solo i campionati con almeno una gara completata dove
        # l'utente ha partecipato
        tournaments_played = (
            Inscription.query.filter_by(user_id=self.id)
            .join(Gara)
            # Solo gare completate
            .filter(Gara.status == GaraStatus.COMPLETED.value)
            .with_entities(Gara.campionato_id)
            .distinct()
            .count()
        )

        # Conta le gare completate dove l'utente ha partecipato
        gare_played = (
            Inscription.query.filter_by(user_id=self.id)
            .join(Gara)
            # Solo gare completate
            .filter(Gara.status == GaraStatus.COMPLETED.value)
            .count()
        )

        total_racks_won = sum(self._racks_won(m) for m in matches)
        total_racks_played = sum(m.player1_score + m.player2_score for m in matches)
        rack_win_percentage = (
            (total_racks_won / total_racks_played * 100) if total_racks_played else 0
        )

        return {
            "total_inscriptions": total_inscriptions,
            "total_matches": total_matches,
            "won_matches": won_matches,
            "lost_matches": lost_matches,
            "win_percentage": round(win_percentage, 1),
            "tournaments_played": tournaments_played,
            "gare_played": gare_played,
            "total_racks_won": total_racks_won,
            "total_racks_played": total_racks_played,
            "rack_win_percentage": round(rack_win_percentage, 1),
        }

    # helper ────────────────────────────────────────────────────────────────────
    def _racks_won(self, match: "Match") -> int:
        if match.player1_id == self.id:
            return match.player1_score
        if match.player2_id == self.id:
            return match.player2_score
        return 0

    # ───────────────────
    # Gamification helpers
    # ───────────────────
    def has_unlocked_achievement(self, achievement_slug: str) -> bool:
        """Check if user has unlocked a specific achievement.

        Args:
            achievement_slug: Slug of the achievement to check

        Returns:
            True if achievement is unlocked, False otherwise

        Usage:
            {% if current_user.has_unlocked_achievement('aspiring_director') %}
                <!-- Show director request button -->
            {% endif %}
        """
        from models.gamification.achievement_service import AchievementService

        return AchievementService.has_achievement(self.id, achievement_slug)

    def can_access(
        self,
        feature_code: str,
        context: Dict[str, Any] | None = None,
        cache: Dict[Any, Any] | None = None,
    ) -> bool:
        """
        Check if user can access a specific feature based on gamification rules.

        Args:
            feature_code: Code of the feature to check (e.g., 'create_match')
            context: Optional context for rule evaluation (e.g., location_id)
            cache: Optional memoization dict per le metriche, da passare SOLO
                dai path di sola lettura (vedi UnlockProgressService, issue #9).

        Returns:
            True if feature is unlocked or overridden, False otherwise.
        """
        if self.gamification_override:
            return True

        if self.is_admin:
            return True

        from models.gamification.unlock_engine import UnlockEngine

        return UnlockEngine.check_eligibility(
            self.id, feature_code, context, cache=cache
        )

    # debug ─────────────────────────────────────────────────────────────────────
    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username} ({self.role})>"


# ────────────────────────────────────────────────────────────────────────────────
# DIRECTOR ASSIGNMENT (GENERIC)
# ────────────────────────────────────────────────────────────────────────────────
class DirectorAssignment(BaseModel):
    __tablename__ = "director_assignment"

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), primary_key=True)
    entity_type = db.Column(db.String(20), primary_key=True)  # 'campionato' o 'gara'
    entity_id = db.Column(db.Integer, primary_key=True)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, default=utc_now)

    # Relationships
    director = db.relationship(
        "User", foreign_keys=[user_id], backref="director_assignments"
    )
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])

    @property
    def campionato(self):
        """Get campionato if this is a campionato assignment."""
        if self.entity_type == "campionato":
            from models.campionato.models import Campionato

            return db.session.get(Campionato, self.entity_id)
        return None

    @property
    def gara(self):
        """Get gara if this is a gara assignment."""
        if self.entity_type == "gara":
            from models.competition.models import Gara

            return db.session.get(Gara, self.entity_id)
        return None

    def __repr__(self):
        return (
            f"<DirectorAssignment {self.user_id} -> "
            f"{self.entity_type}:{self.entity_id}>"
        )


# Legacy aliases for backward compatibility
TournamentDirector = DirectorAssignment  # Backward compatibility
GaraDirector = DirectorAssignment  # Backward compatibility


# ────────────────────────────────────────────────────────────────────────────────
# DIRECTOR REQUEST
# ────────────────────────────────────────────────────────────────────────────────
class DirectorRequest(BaseModel):
    __tablename__ = "director_request"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    requested_at = db.Column(db.DateTime, default=utc_now)
    status = db.Column(
        db.String(20), nullable=False, default="pending"
    )  # pending|approved|rejected
    processed_at = db.Column(db.DateTime)
    processed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    notes = db.Column(db.Text)

    user = db.relationship("User", foreign_keys=[user_id])
    processed_by = db.relationship("User", foreign_keys=[processed_by_id])

    # state helpers ---
    def approve(self, admin: "User") -> None:
        from ..status_enum import DirectorRequestStatus

        self.status = DirectorRequestStatus.APPROVED
        self.processed_at = utc_now()
        self.processed_by = admin
        # Get the user object and update role

        session = db.session
        user = session.get(User, self.user_id)
        if user:
            user.role = "director"

    def reject(self, admin: "User", notes: str | None = None) -> None:
        from ..status_enum import DirectorRequestStatus

        self.status = DirectorRequestStatus.REJECTED
        self.processed_at = utc_now()
        self.processed_by = admin
        if notes:
            self.notes = notes

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DirectorRequest {self.id} {self.status}>"


# ────────────────────────────────────────────────────────────────────────────────
# VENUE MANAGER REQUEST
# ────────────────────────────────────────────────────────────────────────────────
class VenueManagerRequest(BaseModel):
    """Request to manage a specific venue."""

    __tablename__ = "venue_manager_request"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("billiard_hall.id"), nullable=False)
    requested_at = db.Column(db.DateTime, default=utc_now)
    status = db.Column(
        db.String(20), nullable=False, default="pending"
    )  # pending|approved|rejected|cancelled|contested
    processed_at = db.Column(db.DateTime)
    processed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    notes = db.Column(db.Text)  # User notes when requesting
    admin_notes = db.Column(db.Text)  # Admin notes when processing
    is_contested = db.Column(
        db.Boolean, default=False
    )  # True if requesting already managed venue

    user = db.relationship("User", foreign_keys=[user_id])
    processed_by = db.relationship("User", foreign_keys=[processed_by_id])
    venue = db.relationship("BilliardHall", foreign_keys=[venue_id])

    __table_args__ = (
        db.UniqueConstraint("user_id", "venue_id", name="_user_venue_request_uc"),
    )

    # state helpers ---
    def approve(self, admin: "User", admin_notes: str | None = None) -> None:
        """Approve venue manager request and automatically assign venue."""
        from ..status_enum import VenueManagerRequestStatus

        self.status = VenueManagerRequestStatus.APPROVED
        self.processed_at = utc_now()
        self.processed_by = admin
        if admin_notes:
            self.admin_notes = admin_notes

        # Automatically create venue management assignment
        from .services import VenueManagementService

        VenueManagementService.assign_venue_manager(self.user_id, self.venue_id, admin)

    def reject(self, admin: "User", admin_notes: str | None = None) -> None:
        """Reject venue manager request."""
        from ..status_enum import VenueManagerRequestStatus

        self.status = VenueManagerRequestStatus.REJECTED
        self.processed_at = utc_now()
        self.processed_by = admin
        if admin_notes:
            self.admin_notes = admin_notes

    def cancel(self) -> None:
        """Cancel venue manager request."""
        from ..status_enum import VenueManagerRequestStatus

        self.status = VenueManagerRequestStatus.CANCELLED
        self.processed_at = utc_now()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VenueManagerRequest {self.id} {self.status}>"


# ────────────────────────────────────────────────────────────────────────────────
# VENUE MANAGEMENT ASSIGNMENT
# ────────────────────────────────────────────────────────────────────────────────
class VenueManagement(BaseModel):
    """Assignment of venue managers to specific venues."""

    __tablename__ = "venue_management"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    venue_id = db.Column(db.Integer, db.ForeignKey("billiard_hall.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, default=utc_now)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoked_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # Relationships
    user = db.relationship("User", foreign_keys=[user_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])
    revoked_by = db.relationship("User", foreign_keys=[revoked_by_id])
    venue = db.relationship("BilliardHall", foreign_keys=[venue_id])

    # Unique constraint: one manager per venue
    __table_args__ = (
        db.UniqueConstraint("venue_id", "is_active", name="uq_venue_active_manager"),
    )

    def revoke(self, admin: "User") -> None:
        """Revoke venue management assignment."""
        self.is_active = False
        self.revoked_at = utc_now()
        self.revoked_by = admin

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VenueManagement {self.user_id} -> {self.venue_id}>"
