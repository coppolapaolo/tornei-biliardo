# [021] SSE to Polling Migration

**Data**: 2026-02-03
**Stato**: Accepted
**Decisori**: Paolo, Claude

> **Nota (2026-09-02)**: il trasporto a polling resta. È cambiato ciò che sta fra
> un poll e l'altro: l'archivio in memoria non reggeva i tre processi uWSGI, il
> cursore non è più un timestamp, e gli stream SSE «deprecati» qui sotto sono
> stati rimossi. Vedi **ADR-057**.

## Contesto

L'applicazione usava Server-Sent Events (SSE) per aggiornamenti real-time (vedi ADR-006). Tuttavia, su PythonAnywhere con uWSGI sync workers, SSE causava gravi problemi di performance.

### Il Problema

uWSGI su PythonAnywhere ha solo **3 sync workers**. Ogni connessione SSE **blocca un worker** per l'intera durata della connessione (minuti/ore).

```
Log server analysis:
/sse/user/2     response-time=69.361s   (worker bloccato)
/sse/user/2     response-time=110.782s  (worker bloccato)
/sse/user/2     response-time=216.134s  (worker bloccato)
/gamification/dashboard  response-time=180.018s  (IN ATTESA di worker!)
```

Con 3+ utenti che aprono pagine con SSE, **tutti i worker sono occupati** e le richieste normali devono attendere minuti.

### Cause Root

1. **SSE su sync workers**: Il loop `while True: sleep(2)` in `_create_event_stream()` tiene il worker occupato indefinitely
2. **SSE in base.html**: Ogni pagina autenticata apriva una connessione SSE a `/sse/user/{id}`
3. **Nessun limite**: Non c'era timeout sulle connessioni SSE

## Decisione

Migrare da SSE a **polling HTTP con intervallo di 3 secondi**.

### Architettura

```
PRIMA (SSE - blocca worker)           DOPO (Polling - non blocca)
────────────────────────────         ────────────────────────────
Browser ←──── Worker bloccato        Browser ──→ GET /poll/user/2?since=123
              (minuti/ore)                     ←── {events: [...]} (~50ms)
                                              └── repeat ogni 3s
```

### Nuovi Endpoint

| Endpoint Polling | Sostituisce | Scopo |
|------------------|-------------|-------|
| `/sse/poll/user/<id>` | `/sse/user/<id>` | Notifiche user (XP, level up) |
| `/sse/poll/gara/<id>` | `/sse/gara/<id>` | Update gara (match, turni) |
| `/sse/poll/trio/<id>` | `/sse/trio/<id>` | Update trio match (rack) |
| `/sse/poll/individual_match/<id>` | `/sse/individual_match/<id>` | Update match individuali |

### Parametri

- `since`: Unix timestamp - ritorna solo eventi dopo questo tempo
- Response: `{events: [...], timestamp: float}`

### Intervallo Polling

**3 secondi** scelto come compromesso:
- Abbastanza veloce per sembrare "near real-time"
- Non sovraccarica il server con troppe richieste
- 20 richieste/minuto per utente (vs 0 con SSE ma worker bloccato)

## Implementazione

### Backend (`routes/sse.py`)

```python
def _get_events_since(scope: ScopeType, scope_id: int, since: float) -> List[dict]:
    """Get events newer than timestamp."""
    with _events_lock:
        events = _events[scope].get(scope_id, [])
        return [
            {"type": event_type, "data": data, "timestamp": ts}
            for event_type, data, ts in events
            if ts > since
        ]

@sse_bp.route("/poll/user/<int:user_id>")
@login_required
def poll_user(user_id: int):
    if current_user.id != user_id:
        abort(403)
    since = request.args.get("since", 0, type=float)
    events = _get_events_since("user", user_id, since)
    return jsonify({"events": events, "timestamp": time.time()})
```

### Frontend (esempio `base.html`)

```javascript
(function() {
    var userId = {{ current_user.id }};
    var lastTimestamp = 0;
    var pollInterval = 3000;

    function pollUserEvents() {
        fetch('/sse/poll/user/' + userId + '?since=' + lastTimestamp)
            .then(response => response.json())
            .then(result => {
                lastTimestamp = result.timestamp;
                result.events.forEach(handleEvent);
            })
            .catch(err => console.warn('[Poll] Error:', err.message));
    }

    setInterval(pollUserEvents, pollInterval);
    setTimeout(pollUserEvents, 500);
})();
```

## Alternative Considerate

### Alternativa 1: Gevent Workers

**Descrizione**: Usare uWSGI con gevent per async I/O.

- **Pro**: Mantiene SSE, migliaia di connessioni simultanee
- **Contro**:
  - PythonAnywhere non garantisce supporto
  - Richiede modifiche config uWSGI (non controllabile su PA)
  - Rischio race condition con SQLAlchemy/EventBus
  - Effort alto per testing

### Alternativa 2: WebSocket con servizio esterno

**Descrizione**: Usare servizio WebSocket cloud (Pusher, Ably).

- **Pro**: Real-time vero, scalabile
- **Contro**: Costo aggiuntivo, dipendenza esterna, overkill per questa app

### Alternativa 3: Ridurre timeout SSE

**Descrizione**: Disconnettere SSE dopo 30 secondi.

- **Pro**: Minimo cambiamento
- **Contro**: Non risolve il problema fondamentale, con N utenti > N worker si blocca comunque

## Conseguenze

### Positive

- **Risolve il problema**: I worker non si bloccano più
- **Semplice**: Polling è tecnologia web base, nessuna complessità
- **Retrocompatibile**: Gli endpoint SSE vecchi esistono ancora (deprecati)
- **Debuggabile**: Facile vedere richieste polling in Network tab
- **Funziona ovunque**: Nessun requisito speciale del server

### Negative

- **Latenza aumentata**: Max 3s di ritardo vs near-instant con SSE
- **Più richieste HTTP**: ~20 req/min per utente connesso
- **Non elegante**: Polling è "vecchia scuola" rispetto a SSE/WebSocket

### Trade-off Accettato

Per un'app con pochi utenti simultanei su PythonAnywhere free/economico, la latenza di 3 secondi è accettabile. La priorità era **funzionalità base** (pagine che caricano in <1s) vs **real-time perfetto**.

## File Modificati

- `routes/sse.py` - Aggiunti endpoint polling, documentazione aggiornata
- `templates/base.html` - SSE → Polling per notifiche user
- `templates/gamification/dashboard.html` - SSE → Polling
- `templates/gara_detail.html` - SSE → Polling
- `templates/match_detail.html` - SSE → Polling (trio)
- `templates/individual_match/match_detail.html` - SSE → Polling

## Verifiche

1. **Performance**: Caricare pagina con polling attivo, verificare response time <500ms
2. **Notifiche**: Completare match, verificare che toast XP appaia entro ~3s
3. **Multi-utente**: 5+ utenti simultanei, verificare che il server risponda normalmente
4. **Console**: Verificare assenza di errori SSE/SIGPIPE nei log

## Metriche Attese

| Metrica | Prima (SSE) | Dopo (Polling) |
|---------|-------------|----------------|
| Response time pagine | 37-180s (bloccate) | <1s |
| Worker utilization | 100% (bloccati) | <10% |
| Latenza notifiche | ~instant | max 3s |
| Richieste/min/utente | 0 (connessione persistente) | ~20 |

## Riferimenti

- ADR-006: SSE Event Bridge Architecture (superseded per il transport layer)
- uWSGI sync vs async workers documentation
- PythonAnywhere worker limitations
