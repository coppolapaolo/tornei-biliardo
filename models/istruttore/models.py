"""I gruppi di allievi dell'istruttore e le schede che propone (D12, fase 8).

Tre tabelle, e una sola cosa da tenere a mente leggendole:

    training_group          un corso: nome, periodo, e di chi è
      training_group_member chi ne fa parte, da quando a quando
    training_assignment     una scheda proposta a un allievo, e cos'ha risposto

**Nessuna delle tre dà accesso a niente.** È l'ADR-069 §2: l'unico posto in cui
sta scritto chi legge che cosa è `training_sheet_reader`, e queste tabelle
servono a *ordinare* chi te l'ha già dato — non a ottenerlo. Se domani un
allievo ti richiude la sua scheda, la riga del gruppo resta dov'è (è storia) e
tu di quella scheda non vedi più niente di nuovo: le due cose non si parlano, e
il permesso non passa mai da qui.

Da questo discendono le tre scelte che si vedono nello schema.

* **`instructor_id` è anche sul membro**, e non solo sul gruppo. È una
  denormalizzazione, e serve a un indice unico parziale che il database può
  davvero imporre: «un allievo sta in un gruppo solo per volta, per lo stesso
  istruttore». Un'unicità che vive in Python è invisibile a chi scrive in
  blocco — `UserMergeService` decide dallo schema se muovere una colonna riga
  per riga — ed è così che unendo due account un giocatore è finito iscritto
  due volte alla stessa gara. La colonna è sicura perché non cambia mai: un
  gruppo appartiene al suo istruttore per sempre.
* **Chiudere un gruppo data l'uscita dei suoi membri.** Senza, l'indice qui
  sopra impedirebbe di mettere l'allievo nel corso dell'anno dopo: per il
  database sarebbe ancora dentro quello di prima. E dire «è uscito il giorno in
  cui il corso è finito» è anche ciò che è successo davvero.
* **Le righe non si cancellano mai.** «Chi c'era» è la domanda a cui questa
  tabella risponde, come `granted_at`/`revoked_at` per i permessi.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from ..base import BaseModel, db, utc_now


class TrainingGroup(BaseModel):
    """Un corso: un nome, un periodo, e gli allievi che ci sono dentro.

    Il periodo è fatto di due date **facoltative**: chi tiene un corso a
    calendario le mette entrambe, chi segue tre ragazzi tutto l'anno non ne
    mette nessuna. ``ended_on`` valorizzata è anche ciò che distingue un gruppo
    in corso da uno passato — non un `is_active` a parte, che sarebbe un
    secondo posto in cui scrivere la stessa cosa.
    """

    __tablename__ = "training_group"

    id = db.Column(db.Integer, primary_key=True)
    instructor_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    name = db.Column(db.String(120), nullable=False)
    #: Il periodo **dichiarato**: «dal 15/09 al 15/12». Due date facoltative,
    #: ed entrambe descrivono il calendario — non lo stato. Un corso che sul
    #: calendario finisce a dicembre è in corso a settembre.
    started_on = db.Column(db.Date, nullable=True)
    ended_on = db.Column(db.Date, nullable=True)
    #: Quando il corso è stato **chiuso**, che è un atto e non una previsione.
    #: NULL = in corso. Separata da `ended_on` perché le due cose divergono
    #: sempre: la data di fine si scrive a settembre, la chiusura succede a
    #: dicembre — e leggere la prima come stato farebbe nascere archiviato ogni
    #: corso a cui si dà un calendario.
    closed_at = db.Column(db.DateTime, nullable=True)

    instructor = db.relationship("User", foreign_keys=[instructor_id])
    members = db.relationship(
        "TrainingGroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="TrainingGroupMember.joined_at",
    )

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def active_members(self) -> List["TrainingGroupMember"]:
        """Chi ne fa parte adesso, nell'ordine in cui è entrato."""
        return [member for member in self.members if member.left_at is None]

    @property
    def week_of(self) -> Optional[int]:
        """A che settimana è arrivato il corso, se ha una data d'inizio.

        Uno alla prima settimana, non zero: un corso cominciato ieri è alla
        «settimana 1 di 13», come lo direbbe chi lo tiene. Un corso chiuso si
        ferma alla settimana in cui è finito.
        """
        if self.started_on is None:
            return None
        oggi = utc_now().date()
        fine = min(self.ended_on, oggi) if self.ended_on else oggi
        giorni = (fine - self.started_on).days
        if giorni < 0:
            return None
        return giorni // 7 + 1

    @property
    def weeks(self) -> Optional[int]:
        """Quante settimane dura, se il periodo è chiuso da due date."""
        if self.started_on is None or self.ended_on is None:
            return None
        giorni = (self.ended_on - self.started_on).days
        if giorni < 0:
            return None
        return giorni // 7 + 1

    def __repr__(self) -> str:  # pragma: no cover - banale
        return f"<TrainingGroup {self.id} {self.name!r}>"


