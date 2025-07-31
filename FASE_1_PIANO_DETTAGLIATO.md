# 📋 Fase 1: User System & Permissions - Piano Dettagliato

> **Refactoring del sistema utenti e permessi** - Fondazione per il domain-driven design

---

## 🎯 **Obiettivi Fase 1**

### **Cosa Realizziamo**
- ✅ **Modularizzazione User Domain**: Separare User logic dal monolitico `models.py`
- ✅ **Sistema Permessi Granulari**: Implementare permission checking per Admin/Director/Player
- ✅ **Foundation per Fasi Successive**: Creare base solida per domain separation
- ✅ **Backward Compatibility**: Mantenere funzionamento esistente durante transizione

### **Cosa NON Facciamo (Rimandato)**
- ❌ Altri domini (tournament, competition, etc.)
- ❌ Strategy pattern implementation  
- ❌ Routes refactoring
- ❌ UI changes

---

## 📁 **Struttura Target Fase 1**

### **Directory Structure**
```
models/
├── __init__.py                 # ✅ Updated imports
├── base.py                     # ✅ NEW: BaseModel + mixins
├── user/
│   ├── __init__.py            # ✅ NEW: User domain exports
│   ├── models.py              # ✅ NEW: User, TournamentDirector, DirectorRequest
│   ├── permissions.py         # ✅ NEW: Permission checking logic
│   └── services.py            # ✅ NEW: User business logic
└── [rest of models.py]        # ✅ Temporary: All other models remain
```

### **Imports dopo Fase 1**
```python
# Existing code continues to work
from models import User, Tournament, Prova  # ✅ Still works

# New modular imports available
from models.user.models import User
from models.user.permissions import check_tournament_management_permission
from models.user.services import UserService
```

---

## 📋 **Tasks Dettagliati**

### **Task 1.1: Create Base Infrastructure** *(2 ore)*

#### **File:** `models/base.py` *(NUOVO)*
```python
"""
Base models and mixins for the application.
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class BaseModel(db.Model):
    """Base model with common fields"""
    __abstract__ = True
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TimestampMixin:
    """Mixin for models that need timestamp tracking"""
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SoftDeleteMixin:
    """Mixin for models that need soft deletion"""
    deleted_at = db.Column(db.DateTime)
    is_deleted = db.Column(db.Boolean, default=False)
    
    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
```

#### **File:** `models/__init__.py` *(MODIFICATO)*
```python
"""
Models package - maintains backward compatibility while enabling modular imports
"""
from .base import db

# User domain
from .user.models import User, TournamentDirector, DirectorRequest

# Temporary: Import remaining models from old structure
# These will be moved in subsequent phases
from .legacy_models import (
    Tournament, Prova, Inscription, Match, TrioMatch, 
    Rack, MatchResult, Classification, Playoff
)

# Maintain backward compatibility - all models available at package level
__all__ = [
    'db',
    'User', 'TournamentDirector', 'DirectorRequest',
    'Tournament', 'Prova', 'Inscription', 'Match', 'TrioMatch',
    'Rack', 'MatchResult', 'Classification', 'Playoff'
]
```

#### **Deliverable Task 1.1:**
- [x] `models/base.py` created with base classes
- [x] `models/__init__.py` updated with new structure
- [x] All existing imports still work

---

### **Task 1.2: Extract User Models** *(3 ore)*

#### **File:** `models/user/__init__.py` *(NUOVO)*
```python
"""
User domain models and services
"""
from .models import User, TournamentDirector, DirectorRequest
from .permissions import PermissionChecker
from .services import UserService

__all__ = ['User', 'TournamentDirector', 'DirectorRequest', 'PermissionChecker', 'UserService']
```

