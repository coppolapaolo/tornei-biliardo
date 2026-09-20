"""L'obiettivo che un giocatore si dà (#316).

Una tabella sola per le tre forme. La riga dice **dove si vuole arrivare** e da
dove si partiva; il progresso non si salva mai — si legge ogni volta dalle
stesse fonti dell'andamento, perché un progresso memorizzato è un numero da
tenere allineato a mano con dei dati che cambiano sotto.

Due date si scrivono, e sono fatti: `reached_at`, la prima volta che
l'obiettivo risulta raggiunto, e `abandoned_at`, quando si lascia.
**Raggiunto non si toglie**: è la regola dei traguardi (#184) — un record
battuto è un fatto, non uno stato — e serve a che l'obiettivo resti
nell'andamento con la sua data anche se poi si va peggio.

`baseline` si fissa alla creazione e non si rilegge più: è il «da dove parti»,
e ricalcolarlo a ogni lettura farebbe scorrere il punto di partenza dietro ai
progressi, cancellando proprio la cosa che l'obiettivo doveva far vedere
(stesso schema di `TrainingEntry.target_amount`, ADR-067).
"""

from __future__ import annotations

from typing import Optional

from ..base import BaseModel, db
from .kinds import GoalDeadline, GoalKind, GoalRule


class TrainingGoal(BaseModel):
    """Un obiettivo di allenamento, attivo o concluso."""

    __tablename__ = "training_goal"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )

    kind = db.Column(db.String(20), nullable=False)

    #: Su quale esercizio, per gli obiettivi di tipo ``esercizio``.
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenge.id", ondelete="CASCADE"), nullable=True
    )
    #: Su quale categoria, per gli obiettivi di tipo ``abilita``: l'asse
    #: (``abilita``/``gesto``) e il valore del vocabolario, come in
    #: ``challenge_category``.
    axis = db.Column(db.String(20), nullable=True)
    axis_value = db.Column(db.String(40), nullable=True)

    #: Dove si vuole arrivare, **nell'unità della domanda**: il punteggio
    #: dell'esercizio, la percentuale dell'asse, le settimane di fila.
    target = db.Column(db.Integer, nullable=False)
    #: Quando vale raggiunto, per gli obiettivi su un esercizio.
    rule = db.Column(db.String(20), nullable=True)
    #: Quante volte a settimana, per la costanza.
    per_week = db.Column(db.Integer, nullable=True)

    #: Da dove si partiva, nella stessa unità di ``target``. NULL quando alla
    #: creazione non c'era ancora niente da cui partire.
    baseline = db.Column(db.Integer, nullable=True)
    #: Entro quando: la scelta, e la data che ne discende.
    deadline_kind = db.Column(db.String(20), nullable=False, server_default="nessuna")
    deadline = db.Column(db.Date, nullable=True)

    reached_at = db.Column(db.DateTime, nullable=True)
    abandoned_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])
    challenge = db.relationship("Challenge")

    __table_args__ = (db.Index("ix_training_goal_user_id", "user_id"),)

    # ── letture ────────────────────────────────────────────────────────────
    @property
    def kind_enum(self) -> Optional[GoalKind]:
        return GoalKind.parse(self.kind)

    @property
    def rule_enum(self) -> GoalRule:
        return GoalRule.parse(self.rule)

    @property
    def deadline_enum(self) -> GoalDeadline:
        return GoalDeadline.parse(self.deadline_kind)

    @property
    def is_active(self) -> bool:
        """Attivo finché non è raggiunto e non è stato lasciato.

        Una scadenza passata **non** lo chiude: l'obiettivo resta lì, e la
        pagina dice che il tempo è finito. Chiuderlo da soli vorrebbe dire
        togliere dagli occhi proprio la cosa su cui si era indietro.
        """
        return self.reached_at is None and self.abandoned_at is None

    def __repr__(self) -> str:  # pragma: no cover - banale
        return f"<TrainingGoal {self.id} {self.kind} → {self.target}>"


__all__ = ["TrainingGoal"]
