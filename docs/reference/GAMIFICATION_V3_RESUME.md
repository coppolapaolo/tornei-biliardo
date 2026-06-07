# Gamification V3 — Stato & Ripresa (entry point dopo /clear)

**Data**: 2026-06-06 · **Branch**: `claude/gamification-system-review-beIB0`
**Stato**: Fasi 1, 2, 3 **completate**, tutto committato e pushato, working tree pulito.

Questo è il punto d'ingresso rapido per riprendere. Per il dettaglio:
- `docs/reference/GAMIFICATION_V3_HANDOFF.md` — piano + esito Fase 1/2/3 (con ancore).
- `docs/reference/GAMIFICATION_V3.md` — design completo.
- `docs/adr/ADR-031-gamification-gating-model.md` — decisione + audit aggiornato.
- `docs/reference/GAMIFICATION_V3_MANUAL_TESTS.md` — **checklist test manuali**
  (frontend badge/toast, cap sessione, reduced-motion, centro notifiche) non
  coperti dai test automatici. **Da eseguire in browser prima della promozione
  ai player.**

## Cosa è FATTO (verde: pyright 0 errori; unit 940 ok; integration 319 ok `-n 4`)

**Fase 1** (commit `368afcc`, `fd372d9`, `0b92775`):
- Fix `STREAK_LONGEST` leaderboard (score + calculated_at).
- Disattivati achievement non ottenibili (poi tutti riattivati in Fase 2).
- Quest status calcolato a read-time (`Quest.effective_status`, niente cron).

**Fase 2** (commit `5e520f2`→`1a6895f`):
- **Achievement metric-driven**: `models/gamification/achievement_metrics.py`
  (`AchievementMetrics`, fonte di verità per ogni "conta N"). `_check_requirements`
  semplificato; rimosso `progress_increment`. **Tutti** gli achievement ora
  ottenibili (`UNOBTAINABLE_ACHIEVEMENT_SLUGS` vuoto). Migrazioni `20260605/06/07`.
- **`reconcile_achievements(user_id)`**: primitivo unico usato da tutti gli
  handler/trigger (match, inscription, competition, ChallengeService,
  RatingService, ProposalService).
- **#5 editor XP**: award via `GamificationConfigService.get_xp_rate()`.
- **#6 LEVEL_UNLOCKS**: rimosso duplicato morto in `xp_config`; fonte unica
  `ConfigService`/`LevelUnlock`; sblocchi-per-livello = feedback (gating = FeatureConfig).
