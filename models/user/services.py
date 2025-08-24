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
from ..transaction import DomainService, transactional, read_only, transaction_manager

from models.match import Match
from models.competition.models import Prova, Inscription
from models.status_enum import MatchStatus, DirectorRequestStatus
from models.user.role_enum import UserRole


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
        existing_email = self._execute_with_tracking(
            lambda: User.query.filter(
                func.lower(User.email) == func.lower(email.strip())
            ).first()
        )
        if existing_email:
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
                existing = self._execute_with_tracking(
                    lambda: User.query.filter(
                        func.lower(User.email) == func.lower(new_email),
                        User.id != user_id,
                    ).first()
                )
                if existing:
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
            raise ValueError("User not found")

        if not user.check_password(old_password):
            raise ValueError("Current password is incorrect")

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
    def delete_user(user_id: int, admin_id: int) -> Dict[str, Any]:
        """Static wrapper for delete_user."""
        return _user_service_instance.delete_user(user_id, admin_id)


# Maintain backward compatibility by exposing the static wrapper as UserService
UserService = UserServiceCompat


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
