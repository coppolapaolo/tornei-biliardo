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
1. `python migrations/runner.py` (applica `20260605/06/07` + la nuova
   `20260606_perfectionist_honest_description`).
2. `python scripts/reconcile_achievements.py` (una volta, concede badge storici).

## Aperto / prossime fasi (NON ancora fatto)
- **Verifica manuale browser** del badge/anti-invasività (vedi MANUAL_TESTS.md)
  prima di promuovere ai player.
- **Maturity-gate (ADR-028)** — *scelta di rollout, production-visible*: endpoint
  gamification/proposte/quest/achievement NON in `ENDPOINT_ROLES` → admin/director-only
  in prod (voluto in beta). Promuovere ai player a blocchi (`utils/feature_flags.py`
  + `feature_visible` nei template) quando ogni area è validata. **Non farlo senza
  via esplicito dello stakeholder.**
- **Migrazione Availability**: ~~FATTA~~ (ADR-032). La disponibilità è unificata
  sul blueprint `individual_match` con `AvailabilityService` come unica fonte di
  verità (località + sala + discovery); le 5 route legacy e
  `routes/player/proposals.py` sono state rimosse. Restano aperte come *prodotto*:
  la deprecazione completa di `PlayerAvailability` (ancora usato da
  `ProposalService`) e l'eventuale promozione ai player (maturity gate ADR-028).
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
- **Item di design V3 mai iniziati** (fasi successive): onboarding obbligatorio +
  backfill, modello geografico per prossimità (merita ADR dedicato),
  segnale-domanda → director, leaderboard locale/contributo.

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