- **Quest seed**: `models/gamification/quest_seeds.py` (settimanali ricorrenti,
  idempotenti, all'avvio).
- **#3 dedup proposte**: consolidate su blueprint `individual_match`. **Availability
  ora unificata** sul blueprint (ADR-032): `routes/player/proposals.py` rimosso,
  `AvailabilityService` unica fonte di verità (località + sala + discovery).
- **Reconcile retroattivo**: `scripts/reconcile_achievements.py` (ricalcolo
  idempotente, NIENTE reset).

**Fase 3 — Anti-invasività & badge navbar vivo (§11 + §11-quater)**
(commit `a046995` backend, `f23e6c6` frontend, `a22f6dc` doc):
- **Notifiche celebrative toast-only**: i 4 eventi (level-up, achievement, streak,
  quest) non creano più notifica persistente. `notification_handlers.py` è ora un
  **seam** documentato (`register_all_handlers` no-op) per future notifiche
  *azionabili* (es. "streak a rischio"). Risolve alla radice il doppio canale.
- **Badge navbar vivo**: `base.html` espone anello di progresso (conic-gradient da
  `progress_percentage`) + data-* (`level`/`current-xp`/`xp-next`/`progress`);
  `gamification.css` aggiunge `.gami-badge-ring`/`.badge-pulse`/`.badge-levelup`
  con `prefers-reduced-motion`.
- **Scala d'intensità** (`gamification.js`, classe `GamificationBadge`): micro XP
  → solo badge (count-up + pulse, **niente toast**); level-up → glow + l'unico
  toast giustificato; achievement/streak/quest → pulse + toast soggetto al **cap
  di sessione** (≤1 toast capped/sessione via `sessionStorage`; level-up esente).
- Test: `test_anti_invasivita_notifications.py`, `test_navbar_badge_render.py`
  (rende `base.html` in request context, robusto al leak `@transactional`).

**Item aperti chiusi (post-Fase 3)**:
- **i18n quest seed** (`8c0718a`): nomi/descrizioni tradotti a display-time
  (`_(quest.name)`/`_(quest.description)` in `quests.html`, `dashboard.html`,
  toast bridge), con `_i18n_extraction_anchor()` (mai eseguita) per l'estrazione.
  Il valore in DB resta la sorgente IT → idempotenza del seed intatta (non si può
  tradurre al seed: gira all'avvio fuori da request context). **Catalogo EN
  100% (1367/1367, 0 fuzzy)**, compilato.
- **Pulizia lint** (`e89c15b`): `frontend_bridge.py` (file toccato) ora
  black+flake8 clean (E501 di `_NUDGE_COPY` spezzate con concat implicita, valori
  byte-identici); cataloghi riallineati. **Nessun debito introdotto.**

## Da fare al DEPLOY (operativo, non codice)
1. `python migrations/runner.py` (applica `20260605/06/07`,
   `20260606_perfectionist_honest_description` e
   `20260606_drop_player_availability` — quest'ultima migra le disponibilità
   "località" testo-libero su sala dove il nome combacia e poi droppa la tabella
   `player_availability`; **perdita accettata** per le località non censite,
   vedi ADR-033). Include anche `20260606_geo_proximity` (aggiunge
   `user.home_city` + indice coord sala, ADR-034).
2. `python scripts/reconcile_achievements.py` (una volta, concede badge storici).

## Aperto / prossime fasi (NON ancora fatto)
- **Verifica manuale browser** del badge/anti-invasività prima di promuovere ai
  player. Checklist: `GAMIFICATION_V3_MANUAL_TESTS.md`; **report compilabile**
  (esiti da spuntare + firma): `GAMIFICATION_V3_MANUAL_TEST_REPORT.md`.
  È l'unico gate rimasto che i test automatici non coprono.
- **Copertura test pre-apertura** (FATTO, per area): match individuali (route
  proposte/discovery/lifecycle, `matches.py` 19%→63%, `proposals.py` 21%→66%;
  trovato+corretto bug `decline` 500 e incongruenza VALIDATED/completed), rating
  (0→suite dedicata, `rating_service` 35%→77%), catena gamification (9 skip
  sbloccate: XP/achievement end-to-end).
- **Maturity-gate (ADR-028)** — *scelta di rollout, production-visible*: endpoint
  gamification/proposte/quest/achievement NON in `ENDPOINT_ROLES` → admin/director-only
  in prod (voluto in beta). Promuovere ai player a blocchi (`utils/feature_flags.py`
  + `feature_visible` nei template) quando ogni area è validata. **Non farlo senza
  via esplicito dello stakeholder.**
- **Migrazione Availability**: ~~FATTA~~ (ADR-032 + ADR-033). La disponibilità è
  unificata sul blueprint `individual_match` con `AvailabilityService` come unica
  fonte di verità; le 5 route legacy e `routes/player/proposals.py` rimosse.
  **ADR-033 (FATTO)**: `PlayerAvailability` (località testo-libero) **rimosso del
  tutto** — disponibilità ora solo per sala (`UserLocationAvailability`/FK).
  Eligibility proposte aperte e discovery passate a sala + storico giocato;
  migrazione dati + `DROP TABLE`; UI località rimossa; admin overview → "Sale
  attive". Resta aperta solo l'eventuale promozione ai player (maturity gate
  ADR-028).
- **Decisioni di prodotto aperte** (annotate in ADR-031): ~~CHIUSE~~
  - celebrazione level-up vs gating: **reword onesto** — la toast ora dice
    "%(n)d nuove ricompense di livello!" invece di "funzioni sbloccate" (i
    LevelUnlock sono feedback/ricompense, non i gate reali FeatureConfig, con
    vocabolari disgiunti by design). Nessun cambio al gating.
  - `perfectionist`: descrizione allineata alla metrica onesta ("Supera 5 drill
    pass/fail diversi") + migrazione `20260606_perfectionist_honest_description`.
    I drill a punteggio restano esclusi (nessun max assoluto nel modello).
- **Nudge copy i18n**: ~~FATTO~~ — aggiunta `_i18n_nudge_anchor()` in
  `frontend_bridge.py` (stesso pattern delle quest seed); le 16 copy di
  `_NUDGE_COPY` sono ora estratte e tradotte in EN (catalogo 100%).
- **Modello geografico / prossimità**: ~~FATTO~~ — **ADR-034** progettato e
  implementato. GPS browser effimero + fallback `User.home_city` (centroide
  sale della città, no rete); nessuna posizione utente persistita; prossimità su
  sale + proposte aperte (NON giocatori); coord sala manuali (form admin);
  SQLite bounding-box + haversine (`utils/geo.py`, no PostGIS). Discovery
  riordina/filtra per distanza (default 20 km, cap 100, sort ON), eligibility
  ADR-033 invariata. Migrazione `20260606_geo_proximity`. 9 test integrazione +
  16 unit (`utils/geo`), i18n EN 100%.
- **Onboarding obbligatorio + backfill**: ~~FATTO~~ — **ADR-035**. Pagina
  dedicata `/onboarding` (home_city + selezione sale + interessi), enforcement
  `before_request` gated da `ONBOARDING_ENFORCED` (off nei test),
  `User.onboarding_completed`/`onboarding_interests`, migrazione
  `20260607_onboarding`, `OnboardingService`. 13 unit + 7 integrazione, EN 100%.
- **Segnale-domanda → director**: ~~FATTO~~ (core v1) — **ADR-036**. Modello
  `DemandSignal` (geo sul record, ADR-034), fronte di salita ≥6 con cooldown →
  notifica azionabile al director, consumo su creazione gara (handler
  `CompetitionCreatedEvent`) → notifica "gara vicino a te". Route maturity-gated
  `demand.create_signal`. Migrazione `20260607_demand_signal`. 7 unit + 4
  integrazione, EN 100%. Open items: re-eval promozione, segnale-admin zone
  senza director, auto-refresh scadenza, tarature.
- **Leaderboard locale/contributo**: ~~FATTO~~ (v1) — **ADR-037**.
  `CommunityLeaderboardService`: classifica locale per `home_city` (+ città
  vicine via centroide, ranking XP) + board contributo composito (drill
  altrui + gare organizzate + proposte accettate). Route `gamification.
  leaderboards` → tab Zona + Contributo; board XP globale ritirato dalla UI.
  Calcolo on-demand (no migrazione). 6 unit + 2 integrazione, EN 100%. Open
  items: leghe, tarature, performance, gare via DirectorAssignment.
- **Item di design V3 principali**: tutti avviati (§7 onboarding, §10-ter
  segnale-domanda, §11-bis leaderboard).
- **Open items per-ADR chiusi**: **ADR-036 tutti chiusi** (re-eval promozione,
  segnale-admin, ciclo scadenza + **auto-refresh** via `User.last_active_at` +
  `process_expiring_signals` + script); ADR-037 gare_organized via
  DirectorAssignment + tarature (costanti documentate) + **cache TTL**
  classifiche + **tab KPI "Performance"** (osservabilità: dice quando
  materializzare). *Restano*: ADR-037 **leghe** e **materializzazione piena**
  RIMANDATE (cache TTL già attiva); solo tarature numeriche.
- **maturity-gate ADR-028** (rollout ai player, production-visible) — da fare
  solo con via esplicito dello stakeholder.

## Note ambiente (per non riscoprirle)
- Le dipendenze non sono preinstallate: servono `flask_sqlalchemy flask-mail
  flask-babel flask-login flask-wtf flask-limiter Pillow python-dotenv sentry-sdk
  cffi cryptography networkx pytest-xdist` (pip --user). Per ispezionare i
  cataloghi i18n serve `polib` (`msgfmt` NON è installato — usare polib per le
  statistiche). `pyright` via `~/.local/bin`.
- **Integration tests SOLO con `-n 4`** (seriale dà falsi fallimenti di
  ordinamento, es. `test_venue_manager_notifications`). Unit: `-n auto` ok.
  Nota: la suite integration completa può mostrare 1-2 falsi fallimenti
  *transitori* (concorrenza SQLite, es. `test_inscription_blocked_after_gara_start`)
  che passano isolati e al rerun — non sono regressioni.
- **NON** lanciare `black` sull'intero albero: il repo non è black-clean,
  reformatterebbe 100+ file estranei. Black solo sui file toccati.
- **i18n**: il `.po` EN usa `msgstr ""` come *prima riga* di traduzioni
  multi-linea → NON contare le untranslated con `grep '^msgstr ""'` (falsa
  positivi). Usare `polib` (`e.translated()`). L'IT ha msgstr vuoti per design
  (msgid = traduzione).
