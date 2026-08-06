"""Gamification notification handlers — policy un-solo-canale (§11 / ADR-031).

Gli eventi *celebrativi* della gamification (XP, level-up, achievement, streak
milestone, quest completata) sono **toast-only**: vengono mostrati una sola
volta tramite il frontend bridge (`frontend_bridge.py`) e **non** generano una
notifica persistente. La notifica persistente — che resta nel centro notifiche
finché non viene letta — è riservata a ciò che è **azionabile / che puoi
perderti** (es. un nuovo invito a match, una gara aperta nella tua zona).

Razionale (GAMIFICATION_V3 §11): prima della revisione 4 eventi su 5 emettevano
*sia* toast *sia* notifica persistente, senza dedup né rate-limit — una sola
partita poteva generare ~3 toast + ~3 notifiche. Ritirare le notifiche
celebrative risolve la ridondanza alla radice; il feedback sobrio e duraturo per
XP/livello vive ora nel badge in navbar (§11-quater), mentre achievement, streak
e quest restano consultabili nelle rispettive dashboard.

Questo modulo è mantenuto come **seam**: `register_all_handlers()` è il punto in
cui agganciare in futuro le sole notifiche gamification *azionabili* (es. un
avviso "streak a rischio" prima della scadenza, che l'utente può ancora salvare
giocando). Al momento non registra nulla.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class GamificationNotificationHandlers:
    """Seam per le notifiche gamification *azionabili* (oggi vuoto).

    Le notifiche celebrative sono state ritirate (§11): gli eventi celebrativi
    sono toast-only. Le notifiche persistenti restano per gli eventi azionabili,
    che al momento non passano da qui.
    """

    @staticmethod
    def register_all_handlers() -> None:
        """Nessun handler celebrativo da registrare (policy toast-only, §11).

        Mantenuto per compatibilità con l'auto-registrazione all'import e come
        punto d'aggancio per future notifiche gamification azionabili.
        """
        logger.debug(
            "Gamification celebratory notifications are toast-only (§11); "
            "no persistent-notification handlers registered."
        )


# Auto-register on import (no-op finché non esistono notifiche azionabili).
GamificationNotificationHandlers.register_all_handlers()
