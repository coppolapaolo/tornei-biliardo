# 🏗️ REFACTORING_MASTER_PLAN.md - Roadmap Completa

> **Documento Master** per il refactoring architetturale incrementale del sistema tornei biliardo da monolitico a domain-driven design modulare

---

## 🎯 **Obiettivi Finali del Refactoring**

### **🚨 Problemi Attuali da Risolvere**
- ⚠️ **models/legacy_models.py**: 800+ righe monolitiche con 12+ modelli
- ⚠️ **routes/admin.py**: Troppe responsabilità (400+ righe)
- ⚠️ **Query N+1**: Performance degradation su dashboard
- ⚠️ **Hardcoded Amalfi**: Difficile aggiungere nuovi tournament types
- ⚠️ **Estensibilità Limitata**: Classification rules non configurabili

### **✅ Risultati Attesi**
- ✅ **Domain-Driven Design**: Moduli per bounded context (user, tournament, competition, match, classification)
- ✅ **Strategy Pattern**: Estensibile per tournament types e classification rules
- ✅ **Clean Architecture**: Separation of concerns, single responsibility
- ✅ **Performance Optimization**: Query ottimizzate, lazy loading intelligente
- ✅ **Maintainability**: Moduli testabili indipendentemente
- ✅ **Backward Compatibility**: Zero breaking changes durante transizione

---

## 🗺️ **Roadmap Completa a 6 Fasi**

### **🏁 FASE 1: User System & Permissions** *(✅ COMPLETATA)*
**Status**: ✅ **COMPLETATA** - Agosto 2025

**Obiettivi Raggiunti**:
- ✅ Modularizzazione `models/user/` con backward compatibility
- ✅ Permission system granulare con `PermissionChecker`
- ✅ Service layer pattern con `UserService`, `DirectorRequestService`
- ✅ Enhanced reset con sample data professionale
- ✅ Test coverage >90% su dominio user

**Foundation Creata**:
- `models/base.py` con BaseModel, mixins, db instance
- `models/user/` domain completo (models, permissions, services)
- Import aliases in `models/__init__.py` per compatibility
- Quality gates con pytest, flake8, black

**📖 Details**: [docs/phases/PHASE_1_STATUS.md](phases/PHASE_1_STATUS.md)

---

### **🎯 FASE 2: Domain Models Separation** *(🎯 PROSSIMA)*
**Timeline**: 2-3 settimane  
**Status**: 🎯 **PLANNED** - Ready to start

**Obiettivi**:
- 🎯 **Tournament Domain**: `models/tournament/` (Tournament model + services)
- 🎯 **Competition Domain**: `models/competition/` (Prova, Inscription + services)
- 🎯 **Match Domain**: `models/match/` (Match, Rack, MatchResult + services)
- 🎯 **Classification Domain**: `models/classification/` (Classification, RoundClassification + services)
- 🗑️ **Legacy Cleanup**: Eliminazione completa `models/legacy_models.py`

**Target Structure**:
```
models/
├── user/           # ✅ COMPLETATO
├── tournament/     # 🎯 NEW: Tournament management
├── competition/    # 🎯 NEW: Prova, Inscription logic  
├── match/          # 🎯 NEW: Match, Rack tracking
└── classification/ # 🎯 NEW: Ranking & scoring
```

**📖 Details**: [docs/phases/PHASE_2_PLAN.md](phases/PHASE_2_PLAN.md)

---

### **⚙️ FASE 3: Strategy Pattern Implementation** *(📋 PLANNED)*
**Timeline**: 2-3 settimane  
**Dependencies**: Fase 2 completata

**Obiettivi**:
- ⚙️ **Competition Strategies**: Amalfi, RoundRobin, Swiss, Elimination
- ⚙️ **Classification Strategies**: Standard, Weighted, Custom
- ⚙️ **BYE Handling Strategies**: WithX, Rotation, Skip
- ⚙️ **Strategy Factory**: Registry pattern per strategy injection
- ⚙️ **Configuration System**: Tournament-level defaults + Prova overrides

