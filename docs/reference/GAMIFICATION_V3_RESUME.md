# Gamification V3 — Stato & Ripresa (entry point dopo /clear)

**Data**: 2026-06-06 · **Branch**: `claude/gamification-system-review-beIB0`
**Stato**: Fase 1 e Fase 2 **completate**, tutto committato e pushato, working tree pulito.

Questo è il punto d'ingresso rapido per riprendere. Per il dettaglio:
- `docs/reference/GAMIFICATION_V3_HANDOFF.md` — piano + esito Fase 1/2/3 (con ancore).
- `docs/reference/GAMIFICATION_V3.md` — design completo.
- `docs/adr/ADR-031-gamification-gating-model.md` — decisione + audit aggiornato.
- `docs/reference/GAMIFICATION_V3_MANUAL_TESTS.md` — **checklist test manuali**
  (frontend badge/toast, cap sessione, reduced-motion, centro notifiche) non
  coperti dai test automatici.

## Cosa è FATTO (verde: pyright 0 errori; `pytest tests/new/integration -n 4` ok)

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
- **#3 dedup proposte**: consolidate su blueprint `individual_match`; **Availability
  preservato** in `routes/player/proposals.py` (solo quello resta lì).
- **Reconcile retroattivo**: `scripts/reconcile_achievements.py` (ricalcolo
  idempotente, NIENTE reset).

## Da fare al DEPLOY (operativo, non codice)
1. `python migrations/runner.py` (applica `20260605/06/07`).
2. `python scripts/reconcile_achievements.py` (una volta, concede badge storici).

## Aperto / prossime fasi (NON ancora fatto)
- **i18n**: nomi/descrizioni quest seed sono stringhe IT non in `_()`; eventuale
  `/translate` se vanno tradotte.
- **Maturity-gate (ADR-028)**: endpoint proposte/quest/achievement NON in
  `ENDPOINT_ROLES` → admin-only in prod (voluto in beta). Quando validati per i
  player, aggiungere le entry in `utils/feature_flags.py` + `feature_visible` nei
  template.
- **Availability**: ancora nel file legacy `routes/player/proposals.py`; eventuale
  migrazione futura al blueprint `individual_match`.
- **Decisioni di prodotto aperte** (annotate in ADR-031):
  - riconciliare la *celebrazione* level-up (LevelUnlock) con il *gating* reale
    (FeatureConfig) se divergono;
  - `perfectionist` conta solo drill pass/fail (i drill a punteggio non hanno
    `max_score` nel modello).
- **Anti-invasività + badge navbar vivo (§11 + §11-quater)** — ✅ **FATTO**
  (commit `a046995`, `f23e6c6`):
  - Notifiche celebrative **toast-only**: i 4 eventi (level-up, achievement,
    streak, quest) non creano più notifica persistente; `notification_handlers.py`
    è ora un seam per future notifiche *azionabili* (es. streak a rischio).
  - **Badge navbar vivo**: anello di progresso (conic-gradient da
    `progress_percentage`), pulse su XP, glow su level-up, `prefers-reduced-motion`.
  - **Scala d'intensità** (JS): micro XP → solo badge (niente toast); level-up →
    glow + l'unico toast giustificato; achievement/streak/quest → pulse + toast
    soggetto al **cap di sessione** (≤1 toast capped/sessione via `sessionStorage`,
    level-up esente).
  - Test: `test_anti_invasivita_notifications.py`, `test_navbar_badge_render.py`.
- **Item di design V3 mai iniziati** (fasi successive): onboarding obbligatorio +
  backfill, modello geografico per prossimità (merita ADR dedicato),
  segnale-domanda → director, leaderboard locale/contributo.

## Note ambiente (per non riscoprirle)
- Le dipendenze non sono preinstallate: servono `flask_sqlalchemy flask-mail
  flask-babel flask-login flask-wtf flask-limiter Pillow python-dotenv sentry-sdk
  cffi cryptography networkx pytest-xdist` (pip --user). `pyright` via `~/.local/bin`.
- **Integration tests SOLO con `-n 4`** (seriale dà falsi fallimenti di
  ordinamento, es. `test_venue_manager_notifications`). Unit: `-n auto` ok.
- **NON** lanciare `black` sull'intero albero: il repo non è black-clean,
  reformatterebbe 100+ file estranei. Black solo sui file toccati.