#### **File:** `models/user/models.py` *(NUOVO)*
```python
"""
User domain models - extracted from models.py
"""
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, desc
from datetime import datetime

from ..base import db, BaseModel

class User(UserMixin, BaseModel):
    """User model with role-based permissions"""
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    
    # Role system - replaces individual boolean flags
    role = db.Column(db.String(20), nullable=False, default='player')  # admin, director, player
    
    # Profile information
    phone = db.Column(db.String(20))
    
    # Relationships (will be updated in subsequent phases when other models are moved)
    inscriptions = db.relationship('Inscription', backref='user', lazy=True)
    match_results = db.relationship('MatchResult', foreign_keys='MatchResult.user_id', lazy=True)
    classifications = db.relationship('Classification', backref='user', lazy=True)
    playoff_participations = db.relationship('Playoff', backref='user', lazy=True)
    
    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password"""
        return check_password_hash(self.password_hash, password)
    
    # Role checking properties - maintain backward compatibility
    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_director(self):
        return self.role == 'director'

    @property
    def is_player(self):
        return self.role == 'player'
    
    # New permission methods
    def can_manage_tournament(self, tournament_id):
        """Check if user can manage specific tournament"""
        from .permissions import PermissionChecker
        return PermissionChecker.can_manage_tournament(self, tournament_id)
    
    def can_manage_competition(self, competition_id):
        """Check if user can manage specific competition"""
        from .permissions import PermissionChecker
        return PermissionChecker.can_manage_competition(self, competition_id)
    
    def can_view_admin_panel(self):
        """Check if user can access admin panel"""
        return self.is_admin
    
    def can_inscribe_to_competition(self, competition_id):
        """Check if user can inscribe to competition"""
        # Admin cannot inscribe (administrative role only)
        if self.is_admin:
            return False
        
        # Directors and players can inscribe
        # Directors cannot inscribe to their own tournaments (handled in permission checker)
        from .permissions import PermissionChecker
        return not PermissionChecker.can_manage_competition(self, competition_id)
    
    def get_managed_tournaments(self):
        """Get tournaments this user can manage"""
        if self.is_admin:
            # Import here to avoid circular imports
            from ..legacy_models import Tournament
            return Tournament.query.all()
        elif self.is_director:
            return [td.tournament for td in self.tournament_director_associations]
        else:
            return []
    
    def get_statistics(self):
        """Get user statistics - enhanced version"""
        # Import here to avoid circular imports during transition
        from ..legacy_models import Inscription, Match, Prova
        
        # All inscriptions
        total_inscriptions = Inscription.query.filter_by(user_id=self.id).count()
        
        # All matches played
        all_matches = Match.query.filter(
            db.or_(Match.player1_id == self.id, Match.player2_id == self.id),
            Match.status == 'completed'
        ).all()
        
        total_matches = len(all_matches)
        won_matches = len([m for m in all_matches if m.winner_id == self.id])
        lost_matches = total_matches - won_matches
        win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0
        
        # Tournaments played
        tournaments_played = len(set([
            insc.prova.tournament_id 
            for insc in Inscription.query.filter_by(user_id=self.id).join(Prova).all()
        ]))
        
        # Additional statistics for enhanced analytics
        total_racks_won = sum([
            self._count_racks_won_in_match(match) for match in all_matches
        ])
        
        total_racks_played = sum([
            match.player1_score + match.player2_score for match in all_matches
        ])
        
        rack_win_percentage = (total_racks_won / total_racks_played * 100) if total_racks_played > 0 else 0
        
        return {
            'total_inscriptions': total_inscriptions,
            'total_matches': total_matches,
            'won_matches': won_matches,
            'lost_matches': lost_matches,
            'win_percentage': round(win_percentage, 1),
            'tournaments_played': tournaments_played,
            'total_racks_won': total_racks_won,
            'total_racks_played': total_racks_played,
            'rack_win_percentage': round(rack_win_percentage, 1)
        }
    
    def _count_racks_won_in_match(self, match):
        """Helper to count racks won in a specific match"""
        if match.player1_id == self.id:
            return match.player1_score
        elif match.player2_id == self.id:
            return match.player2_score
        return 0
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'

class TournamentDirector(BaseModel):
    """Association table between tournaments and directors"""
    __tablename__ = 'tournament_director'
    
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), primary_key=True)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    director = db.relationship('User', foreign_keys=[user_id], backref='tournament_director_associations')
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id])
    tournament = db.relationship('Tournament', backref='directors_association')

class DirectorRequest(BaseModel):
    """Request for promotion to director role"""
    __tablename__ = 'director_request'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, approved, rejected
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    processed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    notes = db.Column(db.Text)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('director_request', uselist=False))
    processed_by = db.relationship('User', foreign_keys=[processed_by_id])
    
    def approve(self, admin_user):
        """Approve director request"""
        self.status = 'approved'
        self.processed_at = datetime.utcnow()
        self.processed_by_id = admin_user.id
        
        # Promote user to director
        self.user.role = 'director'
    
    def reject(self, admin_user, reason=None):
        """Reject director request"""
        self.status = 'rejected'
        self.processed_at = datetime.utcnow()
        self.processed_by_id = admin_user.id
        if reason:
            self.notes = reason
    
    def __repr__(self):
        return f'<DirectorRequest {self.user.username} - {self.status}>'
```

