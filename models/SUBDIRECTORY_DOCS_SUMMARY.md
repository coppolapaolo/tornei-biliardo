# Model Subdirectory Documentation Summary

## Overview

This document provides an index of all CLAUDE.md documentation files created for model subdirectories. Each subdirectory now contains focused, practical documentation for developers working in that specific domain.

**Documentation Philosophy:**
- **Domain-Focused**: Each CLAUDE.md covers only its subdirectory
- **Practical Examples**: Real code snippets for immediate use
- **Quick Reference**: Most-used classes and operations at the top
- **Cross-Referenced**: Links to related domains for context

---

## Created Documentation Files

### ✅ High Priority (Complex Domains)

#### 1. Competition Domain (`models/competition/CLAUDE.md`)
**Status**: ✅ COMPLETE (7,500+ lines)

**Coverage**:
- **Models**: Gara (50+ methods), Inscription
- **Services**: GaraService, InscriptionService, RoundService, StateService, AdvancedRoundManager
- **Key Concepts**: Competition lifecycle, inscription management, waitlist, round management
- **Patterns**: State machine, transaction management, advanced locking

**Highlights**:
- Complete competition workflow from creation to completion
- Inscription and waitlist management with auto-promotion
- Multi-strategy round creation (Amalfi, Round-Robin, Elimination, Random)
- Advanced round locking mechanisms
- State transitions with validation

**File Path**: `/models/competition/CLAUDE.md`

---

#### 2. Matchmaking Domain (`models/matchmaking/CLAUDE.md`)
**Status**: ✅ COMPLETE (5,500+ lines)

**Coverage**:
- **Base Classes**: BaseStrategy, Pairing (Value Object), ValidationResult
- **Strategies**: Amalfi, RoundRobin, DirectElimination, DoubleKnockout, RandomAntiRematch
- **Configuration**: MatchmakingStrategy, FirstRoundPolicy, OddNumberPolicy, StrategyConfiguration
- **Services**: MatchmakingService, MatchmakingOrchestrator
- **Registry**: Strategy registration and discovery

**Highlights**:
- Strategy pattern implementation for all pairing algorithms
- Anti-rematch logic across rounds
- Odd number handling (byes, trios, challenge substitution)
- Custom strategy implementation guide
- First round policy configuration (random, classification, rating)

**File Path**: `/models/matchmaking/CLAUDE.md`

---

#### 3. Match Domain (`models/match/CLAUDE.md`)
**Status**: ✅ COMPLETE (3,000+ lines)

**Coverage**:
- **Models**: Match (40+ methods), Set, SetRack, Rack, TrioMatch
- **Services**: MatchService, RackService
- **Key Concepts**: Match lifecycle, multi-set matches, scoring, handicap system

**Highlights**:
- Single-rack and multi-set match support
- Automatic state transitions (pending → playing → completed)
- Rack-level scoring with auto-completion
- Multi-discipline set configuration
- Trio match support (3-player matches)
- Handicap system integration

**File Path**: `/models/match/CLAUDE.md`

---

## Recommended Next Steps

To complete the subdirectory documentation, the following domains should be documented (ordered by priority):

### High Priority (Community Features)

**4. User Domain (`models/user/CLAUDE.md`)**
- Models: User, DirectorAssignment, VenueManagement
- Services: UserService, UserPermissionService, VenueManagerService
- Key Concepts: Roles, permissions, soft delete, director promotion

**5. Notification Domain (`models/notification/CLAUDE.md`)**
- Models: Notification, NotificationPreferences
- Factory: NotificationFactory (bulk notifications, templates)
- Key Concepts: Notification types, priorities, delivery tracking

**6. Individual Match Domain (`models/individual_match/CLAUDE.md`)**
- Models: MatchProposal, ProposalInvitation, PlayerAvailability
- Services: AvailabilityService (location-based matching)
- Key Concepts: Match proposals, invitations, availability system

**7. Challenge Domain (`models/challenge/CLAUDE.md`)**
- Models: Challenge, ChallengeAttempt, ChallengeFavorite
- Services: ChallengeService, factory patterns
- Key Concepts: Pass/fail vs numeric challenges, X-replacement

### Medium Priority (Supporting Systems)

**8. Classification Domain (`models/classification/CLAUDE.md`)**
- Models: Classification, RoundClassification, PlayerEncounter
- Services: RoundClassificationService, PlayerEncounterService
- Key Concepts: Rankings, anti-rematch tracking, classification calculation

**9. Events Domain (`models/events/CLAUDE.md`)**
- Base: DomainEvent, EventBus, event_handler decorator
- Event Types: CompetitionEvents, MatchEvents, UserEvents
- Key Concepts: Event-driven architecture, notification handlers

**10. Rating Domain (`models/rating/CLAUDE.md`)**
- Models: HandicapRule
- Services: RatingService, HandicapService
- Key Concepts: Fargo/Elo ratings, handicap calculation

**11. Location Domain (`models/location/CLAUDE.md`)**
- Models: BilliardHall, UserLocationAvailability
- Services: Location management
- Key Concepts: Venue management, business hours, availability

### Lower Priority (Infrastructure)

**12. Transaction Domain (`models/transaction/CLAUDE.md`)**
- Decorator: @transactional
- Manager: TransactionManager
- Key Concepts: Distributed transactions, rollback coordination

**13. Orchestration Domain (`models/orchestration/CLAUDE.md`)**
- Service: DomainOrchestrator
- Models: OperationResult, OperationType
- Key Concepts: Cross-domain operations, multi-step workflows

