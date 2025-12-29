# TODO Backlog

Documento generato il 2025-12-29 dopo triage dei TODO comments nel codebase.

**Totale iniziale**: 28 TODO
**Rimossi (risolti/obsoleti)**: 6
**Rimanenti documentati**: 22

---

## P0 - Bug / Problemi Concreti (3)

### DST Timezone Handling
- **File**: `utils/jinja.py:45`
- **Problema**: Il filtro `datetime_local` usa un offset fisso +2 ore invece di gestire correttamente l'ora legale/solare italiana
- **Impatto**: Orari mostrati sbagliati per ~6 mesi all'anno
- **Soluzione suggerita**: Usare `pytz` o `zoneinfo` per conversione corretta UTC → Europe/Rome

### Playoff Feature Not Implemented
- **File**: `models/playoff/models.py:395, 410`
- **Problema**: Codice commentato con chiamate a metodi che non esistono (`GaraService.create_gara`, `GaraService.inscribe_user`)
- **Impatto**: Feature playoff non funzionante
- **Soluzione suggerita**: Decidere se implementare playoff o rimuovere il codice morto

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

## P2 - Design Questions: Challenge/Gara Coupling (3)

Il sistema Challenge ha un accoppiamento con Gara che potrebbe violare separation of concerns.

### ChallengeAttempt.gara_id
- **File**: `models/challenge/models.py:308`
- **TODO**: "non sono convinto che sia la modellazione giusta, perche' challenge non dovrebbe sapere nulla di campionati e gare e round"
- **Contesto**: gara_id usato quando challenge sostituisce la X nel sistema Amalfi

### ChallengeAttempt.gara Relationship
- **File**: `models/challenge/models.py:316`
- **TODO**: "non sono sicuro che debba essere parte del modello"
- **Correlato**: Stesso problema di coupling

### GaraChallenge Inheritance
- **File**: `models/challenge/gara_challenge_models.py:23`
- **TODO**: "forse questo dovrebbe solo estendere Challenge con le informazioni e i metodi relativi alla connessione con la gara"
- **Soluzione suggerita**: Valutare pattern Decorator o Strategy invece di classe separata

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
