"""
User domain business logic and services

This module contains all business logic and service layer functions for user management.
It implements the service layer pattern, separating business operations from models
and providing a clean API for user-related operations.

Services:
- UserService: Core user management operations
- DirectorRequestService: Director promotion request workflow
- UserStatsService: User statistics and analytics

Author: Refactoring Phase 1 - Task 1.4
Enhanced: Phase 3.3 - Transaction Management
Created: 2025-08-01
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from sqlalchemy import func, desc, or_
from datetime import datetime, timedelta

from ..base import db
from .models import User, TournamentDirector, DirectorRequest
from ..transaction.manager import DomainService, transactional, read_only, transaction_manager

from models.match import Match
from models.competition.models import Prova, Inscription
from models.status_enum import MatchStatus, DirectorRequestStatus
from models.user.role_enum import UserRole
from models.classification.models import Classification


class UserServiceCore(DomainService):
    """
    Enhanced service class for user-related business operations with transaction management.

    This class encapsulates all business logic related to user management,
    including creation, role management, and user operations with proper
    transaction boundaries and domain tracking.
    """
    
    def __init__(self):
        super().__init__("user")

    @transactional(domain="user")
    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        role: str = "player",
        phone: Optional[str] = None,
    ) -> User:
        """
        Create new user with validation and proper transaction management.

        Args:
            username: Unique username
            email: Unique email address
            password: Plain text password (will be hashed)
            role: User role (admin, director, player)
            phone: Optional phone number

        Returns:
            User: Created user instance

        Raises:
            ValueError: If validation fails or user already exists
        """
        # Track domain access
        self._track_domain_access()
        
        # Invariante: singolo amministratore attivo
        if role == UserRole.ADMIN.value:
            exists_active_admin = self._execute_with_tracking(
                lambda: User.query.filter_by(role=UserRole.ADMIN.value)
                .filter(User.deleted_at.is_(None))
                .count()
            )
            if exists_active_admin > 0:
                raise ValueError("Esiste già un amministratore attivo.")
        
        # Validate role
        if role not in ["admin", "director", "player"]:
            raise ValueError(
                f"Invalid role: {role}. Must be one of: admin, director, player"
            )

        # Validate required fields
        if not username or not username.strip():
            raise ValueError("Username is required")

        if not email or not email.strip():
            raise ValueError("Email is required")

        if not password or len(password) < 6:
            raise ValueError("Password must be at least 6 characters long")

        # Check if username already exists (case insensitive)
        existing_username = self._execute_with_tracking(
            lambda: User.query.filter(
                func.lower(User.username) == func.lower(username.strip())
            ).first()
        )
        if existing_username:
            raise ValueError(f"Username '{username}' already exists")

        # Check if email already exists (case insensitive)
        # For encrypted fields, we need to retrieve all users and filter in Python
        users = self._execute_with_tracking(lambda: User.query.all())
        email_normalized = email.strip().lower()
        for user in users:
            if user.email and user.email.lower() == email_normalized:
                raise ValueError(f"Email '{email}' already exists")

        # Create user within transaction
        user = User(
            username=username.strip(),
            email=email.strip().lower(),
            role=role,
            phone=phone.strip() if phone else None,
        )
        user.set_password(password)

        db.session.add(user)
        # Flush to ensure the ID is assigned before returning
        db.session.flush()
        # Transaction will be committed by decorator
        
        return user

    @transactional(domain="user")
    def update_user(self, user_id: int, **kwargs) -> User:
        """
        Update user information with transaction management.

        Args:
            user_id: ID of user to update
            **kwargs: Fields to update (username, email, phone)

        Returns:
            User: Updated user instance

        Raises:
            ValueError: If user not found or validation fails
        """
        self._track_domain_access()
        
        user = self._execute_with_tracking(
            lambda: db.session.get(User, user_id)
        )
        if not user:
            raise ValueError("User not found")

        # Update allowed fields
        if "username" in kwargs:
            new_username = kwargs["username"].strip()
            if new_username != user.username:
                # Check uniqueness
                existing = self._execute_with_tracking(
                    lambda: User.query.filter(
                        func.lower(User.username) == func.lower(new_username),
                        User.id != user_id,
                    ).first()
                )
                if existing:
                    raise ValueError(f"Username '{new_username}' already exists")
                user.username = new_username

        if "email" in kwargs:
            new_email = kwargs["email"].strip().lower()
            if new_email != user.email:
                # Check uniqueness
                # For encrypted fields, we need to retrieve all users and filter in Python
                users = self._execute_with_tracking(lambda: User.query.all())
                for existing_user in users:
                    if existing_user.id != user_id and existing_user.email and existing_user.email.lower() == new_email:
                        raise ValueError(f"Email '{new_email}' already exists")
                user.email = new_email

        if "phone" in kwargs:
            user.phone = kwargs["phone"].strip() if kwargs["phone"] else None

        # Transaction will be committed by decorator
        return user

    @transactional(domain="user")
    def change_password(self, user_id: int, old_password: str, new_password: str) -> bool:
        """
        Change user password with validation and transaction management.

        Args:
            user_id: ID of user
            old_password: Current password
            new_password: New password

        Returns:
            bool: True if password changed successfully

        Raises:
            ValueError: If validation fails
        """
        self._track_domain_access()
        
        user = self._execute_with_tracking(
            lambda: db.session.get(User, user_id)
        )
        if not user:
            return False

        if not user.check_password(old_password):
            return False

        if len(new_password) < 6:
            raise ValueError("New password must be at least 6 characters long")

        user.set_password(new_password)
        # Transaction will be committed by decorator
        return True
    
    @read_only(domain="user")
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID with read-only transaction."""
        self._track_domain_access()
        return self._execute_with_tracking(
            lambda: db.session.get(User, user_id)
        )
    
    @read_only(domain="user")
    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username with read-only transaction."""
        self._track_domain_access()
        return self._execute_with_tracking(
            lambda: User.query.filter(
                func.lower(User.username) == func.lower(username.strip())
            ).first()
        )
    
    @read_only(domain="user")
    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        if not email:
            return None
            
        # Strip and normalize email
        email = email.strip().lower()
        if not email:
            return None
            
        # For encrypted fields, we need to retrieve all users and filter in Python
        # because encrypted values are different each time due to random elements
        users = self._execute_with_tracking(lambda: User.query.all())
        
        # Find user with matching email (case-insensitive)
        for user in users:
            if user.email and user.email.lower() == email:
                return user
                
        return None
    
    @read_only(domain="user")
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password.
        
        Args:
            username: Username to authenticate
            password: Plain text password to verify
            
        Returns:
            User: Authenticated user if successful, None if failed
        """
        self._track_domain_access()
        
        user = self.get_user_by_username(username)
        if user and user.check_password(password):
            return user
        return None
    
    @transactional(domain="user")
    def delete_user(self, user_id: int, admin_id: int) -> Dict[str, Any]:
        """Soft delete user with transaction management and cross-domain cleanup."""
        self._track_domain_access()
        
        user = self._execute_with_tracking(
            lambda: db.session.get(User, user_id)
        )
        if not user:
            raise ValueError("User not found")
        
        if user.role == UserRole.ADMIN.value:
            raise ValueError("Cannot delete administrator account")
        
        # Track cross-domain implications
        transaction_manager.track_domain_access("competition")
        transaction_manager.track_domain_access("match")
        
        # Perform soft delete
        user.soft_delete()
        
        # Return cleanup summary
        return {
            "user_id": user_id,
            "deleted_at": user.deleted_at,
            "deleted_by": admin_id,
            "cleanup_required": True
        }


