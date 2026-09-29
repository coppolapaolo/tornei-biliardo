"""La storia delle modifiche alle impostazioni di gare, campionati e playoff.

ADR-075: il direttore può correggere quasi tutto, quasi sempre, e in cambio
ogni correzione resta scritta. Due tabelle:

    settings_change         una voce per salvataggio: chi, quando, da dove,
                            perché (facoltativo), e da che turno vale
      settings_change_field una riga per campo: prima → dopo

**Le righe non si cancellano e non si correggono.** Chi ha sbagliato un motivo
aggiunge una voce nuova; è la stessa scelta del registro dei comandi del
referto TPA (ADR-044) e dei movimenti XP negativi: il registro racconta quello
che è successo, non quello che si vorrebbe fosse successo.

I valori stanno **grezzi** (`lag`, `alternate`, `2026-10-10`): si traducono in
lettura, nella lingua di chi legge. Una stringa già tradotta sarebbe nella
lingua di chi ha premuto il pulsante (ADR-062).

La storia appartiene a ciò che descrive: `ON DELETE CASCADE` sulla gara, sul
campionato e sulla configurazione dei playoff. Se la gara sparisce
fisicamente (competizione di prova, ADR-058) la sua storia va con lei; la
cancellazione normale è soft e non tocca niente.
"""

from __future__ import annotations

from ..base import BaseModel, db


class SettingsChangeSource:
    """Da dove arriva la modifica. Stringhe in colonna, nomi nel codice."""

    GARA = "gara"
    CAMPIONATO = "campionato"
    PLAYOFF = "playoff"
    #: Uno script di correzione dei dati (`scripts/set_gara_*.py`).
    SCRIPT = "script"


class SettingsChangeAction:
    """Che cosa è successo. «modifica» è il caso comune."""

    MODIFICA = "modifica"
    ANNULLA_AVVIO = "annulla_avvio"
    RICONFERMA = "riconferma"
    PROPOSTA_ACCETTATA = "proposta_accettata"
    PROPOSTA_RIFIUTATA = "proposta_rifiutata"
    NOTA = "nota"
    #: Gli strumenti a mano dei playoff: la riga `giocatore` dice chi.
    GIOCATORE_AGGIUNTO = "giocatore_aggiunto"
    GIOCATORE_TOLTO = "giocatore_tolto"
    RISPOSTA_PER_CONTO = "risposta_per_conto"


class SettingsChange(BaseModel):
    """Una voce della storia: un salvataggio, con le sue righe campo per campo."""

    __tablename__ = "settings_change"

    id = db.Column(db.Integer, primary_key=True)
    gara_id = db.Column(
        db.Integer, db.ForeignKey("gara.id", ondelete="CASCADE"), nullable=True
    )
    campionato_id = db.Column(
        db.Integer,
        db.ForeignKey("campionato.id", ondelete="CASCADE"),
        nullable=True,
    )
    playoff_config_id = db.Column(
        db.Integer,
        db.ForeignKey("playoff_configuration.id", ondelete="CASCADE"),
        nullable=True,
    )
    #: Chi ha agito. NULL per uno script senza utente, o se l'utente sparisse:
    #: la voce resta, perché la modifica è avvenuta.
    author_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    #: Il ruolo **in quel momento**: domani il direttore può non esserlo più,
    #: e la voce deve continuare a dire con che titolo ha agito.
    author_role = db.Column(db.String(20), nullable=True)
    source = db.Column(db.String(20), nullable=False, default=SettingsChangeSource.GARA)
    action = db.Column(
        db.String(30), nullable=False, default=SettingsChangeAction.MODIFICA
    )
    reason = db.Column(db.Text, nullable=True)
    #: Il primo turno a cui la modifica si applica; NULL = tutta la gara.
    from_round = db.Column(db.Integer, nullable=True)

    author = db.relationship("User", foreign_keys=[author_id])
    fields = db.relationship(
        "SettingsChangeField",
        backref="change",
        cascade="all, delete-orphan",
        order_by="SettingsChangeField.id",
        lazy="selectin",
    )

    __table_args__ = (
        db.Index("ix_settings_change_gara_id", "gara_id"),
        db.Index("ix_settings_change_campionato_id", "campionato_id"),
        db.Index("ix_settings_change_playoff_config_id", "playoff_config_id"),
    )


class SettingsChangeField(BaseModel):
    """Una riga di una voce: un campo, il valore di prima e quello di dopo."""

    __tablename__ = "settings_change_field"

    id = db.Column(db.Integer, primary_key=True)
    change_id = db.Column(
        db.Integer,
        db.ForeignKey("settings_change.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field = db.Column(db.String(50), nullable=False)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
