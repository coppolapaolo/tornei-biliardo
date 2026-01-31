# Handoff: Individual Match Domain - Completamento

**Data**: 31 Gennaio 2026
**Sessione**: Completamento task dal piano del 30 Gennaio
**Stato**: ✅ 7/7 task completati

---

## ✅ Task Completati

### Task 1: Notifica Scadenza Proposta al Proponente
**Commit**: `075adfa`

Quando una proposta scade senza essere accettata, il proponente riceve una notifica.

**File modificato**: `models/individual_match/proposal_service.py`
- Aggiunto in `expire_old_proposals()` e `_expire_pending_proposals()`
- Usa `NotificationFactory.create_bulk_notification()` con `NotificationType.MATCH_DECLINED`

---

### Task 2: Auto-Notifica Proposte Aperte
**Commit**: `075adfa`

Quando viene creata una proposta aperta, i giocatori eligibili (disponibili nella location) ricevono notifica.

**File modificato**: `models/individual_match/proposal_service.py`
- Aggiunto in `create_open_proposal()` dopo `db.session.flush()`
- Usa `AvailabilityService.get_available_players_at_venue()` o `get_available_players_at_location()`
- Notifica con `NotificationType.MATCH_PROPOSAL`

---

### Task 4: Sistema Avversari Frequenti
**Commit**: `16f97b2`

Suggerisce giocatori con cui l'utente ha giocato più spesso quando crea una nuova proposta.

**File modificati**:
- `models/individual_match/statistics_service.py` - Nuovo metodo `get_frequent_opponents(user_id, limit=5)`
- `routes/individual_match.py` - Passa `frequent_opponents` al template
- `templates/individual_match/create_proposal.html` - Sezione "Avversari Frequenti" con bottoni cliccabili

**Query SQLAlchemy**:
```python
opponent_id_expr = case(
    (IndividualMatch.player1_id == user_id, IndividualMatch.player2_id),
    else_=IndividualMatch.player1_id,
)
# Group by opponent, order by count desc
```

---

### Task 5: Reminder Match Programmato
**Commit**: `fde914a`

Invia notifica reminder 2 ore prima di un match programmato.

**File creati/modificati**:
- `models/individual_match/match_lifecycle_service.py` - Nuovo metodo `send_match_reminders(hours_before=2, window_minutes=15)`
- `scripts/send_match_reminders.py` - Script per scheduled task

**Setup PythonAnywhere**:
```bash
# Scheduled task ogni 15 minuti
cd /home/paolocoppola/mysite && python scripts/send_match_reminders.py
```

---

### Task 6: Stato VALIDATED per Match
**Commit**: `fb6c247`

Aggiunge conferma bilaterale prima che il match sia considerato valido.

**File modificati**:
- `models/individual_match/models.py` - Rimosso auto-complete in `add_rack_result()`
- `models/match/base_match.py` - `_complete_match_after_confirmation()` ora imposta `VALIDATED` invece di `COMPLETED`

**Nuovo flusso**:
1. Rack aggiunti → score aumenta
2. Quando distance raggiunta → `is_ready_for_validation()` = True, status resta `IN_PROGRESS`
3. Entrambi i giocatori chiamano `confirm_result()`
4. Quando entrambi confermano → status = `VALIDATED`

---

### Task 7: Feature "Giocane un'altra" (Rematch)
**Commit**: `075adfa`

Permette di avviare rapidamente un nuovo match con lo stesso avversario dopo un match completato.

**File modificati**:
- `routes/individual_match.py` - Nuovo route `rematch(match_id)` che redirect a `create_proposal` con params
- `templates/individual_match/match_detail.html` - Pulsante "Giocane un'altra" per match VALIDATED/COMPLETED
- `templates/individual_match/create_proposal.html` - Banner rematch, form pre-popolato, auto-select opponent

**Flow**:
```
match_detail → click "Giocane un'altra" → redirect con query params → create_proposal pre-compilato
```

---

### Task 3: Migrazione FK Location
**Commit**: `93b0b48`

Migrazione da location string a FK `billiard_hall_id`.

**Stato migrazione** (verificato con `python migrations/populate_billiard_hall_fk.py verify`):
- `gara`: 85.7% con FK
- `match_proposal`: 100% con FK
- `individual_match`: 0 records (tabella vuota)

**File modificati**:
- `models/individual_match/statistics_service.py` - Usa `location_display` per stats
- `templates/individual_match/*.html` - Usano `location_display` invece di `location`

**Note**:
- La migrazione FK esisteva già (`migrations/populate_billiard_hall_fk.py`)
- Le property `location_display` esistevano già sui modelli
- Il campo `location` string è mantenuto per backward compat

---

## Commit della Sessione

```
93b0b48 refactor: use location_display property instead of location string
fb6c247 feat: add VALIDATED status with bilateral confirmation for matches
fde914a feat: add match reminder notifications for upcoming matches
16f97b2 feat: add frequent opponents suggestion in match proposal
075adfa feat: add rematch feature and proposal notifications
```

---

## Test Eseguiti

```bash
pytest tests/new/ -n auto -v -k "individual"
# 25/25 passed

pyright models/individual_match/ routes/individual_match.py
# 0 errors
```

---

## Note Tecniche

- **SSE già attivo**: Le notifiche aggiornano i badge in real-time via SSE esistente
- **Terminologia**: "Race to N" (mai "Best of N")
- **Transazioni**: Tutti i service method usano `@transactional`
- **Template JS**: Usare `|tojson` per stringhe tradotte in JavaScript
- **utcnow deprecation**: Il codebase usa ancora `datetime.utcnow()` per convenzione (vedi CLAUDE.md)

---

## Prossimi Passi Consigliati

1. **UI Testing**: Testare manualmente il flusso VALIDATED in browser
2. **Scheduled Task**: Configurare `send_match_reminders.py` su PythonAnywhere (ogni 15 min)
3. **Production Deploy**: Eseguire `python migrations/populate_billiard_hall_fk.py` su PythonAnywhere
