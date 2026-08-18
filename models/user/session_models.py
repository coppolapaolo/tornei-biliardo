"""
Module: models/user/session_models.py
Purpose: traccia degli accessi — chi si collega, quando, per quanto tempo.

Data Structures: UserSession

Non esisteva niente del genere. La scheda «retention» dei KPI mostra gia'
DAU/WAU/MAU, ma li calcola sui **match giocati** (`Match.updated_at`): chi
entra ogni giorno e non gioca risulta dormiente. Una domanda semplice come
«questo utente si e' mai collegato dopo la registrazione?» non aveva risposta
da nessuna parte.

Cosa **non** c'e' dentro, di proposito:

- l'indirizzo IP. E' un dato personale che va difeso, cancellato su richiesta e
  giustificato: per rispondere a «chi si collega e quando» non serve, e tenerlo
  aprirebbe una superficie GDPR per niente.
- lo user agent grezzo, che e' un'impronta. Ne resta la sola famiglia di
  dispositivo (``mobile`` / ``tablet`` / ``desktop``), che e' quanto basta a
  sapere da cosa entra la gente.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from ..base import db, BaseModel, utc_now

# Oltre questo silenzio la sessione e' considerata finita: la visita
# successiva ne apre una nuova invece di allungare la vecchia. Senza, un
# «ricordami» farebbe di una settimana un unico accesso da 7 giorni.
INATTIVITA_MASSIMA = timedelta(minutes=30)


class UserSession(BaseModel):
    """Una permanenza sul sito: da quando entra a quando smette di farsi vivo.

    ``ended_at`` e' valorizzato solo dal logout esplicito, che quasi nessuno
    fa. La durata quindi si misura su ``last_seen_at``: e' l'ultimo istante in
    cui sappiamo che c'era davvero, e dire di piu' sarebbe inventare.
    """

    __tablename__ = "user_session"

    id = db.Column(db.Integer, primary_key=True)
    # `CASCADE` e non il default: una traccia di accessi senza l'utente a cui
    # apparteneva non e' un dato, e' un residuo. Cancellare la persona deve
    # cancellare anche il registro di dove e' stata — che e' anche l'unica
    # risposta onesta a una richiesta di cancellazione.
    #
    # Il `CASCADE` da solo pero' non basta, e vale la pena saperlo: qui gli
    # utenti non si cancellano, si **anonimizzano** (`User.anonymize()`), e la
    # riga `user` resta. La cancellazione delle sessioni sta quindi anche li',
    # esplicita. Il vincolo copre il caso in cui una riga sparisca davvero.
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
    ended_at = db.Column(db.DateTime, nullable=True)
    device = db.Column(db.String(16), nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])

    @property
    def durata(self) -> timedelta:
        """Quanto e' durata: fino al logout, o fino all'ultimo segno di vita."""
        fine = self.ended_at or self.last_seen_at
        return fine - self.started_at

    @property
    def durata_secondi(self) -> int:
        return int(self.durata.total_seconds())

    @property
    def e_aperta(self) -> bool:
        """Nessun logout e visto di recente: e' probabile che sia ancora li'."""
        if self.ended_at is not None:
            return False
        return (utc_now() - self.last_seen_at) <= INATTIVITA_MASSIMA

    def chiudi(self, quando: Optional[object] = None) -> None:
        """Chiude la sessione all'ultimo istante certo, non a «adesso».

        Chiudere ad `utc_now()` regalerebbe alla sessione tutto il tempo in cui
        l'utente non c'era piu': e' proprio la misura che questa tabella deve
        evitare di sbagliare.
        """
        self.ended_at = quando or self.last_seen_at
