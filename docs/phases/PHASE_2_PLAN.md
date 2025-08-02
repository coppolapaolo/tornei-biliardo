# 🎯 PHASE_2_PLAN.md - Tournament Domain Separation

> **Piano Dettagliato Fase 2** - Separazione domini Tournament, Competition, Match e Classification dal monolite legacy

---

## 🎯 **Obiettivi Fase 2**

### **Cosa Realizziamo**
- ✅ **Tournament Domain**: Separare `Tournament` logic da `legacy_models.py`
- ✅ **Competition Domain**: Modularizzare `Prova` e `Inscription` 
- ✅ **Match Domain**: Isolare `Match`, `Rack`, `MatchResult`
- ✅ **Classification Domain**: Separare `Classification` e ranking logic
- ✅ **Backward Compatibility**: Mantenere tutti gli import esistenti funzionanti

### **Cosa NON Facciamo (Rimandato a Fase 3)**
- ❌ Strategy pattern implementation  
- ❌ Algorithm refactoring (Amalfi rimane come è)
- ❌ Routes refactoring (admin.py rimane monolitico)
- ❌ UI/UX changes

---

## 📁 **Target Directory Structure**

### **Post-Fase 2 Organization**
```
models/
├── __init__.py                    # ✅ Import aliases updated
├── base.py                       # ✅ Existing BaseModel infrastructure
├── user/                         # ✅ COMPLETATO in Fase 1
│   ├── models.py                 # User, TournamentDirector, DirectorRequest
│   ├── permissions.py            # PermissionChecker system
│   └── services.py               # UserService, DirectorRequestService
├── tournament/                   # 🎯 NUOVO - Tournament Domain
│   ├── __init__.py              # Exports tournament domain
│   ├── models.py                # Tournament model
│   └── services.py              # TournamentService
├── competition/                  # 🎯 NUOVO - Competition Domain  
│   ├── __init__.py              # Exports competition domain
│   ├── models.py                # Prova, Inscription models
│   └── services.py              # CompetitionService, InscriptionService
├── match/                        # 🎯 NUOVO - Match Domain
│   ├── __init__.py              # Exports match domain
│   ├── models.py                # Match, Rack, MatchResult models
│   └── services.py              # MatchService
└── classification/               # 🎯 NUOVO - Classification Domain
    ├── __init__.py              # Exports classification domain
    ├── models.py                # Classification, RoundClassification models
    └── services.py              # ClassificationService
```

### **Legacy Cleanup**
- 🗑️ **DELETE**: `models/legacy_models.py` (800+ righe eliminate)
- ✅ **PRESERVE**: All existing functionality through new modular structure

---

## 📋 **Task Breakdown Dettagliato**

### **Task 2.1: Tournament Domain** *(Stimate: 4 ore)*

#### **File: `models/tournament/models.py`**
```python
"""
Tournament domain models

Migrates Tournament model from legacy_models.py with enhanced
configuration support for future strategy pattern implementation.
"""
from models.base import BaseModel, db

class Tournament(BaseModel):
    __tablename__ = "tournament"
    
    # Existing fields (migrated from legacy)
    name = db.Column(db.String(100), nullable=False)
    tournament_type = db.Column(db.String(50), nullable=False, default="Amalfi")
    without_x = db.Column(db.Boolean, default=False)
    final_playoffs = db.Column(db.Boolean, default=True)
    challenge_mode = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # Strategy configuration fields (prepared for Phase 3)
    competition_strategy = db.Column(db.String(50), default="amalfi")
    classification_strategy = db.Column(db.String(50), default="standard")
    bye_handling_strategy = db.Column(db.String(50), default="with_x")
    
    # Relationships (updated imports)
    provas = db.relationship("Prova", backref="tournament", lazy=True, 
                           cascade="all, delete-orphan")
    directors = db.relationship("User", secondary="tournament_director",
                              viewonly=True)
    
    # Existing methods preserved
    def can_be_modified(self): # Implementation unchanged
    def can_be_deleted(self): # Implementation unchanged  
    def get_status(self): # Implementation unchanged
    def get_status_badge_class(self): # Implementation unchanged
```

#### **File: `models/tournament/services.py`**
```python
"""
Tournament business logic services
"""
from typing import List, Optional
from models.tournament.models import Tournament
from models.base import db, safe_commit

class TournamentService:
    @staticmethod
    def create_tournament(name: str, config: dict) -> Tournament:
        """Create new tournament with configuration"""
        
    @staticmethod  
    def assign_director(tournament_id: int, user_id: int) -> bool:
        """Assign director to tournament"""
        
    @staticmethod
    def get_tournaments_for_director(user_id: int) -> List[Tournament]:
        """Get tournaments managed by director"""
```

### **Task 2.2: Competition Domain** *(Stimate: 5 ore)*

#### **File: `models/competition/models.py`**
```python
"""
Competition domain models (Prova + Inscription)
"""
from models.base import BaseModel, db

class Prova(BaseModel):
    __tablename__ = "prova"
    
    # All existing fields preserved from legacy_models.py
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournament.id"), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(200))
    description = db.Column(db.Text)
    # ... all other existing fields
    
    # Strategy override fields (for Phase 3)
    competition_strategy_override = db.Column(db.String(50))
    classification_strategy_override = db.Column(db.String(50))
    bye_handling_strategy_override = db.Column(db.String(50))
    
    # Relationships updated with new imports
    inscriptions = db.relationship("Inscription", backref="prova", ...)
    matches = db.relationship("Match", backref="prova", ...)
    
    # All existing methods preserved
    def can_inscribe(self): # Implementation unchanged
    def can_be_modified(self): # Implementation unchanged
    # ... etc

class Inscription(BaseModel):
    __tablename__ = "inscription"
    # All existing fields and methods preserved
```