class TrainingGroupMember(BaseModel):
    """Un allievo dentro un gruppo, da quando a quando.

    Ci si entra solo se si è già allievi — cioè se si è già aperta almeno una
    scheda a questo istruttore (ADR-069). Il controllo sta nel servizio, dove
    stanno le regole; qui c'è solo il fatto, con le sue date.
    """

    __tablename__ = "training_group_member"

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(
        db.Integer,
        db.ForeignKey("training_group.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Copia di `group.instructor_id`: serve all'indice unico parziale, e non
    #: cambia mai (vedi il docstring del modulo).
    instructor_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    joined_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    #: Quando ne è uscito. NULL = ci sta ancora.
    left_at = db.Column(db.DateTime, nullable=True)

    group = db.relationship("TrainingGroup", back_populates="members")
    user = db.relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        db.Index(
            "uq_training_group_member_attivo",
            "instructor_id",
            "user_id",
            unique=True,
            sqlite_where=db.text("left_at IS NULL"),
        ),
        db.Index("ix_training_group_member_group_id", "group_id"),
    )

    @property
    def is_current(self) -> bool:
        return self.left_at is None

    def __repr__(self) -> str:  # pragma: no cover - banale
        return f"<TrainingGroupMember group={self.group_id} user={self.user_id}>"


class EsitoProposta(Enum):
    """Com'è finita una proposta. NULL sulla riga vuol dire «in attesa».

    I valori stanno in una colonna `String` e non in un `db.Enum`: senza
    `values_callable` SQLAlchemy persiste il **nome** del membro, e rinominarlo
    domani romperebbe i dati già scritti (incidente del 2026-08-17). Qui il
    nome resta un fatto del codice e il valore un fatto del database.
    """

    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


class TrainingAssignment(BaseModel):
    """Una scheda che un istruttore propone a un allievo, e cos'ha risposto.

    È una **proposta**, non un'assegnazione: finché l'allievo non accetta non
    esiste nessuna scheda sua, e accettando ne nasce una di cui è proprietario
    lui. L'istruttore, da questa riga, non guadagna una sola lettura — il
    permesso resta una riga di `training_sheet_reader`, e l'allievo la dà nello
    stesso modulo con cui accetta, o non la dà (ADR-071).

    Le date: `proposed_at` quando è partita, `closed_at` quando ha smesso di
    essere in attesa, e `outcome` dice come. Due colonne e non tre timestamp,
    perché «in attesa» è una domanda che si fa spesso — ed è l'indice unico
    parziale a rispondere.
    """

    __tablename__ = "training_assignment"

    id = db.Column(db.Integer, primary_key=True)
    instructor_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    #: La scheda dell'istruttore da cui si copia: il modello.
    source_sheet_id = db.Column(
        db.Integer,
        db.ForeignKey("training_sheet.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: La scheda **nata dall'accettazione**, dell'allievo. NULL finché non
    #: accetta, e per sempre se dice di no. Va a NULL anche se un giorno quella
    #: scheda sparisse: la proposta resta accettata, che è ciò che è successo.
    sheet_id = db.Column(
        db.Integer,
        db.ForeignKey("training_sheet.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: La scheda che questa proposta **promuove**: è «dagli il livello
    #: successivo», il secondo gesto del passaggio (D8). Il primo — il timbro
    #: su `training_sheet.passed_at` — vale da solo, e questo è facoltativo:
    #: si può essere promossi senza avere ancora la scheda dopo.
    promotes_sheet_id = db.Column(
        db.Integer,
        db.ForeignKey("training_sheet.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: Il gruppo da cui è partita, quando è partita da lì. Serve a dire «la
    #: scheda del gruppo» e a fare una media che voglia dire qualcosa.
    group_id = db.Column(
        db.Integer,
        db.ForeignKey("training_group.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: Due parole dell'istruttore: «per l'autunno, fai i giorni A e B».
    message = db.Column(db.String(500), nullable=True)

    proposed_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    closed_at = db.Column(db.DateTime, nullable=True)
    outcome = db.Column(db.String(12), nullable=True)

    instructor = db.relationship("User", foreign_keys=[instructor_id])
    user = db.relationship("User", foreign_keys=[user_id])
    source_sheet = db.relationship("TrainingSheet", foreign_keys=[source_sheet_id])
    sheet = db.relationship("TrainingSheet", foreign_keys=[sheet_id])
    promotes_sheet = db.relationship("TrainingSheet", foreign_keys=[promotes_sheet_id])
    group = db.relationship("TrainingGroup", foreign_keys=[group_id])

    __table_args__ = (
        # Una proposta in attesa per volta, per coppia (istruttore, allievo).
        # Lo impone il database e non un `if`: un'unicità che vive in Python è
        # invisibile a chi scrive in blocco (ADR-070 §2). Due istruttori
        # diversi possono proporre insieme — è il loro mestiere, non una
        # raffica.
        db.Index(
            "uq_training_assignment_in_attesa",
            "instructor_id",
            "user_id",
            unique=True,
            sqlite_where=db.text("closed_at IS NULL"),
        ),
        db.Index("ix_training_assignment_user_id", "user_id"),
        db.Index("ix_training_assignment_group_id", "group_id"),
    )

    @property
    def is_pending(self) -> bool:
        return self.closed_at is None

    @property
    def is_accepted(self) -> bool:
        return self.outcome == EsitoProposta.ACCEPTED.value

    def __repr__(self) -> str:  # pragma: no cover - banale
        stato = "in attesa" if self.is_pending else (self.outcome or "?")
        return f"<TrainingAssignment {self.id} user={self.user_id} {stato}>"


__all__ = [
    "EsitoProposta",
    "TrainingAssignment",
    "TrainingGroup",
    "TrainingGroupMember",
]
