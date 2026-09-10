"""Un evento live: ciò che una pagina aperta deve sapere entro pochi secondi.

Rack segnato, partita chiusa, turno nuovo, XP guadagnati: la pagina che sta
guardando la gara, o il tabellone della partita, li chiede al server ogni tre
secondi (`routes/sse.py`). Fra un poll e l'altro l'evento deve stare da qualche
parte, e quel posto deve essere **condiviso fra i worker**: in produzione sono
tre processi uWSGI con tre memorie separate, e un dizionario Python — com'era
fino a settembre 2026 — faceva arrivare un evento su tre. Vedi ADR-057.

La riga vive un minuto (`routes.sse.MAX_EVENT_AGE`) e poi viene cancellata
dalla pulizia che gira a ogni emit: la tabella contiene sempre e solo l'ultimo
minuto di attività.

`sqlite_autoincrement` non è un dettaglio: il cursore del client è l'`id`
dell'ultimo evento visto, e con il rowid semplice SQLite riusa il numero della
riga più alta appena cancellata — un cursore fermo lì non vedrebbe più nulla.
Con AUTOINCREMENT gli id crescono e basta.
"""

from __future__ import annotations

from models.base import BaseModel, db


class LiveEvent(BaseModel):
    __tablename__ = "live_event"
    __table_args__ = (
        # Le tre colonne del poll, nell'ordine in cui le filtra:
        # «gli eventi di questa gara con id oltre il cursore».
        db.Index("ix_live_event_scope", "scope", "scope_id", "id"),
        {"sqlite_autoincrement": True},
    )

    id = db.Column(db.Integer, primary_key=True)
    #: Uno dei valori di `routes.sse.EventScope` (gara, match, user, ...).
    scope = db.Column(db.String(32), nullable=False)
    scope_id = db.Column(db.Integer, nullable=False)
    event_type = db.Column(db.String(64), nullable=False)
    #: JSON, così com'è arrivato a `emit_event`.
    payload = db.Column(db.Text, nullable=False)
    #: `time.time()` all'emit: serve alla pulizia, non al cursore.
    ts = db.Column(db.Float, nullable=False)

    def __repr__(self) -> str:
        return f"<LiveEvent {self.id} {self.scope}:{self.scope_id} {self.event_type}>"
