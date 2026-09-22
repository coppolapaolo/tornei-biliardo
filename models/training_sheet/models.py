"""La scheda di allenamento, le sue voci, le sedute e il registro (ADR-067).

Cinque tabelle, e il filo che le tiene insieme è uno solo: **una scheda che
cambia non riscrive le sedute già fatte**.

    training_sheet          la scheda: nome, e le opzioni facoltative
      training_sheet_item   una voce: quale esercizio, quanto farne, come si segna
      training_sheet_reader chi la legge, oltre a chi la possiede (D11)
    training_session        una seduta: un giorno, dall'inizio alla fine
      training_entry        una casella del registro: il numero segnato

Il modello viene dal foglio di carta che Rōnin ASD usa davvero (scheda lv.3,
v0.6): una riga per seduta, una colonna per esercizio — sdoppiata quando lo si
fa a destra e a sinistra — e un totale che si confronta con una soglia. Ma la
forma è una sola anche per una scheda che di totale non ne ha: sono le **voci**
a decidere come si segnano (`SheetMeasure`), e livello, soglia, giorni e durata
sono interruttori facoltativi della scheda (decisione dell'utente del 19/09).
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.types import Float, TypeDecorator

from ..base import BaseModel, db, utc_now
from .measure import LevelUp, ScoreAggregation, SheetMeasure


class CellNumber(TypeDecorator):
    """Il numero di una casella: un intero quando lo è, un decimale se no.

    Una media di prove a punteggio fa 6,5 (ADR-072); un «4 su 5» resta un 4,
    e deve **restare** un 4 anche letto dal database — non un 4.0 che poi si
    stampa con la virgola. SQLite scrive il decimale dove scriveva l'intero:
    la colonna non cambia.
    """

    impl = Float
    cache_ok = True

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        numero = float(value)
        return int(numero) if numero.is_integer() else numero


class TrainingSheet(BaseModel):
    """Una scheda di allenamento: una sequenza ordinata di voci.

    ``version`` cresce quando cambia **ciò che i numeri vogliono dire** — una
    voce aggiunta, tolta, o il suo «quanto farne». Ogni seduta si porta dietro
    la versione con cui è stata fatta, così il registro di sei mesi fa continua
    a dire quello che diceva: il «4» di allora era su cinque tiri anche se oggi
    ne sono dieci.
    """

    __tablename__ = "training_sheet"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    owner_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    #: Il gradino di una scala, quando la scheda è fatta a livelli. NULL è la
    #: risposta giusta per una scheda che a livelli non è fatta: mai uno zero
    #: o un uno inventato.
    level = db.Column(db.Integer, nullable=True)
    #: Quanto bisogna fare per dire che la scheda è superata. Si confronta col
    #: totale della seduta, che somma le sole voci «a riusciti» (D17).
    threshold = db.Column(db.Integer, nullable=True)
    #: Quante sedute **di fila** sopra la soglia servono. Uno, di solito: un
    #: colpo di fortuna non è un livello raggiunto, e chi vuole essere severo
    #: alza questo numero.
    threshold_streak = db.Column(
        db.Integer, nullable=False, default=1, server_default="1"
    )
    #: Quante settimane dura il programma. NULL = non si è detto.
    weeks = db.Column(db.Integer, nullable=True)
    #: Se le voci sono divise per giorno (A · B · C). Senza, una seduta fa
    #: tutta la scheda.
    uses_days = db.Column(db.Boolean, nullable=False, default=False, server_default="0")

    #: Se chi legge la scheda vede anche le **note** delle sedute. Spento per
    #: default (ADR-069): la nota è il posto dove si scrive «oggi malissimo,
    #: braccio rigido», e aprirla d'ufficio trasformerebbe un diario in un
    #: rapportino. Chi vuole che l'istruttore la legga lo dice.
    readers_see_notes = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )

    #: Chi sancisce il gradino, quando la soglia è stata tenuta (D8):
    #: `none` nessuno, `auto` la soglia stessa, `instructor` chi ti segue.
    #: I valori stanno in una `String` e non in un `db.Enum`, come `measure`.
    level_up = db.Column(
        db.String(12), nullable=False, default="auto", server_default="auto"
    )
    #: Quando il livello di questa scheda è stato **superato**. NULL = non
    #: ancora. È un fatto, non una previsione: da qui in poi la scheda resta
    #: superata anche se le sedute dopo vanno peggio.
    passed_at = db.Column(db.DateTime, nullable=True)
    #: Chi l'ha sancito. NULL con `auto`, dove a sancire è stata la soglia:
    #: sono due cose diverse e si leggono diversamente («superato il 12/10» /
    #: «confermato da Luca il 12/10»).
    passed_by_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )

    version = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="1")

    owner = db.relationship("User", foreign_keys=[owner_id])
    passed_by = db.relationship("User", foreign_keys=[passed_by_id])
    items = db.relationship(
        "TrainingSheetItem",
        back_populates="sheet",
        cascade="all, delete-orphan",
        order_by="TrainingSheetItem.position",
    )
    readers = db.relationship(
        "TrainingSheetReader",
        back_populates="sheet",
        cascade="all, delete-orphan",
    )
    sessions = db.relationship(
        "TrainingSession",
        back_populates="sheet",
        cascade="all, delete-orphan",
    )

    @property
    def active_items(self) -> List["TrainingSheetItem"]:
        """Le voci che si fanno oggi. Le ritirate restano per le sedute vecchie.

        Ordinate qui e non solo dalla relazione: durante una composizione le
        posizioni cambiano in memoria, e l'ordine della collezione è quello
        dell'ultima lettura dal database.
        """
        return sorted(
            (item for item in self.items if item.is_active),
            key=lambda item: item.position or 0,
        )

    def items_for_day(self, day: Optional[str]) -> List["TrainingSheetItem"]:
        """Le voci di un giorno. Senza giorni, o senza giorno, sono tutte."""
        if not self.uses_days or day is None:
            return self.active_items
        return [item for item in self.active_items if item.day == day]

    @property
    def days(self) -> List[str]:
        """I giorni che le voci nominano, in ordine: A · B · C."""
        if not self.uses_days:
            return []
        return sorted({item.day for item in self.active_items if item.day})

    def total_for_day(self, day: Optional[str] = None) -> int:
        """Quanto vale al massimo una seduta: la somma delle voci «a riusciti».

        È il denominatore del «51 su 60», e il numero con cui si taglia la
        soglia. Una voce fatta a destra e a sinistra conta due volte, perché si
        tirano il doppio dei tiri.
        """
        return sum(item.weight for item in self.items_for_day(day))

    @property
    def total(self) -> int:
        return self.total_for_day(None)

    @property
    def has_threshold(self) -> bool:
        return self.threshold is not None and self.total > 0

    @property
    def level_up_kind(self) -> "LevelUp":
        return LevelUp.parse(self.level_up)

    @property
    def is_passed(self) -> bool:
        return self.passed_at is not None

    def __repr__(self) -> str:  # pragma: no cover - banale
        return f"<TrainingSheet {self.id} {self.name!r}>"


class TrainingSheetItem(BaseModel):
    """Una voce della scheda: quale esercizio, quanto farne, come si segna.

    Una voce con delle registrazioni **non si cancella, si ritira**
    (``is_active``): cancellarla porterebbe via con sé le caselle già compilate
    — la stessa regola di `ChallengeVariant`, che con delle prove si rinomina e
    non si toglie (ADR-065).

    Lo stesso esercizio può comparire in due voci: il rastrello del
    riscaldamento e il rastrello di fine seduta sono due righe del foglio, e il
    registro intesta le colonne con la **posizione**, come il foglio di carta.
    """

    __tablename__ = "training_sheet_item"

    id = db.Column(db.Integer, primary_key=True)
    sheet_id = db.Column(
        db.Integer,
        db.ForeignKey("training_sheet.id", ondelete="CASCADE"),
        nullable=False,
    )
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="CASCADE"), nullable=False
    )
    position = db.Column(db.Integer, nullable=False)

    #: Il titoletto sopra un gruppo di voci: «Riscaldamento», «Tecnica»,
    #: «Gioco». Libero di chi compone, come famiglia e passo dell'esercizio.
    section = db.Column(db.String(60), nullable=True)
    #: Il giorno, quando la scheda ne ha: «A», «B», «C».
    day = db.Column(db.String(12), nullable=True)

    measure = db.Column(
        db.String(20), nullable=False, default="made", server_default="made"
    )
    #: Quanti tiri, partite, minuti — o, col punteggio, **quante prove**
    #: (ADR-072). Il massimo di ogni prova lo dice già l'esercizio.
    amount = db.Column(db.Integer, nullable=True)
    #: Col punteggio, come le N prove diventano il numero della casella:
    #: somma, media, mediana, massimo (`ScoreAggregation`). NULL altrove.
    aggregation = db.Column(db.String(10), nullable=True)
    #: Se le varianti dell'esercizio si segnano separate (destra e sinistra,
    #: A e B), ognuna col suo «quanto farne».
    per_variant = db.Column(
        db.Boolean, nullable=False, default=False, server_default="0"
    )

    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="1")

    sheet = db.relationship("TrainingSheet", back_populates="items")
    challenge = db.relationship("Challenge")
    entries = db.relationship(
        "TrainingEntry", back_populates="item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # L'unicità della posizione vale **fra le voci attive**: una ritirata
        # tiene il posto che aveva, e due ritirate possono averlo avuto uguale.
        # Un `if` in Python non basterebbe (CLAUDE.md, «Contare su un if
        # applicativo per l'unicità di una riga»), e un UNIQUE pieno
        # impedirebbe di ritirare e ricomporre.
        db.Index(
            "uq_training_sheet_item_position",
            "sheet_id",
            "position",
            unique=True,
            sqlite_where=db.text("is_active = 1"),
        ),
    )

    @property
    def measure_kind(self) -> SheetMeasure:
        return SheetMeasure.parse(self.measure)

    @property
    def aggregation_kind(self) -> Optional[ScoreAggregation]:
        """Come si aggregano le prove a punteggio; ``None`` sulle altre misure."""
        if self.measure_kind is not SheetMeasure.SCORE:
            return None
        return ScoreAggregation.parse(self.aggregation)

    @property
    def makes_attempts(self) -> bool:
        """Se le caselle di questa voce sono fatte di prove del catalogo.

        Serve la misura giusta **e** l'esercizio giusto (ADR-072): «riusciti»
        su un esercizio a esito netto, «punteggio» su uno a punteggio. Una voce
        composta prima, con la misura dell'altro tipo, resta una casella e
        basta — leggibile, ma senza prove dietro.
        """
        misura = self.measure_kind
        if not misura.makes_attempts or self.challenge is None:
            return False
        return SheetMeasure.for_challenge(self.challenge) is misura

    @property
    def variants(self):
        """Le varianti su cui si segna questa voce, o lista vuota."""
        if not self.per_variant or self.challenge is None:
            return []
        return list(self.challenge.variants)

    @property
    def slots(self) -> int:
        """Quante caselle occupa nel registro: una, o una per variante."""
        return max(1, len(self.variants)) if self.per_variant else 1

    @property
    def weight(self) -> int:
        """Quanto porta al totale della seduta. Zero se non è «a riusciti»."""
        if not self.measure_kind.counts_toward_threshold or self.amount is None:
            return 0
        return self.amount * self.slots

    def __repr__(self) -> str:  # pragma: no cover - banale
        return f"<TrainingSheetItem {self.id} pos={self.position} {self.measure}>"


class TrainingSheetReader(BaseModel):
    """Chi legge una scheda, oltre a chi la possiede (D11).

    Il legame è **allievo–scheda–istruttore**, non allievo–istruttore: «I miei
    istruttori» e «I miei allievi» sono viste derivate da questa tabella. Lo
    decide il giocatore, scheda per scheda, e vale subito (D18).

    Nasce qui perché è parte della scheda; l'interfaccia che la riempie arriva
    con gli istruttori (fase 8): finché il ruolo non c'è, non c'è nessuno da
    cercare.
    """

    __tablename__ = "training_sheet_reader"

    id = db.Column(db.Integer, primary_key=True)
    sheet_id = db.Column(
        db.Integer,
        db.ForeignKey("training_sheet.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    granted_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    #: Quando il permesso è finito. NULL = legge ancora. Le righe non si
    #: cancellano: «da quando a quando» è la domanda a cui questa tabella
    #: risponde.
    revoked_at = db.Column(db.DateTime, nullable=True)

    sheet = db.relationship("TrainingSheet", back_populates="readers")
    user = db.relationship("User", foreign_keys=[user_id])

    @property
    def is_current(self) -> bool:
        return self.revoked_at is None

    def __repr__(self) -> str:  # pragma: no cover - banale
        return f"<TrainingSheetReader sheet={self.sheet_id} user={self.user_id}>"


class TrainingSession(BaseModel):
    """Una seduta: la riga del foglio (D7).

    È un'entità, non una finestra sull'orologio — al contrario delle «prove di
    oggi» dell'allenamento libero. La differenza sta nel foglio di carta: lì la
    riga esiste prima di essere riempita, si compila in mezz'ora con le mani
    sporche di gesso, e deve sopravvivere a un telefono che si spegne.
    """

    __tablename__ = "training_session"

    id = db.Column(db.Integer, primary_key=True)
    sheet_id = db.Column(
        db.Integer,
        db.ForeignKey("training_sheet.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    #: La versione della scheda con cui è stata fatta: il registro la usa per
    #: sapere quando le colonne sono cambiate.
    sheet_version = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    day = db.Column(db.String(12), nullable=True)

    started_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    #: NULL finché la seduta è aperta. Una seduta aperta non entra nel registro
    #: e non fa media: è quella che si sta facendo.
    ended_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    sheet = db.relationship("TrainingSheet", back_populates="sessions")
    user = db.relationship("User", foreign_keys=[user_id])
    entries = db.relationship(
        "TrainingEntry",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.Index("ix_training_session_sheet_user", "sheet_id", "user_id"),
    )

    @property
    def is_open(self) -> bool:
        return self.ended_at is None

    @property
    def total(self) -> int:
        """Il totale della seduta: somma delle caselle «a riusciti»."""
        return sum(
            entry.value or 0
            for entry in self.entries
            if SheetMeasure.parse(entry.measure).counts_toward_threshold
        )

    @property
    def max_total(self) -> int:
        """Su quanto: la somma dei «quanto farne» delle caselle compilabili.

        Si legge dalle **registrazioni**, non dalla scheda di oggi: è il «su
        60» che quella sera era vero.
        """
        return sum(
            entry.target_amount or 0
            for entry in self.entries
            if SheetMeasure.parse(entry.measure).counts_toward_threshold
        )

    def __repr__(self) -> str:  # pragma: no cover - banale
        stato = "aperta" if self.is_open else "chiusa"
        return f"<TrainingSession {self.id} sheet={self.sheet_id} {stato}>"


class TrainingEntry(BaseModel):
    """Una casella del registro: il numero segnato su una voce, in una seduta.

    ``measure`` e ``target_amount`` sono **copiati dalla voce** al momento in
    cui si segna, e non si rileggono più da lì: se domani la voce passa da
    cinque tiri a dieci, il «4 su 5» di stasera resta un quattro su cinque
    (stesso schema di `ChallengeShot.points`, ADR-066, e di `break_player_id`,
    ADR-056).

    ``marks`` è **come** ci si è arrivati, quando si è contato tiro per tiro:
    una stringa di ``1`` e ``0`` in ordine di tiro. Il numero resta ``value``,
    che è la verità; la striscia è il racconto, e su una voce scritta col
    totale non c'è.

    Dall'ADR-072 una casella «riusciti» o «punteggio» è fatta di **prove del
    catalogo** (``attempts``): cinque prove a esito netto per un «4 su 5», tre
    prove a punteggio per una media. Spariscono con la casella. Le caselle
    scritte prima non ne hanno, e si leggono come sempre.
    """

    __tablename__ = "training_entry"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("training_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_id = db.Column(
        db.Integer,
        db.ForeignKey("training_sheet_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Su quale variante, quando la voce si segna separata per lato. NULL
    #: quando la voce è una casella sola.
    variant_id = db.Column(
        db.Integer,
        db.ForeignKey("challenge_variant.id", ondelete="CASCADE"),
        nullable=True,
    )

    #: Il numero: riusciti, punteggio (anche una media), partite vinte, minuti.
    value = db.Column(CellNumber, nullable=True)
    #: La spunta, per le voci che si segnano «fatto».
    done = db.Column(db.Boolean, nullable=True)
    marks = db.Column(db.String(200), nullable=True)

    measure = db.Column(db.String(20), nullable=False)
    target_amount = db.Column(db.Integer, nullable=True)
    #: Copiata dalla voce come `measure`: come le prove fanno il numero.
    aggregation = db.Column(db.String(10), nullable=True)

    session = db.relationship("TrainingSession", back_populates="entries")
    item = db.relationship("TrainingSheetItem", back_populates="entries")
    variant = db.relationship("ChallengeVariant")
    #: Le prove del catalogo di cui questa casella è fatta (ADR-072), in
    #: ordine. Vuota sulle misure che non fanno prove e sulle caselle vecchie.
    attempts = db.relationship(
        "ChallengeAttempt",
        back_populates="training_entry",
        cascade="all, delete-orphan",
        order_by="[ChallengeAttempt.attempted_at, ChallengeAttempt.id]",
    )

    __table_args__ = (
        # Una casella per (seduta, voce, variante). In SQLite un UNIQUE non
        # vincola le righe con NULL — due caselle «senza variante» passerebbero
        # entrambe — quindi i casi sono due indici parziali, uno per ciascuno.
        db.Index(
            "uq_training_entry_variant",
            "session_id",
            "item_id",
            "variant_id",
            unique=True,
            sqlite_where=db.text("variant_id IS NOT NULL"),
        ),
        db.Index(
            "uq_training_entry_plain",
            "session_id",
            "item_id",
            unique=True,
            sqlite_where=db.text("variant_id IS NULL"),
        ),
    )

    @property
    def measure_kind(self) -> SheetMeasure:
        return SheetMeasure.parse(self.measure)

    @property
    def is_filled(self) -> bool:
        """Se la casella è stata compilata. Uno zero è una risposta."""
        if self.measure_kind is SheetMeasure.DONE:
            return self.done is not None
        return self.value is not None

    @property
    def shots_done(self) -> int:
        """Quanti tiri sono stati segnati uno per uno. Zero col totale."""
        return len(self.marks or "")

    @property
    def aggregation_kind(self) -> Optional[ScoreAggregation]:
        if self.measure_kind is not SheetMeasure.SCORE:
            return None
        return ScoreAggregation.parse(self.aggregation)

    @property
    def completed_attempts(self) -> List:
        """Le prove chiuse, in ordine: una aperta non fa ancora numero."""
        return [a for a in self.attempts if a.completed]

    @property
    def scores(self) -> List[int]:
        """I punteggi delle prove chiuse, per l'aggregazione."""
        return [a.score for a in self.completed_attempts if a.score is not None]

    @property
    def attempts_done(self) -> int:
        return len(self.completed_attempts)

    def __repr__(self) -> str:  # pragma: no cover - banale
        return f"<TrainingEntry s={self.session_id} i={self.item_id} v={self.value}>"


__all__ = [
    "TrainingSheet",
    "TrainingSheetItem",
    "TrainingSheetReader",
    "TrainingSession",
    "TrainingEntry",
]
