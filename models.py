# models.py - STEP 1: Models aggiornati
# ---------------------------------------------------------------------
#  ⚠️  User domain migrato in models/user/.  Manteniamo alias per retro-compat.
# ---------------------------------------------------------------------
from models.user.models import (
    User as _User,
    TournamentDirector as _TournamentDirector,
    DirectorRequest as _DirectorRequest,
)

# Import legacy models from modular structure
from models.legacy_models import (
    Tournament as _Tournament,
    Prova as _Prova,
    Inscription as _Inscription,
    Match as _Match,
    Rack as _Rack,
    MatchResult as _MatchResult,
    Classification as _Classification,
    Playoff as _Playoff,
    PlayerEncounter as _PlayerEncounter,
    RoundClassification as _RoundClassification,
    TrioMatch as _TrioMatch,
)

# Alias legacy → nuove classi (back-compat)
User = _User
TournamentDirector = _TournamentDirector
DirectorRequest = _DirectorRequest

# Alias legacy models
Tournament = _Tournament
Prova = _Prova
Inscription = _Inscription
Match = _Match
Rack = _Rack
MatchResult = _MatchResult
Classification = _Classification
Playoff = _Playoff
PlayerEncounter = _PlayerEncounter
RoundClassification = _RoundClassification
TrioMatch = _TrioMatch
