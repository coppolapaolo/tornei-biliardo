# 🏗️ Piano Migrazione Refactoring - Tornei Biliardo

> **Documento Master** per il refactoring architetturale incrementale del sistema tornei biliardo da monolitico a modularized domain-driven design.

**📖 Riferimenti:**
- **Funzionalità Complete**: Vedere [FUNCTIONAL_REQUIREMENTS.md](FUNCTIONAL_REQUIREMENTS.md) per descrizione dettagliata di tutte le funzioni
- **Piano Fase 1**: Vedere [PHASE_1_DETAILED_PLAN.md](PHASE_1_DETAILED_PLAN.md) per implementazione dettagliata

---

## 🎯 **Obiettivi Finali**

### **Problemi Attuali da Risolvere**
- ⚠️ **models.py Monolitico**: 800+ righe, 12+ modelli
- ⚠️ **routes/admin.py Sovraccarico**: Troppe responsabilità
- ⚠️ **utils.py Confuso**: Mix decoratori + permessi + utility
- ⚠️ **Query N+1**: Performance degradation
- ⚠️ **Estensibilità Limitata**: Hardcoded Amalfi, difficile aggiungere tournament types

### **Risultati Attesi**
- ✅ **Domain-Driven Design**: Moduli per dominio (user, tournament, competition, match, playoff)
- ✅ **Strategy Pattern**: Estensibile per nuovi tournament types e classification rules
- ✅ **Role-Based Access**: Admin/Director/Player con permissions granulari
- ✅ **Performance Optimization**: Query ottimizzate, lazy loading
- ✅ **Clean Architecture**: Separation of concerns, testability
- ✅ **Maintainability**: Single responsibility, easy to extend

### **Problemi Attuali da Risolvere**
- ⚠️ **models.py Monolitico**: 800+ righe, 12+ modelli
- ⚠️ **routes/admin.py Sovraccarico**: Troppe responsabilità
- ⚠️ **utils.py Confuso**: Mix decoratori + permessi + utility
- ⚠️ **Query N+1**: Performance degradation
- ⚠️ **Estensibilità Limitata**: Hardcoded Amalfi, difficile aggiungere tournament types

### **Risultati Attesi**
- ✅ **Domain-Driven Design**: Moduli per dominio (user, tournament, competition, match, playoff)
- ✅ **Strategy Pattern**: Estensibile per nuovi tournament types e classification rules
- ✅ **Role-Based Access**: Admin/Director/Player con permissions granulari
- ✅ **Performance Optimization**: Query ottimizzate, lazy loading
- ✅ **Clean Architecture**: Separation of concerns, testability
- ✅ **Maintainability**: Single responsibility, easy to extend

---

## 📐 **Architettura Target**

### **Struttura Finale**
```
models/
├── __init__.py
├── base.py                     # BaseModel + common mixins
├── user/
│   ├── __init__.py
│   ├── models.py              # User, DirectorRequest, TournamentDirector
│   ├── services.py            # UserService, AuthService
│   └── permissions.py         # Role-based permissions
├── tournament/
│   ├── __init__.py
│   ├── models.py              # Tournament
│   └── services.py            # TournamentService
├── competition/
│   ├── __init__.py
│   ├── models.py              # Prova, Inscription
│   ├── services.py            # CompetitionService
│   └── strategies/
│       ├── __init__.py
│       ├── base.py            # AbstractCompetitionStrategy
│       ├── amalfi.py          # AmalfiStrategy
│       ├── round_robin.py     # RoundRobinStrategy
│       └── elimination.py     # EliminationStrategy
├── classification/
│   ├── __init__.py
│   ├── models.py              # Classification, TurnClassification
│   ├── services.py            # ClassificationService
│   └── strategies/
│       ├── __init__.py
│       ├── base.py            # AbstractClassificationStrategy
│       ├── standard.py        # StandardStrategy (wins → diff → order)
│       ├── weighted.py        # WeightedStrategy
│       └── wins_only.py       # WinsOnlyStrategy
├── match/
│   ├── __init__.py
│   ├── models.py              # Match, TrioMatch, Rack, MatchResult
│   └── services.py            # MatchService
├── playoff/
│   ├── __init__.py
│   ├── models.py              # Playoff, PlayoffCriteria
│   ├── services.py            # PlayoffService
│   └── strategies/
│       ├── __init__.py
│       ├── access_criteria.py # TopN, Range, MinProvas
│       └── tiebreaker.py      # Playoff, SpotShot
└── waiting_list/
    ├── __init__.py
    ├── models.py              # WaitingList, WaitingListEntry
    └── services.py            # WaitingListService
```

