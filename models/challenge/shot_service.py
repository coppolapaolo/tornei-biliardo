"""La prova come sequenza di colpi (ADR-066).

Un esercizio colpo per colpo non si registra con un numero a fine prova: si
registra **un colpo per volta**, e il punteggio è la somma dei colpi. Qui sta
il ciclo di vita di quella prova:

* il primo colpo **apre** la prova (`ChallengeAttempt.completed = False`). Non
  c'è un «inizia»: una prova aperta senza colpi è una riga che nessuno chiuderà
  più, quindi non esiste — nasce col primo colpo e sparisce se lo si annulla;
* finché è aperta si annulla **l'ultimo colpo**, e una prova lasciata a metà si
  **riprende**: chi chiude il browser al colpo 12 lo ritrova lì;
* dopo l'ultimo colpo la prova si **chiude con un gesto**. Non da sola: l'errore
  sull'ultimo tocco è probabile quanto sugli altri, e chiudendo da soli
  l'annulla dovrebbe restituire l'XP appena dato. Chiudere passa da
  `ChallengeService.complete_challenge_attempt`, quindi achievement ed eventi
  sono quelli di ogni altra prova.

Tutte le statistiche leggono `completed = True`: una prova aperta non conta da
nessuna parte, e il suo `score` resta NULL finché non la si chiude.

Questo è l'allenamento dal catalogo. In esami e gare un esercizio colpo per
colpo si registra ancora col totale digitato: lì le prove stanno in altre
tabelle, e non c'è un secondo segnapunti da contraddire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from flask_babel import gettext as _

from models.base import db, utc_now
from models.exceptions import ConflictError, NotFoundError, ValidationError
from models.transaction.manager import transactional

from .draw_spec import parse_draw_spec
from .models import Challenge, ChallengeAttempt, ChallengeShot
from .recording import RecordingMode
from .target import on_cloth, target_from_scene


@dataclass(frozen=True)
class ShotRun:
    """La prova in corso, come la vede chi sta tirando."""

    challenge: Challenge
    attempt: Optional[ChallengeAttempt]
    shots: List[ChallengeShot] = field(default_factory=list)

    @property
    def shots_count(self) -> int:
        return self.challenge.shots_count or 0

    @property
    def total(self) -> int:
        return sum(s.points for s in self.shots)

    @property
    def next_position(self) -> int:
        return len(self.shots) + 1

    @property
    def is_full(self) -> bool:
        """Tirati tutti i colpi: resta da chiudere, o da annullare l'ultimo."""
        return len(self.shots) >= self.shots_count > 0


