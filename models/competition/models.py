"""
Module: models/competition/models.py
Purpose: Competition domain models (Gara, Inscription)
Data Structures: Gara, Inscription
Dependencies: models.base.db, datetime
"""

from models.base import db, SoftDeleteMixin, utc_now
from enum import Enum
from models.status_enum import GaraStatus, MatchStatus, WithdrawPolicy  # noqa: F401
from models.match.break_rules import (
    DEFAULT_BREAK_RULE,
    DEFAULT_START_RULE,
    BreakRule,
    StartRule,
)
from models.matchmaking.configuration import (
    MatchmakingStrategy,
    FirstRoundPolicy,
    OddNumberPolicy,
)
from models.competition.constants import (
    DEFAULT_MIN_PARTICIPANTS,
    DEFAULT_ROUNDS_COUNT,
    DEFAULT_ENTRY_FEE,
    DEFAULT_WITHDRAW_POLICY,
)
from typing import TYPE_CHECKING, Optional, List, Tuple
import json
import secrets

if TYPE_CHECKING:
    pass

# Byte di entropia del token del link pubblico di iscrizione (issue #61).
# 6 byte → 8 caratteri url-safe, ~4.7e13 combinazioni: abbastanza corto da
# stare su una locandina, abbastanza largo da non essere enumerabile.
PUBLIC_TOKEN_BYTES = 6


def generate_public_token() -> str:
    """Token casuale per il link pubblico di una gara.

    Non derivato dall'id: l'id è sequenziale, quindi un link costruito su di
    esso è indovinabile (e la gara accanto è a un carattere di distanza).
    """
    return secrets.token_urlsafe(PUBLIC_TOKEN_BYTES)


class WaitlistReason(str, Enum):
    """Reason why an inscription is on the waiting list.

    CAPACITY: max_participants exceeded (standard waitlist)
    PARITY: odd_number_policy=NO and player count became odd
    """

    CAPACITY = "capacity"
    PARITY = "parity"


