# 📋 Product Backlog - Sistema Tornei Biliardo

> **Last Updated**: 2025-08-08  
> **Product Owner**: Tournament Management Team  
> **Next Sprint Planning**: 2025-08-12

---

## 🎯 Product Vision

Creare il sistema di gestione tornei di biliardo più **completo**, **flessibile** e **user-friendly** del mercato, supportando tutti i formati di competizione con automazione intelligente e analytics avanzate.

---

## 📊 Backlog Overview

| Status | Count | Story Points | Percentage |
|--------|-------|--------------|------------|
| ✅ Completed | 3 | 34 | 20% |
| 🚀 In Progress | 1 | 8 | 5% |
| 📅 Ready | 4 | 42 | 25% |
| 📋 Backlog | 8 | 76 | 45% |
| 🧊 Icebox | 5 | 10 | 5% |
| **TOTAL** | **21** | **170** | **100%** |

---

## 🚀 Current Sprint (Sprint 3)
**Sprint Goal**: Implementare la prima versione di Friendly Matches  
**Dates**: 2025-08-05 to 2025-08-11  
**Velocity Target**: 8 points

| Epic | Story | Points | Status |
|------|-------|--------|--------|
| EPIC-003 | US-003.1: Creazione Match Amichevole | 3 | 🚧 In Progress |
| EPIC-003 | US-003.2: Accettazione/Rifiuto | 3 | 📋 To Do |
| EPIC-003 | US-003.3: Tracking Risultati | 2 | 📋 To Do |

---

## 📅 Next Sprints Planning

### Sprint 4 (2025-08-12 to 2025-08-18)
**Proposed Goal**: Completare Friendly Matches e iniziare Forfait Management  
**Estimated Points**: 8-10

| Epic | Story | Points | Priority | Notes |
|------|-------|--------|----------|-------|
| EPIC-003 | US-003.4: Statistiche Amichevoli | 2 | HIGH | Completamento |
| EPIC-001 | US-001.1: Dichiarazione Forfait | 3 | HIGH | Inizio forfait |
| EPIC-001 | US-001.2: Config Strategia | 5 | HIGH | Core feature |

### Sprint 5-6 (2025-08-19 to 2025-09-01)
**Proposed Goal**: Completare sistema Forfait  
**Estimated Points**: 16

| Epic | Story | Points | Priority |
|------|-------|--------|----------|
| EPIC-001 | Completamento Forfait Management | 8 | HIGH |
| EPIC-004 | Liste d'Attesa Intelligenti (parte 1) | 8 | MEDIUM |

### Epiche future
**Gamification**: un sistema di punti e badge che spingono gli utenti a usare le funzionalità della app e che premiano la fedeltà. Alcune funzionalità sono attivate solo dopo il raggiungimento di livelli oppure a pagamento. 

---

## 📦 Product Backlog (Prioritized)

### 🔴 HIGH Priority (Must Have - Q1 2025)

#### EPIC-001: Gestione Forfait nei Tornei
**Value**: HIGH | **Effort**: 13 pts | **Risk**: MEDIUM
- [ ] US-001.1: Dichiarazione Forfait (3 pts)
- [ ] US-001.2: Configurazione Strategia (5 pts)
- [ ] US-001.3: Gestione Turni Post-Forfait (5 pts)

#### EPIC-005: Competition Strategies
**Value**: HIGH | **Effort**: 34 pts | **Risk**: HIGH
- [ ] US-005.1: Round Robin Implementation (13 pts)
- [ ] US-005.2: Single Elimination (8 pts)
- [ ] US-005.3: Double Elimination (8 pts)
- [ ] US-005.4: Strategy Selection UI (5 pts)

### 🟡 MEDIUM Priority (Should Have - Q2 2025)

#### EPIC-004: Liste d'Attesa Intelligenti
**Value**: MEDIUM | **Effort**: 13 pts | **Risk**: LOW
- [ ] US-004.1: Auto-Enrollment (5 pts)
- [ ] US-004.2: Position Tracking (3 pts)
- [ ] US-004.3: Analytics Liste (5 pts)

