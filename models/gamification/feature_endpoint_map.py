"""Mappa feature gamification → endpoint primario per l'allineamento ADR-028.

La gamification sblocca features (es. ``create_match_direct``) e propone "nudge"
o "unlock" toast per invitare l'utente ad usarle. ADR-028 introduce un
allowlist di visibilità in produzione: un endpoint non listato è admin-only.
Senza questo modulo, la gamification rischia di promuovere all'utente una
feature il cui link non compare nel navbar (e che, se raggiunto via URL
diretto, ritorna 404). Vedi conversazione del 2026-05-10.

Ogni voce qui mappa un ``feature_code`` al **suo endpoint principale** —
quello cui la UI di nudge/unlock punterebbe l'utente. ``NudgeService`` e
``GamificationFrontendBridge.handle_feature_unlock_event`` consultano
``is_endpoint_visible(endpoint, user)`` prima di emettere il toast: se
l'endpoint è gated dall'allowlist e non visibile per quell'utente,
l'evento viene soppresso.

Features UI-only (``legend_status``, ``priority_invites``,
``custom_badge_display``) non vanno mappate: non hanno un endpoint reale
e non sono soggette ad ADR-028.
"""

from __future__ import annotations

FEATURE_PRIMARY_ENDPOINT: dict[str, str] = {
    # Match individuali (modulo individual_match)
    "create_match_direct": "individual_match.dashboard",
    "create_match_community": "individual_match.dashboard",
    "manage_availability": "individual_match.manage_availability",
    "match_proposals": "individual_match.proposal_list",
    "tpa_scoresheet": "individual_match.tpa_referto",
    # Tornei e gare
    "create_campionato": "admin.campionato.create_campionato",
    "create_gara": "admin.competition.create_gara_standalone",
    "tournament_creation": "admin.competition.create_gara_standalone",
    # Challenge
    "do_challenge": "challenge.challenge_catalog",
    "create_challenge": "challenge.challenge_catalog",
    "challenge_creation": "challenge.challenge_catalog",
    # Esami e ruolo esaminatore (ADR-041/042)
    "request_examiner": "roles.request_role_form",
    "take_exam": "exam.exam_catalog",
}


def feature_visible_to_user(feature_code: str, user) -> bool:
    """True se la feature è proponibile in toast/nudge a ``user``.

    Una feature mappata a un endpoint è proponibile solo se quell'endpoint
    è visibile per l'utente nell'allowlist ADR-028 (in dev/test l'allowlist
    è pass-through, quindi questa è no-op). Features non mappate restano
    sempre proponibili: si considerano "UI-only" e non gated.
    """
    endpoint = FEATURE_PRIMARY_ENDPOINT.get(feature_code)
    if endpoint is None:
        return True
    from utils.feature_flags import is_endpoint_visible

    return is_endpoint_visible(endpoint, user)
