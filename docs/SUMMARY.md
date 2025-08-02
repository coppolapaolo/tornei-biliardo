# 📋 SUMMARY.md - Context per Chat

> **Documento Master per Context Chunking** - Panoramica rapida dello stato attuale del progetto per interazioni chat

---

## 🎯 **Stato Attuale Progetto**

### **Versione & Status**
- **Versione Attuale**: v3.0.0 (Sistema Amalfi completo)
- **Fase Refactoring**: ✅ **Fase 1 COMPLETATA** - User Domain modularizzato
- **Architettura**: Flask MVC con Blueprints, SQLAlchemy ORM, Bootstrap 5
- **Deployment**: PythonAnywhere (SQLite dev → PostgreSQL prod)

### **Obiettivo Refactoring**
Trasformare monolite in **domain-driven design modulare** mantenendo backward compatibility e implementando strategy pattern per tornei multi-formato.

---

## 📁 **Struttura Modulare Attuale** *(Post Fase 1)*

### **Directory Structure**
```
models/
├── __init__.py           # Import aliases per backward compatibility
├── base.py              # ✅ BaseModel + mixins + db instance
├── legacy_models.py     # ⚠️ Tournament, Prova, Match, etc. (da modularizzare)
└── user/                # ✅ COMPLETATO - Dominio User
    ├── __init__.py      # Exports pubblici dominio
    ├── models.py        # User, TournamentDirector, DirectorRequest
    ├── permissions.py   # PermissionChecker class + decoratori
    └── services.py      # UserService, DirectorRequestService
```

### **Import Pattern Funzionante**
```python
# ✅ Existing code continua a funzionare
from models import User, Tournament, Prova

# ✅ Nuovi import modulari disponibili  
from models.user.models import User
from models.user.permissions import PermissionChecker
from models.user.services import UserService
```

---

## 🔧 **Stack Tecnologico & Configurazioni**

### **Core Stack**
- **Backend**: Python 3.8+, Flask 2.3.3, SQLAlchemy 3.0.5
- **Auth**: Flask-Login 0.6.3 con custom role system (admin/director/player)
- **Frontend**: Bootstrap 5 + Jinja2 templates responsive
- **Database**: SQLite dev → PostgreSQL prod (Alembic migrations)

### **Quality Gates & CI**
```
Configurazioni attive:
├── .flake8              # Code quality standards
├── pyproject.toml       # Coverage config + tool settings  
├── pytest.ini          # Test discovery + markers
├── requirements-dev.txt # flake8, black, pytest, pytest-cov
└── conftest.py         # Test fixtures
```

**Quality Thresholds:**
- Performance: < 2s per operazione user
- Test Coverage: ≥90% sui file modificati (strategia incrementale)
- Mobile responsive: Bootstrap 5 breakpoints
- Error handling: Graceful 40x/50x con flash messages

---

## 🏆 **Funzionalità Principali Implementate**

### **Sistema Amalfi (Core Business)**
- ✅ **Abbinamenti automatici**: Anti-reincontro con PlayerEncounter tracking
- ✅ **Classifiche real-time**: RoundClassification per ogni turno
- ✅ **Gestione BYE**: Configurabile con/senza X
- ✅ **Multi-round**: Supporto tornei con rounds variabili

### **User Management (Fase 1 ✅)**
- ✅ **Role-based access**: Admin/Director/Player con permission granulari
- ✅ **Director workflow**: Richiesta promozione → Approvazione admin
- ✅ **Tournament assignment**: Direttori assegnabili a tornei specifici
- ✅ **User statistics**: Win rate, matches played, tournament participation

### **Tournament Management**
- ✅ **Multi-tournament**: Gestione tornei paralleli
- ✅ **Prova lifecycle**: Setup → Iscrizioni → Playing → Completed
- ✅ **Match tracking**: Risultati dettagliati con rack-by-rack
- ✅ **Admin tools**: Dashboard completa per gestione

---

## ⚠️ **Technical Debt Identificato**

### **Legacy Code (da modularizzare)**
- 📁 `models/legacy_models.py` - 800+ righe monolitiche
- 📁 `routes/admin.py` - Troppe responsabilità
- 📁 `utils.py` - Mix di funzioni eterogenee

### **Performance Issues**
- 🐌 Query N+1 su alcune dashboard
- 🐌 Lazy loading non ottimizzato
- 🐌 Mancano indici su relazioni frequently-queried

### **Estensibilità Limitata**
- 🔒 Algoritmo Amalfi hardcoded (servono strategy patterns)
- 🔒 Difficile aggiungere nuovi tournament types
- 🔒 Classification rules non configurabili

---

## 🚀 **Roadmap Prossime Fasi**

### **Fase 2: Tournament Domain Separation** *(In Planning)*
```
Obiettivi:
├── models/tournament/     # Separare Tournament logic
├── models/competition/    # Prova, Inscription domain  
├── models/match/         # Match, Rack domain
└── models/classification/ # Classification domain
```

### **Fase 3: Strategy Pattern Implementation**
```
Obiettivi:
├── strategy/competition/     # Amalfi, RoundRobin, Swiss
├── strategy/classification/  # Standard, Weighted, Custom
└── strategy/bye_handling/   # WithX, Rotation, Skip
```

### **Fase 4: Advanced Features**
- Multi-tournament cross-qualification
- Advanced analytics & reporting
- REST API per integrations
- Mobile app support

---

## 📖 **Documentazione References**

### **File Chiave da Consultare** *(Post-ristrutturazione)*
- 📄 `docs/ARCHITETTURA.md` - Overview architetturale
- 📄 `docs/MODULE_SUMMARY.md` - Quick reference moduli
- 📄 `docs/phases/PHASE_1_STATUS.md` - Status Fase 1 completata
- 📄 `docs/phases/PHASE_2_PLAN.md` - Piano prossima fase

### **ADR Decisioni Architetturali**
- 📄 `docs/ADR/ADR-0002-separazione_dominio_user.md` - Rationale modularizzazione
- 📄 `docs/ADR/ADR-0003-sistema_permessi_e_decoratori.md` - Permission system
- 📄 `docs/ADR/ADR-0006-strategia_incrementale_copertura_test.md` - Testing strategy

---

## 💡 **Context per Sviluppo**

### **Quando Modificare Codice**
1. **Leggere sempre** il codice esistente e analizzare pattern
2. **Mantenere backward compatibility** su import esistenti  
3. **Seguire principi modularità**: Single responsibility, clean interfaces
4. **Test coverage ≥90%** sui file modificati
5. **Aggiornare documentazione** e ADR per decisioni architetturali

### **Performance & Quality**
- Tutti i cambiamenti devono passare quality gates
- Mobile-first approach con Bootstrap 5
- Error handling graceful con flash messages
- DB transaction safety con rollback su errori

**Questo documento fornisce il context essenziale per interazioni chat produttive senza overhead.**