### **Routes Target**
```
routes/
├── __init__.py
├── auth.py                    # ✅ Authentication
├── main.py                    # ✅ Homepage, redirects
├── shared/
│   ├── __init__.py
│   ├── tournaments.py         # Tournament list (all roles)
│   ├── competitions.py        # Competition details (read-only)
│   └── matches.py             # Match details (read-only)
├── management/                # Admin + Director combined
│   ├── __init__.py
│   ├── dashboard.py           # Role-filtered dashboard
│   ├── tournaments.py         # Tournament CRUD (permission-filtered)
│   ├── competitions.py        # Competition CRUD (permission-filtered)
│   ├── matches.py             # Match management (permission-filtered)
│   ├── participants.py        # Inscription/waiting list management
│   └── playoffs.py            # Playoff management
├── admin/                     # Admin-only routes
│   ├── __init__.py
│   ├── users.py               # User management
│   ├── system.py              # Database reset, system config
│   └── permissions.py         # Role assignments
└── player/                    # Player routes
    ├── __init__.py
    ├── dashboard.py           # Personal dashboard
    ├── profile.py             # Profile management
    └── inscriptions.py        # Personal inscriptions
```

---

## 📋 **FASI MIGRAZIONE**

### **FASE 1: Foundation - User System & Permissions** *(Settimana 1)*

#### **1.1 User Models Refactoring**
**File:** `models/user/`

**Nuovi Modelli:**
```python
# models/user/models.py
class User(UserMixin, db.Model):
    # Existing fields...
    role = db.Column(db.String(20), default='player')  # admin, director, player
    
    # Permission methods
    def can_manage_tournament(self, tournament_id): pass
    def can_manage_competition(self, competition_id): pass
    def can_view_admin_panel(self): pass

class TournamentDirector(db.Model):
    # Existing relationship table
    
class DirectorRequest(db.Model):
    # Existing model
```

**Permission System:**
```python
# models/user/permissions.py
class PermissionManager:
    @staticmethod
    def can_user_manage_tournament(user, tournament_id):
        if user.is_admin:
            return True
        if user.is_director:
            return TournamentDirector.query.filter_by(
                user_id=user.id, tournament_id=tournament_id
            ).first() is not None
        return False
```

**Test Compatibility:** ✅ Mantiene backward compatibility con existing routes

#### **1.2 Migration Tasks**
1. Create `models/user/` directory structure
2. Move User-related models from `models.py` to `models/user/models.py`
3. Create `models/user/permissions.py` with permission logic
4. Update `models/__init__.py` to import from new location
5. Test all existing functionality

**Git Commit:** Make atomic commit with all changes for easy rollback

---

### **FASE 2: Models Domain Separation** *(Settimana 2-3)*

#### **2.1 Tournament Domain**
**File:** `models/tournament/`

```python
# models/tournament/models.py
class Tournament(db.Model):
    # Existing fields + new strategy configuration
    competition_strategy = db.Column(db.String(50), default='amalfi')
    classification_strategy = db.Column(db.String(50), default='standard')
    bye_handling_strategy = db.Column(db.String(50), default='with_x')
    
    def get_strategy_config(self):
        return {
            'competition': self.competition_strategy,
            'classification': self.classification_strategy,
            'bye_handling': self.bye_handling_strategy
        }
```

#### **2.2 Competition Domain**
**File:** `models/competition/`

```python
# models/competition/models.py
class Prova(db.Model):
    # Existing fields...
    # Strategy overrides (null = use tournament default)
    competition_strategy_override = db.Column(db.String(50))
    classification_strategy_override = db.Column(db.String(50))
    bye_handling_strategy_override = db.Column(db.String(50))
    
    def get_effective_strategy(self, strategy_type):
        override = getattr(self, f'{strategy_type}_strategy_override')
        if override:
            return override
        return getattr(self.tournament, f'{strategy_type}_strategy')

class Inscription(db.Model):
    # Existing model
```

