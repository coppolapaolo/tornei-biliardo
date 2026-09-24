# Analisi Albero Sorgente

> **Generato originariamente il 2026-04-04** (BMad full-scan) — statistiche aggiornate il **2026-05-10**.
> Per pattern architetturali correnti consultare [`CLAUDE.md`](../../CLAUDE.md), gli ADR in [`docs/adr/`](../adr/) e [`docs/reference/ARCHITECTURE.md`](../reference/ARCHITECTURE.md).

## Statistiche Codebase (aggiornate 2026-05-10)

| Metrica | Valore | Note |
|---------|--------|------|
| File Python (esclusi venv, bmad, .codegraph) | 625 | da `find . -name "*.py"` |
| Righe Python | 189.525 | da `wc -l` aggregato |
| Righe Template HTML | 33.487 | |
| Template Jinja2 | 206 | da `find templates -name "*.html"` |
| Classi modello SQLAlchemy | ~50 | invariato |
| Classi servizio | ~50 | invariato |
| File JS | 7 | |
| File CSS | 6 | |
| Migrazioni DB | 42 | `migrations/*.py` esclusi `__init__`, `runner` |
| Test file (`tests/new/`) | 118 | |
| ADR | 23 | `docs/adr/ADR-*.md` (ADR-001..028, con buchi) |
| Lingue supportate | it, en | invariato |

---

## Struttura Directory Annotata

