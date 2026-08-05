# Architettura del Sistema

> **Generato originariamente il 2026-04-04** (BMad full-scan) — integrato il **2026-05-10** con sezione "Decisioni architetturali recenti".
> Le sezioni 1-7 descrivono pattern strutturali stabili; per le decisioni puntuali consultare gli ADR in [`docs/adr/`](../adr/) e la guida operativa in [`CLAUDE.md`](../../CLAUDE.md).

## Executive Summary

**Tornei Biliardo** è una piattaforma web Flask per l'organizzazione di tornei di biliardo americano (pool). L'architettura segue un approccio **Domain-Driven Design (DDD)** con **Service Layer Pattern**, **Strategy Pattern** per il matchmaking, ed **Event-Driven Architecture** per il disaccoppiamento tra domini.

La codebase è un **monolite** Python con server-side rendering (Jinja2), progettato per scalabilità verticale su PythonAnywhere con SQLite come database.

---

## Pattern Architetturali

### 1. Application Factory (Flask)

```
app.py → create_app(config_name)
    ├── Inizializza estensioni (db, login, babel, csrf, limiter)
    ├── Registra blueprint (routes)
    ├── Registra event handler (gamification, rating, notifiche)
    ├── Context processor (permissions, gamification, enums)
    ├── Filtri Jinja2 custom
    ├── Security headers (CSP, HSTS, X-Frame-Options)
    └── Error handlers (404, 429, 500)
```

### 2. Domain-Driven Design

Il dominio è organizzato in **25 bounded context** sotto `models/`:

```
                    ┌─────────────────────────────┐
                    │       EVENT BUS (pub/sub)    │
                    │   coordinamento cross-dominio │
                    └──────────┬──────────────────┘
                               │
          ┌────────────────────┼───────────────────────┐
          │                    │                        │
    ┌─────┴─────┐     ┌──────┴──────┐          ┌─────┴──────┐
    │ COMPETITION│     │    MATCH    │          │ MATCHMAKING │
    │  Gara      │────→│  Match      │←─────────│  Strategies │
    │  Round     │     │  Rack       │          │  Amalfi     │
    │  Inscription│    │  Set        │          │  RoundRobin │
    └─────┬─────┘     │  TrioMatch  │          │  Elimination│
          │           └──────┬──────┘          │  Random     │
          │                  │                  │  DoubleKO   │
          │                  │                  └─────────────┘
          │                  ↓
    ┌─────┴──────┐   ┌──────────────┐   ┌──────────────┐
    │CLASSIFICATION│  │   SCORING    │   │  TIEBREAKER  │
    │  Strategies │  │ ScoringService│   │  Config      │
    │  Registry   │  │ (match domain)│   │  Match       │
    └────────────┘  └──────────────┘   └──────────────┘

    ┌────────────┐   ┌──────────────┐   ┌──────────────┐
    │    USER    │   │  CAMPIONATO  │   │   CHALLENGE  │
    │  RBAC      │   │  Tournament  │   │  Attempt     │
    │  Privacy   │   │  Statistics  │   │  Favorite    │
    │  SoftDelete│   │  Homepage    │   └──────────────┘
    └────────────┘   └──────────────┘

    ┌────────────┐   ┌──────────────┐   ┌──────────────┐
    │GAMIFICATION│   │ INDIVIDUAL   │   │   LOCATION   │
    │  XP/Level  │   │   MATCH      │   │  BilliardHall│
    │  Achievement│  │  Proposal    │   │  GeoMatching │
    │  Streak    │   │  Availability│   └──────────────┘
    │  Quest     │   └──────────────┘
    │  Leaderboard│
    │  ABAC      │
    └────────────┘

    ┌────────────┐   ┌──────────────┐   ┌──────────────┐
    │   EVENTS   │   │ NOTIFICATION │   │   RATING     │
    │  EventBus  │──→│  Factory     │   │  ELO         │
    │  Domain    │   │  Templates   │   │  Handicap    │
    │  Events    │   │  Preferences │   │  Categories  │
    └────────────┘   └──────────────┘   └──────────────┘

    ┌────────────┐   ┌──────────────┐   ┌──────────────┐
    │    KPI     │   │   PLAYOFF    │   │    EXAM      │
    │  Metrics   │   │  Config      │   │  Challenge   │
    │  Milestones│   │  Qualification│  │  Attempt     │
    │  Tracking  │   │  Tournament  │   │  Result      │
    └────────────┘   └──────────────┘   └──────────────┘
```

### 3. Service Layer con @transactional

Ogni dominio espone servizi con gestione transazionale automatica:

```python
# Pattern usato in tutti i servizi
from models.transaction.manager import transactional

class GaraService:
    @transactional
    def create_gara(self, data: dict) -> Gara:
        # Business logic
        gara = Gara(**data)
        db.session.add(gara)
        return gara  # Commit automatico al termine
```

