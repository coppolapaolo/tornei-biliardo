# Gamification V3 — Handoff per l'implementazione

**Data**: 2026-06-05 (agg. 2026-06-06) · **Branch**: `claude/gamification-system-review-beIB0`
**Stato**: Fasi 1–3 **implementate**; ADR-031 (minori), ADR-032/033 (availability),
ADR-034 (geo-prossimità) **implementati**. Vedi "Aggiornamento 2026-06-06" sotto.
Entry-point operativo gemello: `GAMIFICATION_V3_RESUME.md` (stato sintetico +
passi di deploy).

## Cos'è questo
Punto di ingresso per la fase di **implementazione** della revisione gamification.
Il design è interamente deciso e documentato — leggere come fonte di verità:
- **`docs/reference/GAMIFICATION_V3.md`** (design completo; §13 rollout a fasi, §14 tarature)
- **`docs/adr/ADR-031-gamification-gating-model.md`** (decisione + dettagli risolti)

## Decisioni chiave (riassunto, dettaglio nei doc)
- 3 layer di gating ortogonali; **un solo motore ABAC** (via legacy `LEVEL_UNLOCKS`).
- Livelli = **feedback**, non barriera. Loop base aperto dal day-1.
- **Onboarding** brevissimo/obbligatorio + backfill esistenti al primo login (`User.onboarding_completed`).
- Drill: creazione a **slot di engagement** (cap = 3 + drill ingaggiati).
- **Modello geografico per prossimità** (coordinate + raggio) → **FATTO** in
  ADR-034 (vedi Aggiornamento 2026-06-06). Nota: rispetto al design iniziale
  NON usa GeoNames offline né posizione utente persistita — GPS browser effimero
  + fallback centroide-città dalle coord sala.
- **Segnale-domanda → director** (richieste geolocalizzate, soglia ≥6 nel raggio).
- **Leaderboard** riformulato locale/contributo; loop quotidiano auto-referenziale.
- **Quest**: status calcolato dalle date + seed minimo, dietro maturity-gate.
- **Achievement**: seed **già agganciato** all'avvio (vedi correzioni sotto);
  **disattivare** (`is_active=False`) i non-ottenibili.
- **Badge navbar** vivo (anello progresso + scala di intensità toast-vs-badge).

## Verifica codice (2026-06-05) — correzioni e ancore reali
Esplorazione read-only del codice prima di pianificare la Fase 1. Correzioni
rispetto al design:
- **`seed_achievements` È GIÀ chiamato in prod** all'avvio (`app.py:282-290`, solo
  se non `TESTING`, idempotente) → il task "agganciare il seeding" **è già fatto**.
  (Il design diceva "mai chiamato in prod": ERRATO, corretto in V3 §11-ter e ADR-031.)
- **`is_hidden` non nasconde davvero**: il service ritorna tutti gli
  `is_active=True` (`achievement_service.py:511`, nessun filtro `is_hidden`); il
  template mostra solo "???" per hidden+locked → un badge non ottenibile resterebbe
  visibile come "???" per sempre. Per **toglierlo davvero** usare `is_active=False`
  (il service lo filtra già).
- **Achievement non ottenibili (10)**: 2 stub che ritornano sempre False
  (`win_streak`, `category_reached`, `achievement_seeds.py`) + 8 progress-based mai
  incrementati (`social_butterfly`, `popular_player`, `diverse_competitor`,
  `community_pillar`, `strategy_explorer`, `challenge_master`, `perfectionist`,
  `drill_addict`). Wired e funzionanti: match_wins/tournament/level/streak/win_rate.
- **Gotcha seeding idempotente**: `seed_achievements` **salta** gli esistenti →
  cambiare `is_active` nei seed **non** aggiorna le righe già in prod. Serve una
  **migrazione** `UPDATE` per i DB esistenti.
- **`STREAK_LONGEST`**: `leaderboard_service.py` `_calculate_streak_longest()`
  (~riga 201) non setta `calculated_at` **né `score`** (gli altri 4
  `_calculate_*` sì). Nessun test leaderboard esistente.
- **Quest status**: precalcolato in DB, **nessuna** derivazione a read-time;
  `update_quest_statuses()` (`quest_service.py:137`) **mai chiamato** in prod (solo
  test); read-path usa `status` (`get_user_quests`, filtro `active_only`).
  Eventi quest cablati su match/win/inscription/completion. **Nessun seed quest**.