# Create global instance for enhanced functionality
_user_service_instance = UserServiceCore()


# Static wrapper methods for backward compatibility
class UserServiceCompat:
    """Backward compatibility wrapper with static methods."""
    
    @staticmethod
    def create_user(
        username: str,
        email: str,
        password: str,
        role: str = "player",
        phone: Optional[str] = None,
    ) -> User:
        """Static wrapper for create_user."""
        return _user_service_instance.create_user(username, email, password, role, phone)
    
    @staticmethod
    def update_user(user_id: int, **kwargs) -> User:
        """Static wrapper for update_user."""
        return _user_service_instance.update_user(user_id, **kwargs)
    
    @staticmethod
    def change_password(user_id: int, old_password: str, new_password: str) -> bool:
        """Static wrapper for change_password."""
        return _user_service_instance.change_password(user_id, old_password, new_password)
    
    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[User]:
        """Static wrapper for get_user_by_id."""
        return _user_service_instance.get_user_by_id(user_id)
    
    @staticmethod
    def get_user_by_username(username: str) -> Optional[User]:
        """Static wrapper for get_user_by_username."""
        return _user_service_instance.get_user_by_username(username)
    
    @staticmethod
    def get_user_by_email(email: str) -> Optional[User]:
        """Get user by email."""
        if not email:
            return None
            
        # Strip and normalize email
        email = email.strip().lower()
        if not email:
            return None
            
        # For encrypted fields, we need to retrieve all users and filter in Python
        # because encrypted values are different each time due to random elements
        users = User.query.all()
        
        # Find user with matching email (case-insensitive)
        for user in users:
            if user.email and user.email.lower() == email:
                return user
                
        return None
    
    @staticmethod
    def authenticate_user(username: str, password: str) -> Optional[User]:
        """Static wrapper for authenticate_user."""
        return _user_service_instance.authenticate_user(username, password)
    
    @staticmethod
    def delete_user(user_id: int, admin_id: int) -> Dict[str, Any]:
        """Static wrapper for delete_user."""
        return _user_service_instance.delete_user(user_id, admin_id)
    
    @staticmethod
    def get_all_users() -> List[User]:
        """Get all users."""
        return User.query.all()
    
    @staticmethod
    def get_users_by_role(role: str) -> List[User]:
        """Get users by role."""
        return User.query.filter_by(role=role).all()
    
    @staticmethod
    def request_director_promotion(user_id: int, reason: str) -> DirectorRequest:
        """Request director promotion for a user."""
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        
        if user.is_director or user.is_admin:
            raise ValueError("User is already a director or admin")
        
        # Check if there's already a pending request
        existing = DirectorRequest.query.filter_by(
            user_id=user_id, status="pending"
        ).first()
        
        if existing:
            raise ValueError("There's already a pending director request for this user")
        
        request = DirectorRequest(user_id=user_id, notes=reason)
        db.session.add(request)
        # Flush to ensure the ID is assigned before returning
        db.session.flush()
        # Remove manual commit since this should be handled by transaction context
        return request
    
    @staticmethod
    def get_director_requests() -> List[DirectorRequest]:
        """Get all director requests."""
        return DirectorRequest.query.all()
    
    @staticmethod
    def get_director_requests_by_status(status: str) -> List[DirectorRequest]:
        """Get director requests by status."""
        return DirectorRequest.query.filter_by(status=status).all()
    
    @staticmethod
    def update_director_request_status(request_id: int, status: str) -> DirectorRequest:
        """Update director request status."""
        request = db.session.get(DirectorRequest, request_id)
        if not request:
            raise ValueError("Director request not found")
        
        request.status = status
        # Remove manual commit since this should be handled by transaction context
        return request
    
    @staticmethod
    def approve_director_request(request_id: int) -> DirectorRequest:
        """Approve director request."""
        request = db.session.get(DirectorRequest, request_id)
        if not request:
            raise ValueError("Director request not found")
        
        request.approve(User.query.first())  # Use first user as admin for simplicity
        # Remove manual commit since this should be handled by transaction context
        return request
    
    @staticmethod
    def reject_director_request(request_id: int) -> DirectorRequest:
        """Reject director request."""
        request = db.session.get(DirectorRequest, request_id)
        if not request:
            raise ValueError("Director request not found")
        
        request.reject(User.query.first(), "Request rejected")  # Use first user as admin
        # Remove manual commit since this should be handled by transaction context
        return request
    
    @staticmethod
    def get_user_stats(user_id: int) -> Dict[str, Any]:
        """Get user statistics."""
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        
        return user.get_statistics()
    
    @staticmethod
    def can_view_admin_panel(user_id: int) -> bool:
        """Check if user can view admin panel."""
        user = db.session.get(User, user_id)
        if not user:
            return False
        
        return user.can_view_admin_panel()

    @staticmethod
    def soft_delete_user(user_id: int) -> None:
        """Soft delete a user."""
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        
        user.anonymize()
        # Remove manual commit since this should be handled by transaction context





