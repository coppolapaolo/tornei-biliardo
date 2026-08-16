"""Production endpoint allowlist (ADR-028).

Deny-by-default visibility matrix mapping Flask endpoints to user roles
allowed to see them in production. In development (DEBUG_MODE=true) this
module is pass-through: every endpoint is visible regardless of role.
Admins always bypass the matrix.

Roles: "anonimo" (not logged in), "player", "director", "examiner".
Admin = bypass.

A user holds a **set** of roles, not one: the primary role ("anonimo" /
"player" / "director") comes from ``user.role``, while "examiner" is an
orthogonal grant (ADR-041) that adds to it. An endpoint is visible when the
user's role set intersects the endpoint's allowed set — a rule that matters
because an examiner who is not also a director would otherwise fall back to
"player" and lose visibility in production.

Endpoint not present in ``ENDPOINT_ROLES`` and not in
``INFRASTRUCTURE_ALLOWLIST`` is visible only to admins. To expose a new
endpoint to non-admins, add an entry here. Visibility is orthogonal to
authorization (the existing decorators @login_required, @admin_required,
etc. still apply once the endpoint is reached).
"""

from __future__ import annotations

from flask import current_app

Role = str  # "anonimo" | "player" | "director" | "examiner"


# ---------------------------------------------------------------------------
# MVP allowlist: starting set covering registration → login → inscription →
# play → profile (for player/director) and gara/campionato creation (for
# director). All non-listed endpoints are admin-only in production.
#
# TODO(ADR-028 Open Items §1): expand this matrix as features mature.
# Each unexpected 404 in prod logs from a legitimate user flow is evidence
# of a missing entry — find the real endpoint name via app.url_map and add
# it here with the right role set. Promote whole feature areas in blocks
# when judged ready. See docs/adr/ADR-028 sezione "Open Items".
# ---------------------------------------------------------------------------

