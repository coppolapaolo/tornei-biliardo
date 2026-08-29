"""
Module: models/challenge/services.py
Purpose: Challenge domain services for business logic
Requirements: SPECIFICHE.md - Challenge management and statistics
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any
from flask_babel import gettext as _
from sqlalchemy import desc

from ..base import db
from ..exceptions import NotFoundError, ValidationError
from ..transaction.manager import transactional
from .events import DrillOrigin
from .models import Challenge, ChallengeAttempt, ChallengeFavorite

logger = logging.getLogger(__name__)


class ChallengeService:
    """Service per la gestione delle sfide (challenges) e business logic.

    Gestisce il sistema di sfide individuali per l'allenamento e valutazione
    delle competenze dei giocatori, incluso:
    - CRUD operations per sfide
    - Sistema dei preferiti per i giocatori
    - Integrazione X-replacement per sostituzioni in campionato
    - Statistiche e cronologia tentativi
    """

    @staticmethod
    @transactional(domain="challenge")
    def create_challenge(
        description: str,
        image_path: str,
        pass_fail_only: bool = False,
        created_by_id: Optional[int] = None,
        diagram_scene: Optional[str] = None,
        title: Optional[str] = None,
        max_score: Optional[int] = None,
    ) -> Challenge:
        """Crea una nuova sfida nel sistema.

        Args:
            description: Descrizione della sfida e istruzioni per il giocatore
            image_path: Percorso all'immagine che illustra la sfida
            pass_fail_only: True se pass/fail, False se punteggio numerico
            created_by_id: ID del direttore/admin che ha creato la sfida (opzionale)
            diagram_scene: la scena del builder in JSON, se il drill e' stato
                disegnato invece che fotografato. ``None`` per le foto, ed e'
                cio' che dice se il disegno si potra' riaprire
            title: nome del drill. Facoltativo: senza, il drill si chiama col
                suo progressivo (``Drill 12``). La stringa vuota vale None —
                un titolo di soli spazi non e' un titolo
            max_score: punteggio massimo ottenibile. Facoltativo, e vietato
                sugli esercizi superato/non superato

        Returns:
            Challenge: L'oggetto sfida creato e persistito nel database

        Raises:
            ValidationError: max_score incoerente col tipo di esercizio
        """
        max_score = ChallengeService._validate_max_score(max_score, pass_fail_only)

        challenge = Challenge(
            title=(title or "").strip() or None,
            description=description,
            pass_fail_only=pass_fail_only,
            image_path=image_path,
            created_by_id=created_by_id,
            diagram_scene=diagram_scene,
            max_score=max_score,
        )

        db.session.add(challenge)
        return challenge

    @staticmethod
    @transactional(domain="challenge")
    def update_challenge(
        challenge_id: int,
        description: Optional[str] = None,
        image_path: Optional[str] = None,
        pass_fail_only: Optional[bool] = None,
        is_active: Optional[bool] = None,
        diagram_scene: Optional[str] = None,
        title: Optional[str] = None,
        max_score: Optional[int] = None,
        clear_max_score: bool = False,
    ) -> Challenge:
        """Aggiorna una sfida esistente con validazione.

        Args:
            challenge_id: ID della sfida da modificare
            description: Nuova descrizione (mantiene esistente se None)
            image_path: Nuovo percorso immagine (mantiene esistente se None)
            pass_fail_only: Nuovo tipo di scoring (mantiene esistente se None)
            is_active: Nuovo stato attivo/inattivo (mantiene esistente se None)
            diagram_scene: Nuova scena del builder (mantiene esistente se None)
            title: nuovo titolo. ``None`` non tocca niente — il campo non e'
                stato inviato; la **stringa vuota** invece toglie il titolo, ed
                e' quello che arriva da chi svuota la casella nel modulo. Senza
                questa distinzione un titolo, una volta messo, non si potrebbe
                piu' togliere

        Returns:
            Challenge: L'oggetto sfida aggiornato

        Raises:
            404: Se la sfida non esiste
        """
        challenge = db.session.get(Challenge, challenge_id)
        if not challenge:
            raise ValueError("Challenge non trovata")

        # Aggiorna solo i campi specificati (pattern partial update)
        if title is not None:
            challenge.title = title.strip() or None
        if description is not None:
            challenge.description = description
        if image_path is not None:
            challenge.image_path = image_path
        if diagram_scene is not None:
            challenge.diagram_scene = diagram_scene
        if pass_fail_only is not None:
            challenge.pass_fail_only = pass_fail_only
        if is_active is not None:
            challenge.is_active = is_active

        # Il tetto si toglie **solo** su richiesta esplicita: `None` qui vuol
        # dire «campo non inviato», non «azzera». Senza `clear_max_score` una
        # qualsiasi modifica parziale — cambiare il titolo dal builder —
        # cancellerebbe in silenzio il massimo gia' impostato.
        if clear_max_score:
            challenge.max_score = None
        elif max_score is not None:
            challenge.max_score = ChallengeService._validate_max_score(
                max_score, challenge.pass_fail_only
            )

        # Un esercizio che diventa superato/non superato non puo' tenersi un
        # tetto di punteggio: resterebbe scritto da qualche parte senza piu'
        # nessuno che lo legge, pronto a ricomparire se un domani torna a
        # punteggio con un valore che nessuno ha piu' scelto.
        if challenge.pass_fail_only:
            challenge.max_score = None

        return challenge

    @staticmethod
    def _validate_score_against_max(challenge: Challenge, score: int) -> None:
        """Un punteggio non puo' superare il tetto dichiarato dall'esercizio.

        Rifiutare qui e non a schermo: la schermata di allenamento limita gia'
        il tastierino, ma la POST la puo' fare chiunque, e un 40 su una prova
        che arriva a 15 falserebbe per sempre il record personale e la
        classifica dell'esercizio, senza che niente segnali l'anomalia.

        Un esercizio **senza** tetto (``max_score`` a NULL) non ha nulla da
        verificare: e' il caso normale, ed e' una scelta, non un dato mancante.
        """
        if score is None or challenge.max_score is None:
            return
        if score > challenge.max_score:
            raise ValidationError(
                f"Il punteggio massimo di questo esercizio è " f"{challenge.max_score}"
            )
        if score < 0:
            raise ValidationError("Il punteggio non può essere negativo")

    @staticmethod
    def _validate_max_score(
        max_score: Optional[int], pass_fail_only: bool
    ) -> Optional[int]:
        """Il tetto di punteggio e' facoltativo, ma non arbitrario.

        ``None`` resta ``None``: dice «questo esercizio non ha un tetto», ed e'
        una risposta legittima — ci sono prove che si ripetono finche' non si
        sbaglia. Quello che non e' legittimo e' un tetto su un esercizio
        superato/non superato (li' il punteggio e' la rappresentazione 1/0
        dell'esito, non una misura) o un tetto a zero, che renderebbe l'unico
        punteggio ammesso lo zero.
        """
        if max_score is None:
            return None
        if pass_fail_only:
            raise ValidationError(
                "Un esercizio superato/non superato non ha un punteggio massimo"
            )
        try:
            valore = int(max_score)
        except (TypeError, ValueError):
            raise ValidationError("Il punteggio massimo deve essere un numero")
        if valore <= 0:
            raise ValidationError("Il punteggio massimo deve essere maggiore di zero")
        return valore

    @staticmethod
    def get_all_challenges() -> List[Challenge]:
        """Recupera tutte le sfide (incluse quelle inattive) - solo per admin."""
        return db.session.query(Challenge).all()

    @staticmethod
    def get_active_challenges() -> List[Challenge]:
        """Recupera solo le sfide attive visibili ai giocatori."""
        return db.session.query(Challenge).filter_by(is_active=True).all()

    @staticmethod
    def get_user_challenges(user_id: int) -> Dict[str, List[Challenge]]:
        """Organizza sfide attive per relazione con l'utente specificato.

        Args:
            user_id: ID del giocatore per cui organizzare le sfide

        Returns:
            Dict con chiavi:
            - 'favorites': Sfide contrassegnate come preferite dall'utente
            - 'attempted': Sfide già tentate dall'utente (con cronologia)
            - 'general': Sfide mai tentate dall'utente (catalogo generale)
        """
        # Recupera solo sfide attive per evitare confusione
        all_challenges = ChallengeService.get_active_challenges()

        # Identifica preferiti dell'utente tramite relazione ChallengeFavorite
        favorite_ids = {
            fav.challenge_id
            for fav in db.session.query(ChallengeFavorite)
            .filter_by(user_id=user_id)
            .all()
        }
        favorites = [c for c in all_challenges if c.id in favorite_ids]

        # Identifica sfide già tentate dall'utente (cronologia)
        attempted_ids = {
            att.challenge_id
            for att in db.session.query(ChallengeAttempt)
            .filter_by(user_id=user_id)
            .all()
        }
        attempted = [c for c in all_challenges if c.id in attempted_ids]

        # Catalogo generale: sfide non ancora tentate dall'utente
        general = [c for c in all_challenges if c.id not in attempted_ids]

        return {"favorites": favorites, "attempted": attempted, "general": general}

    @staticmethod
    def get_catalog_data(user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get complete data structure for challenge catalog (active only)."""
        # Everyone sees only active challenges
        all_challenges = ChallengeService.get_active_challenges()

        result = {
            "all_challenges": all_challenges,
            "my_challenges": [],
            "favorite_challenges": [],
            "user_favorites": set(),
        }

        if user_id:
            # Get user's created active challenges
            my_challenges = (
                db.session.query(Challenge)
                .filter_by(created_by_id=user_id, is_active=True)
                .all()
            )
            result["my_challenges"] = my_challenges

            # Get user's favorites (only from active challenges)
            favorite_ids = {
                fav.challenge_id
                for fav in db.session.query(ChallengeFavorite)
                .filter_by(user_id=user_id)
                .all()
            }
            result["user_favorites"] = favorite_ids
            result["favorite_challenges"] = [
                c for c in all_challenges if c.id in favorite_ids
            ]

        return result

    @staticmethod
    @transactional(domain="challenge")
    def start_challenge_attempt(
        user_id: int,
        challenge_id: int,
        gara_id: Optional[int] = None,
        round_number: Optional[int] = None,
    ) -> ChallengeAttempt:
        """Start a new challenge attempt.

        If gara_id is provided, also creates a GaraByeChallenge entry to track
        the relationship (Competition → Challenge direction).
        """
        attempt = ChallengeAttempt(
            user_id=user_id,
            challenge_id=challenge_id,
            gara_id=gara_id,  # DEPRECATED: kept for backward compatibility
            round_number=round_number,  # DEPRECATED: kept for backward compatibility
        )

        db.session.add(attempt)
        db.session.flush()  # Get attempt.id before creating GaraByeChallenge

        # Create GaraByeChallenge entry for bye replacement (new pattern)
        if gara_id is not None and round_number is not None:
            from models.competition.gara_bye_challenge import GaraByeChallenge

            bye_challenge = GaraByeChallenge.create_for_bye(
                gara_id=gara_id,
                user_id=user_id,
                round_number=round_number,
            )
            bye_challenge.challenge_attempt_id = attempt.id
            db.session.add(bye_challenge)

        return attempt

    @staticmethod
    @transactional(domain="challenge")
    def complete_challenge_attempt(
        attempt_id: int,
        score: Optional[int] = None,
        passed: Optional[bool] = None,
        notes: Optional[str] = None,
    ) -> ChallengeAttempt:
        """Complete a challenge attempt with results."""
        attempt = db.session.get(ChallengeAttempt, attempt_id)
        if not attempt:
            raise ValueError("Tentativo challenge non trovato")

        attempt.complete_attempt(score=score, passed=passed)
        if notes:
            attempt.notes = notes

        # Gamification: completare un drill può sbloccare achievement
        # (challenge_master, drill_addict, perfectionist). Cross-dominio con
        # errori isolati — un fallimento gamification non blocca il drill.
        try:
            from models.gamification.achievement_service import AchievementService

            AchievementService.reconcile_achievements(attempt.user_id)
        except Exception:
            pass

        ChallengeService._publish_attempt_completed(attempt, DrillOrigin.CATALOG)

        return attempt

    @staticmethod
    @transactional(domain="challenge")
    def delete_attempt(
        attempt_id: int, actor_id: int, actor_is_admin: bool = False
    ) -> int:
        """Cancella una prova sbagliata, e disfa quello che aveva prodotto.

        **Perche' si puo' cancellare.** Una prova si registra in un gesto solo,
        col telefono in mano, mentre si gioca: il tasto sbagliato si preme, e
        senza una via d'uscita l'unico rimedio sarebbe falsare il resto per
        compensare. Vale sia per l'«annulla» della schermata di allenamento sia
        per lo storico del profilo, che sono lo stesso bisogno a due distanze.

        **Perche' l'XP torna indietro.** Il completamento aveva pagato XP
        (``handle_challenge_attempt_completed_for_xp``). Cancellare la riga
        senza restituirlo lascerebbe un modo banale di guadagnare livelli:
        registra, annulla, ripeti. La restituzione e' una **transazione
        compensativa** — un movimento negativo, non la cancellazione del
        movimento originale — cosi' il registro racconta quello che e'
        successo davvero invece di far finta che non sia successo niente.

        Due conseguenze restano volutamente in piedi:

        - la **serie settimanale**: dice «questa settimana ti sei allenato», e
          una prova annullata per un tasto sbagliato non cambia il fatto che
          quella sera eri al tavolo;
        - i **traguardi gia' sbloccati**: si riconciliano da soli al prossimo
          giro, e togliere un traguardo a chi l'ha visto comparire e' una
          punizione sproporzionata per un errore di battitura.

        Returns:
            L'id dell'esercizio a cui la prova apparteneva.

        Raises:
            NotFoundError: la prova non esiste
            PermissionDeniedError: non e' la prova di chi la sta cancellando
        """
        from ..exceptions import PermissionDeniedError

        attempt = db.session.get(ChallengeAttempt, attempt_id)
        if attempt is None:
            raise NotFoundError("Prova non trovata")
        if attempt.user_id != actor_id and not actor_is_admin:
            raise PermissionDeniedError("Questa prova non è tua")

        challenge_id = attempt.challenge_id
        user_id = attempt.user_id
        ChallengeService._refund_xp_for_attempt(attempt)
        db.session.delete(attempt)
        db.session.flush()  # la riga deve essere sparita PRIMA del ricalcolo
        ChallengeService._recompute_after_removal(user_id)
        return challenge_id

    @staticmethod
    def _recompute_after_removal(user_id: int) -> None:
        """Rimette in riga serie settimanali e traguardi dopo la prova tolta.

        **Ricalcola, non sottrae**: se altri esercizi reggono comunque la serie
        o il traguardo, non cambia niente. Chi si allena tutti i giorni non deve
        perdere la serie per un tocco sbagliato.

        Best-effort come il resto del ponte con la gamification, e per la stessa
        ragione: il dato sbagliato tolto vale piu' di un contatore perfetto. Se
        qui esplode qualcosa, la prova resta cancellata e l'errore resta nel log.
        """
        try:
            from models.gamification.recalc_service import GamificationRecalcService

            GamificationRecalcService.recompute_after_drill_removed(user_id)
        except Exception:
            logger.warning(
                "Ricalcolo di serie e traguardi non riuscito per l'utente %s",
                user_id,
                exc_info=True,
            )

    @staticmethod
    def _refund_xp_for_attempt(attempt: ChallengeAttempt) -> None:
        """Restituisce l'XP pagato per questa prova, se era stato pagato.

        Best-effort come il resto del ponte con la gamification: se la
        restituzione fallisce, la cancellazione va avanti lo stesso — il dato
        sbagliato tolto vale piu' di un saldo XP perfetto, e resta nel log.

        Non tutte le prove hanno pagato: in gara pagano solo le prime del
        turno (i tentativi successivi sono lo stesso drill, riprovato). Per
        questo si cerca il movimento invece di dedurne l'importo: se non c'e',
        non c'e' niente da rendere.
        """
        try:
            import json

            from models.gamification.level_service import LevelService
            from models.gamification.models import XPTransaction, XPTransactionType

            movimenti = (
                XPTransaction.query.filter(
                    XPTransaction.user_id == attempt.user_id,
                    XPTransaction.transaction_type
                    == XPTransactionType.CHALLENGE_COMPLETION,
                    XPTransaction.related_entities.isnot(None),
                )
                .order_by(XPTransaction.id.desc())
                .limit(200)
                .all()
            )
            for movimento in movimenti:
                try:
                    legami = json.loads(movimento.related_entities or "{}")
                except ValueError:
                    continue
                if legami.get("challenge_attempt_id") != attempt.id:
                    continue
                if movimento.xp_amount <= 0:
                    return  # gia' restituito: non si rende due volte
                LevelService.award_xp(
                    user_id=attempt.user_id,
                    xp_amount=-movimento.xp_amount,
                    transaction_type=XPTransactionType.CHALLENGE_COMPLETION,
                    reason="Prova annullata",
                    related_entities={
                        "challenge_id": attempt.challenge_id,
                        "challenge_attempt_id": attempt.id,
                        "refund_of": movimento.id,
                    },
                )
                return
        except Exception:
            logger.warning(
                "Restituzione XP non riuscita per la prova %s",
                attempt.id,
                exc_info=True,
            )

    @staticmethod
    def _publish_attempt_completed(
        attempt: ChallengeAttempt,
        origin: "DrillOrigin",
        attempt_number: int = 1,
        gara_id: Optional[int] = None,
    ) -> None:
        """Annuncia che un drill è stato completato (XP, streak).

        Best-effort come le notifiche: un ascoltatore che esplode non deve far
        perdere il punteggio appena registrato, che è il dato importante.
        """
        from models.events.base import EventBus

        from .events import ChallengeAttemptCompletedEvent

        try:
            challenge = attempt.challenge or db.session.get(
                Challenge, attempt.challenge_id
            )
            EventBus.publish(
                ChallengeAttemptCompletedEvent(
                    attempt_id=attempt.id,
                    challenge_id=attempt.challenge_id,
                    challenge_name=(challenge.get_display_name() if challenge else ""),
                    user_id=attempt.user_id,
                    origin=origin.value,
                    score=attempt.score,
                    passed=attempt.passed,
                    gara_id=gara_id,
                    attempt_number=attempt_number,
                )
            )
        except Exception:  # pragma: no cover - la gamification non blocca mai
            logger.warning("Evento di drill completato non pubblicato", exc_info=True)

    @staticmethod
    @transactional(domain="challenge")
    def toggle_favorite(user_id: int, challenge_id: int) -> bool:
        """Toggle challenge as favorite. Returns True if added, False if removed."""
        favorite = (
            db.session.query(ChallengeFavorite)
            .filter_by(user_id=user_id, challenge_id=challenge_id)
            .first()
        )

        if favorite:
            db.session.delete(favorite)
            return False
        else:
            favorite = ChallengeFavorite(user_id=user_id, challenge_id=challenge_id)
            db.session.add(favorite)
            return True

    @staticmethod
    def get_challenges_for_x_choice() -> List[Challenge]:
        """Gli esercizi che si possono offrire per la X, in ordine di nome.

        Il criterio e' quello del ripiego automatico — attivi e **a punteggio**
        — e sta qui una volta sola: il punteggio della X e' una differenza
        triangoli, che un esercizio superato/non superato non produce. Due copie
        di questo filtro sarebbero due copie destinate a divergere, e la
        divergenza si vedrebbe solo il giorno in cui un direttore sceglie un
        esercizio che poi il motore rifiuta.
        """
        return (
            db.session.query(Challenge)
            .filter_by(is_active=True, pass_fail_only=False)
            .order_by(Challenge.title, Challenge.id)
            .all()
        )

    @staticmethod
    def get_challenge_for_x_replacement(gara_id: int) -> Optional[Challenge]:
        """Seleziona una sfida appropriata per sostituzione X in campionato.

        L'algoritmo di selezione implementa una strategia di equità:
        1. Filtra sfide attive con punteggio numerico (no pass/fail only)
        2. Conta utilizzi precedenti nella stessa gara
        3. Preferisce sfide meno utilizzate per bilanciamento

        Args:
            gara_id: ID della gara per cui trovare la sfida sostitutiva

        Returns:
            Challenge: Sfida selezionata, None se nessuna disponibile

        Note:
            X-replacement: quando un giocatore ha 'bye' può fare una sfida
            invece di riposare, per mantenere attivo l'allenamento.
        """
        # La scelta del direttore vince (issue #267). Sta sulla gara e non sul
        # turno: a numero dispari riposa una persona diversa a ogni turno, e un
        # esercizio che cambia renderebbe le prove di due giocatori non
        # confrontabili pur finendo nella stessa classifica.
        #
        # I due filtri del ripiego valgono anche qui: un esercizio disattivato o
        # a esito booleano non torna utilizzabile solo perche' l'ha scelto
        # qualcuno — sul secondo il punteggio della X e' una differenza
        # triangoli, che un superato/non superato non produce. Quando la scelta
        # non e' piu' valida si ricade sul ripiego: meglio un esercizio diverso
        # che una X che non si puo' giocare.
        from models.competition.models import Gara

        gara = db.session.get(Gara, gara_id)
        if gara is not None and gara.x_challenge_id:
            # `scelto is None` non e' paranoia: su uno schema costruito dal
            # modello la chiave esterna c'e' e un id orfano non si scrive, ma in
            # produzione la colonna nasce da un `ALTER TABLE ADD COLUMN`, che in
            # SQLite non puo' creare vincoli. Le due meta' del mondo hanno
            # schemi diversi, e questo ramo copre quella senza vincolo.
            scelto = db.session.get(Challenge, gara.x_challenge_id)
            if scelto is not None and scelto.is_active and not scelto.pass_fail_only:
                return scelto

        # Criteri per X-replacement: attive e con scoring numerico (no pass/fail)
        suitable_challenges = (
            db.session.query(Challenge)
            .filter_by(is_active=True, pass_fail_only=False)
            .all()
        )

        if not suitable_challenges:
            return None

        # Algoritmo equità: conta utilizzi per gara per bilanciare le sfide
        challenge_usage = {}
        for challenge in suitable_challenges:
            usage_count = (
                db.session.query(ChallengeAttempt)
                .filter_by(challenge_id=challenge.id, gara_id=gara_id)
                .count()
            )
            challenge_usage[challenge.id] = usage_count

        # Selezione: sfida con minor numero di utilizzi nella gara corrente
        min_usage = min(challenge_usage.values())
        for challenge in suitable_challenges:
            if challenge_usage[challenge.id] == min_usage:
                return challenge

        return suitable_challenges[0]  # Fallback se tutte hanno stesso utilizzo

    @staticmethod
    def create_x_replacement_attempt(
        user_id: int,
        gara_id: int,
        round_number: int,
        challenge_id: Optional[int] = None,
    ) -> ChallengeAttempt:
        """Create a challenge attempt to replace X in campionato.

        Authz: l'utente deve avere DAVVERO un bye in (gara_id, round_number).
        Il bye è materializzato da round-creation come un Match(is_bye=True,
        player1_id=user_id). Senza questa verifica un qualsiasi utente loggato
        potrebbe fabbricare un bye (e quindi una vittoria in classifica) per
        una gara/turno a cui non ha titolo (IDOR a livello service).
        """
        from ..match.models import Match
        from ..exceptions import PermissionDeniedError

        has_bye = (
            db.session.query(Match.id)
            .filter_by(
                gara_id=gara_id,
                round_number=round_number,
                player1_id=user_id,
                is_bye=True,
            )
            .first()
            is not None
        )
        if not has_bye:
            raise PermissionDeniedError(
                "Nessun bye da sostituire per questo utente in questo turno"
            )

        final_challenge_id: int
        if challenge_id is None:
            challenge = ChallengeService.get_challenge_for_x_replacement(gara_id)
            if not challenge:
                raise ValueError("No suitable challenge available for X replacement")
            final_challenge_id = challenge.id
        else:
            final_challenge_id = challenge_id

        attempt = ChallengeService.start_challenge_attempt(
            user_id=user_id,
            challenge_id=final_challenge_id,
            gara_id=gara_id,
            round_number=round_number,
        )

        return attempt

    @staticmethod
    def complete_x_replacement_attempt(
        attempt_id: int, score: int, notes: Optional[str] = None
    ) -> ChallengeAttempt:
        """Complete X replacement challenge and return match-equivalent result."""
        from models.competition.gara_bye_challenge import GaraByeChallenge

        attempt = db.session.get(ChallengeAttempt, attempt_id)
        if not attempt:
            raise ValueError("Tentativo challenge non trovato")

        # Mark GaraByeChallenge as completed (new pattern)
        bye_challenge = GaraByeChallenge.query.filter_by(
            challenge_attempt_id=attempt_id
        ).first()

        # Il punteggio va verificato PRIMA di scriverlo: è il giocatore stesso
        # a dichiararlo, e senza un limite superiore un valore fuori scala
        # finirebbe dritto in classifica (SPECIFICHE.md riga 65).
        limite = ChallengeService._limite_punteggio_x(
            gara_id=(bye_challenge.gara_id if bye_challenge else attempt.gara_id),
            round_number=(
                bye_challenge.round_number if bye_challenge else attempt.round_number
            ),
            user_id=attempt.user_id,
        )
        if limite is not None and not 0 <= score <= limite:
            raise ValidationError(
                _(
                    "Il punteggio della prova deve essere compreso fra 0 e "
                    "%(massimo)s, la differenza più ampia ottenibile in questo "
                    "turno.",
                    massimo=limite,
                )
            )

        # Complete the attempt
        attempt.complete_attempt(score=score, passed=None)

        # Set notes separately if provided
        if notes:
            attempt.notes = notes

        if bye_challenge:
            bye_challenge.complete_with_attempt(attempt_id)

        # Il punteggio **non** arriva ancora sul match: lo porta li' la
        # validazione del direttore (`validate_x_replacement`). A dichiararlo e'
        # il giocatore stesso, e a differenza di una partita non c'e' un
        # avversario che possa smentirlo — la doppia conferma, qui, non esiste
        # per costruzione. Finche' nessuno valida, la prova e' giocata e non
        # conta, che e' uno stato legittimo e non un dato mancante.

        # Il drill giocato al posto di un match resta un drill: vale per
        # l'abitudine settimanale come qualunque altro. Il bye equivalente non
        # pubblica `MatchCompletedEvent` (il Match nasce già completed, senza
        # passare dal servizio), quindi qui non si paga niente due volte.
        ChallengeService._publish_attempt_completed(
            attempt,
            DrillOrigin.GARA,
            gara_id=(bye_challenge.gara_id if bye_challenge else attempt.gara_id),
        )

        return attempt

    @staticmethod
    def _limite_punteggio_x(
        gara_id: Optional[int], round_number: Optional[int], user_id: int
    ) -> Optional[int]:
        """Quanto può valere al massimo la prova giocata al posto della X.

        `SPECIFICHE.md` riga 65: la prova dà «un punteggio da zero alla massima
        differenza rack raggiungibile in quella gara». La differenza più ampia
        è vincere senza concedere nulla, quindi il massimo è la distanza del
        turno.

        ADR-027: la distanza si legge dal match (`effective_distance`), non da
        `gara.distance` — altrimenti gli override per turno si perdono e in un
        turno «al 3» dentro una gara «al 5» si accetterebbero punteggi fino a 5.

        Restituisce `None` quando per quel turno non esiste (ancora) una
        partita con la X: non c'è scala su cui misurare, e un limite inventato
        sarebbe peggio di nessun limite.
        """
        from ..match.models import Match

        if not gara_id or not round_number:
            return None

        match = (
            db.session.query(Match)
            .filter_by(
                gara_id=gara_id,
                round_number=round_number,
                player1_id=user_id,
                is_bye=True,
            )
            .first()
        )
        return match.effective_distance if match else None

    @staticmethod
    def _ponte_x(gara_id: int, round_number: int, user_id: int):
        """Il ponte gara↔esercizio di quel giocatore in quel turno, se c'e'."""
        from models.competition.gara_bye_challenge import GaraByeChallenge

        return GaraByeChallenge.query.filter_by(
            gara_id=gara_id, round_number=round_number, user_id=user_id
        ).first()

    @staticmethod
    @transactional(domain="challenge")
    def validate_x_replacement(
        gara_id: int,
        round_number: int,
        user_id: int,
        actor_id: int,
        score: Optional[int] = None,
    ) -> "ChallengeAttempt":
        """Il direttore registra e valida la prova giocata al posto della X.

        Una sola operazione per due gesti che sono lo stesso: **confermare** il
        punteggio che il giocatore ha dichiarato, e **registrarlo** al posto suo
        quando non l'ha fatto — che nella pratica e' il caso frequente, perche'
        molti giocatori non usano l'applicazione ed e' il direttore a inserire
        per loro. Con `score` assente vale quello gia' dichiarato; con `score`
        presente lo corregge.

        Da qui, e solo da qui, il punteggio arriva sul match e quindi in
        classifica. E' il controllo che una partita ha nell'avversario e che una
        prova giocata da soli non puo' avere.
        """
        from models.competition.gara_bye_challenge import GaraByeChallenge

        ponte = ChallengeService._ponte_x(gara_id, round_number, user_id)
        attempt = (
            db.session.get(ChallengeAttempt, ponte.challenge_attempt_id)
            if ponte is not None and ponte.challenge_attempt_id
            else None
        )

        # Il direttore puo' arrivare qui prima del giocatore: se non c'e' nessun
        # tentativo lo apre lui. `create_x_replacement_attempt` verifica anche
        # che quel giocatore abbia davvero la X in quel turno, quindi la
        # protezione contro un id sbagliato vale anche per questa strada.
        if attempt is None:
            attempt = ChallengeService.create_x_replacement_attempt(
                user_id=user_id, gara_id=gara_id, round_number=round_number
            )
            ponte = ChallengeService._ponte_x(gara_id, round_number, user_id)

        punteggio = score if score is not None else attempt.score
        if punteggio is None:
            raise ValidationError(
                _("Serve un punteggio: la prova non ne ha ancora uno registrato.")
            )

        limite = ChallengeService._limite_punteggio_x(
            gara_id=gara_id, round_number=round_number, user_id=user_id
        )
        if limite is not None and not 0 <= punteggio <= limite:
            raise ValidationError(
                _(
                    "Il punteggio della prova deve essere compreso fra 0 e "
                    "%(massimo)s, la differenza più ampia ottenibile in questo "
                    "turno.",
                    massimo=limite,
                )
            )

        if attempt.score != punteggio or not attempt.completed:
            attempt.complete_attempt(score=punteggio, passed=None)

        if ponte is None:
            ponte = GaraByeChallenge.create_for_bye(
                gara_id=gara_id, user_id=user_id, round_number=round_number
            )
            db.session.add(ponte)
        ponte.complete_with_attempt(attempt.id)
        ponte.validate(actor_id)

        ChallengeService._create_x_replacement_match_result(attempt)
        return attempt

    @staticmethod
    @transactional(domain="challenge")
    def reset_x_replacement(gara_id: int, round_number: int, user_id: int) -> None:
        """Azzera la prova: il match torna a zero e l'esercizio torna da giocare.

        Il gemello di «annulla il risultato» sui match. Non cancella il
        tentativo — resta nello storico personale del giocatore, che quella
        prova l'ha giocata davvero — ma toglie la validazione e riporta il match
        al valore con cui era nato: zero, che e' quanto vale una X non
        sostituita (SPECIFICHE.md riga 64).
        """
        from ..match.models import Match

        ponte = ChallengeService._ponte_x(gara_id, round_number, user_id)
        if ponte is not None:
            ponte.clear_validation()

        match = (
            db.session.query(Match)
            .filter_by(
                gara_id=gara_id,
                round_number=round_number,
                player1_id=user_id,
                is_bye=True,
            )
            .first()
        )
        if match is not None:
            match.player1_score = 0
            match.player2_score = 0

    @staticmethod
    @transactional(domain="challenge")
    def _create_x_replacement_match_result(attempt: ChallengeAttempt) -> None:
        """Create a match result equivalent for X replacement challenge.

        Uses GaraByeChallenge to get gara context (Competition → Challenge direction).
        Falls back to attempt.gara_id for backward compatibility with existing data.
        """
        from ..match.models import Match
        from models.competition.gara_bye_challenge import GaraByeChallenge

        # Try to get gara context from GaraByeChallenge (new pattern)
        bye_challenge = GaraByeChallenge.query.filter_by(
            challenge_attempt_id=attempt.id
        ).first()

        if bye_challenge:
            gara_id = bye_challenge.gara_id
            round_number = bye_challenge.round_number
        else:
            # Backward compatibility: use deprecated attempt fields
            gara_id = attempt.gara_id
            round_number = attempt.round_number

        if not gara_id or not round_number:
            # Not an X replacement challenge, skip match creation
            return

        # Find or create a match for this X replacement
        match = (
            db.session.query(Match)
            .filter_by(
                gara_id=gara_id,
                round_number=round_number,
                player1_id=attempt.user_id,
                is_bye=True,
            )
            .first()
        )

        if not match:
            match = Match(
                gara_id=gara_id,
                round_number=round_number,
                player1_id=attempt.user_id,
                player2_id=None,
                is_bye=True,
                status="completed",
                winner_id=attempt.user_id,
            )
            db.session.add(match)
            db.session.flush()  # rende match.gara accessibile (effective_distance)

        # `SPECIFICHE.md` riga 65: chi gioca la prova al posto della X ottiene
        # «il match vinto e una differenza rack **pari al punteggio nella
        # challenge**». Il punteggio ci arriva già dentro la scala del turno —
        # `complete_x_replacement_attempt` rifiuta tutto ciò che esce da
        # [0, effective_distance] — quindi qui si usa così com'è.
        #
        # Fino al 2026-08-23 questa riga assegnava `effective_distance`,
        # scartando il punteggio: una difesa contro la scala arbitraria della
        # prova (es. 0-15 su una gara «al 5»), messa però nel posto sbagliato.
        # Difendersi qui significava appiattire ogni prova sullo stesso valore,
        # e quindi rendere la variante con challenge indistinguibile dalla X
        # secca — che è esattamente ciò che la riga 65 vuole evitare. Il
        # controllo sta ora dove il dato entra.
        match.player1_score = attempt.score or 0
        match.player2_score = 0  # X gets 0

    @staticmethod
    def get_admin_statistics() -> List[Dict[str, Any]]:
        """Get statistics for all challenges (admin view)."""
        challenges = Challenge.query.all()
        return [
            {"challenge": challenge, "stats": challenge.get_statistics()}
            for challenge in challenges
        ]

    @staticmethod
    def get_user_challenge_history(user_id: int) -> List[ChallengeAttempt]:
        """Get user's complete challenge attempt history."""
        return (
            ChallengeAttempt.query.filter_by(user_id=user_id, completed=True)
            .order_by(desc("attempted_at"))
            .all()
        )

    @staticmethod
    @transactional(domain="challenge")
    def delete_challenge(challenge_id: int) -> None:
        """Elimina una sfida con logica intelligente per preservare integrità dati.

        Strategia di eliminazione:
        - Hard delete: se mai utilizzata (no tentativi, no selezioni gara)
        - Soft delete: se utilizzata, marca is_active=False per nascondere

        Args:
            challenge_id: ID della sfida da eliminare

        Raises:
            404: Se la sfida non esiste

        Note:
            La soft delete preserva l'integrità referenziale per cronologie
            e statistiche esistenti, mentre nasconde la sfida dai cataloghi.
        """
        challenge = db.session.get(Challenge, challenge_id)
        if not challenge:
            raise ValueError("Challenge non trovata")

        # Verifica se la sfida ha tentativi registrati (cronologia)
        has_attempts = (
            db.session.query(ChallengeAttempt)
            .filter_by(challenge_id=challenge_id)
            .first()
            is not None
        )

        # Verifica se la sfida è stata selezionata in qualche gara
        # Controlla relazioni gara-challenge se il modello esiste
        has_gara_usage = False
        try:
            from models.competition.gara_challenge import GaraChallenge

            has_gara_usage = (
                db.session.query(GaraChallenge)
                .filter_by(challenge_id=challenge_id)
                .first()
                is not None
            )
        except ImportError:
            # Se non esiste relazione gara-challenge, salta questo controllo
            pass

        if not has_attempts and not has_gara_usage:
            # Hard delete: rimozione completa dal database (mai utilizzata)
            db.session.delete(challenge)
        else:
            # Soft delete: marca inattiva ma preserva per dati storici
            challenge.is_active = False

    @staticmethod
    def record_attempt(
        user_id: int,
        challenge_id: int,
        score: Optional[int] = None,
        passed: Optional[bool] = None,
        notes: Optional[str] = None,
        gara_id: Optional[int] = None,
        round_number: Optional[int] = None,
    ) -> ChallengeAttempt:
        """Registra una prova già conclusa: aprire e chiudere sono un gesto solo.

        Chi si allena non «apre un tentativo»: gioca, e dice com'è andata. La
        schermata di allenamento del catalogo passa di qui, così una prova
        costa **una** richiesta invece delle quattro del flusso a due pagine.

        La validazione sta **prima** della creazione, e non è pignoleria:
        ``start_challenge_attempt`` e ``complete_challenge_attempt`` sono due
        transazioni distinte, quindi un esito mancante scoperto solo dalla
        seconda lascerebbe a DB una riga ``completed=False`` che nessuno chiude
        più. Righe così non danno errore da nessuna parte: falsano in silenzio
        il conteggio dei drill completati, che è quello che apre i gate di
        gamification.

        Args:
            user_id: chi ha giocato
            challenge_id: il drill provato
            score: punteggio ottenuto — richiesto sui drill numerici
            passed: esito — richiesto sui drill riuscita-o-no
            notes: appunto facoltativo sulla prova
            gara_id: contesto gara, se la prova nasce lì (DEPRECATED)
            round_number: turno di quella gara (DEPRECATED)

        Returns:
            ChallengeAttempt: la prova completata e persistita

        Raises:
            NotFoundError: il drill non esiste
            ValidationError: manca il dato che quel tipo di drill richiede
        """
        challenge = db.session.get(Challenge, challenge_id)
        if challenge is None:
            raise NotFoundError("Drill non trovato")

        if challenge.pass_fail_only:
            if passed is None:
                raise ValidationError("Serve dire se la prova è stata superata o no")
        elif score is None:
            raise ValidationError("Serve il punteggio ottenuto")
        else:
            ChallengeService._validate_score_against_max(challenge, score)

        attempt = ChallengeService.start_challenge_attempt(
            user_id=user_id,
            challenge_id=challenge_id,
            gara_id=gara_id,
            round_number=round_number,
        )

        return ChallengeService.complete_challenge_attempt(
            attempt_id=attempt.id,
            score=score,
            passed=passed,
            notes=notes,
        )