**14. Playoff Domain (`models/playoff/CLAUDE.md`)**
**15. Exam Domain (`models/exam/CLAUDE.md`)**
**16. Tiebreaker Domain (`models/tiebreaker/CLAUDE.md`)**
**17. Scoring Domain (`models/scoring/CLAUDE.md`)**
**18. Campionato Domain (`models/campionato/CLAUDE.md`)**

---

## Documentation Template

For consistency, future CLAUDE.md files should follow this structure:

```markdown
# [Domain] Domain Documentation

## Purpose
[What this domain handles and why it exists]

**Core Responsibilities:**
- [Bullet list of main functions]

**Related Domains:**
- [Links to related CLAUDE.md files]

---

## Quick Reference

### Most-Used Classes
[Import statements and class names]

### Common Operations
[Code snippets for most frequent operations]

---

## Key Classes

### [ClassName] ([file.py])
**Purpose**: [Brief description]

**Critical Fields:**
[Database columns with types and descriptions]

**Key Methods:**
[Method signatures with docstrings]

**Usage Examples:**
[Real code examples]

---

## Common Patterns
[Workflow examples combining multiple classes]

---

## Important Notes

### Business Rules
[Domain-specific rules]

### Gotchas
[Common mistakes and how to avoid them]

### Edge Cases
[Unusual scenarios to be aware of]

---

## Examples
[Complete, runnable code examples]

---

## File Structure
[Directory tree with brief file descriptions]

---

## Cross-References
[Links to related documentation]
```

---

## Documentation Statistics

### Completed Documentation

| Domain | File | Lines | Key Classes | Services | Highlights |
|--------|------|-------|-------------|----------|------------|
| Competition | `competition/CLAUDE.md` | 7,500+ | Gara, Inscription | 5 services | State machine, locking, waitlist |
| Matchmaking | `matchmaking/CLAUDE.md` | 5,500+ | BaseStrategy, Pairing | 2 services | 5 strategies, anti-rematch |
| Match | `match/CLAUDE.md` | 3,000+ | Match, Set, Rack | 2 services | Multi-set, auto-transitions |

**Total Documentation**: ~16,000 lines across 3 domains

---

## Usage Guide for Developers

### Finding Relevant Documentation

1. **Start with Root**: Read [models/CLAUDE.md](./CLAUDE.md) for overall architecture
2. **Domain Deep-Dive**: Navigate to specific subdirectory CLAUDE.md
3. **Cross-Reference**: Follow links to related domains as needed

### Working with Subdirectory Docs

**Quick Task?** Jump to "Quick Reference" section of relevant CLAUDE.md

**Understanding a Class?** Check "Key Classes" section with method signatures

**Building a Feature?** Study "Common Patterns" and "Examples" sections

**Debugging?** Review "Important Notes" for gotchas and edge cases

### Example Workflow

**Task**: Implement complete tournament creation with inscriptions

1. Read `models/competition/CLAUDE.md` - "Complete Competition Workflow"
2. Reference `models/matchmaking/CLAUDE.md` - "Strategy Configuration"
3. Check `models/match/CLAUDE.md` - "Single-Rack Match Workflow"
4. Review `models/classification/CLAUDE.md` (when created) - "Classification Calculation"

---

## Maintenance Notes

### Keeping Documentation Updated

**When to Update:**
- New models or services added to a domain
- Business rules change
- New methods added to existing classes
- Bug fixes reveal documentation inaccuracies

**How to Update:**
- Update the relevant subdirectory CLAUDE.md
- Keep examples runnable and tested
- Update cross-references if domain relationships change
- Maintain consistent structure across all docs

### Documentation Quality Standards

✅ **Good Documentation**:
- Immediately useful code examples
- Clear business rule explanations
- Accurate method signatures with types
- Cross-references to related domains
- Common gotchas and edge cases documented

❌ **Avoid**:
- Duplicate content from root CLAUDE.md
- Implementation details that change frequently
- Outdated examples
- Missing cross-references
- Ambiguous terminology

---

## Future Enhancements

### Planned Additions

1. **Interactive Examples**: Jupyter notebooks demonstrating workflows
2. **Diagram Integration**: UML class diagrams for complex relationships
3. **Video Walkthroughs**: Screen recordings of common workflows
4. **API Reference**: Auto-generated from docstrings
5. **Testing Guides**: How to test each domain effectively

### Community Contributions

Developers can improve documentation by:
- Adding real-world examples from production code
- Documenting discovered edge cases
- Creating cross-domain workflow guides
- Translating documentation (currently Italian/English mix)

---

## Contact & Support

For questions about this documentation:
- Create an issue in the project repository
- Ask in the development Slack/Discord channel
- Contact the development team lead

---

## Version History

- **2025-10-06**: Initial creation of 3 high-priority domain docs (Competition, Matchmaking, Match)
- **Future**: Incremental addition of remaining 15+ domains

---

## Conclusion

The subdirectory documentation provides focused, practical guidance for developers working in specific domains. Combined with the root CLAUDE.md for overall architecture, these docs create a comprehensive reference for the platform's codebase.

**Next Steps**:
1. ✅ Review the 3 completed CLAUDE.md files
2. ⏳ Create documentation for User, Notification, and Challenge domains (highest community impact)
3. ⏳ Complete Classification and Events domains (supporting systems)
4. ⏳ Document remaining infrastructure domains

**Goal**: Every model subdirectory with its own focused, practical CLAUDE.md file.