Il decoratore `@transactional`:
- Crea una transazione automatica
- Commit al successo
- Rollback su eccezione
- **NON annidare** — solo il metodo più interno deve avere il decoratore

### 4. Strategy Pattern (Matchmaking)

5 strategie di accoppiamento registrate via `StrategyFactory`:

| Strategia | Descrizione | Turni | Uso |
|-----------|-------------|-------|-----|
| **Amalfi** | Accoppiamento basato su classifica (Swiss-style) | Multipli | Gare standard |
| **Round Robin** | Tutti contro tutti | N×(N-1)/2 | Gironi piccoli |
| **Direct Elimination** | Eliminazione diretta a bracket | log₂(N) | Tornei rapidi |
| **Random Anti-Rematch** | Random con massimo matching anti-rematch (networkx) | Multipli | Gare casual |
| **Double Knockout** | Doppia eliminazione | Variabile | Tornei con seconda chance |

Ogni strategia implementa `BaseStrategy` e viene registrata al bootstrap:
```
models/matchmaking/bootstrap.py → StrategyFactory.register(...)
```

La configurazione è centralizzata in `STRATEGY_BEHAVIORS` e `STRATEGY_CONSTRAINTS` (`configuration.py`).

### 5. Event-Driven Architecture

```
DomainEvent.emit()
       ↓
   EventBus.publish()
       ↓
   ┌──────────────────────────────────────────┐
   │            Event Handlers                 │
   ├──────────────────────────────────────────┤
   │ gamification/event_handlers.py → XP, ach │
   │ gamification/notification_handlers.py     │
   │ gamification/frontend_bridge.py → toasts  │
   │ rating/event_handlers.py → ELO update    │
   │ events/notification_handlers.py → notifs  │
   │ routes/sse_bridge.py → real-time SSE     │
   └──────────────────────────────────────────┘
```

**Tipi di eventi** (da `models/events/`):
- `competition_events.py` — 37 simboli (gara, turno, iscrizione)
- `match_events.py` — 21 simboli (match, rack, risultato)
- `user_events.py` — 24 simboli (registrazione, login, profilo)
- `availability_events.py` — 13 simboli (disponibilità giocatori)
- `gamification/events.py` — 33 simboli (XP, level up, achievement)

### 6. Soft Delete (User)

Il modello `User` implementa soft delete con filtro automatico a livello di sessione SQLAlchemy:

```
User.query.all()           → esclude is_deleted=True
User.query.with_deleted()  → include tutti
user.anonymize()           → soft delete + anonimizzazione GDPR
```

Registrato globalmente in `app.py` via `register_soft_delete_filters(SASession)`.

---

## Architettura dei Dati

### Database

- **Motore**: SQLite (sia dev che produzione)
- **ORM**: SQLAlchemy con Flask-SQLAlchemy
- **Migrazioni**: Custom runner (`migrations/runner.py`) con tracking in `migrations_history`
- **File DB**: `instance/billiard_campionato.db`

### Modelli Principali (~50 classi)

| Dominio | Modelli | Tabella principale |
|---------|---------|-------------------|
| User | User, DirectorAssignment, VenueManagement, PrivacySettings | user |
| Competition | Gara, Inscription, Round | gara, inscription |
| Match | Match, Rack, MatchResult, TrioMatch, TrioRack, MatchSet | match, rack |
| Matchmaking | (strategie, no modelli propri) | — |
| Classification | Classification, RoundClassification, GaraClassification, PlayerEncounter | classification |
| Campionato | Campionato | campionato |
| Gamification | UserLevel, XPTransaction, Achievement, UserAchievement, Quest, QuestParticipation, LeaderboardEntry | user_level, xp_transaction |
| Challenge | Challenge, ChallengeAttempt, ChallengeFavorite | challenge |
| Individual Match | IndividualMatch, MatchProposal, PlayerAvailability | individual_match |
| Notification | Notification, NotificationPreference, NotificationTemplate | notification |
| Rating | PlayerRating, RatingHistory, CategoryLevel | player_rating |
| Location | BilliardHall, UserLocationAvailability | billiard_hall |
| KPI | KpiFeatureUsage, KpiDailySnapshot, KpiMilestone | kpi_feature_usage |
| Exam | Exam, ExamChallenge, ExamAttempt, ExamChallengeResult | exam |
| Playoff | PlayoffConfiguration, PlayoffQualification, PlayoffTournament | playoff_configuration |
| Tiebreaker | TiebreakerConfig, TiebreakerMatch | tiebreaker_config |

### Value Objects

- **Distance** (`models/match/distance.py`) — Race-to-N semantics immutabile
- **Score** (`models/match/score.py`) — Punteggio match immutabile

---

## Architettura delle Route

### Blueprint Registration

