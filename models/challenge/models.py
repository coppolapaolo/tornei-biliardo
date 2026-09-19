"""
Dominio Challenge - Modelli per il Sistema di Sfide di Abilità

Questo modulo implementa il sistema di sfide per la piattaforma community di
Biliardo Americano, consentendo ai giocatori di testare e sviluppare le proprie
abilità attraverso sfide individuali.

Architettura Domain-Driven Design:
- Challenge: Entità principale che rappresenta una sfida di abilità
- ChallengeAttempt: Tentativo di un giocatore su una specifica sfida
- ChallengeFavorite: Sistema di preferiti per accesso rapido alle sfide

Tipologie di Sfide:
1. Sfide Numeriche (pass_fail_only=False):
   - Punteggio numerico da 0 a valore massimo
   - Il campo 'passed' rimane None (non applicabile)
   - Utilizzabili come sostituzione X nei campionati
   - Esempi: spot shot rally, sequence shots, break shots

2. Sfide Pass/Fail (pass_fail_only=True):
   - Solo risultato superato/non superato
   - Il campo 'passed' è esplicitamente impostato (True/False)
   - Score è 1 per pass, 0 per fail (rappresentazione numerica)
   - Non utilizzabili per sostituzione X

Integrazione Community:
- Sistema di preferiti per accesso rapido alle sfide preferite
- Statistiche condivise per competizione comunitaria
- Utilizzo nelle gare come sostituzione X per gestione numeri dispari
- Tracciamento delle performance individuali per sviluppo abilità

Modifiche Recenti (Settembre 2025):
- Rimossa logica automatica di pass/fail al 70% (non conforme alle specifiche)
- Per sfide numeriche, 'passed' rimane None (campo non applicabile)
- Solo sfide pass/fail esplicite impostano il campo 'passed'
- Statistiche corrette per gestire pass_rate come None per sfide numeriche
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional

from sqlalchemy import desc

from ..base import db, BaseModel, utc_now
from .vocabulary import Abilita, CategoryAxis, Gesto


class Challenge(BaseModel):
    """
    Entità Challenge - Sfida di Abilità per Giocatori

    Rappresenta una sfida individuale che i giocatori possono affrontare per sviluppare
    le proprie abilità nel biliardo americano. Supporta due modalità di scoring:
    1. Numerica: punteggio da 0 a massimo (es. 15 su 15 palline imbucate)
    2. Pass/Fail: solo superato/non superato (es. sequenza corretta completata)

    Funzionalità:
    - Sistema di tentativi multipli per ogni giocatore
    - Statistiche aggregate per amministratori
    - Integrazione con sistema di sostituzione X nei campionati
    - Sistema di preferiti per accesso rapido
    - Gestione immagini per visualizzazione setup tavolo

    Business Rules:
    - Solo sfide numeriche possono essere usate come sostituzione X
    - Sfide attive (is_active=True) sono visibili ai giocatori
    - Ogni sfida ha una descrizione e un'immagine del setup
    """

    __tablename__ = "challenge"

    id = db.Column(db.Integer, primary_key=True)

    # Il nome del drill, se chi l'ha creato gliene ha dato uno. **Facoltativo**:
    # NULL non e' un dato mancante, e' «non ha un nome», e in quel caso il nome
    # se lo prende dal progressivo (vedi `get_display_name`). Non si riempie con
    # la descrizione troncata, che e' esattamente il problema da cui nasce
    # questa colonna: venti drill che cominciano con «Disponi le bilie…» sono
    # venti card indistinguibili.
    title = db.Column(db.String(120), nullable=True)

    description = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=False)

    # Il disegno del drill, quando e' stato costruito invece che fotografato:
    # la scena del builder in JSON (`{v, title, orient, cloth, ballScale,
    # items}`). NULL su ogni drill nato da una foto, che e' la maggioranza.
    #
    # Perche' due cose e non una. L'immagine serve a **mostrare** il drill e la
    # scena serve a **modificarlo**, e nessuna delle due sa fare il mestiere
    # dell'altra: da un PNG non si torna indietro alle bilie, e una scena non
    # si mette dentro un `<img>` ne' si manda per email. Tenere solo la scena
    # vorrebbe dire ridisegnarla a ogni miniatura del catalogo; tenere solo il
    # PNG vorrebbe dire che correggere una bilia significa rifare il disegno
    # da capo.
    diagram_scene = db.Column(db.Text, nullable=True)

    # Configurazione Scoring - determina il tipo di valutazione dell'esercizio
    pass_fail_only = db.Column(db.Boolean, nullable=False, default=False)
    # False: esercizio a punteggio (0-N), True: esercizio superato/non superato

    # Il punteggio massimo ottenibile, **se l'esercizio ne ha uno**. Facoltativo:
    # NULL non e' un dato mancante, dice «questo esercizio non ha un tetto» — ci
    # sono prove che si ripetono finche' si sbaglia, dove il massimo non esiste.
    #
    # Non e' in conflitto con ``ExamChallenge.max_score`` (ADR-042): le due
    # colonne rispondono a domande diverse.
    #
    #   questo campo          → *quanto vale al massimo questa prova*, che e'
    #                           una proprieta' dell'esercizio: quindici bilie
    #                           sono quindici bilie in qualunque contesto
    #   ExamChallenge.max_score → *quanto pesa dentro quell'esame*, che e' una
    #                           scelta di chi l'esame lo compone
    #
    # Il primo fa da valore proposto al secondo, e serve a due cose che l'esame
    # non copre: mostrare «12 / 15» a chi si allena dal catalogo, e rifiutare un
    # 20 su un esercizio che arriva a 15. Fuori da un esame, prima, non c'era
    # nessun posto dove dire quanto vale al massimo una prova.
    max_score = db.Column(db.Integer, nullable=True)

    # ── Il profilo: che cosa allena e quanto e' difficile (ADR-065) ──────
    #
    # Tutte facoltative, e NULL non e' mai un dato mancante: dice «l'autore non
    # l'ha detto». Gli esercizi nati prima di queste colonne restano cosi'
    # finche' qualcuno non li descrive — un livello 1 messo d'ufficio sarebbe
    # una bugia che il catalogo poi filtra come vera.
    #
    # Le abilita' e i gesti **non** sono qui: un esercizio ne ha zero, una o
    # piu', quindi stanno in `challenge_category` (vedi `abilita` e `gesti`).

    # Livello **dichiarato** dall'autore, da 1 a 5. Il nome non e' «difficolta'»
    # di proposito: quella misurata dai risultati (#174) gli stara' accanto, e
    # due numeri con lo stesso nome in lettura non si distinguono piu'.
    declared_level = db.Column(db.Integer, nullable=True)

    # Famiglia e passo: «stop shot» 1 · 2 · 3, lo stesso gesto sempre piu'
    # difficile. Testo libero dell'autore — a differenza dei due vocabolari —
    # perche' le progressioni le inventa chi insegna, non la piattaforma.
    family = db.Column(db.String(80), nullable=True)
    family_step = db.Column(db.Integer, nullable=True)

    # La bianca: True = si rimette al suo posto a ogni tiro, False = resta dove
    # si ferma (e il tiro dopo parte da li'). Cambia che cosa misura il
    # punteggio, quindi e' un fatto dell'esercizio e non una nota nel testo.
    cue_ball_reset = db.Column(db.Boolean, nullable=True)

    # Metadata
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Relationships
    attempts = db.relationship(
        "ChallengeAttempt",
        back_populates="challenge",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    favorites = db.relationship(
        "ChallengeFavorite",
        back_populates="challenge",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    created_by = db.relationship("User", foreign_keys=[created_by_id])

    # `selectin` e non `dynamic`: il catalogo mostra le etichette di decine di
    # esercizi insieme, e una SELECT per card e' il modo in cui una pagina
    # passa da 3 a 60 query senza che nessun test se ne accorga.
    categories = db.relationship(
        "ChallengeCategory",
        back_populates="challenge",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    variants = db.relationship(
        "ChallengeVariant",
        back_populates="challenge",
        lazy="selectin",
        order_by="ChallengeVariant.position",
        cascade="all, delete-orphan",
    )

    ratings = db.relationship(
        "ChallengeRating",
        back_populates="challenge",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    @property
    def abilita(self) -> List[Abilita]:
        """Le abilita' allenate, **nell'ordine del vocabolario**.

        Una riga con un valore che il vocabolario non conosce piu' si salta:
        togliere una voce dall'enum non deve far esplodere il catalogo.
        """
        presenti = {
            c.value for c in self.categories if c.axis == CategoryAxis.ABILITA.value
        }
        return [a for a in Abilita if a.value in presenti]

    @property
    def gesti(self) -> List[Gesto]:
        """I gesti con cui si esegue, nell'ordine del vocabolario."""
        presenti = {
            c.value for c in self.categories if c.axis == CategoryAxis.GESTO.value
        }
        return [g for g in Gesto if g.value in presenti]

    @property
    def has_variants(self) -> bool:
        """Due o piu' etichette: con una sola non c'e' niente da distinguere."""
        return len(self.variants) >= 2

    def get_statistics(self) -> Dict[str, Any]:
        """
        Calcola Statistiche Sfida per Vista Amministratore

        Genera statistiche complete sui tentativi della sfida per permettere
        agli amministratori di monitorare l'utilizzo e la difficoltà.

        Returns:
            Dict contenente:
            - total_attempts: numero totale tentativi completati
            - unique_players: numero giocatori unici che hanno tentato
            - average_score: punteggio medio (per sfide numeriche)
            - median_score: punteggio mediano
            - max_score_achieved: punteggio massimo raggiunto
            - perfect_score_count: numero di punteggi perfetti
            - pass_rate: percentuale superamento
                (solo per sfide pass/fail, None per numeriche)

        Business Logic:
        - Solo tentativi completati sono considerati
        - Per sfide numeriche: pass_rate è None (non applicabile)
        - Per sfide pass/fail: pass_rate calcolato da campo 'passed'
        """
        # attempts e' lazy='dynamic': materializza UNA volta e deriva tutto in
        # memoria invece di rieseguire la SELECT per count/distinct/passed.
        attempts = self.attempts.filter_by(completed=True).all()

        total_attempts = len(attempts)
        unique_players = len({attempt.user_id for attempt in attempts})

        if total_attempts == 0:
            return {
                "total_attempts": 0,
                "unique_players": 0,
                "average_score": 0,
                "median_score": 0,
                "max_score_achieved": 0,
                "perfect_score_count": 0,
                "pass_rate": None,
            }

        # Calculate statistics
        scores = [attempt.score for attempt in attempts]
        average_score = sum(scores) / len(scores)
        # statistics.median media i due valori centrali per N pari (sorted()[
        # len//2] restituiva erroneamente il valore superiore-centrale).
        median_score = statistics.median(scores)
        max_score_achieved = max(scores)
        perfect_score_count = sum(1 for score in scores if score == max_score_achieved)

        # Calcolo pass_rate basato sul tipo di sfida
        if self.pass_fail_only:
            # Solo per sfide pass/fail esplicite: calcola percentuale di superamento
            # Utilizza il campo 'passed' che è esplicitamente impostato per queste sfide
            pass_rate = (
                sum(1 for attempt in attempts if attempt.passed) / total_attempts * 100
            )
        else:
            # Per sfide numeriche: pass_rate non è applicabile/significativo
            # Il campo 'passed' è None per queste sfide, quindi pass_rate è None
            pass_rate = None

        return {
            "total_attempts": total_attempts,
            "unique_players": unique_players,
            "average_score": round(average_score, 1),
            "median_score": median_score,
            "max_score_achieved": max_score_achieved,
            "perfect_score_count": perfect_score_count,
            "pass_rate": round(pass_rate, 1) if pass_rate is not None else None,
        }

    def get_user_best_attempt(self, user_id: int) -> Optional["ChallengeAttempt"]:
        """
        Recupera Miglior Tentativo Utente per questa Sfida

        Trova il tentativo con il punteggio più alto tra tutti i tentativi
        completati dell'utente per questa specifica sfida.

        Args:
            user_id: ID dell'utente di cui cercare il miglior tentativo

        Returns:
            ChallengeAttempt con score più alto, None se nessun tentativo completato

        Note:
            - Solo tentativi completati sono considerati
            - Ordinamento per score decrescente (migliore per primo)
        """
        return (
            self.attempts.filter_by(user_id=user_id, completed=True)
            .order_by(desc("score"))
            .first()
        )

    def can_be_used_for_x_replacement(self) -> bool:
        """
        Verifica Idoneità per Sostituzione X nei Campionati

        Determina se questa sfida può essere utilizzata come sostituzione X
        nella gestione dei numeri dispari durante i turni dei campionati.

        Business Rules per Sostituzione X:
        - Solo sfide con scoring numerico (pass_fail_only=False)
        - Solo sfide attive (is_active=True)
        - Il punteggio viene convertito in differenza rack equivalente

        Returns:
            True se la sfida può essere usata come X, False altrimenti

        Integration Notes:
        - Utilizzato dall'algoritmo Amalfi per gestione dispari
        - Score utilizzato direttamente come punteggio rack
        """
        # Solo sfide numeriche possono essere usate per sostituzione X
        # perché il punteggio numerico può essere utilizzato direttamente
        return not self.pass_fail_only and self.is_active

    def get_display_name(self) -> str:
        """Il nome con cui il drill si presenta ovunque: catalogo, esami, email.

        L'ordine è: il titolo scelto, altrimenti il progressivo — ``Esercizio 12``,
        dove 12 è l'id. Non si ripiega più sulla descrizione troncata a 50
        caratteri: era il comportamento di prima e faceva sembrare identici
        drill diversi, perché le istruzioni cominciano quasi sempre allo stesso
        modo («Disponi le bilie…»). Un numero distingue; mezza frase no.

        Il fallback è testo dell'interfaccia e passa da gettext, con l'import
        locale usato anche da ``Gara.display_name``: fuori da un contesto
        applicativo (script, migration) gettext solleva, e lì il testo grezzo
        va benissimo.

        Returns:
            Il titolo, oppure ``Esercizio <id>`` per gli esercizi senza titolo.
        """
        title = (self.title or "").strip()
        if title:
            return title

        try:
            from flask_babel import gettext

            return gettext("Esercizio %(number)s", number=self.id)
        except (RuntimeError, ImportError):
            return f"Esercizio {self.id}"

    @property
    def image_filename(self) -> Optional[str]:
        """Estrae nome file immagine (usa config.CHALLENGE_UPLOAD_FOLDER).

        Estrae solo il nome del file dal percorso completo dell'immagine
        per l'utilizzo nei template Jinja2 e nei componenti UI.
        Path configurabile via config.CHALLENGE_UPLOAD_FOLDER.

        Returns:
            Nome file (es. 'challenge_001.jpg') o None se nessun percorso

        Template Usage:
            <img src="{{ url_for('static',
                filename='uploads/challenges/' + challenge.image_filename) }}">
        """
        if self.image_path:
            # Estrae solo il filename dal path completo
            return self.image_path.split("/")[-1]
        return None

    def __repr__(self) -> str:
        return f"<Challenge #{self.id}: {self.get_display_name()}>"


