# PyRight Errors Analysis - tests/new/

## Error Categories and Fix Plan

### 1. RackService API Mismatches (4 errors)
**Files**: test_UC01_usecase_1_to_7_guest_access_workflows.py
**Error**: `Cannot access attribute "create_rack" for class "type[RackService]"`
**Lines**: 590, 592, 763, 765
**Fix**: Replace `RackService.create_rack(match_id, winner_id, reason)` with `RackService.add_rack_with_score_update(match_id, winner_id, reported_by_id=1, validated_by_admin=True)`

### 2. AvailabilityService API Mismatches (4 errors)
**Files**: test_gare_usecase_complete_workflow.py, test_user_workflows_complete.py
**Errors**:
- `set_one_time_availability` → should be `set_player_availability`
- `request_match_from_availability` → should be `create_availability_based_match_request`
- `respond_to_match_request` → needs investigation (might be IndividualMatchService)
- `set_venue_preference` → should be `set_venue_availability`

### 3. IndividualMatchService Missing Methods (4 errors)
**Files**: test_gare_usecase_6_individual_matches.py, test_gare_usecase_complete_workflow.py
**Errors**:
- `confirm_rack_result` - method doesn't exist
- `report_result` - method doesn't exist
**Fix**: Need to check if these should exist or use different API

### 4. GaraService API Mismatches (1 error)
**Files**: test_gare_usecase_5_guest_access.py
**Error**: `Cannot access attribute "create_random_round" for class "type[GaraService]"`
**Fix**: Check if method exists elsewhere or needs different API

### 5. Other Service Missing Methods (multiple errors)
**Services with missing methods**:
- `DirectorRequestService`: `create_director_request`, `approve_director_request`
- `InscriptionService`: `withdraw_inscription`
- `NotificationService`: `send_system_notification`
- `PlayoffService`: `get_qualified_players`
- `ExamService`: `record_challenge_attempt_in_exam`, `finalize_exam_attempt`
- `TournamentService`: `update_campionato_classification`

### 6. Parameter Issues (4 errors)
**Files**: test_user_workflows_complete.py
**Issues**:
- Missing parameter "playoff_type"
- Arguments missing for parameters "name", "director_id"
- No parameter named "title", "challenges", "created_by_id"

### 7. Type Safety Issues (3 errors)
**Files**: test_challenge_image_paths_fix.py
**Issues**:
- `str | None` cannot be assigned to functions expecting `str`
- Need proper null checks

### 8. SQLAlchemy Relationship Issues (1 error)
**Files**: test_gare_usecase_6_individual_matches.py
**Error**: `RelationshipProperty[Any]` incompatible with `Sized` in `len()`
**Fix**: Use `.all()` on relationship: `len(obj.relationship.all())`

## Fix Strategy

1. **Start with API corrections** - fix method name mismatches
2. **Check service implementations** - verify which methods actually exist
3. **Add missing methods** - implement methods that should exist
4. **Fix type safety** - add null checks and proper typing
5. **Fix parameter issues** - correct function calls
6. **Verify all fixes** - run pyright again

## Implementation Order

1. Fix RackService calls (easy, clear fix)
2. Fix AvailabilityService method names (rename to existing methods)
3. Investigate missing service methods (might need implementation)
4. Fix type safety issues (add null checks)
5. Fix parameter issues (check function signatures)
6. Fix SQLAlchemy relationship issues (add .all())