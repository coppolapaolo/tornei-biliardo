# [006] SSE Event Bridge Architecture

**Data**: 2026-01-09
**Stato**: Partially Superseded (transport layer)
**Decisori**: Paolo, Claude

> **Nota (2026-02-03)**: Il transport layer SSE è stato sostituito con polling HTTP.
> Vedi **ADR-021** per i dettagli. L'architettura Event Bridge rimane valida,
> ma i browser ora usano polling invece di EventSource.

## Contesto

L'applicazione aveva già un sistema SSE funzionante per i trio match (aggiornamenti rack in tempo reale). Tuttavia, altri scenari richiedevano aggiornamenti real-time:

1. **Pagina dettaglio gara**: Vedere match completati, nuovi turni, iscrizioni
2. **Dashboard gamification**: Notifiche XP, level-up, achievement
3. **Dashboard player**: Aggiornamenti sui propri match

### Problema

L'emissione SSE era manuale e duplicata - ogni servizio doveva chiamare `emit_trio_event()` esplicitamente. Questo approccio non scalava bene per nuovi scenari.

## Decisione

### Pattern Event Bridge

Connettere il sistema EventBus esistente (usato per gamification) al sistema SSE tramite un "ponte" che traduce eventi domain in eventi SSE.

```
Domain Action (add_rack, complete_match, etc.)
    ↓
Service Layer (GaraService, MatchService)
    ↓
EventBus.publish(DomainEvent)
    ↓
┌─────────────────────────────────────┐
│  SSE Event Bridge (routes/sse_bridge.py)  │
│  - Sottoscrive a eventi rilevanti   │
│  - Converte in SSE events           │
│  - Instrada a scope appropriati     │
└─────────────────────────────────────┘
    ↓
SSE Event Store (routes/sse.py)
    ↓
SSE Endpoints: /sse/gara/<id>, /sse/user/<id>, /sse/trio/<id>
    ↓
Browser EventSource → UI Update
```

### Componenti Implementati

#### 1. Multi-Scope Event Store (`routes/sse.py`)

```python
_events: Dict[str, Dict[int, List[Tuple]]] = {
    "trio": defaultdict(list),
    "gara": defaultdict(list),
    "user": defaultdict(list),
}

def emit_event(scope: str, scope_id: int, event_type: str, data: dict)
def emit_trio_event(trio_id, event_type, data)  # backward compat
def emit_gara_event(gara_id, event_type, data)
def emit_user_event(user_id, event_type, data)
```

#### 2. SSE Endpoints

| Endpoint | Scopo | Sicurezza |
|----------|-------|-----------|
| `/sse/trio/<id>` | Trio match updates | login_required |
| `/sse/gara/<id>` | Gara updates | login_required |
| `/sse/user/<id>` | User notifications | login_required + own user only |

#### 3. Event Bridge (`routes/sse_bridge.py`)

Sottoscrive ai seguenti eventi domain:

| Evento Domain | SSE Scope | SSE Event |
|---------------|-----------|-----------|
| MatchCompletedEvent | gara, user | match_completed, my_match_completed |
| CompetitionStartedEvent | gara | round_started |
| CompetitionCompletedEvent | gara | gara_completed |
| InscriptionCreatedEvent | gara | inscription_added |
| XPGainedEvent | user | xp_gained |
| LevelUpEvent | user | level_up |
| AchievementUnlockedEvent | user | achievement |

### Trio Events: Pattern Ibrido

Gli eventi trio usano un **pattern dual-emit**:

1. **`emit_trio_event()`**: Per aggiornamenti in tempo reale ai player del trio match
2. **`emit_gara_event()`**: Per aggiornamenti ai director che guardano la pagina gara

```python
# In GaraService.add_trio_rack() e remove_trio_rack():
emit_trio_event(trio_id, "rack_added", result)
if trio.match and trio.match.gara_id:
    emit_gara_event(trio.match.gara_id, "match_updated", {...})
```

**Motivazione**:
- I trio events **non** passano per l'Event Bridge perché richiedono aggiornamenti immediati per-rack
- Ma i director che osservano la gara devono vedere gli aggiornamenti in tempo reale
- La connessione SSE nel match_detail rimane attiva anche dopo `is_completed=True` per supportare undo

## Client-Side Implementation

### Gara Detail (`gara_detail.html`)

```javascript
const eventSource = new EventSource('/sse/gara/' + garaId);
eventSource.addEventListener('match_completed', (e) => location.reload());
eventSource.addEventListener('match_updated', (e) => location.reload());  // trio rack added/removed
eventSource.addEventListener('round_started', (e) => location.reload());
// + exponential backoff reconnection
```

### Gamification Dashboard

```javascript
const eventSource = new EventSource('/sse/user/' + userId);
eventSource.addEventListener('xp_gained', (e) => {
    showToast('XP Guadagnati!', '+' + data.xp_amount + ' XP');
    setTimeout(() => location.reload(), 3000);
});
```

## Alternative Considerate

### Alternativa 1: Espandere Pattern Manuale

**Descrizione**: Aggiungere `emit_gara_event()` chiamate manuali in ogni servizio.

- **Pro**: Semplice, nessun nuovo pattern
- **Contro**: Duplicazione codice, facile dimenticare, non scalabile

### Alternativa 2: WebSocket (Socket.IO)

**Descrizione**: Usare WebSocket bidirezionali invece di SSE.

- **Pro**: Comunicazione bidirezionale, più flessibile
- **Contro**: Più complesso, SSE è sufficiente per notifiche one-way

### Alternativa 3: Redis Pub/Sub

**Descrizione**: Usare Redis per la distribuzione eventi.

- **Pro**: Scalabile multi-server
- **Contro**: Overkill per PythonAnywhere single-server

## Conseguenze

### Positive

- **Separation of Concerns**: Servizi emettono eventi, bridge li traduce
- **Single Source of Truth**: Un evento → propagato ovunque automaticamente
- **Easy Extension**: Nuovo evento SSE = nuovo handler nel bridge
- **Backward Compatible**: Trio eventi continuano a funzionare

### Negative

- **Complessità Architetturale**: Nuovo layer (bridge) da mantenere
- **Debugging**: Più difficile tracciare flusso eventi

### Rischi

- **Memory in SSE Store**: Mitigato da cleanup automatico (60 secondi)
- **Event Storm**: Molti match completati = molte SSE, ma page reload le gestisce

## Verifiche

1. **Gara detail**: Aprire gara su 2 browser, completare match → entrambi vedono aggiornamento
2. **Gamification**: Completare match → toast XP appare sulla dashboard gamification
3. **Trio**: Verificare che funzionalità esistente non regredisca

## File Coinvolti

- `routes/sse.py` - Multi-scope event store
- `routes/sse_bridge.py` - Event handlers (nuovo)
- `app.py` - Import bridge per registrazione handlers
- `models/events/match_events.py` - Aggiunto gara_id a MatchCompletedEvent
- `models/match/state_service.py` - Passa gara_id all'evento
- `templates/gara_detail.html` - SSE client per gara
- `templates/gamification/dashboard.html` - SSE client per user notifications

## Riferimenti

- ADR-005: Trio match implementation (contesto SSE originale)
- `models/events/base.py`: EventBus pattern
- `models/gamification/event_handlers.py`: Esempio pattern handler