#### **Deliverable Task 1.2:**
- [x] User models extracted to separate module
- [x] Enhanced with new role system and permission methods
- [x] Backward compatibility maintained
- [x] Import structure prepared for future phases

---

### **Task 1.3: Implement Permission System** *(3 ore)*

#### **File:** `models/user/permissions.py` *(NUOVO)*
```python
"""
Permission checking system for role-based access control
"""
from typing import Optional

class PermissionChecker:
    """Centralized permission checking"""
    
    @staticmethod
    def can_manage_tournament(user, tournament_id: int) -> bool:
        """Check if user can manage a specific tournament"""
        if not user or not user.is_authenticated:
            return False
        
        # Admin can manage all tournaments
        if user.is_admin:
            return True
        
        # Director can manage assigned tournaments
        if user.is_director:
            from .models import TournamentDirector
            assignment = TournamentDirector.query.filter_by(
                user_id=user.id, 
                tournament_id=tournament_id
            ).first()
            return assignment is not None
        
        return False
    
    @staticmethod
    def can_manage_competition(user, competition_id: int) -> bool:
        """Check if user can manage a specific competition"""
        if not user or not user.is_authenticated:
            return False
        
        # Admin can manage all competitions
        if user.is_admin:
            return True
        
        # Director can manage competitions in their tournaments
        if user.is_director:
            # Import here to avoid circular imports during transition
            from ..legacy_models import Prova
            competition = Prova.query.get(competition_id)
            if competition:
                return PermissionChecker.can_manage_tournament(user, competition.tournament_id)
        
        return False
    
    @staticmethod
    def can_view_admin_panel(user) -> bool:
        """Check if user can access admin panel"""
        return user and user.is_authenticated and user.is_admin
    
    @staticmethod
    def can_manage_users(user) -> bool:
        """Check if user can manage other users"""
        return user and user.is_authenticated and user.is_admin
    
    @staticmethod
    def can_inscribe_to_competition(user, competition_id: int) -> bool:
        """Check if user can inscribe to a competition"""
        if not user or not user.is_authenticated:
            return False
        
        # Admin cannot inscribe (administrative role only)
        if user.is_admin:
            return False
        
        # Players can always inscribe
        if user.is_player:
            return True
        
        # Directors cannot inscribe to competitions they manage
        if user.is_director:
            return not PermissionChecker.can_manage_competition(user, competition_id)
        
        return False
    
    @staticmethod
    def can_view_competition_management(user, competition_id: int) -> bool:
        """Check if user can view competition management interface"""
        return PermissionChecker.can_manage_competition(user, competition_id)
    
    @staticmethod
    def can_insert_match_results(user, match_id: int) -> bool:
        """Check if user can insert results for a match"""
        if not user or not user.is_authenticated:
            return False
        
        # Import here to avoid circular imports
        from ..legacy_models import Match
        match = Match.query.get(match_id)
        if not match:
            return False
        
        # Admin can insert any results
        if user.is_admin:
            return True
        
        # Director can insert results for matches in their competitions
        if user.is_director:
            return PermissionChecker.can_manage_competition(user, match.prova_id)
        
        # Players can insert results for their own matches
        if user.is_player:
            return match.player1_id == user.id or match.player2_id == user.id
        
        return False
    
    @staticmethod
    def can_create_tournament(user) -> bool:
        """Check if user can create new tournaments"""
        return user and user.is_authenticated and (user.is_admin or user.is_director)
    
    @staticmethod
    def can_delete_tournament(user, tournament_id: int) -> bool:
        """Check if user can delete a tournament"""
        if not user or not user.is_authenticated:
            return False
        
        # Only admin can delete tournaments
        # (Directors can manage but not delete)
        return user.is_admin
    
    @staticmethod
    def get_tournament_management_level(user, tournament_id: int) -> str:
        """Get the level of management permission for a tournament"""
        if not user or not user.is_authenticated:
            return 'none'
        
        if user.is_admin:
            return 'full'  # Can do everything including delete
        
        if user.is_director and PermissionChecker.can_manage_tournament(user, tournament_id):
            return 'manage'  # Can manage but not delete
        
        return 'view'  # Can only view
    
    @staticmethod
    def filter_tournaments_by_permission(user, tournaments, permission_level='view'):
        """Filter tournaments based on user permissions"""
        if not user or not user.is_authenticated:
            return [] if permission_level != 'view' else tournaments
        
        if user.is_admin:
            return tournaments  # Admin sees everything
        
        if permission_level == 'view':
            return tournaments  # Everyone can view all tournaments
        
        if permission_level == 'manage' and user.is_director:
            # Directors see only their assigned tournaments
            managed_ids = [td.tournament_id for td in user.tournament_director_associations]
            return [t for t in tournaments if t.id in managed_ids]
        
        return []

class RoleRequirement:
    """Decorator helper for role requirements"""
    
    @staticmethod
    def admin_required(f):
        """Decorator for admin-only functions"""
        from functools import wraps
        from flask import abort
        from flask_login import current_user
        
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    
    @staticmethod
    def director_or_admin_required(f):
        """Decorator for director/admin functions"""
        from functools import wraps
        from flask import abort
        from flask_login import current_user
        
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not (current_user.is_admin or current_user.is_director):
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    
    @staticmethod
    def tournament_manager_required(tournament_id_getter):
        """Decorator for tournament management functions"""
        from functools import wraps
        from flask import abort
        from flask_login import current_user
        
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                tournament_id = tournament_id_getter(**kwargs) if callable(tournament_id_getter) else tournament_id_getter
                if not PermissionChecker.can_manage_tournament(current_user, tournament_id):
                    abort(403)
                return f(*args, **kwargs)
            return decorated_function
        return decorator
```