#### **2.3 Match Domain**
**File:** `models/match/`

```python
# models/match/models.py
class Match(db.Model):
    # Existing fields...

class TrioMatch(db.Model):
    # Existing model

class Rack(db.Model):
    # Existing model

class MatchResult(db.Model):
    # Existing model
```

#### **2.4 Classification Domain**
**File:** `models/classification/`

```python
# models/classification/models.py
class Classification(db.Model):
    # Enhanced existing model
    
class TurnClassification(db.Model):
    """New: Per-turn classification tracking"""
    id = db.Column(db.Integer, primary_key=True)
    prova_id = db.Column(db.Integer, db.ForeignKey('prova.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    round_number = db.Column(db.Integer)
    position = db.Column(db.Integer)
    matches_won = db.Column(db.Integer)
    point_difference = db.Column(db.Integer)
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow)
```

#### **2.5 Playoff Domain**
**File:** `models/playoff/`

```python
# models/playoff/models.py
class Playoff(Prova):
    """Playoff inherits from Prova"""
    __tablename__ = 'playoff'
    id = db.Column(db.Integer, db.ForeignKey('prova.id'), primary_key=True)
    
    # Playoff-specific fields
    access_criteria_type = db.Column(db.String(50))  # 'top_n', 'range', 'min_provas'
    access_criteria_config = db.Column(db.JSON)      # {"n": 8} or {"start": 5, "end": 12, "min_provas": 3}
    source_provas = db.Column(db.JSON)               # [1, 2, 3] - which provas to consider
    allows_replacements = db.Column(db.Boolean, default=True)  # Handle withdrawals
    
    __mapper_args__ = {
        'polymorphic_identity': 'playoff'
    }

class PlayoffCriteria(db.Model):
    """Tracks who qualifies for playoffs"""
    id = db.Column(db.Integer, primary_key=True)
    playoff_id = db.Column(db.Integer, db.ForeignKey('playoff.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    position = db.Column(db.Integer)  # 1st, 2nd, etc. qualified
    status = db.Column(db.String(20), default='qualified')  # qualified, withdrawn, replaced
    qualified_at = db.Column(db.DateTime, default=datetime.utcnow)
```

#### **2.6 Waiting List Domain**
**File:** `models/waiting_list/`

```python
# models/waiting_list/models.py
class WaitingList(db.Model):
    """Waiting list for limited-capacity provas"""
    id = db.Column(db.Integer, primary_key=True)
    prova_id = db.Column(db.Integer, db.ForeignKey('prova.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    position = db.Column(db.Integer)  # 1, 2, 3...
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    prova = db.relationship('Prova', backref='waiting_list')
    user = db.relationship('User', backref='waiting_entries')

class WaitingListEntry(db.Model):
    """Historical tracking of waiting list movements"""
    id = db.Column(db.Integer, primary_key=True)
    waiting_list_id = db.Column(db.Integer, db.ForeignKey('waiting_list.id'))
    action = db.Column(db.String(20))  # 'added', 'promoted', 'removed'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
```

#### **Migration Tasks Phase 2**
1. Create all domain directories and models
2. Migrate existing data to new structure
3. Update all imports in existing code
4. Test data integrity and existing functionality

**Database Reset:** Update reset functionality to populate with comprehensive example data

---

### **FASE 3: Strategy Pattern Implementation** *(Settimana 4-5)*

#### **3.1 Competition Strategies**
**File:** `models/competition/strategies/`