ENDPOINT_ROLES: dict[str, set[Role]] = {
    # === Anonymous-only (not logged in) ===
    "auth.login": {"anonimo"},
    "auth.register": {"anonimo"},
    "auth.forgot_password": {"anonimo"},
    "auth.reset_password": {"anonimo"},
    "auth.verify_email": {"anonimo"},
    # === Public (polymorphic: every role sees, template adapts) ===
    "main.index": {"anonimo", "player", "director"},
    "main.public_garas_list": {"anonimo", "player", "director"},
    "main.public_campionatos_list": {"anonimo", "player", "director"},
    "main.gara_detail_public": {"anonimo", "player", "director"},
    # Link pubblico di iscrizione (issue #61): nasce per essere seguito da
    # chi non ha ancora un account, quindi "anonimo" non è opzionale.
    "main.gara_invite": {"anonimo", "player", "director"},
    "main.campionato_detail_public": {"anonimo", "player", "director"},
    # Informativa privacy/cookie: deve essere raggiungibile da chiunque,
    # utenti non registrati inclusi (link nel footer di base.html).
    "main.privacy_policy": {"anonimo", "player", "director"},
    "admin.competition.gara_detail": {"anonimo", "player", "director"},
    # Tabellone della gara (US-13): sola lettura, e la segue anche chi non ha
    # un account — è la schermata che si condivide durante un torneo.
    "admin.competition.gara_bracket": {"anonimo", "player", "director"},
    "i18n.set_language": {"anonimo", "player", "director"},
    # Mini-sito di aiuto: pubblico per costruzione. Chi deve ancora decidere se
    # registrarsi è il primo destinatario della guida, quindi tenerla dietro il
    # login la renderebbe inutile proprio a chi serve di più.
    "help.index": {"anonimo", "player", "director"},
    "help.section": {"anonimo", "player", "director"},
    "help.page": {"anonimo", "player", "director"},
    "help.search": {"anonimo", "player", "director"},
    # Catalogo dei micro-aiuti e API per schermata: predisposizione per
    # l'interfaccia adattiva, materiale di lavoro per chi scrive la guida.
    # `set()` esplicito = admin-only e deciso, non dimenticato: si aprono ai
    # player quando l'interfaccia adattiva li consumerà davvero.
    "help.hints_index": set(),
    "help.screen_api": set(),
    # === Logged-in (player or director) ===
    "auth.logout": {"player", "director"},
    # Il browser comunica il fuso di chi legge (ADR-043). Lo chiama il guscio da
    # ogni pagina, quindi deve essere raggiungibile da chiunque sia loggato:
    # senza, in produzione ogni utente non-admin resterebbe sul fuso dedotto al
    # login e chi si sposta non si aggiornerebbe mai.
    "auth.sync_timezone": {"player", "director"},
    "dashboard.dashboard": {"player", "director"},
    # Onboarding obbligatorio (ADR-035): reachable by ogni utente loggato.
    "onboarding.onboarding": {"player", "director"},
    # Segnale-domanda → director (ADR-036): maturity-gated, admin/director-only
    # in prod nel beta; promozione ai player col maturity-gate quando validato.
    "demand.create_signal": {"director"},
    "demand.refresh_signal": {"director"},
    # Player-side dashboard at /player/ (the "back to dashboard" target from
    # several profile/list pages — also reached by the dashboard router).
    "player.dashboard": {"player", "director"},
    # Profile
    "player.profile": {"player", "director"},
    "player.view_profile": {"player", "director"},
    "player.edit_profile": {"player", "director"},
    "player.change_password": {"player", "director"},
    "player.request_verification_email": {"player", "director"},
    # Solo i player possono richiedere la promozione a director (il form è
    # mostrato unicamente a current_user.role == 'player'). Senza questa
    # entry il POST era admin-only in prod → 404 per il player (ADR-028).
    "player.request_director": {"player"},
    "player.delete_account": {"player", "director"},
    # Notifications
    "player.notifications": {"player", "director"},
    "player.mark_notification_read": {"player", "director"},
    "player.mark_all_notifications_read": {"player", "director"},
    "player.delete_selected_notifications": {"player", "director"},
    "player.update_auto_delete": {"player", "director"},
    # Privacy controls (hide/show personal history items + privacy_settings page)
    "player.privacy_settings": {"player", "director"},
    "player.hide_match": {"player", "director"},
    "player.show_match": {"player", "director"},
    "player.hide_inscription": {"player", "director"},
    "player.show_inscription": {"player", "director"},
    "player.hide_campionato": {"player", "director"},
    "player.show_campionato": {"player", "director"},
    # Inscriptions and play (a director can also play in someone else's gara).
    # main.public_*_list lists gare; player.gara_detail shows a gara from the
    # player's perspective (with inscription/unsubscribe controls); the
    # polymorphic admin.competition.gara_detail above shows the same gara
    # with admin/director management UI.
    "player.history": {"player", "director"},
    "player.gara_detail": {"player", "director"},
    "player.inscribe_to_gara": {"player", "director"},
    "player.unsubscribe_from_gara": {"player", "director"},
    # Match scoring (player side, for matches the user is playing)
    "player.add_rack_simplified": {"player", "director"},
    "player.remove_rack_simplified": {"player", "director"},
    "player.confirm_match_result": {"player", "director"},
    "player.reject_match_result": {"player", "director"},
    "player.forfeit_match": {"player", "director"},
    "player.add_trio_rack": {"player", "director"},
    "player.remove_trio_rack": {"player", "director"},
    "player.confirm_trio_result": {"player", "director"},
    "player.forfeit_trio": {"player", "director"},
    # Playoff invitation: confirm/decline participation (bug 15)
    "player.playoff_invitation": {"player", "director"},
    "player.playoff_confirm": {"player", "director"},
    "player.playoff_decline": {"player", "director"},
    # === Director only: campionato/gara creation and management ===
    "admin.campionato.create_campionato": {"director"},
    "admin.campionato.edit_campionato": {"director"},
    "admin.campionato.campionato_detail": {"director"},
    "admin.campionato.wizard_start": {"director"},
    "admin.campionato.wizard_create": {"director"},
    "admin.campionato.wizard_step2": {"director"},
    "admin.campionato.wizard_cancel": {"director"},
    # Ciclo di vita del campionato. Erano assenti dalla matrice, quindi
    # admin-only in produzione: il director vedeva i pulsanti (i template non
    # li gating-avano) ma il POST rispondeva 404 — sintomo segnalato come
    # "Passa alla fase playoff → 404 su /admin/campionato/<id>/terminate"
    # (issue #59). L'autorizzazione vera resta @campionato_manager_required.
    "admin.campionato.terminate_campionato": {"director"},
    "admin.campionato.delete_campionato": {"director"},
    "admin.campionato.toggle_campionato_active": {"director"},
    "admin.campionato.add_director": {"director"},
    "admin.campionato.remove_director": {"director"},
    # Fase playoff: è il seguito diretto di terminate_campionato, quindi va
    # promossa nello stesso blocco (ADR-028, "promote whole feature areas").
    "admin.campionato.start_playoff": {"director"},
    "admin.campionato.create_playoff_gara": {"director"},
    "admin.campionato.update_playoff_min": {"director"},
    "admin.campionato.playoff_add_config": {"director"},
    "admin.campionato.playoff_edit_config": {"director"},
    "admin.campionato.playoff_deactivate_config": {"director"},
    "admin.campionato.playoff_add_player": {"director"},
    "admin.campionato.playoff_remove_player": {"director"},
    # Soft delete del campionato: admin-only (@admin_required). Set esplicito
    # per documentare la decisione, non per inerzia.
    "admin.campionato.soft_delete_campionato": set(),
    "admin.competition.create_gara_standalone": {"director"},
    "admin.competition.create_gara": {"director"},
    "admin.competition.edit_gara": {"director"},
    "admin.competition.update_tables_config": {"director"},
    "admin.competition.cancel_gara": {"director"},
    "admin.competition.delete_gara": {"director"},
    "admin.competition.soft_delete_gara": {"director"},
    # Director assignment
    "admin.competition.add_director": {"director"},
    "admin.competition.remove_director": {"director"},
    # Inscription management
    "admin.competition.open_inscriptions": {"director"},
    "admin.competition.close_inscriptions": {"director"},
    "admin.competition.modify_inscription_dates": {"director"},
    "admin.competition.admin_inscribe_user": {"director"},
    "admin.competition.admin_uninscribe_user": {"director"},
    # Squadre (US-2/3/8/9): l'elenco lo governa chi dirige la competizione,
    # la squadra della propria iscrizione la scrive anche il giocatore.
    "admin.competition.create_squadra": {"director"},
    "admin.competition.rename_squadra": {"director"},
    "admin.competition.merge_squadra": {"director"},
    "admin.competition.toggle_squadra": {"director"},
    "admin.competition.set_inscription_squadra": {"player", "director"},
    # Round management
    "admin.competition.start_first_round": {"director"},
    "admin.competition.start_round_generic": {"director"},
    "admin.competition.amalfi_start_round": {"director"},
    "admin.competition.cancel_first_round": {"director"},
    "admin.competition.cancel_current_round": {"director"},
    "admin.competition.cancel_round_advanced": {"director"},
    "admin.competition.bulk_reset_round_matches": {"director"},
    "admin.competition.reset_match_advanced": {"director"},
    "admin.competition.terminate_gara": {"director"},
    "admin.competition.get_round_status": {"director"},
    "admin.competition.list_round_configs": {"director"},
    "admin.competition.upsert_round_config": {"director"},
    "admin.competition.delete_round_config": {"director"},
    "admin.competition.amalfi_classification": {"director"},
    "admin.competition.get_strategy_constraints": {"director"},
    "admin.competition.check_match_modification": {"director"},
    # SSR (spareggi) — risoluzione parimerito a fine gara
    "admin.competition.start_ssr": {"director"},
    "admin.competition.cancel_ssr": {"director"},
    "admin.competition.save_ssr_group": {"director"},
    "admin.competition.save_ssr_scores": {"director"},
    # Challenge management (per gare Random con drill-based scoring)
    "admin.competition.add_challenge_to_gara": {"director"},
    "admin.competition.remove_challenge_from_gara": {"director"},
    "admin.competition.create_new_challenge": {"director"},
    "admin.competition.get_available_challenges": {"director"},
    "admin.competition.get_available_challenges_for_gara": {"director"},
    "admin.competition.get_gara_challenges": {"director"},
    "admin.competition.get_gara_challenge_classification": {"director"},
    # Match scoring (admin side, for the director managing the gara).
    # Authorization is enforced by @match_manager_required: visibility here
    # is just "director can reach it"; the decorator then verifies that the
    # specific match belongs to a gara the director manages.
    #
    # match_detail è "vista unificata" (routes/admin/match/detail.py): si
    # adatta automaticamente al ruolo (admin/director con permessi → vista
    # gestionale; player iscritto → vista semplificata). Quindi è esposta
    # anche al player. La pagina stessa decide cosa mostrare in base a
    # current_user.can_manage_competition(...) e is_player_in_match.
    "admin.match.match_detail": {"player", "director"},
    "admin.match.update_match_times": {"director"},
    "admin.match.assign_table": {"director"},
    "admin.match.add_rack_result": {"director"},
    "admin.match.remove_rack_admin": {"director"},
    "admin.match.set_match_result_direct": {"director"},
    "admin.match.validate_match": {"director"},
    "admin.match.validate_rack_admin": {"director"},
    "admin.match.reset_match": {"director"},
    "admin.match.record_challenge_attempt": {"director"},
    "admin.match.record_challenge_attempts": {"director"},
    "admin.match.start_next_set": {"director"},
    "admin.match.add_set_rack": {"director"},
    "admin.match.remove_set_rack": {"director"},
    "admin.competition.trio_add_rack": {"director"},
    "admin.competition.trio_remove_rack": {"director"},
    "admin.competition.trio_confirm": {"director"},
    "admin.competition.trio_forfeit": {"director"},
    "admin.competition.trio_reset": {"director"},
    "admin.competition.trio_set_result": {"director"},
    # User listing and user records: admin-only. Erano listati come
    # {"director"} con la motivazione "so a director can find players to enroll
    # manually", che non regge su nessuno dei due fronti: entrambe le route
    # portano @admin_required e a un direttore rispondono 403, e per iscrivere
    # qualcuno a mano il direttore usa il menu a tendina nella pagina della gara
    # (`_gara_inscriptions.html`), non l'elenco utenti. La matrice prometteva
    # una visibilità che il decoratore nega: 200 atteso, 403 reale.
    "admin.user.users_list": set(),
    "admin.user.user_detail": set(),
    # User management actions: admin-only (explicit empty set = documents the
    # decision; admin bypasses the matrix). Directors must NOT see these buttons.
    "admin.user.anonymize_user": set(),
    "admin.user.verify_user_email": set(),
    "admin.user.resend_verification": set(),
    "admin.user.merge_users": set(),
    # Gamification: director-only at the moment. Player and anonymous viewers
    # do NOT see gamification UI/toasts/notifications in production until the
    # feature stabilises. Admin bypasses the matrix as usual.
    # NB: feature_visible() in templates and the nudge/event filters in
    # models/gamification/frontend_bridge.py automatically hide buttons and
    # suppress toasts for any role not listed here — no code changes elsewhere
    # are required to flip visibility.
    "gamification.dashboard": {"director"},
    "gamification.achievements": {"director"},
    "gamification.quests": {"director"},
    "gamification.streaks": {"director"},
    "gamification.leaderboards": {"director"},
    "gamification.api_level_progress": {"director"},
    "gamification.api_user_stats": {"director"},
    "gamification.api_achievements": {"director"},
    "gamification.api_streaks": {"director"},
    # === Match individuali (casual matches) — ADR-028 ===
    # Feature sbloccata per player/director (la visibilità del menu è inoltre
    # gated dal gate gamification can_access('create_match_direct')). La
    # vera autorizzazione resta nei decoratori @RoleRequirement.
    "individual_match.dashboard": {"player", "director"},
    "individual_match.user_statistics": {"player", "director"},
    "individual_match.match_list": {"player", "director"},
    "individual_match.match_detail": {"player", "director"},
    "individual_match.proposal_list": {"player", "director"},
    "individual_match.proposal_detail": {"player", "director"},
    "individual_match.create_proposal": {"player", "director"},
    "individual_match.search_players": {"player", "director"},
    "individual_match.get_opponents": {"player", "director"},
    "individual_match.accept_proposal": {"player", "director"},
    "individual_match.cancel_proposal": {"player", "director"},
    "individual_match.decline_proposal": {"player", "director"},
    "individual_match.start_match": {"player", "director"},
    "individual_match.add_rack": {"player", "director"},
    "individual_match.remove_rack": {"player", "director"},
    "individual_match.confirm_result": {"player", "director"},
    "individual_match.reject_result": {"player", "director"},
    "individual_match.complete_match": {"player", "director"},
    "individual_match.cancel_match": {"player", "director"},
    "individual_match.update_match_times": {"player", "director"},
    "individual_match.forfeit_match": {"player", "director"},
    "individual_match.rematch": {"player", "director"},
    # Referto TPA (ADR-044). Visibile a player/director come il resto del
    # match individuale; a *sbloccarlo* e' pero' il gate gamification
    # 'tpa_scoresheet', applicato sulle route con @feature_required.
    "individual_match.tpa_referto": {"player", "director"},
    "individual_match.tpa_open": {"player", "director"},
    "individual_match.tpa_press": {"player", "director"},
    "individual_match.tpa_undo": {"player", "director"},
    "individual_match.tpa_state": {"player", "director"},
    "individual_match.tpa_close": {"player", "director"},
    # Availability: visibile a player/director. La visibilità del menu è
    # comunque gated dal gate gamification 'manage_availability' (venue
    # manager / veterano di sala). Superficie consolidata su sala
    # (UserLocationAvailability) — ADR-032/033: il vecchio modello a testo
    # libero PlayerAvailability è stato rimosso.
    "individual_match.manage_availability": {"player", "director"},
    "individual_match.set_venue_availability": {"player", "director"},
    "individual_match.remove_venue_availability": {"player", "director"},
    "individual_match.discover_players": {"player", "director"},
    "individual_match.request_availability_match": {"player", "director"},
    # Admin overview: solo admin (@admin_required).
    "individual_match.admin_overview": set(),
    # === Drill (challenge) ===
    # Il blueprint non era mai stato classificato: per deny-by-default il
    # catalogo dei drill è stato admin-only in produzione da sempre — la voce
    # di menu non compariva (base.html la gatta con feature_visible) e chi
    # arrivava per URL prendeva 404. Si accende ora che il flusso di
    # allenamento è completo (schermata /challenges/<id>/train).
    #
    # Il gate di progressione `can_access('do_challenge')` è **ortogonale** e
    # resta dov'è: questo layer dice solo se l'endpoint esiste in produzione,
    # non se l'utente ha sbloccato la funzione.
    #
    # Allenamento: lo percorre anche un director, dirigere non toglie il
    # diritto di allenarsi.
    "challenge.challenge_catalog": {"player", "director"},
    "challenge.challenge_detail": {"player", "director"},
    "challenge.training_session": {"player", "director"},
    # start_attempt/attempt_detail/complete_attempt sono il percorso della
    # gara (il drill al posto del bye), che il giocatore attraversa da solo.
    "challenge.start_attempt": {"player", "director"},
    "challenge.attempt_detail": {"player", "director"},
    "challenge.complete_attempt": {"player", "director"},
    "challenge.toggle_favorite": {"player", "director"},
    "challenge.create_x_replacement": {"player", "director"},
    "challenge.complete_x_replacement": {"player", "director"},
    # Autorialità e statistiche: portano @director_required, quindi la matrice
    # non deve prometterle a un player — vedrebbe il pulsante e si prenderebbe
    # un 403.
    "challenge.create_challenge": {"director"},
    "challenge.edit_challenge": {"director"},
    "challenge.delete_challenge": {"director"},
    "challenge.challenge_statistics": {"director"},
    # Il builder dei drill sta con l'autorialità per la stessa ragione: chi
    # disegna un drill lo fa per tutti gli altri. Il gate di progressione
    # (`use_drill_builder`) è un'altra cosa e sta sul decoratore — questa
    # matrice dice solo *chi può vedere l'endpoint in produzione*.
    "challenge.diagram_builder": {"director"},
    "challenge.edit_diagram": {"director"},
    # === Ruoli concedibili e delega (ADR-041) ===
    # APERTO IN FASE 5 insieme al catalogo esami: il ruolo di esaminatore serve
    # a somministrare esami, e ora gli esami esistono. Fino alla Fase 4 questa
    # superficie era tutta a `set()` — un "Diventa esaminatore" che non portava
    # da nessuna parte sarebbe stato peggio di nessun bottone.
    #
    # Il gate di progressione (`can_access('request_examiner')`) è **ortogonale**
    # e verificato da route e service: questo layer governa solo la visibilità.
    "roles.request_role_form": {"player", "director"},
    "roles.request_role": {"player", "director"},
    "roles.role_requests": {"examiner"},
    "roles.process_role_request": {"examiner"},
    "roles.grant_role": {"examiner"},
    # Audit della catena e revoca: solo admin **per scelta**, non per rollout
    # (US-A3) — con la propagazione a catena la revoca è l'unico punto di
    # contenimento, e resta in mano ad admin anche adesso.
    "roles.role_holders": set(),
    "roles.revoke_role": set(),
    # Auto-concessione di debug: la route fa già `abort(404)` fuori da
    # DEBUG_MODE, quindi in produzione non esiste. `set()` è ridondante per
    # sicurezza, ma dichiara la decisione invece di lasciarla implicita.
    "roles.debug_self_grant": set(),
    # === Esami (ADR-042) ===
    # Il candidato è un player; l'esaminatore è un ruolo concedibile ortogonale,
    # quindi molte voci sono `{"player", "examiner"}`: un esaminatore resta
    # player e continua a sostenere esami altrui.
    #
    # Il gate `take_exam` è ortogonale a questa matrice e vive nelle route.
    "exam.exam_catalog": {"player", "director", "examiner"},
    "exam.exam_detail": {"player", "director", "examiner"},
    # Sessioni: le vedono candidato ed esaminatore, la route filtra su chi è
    # coinvolto in quella specifica sessione.
    "exam.session_detail": {"player", "director", "examiner"},
    "exam.start_self_practice": {"player", "director", "examiner"},
    "exam.accept_session_start": {"player", "director", "examiner"},
    "exam.record_result": {"player", "director", "examiner"},
    "exam.complete_attempt": {"player", "director", "examiner"},
    "exam.abandon_attempt": {"player", "director", "examiner"},
    # Appuntamento: il candidato chiede, l'esaminatore risponde. Entrambi
    # contrattano, quindi la negoziazione è aperta a tutti e due.
    "exam.request_form": {"player", "director", "examiner"},
    "exam.create_request": {"player", "director", "examiner"},
    "exam.request_list": {"player", "director", "examiner"},
    "exam.request_detail": {"player", "director", "examiner"},
    "exam.counter_propose": {"player", "director", "examiner"},
    "exam.accept_request": {"player", "director", "examiner"},
    "exam.cancel_request": {"player", "director", "examiner"},
    # Rifiutare una richiesta lo fa solo chi è stato interpellato.
    "exam.decline_request": {"examiner"},
    # Aprire la sessione è dell'esaminatore che ha accettato l'appuntamento.
    "exam.open_certified_session": {"examiner"},
    # Composizione e gestione: solo esaminatori.
    "exam.manage_exams": {"examiner"},
    "exam.create_exam": {"examiner"},
    "exam.update_exam": {"examiner"},
    "exam.deactivate_exam": {"examiner"},
    "exam.add_challenge": {"examiner"},
    "exam.update_challenge": {"examiner"},
    "exam.remove_challenge": {"examiner"},
    "exam.reorder_challenges": {"examiner"},
    "exam.manage_examiners": {"examiner"},
    "exam.add_examiner": {"examiner"},
    "exam.remove_examiner": {"examiner"},
}