class ChallengeAttempt(BaseModel):
    """
    Entità ChallengeAttempt - Tentativo di Sfida del Giocatore

    Rappresenta un singolo tentativo di un giocatore su una specifica sfida.
    Gestisce sia sfide numeriche che pass/fail con logica di scoring appropriata.

    Stati del Tentativo:
    - Non completato: completed=False, score=None, passed=None
    - Completato (numerico): completed=True, score=N, passed=None
    - Completato (pass/fail): completed=True, score=1/0, passed=True/False

    Integrazione Campionati:
    - Può essere collegato a una gara specifica (gara_id)
    - Utilizzato come sostituzione X per gestione numeri dispari
    - Score convertito in differenza rack per classifiche

    Business Rules Post-Refactor (Settembre 2025):
    - Rimossa logica automatica 70% pass threshold
    - Campo 'passed' solo per sfide pass/fail esplicite
    - Per sfide numeriche: passed=None sempre (non applicabile)
    - Score numerico sempre registrato per entrambi i tipi
    """

    __tablename__ = "challenge_attempt"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    # Dettagli del Tentativo
    score = db.Column(db.Integer, nullable=True)  # Punteggio: None se non completato
    passed = db.Column(
        db.Boolean, nullable=True
    )  # Solo per sfide pass/fail, None per numeriche
    completed = db.Column(
        db.Boolean, nullable=False, default=False
    )  # Stato completamento
    attempted_at = db.Column(
        db.DateTime, nullable=False, default=utc_now
    )  # Timestamp tentativo

    # Note opzionali sul tentativo (condizioni particolari, osservazioni)
    notes = db.Column(db.Text, nullable=True)

    # Con quale variante dell'esercizio e' stata fatta la prova (dx/sx, A/B).
    # NULL su ogni esercizio senza varianti — la quasi totalita' — e sulle prove
    # nate prima che l'autore le introducesse: «non si sa» resta «non si sa».
    variant_id = db.Column(
        db.Integer,
        db.ForeignKey("challenge_variant.id", ondelete="SET NULL"),
        nullable=True,
    )

    # DEPRECATED (Sprint 11, December 2025)
    # These fields violate DDD: Challenge domain shouldn't know about Gara.
    # Use GaraByeChallenge (models.competition.gara_bye_challenge) instead.
    # These fields are kept for backward compatibility with existing data.
    # New X replacement logic uses GaraByeChallenge as bridge entity.
    # See ADR-004-challenge-gara-decoupling.md for rationale.
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="SET NULL"), nullable=True
    )  # DEPRECATED: Use GaraByeChallenge.gara_id instead
    round_number = db.Column(
        db.Integer, nullable=True
    )  # DEPRECATED: Use GaraByeChallenge.round_number instead

    # Relationships
    challenge = db.relationship("Challenge", back_populates="attempts")
    user = db.relationship("User")
    gara = db.relationship("Gara")  # DEPRECATED: Use GaraByeChallenge.gara instead
    variant = db.relationship("ChallengeVariant")

    def complete_attempt(
        self, score: Optional[int] = None, passed: Optional[bool] = None
    ) -> None:
        """
        Completa il Tentativo con Punteggio/Risultato

        Metodo principale per finalizzare un tentativo, gestendo correttamente
        la logica di scoring basata sul tipo di sfida (numerica vs pass/fail).

        Args:
            score: Punteggio numerico (richiesto per sfide numeriche)
            passed: Risultato pass/fail (richiesto solo per sfide pass/fail)

        Business Logic Post-Refactor:
        - Sfide pass/fail: imposta 'passed' esplicitamente, score = 1/0
          per rappresentazione
        - Sfide numeriche: registra solo score, 'passed' rimane None (non applicabile)
        - Rimossa logica automatica di determinazione pass/fail al 70%

        Raises:
            ValueError: Se parametri non corrispondono al tipo di sfida
        """
        self.completed = True
        self.attempted_at = utc_now()

        if self.challenge.pass_fail_only:
            # Sfide Pass/Fail Esplicite:
            # - Campo 'passed' deve essere impostato esplicitamente
            # - Score è rappresentazione numerica: 1=pass, 0=fail
            if passed is None:
                raise ValueError("Parametro 'passed' richiesto per sfide pass/fail")
            self.passed = passed
            self.score = 1 if passed else 0  # Rappresentazione numerica semplice
        else:
            # Sfide Numeriche:
            # - Solo punteggio numerico è rilevante
            # - Campo 'passed' rimane None (concetto non applicabile)
            # - IMPORTANTE: No auto-determinazione pass/fail (rimossa logica 70%)
            if score is None:
                raise ValueError("Parametro 'score' richiesto per sfide numeriche")
            self.score = score
            self.passed = None  # Esplicitamente None per sfide numeriche

    def __repr__(self) -> str:
        """Rappresentazione stringa per debugging e logging."""
        status = "completed" if self.completed else "pending"
        return (
            f"<ChallengeAttempt {self.user_id} -> "
            f"Challenge#{self.challenge_id}: {self.score} ({status})>"
        )