```python
# models/competition/strategies/base.py
from abc import ABC, abstractmethod

class AbstractCompetitionStrategy(ABC):
    def __init__(self, prova):
        self.prova = prova
        self.tournament = prova.tournament
    
    @abstractmethod
    def create_round_matches(self, round_number, participants):
        """Create matches for a round"""
        pass
    
    @abstractmethod
    def can_create_next_round(self):
        """Check if next round can be created"""
        pass
    
    @abstractmethod
    def get_round_participants(self, round_number):
        """Get participants for a specific round"""
        pass

# models/competition/strategies/amalfi.py
class AmalfiStrategy(AbstractCompetitionStrategy):
    def __init__(self, prova):
        super().__init__(prova)
        from amalfi.engine import AmalfiEngine
        self.engine = AmalfiEngine(prova.tournament, prova)
    
    def create_round_matches(self, round_number, participants=None):
        return self.engine.create_round_matches(self.prova, round_number)
    
    def can_create_next_round(self):
        return self.engine.can_create_next_round()
    
    def get_round_participants(self, round_number):
        return self.engine.get_round_participants(round_number)

# models/competition/strategies/round_robin.py
class RoundRobinStrategy(AbstractCompetitionStrategy):
    def create_round_matches(self, round_number, participants=None):
        # Round Robin implementation
        pass

# models/competition/strategies/elimination.py
class EliminationStrategy(AbstractCompetitionStrategy):
    def create_round_matches(self, round_number, participants=None):
        # Single/Double elimination implementation
        pass
```

#### **3.2 Classification Strategies**
**File:** `models/classification/strategies/`

```python
# models/classification/strategies/base.py
class AbstractClassificationStrategy(ABC):
    @abstractmethod
    def calculate_classification(self, prova_id, round_number=None):
        """Calculate classification for a prova/round"""
        pass
    
    @abstractmethod
    def resolve_tie(self, tied_players, prova):
        """Resolve tie between players"""
        pass

# models/classification/strategies/standard.py
class StandardClassificationStrategy(AbstractClassificationStrategy):
    def calculate_classification(self, prova_id, round_number=None):
        # Current Amalfi logic: wins → point_diff → initial_order
        pass
    
    def resolve_tie(self, tied_players, prova):
        # Return tie resolution options: ['playoff_match', 'spot_shot', 'maintain_tie']
        pass

# models/classification/strategies/weighted.py
class WeightedClassificationStrategy(AbstractClassificationStrategy):
    def calculate_classification(self, prova_id, round_number=None):
        # Different weight for different rounds
        pass

# models/classification/strategies/wins_only.py
class WinsOnlyClassificationStrategy(AbstractClassificationStrategy):
    def calculate_classification(self, prova_id, round_number=None):
        # Only consider wins, ignore point difference
        pass
```

#### **3.3 Playoff Access Strategies**
**File:** `models/playoff/strategies/`

```python
# models/playoff/strategies/access_criteria.py
class PlayoffAccessManager:
    @staticmethod
    def get_qualified_players(playoff):
        criteria_type = playoff.access_criteria_type
        config = playoff.access_criteria_config
        
        if criteria_type == 'top_n':
            return PlayoffAccessManager._get_top_n(playoff, config['n'])
        elif criteria_type == 'range':
            return PlayoffAccessManager._get_range(playoff, config['start'], config['end'])
        elif criteria_type == 'min_provas':
            return PlayoffAccessManager._get_min_provas(playoff, config['start'], config['end'], config['min_provas'])
    
    @staticmethod
    def _get_top_n(playoff, n):
        # Get top N from tournament classification
        pass
    
    @staticmethod
    def _get_range(playoff, start, end):
        # Get positions from start to end
        pass
    
    @staticmethod
    def _get_min_provas(playoff, start, end, min_provas):
        # Get positions from start to end who participated in at least min_provas
        pass
    
    @staticmethod
    def handle_withdrawal(playoff, withdrawn_user):
        # Move first excluded to qualified
        pass
```

#### **Migration Tasks Phase 3**
1. Implement all strategy classes
2. Create strategy factory/registry
3. Update existing Amalfi logic to use strategy pattern
4. Test strategy switching and behavior

---

### **FASE 4: Service Layer Implementation** *(Settimana 6)*

#### **4.1 Service Classes**

