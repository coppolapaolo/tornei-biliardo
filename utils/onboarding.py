"""Enforcement dell'onboarding obbligatorio (ADR-035).

Decisione *pura* (niente Flask/DB) su se una richiesta vada reindirizzata alla
pagina di onboarding, così da essere testabile in isolamento. Il gating per
ambiente (config ``ONBOARDING_ENFORCED``) è responsabilità del chiamante
(``before_request`` in ``app.py``).
"""

from __future__ import annotations

from utils.feature_flags import INFRASTRUCTURE_ALLOWLIST

# Endpoint della pagina di onboarding.
ONBOARDING_ENDPOINT = "onboarding.onboarding"

# Endpoint sempre raggiungibili anche con onboarding incompleto: l'onboarding
# stesso, il logout, il cambio lingua e l'infrastruttura (static, SSE/polling).
# Evita redirect loop e blocchi di funzioni essenziali.
ONBOARDING_EXEMPT_ENDPOINTS: frozenset[str] = frozenset(
    INFRASTRUCTURE_ALLOWLIST | {ONBOARDING_ENDPOINT, "auth.logout", "i18n.set_language"}
)


def needs_onboarding_redirect(user, endpoint: str | None) -> bool:
    """True se la richiesta corrente va reindirizzata all'onboarding.

    Non considera il gating per ambiente: assume che l'enforcement sia attivo.
    - utente non autenticato → no (deve poter raggiungere login/pubbliche)
    - admin → no (utenti interni, esenti)
    - onboarding già completato → no
    - endpoint esente (onboarding/logout/lingua/infra) → no
    - endpoint None (URL sconosciuto) → no (lascia che Flask risponda 404)
    """
    if endpoint is None:
        return False
    if endpoint in ONBOARDING_EXEMPT_ENDPOINTS:
        return False
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_admin", False):
        return False
    if getattr(user, "onboarding_completed", True):
        return False
    return True
