"""Constants for competition (Gara) defaults and business rules."""

from models.status_enum import WithdrawPolicy

# Gara Creation Defaults
DEFAULT_MIN_PARTICIPANTS = 6
DEFAULT_ENTRY_FEE = 0.0
DEFAULT_ROUNDS_COUNT = 3
DEFAULT_WITHDRAW_POLICY = WithdrawPolicy.FORFEIT.value