```python
# models/competition/services.py
class CompetitionService:
    def __init__(self, prova):
        self.prova = prova
        self.strategy = self._get_strategy()
    
    def _get_strategy(self):
        strategy_name = self.prova.get_effective_strategy('competition')
        return StrategyFactory.get_competition_strategy(strategy_name, self.prova)
    
    def create_next_round(self):
        if not self.strategy.can_create_next_round():
            raise ValueError("Cannot create next round")
        
        participants = self.strategy.get_round_participants(self.prova.current_round + 1)
        matches = self.strategy.create_round_matches(self.prova.current_round + 1, participants)
        
        self.prova.current_round += 1
        db.session.add_all(matches)
        db.session.commit()
        
        return matches

# models/waiting_list/services.py
class WaitingListService:
    @staticmethod
    def add_to_waiting_list(prova_id, user_id):
        # Add user to waiting list
        pass
    
    @staticmethod
    def promote_from_waiting_list(prova_id):
        # When someone unsubscribes, promote first in waiting list
        pass
    
    @staticmethod
    def get_waiting_position(prova_id, user_id):
        # Get user's position in waiting list
        pass

# models/playoff/services.py
class PlayoffService:
    @staticmethod
    def calculate_qualified_players(playoff):
        return PlayoffAccessManager.get_qualified_players(playoff)
    
    @staticmethod
    def create_playoff_inscriptions(playoff):
        qualified = PlayoffService.calculate_qualified_players(playoff)
        for user in qualified:
            inscription = Inscription(
                user_id=user.id,
                prova_id=playoff.id,
                created_at=datetime.utcnow()
            )
            db.session.add(inscription)
        db.session.commit()
```

#### **4.2 Factory Pattern**

```python
# models/strategies/factory.py
class StrategyFactory:
    COMPETITION_STRATEGIES = {
        'amalfi': AmalfiStrategy,
        'round_robin': RoundRobinStrategy,
        'elimination': EliminationStrategy
    }
    
    CLASSIFICATION_STRATEGIES = {
        'standard': StandardClassificationStrategy,
        'weighted': WeightedClassificationStrategy,
        'wins_only': WinsOnlyClassificationStrategy
    }
    
    @classmethod
    def get_competition_strategy(cls, strategy_name, prova):
        strategy_class = cls.COMPETITION_STRATEGIES.get(strategy_name)
        if not strategy_class:
            raise ValueError(f"Unknown competition strategy: {strategy_name}")
        return strategy_class(prova)
    
    @classmethod
    def get_classification_strategy(cls, strategy_name):
        strategy_class = cls.CLASSIFICATION_STRATEGIES.get(strategy_name)
        if not strategy_class:
            raise ValueError(f"Unknown classification strategy: {strategy_name}")
        return strategy_class()
```

---

### **FASE 5: Routes Refactoring** *(Settimana 7-8)*

#### **5.1 Shared Routes (All Roles)**
**File:** `routes/shared/`

```python
# routes/shared/tournaments.py
shared_tournaments_bp = Blueprint('shared_tournaments', __name__)

@shared_tournaments_bp.route('/tournaments')
def tournament_list():
    """List all tournaments - visible to all roles"""
    tournaments = Tournament.query.filter_by(is_active=True).all()
    return render_template('shared/tournament_list.html', tournaments=tournaments)

@shared_tournaments_bp.route('/tournament/<int:tournament_id>')
def tournament_detail(tournament_id):
    """Tournament detail - read-only for all roles"""
    tournament = Tournament.query.get_or_404(tournament_id)
    can_manage = current_user.can_manage_tournament(tournament_id) if current_user.is_authenticated else False
    return render_template('shared/tournament_detail.html', tournament=tournament, can_manage=can_manage)

# routes/shared/competitions.py
shared_competitions_bp = Blueprint('shared_competitions', __name__)

@shared_competitions_bp.route('/competition/<int:prova_id>')
def competition_detail(prova_id):
    """Competition detail - read-only for all roles"""
    prova = Prova.query.get_or_404(prova_id)
    can_manage = current_user.can_manage_competition(prova_id) if current_user.is_authenticated else False
    return render_template('shared/competition_detail.html', prova=prova, can_manage=can_manage)
```

#### **5.2 Management Routes (Admin + Director)**
**File:** `routes/management/`

