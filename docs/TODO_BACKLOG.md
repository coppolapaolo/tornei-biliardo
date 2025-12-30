# TODO Backlog

Documento generato il 2025-12-29 dopo triage dei TODO comments nel codebase.
**Aggiornato**: 2025-12-30 (Sprint 11 completion)

**Totale iniziale**: 28 TODO
**Rimossi (risolti/obsoleti)**: 6
**Risolti in Sprint 9**: 1 (DST)
**Risolti in Sprint 10**: 3 (Location FK)
**Risolti in Sprint 11**: 3 (Challenge/Gara decoupling)
**Convertiti a Planned Feature**: 1 (Playoff)
**Rimanenti documentati**: 14

---

## Resolved in Sprint 9

### ~~DST Timezone Handling~~ ✅ FIXED
- **File**: `utils/jinja.py:45`
- **Risolto in**: Commit `553d1a5`
- **Soluzione**: Usato `zoneinfo.ZoneInfo("Europe/Rome")` per conversione automatica DST
- **Output**: Elemento `<time>` semantico con datetime ISO e classe `datetime-local`
- **Bonus**: Aggiunto `static/js/datetime-local.js` per conversione browser-local opzionale
- **Docs**: `docs/LOCAL_DATE_FORMATTING.md` aggiornato

---

## ~~P1 - Location/Venue Refactoring~~ ✅ RESOLVED IN SPRINT 10

### Sprint 10 Resolution (December 2025)
Location FK migration completed. See commits in Sprint 10.

**Completed**:
- ✅ `billiard_hall_id` FK aggiunto a `Gara`, `MatchProposal`, `IndividualMatch`
- ✅ UI datalist implementata per selezione venue
- ✅ Migration script eseguito
- ✅ Backward compatibility mantenuta (campo `location` string deprecato)

**Previously tracked**:
- ~~MatchProposal.location~~ - Migrato a `billiard_hall_id`
- ~~PlayerAvailability.location~~ - Usa datalist con BilliardHall
- ~~IndividualMatch Fields Duplication~~ - `billiard_hall_id` FK aggiunto

---

## ~~P2 - Design Questions: Challenge/Gara Coupling~~ ✅ FULLY RESOLVED IN SPRINT 11

### Sprint 11 Resolution (December 2025)
Domain decoupling fully completed. See `docs/adr/ADR-004-challenge-gara-decoupling.md`.

**All Phases Completed**:
- ✅ FASE 1: Analysis of all coupling usages
- ✅ FASE 2: Moved `GaraChallenge*` models and service to Competition domain
- ✅ FASE 3: Updated all imports across codebase
- ✅ FASE 4: Migrated bye logic to use `GaraByeChallenge`
- ✅ FASE 5: Deprecated `ChallengeAttempt.gara_id` with comments
- ✅ FASE 6: Created database migration script
- ✅ FASE 7: ADR documentation complete

**Key Changes**:
- `GaraByeChallenge` bridge entity created in `models/competition/gara_bye_challenge.py`
- `GaraChallenge*` models moved to `models/competition/gara_challenge.py`
- Dependency direction inverted: Competition → Challenge (correct DDD)
- Backward compatibility via deprecated re-exports

---

## Planned Features (non bug, feature incomplete)

### Playoff System
- **File**: `models/playoff/models.py`
- **Stato**: Modelli esistono, integrazione con servizi pendente
- **Documentazione**: `docs/TODO_PLAYOFF_IMPLEMENTATION.md`
- **Prossimi passi**:
  1. Creare `PlayoffService` con `create_playoff_gara()` e `inscribe_qualified_players()`
  2. Aggiungere routes admin per configurazione playoff
  3. UI per conferma qualificazione giocatori

---

## P2 - Design Questions: Match/Rack Abstraction (6)

Riflessioni su possibili astrazioni per Score, Referto, e Rack.

### Continuous Pool Scoring
- **File**: `models/match/models.py:525`
- **TODO**: "nel pool continuo, un rack non e' detto che abbia un vincitore"
- **Contesto**: Pool continuo usa punteggi progressivi, non winner per rack
- **Impatto**: Feature non supportata

### Referto Class Abstraction
- **Files**: `models/match/models.py:528, 589`
- **TODO**: "forse questo va astratto con una classe Referto"
- **Contesto**: Campi `reported_by_id`, `confirmed_by_player`, `validated_by_admin` su Rack
- **Soluzione suggerita**: Valutare se creare classe `MatchReport` per tracciare chi segnala cosa

### Score Abstraction
- **File**: `models/match/models.py:629`
- **TODO**: "se si astrae Score allora qui va modificato"
- **Dipendenza**: Da decisione su classe Score

### TrioMatch Winner Nullable
- **File**: `models/match/models.py:638`
- **TODO**: "non e' detto che esista un winner"
- **Contesto**: Trio match potrebbe finire in pareggio?
- **Impatto**: Modello assume sempre un vincitore

### SetRack vs Rack
- **File**: `models/match/set_models.py:337`
- **TODO**: "non sono convinto che sia necessario e che non si possa usare Rack"
- **Contesto**: SetRack duplica parte della logica di Rack
- **Soluzione suggerita**: Valutare unificazione con discriminatore

### Multi-Discipline Complexity
- **File**: `models/match/set_models.py:68`
- **TODO**: "questo mi sembra sovraingegnerizzato"
- **Contesto**: `configure_multi_discipline` ha logica complessa per casi rari
- **Impatto**: Basso - feature opzionale

---

## P2 - Design Questions: Discipline Modeling (1)

### Discipline Field Structure
- **File**: `models/match/models.py:407`
- **TODO**: "controllare se la modellazione cosi' e' ok. la disciplina e' un campo strutturato?"
- **Contesto**: Discipline come stringa semplice vs struttura per multi-disciplina (es. APA: primi 4 rack palla 8, poi palla 9)
- **Decisione**: Se app funziona senza struttura, lasciare stringa

---

## P3 - Minor / Low Priority (5)

### Availability Time Format Validation
- **File**: `models/individual_match/availability_service.py:73`
- **TODO**: "bisogna assicurarsi che l'interfaccia forzi questo formato"
- **Impatto**: Parsing può fallire silenziosamente se formato sbagliato

### IndividualMatch Score Delegation
- **File**: `models/individual_match/models.py:481`
- **TODO**: "forse questo va delegato ad un servizio che astrae il punteggio"
- **Contesto**: Logica di scoring in model invece che in service
- **Impatto**: Basso - funziona ma viola separation of concerns

### Unknown Context TODO
- **File**: `models/individual_match/models.py:570`
- **TODO**: "non sono convintissimo che serva questo e non sia sufficiente"
- **Nota**: Contesto non chiaro, richiede investigazione

---

## Note per Implementazione

### Priorità suggerita:
1. ~~**P0**: Bug DST~~ ✅ Risolto Sprint 9
2. ~~**P1**: Location refactoring~~ ✅ Risolto Sprint 10
3. **P2**: Design questions - valutare solo se si toccano quei file
4. **P3**: Minor - ignorare fino a refactoring maggiore

### Pattern comuni risolti:
- ~~**Stringhe libere invece di FK**~~: ✅ Migrato a `billiard_hall_id` FK (Sprint 10)
- ~~**Coupling Challenge-Gara**~~: ✅ Invertito a Competition → Challenge (Sprint 11)

### Pattern ancora presenti:
- **Duplicazione campi**: IndividualMatch duplica MatchProposal (valutare se necessario)
- **Astrazioni mancanti**: Score, Referto, SetRack vs Rack (P2 - low priority)

---

*Documento aggiornato durante Sprint 11 del refactoring.*