class DirectorRequestService:
    """
    Service for managing director promotion requests.
    """
    
    @staticmethod
    def create_request(user_id: int, notes: Optional[str] = None) -> DirectorRequest:
        """
        Create director promotion request.

        Args:
            user_id: ID of user requesting promotion
            notes: Optional notes from the user

        Returns:
            DirectorRequest: Created request

        Raises:
            ValueError: If user invalid or request already exists
        """
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        if user.is_admin or user.is_director:
            raise ValueError("User is already admin or director")

        # Check if there's already a pending request
        existing = DirectorRequest.query.filter_by(
            user_id=user_id, status="pending"
        ).first()

        if existing:
            raise ValueError("There's already a pending director request for this user")

        try:
            request = DirectorRequest(user_id=user_id, notes=notes)

            db.session.add(request)
            db.session.commit()

            return request

        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Failed to create director request: {str(e)}")

    @staticmethod
    def get_pending_requests() -> List[DirectorRequest]:
        """
        Get all pending director requests.

        Returns:
            List[DirectorRequest]: Pending requests ordered by date
        """
        return (
            DirectorRequest.query.filter_by(status="pending")
            .order_by(DirectorRequest.requested_at)
            .all()
        )

    @staticmethod
    def get_user_requests(user_id: int) -> List[DirectorRequest]:
        """
        Get all requests for a specific user.

        Args:
            user_id: ID of user

        Returns:
            List[DirectorRequest]: User's requests ordered by date
        """
        return (
            DirectorRequest.query.filter_by(user_id=user_id)
            .order_by(desc(DirectorRequest.requested_at))
            .all()
        )

    @staticmethod
    def process_request(
        request_id: int, admin_user: User, approve: bool, notes: Optional[str] = None
    ) -> DirectorRequest:
        """
        Process director request (approve/reject).

        Args:
            request_id: ID of request to process
            admin_user: Admin user processing the request
            approve: True to approve, False to reject
            notes: Optional processing notes

        Returns:
            DirectorRequest: Processed request

        Raises:
            PermissionError: If admin_user is not admin
            ValueError: If request not found or already processed
        """
        if not admin_user.is_admin:
            raise PermissionError("Only admins can process director requests")

        request = db.session.get(DirectorRequest, request_id)
        if not request:
            raise ValueError("Director request not found")

        if request.status != "pending":
            raise ValueError("Request has already been processed")

        try:
            if notes:
                request.notes = notes

            if approve:
                request.approve(admin_user)
            else:
                request.reject(admin_user, notes)

            db.session.commit()
            return request

        except Exception as e:
            db.session.rollback()
            raise ValueError(f"Failed to process request: {str(e)}")

    @staticmethod
    def get_requests_summary() -> Dict[str, int]:
        """
        Get summary of director requests.

        Returns:
            Dict[str, int]: Request counts by status
        """
        summary = {}

        # Count requests by status
        for status in ["pending", "approved", "rejected"]:
            count = DirectorRequest.query.filter_by(status=status).count()
            summary[status] = count

        summary["total"] = DirectorRequest.query.count()

        return summary