```python
# routes/management/tournaments.py
management_tournaments_bp = Blueprint('management_tournaments', __name__)

@management_tournaments_bp.route('/tournaments')
@login_required
def tournament_list():
    """Tournament management list - filtered by permissions"""
    if current_user.is_admin:
        tournaments = Tournament.query.all()
    elif current_user.is_director:
        tournaments = current_user.managed_tournaments
    else:
        abort(403)
    
    return render_template('management/tournament_list.html', tournaments=tournaments)

@management_tournaments_bp.route('/tournament/create', methods=['GET', 'POST'])
@login_required
def create_tournament():
    """Create tournament - admin or director"""
    if not (current_user.is_admin or current_user.is_director):
        abort(403)
    
    # Tournament creation logic with strategy configuration
    pass

# routes/management/competitions.py
management_competitions_bp = Blueprint('management_competitions', __name__)

@management_competitions_bp.route('/competition/<int:prova_id>/manage')
@login_required
def manage_competition(prova_id):
    """Manage competition - permission-filtered"""
    prova = Prova.query.get_or_404(prova_id)
    if not current_user.can_manage_competition(prova_id):
        abort(403)
    
    return render_template('management/competition_manage.html', prova=prova)

@management_competitions_bp.route('/competition/<int:prova_id>/create-round', methods=['POST'])
@login_required
def create_round(prova_id):
    """Create next round using strategy pattern"""
    prova = Prova.query.get_or_404(prova_id)
    if not current_user.can_manage_competition(prova_id):
        abort(403)
    
    service = CompetitionService(prova)
    try:
        matches = service.create_next_round()
        flash(f'Turno {prova.current_round} creato con {len(matches)} partite')
    except ValueError as e:
        flash(str(e), 'error')
    
    return redirect(url_for('management_competitions.manage_competition', prova_id=prova_id))
```

#### **5.3 Admin-Only Routes**
**File:** `routes/admin/`

```python
# routes/admin/users.py
admin_users_bp = Blueprint('admin_users', __name__)

@admin_users_bp.route('/users')
@admin_required
def user_list():
    """User management - admin only"""
    users = User.query.all()
    return render_template('admin/user_list.html', users=users)

@admin_users_bp.route('/user/<int:user_id>/promote', methods=['POST'])
@admin_required
def promote_user(user_id):
    """Promote user to director - admin only"""
    user = User.query.get_or_404(user_id)
    user.role = 'director'
    db.session.commit()
    flash(f'Utente {user.username} promosso a direttore')
    return redirect(url_for('admin_users.user_list'))

# routes/admin/system.py
admin_system_bp = Blueprint('admin_system', __name__)

@admin_system_bp.route('/system/reset', methods=['GET', 'POST'])
@admin_required
def reset_database():
    """Database reset - admin only"""
    # Existing reset logic
    pass
```

#### **5.4 Backward Compatibility**
**File:** `routes/legacy.py`

```python
# routes/legacy.py - Temporary backward compatibility
legacy_bp = Blueprint('legacy', __name__)

# Redirect old admin routes to new structure
@legacy_bp.route('/admin/')
def old_admin_dashboard():
    return redirect(url_for('management_tournaments.tournament_list'))

@legacy_bp.route('/admin/tournament/<int:tournament_id>')
def old_tournament_detail(tournament_id):
    return redirect(url_for('shared_tournaments.tournament_detail', tournament_id=tournament_id))

# Add more redirects as needed during migration
```

---

### **FASE 6: Templates & UI** *(Settimana 9)*

#### **6.1 Dynamic Navbar**
**File:** `templates/base.html`

