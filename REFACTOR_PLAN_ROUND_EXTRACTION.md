# Refactor Plan: Complete RoundService Extraction

## Overview
Complete extraction of complex round management methods from GaraService to RoundService, following TDD principles and maintaining codebase consistency.

## Status: Task 1.2 - GaraService Decomposition (50% → 80%)

### Current State
- **GaraService**: 1427 lines (target: <500 lines)
- **Extracted**: StateService (82), InscriptionService (377), RoundService (248)
- **Remaining**: ~275 lines of complex round logic to extract

### Methods to Extract

#### 1. `create_round_with_strategy` (~150 lines)
**Complexity**: High - Multi-strategy support, transaction management, match creation
```python
def create_round_with_strategy(gara_id: int, round_number: int, discipline_override: Optional[str] = None) -> tuple[int, int, int, int]
```
**Dependencies**:
- `models.matchmaking.bootstrap.get_registry()` - Strategy pattern
- `amalfi.create_amalfi_round_matches()` - Legacy Amalfi binding
- `models.match.models.Match, TrioMatch` - Match creation
- Database transaction handling

**Logic Flow**:
1. Validate gara and round_number
2. Check for existing matches (idempotent)
3. Route to Amalfi legacy or unified strategy
4. Create Match/TrioMatch records
5. Return match statistics

#### 2. `preview_round_with_strategy` (~80 lines)
**Complexity**: Medium - Similar to create but read-only
```python
def preview_round_with_strategy(gara_id: int, round_number: int) -> Dict[str, Any]
```
**Dependencies**:
- Same strategy routing as create_round_with_strategy
- `models.user.models.User` - Display names for preview
- No database writes (preview only)

**Logic Flow**:
1. Validate gara and round_number
2. Route to appropriate strategy preview
3. Convert strategy output to UI format
4. Return formatted match preview

#### 3. `update_round_progression` (~45 lines)
**Complexity**: Medium - Round completion detection and classification updates
```python
def update_round_progression(gara_id: int) -> None
```
**Dependencies**:
- `models.match.models.Match` - Round completion check
- `models.classification.models.RoundClassification` - Classification calculation
- Database updates for progression state

**Logic Flow**:
1. Iterate through all rounds
2. Check completion status
3. Update current_round if needed
4. Calculate/update round classifications
5. Commit progression state

## TDD Strategy

### Phase 1: Red - Create Failing Tests
Update existing `tests/new/refactor/tdd/test_round_service_tdd.py`:
- Test complete `create_round_with_strategy` behavior
- Test complete `preview_round_with_strategy` behavior
- Test complete `update_round_progression` behavior
- Test error cases and edge conditions

### Phase 2: Green - Extract Methods
Move methods from GaraService to RoundService:
1. Copy method implementations
2. Update imports and dependencies
3. Maintain exact behavior compatibility
4. Ensure all tests pass

### Phase 3: Refactor - Optimize
1. Remove duplicated code
2. Improve error handling
3. Optimize type safety
4. Clean up method signatures

## Implementation Details

### Strategy Pattern Consistency
```python
# Use existing registry pattern
from models.matchmaking.bootstrap import get_registry

registry = get_registry()
strategy_mapping = {
    "random": "random_anti_rematch",
    "amalfi": "amalfi",
    "round_robin": "round_robin",
    "direct_elimination": "direct_elimination",
    "double_knockout": "double_knockout",
}
```

### Transaction Pattern
```python
try:
    # Business logic with database operations
    db.session.commit()
    return result
except Exception as e:
    db.session.rollback()
    raise ValueError(f"Error message: {str(e)}")
```

### Type Safety
- Maintain exact return types as current implementation
- Add proper type hints for all parameters
- Use TYPE_CHECKING for circular import avoidance

## Backward Compatibility

### GaraService Facade
Methods will remain in GaraService as delegates to RoundService to maintain existing API contracts:
```python
@staticmethod
def create_round_with_strategy(gara_id: int, round_number: int, discipline_override=None):
    """Facade: delegate to RoundService."""
    return RoundService.create_round_with_strategy(gara_id, round_number, discipline_override)
```

### Import Consistency
Maintain existing import patterns for routes and other consumers.

## Quality Assurance

### Code Quality Checklist
- [ ] `black .` - Format all modified code
- [ ] `pyright` - Ensure 0 type errors
- [ ] All existing tests pass
- [ ] New TDD tests pass
- [ ] No duplicated code
- [ ] Consistent error handling

### Test Coverage
- [ ] Unit tests for each extracted method
- [ ] Integration tests with different strategies
- [ ] Error condition tests
- [ ] Edge case tests (empty matches, invalid rounds)

## Expected Outcomes

### Metrics After Completion
- **GaraService**: ~1152 lines (1427 - 275) = **35.8% reduction**
- **RoundService**: ~523 lines (248 + 275) = **Complete service**
- **Overall Progress**: Task 1.2 from 50% → **80% complete**

### Benefits
1. **Single Responsibility**: Round logic centralized
2. **Testability**: Easier to test round operations in isolation
3. **Maintainability**: Clear separation of concerns
4. **Extensibility**: Easier to add new round features

## Risk Mitigation

### Strategy Pattern Complexity
- Keep legacy Amalfi binding for compatibility
- Ensure strategy registry works correctly
- Test all strategy types thoroughly

### Transaction Management
- Preserve existing transaction patterns
- Ensure proper rollback on errors
- Maintain database consistency

### Integration Points
- Verify all route integrations work
- Check service interdependencies
- Ensure classification updates work

## Next Steps After Completion

1. **Continue GaraService Reduction**: Target remaining ~650 lines
2. **Transaction Management**: Implement @transactional decorator (Task 1.1)
3. **UserService Decomposition**: Start Task 1.3

---

**Created**: 2025-01-18
**Author**: Refactoring Task 1.2
**Status**: Ready for Implementation