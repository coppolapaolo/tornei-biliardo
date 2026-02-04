# Match Result Flow - Inserimento Risultati e Validazione

Questo documento descrive il flusso completo di inserimento risultati, conferma e validazione dei match nelle gare.

---

## Indice

1. [Stati del Match](#stati-del-match)
2. [Modalità Distanza](#modalità-distanza)
3. [Flusso Player](#flusso-player)
4. [Flusso Admin/Director](#flusso-admindirector)
5. [Conferma e Validazione](#conferma-e-validazione)
6. [Gestione Pareggi](#gestione-pareggi)
7. [Real-time Updates (Polling)](#real-time-updates-polling)
8. [Diagrammi di Stato](#diagrammi-di-stato)

---

## Stati del Match

```python
class MatchStatus(Enum):
    PENDING = "pending"        # Match creato, nessun rack giocato
    PLAYING = "playing"        # Almeno un rack inserito
    COMPLETED = "completed"    # Distanza raggiunta e confermato
    VALIDATED = "validated"    # Validato da admin (opzionale)
```

### Transizioni di Stato

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    ▼                                     │
PENDING ──────► PLAYING ──────► COMPLETED ──────► VALIDATED
   │               │                │                  │
   │               │                │                  │
   │               ▼                │                  │
   │          (rack removed,       │                  │
   │           score = 0-0)        │                  │
   │               │                │                  │
   └───────────────┘                │                  │
                                    │                  │
                    ┌───────────────┘                  │
                    │ (admin reset)                    │
                    ▼                                  │
                 PENDING ◄────────────────────────────┘
                           (admin reset)
```

---

## Modalità Distanza

### "Al N" (Race to N) - Default

**Configurazione:** `gara.best_of = False` (o `True` con interpretazione race-to)

**Regola:** Il primo giocatore a raggiungere N rack vince.

**Esempi:**
- "Al 5": primo a 5 rack vince (possibili punteggi: 5-0, 5-1, 5-2, 5-3, 5-4)
- Match 5-3: CRISTIAN vince (ha raggiunto 5)

**Validazione automatica:** Quando un giocatore raggiunge la distanza, `is_ready_for_validation()` ritorna `True`.

```python
# RackScore.is_complete() per race-to
if self.distance.is_race_to_racks:
    return (
        self.player1_racks >= winning_racks
        or self.player2_racks >= winning_racks
    )
```

### "Esattamente N" (Exact N)

**Configurazione:** Distanza con total racks fisso

**Regola:** Si giocano esattamente N rack totali, vince chi ne ha di più.

**Esempi:**
- "Esattamente 6": si giocano 6 rack (possibili: 6-0, 5-1, 4-2, 3-3)
- Match 3-3: PAREGGIO (nessun vincitore)

**Validazione:** Quando total_racks == N, `is_ready_for_validation()` ritorna `True`.

```python
# RackScore.is_complete() per exact
else:
    total_racks = self.player1_racks + self.player2_racks
    return total_racks >= self.distance.racks
```

---

## Flusso Player

### 1. Aggiunta Rack

**Endpoint:** `POST /player/match/<id>/racks/add`
**Parametri:** `winner_id` (ID del giocatore che ha vinto il rack)

```
Player clicca "+CRISTIAN" (winner_id=10)
    │
    ▼
MatchService.add_rack_for_player(match_id, user_id, winner_id)
    │
    ▼
ScoringService.add_rack_for_player()
    ├── Crea Rack record
    ├── Aggiorna player1_score / player2_score
    └── Se primo rack: PENDING → PLAYING
    │
    ▼
emit_match_event(match_id, "rack_added", {...})     ← per match_detail
emit_gara_event(gara_id, "match_updated", {...})   ← per gara_detail (directors)
    │
    ▼
Response: { success, player1_score, player2_score, is_ready_for_validation }
```

### 2. Rimozione Rack (Undo)

**Endpoint:** `POST /player/match/<id>/racks/remove`
**Parametri:** `player_id` (ID del giocatore a cui togliere un rack)

```
Player clicca "-CRISTIAN" (player_id=10)
    │
    ▼
MatchService.remove_rack_for_player(match_id, user_id, player_id)
    │
    ▼
ScoringService.remove_rack_for_player()
    ├── Soft-delete ultimo Rack del giocatore
    ├── Aggiorna score
    └── Se score torna 0-0: PLAYING → PENDING (opzionale)
    │
    ▼
emit_match_event + emit_gara_event
```

### 3. Conferma Risultato (Player)

**Endpoint:** `POST /player/match/<id>/confirm`

**Precondizione:** `match.is_ready_for_validation() == True`

```
Player 1 clicca "Accetta"
    │
    ▼
MatchService.confirm_match_result(match_id, user_id)
    │
    ▼
match.confirm_result(user_id)
    ├── player1_confirmed = True
    ├── player1_confirmed_at = now()
    └── Ritorna False (attende player2)
    │
    ▼
Response: { player1_confirmed: true, player2_confirmed: false, completed: false }

═══════════════════════════════════════════════════════════════

Player 2 clicca "Accetta"
    │
    ▼
MatchService.confirm_match_result(match_id, user_id)
    │
    ▼
match.confirm_result(user_id)
    ├── player2_confirmed = True
    ├── player2_confirmed_at = now()
    ├── Entrambi confermati → _complete_match_after_confirmation()
    │       ├── status = COMPLETED
    │       ├── Determina winner_id (o NULL se pareggio)
    │       └── completed_at = now()
    └── Ritorna True
    │
    ▼
Se is_completed e ha tavolo:
    TableAssignmentService.release_and_reassign_table(match_id)
    │
    ▼
emit_match_event(match_id, "result_confirmed", {...})
emit_gara_event(gara_id, "match_completed", {...})  ← trigger reload gara_detail
    │
    ▼
Response: { player1_confirmed: true, player2_confirmed: true, completed: true }
```

### 4. Rifiuta Risultato

**Endpoint:** `POST /player/match/<id>/reject`

```
Player clicca "Rifiuta"
    │
    ▼
MatchService.reject_match_result(match_id, user_id)
    │
    ▼
match.reject_result(user_id)
    ├── Rimuove ultimo rack
    ├── Reset confirmations (player1_confirmed = player2_confirmed = False)
    └── Match torna a PLAYING (se aveva raggiunto distanza)
    │
    ▼
emit_match_event + emit_gara_event("match_updated")
```

### 5. Forfait

**Endpoint:** `POST /player/match/<id>/forfeit`

```
Player clicca "Forfait"
    │
    ▼
MatchService.forfeit_match(match_id, user_id)
    ├── winner_id = avversario
    ├── status = COMPLETED
    ├── is_forfeit = True
    └── Rilascia tavolo
    │
    ▼
emit_match_event(match_id, "forfeit", {...})
emit_gara_event(gara_id, "match_completed", {...})
```

---

## Flusso Admin/Director

### 1. Quick Result (Modal)

**Da:** gara_detail → click "Risultato" su match card

```
Admin inserisce punteggio nel modal (es. 5-2)
    │
    ▼
POST /admin/match/<id>/quick-result
    body: player1_score=5, player2_score=2, start_time=..., end_time=...
    │
    ▼
Crea/aggiorna rack records per raggiungere il punteggio
    │
    ▼
Se distanza raggiunta: is_ready_for_validation = True
```

### 2. Aggiunta Rack Singolo (Admin)

**Endpoint:** `POST /admin/match/<id>/racks/add`

```
Admin clicca "+Player" nella pagina match_detail
    │
    ▼
RackService.add_rack_with_score_update(match_id, winner_id, ...)
    │
    ▼
emit_gara_event(gara_id, "match_updated", {...})
```

### 3. Validazione Admin

**Endpoint:** `POST /admin/match/<id>/validate`

**Precondizione:** `match.is_at_distance == True` (distanza raggiunta)

```
Admin clicca ✓ (validate) su match card
    │
    ▼
validate_match(match_id)
    │
    ├── Se winner_id non impostato:
    │       ├── player1_score > player2_score → winner_id = player1_id
    │       ├── player2_score > player1_score → winner_id = player2_id
    │       └── Pareggio → winner_id = NULL (consentito!)
    │
    ├── validated_by_admin = True
    ├── MatchService.to_completed(match_id)
    │       └── status = COMPLETED
    │
    ├── Rilascia e riassegna tavolo
    │
    └── GaraService.update_round_progression(gara_id)
    │
    ▼
emit_gara_event(gara_id, "match_completed", {...})
```

### 4. Reset Match

**Endpoint:** `POST /admin/match/<id>/reset`

```
Admin clicca "Reset" su match completato
    │
    ▼
MatchService.reset_to_pending(match_id)
    ├── Soft-delete tutti i rack
    ├── player1_score = player2_score = 0
    ├── winner_id = NULL
    ├── player1_confirmed = player2_confirmed = False
    └── status = PENDING
    │
    ▼
emit_gara_event(gara_id, "match_updated", {...})
```

---

## Conferma e Validazione

### Differenza tra Conferma Player e Validazione Admin

| Aspetto | Conferma Player | Validazione Admin |
|---------|-----------------|-------------------|
| **Chi** | Entrambi i giocatori | Admin/Director |
| **Quando** | Distanza raggiunta | Distanza raggiunta |
| **Requisito** | Entrambi devono confermare | Singola azione |
| **Flag** | `player1_confirmed`, `player2_confirmed` | `validated_by_admin` |
| **Stato finale** | `COMPLETED` | `COMPLETED` (può diventare `VALIDATED`) |

### is_player_validated vs validated_by_admin

```python
# Match confermato dai giocatori
match.is_player_validated = (match.player1_confirmed and match.player2_confirmed)

# Match validato dall'admin
match.validated_by_admin = True/False
```

### Quando mostrare il pulsante "Valida"

```jinja2
{# Mostra ✓ solo se: distanza raggiunta E non validato da admin E non confermato da players #}
{% if match.is_at_distance and not match.validated_by_admin and not match.is_player_validated %}
    <button onclick="validateMatchQuick({{ match.id }})">✓</button>
{% endif %}
```

---

## Gestione Pareggi

### Quando può verificarsi un pareggio

Solo in modalità **"Esattamente N"** con N pari:
- "Esattamente 6": possibile 3-3
- "Esattamente 4": possibile 2-2

In modalità **"Al N"** non è possibile il pareggio (uno dei due raggiunge sempre N prima).

### Come viene gestito

```python
# routes/admin/match.py - validate_match()

if match.player1_score > match.player2_score:
    match.winner_id = match.player1_id
elif match.player2_score > match.player1_score:
    match.winner_id = match.player2_id
# else: Pareggio - winner_id rimane NULL (consentito)
```

### Impatto sulla Classificazione

Un match in pareggio:
- `winner_id = NULL`
- Nessuno guadagna "match vinto"
- Entrambi guadagnano i rack fatti
- Il `rack_difference` considera i rack giocati

```python
# Esempio 3-3
player1.racks_won += 3
player1.racks_lost += 3
player1.rack_difference += 0  # (3-3)

player2.racks_won += 3
player2.racks_lost += 3
player2.rack_difference += 0  # (3-3)

# Nessuno incrementa matches_won
```

---

## Real-time Updates (Polling)

### Architettura

```
Player aggiunge rack
    │
    ▼
Service Layer (add_rack_for_player)
    │
    ▼
emit_match_event(match_id, "rack_added", data)    ─► MATCH scope
emit_gara_event(gara_id, "match_updated", data)   ─► GARA scope
    │
    ▼
Event Store (_events dict in routes/sse.py)
    │
    ▼
Browser polling ogni 3 secondi
    GET /sse/poll/gara/<id>?since=<timestamp>
    GET /sse/poll/match/<id>?since=<timestamp>
    │
    ▼
Se evento in reloadOn → location.reload()
```

### Eventi per Scope

#### GARA Scope (gara_detail page)

```javascript
reloadOn: [
    'match_completed',    // Match finito (conferma o forfait)
    'match_updated',      // Punteggio cambiato
    'round_started',      // Nuovo turno creato
    'inscription_added',  // Nuova iscrizione
    'gara_completed'      // Gara terminata
]
```

#### MATCH Scope (match_detail page)

```javascript
reloadOn: [
    'rack_added',         // Rack aggiunto
    'rack_removed',       // Rack rimosso (undo)
    'result_confirmed',   // Player ha confermato
    'forfeit'             // Forfait dichiarato
]
```

### Chi emette cosa

| Route | emit_match_event | emit_gara_event |
|-------|------------------|-----------------|
| `routes/player/matches.py` | ✅ | ✅ |
| `routes/admin/match.py` | ✅ | ✅ |
| `models/competition/services.py` (trio) | ✅ | ✅ |

---

## Diagrammi di Stato

### Match Lifecycle

```
                          ┌──────────────────┐
                          │                  │
                          │     PENDING      │
                          │   (no racks)     │
                          │                  │
                          └────────┬─────────┘
                                   │
                          add_rack │
                                   ▼
                          ┌──────────────────┐
                          │                  │
                          │     PLAYING      │◄────────────────┐
                          │  (racks > 0)     │                 │
                          │                  │                 │
                          └────────┬─────────┘                 │
                                   │                           │
                    distance       │                           │
                    reached        │                    reject │
                                   ▼                    result │
                          ┌──────────────────┐                 │
                          │                  │                 │
                          │ READY FOR        │─────────────────┘
                          │ VALIDATION       │
                          │                  │
                          └────────┬─────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │                                         │
     both players                              admin validates
       confirm                                         │
              │                                         │
              ▼                                         ▼
     ┌──────────────────┐                    ┌──────────────────┐
     │                  │                    │                  │
     │    COMPLETED     │                    │    COMPLETED     │
     │ (player confirm) │                    │ (admin validate) │
     │                  │                    │                  │
     └──────────────────┘                    └──────────────────┘
```

### Confirmation Flow

```
                    ┌─────────────────────────────┐
                    │     READY FOR VALIDATION    │
                    │  player1_confirmed: false   │
                    │  player2_confirmed: false   │
                    └──────────────┬──────────────┘
                                   │
                    Player 1 clicks "Accetta"
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │     WAITING FOR PLAYER 2    │
                    │  player1_confirmed: true    │
                    │  player2_confirmed: false   │
                    └──────────────┬──────────────┘
                                   │
                    Player 2 clicks "Accetta"
                                   │
                                   ▼
                    ┌─────────────────────────────┐
                    │         COMPLETED           │
                    │  player1_confirmed: true    │
                    │  player2_confirmed: true    │
                    │  status: completed          │
                    │  winner_id: determined      │
                    └─────────────────────────────┘
```

---

## File Coinvolti

### Backend

| File | Responsabilità |
|------|----------------|
| `routes/player/matches.py` | Endpoint player per rack e conferma |
| `routes/admin/match.py` | Endpoint admin per validazione e reset |
| `models/match/services.py` | MatchService, RackService |
| `models/match/scoring_service.py` | ScoringService per rack |
| `models/match/base_match.py` | BaseMatchMixin con confirm_result() |
| `models/match/score.py` | RackScore.is_complete() |
| `routes/sse.py` | Event store e polling endpoints |

### Frontend

| File | Responsabilità |
|------|----------------|
| `templates/match_detail.html` | Pagina dettaglio match |
| `templates/gara_detail.html` | Pagina dettaglio gara |
| `templates/components/_match_card.html` | Card match (mobile) |
| `templates/components/_match_result_row.html` | Riga match (desktop) |
| `templates/components/_unified_rack_input.html` | Pulsanti +/- rack |
| `static/js/polling.js` | Utility polling |

---

## Troubleshooting

### Match non passa a COMPLETED dopo conferma

1. Verificare che `is_ready_for_validation()` ritorni `True`
2. Verificare che entrambi i player abbiano confermato
3. Controllare i log per errori in `_complete_match_after_confirmation()`

### Director non vede aggiornamenti real-time

1. Verificare che le route player chiamino `emit_gara_event()`
2. Verificare che il polling sia attivo (check console browser)
3. Verificare che `match.gara_id` non sia NULL

### Pareggio non validabile

1. Verificare che la gara sia in modalità "Esattamente N"
2. Il codice ora permette `winner_id = NULL` per pareggi
3. Se ancora errore, verificare `validate_match()` in `routes/admin/match.py`

### Mobile mostra stato diverso da desktop

1. Verificare che `_match_card.html` usi `is_finished` invece di `match.status == 'completed'`
2. `is_finished = match.status in ['completed', 'validated']`