#### **Deliverable Task 1.3:**
- [x] Comprehensive permission system implemented
- [x] Role-based access control with granular permissions
- [x] Decorator helpers for route protection
- [x] Future-proof for complex permission scenarios

---

### **Task 1.4: Create User Services** *(2 ore)*

#### **File:** `models/user/services.py` *(NUOVO)*
```python
"""
User domain business logic and services
"""
from typing import List, Optional, Dict, Any
from sqlalchemy import func, desc, or_
from datetime import datetime, timedelta

from ..base import db
from .models import User, TournamentDirector, DirectorRequest

class UserService:
    """Service class for user-related business operations"""
    
    @staticmethod
    def create_user(username: str, email: str, password: str, role: str = 'player') -> User:
        """Create new user with validation"""
        # Validate role
        if role not in ['admin', 'director', 'player']:
            raise ValueError(f"Invalid role: {role}")
        
        # Check if username/email already exists
        if User.query.filter_by(username=username).first():
            raise ValueError(f"Username '{username}' already exists")
        
        if User.query.filter_by(email=email).first():
            raise ValueError(f"Email '{email}' already exists")
        
        user = User(
            username=username,
            email=email,
            role=role
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        return user
    
    @staticmethod
    def promote_to_director(user_id: int, admin_user: User) -> bool:
        """Promote user to director role"""
        if not admin_user.is_admin:
            raise PermissionError("Only admins can promote users")
        
        user = User.query.get(user_id)
        if not user:
            raise ValueError("User not found")
        
        if user.is_director or user.is_admin:
            raise ValueError("User is already director or admin")
        
        user.role = 'director'
        db.session.commit()
        
        return True
    
    @staticmethod
    def demote_from_director(user_id: int, admin_user: User) -> bool:
        """Demote director to player role"""
        if not admin_user.is_admin:
            raise PermissionError("Only admins can demote users")
        
        user = User.query.get(user_id)
        if not user:
            raise ValueError("User not found")
        
        if not user.is_director:
            raise ValueError("User is not a director")
        
        # Remove all tournament assignments
        TournamentDirector.query.filter_by(user_id=user_id).delete()
        
        user.role = 'player'
        db.session.commit()
        
        return True
    
    @staticmethod
    def assign_tournament_director(tournament_id: int, director_id: int, admin_user: User) -> TournamentDirector:
        """Assign director to tournament"""
        if not admin_user.is_admin:
            raise PermissionError("Only admins can assign directors")
        
        director = User.query.get(director_id)
        if not director or not director.is_director:
            raise ValueError("Invalid director")
        
        # Check if already assigned
        existing = TournamentDirector.query.filter_by(
            user_id=director_id,
            tournament_id=tournament_id
        ).first()
        
        if existing:
            raise ValueError("Director already assigned to this tournament")
        
        assignment = TournamentDirector(
            user_id=director_id,
            tournament_id=tournament_id,
            assigned_by_id=admin_user.id
        )
        
        db.session.add(assignment)
        db.session.commit()
        
        return assignment
    
    @staticmethod
    def remove_tournament_director(tournament_id: int, director_id: int, admin_user: User) -> bool:
        """Remove director from tournament"""
        if not admin_user.is_admin:
            raise PermissionError("Only admins can remove directors")
        
        assignment = TournamentDirector.query.filter_by(
            user_id=director_id,
            tournament_id=tournament_id
        ).first()
        
        if not assignment:
            raise ValueError("Director assignment not found")
        
        db.session.delete(assignment)
        db.session.commit()
        
        return True
    
    @staticmethod
    def get_users_by_role(role: str) -> List[User]:
        """Get all users with specific role"""
        return User.query.filter_by(role=role).order_by(User.username).all()
    
    @staticmethod
    def get_user_statistics(user_id: int) -> Dict[str, Any]:
        """Get comprehensive user statistics"""
        user = User.query.get(user_id)
        if not user:
            raise ValueError("User not found")
        
        return user.get_statistics()
    
    @staticmethod
    def search_users(query: str, role: Optional[str] = None) -> List[User]:
        """Search users by username or email"""
        search_filter = or_(
            User.username.ilike(f'%{query}%'),
            User.email.ilike(f'%{query}%')
        )
        
        users_query = User.query.filter(search_filter)
        
        if role:
            users_query = users_query.filter_by(role=role)
        
        return users_query.order_by(User.username).all()

class DirectorRequestService:
    """Service for director promotion requests"""
    
    @staticmethod
    def create_request(user_id: int) -> DirectorRequest:
        """Create director promotion request"""
        user = User.query.get(user_id)
        if not user:
            raise ValueError("User not found")
        
        if user.is_admin or user.is_director:
            raise ValueError("User is already admin or director")
        
        # Check if there's already a pending request
        existing = DirectorRequest.query.filter_by(
            user_id=user_id,
            status='pending'
        ).first()
        
        if existing:
            raise ValueError("There's already a pending request for this user")
        
        request = DirectorRequest(user_id=user_id)
        db.session.add(request)
        db.session.commit()
        
        return request
    
    @staticmethod
    def get_pending_requests() -> List[DirectorRequest]:
        """Get all pending director requests"""
        return DirectorRequest.query.filter_by(status='pending').order_by(DirectorRequest.requested_at).all()
    
    @staticmethod
    def process_request(request_id: int, admin_user: User, approve: bool, notes: Optional[str] = None) -> DirectorRequest:
        """Process director request (approve/reject)"""
        if not admin_user.is_admin:
            raise PermissionError("Only admins can process director requests")
        
        request = DirectorRequest.query.get(request_id)
        if not request:
            raise ValueError("Request not found")
        
        if request.status != 'pending':
            raise ValueError("Request has already been processed")
        
        if notes:
            request.notes = notes
        
        if approve:
            request.approve(admin_user)
        else:
            request.reject(admin_user, notes)
        
        db.session.commit()
        
        return request

class UserStatsService:
    """Service for user statistics and analytics"""
    
    @staticmethod
    def get_top_players(limit: int = 10, by: str = 'win_rate') -> List[Dict[str, Any]]:
        """Get top players by various metrics"""
        # This will be enhanced in later phases when match data is modularized
        users = User.query.filter_by(role='player').all()
        
        user_stats = []
        for user in users:
            stats = user.get_statistics()
            user_stats.append({
                'user': user,
                'stats': stats
            })
        
        # Sort by specified metric
        if by == 'win_rate':
            user_stats.sort(key=lambda x: x['stats']['win_percentage'], reverse=True)
        elif by == 'matches_played':
            user_stats.sort(key=lambda x: x['stats']['total_matches'], reverse=True)
        elif by == 'tournaments_played':
            user_stats.sort(key=lambda x: x['stats']['tournaments_played'], reverse=True)
        
        return user_stats[:limit]
    
    @staticmethod
    def get_activity_summary() -> Dict[str, Any]:
        """Get system-wide activity summary"""
        total_users = User.query.count()
        admins = User.query.filter_by(role='admin').count()
        directors = User.query.filter_by(role='director').count()
        players = User.query.filter_by(role='player').count()
        
        # Recent registrations (last 30 days)
        recent_cutoff = datetime.utcnow() - timedelta(days=30)
        recent_registrations = User.query.filter(User.created_at >= recent_cutoff).count()
        
        return {
            'total_users': total_users,
            'admins': admins,
            'directors': directors,
            'players': players,
            'recent_registrations': recent_registrations,
            'pending_director_requests': DirectorRequest.query.filter_by(status='pending').count()
        }
```

