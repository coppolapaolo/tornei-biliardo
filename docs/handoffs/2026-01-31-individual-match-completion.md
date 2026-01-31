# Handoff: Individual Match Domain - Completamento

**Data**: 31 Gennaio 2026
**Sessione**: Completamento task dal piano del 30 Gennaio
**Stato**: 6/7 task completati

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

## ⏳ Task Rimanente

### Task 3: Migrazione Completa a FK per Location
**Effort stimato**: 6 ore
**Priorità**: MEDIA (technical debt)

**Descrizione**: Eliminare il dual support (stringa + FK) per location, migrando tutto a `billiard_hall_id`.

**File da modificare**:
- `models/individual_match/models.py` - Deprecare campo `location` stringa
- `migrations/YYYYMMDD_migrate_location_to_fk.py` - Script migrazione (fuzzy match)
- Template che usano `location` direttamente

**Steps**:
1. Creare script che popola `billiard_hall_id` da `location` string (fuzzy match)
2. Aggiornare query per usare solo FK
3. Deprecare campo string (non rimuovere subito per backward compat)

---

## Commit della Sessione

```
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

1. **Task 3**: Completare migrazione FK location quando c'è tempo
2. **UI Testing**: Testare manualmente il flusso VALIDATED in browser
3. **Scheduled Task**: Configurare `send_match_reminders.py` su PythonAnywhere
