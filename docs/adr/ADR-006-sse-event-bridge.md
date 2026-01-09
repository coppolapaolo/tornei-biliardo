# [006] SSE Event Bridge Architecture

**Data**: 2026-01-09
**Stato**: Accepted
**Decisori**: Paolo, Claude

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

### Trio Events: Eccezione Deliberata

Gli eventi trio (rack_added, rack_removed, forfeit) **non** passano per l'Event Bridge perché:

1. **Granularità**: Richiedono aggiornamenti per-rack immediati
2. **Non sono Domain Events**: Sono operazioni UI, non eventi business
3. **Funzionano bene**: L'implementazione esistente è testata e stabile

Il pattern `emit_trio_event()` diretto viene mantenuto per i trio.

## Client-Side Implementation

### Gara Detail (`gara_detail.html`)

```javascript
const eventSource = new EventSource('/sse/gara/' + garaId);
eventSource.addEventListener('match_completed', (e) => location.reload());
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
