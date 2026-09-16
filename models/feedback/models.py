"""La segnalazione di un utente, e il suo legame con la issue su GitHub.

**La segnalazione si salva prima su DB, poi si prova a spedirla.** Se il token
manca, se GitHub risponde 5xx, se la rete non c'è, la segnalazione è comunque
salva e chi l'ha scritta vede «ricevuta»; il rinvio lo fa il job giornaliero.
La strada opposta — chiamare GitHub dentro la richiesta e mostrare un errore —
perde il testo che l'utente ha appena scritto, ed è il modo migliore per non
riceverne mai più.

Il repo è **privato**: le issue non sono leggibili senza token, quindi l'app
non mostra mai link a github.com. Quello che l'utente sa di GitHub è zero, e
`issue_number` esiste solo per l'admin e per il polling.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from ..base import BaseModel, db

#: Il titolo entra in una riga; il corpo è un racconto, ma non un romanzo.
MAX_TITLE_LENGTH = 200
MAX_BODY_LENGTH = 5000


class FeedbackType(Enum):
    """Le tre categorie che i giocatori riconoscono.

    I **valori** sono le label di GitHub, così la traduzione da «Qualcosa non
    funziona» a `bug` la fa l'app una volta sola, qui, e non ogni chiamante.
    """

    BUG = "bug"
    IDEA = "enhancement"
    DOMANDA = "question"

    @property
    def label_github(self) -> str:
        return self.value

    @classmethod
    def parse(cls, value: Optional[str]) -> Optional["FeedbackType"]:
        """Il tipo scritto in un form, o `None` se non è uno dei tre."""
        for membro in cls:
            if membro.value == value:
                return membro
        return None


class FeedbackStatus(Enum):
    """Lo stato interno. Cosa legge l'utente lo decide la UI, non questo enum.

    Sono quattro perché quattro sono le cose che si possono onestamente dire a
    chi ha segnalato: l'abbiamo ricevuta, l'abbiamo guardata, è fatta, non la
    faremo. Ogni sfumatura in più sarebbe una promessa che non sappiamo
    mantenere.
    """

    RICEVUTA = "ricevuta"
    PRESA_IN_CARICO = "presa_in_carico"
    RISOLTA = "risolta"
    NON_PREVISTA = "non_prevista"


class FeedbackReport(BaseModel):
    """Una segnalazione, dal modulo compilato fino alla issue che ne è nata."""

    __tablename__ = "feedback_report"
    __table_args__ = (
        db.Index("ix_feedback_report_user", "user_id"),
        # Il job cerca due cose: chi non è ancora partito (issue_number NULL)
        # e chi va ricontrollato (issue_number valorizzato).
        db.Index("ix_feedback_report_issue", "issue_number"),
    )

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Le colonne enum tengono il **valore**, non il nome del membro: una
    # `db.Enum(FeedbackType)` senza `values_callable` persisterebbe `BUG`, e il
    # giorno che qualcuno rinomina il membro le righe già scritte diventano
    # illeggibili (incidente 2026-08-17, `test_enum_columns_store_values.py`).
    tipo = db.Column(db.String(20), nullable=False)
    titolo = db.Column(db.String(MAX_TITLE_LENGTH), nullable=False)
    corpo = db.Column(db.Text, nullable=False)

    #: Pagina di provenienza, versione, ruolo, user agent, lingua: ciò che
    #: l'utente non saprebbe dare e che serve sempre. Nessun dato personale.
    contesto = db.Column(db.Text, nullable=True)

    stato = db.Column(
        db.String(20), nullable=False, default=FeedbackStatus.RICEVUTA.value
    )
    #: Quando lo stato è cambiato l'ultima volta, per la sezione «Novità».
    stato_cambiato_il = db.Column(db.DateTime, nullable=True)

    #: La frase che il maintainer ha scritto **per l'utente** (un commento che
    #: comincia con il marcatore). Un commento qualunque non arriva qui: sulla
    #: issue si deve poter ragionare senza pubblicare.
    nota_pubblica = db.Column(db.Text, nullable=True)

    #: NULL finché la issue non è nata. È il segnale che il job usa per
    #: rispedire, e non si mostra a chi ha segnalato: il numero è il ponte con
    #: il backlog, non un'informazione per l'utente. Fino al 2026-09-16 il
    #: motivo era anche che il repository era privato; ora è pubblico, ma la
    #: scelta non è stata riesaminata.
    issue_number = db.Column(db.Integer, nullable=True)
    tentativi_invio = db.Column(db.Integer, nullable=False, default=0)
    #: L'ultimo errore di spedizione, in chiaro, per l'admin. Un rinvio
    #: riuscito lo azzera: un errore vecchio accanto a una issue creata
    #: racconterebbe un guasto che non c'è più.
    ultimo_errore = db.Column(db.String(500), nullable=True)

    user = db.relationship("User", backref=db.backref("feedback_reports", lazy=True))

    def __repr__(self) -> str:
        return f"<FeedbackReport {self.id} {self.tipo} {self.stato}>"

    @property
    def tipo_enum(self) -> Optional[FeedbackType]:
        return FeedbackType.parse(self.tipo)

    @property
    def stato_enum(self) -> FeedbackStatus:
        return FeedbackStatus(self.stato)

    @property
    def in_attesa_di_invio(self) -> bool:
        """Salvata qui ma non ancora diventata una issue."""
        return self.issue_number is None


class FeedbackSyncState(BaseModel):
    """Dove il job ha lasciato le cose l'ultima volta. Una riga sola.

    Serve a due cose che il processo del job non può ricordarsi da sé — nasce
    e muore ogni notte:

    * `ultimo_controllo`, che diventa il `since` della chiamata: si chiedono
      solo le issue toccate da allora, non tutte;
    * `etag`, che rende il caso normale — «non è cambiato niente» — un 304 da
      poche centinaia di byte invece di cento issue.

    Una tabella invece di un file perché su PythonAnywhere il disco è NFS e i
    processi sono due (web app e scheduled task): il DB è l'unico posto dove
    entrambi guardano davvero.
    """

    __tablename__ = "feedback_sync_state"

    id = db.Column(db.Integer, primary_key=True)
    #: Fine dell'ultimo giro **riuscito**. Un giro fallito non la sposta:
    #: altrimenti le issue cambiate in quella finestra non si rileggerebbero
    #: mai più.
    ultimo_controllo = db.Column(db.DateTime, nullable=True)
    etag = db.Column(db.String(200), nullable=True)

    @classmethod
    def corrente(cls) -> "FeedbackSyncState":
        """La riga, creandola al primo giro."""
        stato = db.session.get(cls, 1)
        if stato is None:
            stato = cls(id=1)
            db.session.add(stato)
            db.session.flush()
        return stato
