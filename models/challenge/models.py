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

from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING

from sqlalchemy import desc

from ..base import db, BaseModel, TimestampMixin

if TYPE_CHECKING:
    pass


class Challenge(BaseModel, TimestampMixin):
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
    description = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=False)

    # Configurazione Scoring - determina il tipo di valutazione della sfida
    pass_fail_only = db.Column(db.Boolean, nullable=False, default=False)
    # False: sfida numerica (punteggio 0-N), True: sfida pass/fail

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
        attempts_query = self.attempts.filter_by(completed=True)

        total_attempts = attempts_query.count()
        unique_players = (
            attempts_query.with_entities(ChallengeAttempt.user_id).distinct().count()
        )

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
        scores = [attempt.score for attempt in attempts_query.all()]
        average_score = sum(scores) / len(scores)
        median_score = sorted(scores)[len(scores) // 2]
        max_score_achieved = max(scores)
        perfect_score_count = sum(1 for score in scores if score == max_score_achieved)

        # Calcolo pass_rate basato sul tipo di sfida
        if self.pass_fail_only:
            # Solo per sfide pass/fail esplicite: calcola percentuale di superamento
            # Utilizza il campo 'passed' che è esplicitamente impostato per queste sfide
            pass_rate = (
                sum(1 for attempt in attempts_query if attempt.passed)
                / total_attempts
                * 100
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
        """
        Genera Nome Display Breve per Interfaccia Utente

        Crea una versione abbreviata della descrizione per l'utilizzo
        in liste, tabelle e componenti UI con spazio limitato.

        Returns:
            Descrizione troncata a 50 caratteri con '...' se necessario
        """
        short_desc = (
            self.description[:50] + "..."
            if len(self.description) > 50
            else self.description
        )
        return short_desc

    @property
    def image_filename(self) -> Optional[str]:
        """
        Estrae Nome File Immagine per Utilizzo nei Template

        Estrae solo il nome del file dal percorso completo dell'immagine
        per l'utilizzo nei template Jinja2 e nei componenti UI.

        Returns:
            Nome file (es. 'challenge_001.jpg') o None se nessun percorso

        Template Usage:
            <img src="{{ url_for('static', filename='challenges/' + challenge.img_filename) }}">
        """
        if self.image_path:
            return self.image_path.split("/")[-1]
        return None

    def __repr__(self) -> str:
        return f"<Challenge #{self.id}: {self.get_display_name()}>"


class ChallengeAttempt(BaseModel, TimestampMixin):
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
    passed = db.Column(db.Boolean, nullable=True)  # Solo per sfide pass/fail, None per numeriche
    completed = db.Column(db.Boolean, nullable=False, default=False)  # Stato completamento
    attempted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)  # Timestamp tentativo

    # Note opzionali sul tentativo (condizioni particolari, osservazioni)
    notes = db.Column(db.Text, nullable=True)

    # Integrazione Campionati - quando usato come sostituzione X
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="SET NULL"), nullable=True
    )  # Gara di appartenenza se usato come X
    round_number = db.Column(db.Integer, nullable=True)  # Turno specifico della gara

    # Relationships
    challenge = db.relationship("Challenge", back_populates="attempts")
    user = db.relationship("User")
    gara = db.relationship("Gara")

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
        - Sfide pass/fail: imposta 'passed' esplicitamente, score = 1/0 per rappresentazione
        - Sfide numeriche: registra solo score, 'passed' rimane None (non applicabile)
        - Rimossa logica automatica di determinazione pass/fail al 70%

        Raises:
            ValueError: Se parametri non corrispondono al tipo di sfida
        """
        self.completed = True
        self.attempted_at = datetime.utcnow()

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
    favorited_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

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
        return f"<ChallengeFavorite User#{self.user_id} -> Challenge#{self.challenge_id}>"
