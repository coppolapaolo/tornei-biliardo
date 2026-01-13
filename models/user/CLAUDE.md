# User Domain

## Purpose

Central entity of the platform, referenced by ALL other domains.

**Core Responsibilities:**
- User authentication and password management
- Role-based access control (Admin, Director, Player)
- Director promotion workflow with request system
- Venue manager assignment and permissions
- Soft delete with PII anonymization (GDPR)
- Encrypted personal data (email, phone)

---

## Quick Reference

```python
from models.user import User, DirectorAssignment, DirectorRequest, VenueManagement
from models.user.services import UserService
from models.user.permission_service import UserPermissionService
from models.user.venue_manager_service import VenueManagerService
from models.user.permissions import PermissionChecker
from models.user.role_enum import UserRole

# Create user
user = UserService.create_user(
    username="mario", email="mario@example.com",
    password="secure123", role="player"
)

# Check role
if user.is_admin: ...
elif user.is_director: ...
elif user.is_player: ...

# Check permissions
if user.can_manage_competition(gara_id): ...
if user.can_manage_campionato(campionato_id): ...

# Director promotion workflow
request = UserPermissionService.create_director_request(user.id)
UserPermissionService.process_director_request(
    request_id=request.id, admin_user=admin, approve=True
)

# Soft delete with anonymization
user.anonymize()
db.session.commit()
# username → "deleted-{id}-{date}", email/phone → None
```

---

## Key Models

### User
**Key Fields:** `username`, `email` (encrypted), `password_hash`, `role`, `phone` (encrypted), `fargo_rating`, `elo_rating`, `deleted_at`

**Role Properties:** `is_admin`, `is_director`, `is_player`, `is_venue_manager`, `is_active`

**Permission Methods:**
- `can_manage_campionato(campionato_id)` - Admin or assigned director
- `can_manage_competition(competition_id)` - Admin or assigned director
- `can_inscribe_to_competition(competition_id)` - Player, not manager

**Key Methods:**
- `set_password(password)`, `check_password(password)`
- `anonymize()` - Soft delete with PII removal
- `get_statistics()` - Dashboard stats

### DirectorAssignment
Generic director assignment to campionato or gara.

**Composite PK:** `(user_id, entity_type, entity_id)` where `entity_type` is "campionato" or "gara"

### DirectorRequest
Director promotion request with admin approval.

**Key Fields:** `user_id`, `status` (pending/approved/rejected), `processed_by_id`

**Methods:** `approve(admin)`, `reject(admin, notes)`

### VenueManagement
Venue manager assignment.

**Key Fields:** `user_id`, `venue_id`, `assigned_by_id`, `is_active`

---

## Services

### UserService (Facade)
- `create_user(...)`, `update_user(...)`, `change_password(...)`
- `promote_to_director(...)`, `soft_delete_user(...)`

### UserPermissionService
- `create_director_request(user_id)` - Emits `DirectorRequestCreatedEvent`
- `process_director_request(...)` - Approve/reject
- `get_pending_director_requests()`

### VenueManagerService
- `create_venue_manager_request(...)`, `process_venue_manager_request(...)`

### PermissionChecker
Static methods for permission checks + decorators:
```python
@role_required(UserRole.ADMIN)
@permission_required("manage_competition", competition_id_param="gara_id")
```

---

## Do Not

- **Do not hard-delete User records** - Use `user.anonymize()` to preserve foreign key relationships
- **Do not set role via properties** - `user.is_admin = True` fails; use `user.role = UserRole.ADMIN.value`
- **Do not query encrypted fields directly** - `EncryptedString` handles encryption/decryption
- **Do not forget soft delete filter** - `User.query.all()` auto-excludes deleted; use `with_deleted()` to include
- **Do not call `db.session.commit()`** - Services use `@transactional`
- **Do not skip permission checks** - Always verify `can_manage_*` before allowing operations

---

## Role Hierarchy

- **Admin**: Manage ALL campionatos, gare, venues
- **Director**: Manage ASSIGNED campionatos/gare only
- **Player**: Inscribe to competitions, propose matches, request promotions

---

## Cross-References

- **Competition Domain**: Inscription, director assignments
- **Notification Domain**: User notifications
- **Events Domain**: `DirectorRequestCreatedEvent`, `UserEvents`
