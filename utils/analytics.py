"""Analytics bridge - invio di eventi custom a Google Analytics 4.

Le azioni di dominio interessanti (registrazione completata, iscrizione a una
gara, creazione di una gara) avvengono in un POST che termina con un redirect.
Un `gtag('event')` agganciato all'`onclick` del bottone traccerebbe quindi il
*tentativo* e non l'*esito*: finirebbero nelle statistiche anche le
registrazioni fallite per email duplicata, rendendo il dato inutile proprio
dove serve (capire dove gli utenti si bloccano).

Questo modulo usa lo stesso meccanismo del bridge gamification
(`models/gamification/frontend_bridge.py`): l'evento viene messo in flash e
consumato dal template alla richiesta successiva, cioe' dopo il redirect,
quando l'azione e' andata davvero a buon fine.

ATTENZIONE - niente PII nei parametri: username, email, nome e cognome non
devono mai essere inviati a Google. Gli identificativi numerici di dominio
(gara_id, campionato_id) non sono dati personali e si possono usare.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from flask import current_app, flash, has_request_context
from flask_login import current_user

logger = logging.getLogger(__name__)

#: Categoria flash dedicata, consumata da `templates/components/_analytics_events.html`.
ANALYTICS_FLASH_CATEGORY = "analytics_event"


class AnalyticsEvent:
    """Nomi degli eventi custom inviati a GA4.

    GA4 richiede nomi in snake_case di massimo 40 caratteri. Sono centralizzati
    qui perche' un refuso non produce alcun errore: l'evento arriverebbe a
    Google sotto un nome diverso e resterebbe invisibile nei report.
    """

    USER_REGISTERED = "user_registered"
    GARA_INSCRIPTION = "gara_inscription"
    GARA_CREATED = "gara_created"


def track_event(name: str, **params: Any) -> None:
    """Accoda un evento custom da inviare a GA4 al prossimo render di pagina.

    No-op silenzioso quando GA non e' configurato (sviluppo, test), fuori da un
    contesto di richiesta, o per gli utenti admin - le visite del gestore del
    sito falserebbero le statistiche.

    Args:
        name: nome dell'evento, preferibilmente una costante di `AnalyticsEvent`.
        **params: parametri dell'evento. Solo valori non identificativi.
    """
    if not has_request_context():
        return

    if not current_app.config.get("GA_MEASUREMENT_ID"):
        return

    if current_user.is_authenticated and current_user.is_admin:
        return

    try:
        payload: Dict[str, Any] = {"name": name, "params": params}
        flash(json.dumps(payload), category=ANALYTICS_FLASH_CATEGORY)
        logger.debug("Analytics event accodato: %s", name)
    except Exception:
        # Il tracking non deve mai far fallire l'azione dell'utente. Si usa
        # logger.exception per conservare lo stacktrace: un no-op silenzioso
        # senza traccia sarebbe indiagnosticabile (payload non serializzabile,
        # sessione piena, ...).
        logger.exception("Errore nell'accodare l'evento analytics %s", name)