#### **Deliverable Task 1.4:**
- [x] Comprehensive user service layer
- [x] Business logic separated from models
- [x] Enhanced statistics and analytics
- [x] Request processing workflows

---

### **Task 1.5: Update Existing Code** *(2 ore)*

#### **File:** `models/legacy_models.py` *(NUOVO)*
```python
"""
Temporary file containing all non-user models
This will be broken down in subsequent phases
"""
# Copy all existing models from original models.py EXCEPT:
# - User, TournamentDirector, DirectorRequest (now in user domain)

# Note: This is a temporary solution for Phase 1 only
# These models will be properly modularized in subsequent phases
```

#### **Update existing files:**
- Update `utils.py` decorators to use new permission system
- Update any direct User model usage in routes
- Test all existing functionality

#### **Deliverable Task 1.5:**
- [x] All existing functionality works
- [x] Legacy models temporarily preserved
- [x] Import paths updated where needed
- [x] No breaking changes

---

### **Task 1.6: Enhanced Reset Data** *(2 ore)*

#### **File:** `utils/reset_data.py` *(NUOVO o UPDATE)*
```python
"""
Enhanced reset functionality with comprehensive example data
"""
from models.user.models import User, TournamentDirector, DirectorRequest
from models.user.services import UserService
from models.base import db

def create_enhanced_users():
    """Create diverse set of example users for testing"""
    
    # Admin users
    admin = UserService.create_user(
        username='admin',
        email='admin@tornei.com',
        password='admin123',
        role='admin'
    )
    
    # Director users
    director1 = UserService.create_user(
        username='mario_rossi',
        email='mario.rossi@email.com',
        password='mario123',
        role='director'
    )
    
    director2 = UserService.create_user(
        username='lucia_verdi',
        email='lucia.verdi@email.com',
        password='lucia123',
        role='director'
    )
    
    # Player users with variety
    players_data = [
        ('giovanni_bianchi', 'giovanni@email.com', 'giovanni123'),
        ('anna_ferrari', 'anna@email.com', 'anna123'),
        ('marco_russo', 'marco@email.com', 'marco123'),
        ('sara_marino', 'sara@email.com', 'sara123'),
        ('luca_greco', 'luca@email.com', 'luca123'),
        ('elena_ricci', 'elena@email.com', 'elena123'),
        ('davide_costa', 'davide@email.com', 'davide123'),
        ('chiara_lombardi', 'chiara@email.com', 'chiara123'),
        ('andrea_conti', 'andrea@email.com', 'andrea123'),
        ('valeria_galli', 'valeria@email.com', 'valeria123'),
    ]
    
    players = []
    for username, email, password in players_data:
        player = UserService.create_user(
            username=username,
            email=email,
            password=password,
            role='player'
        )
        players.append(player)
    
    # Create some director requests for testing admin workflows
    pending_user = UserService.create_user(
        username='aspirante_director',
        email='aspirante@email.com',
        password='aspirante123',
        role='player'
    )
    
    from models.user.services import DirectorRequestService
    DirectorRequestService.create_request(pending_user.id)
    
    return {
        'admin': admin,
        'directors': [director1, director2],
        'players': players,
        'pending_request_user': pending_user
    }
```