```
tornei-biliardo/
├── app.py                          # ★ Entry point — Flask factory create_app()
├── config.py                       # Configurazione per dev/prod/test
├── CLAUDE.md                       # Guida AI principale del progetto
├── requirements.txt                # Dipendenze produzione (13 pacchetti)
├── requirements-dev.txt            # Dipendenze sviluppo (pytest, pyright, etc.)
├── pyproject.toml                  # Config Black e coverage
├── pyrightconfig.json              # Type checking config (Python 3.9 compat)
├── babel.cfg                       # Estrazione stringhe i18n
├── messages.pot                    # Catalogo stringhe traducibili
│
├── models/                         # ★ DOMINIO — ~50.000 LOC, 25 domini
│   ├── __init__.py                 # Esporta db, User e modelli principali
│   ├── base.py                     # BaseModel, utc_now(), mail, transactional import
│   ├── status_enum.py              # GaraStatus, MatchStatus, InscriptionStatus
│   ├── exceptions.py               # Eccezioni di dominio
│   ├── fields.py                   # Campi SQLAlchemy custom (EncryptedField)
│   │
│   ├── user/                       # Utenti, ruoli, permessi, privacy
│   │   ├── models.py              # User (soft delete), DirectorAssignment, VenueManagement
│   │   ├── services.py            # UserService, UserDeletionService
│   │   ├── permission_service.py  # Gestione permessi RBAC
│   │   ├── permissions.py         # Decoratori e helper
│   │   ├── role_decorators.py     # @admin_required, @director_required, etc.
│   │   ├── privacy_models.py      # PrivacySettings (GDPR)
│   │   ├── privacy_service.py     # Gestione consenso e export dati
│   │   ├── profile_service.py     # Profilo utente
│   │   ├── stats_service.py       # Statistiche giocatore
│   │   ├── tokens.py              # Token verifica email / reset password
│   │   ├── venue_manager_service.py # Gestione sale biliardo
│   │   └── soft_delete_filter.py  # Filtro automatico soft delete
│   │
│   ├── competition/                # ★ Gare e turni — cuore del dominio
│   │   ├── models.py              # Gara (52 sym), Inscription, Round, WaitlistReason
│   │   ├── services.py            # GaraService — orchestrazione gara
│   │   ├── state_service.py       # Macchina a stati della gara
│   │   ├── round_manager.py       # Gestione turni (creazione, cancellazione)
│   │   ├── round_service.py       # RoundService
│   │   ├── round_creation.py      # Logica creazione turno
│   │   ├── round_configuration.py # Configurazione turno
│   │   ├── round_cancellation.py  # Cancellazione turno
│   │   ├── inscription_service.py # Iscrizioni e waitlist
│   │   ├── validators.py          # Validazioni gara (date, strategia, etc.)
│   │   ├── trio_service.py        # Match a 3 giocatori
│   │   ├── spareggio_service.py   # Spareggi
│   │   ├── tiebreaker_service.py  # Gestione parimerito
│   │   ├── gara_challenge.py      # Sfide per gara
│   │   ├── gara_challenge_service.py
│   │   ├── gara_bye_challenge.py  # Bye con sfida
│   │   ├── status_resolver.py     # Risoluzione stato gara
│   │   ├── withdraw_policy_service.py # Politiche ritiro
│   │   └── constants.py           # Costanti dominio
│   │
│   ├── match/                      # Match, set, rack, scoring
│   │   ├── models.py              # Match (51 sym), Rack, MatchResult, TrioMatch, TrioRack
│   │   ├── base_match.py          # BaseMatch — logica condivisa match/individual
│   │   ├── match_service.py       # MatchService
│   │   ├── scoring_service.py     # ScoringService — punteggio rack
│   │   ├── rack_service.py        # RackService — gestione rack
│   │   ├── result_service.py      # MatchResultService
│   │   ├── state_service.py       # MatchStateService
│   │   ├── validation_service.py  # Validazioni match
│   │   ├── set_models.py          # MatchSet — supporto multi-set
│   │   ├── set_lifecycle_service.py # Ciclo vita set
│   │   ├── multi_discipline_service.py # Multi-disciplina
│   │   ├── table_assignment_service.py # Assegnazione tavoli
│   │   ├── distance.py            # Value Object Distance (race-to-N)
│   │   ├── score.py               # Value Object Score
│   │   ├── trio_config.py         # Configurazione match trio
│   │   ├── trio_punteggio.py      # Trio a totali: sequenze del girone e vincitore
│   │   ├── trio_scoring_service.py # Scoring trio
│   │   └── trio_state_serializer.py
│   │
│   ├── matchmaking/                # ★ Strategie di accoppiamento
│   │   ├── service.py             # MatchmakingOrchestrator, MatchmakingService
│   │   ├── configuration.py       # MatchmakingStrategy enum, StrategyBehaviorConfig
│   │   ├── registry.py            # StrategyFactory — pattern registro
│   │   ├── bootstrap.py           # Registrazione strategie all'avvio
│   │   ├── policies.py            # Politiche (pari/dispari, bye)
│   │   ├── amalfi_challenge_bye_service.py
│   │   └── strategies/
│   │       ├── base.py            # BaseStrategy — interfaccia comune
│   │       ├── amalfi.py          # ★ Amalfi — strategia principale
│   │       ├── round_robin.py     # Round Robin
│   │       ├── direct_elimination.py # Eliminazione diretta
│   │       ├── random_anti_rematch.py # Random con anti-rematch (networkx)
│   │       └── double_knockout.py # Doppia eliminazione
│   │
│   ├── classification/             # Classifiche e punteggi
│   │   ├── models.py              # Classification, RoundClassification, GaraClassification
│   │   ├── services.py            # ClassificationService
│   │   ├── gara_classification.py # StrategyBasedClassificationService
│   │   ├── campionato_classification.py # Classifica campionato
│   │   ├── encounter_service.py   # Storico incontri
│   │   ├── score_aggregator.py    # Aggregazione punteggi
│   │   ├── tiebreaker_resolver.py # Risoluzione parimerito
│   │   ├── registry.py            # Registro sistemi classificazione
│   │   └── strategies/            # Strategie classificazione per contesto
│   │       ├── base.py
│   │       ├── gara_strategies.py
│   │       ├── round_strategies.py
│   │       ├── position_strategies.py
│   │       └── challenge_strategies.py
│   │
│   ├── campionato/                 # Campionati (raggruppamento gare)
│   │   ├── models.py              # Campionato
│   │   ├── services.py            # CampionatoService (legacy facade)
│   │   ├── tournament_service.py  # TournamentService
│   │   ├── homepage_service.py    # HomepageService
│   │   └── statistics_service.py  # TournamentStatisticsService
│   │
│   ├── gamification/               # ★ Sistema gamification completo
│   │   ├── models.py              # UserLevel, XPTransaction, Achievement, Quest, etc.
│   │   ├── level_service.py       # LevelService — XP e livelli
│   │   ├── achievement_service.py # AchievementService
│   │   ├── achievement_seeds.py   # Seed dati achievement
│   │   ├── streak_service.py      # StreakService — serie consecutive
│   │   ├── quest_service.py       # QuestService — missioni
│   │   ├── leaderboard_service.py # LeaderboardService — classifiche
│   │   ├── xp_config.py           # Configurazione XP per azione
│   │   ├── event_handlers.py      # Handler eventi → XP/achievement
│   │   ├── events.py              # Eventi gamification (33 sym)
│   │   ├── notification_handlers.py # Notifiche gamification
│   │   ├── frontend_bridge.py     # Bridge eventi → flash UI (toast)
│   │   ├── config_models.py       # Modelli configurazione
│   │   ├── config_service.py      # GamificationConfigService
│   │   ├── feature_models.py      # ABAC feature flags
│   │   ├── feature_config_service.py # Gestione feature toggle
│   │   ├── nudge_service.py       # Nudge motivazionali
│   │   ├── unlock_engine.py       # Motore sblocco feature
│   │   ├── unlock_progress_service.py
│   │   └── ui_helpers.py          # Helper UI gamification
│   │
│   ├── individual_match/           # Match casuali tra giocatori
│   │   ├── models.py              # Re-export
│   │   ├── match_models.py        # IndividualMatch (41 sym)
│   │   ├── proposal_models.py     # MatchProposal
│   │   ├── availability_models.py # PlayerAvailability
│   │   ├── services.py            # MatchProposalService, IndividualMatchService
│   │   ├── proposal_service.py    # ProposalService
│   │   ├── match_lifecycle_service.py # Ciclo vita match individuale
│   │   ├── individual_rack_service.py # Rack match individuale
│   │   ├── availability_service.py # Disponibilità giocatori
│   │   └── statistics_service.py  # Statistiche match individuali
│   │
│   ├── events/                     # ★ Sistema eventi di dominio
│   │   ├── base.py                # DomainEvent, EventBus (pub/sub)
│   │   ├── competition_events.py  # Eventi gara/turno/iscrizione (37 sym)
│   │   ├── match_events.py        # Eventi match (21 sym)
│   │   ├── user_events.py         # Eventi utente (24 sym)
│   │   ├── availability_events.py # Eventi disponibilità
│   │   └── notification_handlers.py # Handler → notifiche
│   │
│   ├── notification/               # Sistema notifiche
│   │   ├── models.py              # Notification, NotificationPreference, Template
│   │   ├── services.py            # NotificationService
│   │   ├── factory.py             # NotificationFactory
│   │   └── templates.py           # Template notifiche
│   │
│   ├── rating/                     # Sistema rating ELO
│   │   ├── models.py              # PlayerRating, RatingHistory, CategoryLevel
│   │   ├── rating_service.py      # RatingService
│   │   ├── calculation_service.py # Calcolo ELO
│   │   ├── handicap_service.py    # Handicap per livello
│   │   ├── event_handlers.py      # Rating event handlers
│   │   └── services.py            # Facade
│   │
│   ├── challenge/                  # Sfide (prove di abilità)
│   │   ├── models.py              # Challenge, ChallengeAttempt, ChallengeFavorite
│   │   └── services.py            # ChallengeService
│   │
│   ├── location/                   # Sale biliardo e geolocalizzazione
│   │   ├── models.py              # BilliardHall, UserLocationAvailability
│   │   ├── services.py            # LocationService
│   │   └── geo_service.py         # GeoMatchingService
│   │
│   ├── kpi/                        # KPI e metriche piattaforma
│   │   ├── models.py              # KpiFeatureUsage, KpiDailySnapshot, KpiMilestone
│   │   ├── services.py            # KpiService
│   │   ├── metrics_service.py     # MetricsService
│   │   ├── community_service.py   # CommunityService
│   │   ├── milestone_service.py   # MilestoneService
│   │   ├── tracker.py             # KPI tracker
│   │   ├── user_metrics.py        # Metriche utente
│   │   ├── notifications.py       # Notifiche KPI
│   │   └── enums.py               # Enum KPI
│   │
│   ├── exam/                       # Esami e prove
│   │   ├── models.py              # Exam, ExamChallenge, ExamAttempt
│   │   └── services.py            # ExamService
│   │
│   ├── playoff/                    # Sistema playoff
│   │   ├── models.py              # PlayoffConfiguration, PlayoffQualification, PlayoffTournament
│   │   └── services.py            # PlayoffService
│   │
│   ├── tiebreaker/                 # Spareggi
│   │   ├── models.py              # TiebreakerConfig, TiebreakerMatch
│   │   └── services.py            # TiebreakerService, TiebreakerConfigurationService
│   │
│   ├── dashboard/                  # Dashboard composito
│   │   ├── dashboard_service.py   # DashboardService
│   │   ├── section_builders.py    # Builder sezioni dashboard
│   │   ├── item_builders.py       # Builder item
│   │   ├── query_builders.py      # Builder query ottimizzate
│   │   ├── view_models.py         # ViewModel dashboard
│   │   └── services.py            # Facade
│   │
│   ├── shared/                     # Value object / helper cross-dominio
│   │   ├── operation_result.py    # OperationResult, OperationType
│   │   └── email_service.py       # EmailService
│   │
│   ├── transaction/                # Gestione transazioni
│   │   └── manager.py             # @transactional, DomainService
│   │
│   ├── caching/                    # Cache query
│   │   └── manager.py             # CacheManager (61 sym)
│   │
│   ├── optimization/               # Helper ottimizzazione query
│   │   └── query_optimizer.py     # optimized_query (caching) + bulk_load_relationships
│   │
│   ├── soft_delete/                # Filtro soft delete globale
│   │   └── filter.py              # register_soft_delete_filters
│   │
│   ├── shared/                     # Utilità condivise
│   │   ├── email_service.py       # EmailService (Flask-Mail)
│   │   └── utils.py               # Utility condivise
│   │
│   └── player/                     # Storico giocatore
│       └── history_service.py     # PlayerHistoryService
│
├── routes/                         # ★ ROUTE HANDLERS — 12.534 LOC
│   ├── __init__.py                # register_blueprints() — registra tutti i blueprint
│   ├── auth.py                    # Login, registrazione, password reset, verifica email
│   ├── main.py                    # Homepage, pagine pubbliche, reset DB (dev only)
│   ├── dashboard.py               # Dashboard unificato (role-based)
│   ├── challenge.py               # Catalogo sfide, creazione, tentativi
│   ├── rating.py                  # Dashboard rating, classifiche, handicap, statistiche
│   ├── i18n.py                    # Cambio lingua
│   ├── sse.py                     # Server-Sent Events endpoint
│   ├── sse_bridge.py              # Bridge eventi dominio → SSE
│   │
│   ├── admin/                     # ★ Routes amministrazione
│   │   ├── __init__.py           # Blueprint admin + sotto-blueprint
│   │   ├── campionato.py         # Wizard campionato, CRUD, gestione
│   │   ├── user.py               # Gestione utenti, ruoli, director
│   │   ├── venue.py              # Gestione sale biliardo
│   │   ├── kpi.py                # Dashboard KPI amministratore
│   │   ├── competition/          # Gestione gare
│   │   │   ├── crud.py           # CRUD gara
│   │   │   ├── detail.py         # Dettaglio gara
│   │   │   ├── inscriptions.py   # Gestione iscrizioni
│   │   │   ├── rounds.py         # Gestione turni
│   │   │   ├── matches.py        # Gestione match del turno
│   │   │   ├── challenges.py     # Sfide per gara
│   │   │   └── form_parser.py    # Parser form gara
│   │   └── match/                # Gestione match
│   │       ├── detail.py         # Dettaglio match
│   │       ├── scoring.py        # Inserimento punteggi
│   │       ├── multi_set.py      # Match multi-set
│   │       └── challenges.py     # Sfide match
│   │
│   ├── player/                    # Routes giocatore
│   │   ├── profile.py            # Profilo, modifica
│   │   ├── account.py            # Account, cambio password
│   │   ├── competitions.py       # Le mie gare, storico
│   │   ├── matches.py            # I miei match
│   │   ├── challenges.py         # Le mie sfide
│   │   ├── notifications.py      # Notifiche
│   │   ├── proposals.py          # Proposte match
│   │   ├── privacy.py            # Impostazioni privacy
│   │   ├── exports.py            # Export dati GDPR
│   │   └── geo.py                # Ricerca sale vicine
│   │
│   ├── gamification/              # Routes gamification
│   │   ├── dashboard.py          # Dashboard, achievement, quest, streak, leaderboard
│   │   ├── admin.py              # Admin gamification
│   │   ├── config.py             # Configurazione gamification
│   │   └── features.py           # Feature toggle
│   │
│   └── individual_match/          # Routes match individuali
│       ├── views.py              # Dashboard, statistiche
│       ├── matches.py            # Gestione match, scoring, rematch
│       └── proposals.py          # Proposte e accettazione
│
├── templates/                      # ★ TEMPLATE JINJA2 — 29.419 LOC, ~160 file
│   ├── base.html                  # Layout base con navbar, CSS, JS
│   ├── base_navbar_section.html   # Sezione navbar
│   ├── index.html                 # Homepage pubblica
│   ├── login.html                 # Login
│   ├── register.html              # Registrazione
│   ├── gara_detail.html           # Dettaglio gara (pubblica)
│   ├── match_detail.html          # Dettaglio match
│   ├── components/                # ~100 componenti riutilizzabili (_prefisso)
│   ├── admin/                     # Template admin (~15 file)
│   ├── dashboard/                 # Dashboard per ruolo
│   ├── player/                    # Template giocatore (~15 file)
│   ├── gamification/              # Template gamification + admin
│   ├── individual_match/          # Template match individuali
│   ├── challenge/                 # Template sfide
│   ├── public/                    # Pagine pubbliche (guest access)
│   ├── auth/                      # Password reset, forgot
│   └── errors/                    # 404, 429, 500
│
├── static/                         # Asset statici
│   ├── css/
│   │   ├── main.css               # CSS principale
│   │   ├── variables.css          # CSS custom properties
│   │   └── gamification.css       # CSS gamification
│   └── js/
│       ├── polling.js             # Polling match status
│       ├── notifications.js       # Notifiche real-time
│       ├── gamification.js        # Animazioni gamification
│       └── datetime-local.js      # Formattazione date
│
├── translations/                   # Internazionalizzazione
│   ├── it/                        # Italiano (lingua principale)
│   └── en/                        # Inglese
│
├── utils/                          # Utilità — 2.298 LOC
│   ├── __init__.py                # create_admin_if_not_exists, UserPermissions
│   ├── jinja.py                   # Filtri Jinja2 (format_distance, format_score, etc.)
│   ├── route_helpers.py           # get_or_ajax_404, ajax_success/error, handle_service_action
│   ├── permissions.py             # UserPermissions helper
│   ├── database_utils.py          # Statistiche DB
│   ├── encryption.py              # Utility crittografia
│   ├── image_paths.py             # Path immagini sfide
│   ├── rate_limiter.py            # Flask-Limiter config
│   ├── status_ui.py               # Filtri status per template
│   ├── reset_data.py              # Reset dati (dev only)
│   └── reset_manager.py           # Manager reset
│
├── migrations/                     # Migrazioni DB — 38 file, 6.368 LOC
│   ├── runner.py                  # Runner migrazioni con tracking
│   ├── 20260106_*.py → 20260209_*.py  # Migrazioni date-prefixed (2026)
│   └── add_*.py, update_*.py, populate_*.py  # Migrazioni legacy
│
├── scripts/                        # Script utilità
│   ├── auto_deploy.py             # Deploy automatico PythonAnywhere
│   ├── backup_db.py               # Backup database
│   ├── generate_schema_docs.py    # Genera docs schema DB
│   ├── recalc_elo.py              # Ricalcolo rating ELO
│   ├── send_match_reminders.py    # Reminder match via email
│   └── verify_classification_configs.py
│
├── tests/                          # Test — 39.013 LOC
│   ├── new/                       # ★ Test attivi
│   │   ├── conftest.py           # Fixture condivise (app, db_session, client)
│   │   ├── unit/                 # Test unitari (~60 file) — usa -n auto
│   │   ├── integration/          # Test integrazione (~30 file) — usa -n 4
│   │   ├── refactor/             # Test refactoring (TDD, characterization)
│   │   └── e2e/                  # Test end-to-end
│   ├── unit/                     # Alcuni test unitari extra (gamification)
│   └── legacy/                   # ⚠ Test legacy — NON mantenuti
│
├── .github/
│   └── workflows/
│       └── ci.yml                 # CI: unit tests + pyright + deploy PythonAnywhere
│
├── instance/
│   └── billiard_campionato.db     # Database SQLite (dev)
│
└── docs/                           # ★ Documentazione — 50+ file
    ├── adr/                       # 18 Architecture Decision Records
    ├── usecases/                  # 4 use case documentati
    ├── specs/                     # Specifiche tecniche
    ├── handoffs/                  # Handoff tecnici
    ├── DATABASE_SCHEMA.md         # Schema DB auto-generato
    ├── AUTHENTICATION.md          # Sistema autenticazione
    ├── GAMIFICATION_V2.md         # Gamification v2
    ├── CLASSIFICATION_SYSTEM.md   # Sistema classifiche
    ├── SPECIFICHE.md              # Specifiche complete (italiano)
    ├── UI_CONVENTIONS.md          # Convenzioni UI
    ├── INTERNATIONALIZATION.md    # i18n
    └── ...                        # Altri documenti tecnici
```

