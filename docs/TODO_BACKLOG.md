# TODO Backlog

Documento generato il 2025-12-29 dopo triage dei TODO comments nel codebase.
**Aggiornato**: 2025-12-29 (Sprint 9 - P0 resolution)

**Totale iniziale**: 28 TODO
**Rimossi (risolti/obsoleti)**: 6
**Risolti in Sprint 9**: 1 (DST)
**Convertiti a Planned Feature**: 1 (Playoff)
**Rimanenti documentati**: 20

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

## P1 - Location/Venue Refactoring (4)

Questi TODO sono correlati: il sistema usa stringhe libere invece di FK a BilliardHall.

### MatchProposal.location
- **File**: `models/individual_match/models.py:59`
- **TODO**: "da modificare con un riferimento alle location nel DB"
- **Impatto**: Nessuna validazione, duplicati, nessun link a venue

### PlayerAvailability.location
- **File**: `models/individual_match/models.py:629`
- **TODO**: "deve essere collegato alle location, non una stringa libera"
- **Impatto**: Stesso problema, duplicazione

### IndividualMatch Fields Duplication
- **Files**: `models/individual_match/models.py:337, 339, 347`
- **TODO**: Campi duplicati da MatchProposal (`location`, `scheduled_at`, `discipline`, etc.)
- **Soluzione suggerita**:
  1. Migrare `location` a `billiard_hall_id` FK
  2. Valutare se IndividualMatch deve fare riferimento a MatchProposal invece di duplicare campi

### Availability Time Format Validation
- **File**: `models/individual_match/availability_service.py:73`
- **TODO**: "bisogna assicurarsi che l'interfaccia forzi questo formato"
- **Impatto**: Parsing può fallire silenziosamente se formato sbagliato

---

## ~~P2 - Design Questions: Challenge/Gara Coupling~~ ✅ PARTIALLY RESOLVED

### Sprint 11 Progress (December 2025)
Domain decoupling completed in FASE 1-3. See `docs/decisions/ADR-004-challenge-gara-decoupling.md`.

**Completed**:
- ✅ FASE 1: Analysis of all coupling usages
- ✅ FASE 2: Moved `GaraChallenge*` models and service to Competition domain
- ✅ FASE 3: Updated all imports across codebase
- ✅ Created `GaraByeChallenge` model for bye replacement
- ✅ Backward compatibility via deprecated re-exports

**Pending** (future sprints):
- ⏳ FASE 4: Migrate bye logic to use `GaraByeChallenge`
- ⏳ FASE 5: Deprecate `ChallengeAttempt.gara_id`
- ⏳ FASE 6: Create database migration script

### ~~ChallengeAttempt.gara_id~~ (TO BE DEPRECATED)
- **File**: `models/challenge/models.py:308`
- **Status**: Will be replaced by `GaraByeChallenge` bridge entity
- **New Location**: `models/competition/gara_bye_challenge.py`

### ~~GaraChallenge Inheritance~~ ✅ RESOLVED
- **Old Location**: `models/challenge/gara_challenge_models.py`
- **New Location**: `models/competition/gara_challenge.py`
- **Solution**: Moved to Competition domain (proper DDD boundaries)

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
1. **P0**: Bug DST - impatta UX quotidianamente
2. **P1**: Location refactoring - preparazione per feature venue-based
3. **P2**: Design questions - valutare solo se si toccano quei file
4. **P3**: Minor - ignorare fino a refactoring maggiore

### Pattern comuni identificati:
- **Stringhe libere invece di FK**: `location` in MatchProposal, IndividualMatch, PlayerAvailability
- **Coupling Challenge-Gara**: ChallengeAttempt sa troppo delle gare
- **Duplicazione campi**: IndividualMatch duplica MatchProposal
- **Astrazioni mancanti**: Score, Referto, SetRack vs Rack

---

*Documento generato durante Sprint 5 del refactoring audit.*