#### **Update existing reset functionality:**
- Integrate new user creation into existing reset
- Maintain existing tournament/prova creation
- Add more comprehensive example data

#### **Deliverable Task 1.6:**
- [x] Enhanced reset with rich user data
- [x] Different roles represented
- [x] Example director requests
- [x] Ready for testing new permission system

---

## 🧪 **Testing Strategy Fase 1**

### **Unit Tests** *(1 ora)*
```python
# tests/test_user_models.py
def test_user_role_properties():
    """Test role checking properties"""
    admin = User(role='admin')
    assert admin.is_admin
    assert not admin.is_director
    assert not admin.is_player

def test_user_permissions():
    """Test permission methods"""
    user = User(role='player')
    assert not user.can_view_admin_panel()
    
def test_password_hashing():
    """Test password security"""
    user = User()
    user.set_password('test123')
    assert user.check_password('test123')
    assert not user.check_password('wrong')

# tests/test_user_services.py  
def test_user_creation():
    """Test user service creation"""
    user = UserService.create_user('test', 'test@email.com', 'password123')
    assert user.username == 'test'
    assert user.is_player

def test_permission_checking():
    """Test permission checker"""
    admin = User(role='admin')
    assert PermissionChecker.can_view_admin_panel(admin)
```

### **Integration Tests** *(1 ora)*
```python
# tests/test_integration_phase1.py
def test_backward_compatibility():
    """Test that existing imports still work"""
    from models import User  # Should work
    from models.user.models import User  # Should also work
    
def test_existing_functionality():
    """Test that all existing routes still work"""
    # Test login, dashboard, etc.
    pass
```