```python
# routes/__init__.py → register_blueprints(app)
app.register_blueprint(main_bp)           # /
app.register_blueprint(auth_bp)           # /auth
app.register_blueprint(dashboard_bp)      # /dashboard
app.register_blueprint(admin_bp)          # /admin
app.register_blueprint(player_bp)         # /player
app.register_blueprint(challenge_bp)      # /challenges
app.register_blueprint(individual_bp)     # /individual-match
app.register_blueprint(gamification_bp)   # /gamification
app.register_blueprint(rating_bp)         # /rating
app.register_blueprint(i18n_bp)           # /i18n
app.register_blueprint(sse_bp)            # /sse
```

### Struttura Ruoli

```
Utenti
├── Guest (non autenticato) → Homepage, gare pubbliche, classifiche
├── Player → Dashboard, profilo, iscrizioni, match, sfide, notifiche
├── Director → Gestione gare assegnate, turni, match, classifiche
└── Admin → Tutto + gestione utenti, campionati, KPI, gamification
```

---

## Sicurezza

| Misura | Implementazione |
|--------|----------------|
| Autenticazione | Flask-Login con sessioni server-side |
| CSRF | Flask-WTF CSRFProtect |
| Rate Limiting | Flask-Limiter |
| Password Hashing | Werkzeug security (bcrypt) |
| Security Headers | CSP, X-Frame-Options, X-Content-Type-Options, HSTS |
| Soft Delete | Anonimizzazione GDPR-compliant |
| Email Verification | Token-based verification |
| Password Reset | Token-based reset con scadenza |
| Crittografia campi | `EncryptedField` per dati sensibili |
| Error Tracking | Sentry/GlitchTip per monitoring |

---

## Gamification

Sistema completo event-driven:

```
Azione utente (match, iscrizione, etc.)
    ↓ DomainEvent
event_handlers.py → XP, achievement check, streak update
    ↓ GamificationEvent
notification_handlers.py → Notification persistente
frontend_bridge.py → Flash message (toast UI)
    ↓
Template Jinja2 → Toast animato (gamification.js)
```

Componenti:
- **XP & Livelli**: Progressione continua con configurazione per azione
- **Achievement**: 50+ achievement con categorie e difficoltà, seed automatico
- **Streak**: Serie consecutive (login, match, vittorie)
- **Quest**: Missioni con obiettivi multipli
- **Leaderboard**: Classifiche per XP, match, vittorie
- **ABAC Feature Flags**: Sblocco feature progressivo basato su livello/achievement
- **Nudge**: Motivazioni contestuali al login

---

## Pattern di Comunicazione

| Pattern | Dove | Come |
|---------|------|------|
| Sincrono | Route → Service | Chiamata diretta service method |
| Event-driven | Service → Handler | EventBus pub/sub (in-process) |
| SSE | Server → Browser | Server-Sent Events per aggiornamenti live |
| Polling | Browser → Server | polling.js per stato match |
| Email | Server → Utente | Flask-Mail SMTP |
| Flash | Service → Template | Flash message + gamification toast |

---

## Decisioni architetturali recenti (post-2026-04-04)

Tra il 2026-04-05 e il 2026-05-09 sono state introdotte quattro decisioni che modificano vincoli architetturali importanti rispetto al testo di questo documento. Vedere gli ADR per il contesto completo; qui un riepilogo per orientamento.

| ADR | Area | Effetto su questa architettura |
|-----|------|-------------------------------|
| [ADR-025](../adr/ADR-025-savepoint-integrity-error-translation.md) | Service Layer / Transactions | Aggiunge `SAVEPOINT` + `flush()` per tradurre `IntegrityError` in `ValueError` di dominio nel pattern `@transactional`. Mantiene atomicità senza propagare errori SQL ai layer superiori. |
| [ADR-026](../adr/ADR-026-reset-match-preserves-pair-semantics.md) | Match domain | Il reset di un match ora preserva la semantica della coppia (player1/player2 non vengono swappati). Cambia il contratto di `MatchService.reset_to_pending()`. |
| [ADR-027](../adr/ADR-027-round-level-configuration-enforcement.md) | Match scoring / Distance VO | Override per turno (`RoundConfiguration`) persistiti server-side. **`Distance` VO è la single source of truth per scoring/validation**: usare `match.distance_config` o `match.effective_*`, **non** `match.gara.distance`/`is_race_to`. |
| [ADR-028](../adr/ADR-028-production-endpoint-allowlist.md) | Routing / Sicurezza | Allowlist deny-by-default in produzione: `utils/feature_flags.ENDPOINT_ROLES` definisce per ogni endpoint quali ruoli (anonimo/player/director) possono raggiungerlo; admin sempre. Nuovi endpoint senza entry sono admin-only. Inventario completo in [`docs/reference/PRODUCTION_INVENTORY.md`](./PRODUCTION_INVENTORY.md). |

Per l'elenco completo degli ADR vedere [`docs/adr/README.md`](../adr/README.md).
