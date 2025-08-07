# 🏗️ ARCHITETTURA.md - Overview Architetturale

> **Documento Architetturale Master** - Descrizione completa dell'architettura attuale e target del sistema tornei biliardo

---

## 🎯 **Architectural Vision**

### **Design Philosophy**
- **Domain-Driven Design**: Moduli organizzati per bounded context
- **Clean Architecture**: Separation of concerns tra layers
- **Backward Compatibility**: Zero breaking changes durante refactoring
- **Strategy Pattern Ready**: Estensibile per nuovi tournament formats
- **Performance First**: < 2s per ogni operazione utente

### **Current Status: Post Phase 2 Sprint 2**
✅ **User Domain**: Completamente modularizzato (Fase 1)
✅ **Tournament Domain**: Completamente modularizzato (Fase 2 Sprint 1)
✅ **Competition Domain**: Completamente modularizzato (Fase 2 Sprint 1)
✅ **Match Domain**: Completamente modularizzato (Fase 2 Sprint 1)
✅ **Competition Domain**: Completamente modularizzato + Standalone support (Sprint 2)
⚠️ **Legacy**: Solo Playoff da migrare
🎯 **Prossimo**: Sprint 3 - FriendlyMatch feature
---

## 📁 **Directory Structure Attuale**

### **Application Layout**
```
tornei-biliardo/
├── app.py                 # Flask application factory
├── config.py             # Environment configurations
├── models/               # ✅ Domain models (modulari + legacy ridotto)
│   ├── __init__.py       # Backward compatibility imports
│   ├── base.py          # BaseModel + db instance
│   ├── legacy_models.py # ⚠️ Solo Classification, Playoff, PlayerEncounter, RoundClassification
│   ├── user/            # ✅ FASE 1 COMPLETATA
│   │   ├── models.py    # User, TournamentDirector, DirectorRequest
│   │   ├── permissions.py # PermissionChecker + decoratori
│   │   └── services.py  # UserService, DirectorRequestService
│   ├── tournament/      # ✅ FASE 2 SPRINT 1 COMPLETATO
│   │   ├── models.py    # Tournament
│   │   └── services.py  # TournamentService
│   ├── competition/     # ✅ FASE 2 SPRINT 1 COMPLETATO
│   │   ├── models.py    # Prova, Inscription
│   │   └── services.py  # ProvaService, InscriptionService
│   └── match/           # ✅ FASE 2 SPRINT 1 COMPLETATO
│       ├── models.py    # Match, Rack, MatchResult, TrioMatch
│       └── services.py  # MatchService, RackService, etc.
├── routes/              # Flask Blueprints per controller
│   ├── admin.py         # ⚠️ Amministrazione (da spezzare)
│   ├── auth.py          # Autenticazione
│   ├── main.py          # Home e funzioni base
│   └── player.py        # Dashboard giocatori
├── templates/           # Jinja2 templates responsive
├── amalfi/              # ✅ Algoritmo abbinamenti
├── utils/               # ✅ Reset data + utilities
└── tests/               # ✅ Test suite completa
```

### **Domain Organization Target** *(Phase 2-3)*
```
models/
├── base.py              # ✅ Common base classes
├── user/                # ✅ COMPLETATO
├── tournament/          # ✅ COMPLETATO
├── competition/         # ✅ COMPLETATO
├── match/               # ✅ COMPLETATO
├── classification/      # 🎯 PROSSIMO - Ranking & scoring
└── strategy/            # 🎯 FASE 3 - Pluggable algorithms
    ├── competition/     # Amalfi, RoundRobin, Swiss
    ├── classification/  # Standard, Weighted, Custom  
    └── bye_handling/    # WithX, Rotation, Skip
```

---

## 🔧 **Technology Stack**

### **Backend Core**
- **Framework**: Flask 2.3.3 (lightweight, modular)
- **ORM**: SQLAlchemy 3.0.5 (declarative models)
- **Database**: SQLite dev → PostgreSQL prod
- **Migrations**: Alembic (schema evolution)
- **Authentication**: Flask-Login + custom RBAC

### **Frontend Stack**
- **Templates**: Jinja2 (server-side rendering)
- **CSS Framework**: Bootstrap 5 (mobile-first)
- **JavaScript**: Vanilla JS + Bootstrap components
- **Icons**: Bootstrap Icons + Font Awesome
- **Responsive**: Mobile breakpoints validated

### **Development & CI**
```yaml
Quality Tools:
  - flake8: Code quality standards
  - black: Code formatting  
  - pytest: Test framework
  - pytest-cov: Coverage analysis (>90% target)
  
Configuration Files:
  - .flake8: Linting rules
  - pyproject.toml: Tool configurations
  - pytest.ini: Test discovery
  - requirements-dev.txt: Dev dependencies
```