---

## Cartelle Critiche

| Directory | Scopo | LOC | Simboli |
|-----------|-------|-----|---------|
| `models/competition/` | Cuore del dominio — gare, turni, iscrizioni | ~3.500 | 52+ |
| `models/match/` | Match, rack, scoring, multi-set, trio | ~4.000 | 51+ |
| `models/matchmaking/` | Strategie accoppiamento (5 strategie) | ~2.500 | 23+ |
| `models/gamification/` | XP, livelli, achievement, quest, streak | ~4.000 | 33+ |
| `models/user/` | Utenti, RBAC, privacy GDPR, soft delete | ~3.000 | 50+ |
| `models/classification/` | Classifiche multi-strategia | ~2.500 | 31+ |
| `routes/admin/` | Amministrazione completa | ~4.000 | 28+ |
| `templates/components/` | ~100 componenti Jinja2 riutilizzabili | ~15.000 | — |

## Entry Points

| File | Funzione | Descrizione |
|------|----------|-------------|
| `app.py` | `create_app()` | Factory Flask — inizializza tutto |
| `app.py:291` | `__main__` | Avvia server di sviluppo |
| `migrations/runner.py` | `main()` | Esegue migrazioni DB |
| `scripts/auto_deploy.py` | `main()` | Deploy automatico |
| `routes/__init__.py` | `register_blueprints()` | Registra tutti i blueprint |
