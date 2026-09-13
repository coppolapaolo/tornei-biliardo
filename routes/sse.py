# routes/sse.py
"""Aggiornamenti live: polling HTTP su una tabella condivisa fra i worker.

Il nome del modulo è storico — il trasporto era Server-Sent Events, ed è
rimasto negli URL (`/sse/poll/...`) e negli import. Quello che fa oggi:

    eventi di dominio → EventBus → routes/sse_bridge.py ─┐
    route, dopo il commit del servizio ──────────────────┼→ emit_event()
                                                         │
    emit_event() → tabella `live_event` ← GET /sse/poll/<scope>/<id>?since=<cursore>

Due decisioni, entrambe dettate da PythonAnywhere:

* **polling e non SSE** (ADR-021, febbraio 2026): i worker uWSGI sono sincroni
  e pochi, e una connessione SSE ne tiene occupato uno per tutta la sua
  durata. Con tre pagine aperte il sito non rispondeva più;
* **una tabella e non la memoria** (ADR-057, settembre 2026): i worker sono
  tre **processi**, e un dizionario Python vive in uno solo. Un evento scritto
  dal worker che serviva il giocatore lo vedeva soltanto un poll capitato sullo
  stesso worker: un evento su tre arrivava.

Protocollo col client (`static/js/polling.js`):

* il primo poll arriva **senza** `since`: risponde con `events: []` e il
  cursore corrente. Il client non ha un orologio da confrontare col server,
  e il passato non gli interessa: la pagina l'ha appena caricata;
* da lì in poi `since` è l'**id** dell'ultimo evento visto. SQLite ha un solo
  scrittore per volta, quindi gli id si committano in ordine: «id maggiore
  del cursore» non salta niente, e un evento emesso dentro una transazione
  compare solo al commit, insieme al fatto che lo ha generato;
* `retention` dice per quanti secondi il server conserva gli eventi. Una
  scheda rimasta nascosta più a lungo non può recuperare: il client lo sa e
  ricarica.

Chi emette:

* il bridge, dentro `@transactional`: la riga viaggia con la transazione del
  servizio, e `emit_event` non committa;
* le route, dopo che il servizio ha già committato: lì `emit_event` committa
  da solo, altrimenti il teardown della richiesta butterebbe via la riga.
"""

import json
import time
from enum import Enum
from typing import List

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func

from models.base import db
from models.live_event import LiveEvent
from models.transaction.manager import transaction_manager

sse_bp = Blueprint("sse", __name__, url_prefix="/sse")


class EventScope(Enum):
    """A chi è rivolto un evento: la pagina che lo aspetta lo chiede per scope."""

    TRIO = "trio"
    GARA = "gara"
    USER = "user"
    INDIVIDUAL_MATCH = "individual_match"
    MATCH = "match"  # partita di gara


_SCOPES = {scope.value for scope in EventScope}

#: Quanto vive un evento, in secondi. È anche il tempo massimo che una scheda
#: può restare nascosta senza perdere niente: il client lo riceve come
#: `retention` e oltre quel limite ricarica.
MAX_EVENT_AGE = 60

#: La pulizia è ammortizzata: una DELETE ogni SWEEP_INTERVAL secondi, per
#: processo, non una per rack. La tabella tiene comunque solo l'ultimo minuto.
SWEEP_INTERVAL = 30.0
_last_sweep: float = 0.0


def _maybe_sweep(now: float) -> None:
    """Cancella gli eventi più vecchi di MAX_EVENT_AGE, al più ogni SWEEP_INTERVAL.

    Gira dentro `emit_event`, cioè da chi sta già scrivendo: il poll resta
    una lettura pura e non compete mai per il lock di scrittura di SQLite.
    """
    global _last_sweep
    if now - _last_sweep < SWEEP_INTERVAL:
        return
    _last_sweep = now
    LiveEvent.query.filter(LiveEvent.ts < now - MAX_EVENT_AGE).delete(
        synchronize_session=False
    )


# ═══════════════════════════════════════════════════════════════════════════
# Emit
# ═══════════════════════════════════════════════════════════════════════════


def emit_event(scope: EventScope, scope_id: int, event_type: str, data: dict) -> None:
    """Registra un evento per chi sta facendo il poll su (scope, scope_id).

    Dentro una transazione gestita (`@transactional`) la riga si committa con
    il resto; fuori — le route che emettono dopo il servizio — si committa
    qui, subito.
    """
    scope_key = scope.value if isinstance(scope, EventScope) else scope
    if scope_key not in _SCOPES:
        raise ValueError(
            f"Invalid scope: {scope_key}. Must be one of: {sorted(_SCOPES)}"
        )

    now = time.time()
    db.session.add(
        LiveEvent(
            scope=scope_key,
            scope_id=scope_id,
            event_type=event_type,
            payload=json.dumps(data),
            ts=now,
        )
    )
    _maybe_sweep(now)

    if transaction_manager.current_transaction is None:
        db.session.commit()


def emit_trio_event(trio_id: int, event_type: str, data: dict) -> None:
    """Partita a tre: rack_added, rack_removed, forfeit, result_confirmed."""
    emit_event(EventScope.TRIO, trio_id, event_type, data)


def emit_gara_event(gara_id: int, event_type: str, data: dict) -> None:
    """Gara: match_completed, match_updated, round_started, inscription_added,
    gara_completed."""
    emit_event(EventScope.GARA, gara_id, event_type, data)


def emit_user_event(user_id: int, event_type: str, data: dict) -> None:
    """Utente: notification, xp_gained, level_up, achievement,
    my_match_completed, match_table_changed."""
    emit_event(EventScope.USER, user_id, event_type, data)