class ChallengeFavorite(BaseModel):
    """
    Entità ChallengeFavorite - Sistema Preferiti Utente

    Gestisce le sfide preferite degli utenti per accesso rapido e
    personalizzazione dell'esperienza comunitaria.

    Funzionalità Community:
    - Accesso rapido alle sfide più utilizzate
    - Personalizzazione dashboard giocatore
    - Tracking preferenze per raccomandazioni
    - Sistema sociale di condivisione sfide popolari

    Business Rules:
    - Un utente può aggiungere una sfida ai preferiti solo una volta
    - Constraint unico su (challenge_id, user_id)
    - Rimozione automatica se sfida o utente vengono eliminati
    - Timestamp per tracking evoluzione preferenze
    """

    __tablename__ = "challenge_favorite"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    favorited_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    # Relazioni per navigazione dominio
    challenge = db.relationship("Challenge", back_populates="favorites")
    user = db.relationship("User")  # Utente proprietario dei preferiti

    # Vincolo di unicità: un utente può aggiungere una sfida ai preferiti solo una volta
    # Previene duplicati e garantisce integrità sistema preferiti
    __table_args__ = (
        db.UniqueConstraint("challenge_id", "user_id", name="uq_challenge_favorite"),
    )

    def __repr__(self) -> str:
        """Rappresentazione stringa per debugging e logging sistema preferiti."""
        return (
            f"<ChallengeFavorite User#{self.user_id} -> Challenge#{self.challenge_id}>"
        )