### **Task 2.3: Match Domain** *(Stimate: 4 ore)*

#### **File: `models/match/models.py`**
```python
"""
Match domain models (Match, Rack, MatchResult)
"""
from models.base import BaseModel, db

class Match(BaseModel):
    __tablename__ = "match"
    # All existing fields preserved
    # All existing methods preserved
    
class Rack(BaseModel):
    __tablename__ = "rack"  
    # All existing fields preserved
    # All existing methods preserved

class MatchResult(BaseModel):
    __tablename__ = "match_result"
    # All existing fields preserved
    # All existing methods preserved
```

### **Task 2.4: Classification Domain** *(Stimate: 3 ore)*

#### **File: `models/classification/models.py`**
```python
"""
Classification and ranking models
"""
from models.base import BaseModel, db

class Classification(BaseModel):
    __tablename__ = "classification"
    # All existing fields preserved
    # All existing methods preserved

class RoundClassification(BaseModel):
    """Enhanced: Per-round classification tracking"""
    __tablename__ = "round_classification"
    
    prova_id = db.Column(db.Integer, db.ForeignKey("prova.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)
    position = db.Column(db.Integer, nullable=False)
    matches_won = db.Column(db.Integer, default=0)
    matches_lost = db.Column(db.Integer, default=0)
    racks_won = db.Column(db.Integer, default=0)
    racks_lost = db.Column(db.Integer, default=0)
    points = db.Column(db.Float, default=0.0)
```

### **Task 2.5: Update Import System** *(Stimate: 2 ore)*

#### **File: `models/__init__.py` Updated**
```python
"""
Updated import aliases maintaining backward compatibility
"""
# Import from new modular structure
from models.user.models import User, TournamentDirector, DirectorRequest
from models.tournament.models import Tournament
from models.competition.models import Prova, Inscription  
from models.match.models import Match, Rack, MatchResult
from models.classification.models import Classification, RoundClassification

# Legacy aliases (PRESERVE existing imports)
__all__ = [
    'User', 'TournamentDirector', 'DirectorRequest',
    'Tournament', 'Prova', 'Inscription', 
    'Match', 'Rack', 'MatchResult',
    'Classification', 'RoundClassification'
]
```

### **Task 2.6: Enhanced Testing** *(Stimate: 4 ore)*

#### **New Test Files**
```python
tests/
├── test_tournament_domain.py     # Tournament model + service tests
├── test_competition_domain.py    # Prova + Inscription tests  
├── test_match_domain.py         # Match + Rack tests
├── test_classification_domain.py # Classification tests
├── test_phase2_integration.py   # Cross-domain integration
└── test_backward_compatibility_phase2.py # Import compatibility
```

---

## 🔧 **Migration Strategy**

### **Step-by-Step Migration Process**
1. **Create Domain Directories**: Setup modular structure
2. **Extract Models**: Move models from `legacy_models.py` to domains
3. **Update Relationships**: Fix cross-domain references  
4. **Create Services**: Business logic extraction
5. **Update Imports**: Maintain backward compatibility
6. **Test Everything**: Comprehensive testing
7. **Delete Legacy**: Remove `legacy_models.py`

### **Risk Mitigation**
- **Atomic Commits**: Each domain migration is separate commit
- **Import Testing**: Verify all existing imports work
- **Functional Testing**: All routes continue working
- **Rollback Plan**: Git revert per domain if issues

---

## 📊 **Quality Gates Fase 2**

### **Code Quality Requirements**
- **Test Coverage**: ≥90% on all new modular code
- **Import Compatibility**: 100% existing imports working
- **Performance**: No regression on page load times
- **Documentation**: Comprehensive docstrings per module

### **Success Criteria**
- [ ] All 4 domains successfully separated
- [ ] `legacy_models.py` completely removed
- [ ] All existing routes/templates working unchanged
- [ ] Test suite passing with >90% coverage
- [ ] Import patterns documented and tested

---

## 🚀 **Benefits Post-Fase 2**

### **Architectural Improvements**
✅ **Clean Domain Separation**: Each domain has single responsibility  
✅ **Modular Development**: Teams can work on domains independently  
✅ **Reduced Coupling**: Clear interfaces between domains  
✅ **Enhanced Testability**: Domain-specific test suites  

### **Foundation for Fase 3**
✅ **Strategy Pattern Ready**: Configuration fields in place  
✅ **Service Layer**: Business logic properly abstracted  
✅ **Clean Import Structure**: Ready for algorithm plugins  
✅ **Comprehensive Testing**: Safety net for major changes  

### **Technical Debt Eliminated**
- 🗑️ **800+ line monolite** `legacy_models.py` removed
- ✅ **Clear responsibilities** per domain
- ✅ **Maintainable code** structure
- ✅ **Future-proof** architecture

**Fase 2 completa la modularizzazione structurale, preparando il terreno per implementazione strategy patterns in Fase 3.**