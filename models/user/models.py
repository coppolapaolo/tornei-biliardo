"""
User domain models - extracted from monolithic models.py

This module contains all user-related models following Domain-Driven Design:
- User: Core user model with role-based authentication
- TournamentDirector: Association between users and tournaments
- DirectorRequest: Workflow for director role promotions

Author: Refactoring Phase 1
Created: 2025-01-31
"""

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, desc, or_
from datetime import datetime

from ..base import db, BaseModel

class User(UserMixin, BaseModel):
    """
    User model with role-based permissions and enhanced functionality.
    
    Supports three roles:
    - admin: Full system access, cannot participate in games
    - director: Tournament management, can participate in non-managed tournaments  
    - player: Game participation, read-only access to tournaments
    """
    __tablename__ = 'user'
    
    # Primary identification
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(120), nullable=False)
    
    # Role system - replaces individual boolean flags
    role = db.Column(db.String(20), nullable=False, default='player', index=True)  # admin, director, player
    
    # Profile information
    phone = db.Column(db.String(20))
    
    # Relationships - DISABLED during Phase 1 to avoid dependency issues
    # These will be properly configured when other models are migrated in Phase 2+
    # For now, we'll handle these relationships through queries in the service methods
    
    # inscriptions = db.relationship('Inscription', backref='user', lazy=True)
    # match_results = db.relationship('MatchResult', foreign_keys='MatchResult.user_id', lazy=True) 
    # classifications = db.relationship('Classification', backref='user', lazy=True)
    
    # Relationships for director functionality
    tournament_director_associations = db.relationship('TournamentDirector', foreign_keys='TournamentDirector.user_id', backref='director')
    
    def set_password(self, password):
        """Set password hash using secure hashing"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against stored hash"""
        return check_password_hash(self.password_hash, password)
    
    # Role checking properties - maintain backward compatibility
    @property
    def is_admin(self):
        """Check if user has admin role"""
        return self.role == 'admin'

    @property  
    def is_director(self):
        """Check if user has director role"""
        return self.role == 'director'

    @property
    def is_player(self):
        """Check if user has player role"""
        return self.role == 'player'
    
    # New permission methods using future permission system
    def can_manage_tournament(self, tournament_id):
        """Check if user can manage specific tournament"""
        if self.is_admin:
            return True
        
        if self.is_director:
            # Check if director is assigned to this tournament
            assignment = TournamentDirector.query.filter_by(
                user_id=self.id,
                tournament_id=tournament_id
            ).first()
            return assignment is not None
        
        return False
    
    def can_manage_competition(self, competition_id):
        """Check if user can manage specific competition"""
        if self.is_admin:
            return True
        
        if self.is_director:
            # Import here to avoid circular imports during transition
            try:
                # Try to import from current structure
                from models import Prova
                competition = Prova.query.get(competition_id)
                if competition:
                    return self.can_manage_tournament(competition.tournament_id)
            except:
                # Fallback for development
                pass
        
        return False
    
    def can_view_admin_panel(self):
        """Check if user can access admin panel"""
        return self.is_admin
    
    def can_inscribe_to_competition(self, competition_id):
        """Check if user can inscribe to competition"""
        # Admin cannot inscribe (administrative role only)
        if self.is_admin:
            return False
        
        # Players can always inscribe
        if self.is_player:
            return True
        
        # Directors cannot inscribe to competitions they manage
        if self.is_director:
            return not self.can_manage_competition(competition_id)
        
        return False
    
    def get_managed_tournaments(self):
        """Get tournaments this user can manage"""
        if self.is_admin:
            # Import here to avoid circular imports
            try:
                from models import Tournament
                return Tournament.query.all()
            except ImportError:
                return []
        elif self.is_director:
            # Get tournaments where user is assigned as director - using direct query
            try:
                assignments = TournamentDirector.query.filter_by(user_id=self.id).all()
                tournaments = []
                for assignment in assignments:
                    tournaments.append(assignment.tournament)
                return tournaments
            except:
                return []
        else:
            return []
    
    def get_statistics(self):
        """Get comprehensive user statistics"""
        try:
            # Import here to avoid circular imports during transition
            from models import Inscription, Match, Prova
            
            # All inscriptions - using direct query instead of relationship
            total_inscriptions = Inscription.query.filter_by(user_id=self.id).count()
            
            # All matches played - using direct query instead of relationship
            all_matches = Match.query.filter(
                or_(Match.player1_id == self.id, Match.player2_id == self.id),
                Match.status == 'completed'
            ).all()
            
            total_matches = len(all_matches)
            won_matches = len([m for m in all_matches if m.winner_id == self.id])
            lost_matches = total_matches - won_matches
            win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0
            
            # Tournaments played - using join query instead of relationship
            tournaments_played = len(set([
                insc.prova.tournament_id 
                for insc in Inscription.query.filter_by(user_id=self.id).join(Prova).all()
            ]))
            
            # Additional statistics for enhanced analytics
            total_racks_won = sum([
                self._count_racks_won_in_match(match) for match in all_matches
            ])
            
            total_racks_played = sum([
                (match.player1_score or 0) + (match.player2_score or 0) for match in all_matches
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
        except ImportError as e:
            # Models not available yet - return basic stats
            return {
                'total_inscriptions': 0,
                'total_matches': 0,
                'won_matches': 0,
                'lost_matches': 0,
                'win_percentage': 0.0,
                'tournaments_played': 0,
                'total_racks_won': 0,
                'total_racks_played': 0,
                'rack_win_percentage': 0.0,
                'note': 'Statistics unavailable - models not yet migrated'
            }
        except Exception as e:
            # Other errors - return error info for debugging
            return {
                'total_inscriptions': 0,
                'total_matches': 0,
                'won_matches': 0,
                'lost_matches': 0,
                'win_percentage': 0.0,
                'tournaments_played': 0,
                'total_racks_won': 0,
                'total_racks_played': 0,
                'rack_win_percentage': 0.0,
                'error': str(e)
            }
    
    def _count_racks_won_in_match(self, match):
        """Helper to count racks won in a specific match"""
        if match.player1_id == self.id:
            return match.player1_score or 0
        elif match.player2_id == self.id:
            return match.player2_score or 0
        return 0
    
    def validate(self):
        """Validate user data"""
        errors = []
        
        # Username validation
        if not self.username or len(self.username.strip()) < 3:
            errors.append("Username must be at least 3 characters long")
        
        # Email validation (basic)
        if not self.email or '@' not in self.email:
            errors.append("Valid email address is required")
        
        # Role validation
        if self.role not in ['admin', 'director', 'player']:
            errors.append("Role must be admin, director, or player")
        
        # Check uniqueness
        existing_username = User.query.filter(
            User.username == self.username,
            User.id != self.id if self.id else True
        ).first()
        if existing_username:
            errors.append("Username already exists")
        
        existing_email = User.query.filter(
            User.email == self.email,
            User.id != self.id if self.id else True
        ).first()
        if existing_email:
            errors.append("Email already exists")
        
        if errors:
            raise ValueError("; ".join(errors))
        
        return True
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class TournamentDirector(BaseModel):
    """
    Association table between tournaments and directors.
    
    Allows multiple directors per tournament and tracks assignment history.
    """
    __tablename__ = 'tournament_director'
    
    # Composite primary key
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), primary_key=True)
    
    # Assignment metadata
    assigned_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_id])
    tournament = db.relationship('Tournament', backref='directors_association')
    
    def validate(self):
        """Validate tournament director assignment"""
        errors = []
        
        # Check that user exists and is a director
        user = User.query.get(self.user_id)
        if not user:
            errors.append("User not found")
        elif not user.is_director:
            errors.append("User must have director role")
        
        # Check that assigned_by user exists and is admin
        assigned_by = User.query.get(self.assigned_by_id)
        if not assigned_by:
            errors.append("Assigning user not found")
        elif not assigned_by.is_admin:
            errors.append("Only admins can assign directors")
        
        # Check for duplicate assignment
        existing = TournamentDirector.query.filter(
            TournamentDirector.user_id == self.user_id,
            TournamentDirector.tournament_id == self.tournament_id
        ).first()
        
        if existing and existing != self:
            errors.append("Director already assigned to this tournament")
        
        if errors:
            raise ValueError("; ".join(errors))
        
        return True
    
    def __repr__(self):
        return f'<TournamentDirector user_id={self.user_id} tournament_id={self.tournament_id}>'