class UserStatsService:
    """
    Service for user statistics and analytics.

    Provides comprehensive analytics and statistics about users,
    their activities, and system-wide metrics.
    """

    @staticmethod
    def get_top_players(
        limit: int = 10, by: str = "win_rate", min_matches: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get top players by various metrics.

        Args:
            limit: Number of players to return
            by: Metric to sort by (win_rate, matches_played, tournaments_played)
            min_matches: Minimum matches played to be included

        Returns:
            List[Dict[str, Any]]: Top players with their stats
        """
        users = User.query.filter_by(role="player").all()

        user_stats = []
        for user in users:
            stats = user.get_statistics()

            # Filter by minimum matches
            if stats["total_matches"] >= min_matches:
                user_stats.append({"user": user, "stats": stats})

        # Sort by specified metric
        if by == "win_rate":
            user_stats.sort(key=lambda x: x["stats"]["win_percentage"], reverse=True)
        elif by == "matches_played":
            user_stats.sort(key=lambda x: x["stats"]["total_matches"], reverse=True)
        elif by == "tournaments_played":
            user_stats.sort(
                key=lambda x: x["stats"]["tournaments_played"], reverse=True
            )
        elif by == "rack_win_rate":
            user_stats.sort(
                key=lambda x: x["stats"].get("rack_win_percentage", 0), reverse=True
            )

        return user_stats[:limit]


class UserDeletionService:
    @staticmethod
    def _get_admin_user() -> User:
        # policy: primo utente con ruolo 'admin'
        admin = User.query.filter_by(role=UserRole.ADMIN.value).first()
        if not admin:
            raise RuntimeError("Nessun utente admin trovato per riassegnazioni")
        return admin

    @staticmethod
    def _remove_director_requests(user: User) -> None:
        DirectorRequest.query.filter_by(
            user_id=user.id, status=DirectorRequestStatus.PENDING.value
        ).delete(synchronize_session=False)
        # se approvata, la gestione avviene in _reassign_directorships

    @staticmethod
    def _reassign_directorships(user: User) -> None:
        admin = UserDeletionService._get_admin_user()
        # Tornei dove è unico direttore → assegna ad admin
        td_rows = db.session.query(TournamentDirector).filter_by(user_id=user.id).all()
        tournament_ids = {r.tournament_id for r in td_rows}
        for tid in tournament_ids:
            # conta co-direttori diversi da user
            others = (
                db.session.query(TournamentDirector)
                .filter(
                    TournamentDirector.tournament_id == tid,
                    TournamentDirector.user_id != user.id,
                )
                .count()
            )
            if others == 0:
                # aggiungi admin come direttore, se non già presente
                exists = (
                    db.session.query(TournamentDirector)
                    .filter_by(tournament_id=tid, user_id=admin.id)
                    .first()
                )
                if not exists:
                    db.session.add(
                        TournamentDirector(
                            tournament_id=tid, user_id=admin.id, assigned_by_id=admin.id
                        )
                    )
        # rimuovi user dal ruolo direttore in tutti i tornei
        db.session.query(TournamentDirector).filter_by(user_id=user.id).delete(
            synchronize_session=False
        )
        # Prove standalone con director_id=user.id → assegna ad admin
        db.session.query(Prova).filter_by(director_id=user.id).update(
            {"director_id": admin.id}, synchronize_session=False
        )

    @staticmethod
    def _handle_inscriptions(user: "User") -> None:
        """Prove non iniziate → disiscrizione; iniziate → marca withdrawn
        (policy è su Prova)."""
        inscriptions = Inscription.query.filter_by(user_id=user.id).all()
        for ins in inscriptions:
            prova = db.session.get(Prova, ins.prova_id)
            if not prova:
                continue
            # Prova non iniziata: rimuoviamo l'iscrizione
            if (prova.current_round or 0) == 0:
                db.session.delete(ins)
            else:
                # Prova iniziata: marca come ritirato (policy gestita a livello Prova)
                if not ins.is_withdrawn:
                    ins.is_withdrawn = True
                    ins.withdrawn_at = datetime.utcnow()

    @staticmethod
    def _forfeit_playing_matches(user: "User") -> None:
        """Quando un utente si cancella:
        - vs X (bye) → elimina match
        - vs cancellato/ritirato anch'esso → elimina match se non completato
        - vs avversario attivo → chiudi a tavolino (punteggio massimo all'avversario)
        """
        in_progress = Match.query.filter(
            Match.__table__.c.status.in_([MatchStatus.PENDING.value, MatchStatus.PLAYING.value]),
            ((Match.player1_id == user.id) | (Match.player2_id == user.id)),
        ).all()

        withdrawn_ids = {
            ins.user_id for ins in Inscription.query.filter_by(is_withdrawn=True).all()
        }
        deleted_ids = {
            u.id for u in User.query.filter(User.deleted_at.isnot(None)).all()
        }
        cancelled_ids = withdrawn_ids | deleted_ids

        for m in in_progress:
            # BYE (X) → elimina subito
            if m.player1_id is None or m.player2_id is None:
                db.session.delete(m)
                continue

            opp_id = m.player2_id if m.player1_id == user.id else m.player1_id
            opp_cancelled = opp_id in cancelled_ids

            # entrambi cancellati → elimina (qui siamo in pending/playing)
            if opp_cancelled:
                db.session.delete(m)
                continue

            # avversario attivo → forfait
            prova = db.session.get(Prova, m.prova_id)
            if not prova:
                # Se la prova non esiste, elimina il match
                db.session.delete(m)
                continue
            
            to_win = prova.get_winning_score()
            if m.player1_id == user.id:
                m.player2_score = to_win
            else:
                m.player1_score = to_win
            m.status = MatchStatus.COMPLETED.value

    @staticmethod
    def delete_user(user: User) -> None:
        """Soft delete + orchestrazione dominio. No bulk-ops ORM mixate
        con stateful objects.
        Solleva in caso manchino precondizioni (es. admin assente).
        """
        # Guard: impedisci eliminazione dell'ultimo admin
        if user.role == UserRole.ADMIN.value:
            active_admins = (
                User.query.filter_by(role=UserRole.ADMIN.value)
                .filter(User.deleted_at.is_(None))
                .count()
            )
            if active_admins <= 1:
                raise ValueError("Non è possibile eliminare l’ultimo amministratore.")

        # 1) richieste direttore
        UserDeletionService._remove_director_requests(user)
        # 2) riassegnazioni di direzione
        UserDeletionService._reassign_directorships(user)
        # 3) iscrizioni e forfait
        UserDeletionService._handle_inscriptions(user)
        UserDeletionService._forfeit_playing_matches(user)
        # 4) anonimizzazione e blocco
        user.anonymize()
        db.session.flush()  # forza validazione UoW qui
        db.session.commit()


@staticmethod
def get_activity_summary(days: int = 30) -> Dict[str, Any]:
    """
    Get system-wide activity summary.

    Args:
        days: Number of days to look back for recent activity

    Returns:
        Dict[str, Any]: Activity summary
    """
    # Total users by role
    total_users = User.query.count()
    admins = User.query.filter_by(role="admin").count()
    directors = User.query.filter_by(role="director").count()
    players = User.query.filter_by(role="player").count()

    # Since User doesn't have created_at timestamp, we can't calculate recent
    # registrations
    # This will be enhanced in Task 1.5 if timestamp functionality is needed
    recent_registrations = 0  # Placeholder for User model without timestamps

    # Director requests (these have timestamps via BaseModel)
    recent_cutoff = datetime.utcnow() - timedelta(days=days)
    recent_requests = DirectorRequest.query.filter(
        DirectorRequest.requested_at >= recent_cutoff
    ).count()

    # Tournament assignments
    active_assignments = TournamentDirector.query.count()

    return {
        "user_counts": {
            "total_users": total_users,
            "admins": admins,
            "directors": directors,
            "players": players,
        },
        "recent_activity": {
            "recent_registrations": recent_registrations,
            "recent_director_requests": recent_requests,
            "days_analyzed": days,
        },
        "director_info": {
            "pending_requests": DirectorRequest.query.filter_by(
                status="pending"
            ).count(),
            "active_assignments": active_assignments,
        },
    }

    @staticmethod
    def get_user_activity_timeline(user_id: int, days: int = 90) -> Dict[str, Any]:
        """
        Get user activity timeline.

        Args:
            user_id: ID of user
            days: Number of days to analyze

        Returns:
            Dict[str, Any]: User activity timeline

        Raises:
            ValueError: If user not found
        """
        user = db.session.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        timeline = {"user": user, "period_days": days, "activities": []}

        # Add registration if within period
        if user.created_at >= cutoff_date:
            timeline["activities"].append(
                {
                    "type": "registration",
                    "date": user.created_at,
                    "description": "User registered",
                }
            )

        # Add director requests
        requests = (
            DirectorRequest.query.filter(
                DirectorRequest.user_id == user_id,
                DirectorRequest.requested_at >= cutoff_date,
            )
            .order_by(DirectorRequest.requested_at)
            .all()
        )

        for request in requests:
            timeline["activities"].append(
                {
                    "type": "director_request",
                    "date": request.requested_at,
                    "description": f"Director promotion requested - {request.status}",
                }
            )

        # Add tournament assignments (if director)
        if user.is_director:
            assignments = (
                TournamentDirector.query.filter(
                    TournamentDirector.user_id == user_id,
                    TournamentDirector.assigned_at >= cutoff_date,
                )
                .order_by(TournamentDirector.assigned_at)
                .all()
            )

            for assignment in assignments:
                timeline["activities"].append(
                    {
                        "type": "tournament_assignment",
                        "date": assignment.assigned_at,
                        "description": (
                            "Assigned to tournament " f"{assignment.tournament_id}"
                        ),
                    }
                )

        # Sort activities by date
        timeline["activities"].sort(key=lambda x: x["date"], reverse=True)

        return timeline

    @staticmethod
    def get_role_distribution() -> Dict[str, Any]:
        """
        Get distribution of users by role with percentages.

        Returns:
            Dict[str, Any]: Role distribution data
        """
        total_users = User.query.count()

        if total_users == 0:
            return {"total_users": 0, "roles": {}, "percentages": {}}

        roles = {}
        percentages = {}

        for role in ["admin", "director", "player"]:
            count = User.query.filter_by(role=role).count()
            roles[role] = count
            percentages[role] = round((count / total_users) * 100, 1)

        return {"total_users": total_users, "roles": roles, "percentages": percentages}


@staticmethod
def get_registration_trends(days: int = 30) -> Dict[str, Any]:
    """
    Get user registration trends over time.

    Args:
        days: Number of days to analyze

    Returns:
        Dict[str, Any]: Registration trend data
    """
    # Since User model doesn't have timestamps, we can't provide actual trends
    # Return a basic structure for compatibility
    total_users = User.query.count()

    return {
        "period_days": days,
        "total_registrations": 0,  # No timestamp data available
        "average_per_day": 0.0,
        "daily_breakdown": {},
        "note": "Registration trends unavailable - User model has no timestamp fields",
        "total_users_in_system": total_users,
    }


class UserService(UserServiceCore):
    """
    Enhanced UserService that extends UserServiceCore with additional business logic methods.
    This class consolidates complex queries from routes into the service layer.
    """
    
    # Instance for static method delegation
    _instance = None
    
    def __init__(self):
        super().__init__()
    
    @classmethod
    def _get_instance(cls):
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = UserServiceCore()
        return cls._instance
    
    @classmethod
    def create_user(cls, username: str, email: str, password: str, role: str = "player", phone: Optional[str] = None) -> User:
        """Static wrapper for create_user instance method."""
        return cls._get_instance().create_user(username, email, password, role, phone)
    
    @classmethod
    def update_user(cls, user_id: int, **kwargs) -> User:
        """Static wrapper for update_user instance method."""
        return cls._get_instance().update_user(user_id, **kwargs)
    
    @classmethod
    def change_password(cls, user_id: int, old_password: str, new_password: str) -> bool:
        """Static wrapper for change_password instance method."""
        return cls._get_instance().change_password(user_id, old_password, new_password)
    
    @classmethod
    def authenticate_user(cls, username: str, password: str) -> Optional[User]:
        """Static wrapper for authenticate_user instance method."""
        return cls._get_instance().authenticate_user(username, password)
    
    @classmethod
    def get_user_by_id(cls, user_id: int) -> Optional[User]:
        """Static wrapper for get_user_by_id instance method."""
        return cls._get_instance().get_user_by_id(user_id)
    
    @classmethod
    def get_user_by_username(cls, username: str) -> Optional[User]:
        """Static wrapper for get_user_by_username instance method."""
        return cls._get_instance().get_user_by_username(username)
    
    @classmethod
    def get_user_by_email(cls, email: str) -> Optional[User]:
        """Static wrapper for get_user_by_email instance method."""
        return cls._get_instance().get_user_by_email(email)
    
    @classmethod
    def get_all_users(cls) -> List[User]:
        """Static wrapper for get_all_users."""
        return UserServiceCompat.get_all_users()
    
    @classmethod
    def get_users_by_role(cls, role: str) -> List[User]:
        """Static wrapper for get_users_by_role."""
        return UserServiceCompat.get_users_by_role(role)
    
    @classmethod
    def delete_user(cls, user_id: int, admin_id: int) -> Dict[str, Any]:
        """Static wrapper for delete_user instance method."""
        return cls._get_instance().delete_user(user_id, admin_id)
    
    @classmethod
    def request_director_promotion(cls, user_id: int, reason: str) -> DirectorRequest:
        """Static wrapper for request_director_promotion."""
        return UserServiceCompat.request_director_promotion(user_id, reason)
    
    @classmethod
    def get_director_requests(cls) -> List[DirectorRequest]:
        """Static wrapper for get_director_requests."""
        return UserServiceCompat.get_director_requests()
    
    @classmethod
    def get_director_requests_by_status(cls, status: str) -> List[DirectorRequest]:
        """Static wrapper for get_director_requests_by_status."""
        return UserServiceCompat.get_director_requests_by_status(status)
    
    @classmethod
    def update_director_request_status(cls, request_id: int, status: str) -> DirectorRequest:
        """Static wrapper for update_director_request_status."""
        return UserServiceCompat.update_director_request_status(request_id, status)
    
    @classmethod
    def approve_director_request(cls, request_id: int) -> DirectorRequest:
        """Static wrapper for approve_director_request."""
        return UserServiceCompat.approve_director_request(request_id)
    
    @classmethod
    def reject_director_request(cls, request_id: int) -> DirectorRequest:
        """Static wrapper for reject_director_request."""
        return UserServiceCompat.reject_director_request(request_id)
    
    @classmethod
    def get_user_stats(cls, user_id: int) -> Dict[str, Any]:
        """Static wrapper for get_user_stats."""
        return UserServiceCompat.get_user_stats(user_id)
    
    @classmethod
    def can_view_admin_panel(cls, user_id: int) -> bool:
        """Static wrapper for can_view_admin_panel."""
        return UserServiceCompat.can_view_admin_panel(user_id)
    
    @classmethod
    def soft_delete_user(cls, user_id: int) -> None:
        """Static wrapper for soft_delete_user."""
        return UserServiceCompat.soft_delete_user(user_id)

    @read_only(domain="user")
    def get_users_with_stats(self) -> List[tuple]:
        """
        Get all users with their statistics for the users list page.
        This consolidates the complex query from the users_list route.
        
        Returns:
            List of tuples containing (User, total_inscriptions, total_matches, matches_won)
        """
        from sqlalchemy import case
        
        # Track domain access
        self._track_domain_access()
        
        users = self._execute_with_tracking(
            lambda: db.session.query(
                User,
                func.count(Inscription.id).label("total_inscriptions"),
                func.count(Match.id).label("total_matches"),
                func.sum(case((Match.winner_id == User.id, 1), else_=0)).label(
                    "matches_won"
                ),
            )
            .outerjoin(Inscription, User.id == Inscription.user_id)
            .outerjoin(
                Match, db.or_(Match.player1_id == User.id, Match.player2_id == User.id)
            )
            .filter(User.role != "admin")
            .group_by(User.id)
            .order_by(desc("total_inscriptions"), User.username)
            .all()
        )
        
        return users
    
    @read_only(domain="user")
    def get_user_detail_data(self, user_id: int) -> Dict[str, Any]:
        """
        Get all data needed for the user detail page.
        This consolidates the complex queries from the user_detail route.
        
        Args:
            user_id: ID of the user to get data for
            
        Returns:
            Dictionary containing all user detail data
        """
        # Track domain access
        self._track_domain_access()
        
        user = self._execute_with_tracking(
            lambda: db.session.get(User, user_id)
        )
        if not user:
            raise ValueError("User not found")
        
        # Iscrizioni dell'utente
        inscriptions = self._execute_with_tracking(
            lambda: (
                Inscription.query.filter_by(user_id=user_id)
                .join(Prova)
                .join(Tournament)
                .order_by(Tournament.created_at.desc(), Prova.number.desc())
                .all()
            )
        )
        
        # Partite giocate
        matches = self._execute_with_tracking(
            lambda: (
                Match.query.filter(
                    db.or_(Match.player1_id == user_id, Match.player2_id == user_id)
                )
                .join(Prova)
                .join(Tournament)
                .order_by(
                    Tournament.created_at.desc(), Prova.number.desc(), Match.round_number.desc()
                )
                .all()
            )
        )
        
        # Classifiche per torneo
        classifications = self._execute_with_tracking(
            lambda: (
                Classification.query.filter_by(user_id=user_id)
                .join(Tournament)
                .order_by(Tournament.created_at.desc())
                .all()
            )
        )
        
        return {
            "user": user,
            "inscriptions": inscriptions,
            "matches": matches,
            "classifications": classifications
        }
    
    @read_only(domain="user")
    def get_user_statistics(self, user_id: int) -> Dict[str, Any]:
        """
        Calculate user statistics for display on the user detail page.
        
        Args:
            user_id: ID of the user to calculate statistics for
            
        Returns:
            Dictionary containing user statistics
        """
        # Track domain access
        self._track_domain_access()
        
        user_data = self.get_user_detail_data(user_id)
        matches = user_data["matches"]
        inscriptions = user_data["inscriptions"]
        
        total_matches = len([m for m in matches if m.status == MatchStatus.COMPLETED.value])
        won_matches = len(
            [
                m
                for m in matches
                if m.status == MatchStatus.COMPLETED.value and m.winner_id == user_id
            ]
        )
        win_percentage = (won_matches / total_matches * 100) if total_matches > 0 else 0
        
        stats = {
            "total_inscriptions": len(inscriptions),
            "total_matches": total_matches,
            "won_matches": won_matches,
            "lost_matches": total_matches - won_matches,
            "win_percentage": round(win_percentage, 1),
            "tournaments_played": len(
                set([insc.prova.tournament_id for insc in inscriptions])
            ),
        }
        
        return stats
    
    @read_only(domain="user")
    def get_user_matches(self, user_id: int, limit: int = 10) -> List[Match]:
        """
        Get user matches with proper ordering, limited to recent matches.
        
        Args:
            user_id: ID of the user to get matches for
            limit: Maximum number of matches to return
            
        Returns:
            List of recent matches
        """
        # Track domain access
        self._track_domain_access()
        
        user_data = self.get_user_detail_data(user_id)
        matches = user_data["matches"]
        
        # Partite recenti (ultime 10)
        recent_matches = [m for m in matches if m.status == MatchStatus.COMPLETED.value][
            :limit
        ]
        
        return recent_matches
    
    @read_only(domain="user")
    def get_user_classifications(self, user_id: int) -> List[Classification]:
        """
        Get user classifications ordered by date.
        
        Args:
            user_id: ID of the user to get classifications for
            
        Returns:
            List of user classifications
        """
        # Track domain access
        self._track_domain_access()
        
        user_data = self.get_user_detail_data(user_id)
        return user_data["classifications"]