```html
<!-- Dynamic navbar based on user role -->
<nav class="navbar navbar-expand-lg navbar-dark bg-dark">
    <div class="container">
        <a class="navbar-brand" href="{{ url_for('main.index') }}">🎱 Tornei Biliardo</a>
        
        <div class="navbar-nav">
            <!-- All users can see tournaments -->
            <a class="nav-link" href="{{ url_for('shared_tournaments.tournament_list') }}">Tornei</a>
            
            {% if current_user.is_authenticated %}
                <!-- Management section for admin/director -->
                {% if current_user.is_admin or current_user.is_director %}
                    <div class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">
                            Gestione
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="{{ url_for('management_tournaments.tournament_list') }}">I Miei Tornei</a></li>
                            <li><a class="dropdown-item" href="{{ url_for('management_competitions.competition_list') }}">Le Mie Prove</a></li>
                            {% if current_user.is_admin %}
                                <li><hr class="dropdown-divider"></li>
                                <li><a class="dropdown-item" href="{{ url_for('admin_users.user_list') }}">Gestione Utenti</a></li>
                                <li><a class="dropdown-item" href="{{ url_for('admin_system.system_dashboard') }}">Sistema</a></li>
                            {% endif %}
                        </ul>
                    </div>
                {% endif %}
                
                <!-- Player section for all authenticated users -->
                <div class="nav-item dropdown">
                    <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">
                        {{ current_user.username }}
                    </a>
                    <ul class="dropdown-menu">
                        <li><a class="dropdown-item" href="{{ url_for('player.dashboard') }}">La Mia Dashboard</a></li>
                        <li><a class="dropdown-item" href="{{ url_for('player.profile') }}">Il Mio Profilo</a></li>
                        <li><a class="dropdown-item" href="{{ url_for('player.inscriptions') }}">Le Mie Iscrizioni</a></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><a class="dropdown-item" href="{{ url_for('auth.logout') }}">Logout</a></li>
                    </ul>
                </div>
            {% else %}
                <a class="nav-link" href="{{ url_for('auth.login') }}">Login</a>
                <a class="nav-link" href="{{ url_for('auth.register') }}">Registrati</a>
            {% endif %}
        </div>
    </div>
</nav>
```

#### **6.2 Strategy Configuration UI**
**File:** `templates/management/tournament_create.html`

```html
<!-- Tournament creation with strategy selection -->
<form method="POST">
    <div class="mb-3">
        <label class="form-label">Nome Torneo</label>
        <input type="text" class="form-control" name="name" required>
    </div>
    
    <div class="mb-3">
        <label class="form-label">Tipo di Competizione (Default)</label>
        <select class="form-select" name="competition_strategy">
            <option value="amalfi">Sistema Amalfi</option>
            <option value="round_robin">Girone All'Italiana</option>
            <option value="elimination">Eliminazione Diretta</option>
        </select>
        <small class="text-muted">Ogni prova potrà sovrascrivere questa impostazione</small>
    </div>
    
    <div class="mb-3">
        <label class="form-label">Sistema di Classifica (Default)</label>
        <select class="form-select" name="classification_strategy">
            <option value="standard">Standard (Vittorie → Diff Punti → Ordine)</option>
            <option value="weighted">Pesato per Turno</option>
            <option value="wins_only">Solo Vittorie</option>
        </select>
    </div>
    
    <div class="mb-3">
        <label class="form-label">Gestione Numeri Dispari</label>
        <select class="form-select" name="bye_handling_strategy">
            <option value="with_x">Con X (Bye)</option>
            <option value="without_x">Senza X (Trii)</option>
        </select>
    </div>
    
    <!-- Playoff Configuration -->
    <div class="mb-3">
        <div class="form-check">
            <input class="form-check-input" type="checkbox" name="has_playoffs" id="has_playoffs">
            <label class="form-check-label" for="has_playoffs">
                Configura Playoff Finali
            </label>
        </div>
    </div>
    
    <div id="playoff-config" style="display: none;">
        <div class="card">
            <div class="card-body">
                <h6>Configurazione Playoff</h6>
                <div class="mb-3">
                    <label class="form-label">Criterio di Accesso</label>
                    <select class="form-select" name="playoff_access_type">
                        <option value="top_n">Primi N Classificati</option>
                        <option value="range">Dalla Posizione X alla Y</option>
                        <option value="min_provas">Con Partecipazione Minima</option>
                    </select>
                </div>
                <!-- Dynamic config based on selection -->
            </div>
        </div>
    </div>
    
    <button type="submit" class="btn btn-primary">Crea Torneo</button>
</form>

<script>
document.getElementById('has_playoffs').addEventListener('change', function() {
    document.getElementById('playoff-config').style.display = this.checked ? 'block' : 'none';
});
</script>
```

---

## 🧪 **Testing Strategy**

### **Unit Tests per Fase**

#### **Phase 1-2: Models Testing**
```python
# tests/test_models_user.py
def test_user_permissions():
    admin = User(role='admin')
    director = User(role='director')
    player = User(role='player')
    
    assert admin.can_view_admin_panel()
    assert not director.can_view_admin_panel()
    assert not player.can_view_admin_panel()

# tests/test_models_competition.py
def test_strategy_override():
    tournament = Tournament(competition_strategy='amalfi')
    prova = Prova(tournament=tournament, competition_strategy_override='round_robin')
    
    assert prova.get_effective_strategy('competition') == 'round_robin'
    assert tournament.competition_strategy == 'amalfi'
```