class ChallengeCategory(BaseModel):
    """Una voce di vocabolario attaccata a un esercizio (ADR-065).

    Una tabella sola per i due assi, con `axis` a dire quale: abilita' e gesto
    hanno la stessa forma (esercizio → voce) e la stessa vita, e due tabelle
    gemelle sarebbero due posti da tenere allineati a ogni ritocco.

    `value` e' il **valore** dell'enum (`Abilita`/`Gesto`), in una colonna
    `String`: il vocabolario vive nel codice, dove si traduce, e qui resta solo
    l'associazione.
    """

    __tablename__ = "challenge_category"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="CASCADE"), nullable=False
    )
    axis = db.Column(db.String(20), nullable=False)
    value = db.Column(db.String(30), nullable=False)

    challenge = db.relationship("Challenge", back_populates="categories")

    __table_args__ = (
        db.UniqueConstraint(
            "challenge_id", "axis", "value", name="uq_challenge_category"
        ),
        db.Index("ix_challenge_category_axis_value", "axis", "value"),
    )

    def __repr__(self) -> str:  # pragma: no cover - banale
        return f"<ChallengeCategory #{self.challenge_id} {self.axis}={self.value}>"


class ChallengeVariant(BaseModel):
    """Una variante etichettata di **uno stesso** esercizio: dx/sx, A/B.

    Non e' un secondo esercizio: disegno, istruzioni, profilo e voto sono
    quelli del padre. Cambia solo da che parte ci si mette, e le prove si
    registrano separate (`ChallengeAttempt.variant_id`) perche' il 9 su 10 di
    destra e il 4 su 10 di sinistra sono la notizia, non la loro media.

    Le etichette sono N, libere dell'autore: due bastano quasi sempre, ma
    niente nel modello lo presume.
    """

    __tablename__ = "challenge_variant"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="CASCADE"), nullable=False
    )
    label = db.Column(db.String(40), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=1)

    challenge = db.relationship("Challenge", back_populates="variants")

    __table_args__ = (
        db.UniqueConstraint("challenge_id", "label", name="uq_challenge_variant"),
    )

    def __repr__(self) -> str:  # pragma: no cover - banale
        return f"<ChallengeVariant #{self.challenge_id} {self.label!r}>"


class ChallengeRating(BaseModel):
    """Il voto di un giocatore a un esercizio, da 1 a 5 (ADR-065, D6).

    Un voto per giocatore per esercizio: rivotare **sostituisce**. L'unicita'
    sta nello schema e non in un `if`, perche' `UserMergeService` decide dallo
    schema come spostare le righe quando due account si fondono.
    """

    __tablename__ = "challenge_rating"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    rating = db.Column(db.Integer, nullable=False)

    challenge = db.relationship("Challenge", back_populates="ratings")
    user = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("challenge_id", "user_id", name="uq_challenge_rating"),
        db.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_challenge_rating_range"),
    )

    def __repr__(self) -> str:  # pragma: no cover - banale
        return (
            f"<ChallengeRating User#{self.user_id} -> "
            f"Challenge#{self.challenge_id}: {self.rating}>"
        )
