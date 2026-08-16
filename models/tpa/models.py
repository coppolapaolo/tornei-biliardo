"""Persistenza del referto TPA, agganciata al match individuale.

## Cosa si salva

Si salva **quello che il compilatore preme**, in ordine: un registro di comandi
(`TpaComando`). I rack, i turni, le bilie e il TPA non stanno su nessuna
colonna: si ricavano rigiocando il registro nel motore (`models.tpa.engine`).

E' una scelta, e ha tre conseguenze che valgono il prezzo:

1. **Una sola verita'.** Un totale salvato accanto ai dati che lo generano e'
   un totale che prima o poi diverge — dopo un annulla, dopo una correzione,
   dopo un cambio di regola.
2. **L'annulla e' esatto.** Togliere l'ultimo comando e rigiocare riporta allo
   stato esatto di un istante prima, senza dover sapere quale casella era stata
   toccata per ultima.
3. **Le regole restano correggibili.** Se un giorno il conteggio di un errore
   cambia, i referti gia' compilati si rileggono con le regole nuove invece di
   restare cristallizzati su un numero vecchio.

Il costo e' rigiocare a ogni lettura: qualche centinaio di comandi per partita,
cioe' niente.
"""

from __future__ import annotations

from typing import Optional

from models.base import BaseModel, db, utc_now


class TpaReferto(BaseModel):
    """Il referto TPA di un match individuale.

    Uno per match: chi annota deve essere sempre lo stesso, e due referti
    paralleli dello stesso incontro sarebbero due verita' diverse.
    """

    __tablename__ = "tpa_referto"

    id = db.Column(db.Integer, primary_key=True)

    individual_match_id = db.Column(
        db.Integer,
        db.ForeignKey("individual_match.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    #: Chi tiene il referto: uno dei due giocatori, quello che lo ha aperto.
    #: L'altro vede la stessa schermata, in sola lettura.
    compiler_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    #: Bilie del rack: 8, 9 o 10. Si fissa all'apertura perche' il motore ci
    #: calcola sopra le bilie rimaste, e un match non cambia disciplina a meta'.
    game_type = db.Column(db.Integer, nullable=False)

    closed_at = db.Column(db.DateTime, nullable=True)

    match = db.relationship(
        "IndividualMatch",
        foreign_keys=[individual_match_id],
        backref=db.backref("tpa_referto", uselist=False),
    )
    compiler = db.relationship("User", foreign_keys=[compiler_id])
    comandi = db.relationship(
        "TpaComando",
        back_populates="referto",
        cascade="all, delete-orphan",
        order_by="TpaComando.sequence",
    )

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None

    def player_number(self, user_id: int) -> Optional[int]:
        """1, 2 oppure ``None``: che posto occupa un utente in questo referto.

        Il referto ragiona per posti (il giocatore 1 spacca per primo), il match
        per identita'. Questa e' l'unica traduzione fra le due cose.
        """
        match = self.match
        if match is None:
            return None
        if user_id == match.player1_id:
            return 1
        if user_id == match.player2_id:
            return 2
        return None

    def user_id_for(self, player_number: int) -> Optional[int]:
        match = self.match
        if match is None:
            return None
        return match.player1_id if player_number == 1 else match.player2_id

    def close(self) -> None:
        self.closed_at = utc_now()

    def __repr__(self) -> str:
        count = len(self.comandi or [])
        return f"<TpaReferto match={self.individual_match_id} comandi={count}>"


class TpaComando(BaseModel):
    """Un gesto del compilatore, nell'ordine in cui e' avvenuto.

    ``command`` e' quello che c'e' scritto sul pulsante — ``"3"``, ``"M"``,
    ``"S"``, ``"P"`` — piu' due comandi che pulsanti non sono:

    - ``"end"``: tavolo passato all'avversario, cioe' fine turno;
    - ``"seat:1"`` / ``"seat:2"``: chi spacca questo rack.

    Il vocabolario e' quello del referto cartaceo Accu-Stats e non una
    reinterpretazione: chi ha imparato a compilarlo a mano ritrova le stesse
    lettere anche leggendo il database.
    """

    __tablename__ = "tpa_comando"

    #: Fine turno: il tavolo passa all'avversario.
    END_TURN = "end"
    #: Prefisso del comando che sceglie chi spacca il rack corrente.
    SEAT_PREFIX = "seat:"

    id = db.Column(db.Integer, primary_key=True)
    referto_id = db.Column(
        db.Integer,
        db.ForeignKey("tpa_referto.id", ondelete="CASCADE"),
        nullable=False,
    )

    #: Progressivo dentro il referto, da 1. E' l'ordine di gioco: senza, il
    #: registro non si puo' rigiocare.
    sequence = db.Column(db.Integer, nullable=False)

    command = db.Column(db.String(16), nullable=False)

    #: Quando e' stato premuto. Non serve al conteggio, serve a sapere quanto
    #: e' durata una partita e quanto un rack.
    pressed_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    referto = db.relationship("TpaReferto", back_populates="comandi")

    __table_args__ = (
        db.UniqueConstraint("referto_id", "sequence", name="uq_tpa_comando_sequence"),
        db.Index("idx_tpa_comando_referto", "referto_id"),
    )

    @classmethod
    def seat_command(cls, player_number: int) -> str:
        return f"{cls.SEAT_PREFIX}{player_number}"

    @property
    def seat_number(self) -> Optional[int]:
        """Il posto scelto, se questo comando sceglie chi spacca."""
        if not self.command.startswith(self.SEAT_PREFIX):
            return None
        return int(self.command[len(self.SEAT_PREFIX) :])

    def __repr__(self) -> str:
        return f"<TpaComando #{self.sequence} {self.command}>"


__all__ = ["TpaReferto", "TpaComando"]