#### **Phase 3: Strategy Testing**
```python
# tests/test_strategies.py
def test_amalfi_strategy():
    prova = create_test_prova()
    strategy = AmalfiStrategy(prova)
    
    matches = strategy.create_round_matches(1, [])
    assert len(matches) > 0
    assert strategy.can_create_next_round()

def test_strategy_factory():
    prova = create_test_prova()
    
    strategy = StrategyFactory.get_competition_strategy('amalfi', prova)
    assert isinstance(strategy, AmalfiStrategy)
    
    with pytest.raises(ValueError):
        StrategyFactory.get_competition_strategy('nonexistent', prova)
```

#### **Integration Tests**
```python
# tests/test_integration.py
def test_full_tournament_flow():
    # Create tournament with strategies
    # Create prova with participants
    # Run multiple rounds
    # Test classifications
    # Test playoff qualification
    # Verify all data consistency
    pass
```

---

## 📊 **Performance Monitoring**

### **Query Optimization Checkpoints**
- [ ] **N+1 Query Detection**: Use SQLAlchemy lazy loading and joinedload strategically
- [ ] **Index Creation**: Add indexes for frequent queries (user_id, tournament_id, prova_id)
- [ ] **Pagination**: Implement pagination for large lists (tournaments, users, matches)
- [ ] **Caching**: Add Redis caching for classifications and statistics
- [ ] **Database Profiling**: Monitor slow queries during testing

### **Performance Metrics**
- Tournament list page: < 500ms
- Competition detail page: < 1s  
- Round creation: < 2s for 20 players
- Classification calculation: < 1s for 100+ matches

---

## 🗓️ **Rollout Timeline**

| Settimana | Fase | Deliverables | Testing |
|-----------|------|-------------|---------|
| 1 | User System | User models, permissions | Unit tests |
| 2-3 | Models Domain | All domain models | Integration tests |
| 4-5 | Strategies | Strategy pattern implementation | Strategy tests |
| 6 | Services | Service layer | Service tests |
| 7-8 | Routes | Route refactoring | Route tests |
| 9 | UI/Templates | Template updates | UI testing |
| 10 | Finalization | Bug fixes, optimization | Performance testing |

---

## 🔒 **Risk Management**

### **High Risk Areas**
1. **Model Refactoring**: Breaking imports and relationships
2. **Strategy Switching**: Test all combinations thoroughly
3. **Permission System**: Verify access controls thoroughly
4. **Performance**: Monitor query performance continuously

### **Git Strategy & Rollback Plans**
- **Atomic Commits**: Each phase gets dedicated commits for easy rollback
- **Feature Branches**: Work on feature branches, merge to main when stable
- **Reset Data Evolution**: Update reset functionality progressively with richer example data
- **Tag Releases**: Tag stable points for easy checkout

### **Development Workflow**
```bash
# Start each phase
git checkout -b phase-1-user-system
# Work on phase...
git add . && git commit -m "Phase 1: User system refactoring complete"
git checkout main && git merge phase-1-user-system
git tag v-phase-1-complete

# If rollback needed
git checkout v-previous-phase-tag
# or
git revert commit-hash
```

### **Reset Data Strategy**
- **Phase 1**: Basic users with different roles
- **Phase 2**: Rich tournament/prova examples with different strategies
- **Phase 3**: Complete matches and classifications
- **Final**: Production-ready example data with all features

### **Monitoring**
- Application logs for errors
- Database performance monitoring
- User feedback collection
- Automated test suite execution

---

## ✅ **Definition of Done**

### **Per Phase**
- [ ] All code changes implemented
- [ ] Unit tests passing (>90% coverage)
- [ ] Integration tests passing
- [ ] Performance benchmarks met
- [ ] Documentation updated
- [ ] Code review completed

### **Final**
- [ ] All existing functionality preserved
- [ ] New strategy system working
- [ ] Performance improved from baseline
- [ ] User acceptance testing completed
- [ ] Production deployment successful
- [ ] Rollback plan tested and ready