class Gara(SoftDeleteMixin, db.Model):
    """Competition round within a campionato or standalone.

    Supports soft delete via SoftDeleteMixin:
    - deleted_at: datetime when soft deleted
    - is_deleted: property to check if deleted
    - Automatic query filtering via soft_delete_filter
    """

    __tablename__ = "gara"

    id = db.Column(db.Integer, primary_key=True)

    # Soft delete reason (optional)
    deleted_reason = db.Column(db.String(255), nullable=True)

    # Competizione di prova (ADR-058): la stessa gara con un flag, visibile
    # solo a chi la dirige (filtro di sessione in `models/prova/visibility.py`),
    # popolata da giocatori fittizi, fuori da ELO e gamification. Le gare di
    # un campionato di prova lo ereditano alla creazione, come la regola di
    # apertura. `prova_expires_at` vive solo sulla radice — la gara singola —
    # e per le gare di campionato resta NULL: la scadenza e' del campionato.
    is_prova = db.Column(db.Boolean, nullable=False, default=False, index=True)
    prova_expires_at = db.Column(db.DateTime, nullable=True)
    prova_avviso_inviato_at = db.Column(db.DateTime, nullable=True)

    # FK nullable per supportare standalone competitions
    # RESOLVED: See docs/_archive/2025-12-architectural-decisions-pre-adr.md ADR-002.
    # Decision: Keep FK in Gara (natural direction, efficient queries).
    campionato_id = db.Column(
        db.Integer, db.ForeignKey("campionato.id", ondelete="CASCADE"), nullable=True
    )

    # Director FK per standalone competitions
    director_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # RESOLVED: See docs/_archive/2025-12-architectural-decisions-pre-adr.md ADR-005.
    # Decision: Keep on Gara, add validation for standalone gare.
    number = db.Column(db.Integer, nullable=False)  # 1-10
    name = db.Column(db.String(100))

    # Token del link pubblico di iscrizione (issue #61): /g/<public_token>.
    # Nullable perché le gare create prima della migration lo ricevono dal
    # backfill (o pigramente, vedi GaraService.ensure_public_token).
    public_token = db.Column(
        db.String(32), unique=True, nullable=True, default=generate_public_token
    )
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=True)  # Ora della gara

    #: Quando la gara è stata **creata**, che non è `date` — quello è il giorno
    #: in cui si gioca, e può stare mesi nel futuro. `Gara` estende `db.Model`
    #: e non `BaseModel`, quindi questa colonna non arrivava dal mixin come per
    #: quasi tutte le altre entità: mancava e basta.
    #:
    #: Serve a distinguere «l'ultima cosa che questo direttore ha fatto»
    #: (dashboard adattiva, `models/dashboard/activity_feedback.py`). Nullable
    #: perché sulle gare già esistenti la data vera non c'è più: la migration
    #: `20260825_gara_created_at` la ricostruisce dalla prima iscrizione dove
    #: c'è, e dove non c'è resta il ripiego documentato lì.
    created_at = db.Column(db.DateTime, nullable=True, default=utc_now)

    # Location - FK to BilliardHall (nullable for backward compatibility)
    billiard_hall_id = db.Column(
        db.Integer,
        db.ForeignKey("billiard_hall.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Legacy: string-based location (kept for backward compatibility and display cache)
    location = db.Column(db.String(200))
    # Available tables for this gara - JSON list: '["2", "3", "5"]'
    # If set, overrides venue's tables. If None, uses venue's tables.
    available_tables = db.Column(db.Text, nullable=True)
    # Se True (effettivo solo con strategia random): dal secondo turno i tavoli
    # vengono assegnati "a ondate" — si attende la fine di tutte le partite del
    # turno precedente, poi il primo tavolo della lista (ordine di pregio) va
    # al match con il giocatore meglio piazzato in classifica provvisoria.
    assign_tables_by_ranking = db.Column(db.Boolean, nullable=False, default=False)
    description = db.Column(db.Text)  # Descrizione opzionale
    rounds_count = db.Column(
        db.Integer, nullable=False, default=DEFAULT_ROUNDS_COUNT
    )  # Numero di turni per questa gara
    min_participants = db.Column(
        db.Integer, default=DEFAULT_MIN_PARTICIPANTS
    )  # Minimo iscritti
    max_participants = db.Column(db.Integer)  # Massimo iscritti (opzionale)
    entry_fee = db.Column(
        db.Float, default=DEFAULT_ENTRY_FEE
    )  # Quota di partecipazione

    # ── Vetrina da condividere sui social (issue #235) ───────────────────
    # Il banner e il link esterno si ereditano dal campionato quando la gara
    # non ne ha di propri: si legge `effective_banner_path` /
    # `effective_external_link`, mai queste colonne direttamente, altrimenti
    # una gara che eredita risulta senza immagine.
    banner_path = db.Column(db.String(255), nullable=True)
    external_url = db.Column(db.String(500), nullable=True)
    external_label = db.Column(db.String(60), nullable=True)
    #: Indirizzo leggibile facoltativo, accanto a `public_token`: `/g/<slug>`
    #: e `/g/<token>` aprono la stessa pagina. Il token non si tocca mai — le
    #: locandine già stampate devono continuare a funzionare.
    slug = db.Column(db.String(60), unique=True, nullable=True, index=True)

    # Game settings
    discipline = db.Column(db.String(50), nullable=False)  # palla 8, 9, 10
    # Distance configuration (use distance_config property for abstraction)
    distance = db.Column(db.Integer, nullable=False)
    is_race_to = db.Column(
        db.Boolean, default=False
    )  # Se True: "al N rack", se False: "esatto numero"

    # Multi-set configuration (Phase 6: Frontend Integration)
    is_multi_set = db.Column(db.Boolean, default=False, nullable=False)
    match_distance = db.Column(db.Integer, nullable=True)  # Number of sets
    is_race_to_sets = db.Column(
        db.Boolean, default=True, nullable=True
    )  # Race-to vs exact sets

    # Handicap mode: NULL = eredita dal campionato (vedi effective_has_handicap).
    # I match di una gara con handicap non aggiornano il rating Elo.
    has_handicap = db.Column(db.Boolean, nullable=True)

    # Regola di inizio e regola di apertura (ADR-056).
    # NULL = eredita dal campionato; su una gara standalone il ripiego è il
    # default del progetto. I match della gara le ereditano **sempre**: sul
    # singolo match non c'è niente da scegliere.
    start_rule = db.Column(db.String(20), nullable=True)  # first_player, lag
    break_rule = db.Column(
        db.String(20), nullable=True
    )  # winner_breaks, alternate, alternate_two, loser_breaks

    # Date iscrizioni
    inscription_start = db.Column(db.DateTime)
    inscription_end = db.Column(db.DateTime)

    # Stato della gara
    status = db.Column(
        db.String(20), default=GaraStatus.SETUP.value
    )  # setup, inscription, playing, completed
    current_round = db.Column(db.Integer, default=0)  # 0=non iniziata, 1,2,3=turni

    withdraw_policy = db.Column(
        db.String(10), nullable=False, default=DEFAULT_WITHDRAW_POLICY
    )

    # Classification: RACK (rack totali), WINS (vittorie+diff), POSITION (bracket)
    # See docs/CLASSIFICATION_SYSTEM.md for constraints per system
    classification_system = db.Column(
        db.String(10), nullable=False, default="WINS"
    )  # RACK, WINS, POSITION

    # Matchmaking strategy configuration
    matchmaking_strategy = db.Column(
        db.String(50), nullable=False, default=MatchmakingStrategy.AMALFI.value
    )  # amalfi, round_robin, direct_elimination, double_knockout, random
    first_round_policy = db.Column(
        db.String(50), default=FirstRoundPolicy.RANDOM.value
    )  # random, rating, classification
    odd_number_policy = db.Column(
        db.String(50), default=OddNumberPolicy.BYE.value
    )  # bye, trio (trio solo per alcune strategie e distanze)
    anti_rematch_enabled = db.Column(
        db.Boolean, default=True
    )  # Evita reincontri tra giocatori
    # A chi tocca la X nel primo turno quando i giocatori sono dispari e la
    # policy è "bye" (o "bye con esercizio"): False = la sorteggia
    # l'algoritmo, True = va all'ultimo iscritto. Il resto degli abbinamenti
    # resta casuale in entrambi i casi. Scelto dal direttore all'avvio, e
    # persistito come `draw_seed`: dice come è stato fatto quel sorteggio.
    # Vedi models/matchmaking/bye_preference.py.
    bye_to_last_inscribed = db.Column(db.Boolean, nullable=False, default=False)

    # ── Configurazione a tabellone (eliminazione diretta / doppio KO) ──────
    # Separazione dei compagni di squadra nel sorteggio del primo turno.
    # Spenta di default: chi non usa le squadre non vede alcun cambiamento.
    # Decidibile solo in stato setup, così ogni iscrizione nasce con la sua
    # squadra e non esiste il caso "metà iscritti senza squadra".
    separate_teammates = db.Column(db.Boolean, nullable=False, default=False)
    # Finale per il 3°/4° posto. Solo eliminazione diretta: nel doppio KO il
    # terzo posto lo determina già il tabellone. Non aggiunge turni — il match
    # occupa lo stesso turno della finale.
    third_place_match = db.Column(db.Boolean, nullable=False, default=False)
    # Seme del sorteggio, generato una volta all'avvio del primo turno e
    # persistito perché preview e create_round diano lo stesso tabellone.
    # Azzerato da cancel_first_round_startup: riavviare = risorteggiare.
    draw_seed = db.Column(db.Integer, nullable=True)
    # Quale rating usare quando first_round_policy == "rating". Oggi ha un
    # valore solo, "elo": la colonna resta come appiglio se un giorno ne
    # arrivera' un secondo, ma non e' selezionabile.
    seeding_rating = db.Column(db.String(16), nullable=False, default="elo")
    # Formula FISBB: quanti turni di doppio KO si giocano dentro il girone
    # prima del troncamento. NULL = nessuna fase a gironi, cioè il doppio KO
    # classico su un tabellone solo. Valorizzato, la taglia del girone ne
    # discende (G = 2^(w+1)) e la gara diventa a due fasi: gironi in
    # parallelo, poi tabellone finale a eliminazione diretta fra i qualificati.
    # Vale solo per la strategia double_knockout.
    double_ko_rounds = db.Column(db.Integer, nullable=True)

    # Tiebreaker configuration (spareggio fine gara)
    tiebreaker_enabled = db.Column(
        db.Boolean, default=True
    )  # Se True, spareggio per pari merito nel podio
    tiebreaker_until_position = db.Column(
        db.Integer, default=3
    )  # Spareggio fino a questa posizione (es. 3 = podio)
    tiebreaker_mode = db.Column(
        db.String(20), default="playoff_match"
    )  # "playoff_match" (partita secca) | "challenge" (drill dalla banca dati)
    tiebreaker_challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="SET NULL"), nullable=True
    )  # FK a Challenge se mode = "challenge"

    # L'esercizio che si gioca al posto della X, scelto dal direttore (issue
    # #267). Sta sulla **gara** e non sul turno di proposito: a numero dispari
    # riposa una persona diversa a ogni turno, e un esercizio che cambia
    # renderebbe le prove di due giocatori non confrontabili pur finendo nella
    # stessa classifica. NULL significa «sceglie l'applicazione» — il
    # comportamento storico, e quello di ogni gara creata prima.
    x_challenge_id = db.Column(
        db.Integer,
        db.ForeignKey("challenge.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Moltiplicatore del punteggio di questa gara nella classifica generale
    # del campionato (issue #64). 1 = comportamento storico. È l'UNICA fonte
    # letta da `ScoreAggregator`: la configurazione playoff lo imposta qui
    # quando crea la propria gara, come già fa con distanza e turni.
    # Le statistiche (Elo, percentuale vittorie) non lo guardano mai.
    weight = db.Column(db.Integer, nullable=False, default=1, server_default="1")

    # Playoff configuration (if this gara is a playoff)
    playoff_config_id = db.Column(
        db.Integer,
        db.ForeignKey("playoff_configuration.id", ondelete="SET NULL"),
        nullable=True,
    )  # If set, this gara is a playoff tournament

    # Relazioni
    inscriptions = db.relationship(
        "Inscription",
        backref="gara",
        lazy=True,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    matches = db.relationship(
        "Match",
        backref="gara",
        lazy=True,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    director = db.relationship(
        "User", foreign_keys=[director_id], backref="standalone_garas"
    )
    tiebreaker_challenge = db.relationship(
        "Challenge", foreign_keys=[tiebreaker_challenge_id]
    )
    billiard_hall = db.relationship("BilliardHall", foreign_keys=[billiard_hall_id])
    playoff_config = db.relationship(
        "PlayoffConfiguration", foreign_keys=[playoff_config_id], back_populates="gara"
    )

    x_challenge = db.relationship("Challenge", foreign_keys=[x_challenge_id])

    @property
    def is_playoff(self) -> bool:
        """Check if this gara is a playoff tournament."""
        return self.playoff_config_id is not None

    @property
    def classification_weight(self) -> int:
        """Quanto pesa questa gara nella classifica generale del campionato.

        Vale 0 per la gara di un playoff che **decide** la classifica finale:
        lì l'ordine dei partecipanti lo detta il playoff stesso, e sommarne
        anche il punteggio sposterebbe la posizione di chi al playoff non è
        andato — che è esattamente ciò che quella modalità non vuole.
        """
        config = self.playoff_config
        if config is not None and config.decides_final_ranking:
            return 0
        return 1 if self.weight is None else int(self.weight)

    # Co-directors relationship (similar to campionati)
    @property
    def directors(self):
        """Get co-directors for this gara."""
        from models.user.models import DirectorAssignment, User

        return (
            db.session.query(User)
            .join(DirectorAssignment, User.id == DirectorAssignment.user_id)
            .filter(
                DirectorAssignment.entity_type == "gara",
                DirectorAssignment.entity_id == self.id,
            )
            .all()
        )

    @property
    def venue(self):
        """Get the associated BilliardHall.

        Prefers FK relationship, falls back to name lookup for legacy data.
        """
        # Prefer FK if set
        if self.billiard_hall:
            return self.billiard_hall
        # Fallback: lookup by name for legacy data
        if not self.location:
            return None
        from models.location.models import BilliardHall

        return BilliardHall.query.filter_by(name=self.location).first()

    @property
    def location_display(self) -> str:
        """Get display name for location.

        Returns billiard_hall.name if FK set, otherwise falls back
        to legacy location string.

        Returns:
            str: Location name for display
        """
        if self.billiard_hall:
            return self.billiard_hall.name
        return self.location or ""

    @staticmethod
    def parse_tables_input(input_str: str) -> List[str]:
        """Parse user input to list of table names.

        Delegates to models.shared.utils.parse_tables_input.
        Kept as static method on Gara for backward compatibility.
        """
        from models.shared.utils import parse_tables_input as _parse_tables

        return _parse_tables(input_str)

    def get_available_tables(self) -> List[str]:
        """Return available table names for this gara.

        Priority:
        1. gara.available_tables if set (parsed from JSON)
        2. venue.get_table_names() if venue exists
        3. Empty list
        """
        # Priority 1: gara-specific tables
        if self.available_tables:
            try:
                return json.loads(self.available_tables)
            except (json.JSONDecodeError, TypeError):
                return []

        # Priority 2: venue tables
        venue = self.venue
        if venue:
            return venue.get_table_names()

        # Priority 3: no tables
        return []

    def set_available_tables(self, tables: List[str]) -> None:
        """Set available tables from a list.

        Args:
            tables: List of table names, or empty list for None
        """
        if tables:
            self.available_tables = json.dumps(tables)
        else:
            self.available_tables = None

    # Property per identificare se è standalone
    # RESOLVED: ADR-002 (docs/_archive/2025-12-architectural-decisions-pre-adr.md)
    # — keep bidirectional
    @property
    def is_standalone(self):
        """Check if this is a standalone competition."""
        return self.campionato_id is None

    @property
    def effective_has_handicap(self) -> bool:
        """Handicap mode effettivo: override gara → campionato → False.

        NULL su `has_handicap` significa "eredita dal campionato". Per gare
        standalone (campionato_id NULL) il fallback è False.
        """
        if self.has_handicap is not None:
            return self.has_handicap
        if self.campionato is not None:
            return bool(self.campionato.has_handicap)
        return False

    @property
    def effective_start_rule(self) -> "StartRule":
        """Regola di inizio effettiva: gara → campionato → primo giocatore.

        NULL su `start_rule` significa "eredita dal campionato" (ADR-056). Su
        una gara standalone non c'è niente da cui ereditare e vale il default
        del progetto, che è il comportamento storico: apre il primo giocatore.
        """
        scelta = StartRule.normalize(self.start_rule)
        if scelta is not None:
            return scelta
        if self.campionato is not None:
            ereditata = StartRule.normalize(self.campionato.default_start_rule)
            if ereditata is not None:
                return ereditata
        return DEFAULT_START_RULE

    @property
    def effective_break_rule(self) -> "BreakRule":
        """Regola di apertura effettiva: gara → campionato → a turno.

        Stessa catena di `effective_start_rule`. Il ripiego è `alternate`, i
        tiri di apertura alternati della regola standard FIBiS.
        """
        scelta = BreakRule.normalize(self.break_rule)
        if scelta is not None:
            return scelta
        if self.campionato is not None:
            ereditata = BreakRule.normalize(self.campionato.default_break_rule)
            if ereditata is not None:
                return ereditata
        return DEFAULT_BREAK_RULE

    @property
    def effective_banner_path(self) -> Optional[str]:
        """La locandina di questa gara: propria → campionato → nessuna.

        Il direttore che carica un'immagine sul campionato la sta scegliendo
        per tutte le sue gare: è il caso normale, e gli evita di ricaricarla
        dieci volte. La singola gara la scavalca quando serve — la tappa
        speciale, la finale con la sua grafica.

        `None` non è un difetto da correggere a valle: significa "nessuna
        locandina", e la vetrina mostra l'immagine di ripiego del sito.
        """
        if self.banner_path:
            return self.banner_path
        if self.campionato is not None:
            return self.campionato.banner_path or None
        return None

    @property
    def effective_external_link(self) -> Optional[Tuple[str, Optional[str]]]:
        """Link fuori dall'applicazione: (indirizzo, etichetta), o `None`.

        Stessa catena della locandina, e per la stessa ragione: il regolamento
        di un campionato vale per tutte le sue gare, finché una non ne
        pubblica uno proprio.

        L'indirizzo e l'etichetta viaggiano **insieme**: ereditarli
        separatamente produrrebbe il regolamento del campionato sotto
        l'etichetta scelta per un'altra pagina.
        """
        if self.external_url:
            return (self.external_url, self.external_label or None)
        if self.campionato is not None and self.campionato.external_url:
            return (
                self.campionato.external_url,
                self.campionato.external_label or None,
            )
        return None

    @property
    def public_slug_or_token(self) -> Optional[str]:
        """Cosa mettere nell'indirizzo pubblico: lo slug se c'è, il token se no.

        Sono due nomi per la stessa pagina e restano validi entrambi. Questo
        dice solo quale **pubblicare**: chi ha scelto un nome leggibile vuole
        che sia quello a comparire sulla locandina e nel post.
        """
        return self.slug or self.public_token

    @property
    def display_name(self) -> str:
        """Come si chiama questa gara per chi la legge.

        Il nome scelto dal direttore se c'è, altrimenti "Gara <numero>". È il
        campo che porta l'identità pubblica della prova (locandine, post), e
        quando il direttore lo compila è lui a decidere come va letta: per
        questo il numero non viene anteposto, sarebbe l'applicazione che si
        sovrappone alla sua scelta — e su un nome come "2ª prova" produrrebbe
        anche una ripetizione.

        Unica fonte per il titolo di una gara: prima la formattazione era
        ripetuta nei template con tre regole diverse (nome con fallback / solo
        numero / nome senza fallback), e le gare di campionato finivano per
        mostrare "Gara 2" ignorando il nome impostato (issue #56), mentre
        altrove il nome mancante lasciava il vuoto invece di "Gara N"
        (issue #57).
        """
        name = (self.name or "").strip()
        if name:
            return name

        # Il fallback è testo dell'interfaccia e va tradotto: i template che
        # lo producevano a mano usavano `_('Gara %(id)s')`, e restituire qui
        # una stringa italiana fissa sarebbe una regressione per la locale EN.
        # Import locale come in `models/notification/models.py`: fuori da un
        # contesto applicativo (script, migration) gettext solleva, e lì il
        # testo grezzo va benissimo.
        try:
            from flask_babel import gettext

            return gettext("Gara %(number)s", number=self.number)
        except (RuntimeError, ImportError):
            return f"Gara {self.number}"

    # RESOLVED: See docs/_archive/2025-12-architectural-decisions-pre-adr.md ADR-002.
    # Decision: Keep bidirectional - Gara has FK, Campionato has property.
    def get_display_name(self):
        """Nome della gara qualificato dal contesto (campionato o standalone).

        Diverso da `display_name`, che è il titolo nudo: questo lo colloca.
        Usa `display_name` come base, così una gara senza nome non produce
        più "None - Campionato X".
        """
        if self.is_standalone:
            return f"{self.display_name} (Standalone)"
        return f"{self.display_name} - {self.campionato.name}"

    def get_real_status(self):
        """Restituisce lo status reale, considerando anche round e iscrizioni.

        Delegates to GaraStatusResolver for the actual logic.
        """
        from models.competition.status_resolver import GaraStatusResolver

        return GaraStatusResolver.resolve(self)

    def get_status_badge_info(self):
        """Restituisce info per badge status nel template.

        Delegates to status_resolver.get_status_badge for the badge mapping.
        """
        from models.competition.status_resolver import get_status_badge

        return get_status_badge(self)

    @property
    def display_round(self) -> int:
        """Turno da mostrare all'utente ("Turno corrente: N / M").

        `current_round` è la progressione *stretta*: avanza solo quando tutti
        i match del turno N sono conclusi. Le strategie che pre-generano i
        turni (random, round robin) creano i match di tutti i turni all'avvio
        e lasciano `current_round` indietro finché il turno precedente non è
        chiuso del tutto — la gara intanto sta già giocando i turni
        successivi, e il riquadro pubblico mostrava "Turno corrente: 1 / 3" a
        gara al terzo turno (issue #62).

        Il turno da mostrare è il più basso con match ancora aperti; se sono
        tutti conclusi è il più alto con match (gara finita). Senza match si
        ricade su `current_round`, e su 1 per una gara PLAYING che non ha
        ancora match (edge case di avvio).
        """
        rounds = [
            m.round_number
            for m in (getattr(self, "matches", []) or [])
            if getattr(m, "round_number", None)
        ]
        if rounds:
            open_rounds = [
                m.round_number
                for m in self.matches
                if m.round_number and not MatchStatus.is_finished(m.status)
            ]
            return min(open_rounds) if open_rounds else max(rounds)
        if self.current_round and self.current_round > 0:
            return self.current_round
        return 1 if self.status == GaraStatus.PLAYING.value else 0

    def can_inscribe(self):
        """Verifica se si possono fare iscrizioni"""
        if self.status != GaraStatus.INSCRIPTION.value:
            return False
        now = utc_now()
        if self.inscription_start and now < self.inscription_start:
            return False
        if self.inscription_end and now > self.inscription_end:
            return False
        return True

    def is_user_inscribed(self, user_id) -> bool:
        """Verifica se un utente è iscritto"""
        inscriptions_list = getattr(self, "inscriptions", []) or []
        return any(insc.user_id == user_id for insc in inscriptions_list)

    def validate_strategy_configuration(self):
        """Valida coerenza strategia (delegato a StrategyConfiguration).

        Usa models.matchmaking.configuration.StrategyConfiguration
        per validazione centralizzata.
        """
        from models.matchmaking.configuration import (
            BRACKET_STRATEGIES,
            StrategyConfiguration,
        )

        # Crea config da gara e valida
        config = StrategyConfiguration.from_gara(self)
        num_participants = len(getattr(self, "inscriptions", []) or [])

        # Delega validazione a StrategyConfiguration
        errors = config.validate(
            num_players=num_participants if num_participants > 0 else None,
            distance=self.distance,
            is_race_to=self.is_race_to,
        )

        # Le strategie a tabellone hanno bisogno della capienza dichiarata: è
        # da lì che si stima il numero di turni in fase di creazione, quando
        # gli iscritti non ci sono ancora. (La dimensione *effettiva* del
        # tabellone la fissa poi il sorteggio sugli iscritti reali.)
        if (
            self.matchmaking_strategy in BRACKET_STRATEGIES
            and not self.max_participants
        ):
            errors.append(
                "Le gare a tabellone richiedono un numero massimo di partecipanti"
            )

        return errors

    def calculate_rounds_for_strategy(self, num_players):
        """Calcola turni ottimali (delegato a configuration module).

        Usa models.matchmaking.configuration.calculate_rounds_for_strategy
        """
        from models.matchmaking.configuration import (
            calculate_rounds_for_strategy,
            MatchmakingStrategy,
        )

        strategy = MatchmakingStrategy(self.matchmaking_strategy)
        return calculate_rounds_for_strategy(strategy, num_players)

    def get_strategy_constraints(self):
        """Vincoli strategia (delegato a STRATEGY_CONSTRAINTS).

        Usa models.matchmaking.configuration.STRATEGY_CONSTRAINTS
        """
        from models.matchmaking.configuration import (
            STRATEGY_CONSTRAINTS,
            MatchmakingStrategy,
        )

        try:
            strategy = MatchmakingStrategy(self.matchmaking_strategy)
            return STRATEGY_CONSTRAINTS.get(
                strategy, STRATEGY_CONSTRAINTS[MatchmakingStrategy.AMALFI]
            )
        except (ValueError, KeyError):
            # Fallback to Amalfi if strategy not found
            return STRATEGY_CONSTRAINTS[MatchmakingStrategy.AMALFI]

    # =========================================================================
    # Strategy Behavior Methods
    # =========================================================================
    # These methods provide access to strategy-specific behaviors defined in
    # models/matchmaking/configuration.py (StrategyBehaviorConfig)

    def get_strategy_behavior(self):
        """Get the StrategyBehaviorConfig for this gara's strategy.

        Returns:
            StrategyBehaviorConfig with all behavioral settings

        Example:
            behavior = gara.get_strategy_behavior()
            if behavior.supports_round_locking:
                # Apply round locking logic
        """
        from models.matchmaking.configuration import (
            get_strategy_behavior,
            MatchmakingStrategy,
            STRATEGY_BEHAVIORS,
        )

        try:
            strategy = MatchmakingStrategy(self.matchmaking_strategy)
            return get_strategy_behavior(strategy)
        except (ValueError, KeyError):
            # Fallback to Amalfi behavior
            return STRATEGY_BEHAVIORS[MatchmakingStrategy.AMALFI]

    def supports_round_locking(self) -> bool:
        """Check if this gara's strategy supports round locking.

        Random strategy: False (all rounds modifiable)
        Other strategies: True (past rounds locked)
        """
        return self.get_strategy_behavior().supports_round_locking

    def get_classification_type(self):
        """Get classification structure type for this strategy.

        Returns:
            ClassificationType.PER_ROUND or ClassificationType.OVERALL
        """
        return self.get_strategy_behavior().classification_type

    def get_classification_criteria(self):
        """Get ranking criteria for this strategy.

        Returns:
            ClassificationCriteria.MATCH_WINS or ClassificationCriteria.RACKS_WON
        """
        return self.get_strategy_behavior().classification_criteria

    def should_update_classification_on_match_complete(self) -> bool:
        """Check if classification should update after each match.

        Random strategy: True (update after each match)
        Other strategies: False (update after round completes)
        """
        from models.matchmaking.configuration import ClassificationUpdateTiming

        timing = self.get_strategy_behavior().classification_update
        return timing == ClassificationUpdateTiming.ON_MATCH_COMPLETE

    def get_default_odd_policy(self):
        """Get default odd number policy based on strategy and distance.

        Random (distance <= 7): TRIO
        Random (distance > 7): BYE_WITH_CHALLENGE
        Other strategies: BYE
        """
        return self.get_strategy_behavior().get_default_odd_policy(self.distance)

    def can_use_trio(self) -> bool:
        """Check if trio matches are allowed for this gara.

        Trio matches only allowed for distances 2-7 (per ADR-005).
        """
        return self.get_strategy_behavior().can_use_trio(self.distance)

    @property
    def ammette_esercizi_fra_i_turni(self) -> bool:
        """Questa gara puo' avere esercizi fra i turni (`GaraChallenge`).

        Valgono con ogni formula **a turni** — Amalfi e casuale — e non sui
        tabelloni, dove i turni non sono un momento della serata ma un ramo
        dell'albero. In un campionato decide `challenge_mode`.

        Fino al 2026-09-12 erano offerti solo con l'accoppiamento casuale: il
        limite stava nei template e nelle route, non nel servizio (canvas
        «Pagina gara del direttore», decisione 4).
        """
        from models.matchmaking.configuration import BRACKET_STRATEGIES

        if self.matchmaking_strategy in BRACKET_STRATEGIES:
            return False
        campionato = getattr(self, "campionato", None)
        if campionato is not None and not getattr(campionato, "challenge_mode", True):
            return False
        return True

    def creates_all_rounds_at_startup(self) -> bool:
        """Check if this strategy creates all rounds at tournament startup.

        Random strategy creates all rounds at once (no progressive round creation).
        Other strategies create rounds one at a time.
        """
        return self.get_strategy_behavior().creates_all_rounds_at_startup

    def can_modify_inscription_dates(self):
        """Verifica se si possono modificare le date iscrizioni"""
        # Permetti modifica in setup, inscription, o quando le iscrizioni sono scadute
        # ma la gara non è ancora iniziata
        return self.status in [GaraStatus.SETUP.value, GaraStatus.INSCRIPTION.value]

    def can_be_modified(self):
        """Verifica se la gara può essere modificata"""
        inscriptions_list = getattr(self, "inscriptions", []) or []
        return not inscriptions_list and self.status == GaraStatus.SETUP.value

    def can_be_deleted(self):
        """Verifica se la gara può essere cancellata"""
        inscriptions_list = getattr(self, "inscriptions", []) or []
        return not inscriptions_list and self.status == GaraStatus.SETUP.value

    def soft_delete(self, reason: str = "") -> None:
        """Override soft_delete to support deleted_reason field.

        Args:
            reason: Optional reason for deletion
        """
        self.deleted_at = utc_now()
        self.deleted_reason = reason

    def can_cancel_round(self, round_number: Optional[int] = None) -> bool:
        """Verifica se l'avvio di un turno può essere cancellato.

        Args:
            round_number: Numero del turno da verificare. Se None, usa
                current_round.

        Returns:
            bool: True se il turno può essere cancellato, False altrimenti.

        Business Rules:
            - La gara deve essere in stato PLAYING
            - Il turno specificato deve esistere
            - Non devono esserci risultati inseriti (neanche parziali)
            - Tutti i match devono essere in stato PENDING
        """
        if self.status != GaraStatus.PLAYING.value:
            return False

        # Use current_round if round_number not specified
        target_round = round_number if round_number is not None else self.current_round

        # Verifica che non ci siano risultati inseriti nelle partite del turno
        try:
            from models.match.models import Match

            round_matches = Match.query.filter_by(
                gara_id=self.id, round_number=target_round
            ).all()
            if not round_matches:
                return False

            # Controlla che non ci siano risultati inseriti (neanche parziali)
            # Esclude i match bye che sono auto-completati con 3-0
            for match in round_matches:
                if match.is_bye:
                    continue  # Skip bye matches - they're auto-completed

                # Check normal match scores
                if match.player1_score > 0 or match.player2_score > 0:
                    return False

                # Check trio match scores
                if match.is_trio and match.trio_match:
                    trio = match.trio_match
                    if (
                        trio.player1_racks > 0
                        or trio.player2_racks > 0
                        or trio.player3_racks > 0
                        or trio.is_completed
                    ):
                        return False

            return True
        except Exception:
            return False

    @property
    def distance_config(self):
        """Get Distance value object for this gara.

        Returns unified Distance abstraction supporting both single-set
        and multi-set configurations.

        Returns:
            Distance: Immutable distance configuration
        """
        from models.match.distance import Distance

        if not self.is_multi_set:
            # Single-set configuration (backward compatible)
            return Distance(
                racks=self.distance,
                is_race_to_racks=self.is_race_to,
                is_multi_set=False,
                sets=1,
                is_race_to_sets=True,
            )
        else:
            # Multi-set configuration (Phase 6: Frontend Integration)
            return Distance(
                racks=self.distance,
                is_race_to_racks=self.is_race_to,
                is_multi_set=True,
                sets=self.match_distance if self.match_distance else 1,
                is_race_to_sets=(
                    self.is_race_to_sets if self.is_race_to_sets is not None else True
                ),
            )

    def copy_settings_from(self, source_gara):
        """Copia le impostazioni da un'altra gara"""
        self.discipline = source_gara.discipline
        self.distance = source_gara.distance
        self.is_race_to = source_gara.is_race_to
        self.rounds_count = source_gara.rounds_count
        self.min_participants = source_gara.min_participants
        self.max_participants = source_gara.max_participants
        self.entry_fee = source_gara.entry_fee

    def get_active_inscriptions_count(self):
        """Conta le iscrizioni attive (non in lista d'attesa e non ritirate)"""
        return Inscription.active_count_for_gara(self.id)

    def get_waitlist_count(self):
        """Conta i giocatori in lista d'attesa"""
        return len(
            [i for i in self.inscriptions if i.is_waitlist and not i.is_withdrawn]
        )

    def get_podium(self):
        """
        Restituisce il podio (top positions) della classifica finale in base
        a tiebreaker_until_position.

        Returns:
            List[dict]: Lista di dizionari con 'position', 'user', 'username'
                        per i premiati. Lista vuota se la gara
                        non è completata o non ha classifiche.
        """
        if self.status != GaraStatus.COMPLETED.value:
            return []

        try:
            from models.classification.services import RoundClassificationService

            # Use tiebreaker_until_position to define the podium size
            limit = self.tiebreaker_until_position or 3

            standings = RoundClassificationService.get_round_standings(
                self.id, self.rounds_count
            )
            podium = []
            for rc in standings[:limit]:
                podium.append(
                    {
                        "position": rc.position,
                        "user": rc.user,
                        "username": rc.user.username if rc.user else "?",
                    }
                )
            return podium
        except Exception:
            return []

    def is_full(self):
        """Verifica se la gara ha raggiunto il numero massimo di partecipanti"""
        if not self.max_participants:
            return False
        return self.get_active_inscriptions_count() >= self.max_participants

    def has_waitlist(self):
        """Verifica se la gara ha una lista d'attesa attiva"""
        return self.max_participants is not None and self.is_full()

    def __repr__(self):
        if self.is_standalone:
            return f"<Gara Standalone '{self.name}'>"
        return f"<Gara {self.name} (Campionato {self.campionato_id})>"


class Inscription(db.Model):
    """Player registration to a competition round."""

    __tablename__ = "inscription"

    # Un giocatore, un'iscrizione per gara. La regola c'è da sempre, ma stava
    # solo in `InscriptionService.inscribe_user` (`if existing: return
    # existing`) — cioè in un `if` di Python, invisibile a chi scrive in SQL.
    # L'unione di due account riassegnava le iscrizioni con un UPDATE di massa
    # e sulle gare comuni lasciava il giocatore iscritto due volte, una con la
    # categoria e una senza. Il vincolo è anche ciò che insegna la regola alla
    # dedup del merge, che deduce l'unicità logica dallo schema
    # (`UserMergeService._is_constrained`).
    __table_args__ = (
        db.UniqueConstraint("gara_id", "user_id", name="uq_inscription_gara_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=False
    )
    created_at = db.Column(db.DateTime, default=utc_now)
    initial_order = db.Column(db.Integer)  # ordine sorteggio iniziale

    user = db.relationship(
        "User", back_populates="inscriptions", foreign_keys=[user_id]
    )

    # Chi ha registrato l'iscrizione, quando non è stato il giocatore: il
    # direttore che lo ha iscritto a mano, anche a finestra chiusa. NULL vuol
    # dire «non si sa» — le iscrizioni precedenti al 2026-09-16 non lo hanno
    # mai scritto. Stesso schema di `PlayoffQualification.responded_by_id`.
    inscribed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    inscribed_by = db.relationship("User", foreign_keys=[inscribed_by_id])

    @property
    def iscritto_dal_direttore(self) -> bool:
        """True se a iscriverlo è stato qualcun altro."""
        return self.inscribed_by_id is not None and self.inscribed_by_id != self.user_id

    is_withdrawn = db.Column(db.Boolean, default=False, nullable=False)
    withdrawn_at = db.Column(db.DateTime, nullable=True)

    # Forfait status (for withdraw policy handling)
    is_forfeit = db.Column(db.Boolean, default=False, nullable=False)
    forfeit_at = db.Column(db.DateTime, nullable=True)

    # Lista d'attesa
    is_waitlist = db.Column(db.Boolean, default=False, nullable=False)
    waitlist_position = db.Column(db.Integer, nullable=True)
    # Reason: 'capacity' (max exceeded) or 'parity' (odd count w/ NO policy)
    waitlist_reason = db.Column(db.String(20), nullable=True)

    # Squadra con cui il giocatore disputa QUESTA gara. È l'unica fonte
    # autorevole per la separazione dei compagni nel sorteggio: il testo
    # libero sul profilo (user.squadra) serve solo a precompilare questo
    # campo al momento dell'iscrizione, e non viene più riletto dopo.
    # NULL = "gioca senza squadra qui", uno stato legittimo e distinto.
    squadra_id = db.Column(
        db.Integer, db.ForeignKey("squadra.id", ondelete="SET NULL"), nullable=True
    )
    squadra = db.relationship("Squadra", foreign_keys=[squadra_id])

    # Categoria di gioco del giocatore in QUESTA gara. Decide se le sue
    # partite contano per l'ELO quando la gara ha l'handicap: due giocatori
    # della stessa categoria si affrontano ad armi pari, quindi il risultato
    # dice qualcosa sulla loro forza. Vedi ADR-049.
    # NULL = "categoria non assegnata", che qui NON è una scelta legittima
    # come per la squadra ma un dato mancante: è la ragione per cui quelle
    # partite restano fuori dall'ELO.
    categoria_id = db.Column(
        db.Integer, db.ForeignKey("categoria.id", ondelete="SET NULL"), nullable=True
    )
    categoria = db.relationship("Categoria", foreign_keys=[categoria_id])

    @classmethod
    def active_for_gara(cls, gara_id: int) -> list["Inscription"]:
        """Return active (non-withdrawn, non-waitlist) inscriptions for a gara."""
        return cls.query.filter_by(
            gara_id=gara_id, is_withdrawn=False, is_waitlist=False
        ).all()

    @classmethod
    def active_count_for_gara(cls, gara_id: int) -> int:
        """Count active (non-withdrawn, non-waitlist) inscriptions for a gara."""
        return cls.query.filter_by(
            gara_id=gara_id, is_withdrawn=False, is_waitlist=False
        ).count()

    def __repr__(self):
        return f"<Inscription {self.user_id} -> {self.gara_id}>"