---

## 📊 **Success Metrics Fase 1**

### **Technical Metrics**
- [ ] **Import Compatibility**: All existing `from models import X` work
- [ ] **Functionality Preservation**: All existing routes work without changes
- [ ] **Test Coverage**: >90% for new user domain code
- [ ] **Performance**: No regression in page load times

### **Feature Metrics**
- [ ] **Enhanced Permissions**: Granular permission checking works
- [ ] **Role Management**: Admin can promote/demote users
- [ ] **Director Assignments**: Tournament director assignment works
- [ ] **Statistics Enhancement**: Richer user statistics available

---

## 🔄 **Git Workflow Fase 1**

### **Branch Strategy**
```bash
# Start phase 1
git checkout -b phase-1-user-system

# Create commits for each major task
git add models/base.py models/__init__.py
git commit -m "Task 1.1: Create base infrastructure"

git add models/user/
git commit -m "Task 1.2: Extract user models"

git add models/user/permissions.py
git commit -m "Task 1.3: Implement permission system"

git add models/user/services.py  
git commit -m "Task 1.4: Create user services"

git add models/legacy_models.py
git commit -m "Task 1.5: Update existing code integration"

git add utils/reset_data.py
git commit -m "Task 1.6: Enhanced reset data"

# Final integration and testing
git add tests/
git commit -m "Task 1.7: Add comprehensive tests"

# Merge to main when everything works
git checkout main
git merge phase-1-user-system
git tag v-phase-1-complete
```

### **Rollback Strategy**
```bash
# If something breaks during development
git checkout main  # Return to stable state

# If need to rollback after merge
git revert v-phase-1-complete
# or
git reset --hard HEAD~1  # If no other changes made
```

---

## ✅ **Definition of Done - Fase 1**

### **Code Quality**
- [ ] All new code follows PEP 8 standards
- [ ] Comprehensive docstrings for all public methods
- [ ] Type hints where appropriate
- [ ] No circular imports
- [ ] Clean separation of concerns

### **Functionality**
- [ ] All existing features work without modification
- [ ] New permission system fully functional
- [ ] Enhanced user statistics working
- [ ] Director request workflow complete
- [ ] Reset functionality enhanced with rich data

### **Testing**
- [ ] Unit tests for all new models and services
- [ ] Integration tests for backward compatibility
- [ ] Manual testing of all user workflows
- [ ] Performance testing shows no regression

### **Documentation**
- [ ] All new modules properly documented
- [ ] Import structure clearly explained
- [ ] Permission system documented
- [ ] Migration path for future phases prepared

---

## 🚀 **Ready for Phase 2**

After Phase 1 completion, we'll have:
- ✅ **Solid Foundation**: User system properly modularized
- ✅ **Permission Framework**: Ready for tournament/competition permissions
- ✅ **Service Pattern**: Template for other domain services
- ✅ **Clean Import Structure**: Ready for other domain migrations
- ✅ **Enhanced Reset**: Rich example data for testing subsequent phases

**Next Phase Preview**: Tournament and Competition domain separation with strategy pattern foundations.