**Strategy Architecture**:
```python
# Abstract base classes
class AbstractCompetitionStrategy(ABC):
    def create_round_matches(self, round_number, participants): pass
    def can_create_next_round(self): pass
    def get_round_participants(self, round_number): pass

# Concrete implementations  
class AmalfiStrategy(AbstractCompetitionStrategy): # Existing logic
class RoundRobinStrategy(AbstractCompetitionStrategy): # New
class SwissStrategy(AbstractCompetitionStrategy): # New
```

**Benefits**:
- Pluggable tournament types senza code changes
- A/B testing di diversi algoritmi
- Easy extension per nuovi formati

---

### **🏛️ FASE 4: Service Layer & Business Logic** *(📋 PLANNED)*
**Timeline**: 2 settimane  
**Dependencies**: Fase 3 completata

**Obiettivi**:
- 🏛️ **Service Classes**: Business logic extraction dai models
- 🏛️ **Factory Pattern**: Strategy injection e object creation
- 🏛️ **Workflow Orchestration**: Complex operations automation
- 🏛️ **Transaction Management**: ACID compliance per complex operations
- 🏛️ **Event System**: Domain events per loose coupling

**Service Architecture**:
```python
class TournamentService:
    def create_tournament_with_defaults(self, config): pass
    def assign_director(self, tournament_id, user_id): pass

class CompetitionService:  
    def __init__(self, prova):
        self.strategy = StrategyFactory.get_competition_strategy(prova)
    def create_next_round(self): pass
    def calculate_final_classification(self): pass

class MatchService:
    def record_match_result(self, match_id, result): pass
    def validate_result_integrity(self, result): pass
```

**Benefits**:
- Complex business logic centralizzato
- Testable business operations
- Clean separation models ↔ business logic

---

### **🚏 FASE 5: Routes & Controller Refactoring** *(📋 PLANNED)*
**Timeline**: 2-3 settimane  
**Dependencies**: Fase 4 completata

**Obiettivi**:
- 🚏 **Blueprint Reorganization**: Domain-aligned routes structure
- 🚏 **Controller Thin**: Logic delegation ai Services
- 🚏 **Permission Integration**: Granular access control per domain
- 🚏 **API Foundation**: RESTful endpoints preparation
- 🚏 **Error Handling**: Consistent error responses

**Target Routes Structure**:
```
routes/
├── auth.py              # ✅ Authentication
├── shared/              # 🎯 Cross-domain public routes
│   ├── tournaments.py   # Tournament list (all roles)
│   └── competitions.py  # Competition details (read-only)
├── management/          # 🎯 Admin + Director combined  
│   ├── tournaments.py   # Tournament CRUD (permission-filtered)
│   ├── competitions.py  # Competition CRUD (permission-filtered)  
│   └── matches.py       # Match management (permission-filtered)
└── admin/               # 🎯 Admin-only routes
    ├── users.py         # User management
    └── system.py        # System administration
```

**Benefits**:
- Eliminazione `routes/admin.py` monolitico (400+ righe)
- Clear separation of concerns
- Permission-aware routing

---

### **🚀 FASE 6: Performance & Advanced Features** *(📋 PLANNED)*
**Timeline**: 3-4 settimane  
**Dependencies**: Fase 5 completata

**Obiettivi**:
- 🚀 **Query Optimization**: N+1 elimination, eager loading
- 🚀 **Caching System**: Redis/Memcached per query pesanti
- 🚀 **Background Jobs**: Celery per operazioni asincrone
- 🚀 **API Layer**: REST API completa per mobile/integrations
- 🚀 **Advanced Analytics**: Performance metrics e reporting
- 🚀 **Monitoring**: APM integration (Sentry, DataDog)

**Performance Targets**:
- Page load times: < 1s (vs current 2s)
- Amalfi algorithm: < 500ms per 50+ players
- Database queries: < 100ms average
- Memory usage: < 100MB per worker