#### EPIC-002: Sistema Playoff Avanzato
**Value**: MEDIUM | **Effort**: 21 pts | **Risk**: MEDIUM
- [ ] US-002.1: Configurazione Criteri (8 pts)
- [ ] US-002.2: Gestione Rinunce (8 pts)
- [ ] US-002.3: Tracking Qualificati (5 pts)

#### EPIC-007: Multi-Tournament Management
**Value**: MEDIUM | **Effort**: 21 pts | **Risk**: MEDIUM
- [ ] Cross-tournament analytics
- [ ] Season management
- [ ] League structures

### 🟢 LOW Priority (Nice to Have - Q3 2025)

#### EPIC-006: Gestione Pari Merito Avanzata
**Value**: LOW | **Effort**: 8 pts | **Risk**: LOW
- [ ] Criteri automatici configurabili
- [ ] Playoff spareggio
- [ ] Spot-shot rally

#### EPIC-008: Analytics & Reporting Avanzato
**Value**: MEDIUM | **Effort**: 34 pts | **Risk**: LOW
- [ ] Dashboard analytics
- [ ] Report PDF generazione
- [ ] Export Excel
- [ ] Predictive analytics

#### EPIC-009: Sistema Notifiche
**Value**: MEDIUM | **Effort**: 13 pts | **Risk**: MEDIUM
- [ ] Email notifications
- [ ] Push notifications
- [ ] In-app notifications
- [ ] SMS integration

---

## ✅ Completed Epics

### ✅ Phase 1: User Domain Modularization
**Completed**: 2025-07-15 | **Points**: 13
- User/Director/Admin separation
- Permission system
- Service layer implementation

### ✅ Phase 2 Sprint 1: Domain Separation  
**Completed**: 2025-08-01 | **Points**: 21
- Tournament domain
- Competition domain
- Match domain
- Classification domain

### ✅ Phase 2 Sprint 2: Standalone Competitions
**Completed**: 2025-08-07 | **Points**: 8
- Nullable FK implementation
- Director può creare competizioni standalone
- UI updates

---

## 📈 Velocity Tracking

| Sprint | Planned | Delivered | Velocity |
|--------|---------|-----------|----------|
| Sprint -2 | 13 | 13 | 100% |
| Sprint -1 | 21 | 21 | 100% |
| Sprint 0 | 8 | 8 | 100% |
| Sprint 1 | 8 | 8 | 100% |
| Sprint 2 | 8 | 8 | 100% |
| Sprint 3 | 8 | *In Progress* | - |
| **Average** | **11** | **11.6** | **100%** |

---

## 🎯 Release Planning

### Release 1.0 - "Foundation" ✅
**Released**: 2025-08-01
- User management
- Basic tournament creation
- Amalfi algorithm
- Basic classification

### Release 2.0 - "Competition" 🚧
**Target**: 2025-09-01
- Friendly matches
- Forfait management
- Waiting lists
- Enhanced notifications

### Release 3.0 - "Strategy"
**Target**: 2025-10-01
- Multiple competition formats
- Advanced playoffs
- Cross-tournament features

### Release 4.0 - "Analytics"
**Target**: 2025-11-01
- Advanced reporting
- Predictive analytics
- Season management

---

## 📝 Backlog Refinement Notes

### Refinement Session 2025-08-08
**Participants**: PO, Tech Lead, Directors  
**Decisions**:
1. Forfait management prioritized over new competition strategies
2. Friendly matches reduced scope for MVP
3. Analytics pushed to Q3

### Technical Debt Items
- [ ] Refactor admin routes (monolithic)
- [ ] Optimize Amalfi algorithm for 100+ players
- [ ] Add caching layer for classifications
- [ ] Migrate to PostgreSQL in production

### Definition of Ready
- [ ] User story has acceptance criteria
- [ ] Story points estimated by team
- [ ] Dependencies identified
- [ ] Technical approach agreed
- [ ] UI/UX mockups approved (if applicable)

### Definition of Done
- [ ] Code complete and reviewed
- [ ] Unit tests written (>90% coverage)
- [ ] Integration tests passed
- [ ] Documentation updated
- [ ] Deployed to staging
- [ ] PO acceptance on staging
- [ ] No critical bugs
- [ ] Performance requirements met