class ShotRunService:
    # ── Lettura ───────────────────────────────────────────────────────────
    @staticmethod
    def current(user_id: int, challenge_id: int) -> ShotRun:
        challenge = ShotRunService._challenge(challenge_id)
        return ShotRunService._run(challenge, user_id)

    @staticmethod
    def _challenge(challenge_id: int, *, mode: Optional[RecordingMode] = None):
        """L'esercizio, se si registra a colpi — e, se richiesto, **in quel modo**.

        Il gesto e il modo devono corrispondere: toccare il panno su un
        esercizio con estrazione, o scegliere un esito su uno col bersaglio,
        sono due richieste che non vogliono dire niente, e accettarle
        scriverebbe un colpo senza il dato che lo qualifica.
        """
        challenge = db.session.get(Challenge, challenge_id)
        if challenge is None:
            raise NotFoundError(_("Esercizio non trovato"))
        modo = RecordingMode.parse(challenge.recording_mode)
        if not modo.is_sequence:
            raise ValidationError(_("Questo esercizio non si registra colpo per colpo"))
        if mode is not None and modo is not mode:
            raise ValidationError(_("Non è così che si registra questo esercizio"))
        return challenge

    @staticmethod
    def _open_attempt(user_id: int, challenge_id: int) -> Optional[ChallengeAttempt]:
        # `gara_id IS NULL`: la prova giocata al posto della X nasce aperta
        # anche lei, ma ha la sua gara e il suo percorso — non è allenamento.
        return (
            ChallengeAttempt.query.filter_by(
                user_id=user_id, challenge_id=challenge_id, completed=False
            )
            .filter(ChallengeAttempt.gara_id.is_(None))
            .order_by(ChallengeAttempt.id.desc())
            .first()
        )

    @staticmethod
    def _run(challenge: Challenge, user_id: int) -> ShotRun:
        attempt = ShotRunService._open_attempt(user_id, challenge.id)
        return ShotRun(
            challenge=challenge,
            attempt=attempt,
            shots=list(attempt.shots) if attempt else [],
        )

    # ── Scrittura ─────────────────────────────────────────────────────────
    @staticmethod
    @transactional(domain="challenge")
    def record_shot(
        user_id: int,
        challenge_id: int,
        *,
        made: bool,
        x: Optional[float] = None,
        y: Optional[float] = None,
        variant_id: Optional[int] = None,
    ) -> ShotRun:
        """Un colpo in più nella prova aperta; il primo la apre.

        I punti li decide il bersaglio e si **scrivono sul colpo**: se domani
        l'autore lo sposta, i colpi già tirati valgono ancora quello che
        valevano.
        """
        challenge = ShotRunService._challenge(challenge_id, mode=RecordingMode.SHOTS)
        run = ShotRunService._run(challenge, user_id)
        if run.is_full:
            raise ConflictError(
                _("Hai già tirato tutti i colpi: chiudi la prova o annulla l'ultimo.")
            )

        punti = 0
        if made:
            bersaglio = target_from_scene(challenge.diagram_scene)
            if bersaglio is None:
                raise ValidationError(_("Questo esercizio non ha un bersaglio."))
            if not on_cloth(x, y):
                raise ValidationError(
                    _("Tocca il panno nel punto in cui si è fermata la bianca.")
                )
            assert x is not None and y is not None
            punti = bersaglio.points_at(x, y)
        else:
            # Il colpo non imbucato non ha un punto: non lo si inventa.
            x = y = None

        attempt = run.attempt
        if attempt is None:
            if variant_id is not None and variant_id not in {
                v.id for v in challenge.variants
            }:
                raise ValidationError(_("Questa variante non è di questo esercizio"))
            attempt = ChallengeAttempt(
                user_id=user_id, challenge_id=challenge.id, variant_id=variant_id
            )
            db.session.add(attempt)
            db.session.flush()

        db.session.add(
            ChallengeShot(
                attempt_id=attempt.id,
                position=run.next_position,
                made=bool(made),
                points=punti,
                x=x,
                y=y,
            )
        )
        db.session.flush()
        db.session.expire(attempt, ["shots"])
        return ShotRunService._run(challenge, user_id)

    @staticmethod
    @transactional(domain="challenge")
    def draw_next(user_id: int, challenge_id: int) -> ShotRun:
        """La consegna del colpo che sta per essere giocato (#452).

        La **prima** estrazione apre la prova: con l'estrazione cominciare è un
        atto — ti dice che cosa fare — mentre col bersaglio il primo dato è già
        il primo colpo.

        Se una consegna in attesa c'è già, **non se ne estrae un'altra**:
        chiamare di nuovo non è un modo di rifare il sorteggio finché piace.
        """
        challenge = ShotRunService._challenge(challenge_id, mode=RecordingMode.DRAW)
        spec = parse_draw_spec(challenge.draw_spec)
        if spec is None:
            raise ValidationError(_("Questo esercizio non ha niente da estrarre."))

        run = ShotRunService._run(challenge, user_id)
        if run.is_full:
            raise ConflictError(
                _("Hai già tirato tutti i colpi: chiudi la prova o annulla l'ultimo.")
            )

        attempt = run.attempt
        if attempt is None:
            attempt = ChallengeAttempt(user_id=user_id, challenge_id=challenge.id)
            db.session.add(attempt)
            db.session.flush()
        if not attempt.pending_prompt:
            attempt.pending_prompt = spec.draw()
        db.session.flush()
        return ShotRunService._run(challenge, user_id)

    @staticmethod
    @transactional(domain="challenge")
    def record_outcome(user_id: int, challenge_id: int, *, outcome_index) -> ShotRun:
        """Com'è andato il colpo estratto: una voce della scala, col suo nome.

        Consegna e nome dell'esito si scrivono **sul colpo**, come i punti: se
        domani l'autore riscrive le liste o la scala, il colpo giocato deve
        continuare a raccontare quello che è successo.
        """
        challenge = ShotRunService._challenge(challenge_id, mode=RecordingMode.DRAW)
        spec = parse_draw_spec(challenge.draw_spec)
        if spec is None:
            raise ValidationError(_("Questo esercizio non ha niente da estrarre."))

        run = ShotRunService._run(challenge, user_id)
        if run.is_full:
            raise ConflictError(
                _("Hai già tirato tutti i colpi: chiudi la prova o annulla l'ultimo.")
            )
        # Prima si sa che cosa fare, poi si tira: mai il contrario.
        if run.attempt is None or not run.attempt.pending_prompt:
            raise ConflictError(_("Estrai la consegna prima di registrare il colpo."))

        esito = spec.outcome_at(outcome_index)
        consegna = run.attempt.pending_prompt
        db.session.add(
            ChallengeShot(
                attempt_id=run.attempt.id,
                position=run.next_position,
                made=None,
                points=esito.points,
                prompt=consegna,
                outcome_label=esito.label,
            )
        )
        # La consegna dopo esce subito: chi sta tirando non deve chiederla.
        # All'ultimo colpo no — non c'è nessun colpo dopo da preparare.
        resta = run.shots_count - (len(run.shots) + 1) > 0
        run.attempt.pending_prompt = spec.draw() if resta else None
        db.session.flush()
        db.session.expire(run.attempt, ["shots"])
        return ShotRunService._run(challenge, user_id)

    @staticmethod
    @transactional(domain="challenge")
    def undo_last(user_id: int, challenge_id: int) -> ShotRun:
        """Toglie l'ultimo colpo. Tolto l'unico, la prova aperta sparisce."""
        challenge = ShotRunService._challenge(challenge_id)
        run = ShotRunService._run(challenge, user_id)
        if run.attempt is None or not run.shots:
            raise NotFoundError(_("Non c'è nessun colpo da annullare."))

        ultimo = run.shots[-1]
        # Con l'estrazione la consegna del colpo tolto torna in attesa: se se ne
        # estraesse una nuova, annullare sarebbe un modo di riestrarre finché
        # la consegna piace.
        con_estrazione = (
            RecordingMode.parse(challenge.recording_mode) is RecordingMode.DRAW
        )
        if ultimo.prompt:
            run.attempt.pending_prompt = ultimo.prompt
        db.session.delete(ultimo)
        # Tolto l'unico colpo la prova sparisce — una prova aperta e vuota è una
        # riga che nessuno chiude più. Non con l'estrazione: lì la prova è nata
        # dall'estrazione, non dal colpo, e la consegna appena rimessa in attesa
        # è ancora da giocare.
        prova_resta = len(run.shots) > 1 or con_estrazione
        if not prova_resta:
            db.session.delete(run.attempt)
        db.session.flush()
        if prova_resta:
            # La relazione è in cache: senza, la prova continuerebbe a portarsi
            # dietro il colpo appena tolto.
            db.session.expire(run.attempt, ["shots"])
        return ShotRunService._run(challenge, user_id)

    @staticmethod
    @transactional(domain="challenge")
    def restart(user_id: int, challenge_id: int) -> None:
        """Butta la prova aperta, colpi compresi. Le prove chiuse non si toccano."""
        ShotRunService._challenge(challenge_id)
        attempt = ShotRunService._open_attempt(user_id, challenge_id)
        if attempt is not None:
            db.session.delete(attempt)

    @staticmethod
    @transactional(domain="challenge")
    def close(
        user_id: int, challenge_id: int, notes: Optional[str] = None
    ) -> ChallengeAttempt:
        """Chiude la prova: il punteggio è la somma dei colpi, l'ora è adesso."""
        from .services import ChallengeService

        challenge = ShotRunService._challenge(challenge_id)
        run = ShotRunService._run(challenge, user_id)
        if run.attempt is None or not run.is_full:
            raise ConflictError(
                _("La prova si chiude dopo l'ultimo colpo: ne mancano ancora.")
            )
        # L'ora della prova è quella in cui finisce: è lì che entra nelle
        # «prove di oggi», e una ripresa il giorno dopo non la lascia a ieri.
        run.attempt.attempted_at = utc_now()
        run.attempt.pending_prompt = None
        chiusa = run.attempt.id
        return ChallengeService.complete_challenge_attempt(
            attempt_id=chiusa, score=run.total, notes=notes
        )


__all__ = ["ShotRun", "ShotRunService"]
