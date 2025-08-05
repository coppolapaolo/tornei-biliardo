# 📚 MODULE_SUMMARY.md - Quick Reference Moduli

> **Guida Rapida ai Moduli** - Reference completa per sviluppatori sui moduli implementati e pianificati

---

## 🎯 **Status Legend**
- ✅ **COMPLETATO**: Implementato e testato
- ⚠️ **LEGACY**: Funzionante ma da refactorizzare  
- 🎯 **PLANNED**: Da implementare nelle prossime fasi
- 🔧 **UTILITY**: Tools e configurazioni

---

## 📁 **Core Application Modules**

### **`app.py`** 🔧
```python
Purpose: Flask application factory
Status: ✅ COMPLETATO
Dependencies: config.py, models, routes
Key Functions:
  - create_app(config_name) -> Flask app
  - Blueprint registration
  - Database initialization
  - Admin user creation
```

### **`config.py`** 🔧  
```python
Purpose: Environment configurations
Status: ✅ COMPLETATO
Classes:
  - Config: Base configuration
  - DevelopmentConfig: Debug mode
  - ProductionConfig: Production settings
  - TestingConfig: In-memory DB
```

---

## 🗄️ **Data Layer (models/)**

### **`models/base.py`** ✅
```python
Purpose: Base classes and database instance
Status: ✅ COMPLETATO - Fase 1
Key Components:
  - db: SQLAlchemy instance
  - BaseModel: Common fields (id, created_at, updated_at, deleted_at)
  - TimestampMixin: Auto-timestamps
  - SoftDeleteMixin: Logical deletion
  - safe_commit(): Transaction safety
```

### **`models/user/`** ✅  
```python
Purpose: User domain (authentication, roles, permissions)
Status: ✅ COMPLETATO - Fase 1
Files:
  - models.py: User, TournamentDirector, DirectorRequest
  - permissions.py: PermissionChecker, decoratori RBAC
  - services.py: UserService, DirectorRequestService
Import Examples:
  from models.user.models import User
  from models.user.permissions import PermissionChecker  
  from models.user.services import UserService
```

### **`models/legacy_models.py`** ⚠️
```python
Purpose: Modelli non ancora modularizzati  
Status: ⚠️ LEGACY - Da separare in Fase 2
Models Included:
  - Tournament: Gestione tornei
  - Prova: Competizioni individuali
  - Inscription: Iscrizioni giocatori
  - Match: Incontri e risultati
  - Rack: Tracking dettagliato game
  - Classification: Classifiche
  - MatchResult: Risultati aggregati
  - Playoff: Fasi finali
Technical Debt: 800+ righe, responsabilità multiple
```

### **`models/__init__.py`** ✅
```python
Purpose: Backward compatibility imports
Status: ✅ COMPLETATO
Pattern:
  # Legacy imports (always work)
  from models import User, Tournament, Prova
  
  # New modular imports (available)  
  from models.user.models import User
```

---

## 🎯 **Planned Domain Modules** *(Fase 2-3)*

### **`models/tournament/`** 🏃
```python
Purpose: Tournament management domain
Status: 🏃 IN PROGRESS - Fase 2 Sprint 1 (Domain Separation)
Current Implementation:
  - models.py: Tournament core entity (✅ estratto da legacy)
  - services.py: TournamentService placeholder (✅ struttura base)
  - __init__.py: Domain exports (✅)
  
Import Examples:
  from models import Tournament  # Backward compatible
  from models.tournament.models import Tournament  # New modular
  from models.tournament.services import TournamentService

Future Enhancements (Post-Sprint 1):
  - TournamentSettings: Configuration management
  - TournamentStats: Analytics and reporting
  - Strategy Integration:
    - competition_strategy: "amalfi" | "round_robin" | "swiss"
    - classification_strategy: "standard" | "weighted"
```

### **`models/competition/`** 🏃
```python
Purpose: Competition (Prova) domain  
Status: 🏃 IN PROGRESS - Fase 2 Sprint 1 (Domain Separation)
Current Implementation:
  - models.py: Prova, Inscription entities (✅ estratti da legacy)
  - services.py: ProvaService, InscriptionService placeholders (✅)
  - __init__.py: Domain exports (✅)
  
Import Examples:
  from models import Prova, Inscription  # Backward compatible
  from models.competition.models import Prova, Inscription  # New modular
  from models.competition.services import ProvaService, InscriptionService

Future Enhancements (Post-Sprint 1):
  - CompetitionRules: Rule configurations
  - StandaloneCompetition: Competitions without tournaments
  - Advanced Business Logic:
    - Registration management with waiting lists
    - Competition lifecycle automation
    - Rule enforcement engine
```

### **`models/match/`** ✅
```python
Purpose: Match and game tracking domain
Status: ✅ COMPLETATO - Fase 2 Sprint 1
Files:
  - models.py: Match, Rack, MatchResult, TrioMatch
  - services.py: MatchService, RackService, MatchResultService, TrioMatchService
  - __init__.py: Domain exports
Import Examples:
  from models import Match, Rack  # Backward compatible
  from models.match.models import Match, Rack  # New modular
  from models.match.services import MatchService
Key Features:
  - Match lifecycle management (pending → playing → completed)
  - Rack-by-rack score tracking with validation
  - Trio match special handling
  - Player confirmation system for results
  - Admin validation capabilities
```

