# 🎯 PHASE_2_PLAN.md - Domain Separation (Approccio Agile)

> **Piano Agile Fase 2** - Separazione domini con sprint settimanali e nuove features incrementali

---

## ✅ Pre-requisiti (Verificati)

- [x] Fase 1 completata
- [x] User domain funzionante
- [x] Test suite passing
- [x] ADR-0009 approvato (eventi non-torneo)

---

## 🚀 **Approccio Agile - Sprint Settimanali**

### **Sprint 1: Domain Separation Pure** (Settimana 1)
**Goal**: Separare i domini SENZA aggiungere features

#### Deliverables:
- [ ] `models/tournament/` - Tournament model separato
- [ ] `models/competition/` - Prova, Inscription separati
- [ ] `models/match/` - Match, Rack, MatchResult, TrioMatch separati
- [ ] `models/classification/` - Classification, RoundClassification, PlayerEncounter
- [ ] Rimozione `legacy_models.py`
- [ ] 100% backward compatibility
- [ ] Tutti test passano

#### Definition of Done:
- App funziona identica a prima
- Import da `models` continuano a funzionare
- Coverage ≥90% sui file modificati
- Zero breaking changes

---

### **Sprint 2: StandaloneCompetition** (Settimana 2)
**Goal**: Director può creare competizioni senza torneo

#### User Stories:
```
Come Director
Voglio creare una competizione standalone
Per organizzare eventi singoli senza dover creare un torneo
```

#### Deliverables:
- [ ] Modello `StandaloneCompetition` in `models/competition/`
- [ ] Route per creare/gestire competizioni standalone
- [ ] UI per director dashboard
- [ ] Classification per competizioni standalone (se multi-round)
- [ ] Test e documentazione

---

### **Sprint 3: FriendlyMatch** (Settimana 3)
**Goal**: Player può organizzare match amichevoli

#### User Stories:
```
Come Player
Voglio organizzare match amichevoli
Per giocare partite informali con tracking risultati
```

#### Deliverables:
- [ ] Modello `FriendlyMatch` in `models/match/`
- [ ] Sistema privacy (public/friends/private)
- [ ] Route per creare/gestire match amichevoli
- [ ] UI per player dashboard
- [ ] Statistiche separate per match amichevoli
- [ ] Test e documentazione

---

## 📋 **Backlog** (Da prioritizzare dopo Sprint 3)

### **Epic: Statistiche Unificate**
- [ ] Statistiche globali (tutto incluso)
- [ ] Statistiche ufficiali (solo tornei)
- [ ] Statistiche per tipo evento
- [ ] Dashboard con filtri

### **Epic: Privacy Granulare**
- [ ] Privacy per singolo match
- [ ] Privacy per competizione
- [ ] Visibilità profilo giocatore

### **Epic: Classification Strategies**
- [ ] Refactor per supportare diverse strategie
- [ ] Strategy pattern implementation
- [ ] Configurazione per competizione

---

## 📁 **Struttura Target Sprint 1**

```
models/
├── __init__.py          # Import aliases mantenuti
├── base.py             # BaseModel esistente
├── user/               # ✅ Già completato
├── tournament/         # 🎯 Sprint 1
│   ├── __init__.py
│   ├── models.py       # Tournament
│   └── services.py     # TournamentService
├── competition/        # 🎯 Sprint 1 + Sprint 2
│   ├── __init__.py
│   ├── models.py       # Prova, Inscription, (StandaloneCompetition)
│   └── services.py
├── match/              # 🎯 Sprint 1 + Sprint 3
│   ├── __init__.py
│   ├── models.py       # Match, Rack, MatchResult, TrioMatch, (FriendlyMatch)
│   └── services.py
└── classification/     # 🎯 Sprint 1
    ├── __init__.py
    ├── models.py       # Classification, RoundClassification, PlayerEncounter
    └── services.py
```

---

## 🏃 **Execution Plan Sprint 1**

### Day 1-2: Tournament + Competition domains
- Extract Tournament → `models/tournament/`
- Extract Prova, Inscription → `models/competition/`
- Create basic services
- Update imports

### Day 3-4: Match + Classification domains
- Extract Match, Rack, etc → `models/match/`
- Extract Classification, etc → `models/classification/`
- Create basic services
- Fix circular dependencies

### Day 5: Integration & Testing
- Remove `legacy_models.py`
- Run full test suite
- Fix any broken imports
- Verify all routes work

### Day 6-7: Documentation & Review
- Update ADRs
- Code review
- Performance testing
- Sprint retrospective

---

## 🎯 **Success Metrics**

### Sprint 1:
- [ ] Zero breaking changes
- [ ] All tests pass
- [ ] Performance unchanged
- [ ] Clean domain separation

### Overall:
- [ ] Directors can create standalone competitions (Sprint 2)
- [ ] Players can create friendly matches (Sprint 3)
- [ ] Clean, maintainable architecture

---

**Agile Manifesto Applied**:
- Working software over comprehensive documentation
- Responding to change over following a plan
- Customer collaboration over contract negotiation