class DirectorRequest(BaseModel):
    """
    Request for promotion to director role.
    
    Manages the workflow for players requesting director privileges.
    """
    __tablename__ = 'director_request'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    
    # Request status workflow
    status = db.Column(db.String(20), nullable=False, default='pending', index=True)  # pending, approved, rejected
    
    # Timeline tracking
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    processed_at = db.Column(db.DateTime, nullable=True)
    
    # Processing information
    processed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('director_request', uselist=False))
    processed_by = db.relationship('User', foreign_keys=[processed_by_id])
    
    def approve(self, admin_user):
        """Approve director request and promote user"""
        if not admin_user.is_admin:
            raise ValueError("Only admins can approve director requests")
        
        if self.status != 'pending':
            raise ValueError("Request has already been processed")
        
        # Update request status
        self.status = 'approved'
        self.processed_at = datetime.utcnow()
        self.processed_by_id = admin_user.id
        
        # Promote user to director
        self.user.role = 'director'
        
        db.session.commit()
    
    def reject(self, admin_user, reason=None):
        """Reject director request"""
        if not admin_user.is_admin:
            raise ValueError("Only admins can reject director requests")
        
        if self.status != 'pending':
            raise ValueError("Request has already been processed")
        
        # Update request status
        self.status = 'rejected'
        self.processed_at = datetime.utcnow()
        self.processed_by_id = admin_user.id
        
        if reason:
            self.notes = reason
        
        db.session.commit()
    
    def cancel(self):
        """Cancel pending request (user can cancel their own request)"""
        if self.status != 'pending':
            raise ValueError("Only pending requests can be cancelled")
        
        self.status = 'cancelled'
        self.processed_at = datetime.utcnow()
        
        db.session.commit()
    
    @property
    def is_pending(self):
        """Check if request is still pending"""
        return self.status == 'pending'
    
    @property
    def is_approved(self):
        """Check if request was approved"""
        return self.status == 'approved'
    
    @property
    def is_rejected(self):
        """Check if request was rejected"""
        return self.status == 'rejected'
    
    @property
    def days_pending(self):
        """Calculate days since request was submitted"""
        if self.processed_at:
            return (self.processed_at - self.requested_at).days
        else:
            return (datetime.utcnow() - self.requested_at).days
    
    def validate(self):
        """Validate director request"""
        errors = []
        
        # Check that user exists
        user = User.query.get(self.user_id)
        if not user:
            errors.append("User not found")
        else:
            # Check that user is not already admin or director
            if user.is_admin or user.is_director:
                errors.append("User is already admin or director")
            
            # Check for existing pending request
            existing_pending = DirectorRequest.query.filter(
                DirectorRequest.user_id == self.user_id,
                DirectorRequest.status == 'pending',
                DirectorRequest.id != self.id if self.id else True
            ).first()
            
            if existing_pending:
                errors.append("User already has a pending director request")
        
        # Status validation
        if self.status not in ['pending', 'approved', 'rejected', 'cancelled']:
            errors.append("Invalid status")
        
        # If processed, must have processed_by
        if self.status in ['approved', 'rejected'] and not self.processed_by_id:
            errors.append("Processed requests must have processed_by_id")
        
        if errors:
            raise ValueError("; ".join(errors))
        
        return True
    
    def __repr__(self):
        return f'<DirectorRequest {self.user.username} - {self.status}>'


# Model registration for relationship setup
# This ensures all relationships are properly configured
def _setup_relationships():
    """Setup relationships between user models and external models"""
    # This will be called when all models are loaded
    pass

# Export models list for introspection
USER_MODELS = [User, TournamentDirector, DirectorRequest]