### **`models/classification/`** 🎯
```python
Purpose: Ranking and scoring
Status: 🎯 PLANNED - Fase 2
Planned Models:
  - Classification: Final rankings
  - RoundClassification: Per-round standings
  - PlayerStats: Performance metrics
Algorithms:
  - Multiple ranking strategies
  - Configurable scoring systems
  - Advanced analytics
```

---

## 🔧 **Controller Layer (routes/)**

### **`routes/auth.py`** ✅
```python
Purpose: Authentication blueprint
Status: ✅ COMPLETATO
Endpoints:
  - /auth/login: User login
  - /auth/logout: Session termination  
  - /auth/register: New user registration
Dependencies: models.user.models, Flask-Login
```

### **`routes/main.py`** ✅
```python
Purpose: Public pages and dashboard
Status: ✅ COMPLETATO
Endpoints:
  - /: Homepage
  - /dashboard: User dashboard (role-based)
  - /match/<id>: Match details
Dependencies: models, permissions
```

### **`routes/player.py`** ✅
```python
Purpose: Player-specific functionality  
Status: ✅ COMPLETATO
Endpoints:
  - /player/profile: Profile management
  - /player/delete-account: Account deletion
  - /player/statistics: Performance stats
Permissions: Player role required
```

### **`routes/admin.py`** ⚠️
```python
Purpose: Administration interface
Status: ⚠️ LEGACY - Troppo monolitico
Current Scope:
  - Tournament management
  - User administration  
  - Prova management
  - Director assignments
  - Match results
Technical Debt: 400+ righe, responsabilità multiple
Planned Refactoring: Spezzare in admin/, tournament/, competition/
```

---

## 🧠 **Business Logic (amalfi/)**

### **`amalfi/engine.py`** ✅
```python
Purpose: Core tournament algorithm
Status: ✅ COMPLETATO
Class: AmalfiEngine
Key Methods:
  - create_round_matches(): Generate pairings
  - calculate_classification(): Update rankings
  - handle_bye_players(): BYE management
  - validate_configuration(): Setup validation
Performance: < 1s for 20+ players
```

### **`amalfi/__init__.py`** ✅
```python
Purpose: Algorithm exports
Status: ✅ COMPLETATO  
Public Interface:
  - create_amalfi_round_matches()
  - get_amalfi_classification()
  - validate_amalfi_configuration()
```

---

## 🛠️ **Utilities & Tools**

### **`utils/reset_data.py`** ✅
```python
Purpose: Database reset with sample data
Status: ✅ COMPLETATO - Enhanced in Fase 1
Function: reset_database_enhanced()
Sample Data:
  - 1 admin, 2 directors, 11+ players
  - 3 sample tournaments
  - Rich relationships
CLI: python -m utils.reset_data
```

### **`conftest.py`** ✅
```python
Purpose: PyTest configuration
Status: ✅ COMPLETATO
Fixtures:
  - app(): Flask test application
  - Clean in-memory database per test
Path Setup: Automatic project root addition
```

---

## 🧪 **Test Modules (tests/)**

### **User Domain Tests** ✅
```python
test_user_models.py: User model functionality
test_user_services.py: Business logic testing  
test_permissions.py: Permission system
test_reset_roles.py: Database reset validation
Status: ✅ COMPLETATO - Coverage >90%
```

### **Integration Tests** ✅
```python
test_integration_phase1.py: Backward compatibility
test_enhanced_reset.py: Reset functionality
test_user_statistics_complete.py: Stats calculation
Status: ✅ COMPLETATO
```

---

## 📄 **Configuration Files** 🔧

### **Quality & Testing**
```yaml
.flake8: Code quality standards
pytest.ini: Test discovery and markers
pyproject.toml: Coverage configuration + tool settings
requirements-dev.txt: Development dependencies
```

### **Deployment** 
```yaml
requirements.txt: Production dependencies
LICENSE: MIT license
README.md: Project overview and setup
```

---

## 📋 **Import Patterns Reference**

### **Backward Compatible** ✅
```python
# Legacy pattern (sempre funzionante)
from models import User, Tournament, Prova, Match
from models import TournamentDirector, DirectorRequest
```

### **Modular Pattern** ✅
```python
# New pattern (raccomandato per nuovo codice)
from models.user.models import User, TournamentDirector
from models.user.permissions import PermissionChecker
from models.user.services import UserService
```

### **Service Layer** ✅
```python
# Business logic through services
from models.user.services import UserService, DirectorRequestService

user = UserService.create_user("username", "email", "password")
UserService.promote_to_director(user.id, admin_user)
```

### **Permission Checking** ✅
```python
# Granular permissions
from models.user.permissions import PermissionChecker

if PermissionChecker.can_manage_tournament(user, tournament_id):
    # Allow tournament management
```

**Questa reference copre tutti i moduli implementati e fornisce guidance chiara per lo sviluppo.**