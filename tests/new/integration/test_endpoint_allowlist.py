"""Integration tests for ADR-028 endpoint allowlist coverage.

Two assertions:
1. Every name in ENDPOINT_ROLES must correspond to a real Flask endpoint
   (catches typos when adding entries).
2. Every name in INFRASTRUCTURE_ALLOWLIST must also correspond to a real
   endpoint.

Endpoints registered in Flask but absent from both sets are treated as
"admin-only by design" (the matrix is intentionally a starting subset);
they are reported via warning, not asserted.
"""

from __future__ import annotations

import warnings

from utils.feature_flags import ENDPOINT_ROLES, INFRASTRUCTURE_ALLOWLIST


def _flask_endpoints(app) -> set[str]:
    return {rule.endpoint for rule in app.url_map.iter_rules()}


def test_endpoint_roles_names_are_real(app):
    """Every entry in ENDPOINT_ROLES must be a registered Flask endpoint —
    typos here would silently never match in production."""
    declared = set(ENDPOINT_ROLES.keys())
    real = _flask_endpoints(app)
    bogus = declared - real
    assert not bogus, (
        f"ENDPOINT_ROLES contains names that are NOT registered Flask "
        f"endpoints (typos?): {sorted(bogus)}"
    )


def test_infrastructure_allowlist_names_are_real(app):
    """Every entry in INFRASTRUCTURE_ALLOWLIST must be a registered endpoint."""
    real = _flask_endpoints(app)
    bogus = INFRASTRUCTURE_ALLOWLIST - real
    assert not bogus, (
        f"INFRASTRUCTURE_ALLOWLIST contains names that are NOT registered "
        f"Flask endpoints: {sorted(bogus)}"
    )


def test_report_unclassified_endpoints(app):
    """Lists endpoints registered in Flask but not in any allowlist.

    Unclassified endpoints are admin-only in production by default. This
    is intentional during MVP rollout; the test only emits a warning so
    we can see the gap shrink as features are promoted.

    TODO(ADR-028 Open Items §3): when the matrix is stable (~120+ explicit
    entries) convert this warning to a hard `assert not unclassified`. At
    that point every Flask endpoint must be classified explicitly — even
    admin-only ones with `set()` — to prevent silent admin-only-by-inertia.
    """
    real = _flask_endpoints(app)
    classified = set(ENDPOINT_ROLES.keys()) | INFRASTRUCTURE_ALLOWLIST
    unclassified = real - classified
    if unclassified:
        warnings.warn(
            f"{len(unclassified)} endpoint(s) are admin-only by default "
            f"(not in ENDPOINT_ROLES nor INFRASTRUCTURE_ALLOWLIST). "
            f"Sample: {sorted(unclassified)[:10]}",
            stacklevel=2,
        )