# ---------------------------------------------------------------------------
# Infrastructure: always reachable, regardless of role. Real-time polling
# endpoints for MVP features, plus Flask built-ins. Endpoints listed here
# should still rely on @login_required for actual access control where
# applicable — this set governs only allowlist visibility, not authorization.
# ---------------------------------------------------------------------------

INFRASTRUCTURE_ALLOWLIST: set[str] = {
    "static",
    "health",
    # MVP polling
    "sse.poll_gara",
    "sse.poll_match",
    "sse.poll_trio",
    "sse.poll_user",
    # Real-time sync per i match individuali (match_detail polling)
    "sse.poll_individual_match",
    # Legacy SSE streams kept for backward compat (ADR-021)
    "sse.gara_stream",
    "sse.user_stream",
    "sse.trio_stream",
    "sse.individual_match_stream",
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def _is_production() -> bool:
    """True when the allowlist must be enforced.

    Pass-through during testing (so existing tests don't need migration) and
    in development (DEBUG_MODE=true).
    """
    if current_app.config.get("TESTING", False):
        return False
    return not current_app.config.get("DEBUG_MODE", False)


#: Ruoli che NON derivano da ``user.role`` ma da una tabella di concessione
#: (ADR-041), e che quindi costano una query per essere accertati. Serve a
#: ``is_endpoint_visible`` per non pagare quel costo quando l'endpoint non li
#: ammette comunque.
GRANTABLE_ROLES: frozenset[Role] = frozenset({"examiner"})


def _primary_role(user) -> Role:
    """Ruolo primario, derivato da ``user.role``: nessun accesso al DB."""
    if not user.is_authenticated:
        return "anonimo"
    return "director" if getattr(user, "is_director", False) else "player"


def _grantable_roles(user) -> set[Role]:
    """Ruoli concedibili posseduti dall'utente. **Costa una query** per ruolo.

    Chiamare solo quando l'endpoint ne ammette almeno uno: vedi
    ``is_endpoint_visible``.
    """
    if not user.is_authenticated:
        return set()
    return {"examiner"} if getattr(user, "is_examiner", False) else set()


def _user_roles(user) -> set[Role]:
    """Role **set** completo per l'utente: primario + concedibili.

    Il primario (``user.role``) contribuisce esattamente una voce; i ruoli
    concedibili (ADR-041) si aggiungono. Restituire un insieme invece di una
    stringa è ciò che impedisce a un esaminatore che non è anche director di
    essere appiattito su ``"player"``, perdendo in produzione gli endpoint
    dichiarati per ``{"examiner"}``.

    ``is_endpoint_visible`` **non** usa questa funzione nel percorso caldo,
    perché accerterebbe i concedibili anche quando non servono; la usano i
    chiamanti che vogliono davvero l'insieme completo (introspezione, test).

    Gli admin sono gestiti dal ramo di bypass in ``is_endpoint_visible`` e non
    devono arrivare qui.
    """
    if not user.is_authenticated:
        return {"anonimo"}
    return {_primary_role(user)} | _grantable_roles(user)


def is_endpoint_visible(endpoint: str | None, user) -> bool:
    """Return True if ``endpoint`` should be reachable for ``user``.

    Order of checks:
    1. ``endpoint is None``: pass-through (Flask raises 404 itself).
    2. Pass-through in dev/test (``_is_production()`` is False).
    3. ``endpoint in INFRASTRUCTURE_ALLOWLIST``: True for every role.
    4. Admin user: True (global bypass).
    5. The user's **primary** role is in ``ENDPOINT_ROLES[endpoint]``: True.
    6. The endpoint admits a grantable role and the user holds it: True.
    7. Otherwise: False.

    Endpoints absent from ``ENDPOINT_ROLES`` (and not in infrastructure)
    are visible only to admins by default.

    Steps 5-6 are split on purpose. ``feature_visible()`` is a template global
    called once per gated link, so a single page render invokes this function
    dozens of times, and establishing a grantable role costs a query. Step 6
    therefore runs only when the primary role was not already enough **and**
    the endpoint actually admits a grantable role — today a handful of
    endpoints out of ~250, and none at all while the rollout is dark.
    """
    if endpoint is None:
        return True
    if not _is_production():
        return True
    if endpoint in INFRASTRUCTURE_ALLOWLIST:
        return True
    if user.is_authenticated and getattr(user, "is_admin", False):
        return True

    allowed = ENDPOINT_ROLES.get(endpoint, set())
    if not allowed:
        return False
    if _primary_role(user) in allowed:
        return True
    if not (allowed & GRANTABLE_ROLES):
        return False
    return bool(_grantable_roles(user) & allowed)
