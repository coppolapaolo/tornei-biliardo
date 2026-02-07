# models/dashboard/services.py
"""Re-export shim for backward compatibility (Round 4 P3).

Original 1100 LOC split into:
- dashboard_service.py: DashboardService role facades + query builders
- section_builders.py: DashboardSectionBuilder section methods
- view_models.py: Dataclasses + query helpers
"""

from .dashboard_service import DashboardService
from .view_models import (
    CapabilityVM,
    DashboardVM,
    UnifiedDashboardItem,
    _compute_user_stats,
    _role_truthy,
)

__all__ = [
    "DashboardService",
    "CapabilityVM",
    "DashboardVM",
    "UnifiedDashboardItem",
    "_compute_user_stats",
    "_role_truthy",
]