def emit_individual_match_event(match_id: int, event_type: str, data: dict) -> None:
    """Sfida individuale: match_started, rack_updated, result_confirmed,
    match_completed, e i comandi del referto TPA."""
    emit_event(EventScope.INDIVIDUAL_MATCH, match_id, event_type, data)


def emit_match_event(match_id: int, event_type: str, data: dict) -> None:
    """Partita di gara: rack_added, rack_removed, forfeit, result_confirmed,
    table_assigned, table_removed, table_swapped."""
    emit_event(EventScope.MATCH, match_id, event_type, data)


# ═══════════════════════════════════════════════════════════════════════════
# Lettura
# ═══════════════════════════════════════════════════════════════════════════


def _current_cursor() -> int:
    """L'id più alto scritto finora: il punto di partenza di un client nuovo."""
    return db.session.query(func.max(LiveEvent.id)).scalar() or 0


def _get_events_since(scope: EventScope, scope_id: int, since_id: int) -> List[dict]:
    """Gli eventi di (scope, scope_id) con id oltre `since_id`, in ordine."""
    rows = (
        LiveEvent.query.filter(
            LiveEvent.scope == scope.value,
            LiveEvent.scope_id == scope_id,
            LiveEvent.id > since_id,
        )
        .order_by(LiveEvent.id)
        .all()
    )
    return [
        {
            "id": row.id,
            "type": row.event_type,
            "data": json.loads(row.payload),
            "timestamp": row.ts,
        }
        for row in rows
    ]


def _get_events_after_ts(
    scope: EventScope, scope_id: int, since_ts: float
) -> List[dict]:
    """Il vecchio criterio, per le pagine rimaste aperte col vecchio client.

    Fino a settembre 2026 `since` era un timestamp e il client teneva come
    cursore il `timestamp` della risposta. Una pagina aperta prima del deploy
    continua a mandarlo — e non riceve né il cursore nuovo né il `retention`,
    quindi non ricaricherebbe mai da sola. Per lei vale il criterio di prima,
    con i suoi difetti: sparisce col primo ricaricamento.
    """
    rows = (
        LiveEvent.query.filter(
            LiveEvent.scope == scope.value,
            LiveEvent.scope_id == scope_id,
            LiveEvent.ts > since_ts,
        )
        .order_by(LiveEvent.id)
        .all()
    )
    return [
        {
            "id": row.id,
            "type": row.event_type,
            "data": json.loads(row.payload),
            "timestamp": row.ts,
        }
        for row in rows
    ]


def _poll_response(scope: EventScope, scope_id: int):
    """La risposta di ogni endpoint di poll.

    `since` assente — un client appena aperto — vale come primo poll: nessun
    evento, solo il cursore da cui partire. Un `since` con la virgola è un
    timestamp del vecchio client: per lui vale ancora il criterio a tempo.
    """
    since = request.args.get("since", type=int)
    grezzo = request.args.get("since")
    if since is None and grezzo is not None:
        try:
            since_ts = float(grezzo)
        except ValueError:
            since_ts = None
        if since_ts is not None:
            return jsonify(
                {
                    "events": _get_events_after_ts(scope, scope_id, since_ts),
                    "cursor": _current_cursor(),
                    "timestamp": time.time(),
                    "retention": MAX_EVENT_AGE,
                }
            )

    current = _current_cursor()
    if since is None or since > current:
        # Oltre l'ultimo id scritto può capitare dopo un ripristino del DB
        # (o il seed in sviluppo): il cursore torna a terra invece di
        # aspettare che gli id lo raggiungano.
        events: List[dict] = []
        cursor = current
    else:
        events = _get_events_since(scope, scope_id, since)
        cursor = events[-1]["id"] if events else since
    return jsonify(
        {
            "events": events,
            "cursor": cursor,
            "timestamp": time.time(),
            "retention": MAX_EVENT_AGE,
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
# Endpoint di poll
# ═══════════════════════════════════════════════════════════════════════════


@sse_bp.route("/poll/trio/<int:trio_id>")
@login_required
def poll_trio(trio_id: int):
    return _poll_response(EventScope.TRIO, trio_id)


@sse_bp.route("/poll/gara/<int:gara_id>")
@login_required
def poll_gara(gara_id: int):
    return _poll_response(EventScope.GARA, gara_id)


@sse_bp.route("/poll/sala/<token>")
def poll_sala(token: str):
    """Il poll dello schermo in sala: pubblico, per indirizzo e non per id.

    Lo schermo lo apre chiunque abbia il link della vetrina, spesso un
    computer della sala senza nessuno collegato, quindi niente login. Si
    passa dall'indirizzo pubblico e non dall'id: una prova (ADR-058) risponde
    404 come la sua vetrina, e gli id delle gare non si enumerano. Gli eventi
    della gara dicono punteggi e turni, gli stessi che lo schermo mostra.
    """
    from models.competition.showcase_service import resolve_public_identifier

    gara = resolve_public_identifier(token)
    if gara is None:
        abort(404)
    return _poll_response(EventScope.GARA, gara.id)


@sse_bp.route("/poll/user/<int:user_id>")
@login_required
def poll_user(user_id: int):
    """Solo i propri eventi: XP, livelli, notifiche sono cose personali."""
    if current_user.id != user_id:
        abort(403)
    return _poll_response(EventScope.USER, user_id)


@sse_bp.route("/poll/individual_match/<int:match_id>")
@login_required
def poll_individual_match(match_id: int):
    return _poll_response(EventScope.INDIVIDUAL_MATCH, match_id)


@sse_bp.route("/poll/match/<int:match_id>")
@login_required
def poll_match(match_id: int):
    return _poll_response(EventScope.MATCH, match_id)