**Advanced Features**:
- Multi-tenant support
- Real-time notifications (WebSocket)
- Advanced reporting (PDF/Excel)
- Mobile PWA optimization

---

## 📊 **Quality Gates per Fase**

### **🧪 Testing Requirements**
- **Unit Tests**: ≥90% coverage su file modificati
- **Integration Tests**: Cross-domain functionality 
- **Performance Tests**: No regression vs baseline
- **Backward Compatibility**: All existing imports work

### **📏 Code Quality Standards**
- **flake8**: Zero violations
- **Black**: 100% formatting compliance  
- **Type Hints**: Su tutte le public functions
- **Documentation**: Comprehensive docstrings

### **🔒 Safety Requirements**
- **Atomic Commits**: Per-phase rollback capability
- **Feature Flags**: Gradual rollout new functionality
- **Database Migrations**: Alembic scripts con rollback
- **Backup Strategy**: Pre-phase state preservation

---

## 🎯 **Success Metrics Finali**

### **📈 Technical Metrics**
- **Modularization**: 0 files >300 righe
- **Test Coverage**: >95% globale 
- **Performance**: 50% improvement page loads
- **Maintainability**: Cyclomatic complexity <10 per function

### **🏆 Business Metrics**  
- **Zero Downtime**: Durante tutto il refactoring
- **Feature Parity**: 100% funzionalità preservate
- **Extensibility**: Nuovi tournament types in <1 day
- **Developer Experience**: Onboarding time <2 hours

### **🔧 Architecture Metrics**
- **Coupling**: Minimized cross-domain dependencies
- **Cohesion**: High within-domain cohesion
- **Scalability**: Ready per 1000+ concurrent users
- **Monitoring**: Real-time health metrics

---

## 🚀 **Ready to Execute**

### **🎯 Current Status**
- ✅ **Fase 1**: User domain separation COMPLETATA
- 🎯 **Fase 2**: Tournament domain separation READY TO START
- 📋 **Fasi 3-6**: Detailed plans available

### **📋 Next Action Items**
1. **Immediate**: Start Fase 2 domain separation  
2. **Week 2-3**: Complete Tournament/Competition/Match/Classification domains
3. **Week 4-5**: Strategy pattern implementation
4. **Month 2**: Service layer + Routes refactoring
5. **Month 3**: Performance optimization + advanced features

**🎱 Questo piano trasformerà il monolite in un sistema modulare, performante e maintainable per gestione tornei professionali.**

---

## 📅 **Timeline Agile (Aggiornata da ADR-0009)**

### **Passaggio da Waterfall ad Agile**
A seguito di ADR-0009, abbiamo abbandonato l'approccio waterfall delle fasi 2-6 per adottare sprint settimanali con rilasci incrementali.

### **Sprint Completati**
- ✅ **Fase 1** (4 settimane): User domain separation - COMPLETATA

### **Sprint In Corso**
- 🏃 **Fase 2 Sprint 1** (1 settimana): Domain separation pura
  - Start: 05/08/2025
  - Goal: Refactoring senza nuove features
  - Deliverables: Tournament, Competition, Match, Classification domains separati

### **Sprint Pianificati**
- 📅 **Fase 2 Sprint 2** (1 settimana): StandaloneCompetition
- 📅 **Fase 2 Sprint 3** (1 settimana): FriendlyMatch
- 📅 **Sprint successivi**: Strategy patterns e features avanzate (priorità TBD)

### **Vantaggi del Nuovo Approccio**
- ✅ **Rilasci settimanali**: Software funzionante ogni sprint
- ✅ **Feedback continuo**: Adattamento basato su input utenti
- ✅ **Riduzione rischio**: Piccoli incrementi testabili
- ✅ **Flessibilità**: Possibilità di cambiare priorità

### **Note**
- Le Fasi 3-6 del piano originale rimangono come backlog
- Le timeline waterfall (2-3 settimane per fase) sono sostituite da sprint agili
- Dettagli implementativi decisi just-in-time per ogni sprint