- **Editor XP no-op (#5)**: award legge `XP_RATES` hardcoded
  (`event_handlers.py:143,156,255,333,348`); `ConfigService.get_xp_rate()` mai usato.
- **Dedup proposte (#3)**: legacy `routes/player/proposals.py`
  (`player.match_proposals`, referenziato dai componenti dashboard) vs nuovo
  `routes/individual_match/proposals.py`. ⚠️ il legacy contiene **anche il sistema
  Availability** (righe ~221-453) **non** replicato altrove → non è un delete pulito.
- **`LEVEL_UNLOCKS` (#6)**: non fa gating (lo fa FeatureConfig/UnlockEngine), ma è
  ancora letto per **notifica level-up** + **hint "prossimo unlock"**
  (`level_service.py:113,130,248,260`) → reinstradare su FeatureConfig prima di togliere.

## Fase 1 — SOLO i 3 a basso rischio (non visibile agli utenti) — ✅ COMPLETATA
**Stato (2026-06-05)**: implementata su `claude/gamification-system-review-beIB0`
(Task A `368afcc`, Task B `fd372d9`, Task C `0b92775`). Ogni task ha test dedicati;
`pyright` pulito; unit suite + gamification integration verdi. Dettaglio sotto.

Ambito deciso: i task a rischio medio/alto (#3, #5, #6 + cablaggi/seed) → **Fase 2**.

- **Task 0 — doc** (nessun codice): correzioni già applicate in V3/ADR/handoff.
- ✅ **Task A — fix `STREAK_LONGEST`** (`368afcc`): `_calculate_streak_longest()`
  ora imposta `score=streak.longest_streak` e `calculated_at=utc_now()`. Era un
  crash, non solo un campo mancante: `score` è `NOT NULL` → il refresh falliva.
  Primo test del leaderboard in `tests/new/integration/gamification/test_leaderboard_service.py`.
- ✅ **Task B — disattivare gli achievement non ottenibili** (`fd372d9`):
  costante `UNOBTAINABLE_ACHIEVEMENT_SLUGS` (**12** slug: i 2 stub mappano a 4
  badge + 8 progress-based — l'"(10)" era impreciso) + `is_active=False` nei seed
  **+ migrazione** idempotente `20260605_disable_unobtainable_achievements.py`.
  Test su seed/service + drift-guard seed↔migrazione.
- ✅ **Task C — quest status lazy** (`0b92775`): property
  `Quest.effective_status`/`is_currently_active` derivate da `start_date`/`end_date`
  con `utc_now()` (override admin `COMPLETED`/`EXPIRED` prioritari); `get_user_quests`
  con `active_only` filtra su `is_currently_active`. Test su date passate/future/
  correnti + override, senza chiamare `update_quest_statuses`.

Sequenza eseguita: 0 → A → B → C, commit atomici; chiuso con `pyright` (0 errori)
+ unit suite e gamification integration verdi (solo skip preesistenti).

### Fase 2 — ✅ COMPLETATA (tutti gli item)
- ✅ **#5 editor XP**: scelta **A** — award event-driven + milestone streak
  instradati su `GamificationConfigService.get_xp_rate()` (override DB, fallback
  `DEFAULT_XP_RATES` esteso con gara/campionato creation). Editor ora effettivo.
- ✅ **#3 dedup proposte**: consolidato sul blueprint `individual_match`;
  rimosse le route/template proposta legacy; **preservato** il sistema
  Availability (solo nel file legacy). Allowlist ADR-028 invariata.
- ✅ **#6 `LEVEL_UNLOCKS`**: il runtime già passava da ConfigService (DB
  `LevelUnlock`); rimosso il duplicato morto `xp_config.LEVEL_UNLOCKS` +
  funzioni. Fonte unica; sblocchi-per-livello = feedback (ADR-031), gating =
  FeatureConfig.
- ✅ **Achievement ottenibili** (tutti): vedi sotto — i 4 social + gli 8
  rimanenti, re-engineering metric-driven.
- ✅ **seed quest**: quest personali settimanali ricorrenti
  (`quest_seeds.seed_weekly_quests`, idempotente, no cron). Visibilità gated.
- ✅ **reconcile retroattivo**: `scripts/reconcile_achievements.py` (ricalcolo
  idempotente, nessun reset) per concedere i badge storici dopo il deploy.

### ✅ Achievement ottenibili — FATTO (re-engineering metric-driven)
Scelta utente: blocco "Achievement ottenibili" + opzione **A** (cablare). Invece
di patchare i singoli rami, è stata reingegnerizzata l'idoneità su un **modello
unico** (commit `refactor(gamification): idoneità achievement metric-driven` +
`feat(gamification): rendi ottenibili i 4 social/avversari`):

- nuovo **`AchievementMetrics`**: ogni achievement "conta N" deriva il valore
  reale dalla fonte di verità (won_matches, iscrizioni, **ledger XP** per i
  piazzamenti gara, avversari unici, proposte create/accettate). Idempotente,
  auto-correttivo, niente backfill. `current_progress` diventa solo display.
- `_check_requirements` semplificato (rimosso `current_progress`, ~145 righe
  if/elif collassate); `check_and_award` senza `progress_increment`.
- Resi ottenibili: **champion, podium_finish, tournament_dominator** (dal ledger
  XP), **diverse_competitor, community_pillar** (avversari unici, via match
  handler), **social_butterfly, popular_player** (proposte, via `proposal_service`
  con rivalutazione cross-dominio a errori isolati). Riattivati i 4 social
  (`is_active=1`) con migrazione idempotente `20260606` (netto disattivato 8).
  *Bonus*: il refactor ha sanato anche `tournament_debut`/`tournament_regular`,
  anch'essi rotti (chiave stats inesistente).
- **Gli 8 ultimi resi ottenibili** (seconda iterazione): `win_streak`
  (hot_streak/unstoppable, max vittorie consecutive da Match), `strategies_tried`
  (strategy_explorer, strategie distinte da Inscription→Gara),
  `challenges_completed` (challenge_master/drill_addict, drill completati),
  `perfect_challenges` (perfectionist, drill pass/fail superati distinti),
  `category_reached` (category_climber/elite_player, da PlayerCategory). Trigger:
  match/inscription/competition handler + ChallengeService + RatingService, tutti
  via il primitivo unico **`reconcile_achievements`**. UNOBTAINABLE ora **vuoto**;
  migrazione `20260607` riattiva gli 8 sui DB esistenti.

**Nessun achievement resta non ottenibile.** Tutto resta **director-only**
(maturity-gate ADR-028) finché non validato.

## Fase 3 — Anti-invasività & badge navbar vivo (§11 + §11-quater) — ✅ COMPLETATA
Commit `a046995` (backend), `f23e6c6` (frontend).

- **Notifiche celebrative toast-only** (`a046995`): i 4 eventi celebrativi
  (LevelUp, Achievement, StreakMilestone, QuestCompleted) **non** creano più una
  notifica persistente — risolve alla radice il doppio canale toast+notifica.
  `notification_handlers.py` diventa un seam documentato (`register_all_handlers`
  no-op) per future notifiche gamification *azionabili* (es. "streak a rischio").
  Test: `test_anti_invasivita_notifications.py` (nessuna notifica per i 4 eventi);
  aggiornato il test skipped in `test_achievement_workflow.py` al nuovo contratto.
- **Badge navbar vivo** (`f23e6c6`): `base.html` espone anello di progresso
  (conic-gradient da `progress_percentage`) + data-* (`level`/`current-xp`/
  `xp-next`/`progress`); `gamification.css` aggiunge `.gami-badge-ring`,
  `.badge-pulse`, `.badge-levelup`, con `prefers-reduced-motion`.
- **Scala d'intensità** (`gamification.js`, classe `GamificationBadge`): micro XP
  → solo badge (count-up + pulse, **niente toast**); level-up → glow del badge +
  **l'unico toast celebrativo giustificato**; achievement/streak/quest → pulse +
  toast soggetto al **cap di sessione** (≤1 toast capped/sessione via
  `sessionStorage`; level-up esente). Test: `test_navbar_badge_render.py` (rende
  `base.html` in request context, robusto al leak `@transactional` dei route).

## Aggiornamento 2026-06-06 — chiusure ADR-031 + availability + geo

Lavoro successivo alle Fasi 1–3, tutto su `claude/gamification-system-review-beIB0`.

### Chiusure decisioni di prodotto ADR-031 (3 item minori)
- **Level-up vs gating** (`3e4e241`): la toast diceva "N nuove funzioni
  sbloccate" contando i `LevelUnlock`, ma quel vocabolario è disgiunto dai gate
  reali (FeatureConfig) → reword onesto "N nuove ricompense di livello!". Nessun
  cambio al gating.
- **`perfectionist`** (`cc8dfcd`): descrizione allineata alla metrica reale
  ("Supera 5 drill pass/fail diversi") + migrazione
  `20260606_perfectionist_honest_description` (i drill a punteggio non hanno max
  assoluto nel modello → restano esclusi by design).
- **Nudge copy i18n** (`856f4b7`): le 16 `_NUDGE_COPY` in `frontend_bridge.py`
  usavano `_(variabile)` (non estraibili) → aggiunta `_i18n_nudge_anchor()`
  (pattern quest-seed); ora estratte e tradotte EN.

### Availability: ADR-032 (consolidamento) → ADR-033 (rimozione testo-libero)
- **ADR-032**: superficie disponibilità unificata sul blueprint
  `individual_match` con `AvailabilityService` come unica fonte di verità; 5 route
  legacy + `routes/player/proposals.py` rimossi.
- **ADR-033** (`6fce2f3`): rimosso del tutto `PlayerAvailability` (disponibilità
  per *località testo-libero*). Disponibilità ora **solo per sala**
  (`UserLocationAvailability`/FK). Eligibility proposte aperte e discovery →
  sala + storico-giocato. Migrazione `20260606_drop_player_availability` (mappa
  per nome→sala dove combacia, **scarta** le località non censite, poi DROP).
  UI località rimossa; admin overview → "Sale attive".

### ADR-034 — Modello geo/prossimità (`2c6d27c` design, `2ab2209` impl.)
Intervista strutturata + ADR, poi implementazione. Decisioni:
- Posizione: **GPS browser effimero** (mai persistito) + fallback
  `User.home_city` (livello città, opt-in) risolto a **centroide delle coord
  sala** di quella città (nessuna rete/geocoding).
- Prossimità su **sale** e **proposte aperte** (NON giocatori → zero coordinate
  giocatore). È overlay di **ordinamento/filtro**: l'eligibility ADR-033 resta
  invariata.
- Coord sala **manuali** (form admin); sale senza coord mostrate in sezione
  separata, mai nascoste.
- Tecnica: `utils/geo.py` (haversine + bounding-box + clamp raggio + centroide),
  SQLite, **no PostGIS**. Default raggio **20 km**, cap **100**, sort ON.
- Migrazione `20260606_geo_proximity` (`user.home_city` + indice coord sala).
- Test: 16 unit (`utils/geo`) + 9 integrazione (`test_geo_proximity.py`).

### Stato verifica (2026-06-06)
Unit **956**, integrazione **340** (skip preesistenti), `pyright` 0 errori sui
file toccati (resta 1 errore **preesistente** in `round_manager.py`, non in
scope), cataloghi i18n EN **100%**.

### Deploy (oltre a quanto già in RESUME)
`python migrations/runner.py` applica anche `20260606_perfectionist_honest_description`,
`20260606_drop_player_availability`, `20260606_geo_proximity`. Le coordinate sala
vanno inserite a mano (form admin) perché la prossimità abbia dati.

### Aperto / prossimi (design già in V3, codice non iniziato)
- **Onboarding obbligatorio + backfill** (`User.onboarding_completed`).
- **Segnale-domanda → director** (richieste geolocalizzate, soglia ≥6 nel raggio)
  — ora abilitabile sopra il modello geo di ADR-034.
- **Leaderboard locale/contributo**.
- **Maturity-gate ADR-028**: promozione ai player a blocchi (gamification +
  availability/discovery) quando validati — *non senza via dello stakeholder*.

## Convenzioni
Vedi `CLAUDE.md` (transactional, utc_now, Distance VO/ADR-027, ADR-028 endpoint
allowlist, naming italiano, EventBus isolation nei test). Verifica con `pyright`
+ `pytest tests/new/`.

## Tarature (NON bloccanti — affinare sui dati reali)
Soglie progressione/drill, raggio default (~30 km), finestre scadenza (~60 gg),
set quest seed, grafica onboarding, classifiche locali (leghe vs raggio).