### **Deployment Target**
- **Platform**: PythonAnywhere
- **Environment**: Development → Production pipeline
- **Database Migration**: SQLite → PostgreSQL seamless
- **CI/CD**: per ora no. da analizzare solo dopo la prima versione funzionante

---

## 🗄️ **Data Architecture**

### **Current Schema Overview**
```sql
-- ✅ User Domain (modularizzato)
user (id, username, email, role, password_hash)
tournament_director (tournament_id, user_id) 
director_request (id, user_id, status, processed_by_id)

-- ⚠️ Legacy Schema (da modularizzare)
tournament (id, name, tournament_type, configuration)
prova (id, tournament_id, name, date, status, settings)
inscription (prova_id, user_id, position)
match (id, prova_id, round_number, player1_id, player2_id)
rack (id, match_id, winner_id, sequence)
classification (prova_id, user_id, position, points)
```

### **Relationship Patterns**
- **User ↔ Tournament**: Many-to-Many via TournamentDirector
- **Tournament → Prova**: One-to-Many composition
- **Prova → Match**: One-to-Many per round
- **Match → Rack**: One-to-Many detailed tracking
- **User ↔ Prova**: Many-to-Many via Inscription

### **Data Integrity Rules**
- Foreign key constraints enforced
- Soft delete pattern (BaseModel.deleted_at)
- Audit trail (created_at, updated_at)
- Transaction safety con rollback automatico

---

## 🏛️ **Architectural Patterns**

### **MVC Implementation**
```
Models (models/):
  - Domain entities + business logic
  - SQLAlchemy ORM mappings
  - Service layer for complex operations
  
Views (templates/):
  - Jinja2 server-side rendering
  - Bootstrap responsive components
  - Progressive enhancement con JS
  
Controllers (routes/):
  - Flask Blueprints per domain
  - Request/response handling
  - Permission checking decorators
```

### **Service Layer Pattern** *(Implemented in Phase 1)*
```python
# Separazione business logic dai modelli
UserService.create_user()        # Creation logic
UserService.promote_to_director() # Role management
DirectorRequestService.process() # Workflow logic
```

### **Permission System**
```python
# Granular role-based access control
@login_required
@admin_required
def admin_dashboard():
    pass

# Context-aware permissions  
PermissionChecker.can_manage_tournament(user, tournament_id)
```

---

## ⚡ **Performance Architecture**

### **Database Optimization**
- **Query Optimization**: Eager loading per relationships frequenti
- **Indexing Strategy**: Composite indexes su query patterns
- **Connection Pooling**: SQLAlchemy engine ottimizzato
- **N+1 Prevention**: Select queries con join appropriati

### **Caching Strategy** *(Planned)*
- **Application Cache**: Flask-Caching per query pesanti
- **Template Caching**: Jinja2 cache per components
- **Static Assets**: CDN per Bootstrap/icons

### **Scalability Considerations**
- **Horizontal Scaling**: Stateless design per load balancing
- **Database Scaling**: Read replicas per analytics
- **Session Management**: Database-backed sessions

---

## 🔒 **Security Architecture**

### **Authentication & Authorization**
```python
# Three-tier role system
- Admin: Full system access + user management
- Director: Tournament management assigned
- Player: Own profile + tournament participation

# Password Security
- Werkzeug password hashing
- Session management con Flask-Login
- CSRF protection con Flask-WTF
```

### **Data Protection**
- Input validation su tutte le form
- SQL injection prevention (SQLAlchemy ORM)
- XSS protection (Jinja2 auto-escaping)
- Secure session cookies

---

## 📊 **Business Logic Architecture**

### **Core Algorithms**
```python
# Sistema Amalfi (core business)
amalfi/engine.py:
  - Anti-reincontro algorithm
  - Round classification
  - BYE handling strategies
  - Performance optimization per 20+ players
```

### **Workflow Management**
- **Tournament Lifecycle**: Setup → Registration → Playing → Completed
- **Match Processing**: Results → Rack tracking → Classification update
- **Director Approval**: Request → Admin review → Role assignment

---

## 🚀 **Migration Strategy**

### **Phase Approach**
1. **✅ Phase 1**: User domain separated + permission system
2. **🎯 Phase 2**: Tournament/Competition/Match domain separation  
3. **🎯 Phase 3**: Strategy pattern implementation
4. **🎯 Phase 4**: Advanced features 

### **Backward Compatibility Guarantee**
```python
# Legacy imports continuano a funzionare
from models import User, Tournament, Prova  # ✅ Always works
```

### **Risk Mitigation**
- Atomic commits per phase
- Feature flags per new functionality
- Comprehensive test suite
- Rollback plans documented

**L'architettura è progettata per crescita sostenibile mantenendo semplicità e performance.**