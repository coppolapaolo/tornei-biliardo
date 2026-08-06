# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

### Essential Commands
```bash
# Start development server
python app.py

# Run all tests (use -n 4 for integration to avoid SQLite deadlocks)
pytest tests/new/ -n 4

# Run specific test types
pytest tests/new/unit/ -n auto          # Unit tests: -n auto OK
pytest tests/new/integration/ -n 4      # Integration: MUST use -n 4 (SQLite concurrency)

# Run single test file
pytest tests/new/unit/test_specific.py -v -n auto

# Debug single test (no parallel, with output)
pytest tests/new/unit/test_file.py::test_name -v -s

# Frontend headless tests (jsdom, Node — gamification badge/anti-invasività)
cd tests/frontend && npm install && npm test   # run after editing static/js/gamification.js

# Type check (MANDATORY before commits)
pyright

# Format code
black . && flake8

# Internationalization (i18n)
pybabel extract -F babel.cfg -o messages.pot .  # Extract new strings
pybabel update -i messages.pot -d translations  # Update catalogs
pybabel compile -d translations                 # Compile translations

# Documentation
python scripts/generate_schema_docs.py          # Regenerate DB schema docs
```

### Key Files & Locations
- **Application Entry**: `app.py` - Flask factory pattern
- **Configuration**: `config.py` - Environment-based config
- **Database**: `instance/billiard_campionato.db` (SQLite dev)
- **Domain Documentation**: `models/CLAUDE.md`, `routes/CLAUDE.md`, `tests/CLAUDE.md`
- **Template Documentation**: `templates/CLAUDE.md` - Jinja2/JS integration patterns

### CI/CD & Deployment

**Production URL**: https://www.torneibiliardo.it

```bash
# Run migrations (with tracking)
python migrations/runner.py              # Run pending migrations
python migrations/runner.py --status     # Show migration status
python migrations/runner.py --mark-all-applied  # Init existing DB

# Deploy to PythonAnywhere (manual)
cd /home/paolocoppola/mysite
git pull origin main
# ATTENZIONE: migrations SOLO con web app Disabled (tab Web)!
python migrations/runner.py
# Web app auto-reloads on push via GitHub Actions
```

**GitHub Actions** (`.github/workflows/ci.yml`):
- Runs unit tests and pyright on every push/PR
- Reloads PythonAnywhere web app on push to main
- Git pull and migrations must be run manually or via scheduled task

**⚠️ Branch protection su `main` (dal 2026-06)**: `main` è protetto e
`enforce_admins=true` — **niente push diretti su `main`, neanche da admin**.
Ogni modifica passa da una PR e il merge è bloccato finché lo status check
`test-and-typecheck` (unit test + pyright) non è verde. Workflow obbligatorio:

```bash
git checkout -b claude/descrizione   # branch di lavoro
# ... commit ...
git push -u origin claude/descrizione
gh pr create                          # apri la PR
# attendi che la CI sia verde, poi merge → il push su main fa scattare il deploy
```

Un `git push origin main` diretto viene rifiutato (`protected branch hook
declined`). L'auto-deploy (reload PythonAnywhere) parte normalmente al merge,
ma solo su codice che ha passato la CI. Il gate è solo `test-and-typecheck`:
gli altri job (`check-migrations`, `deploy`, `skip-deploy-notification`) girano
solo sull'evento `push` a `main`, **non** sulle PR, quindi non vanno mai
richiesti come status check (resterebbero in pending all'infinito). Per un
hotfix urgente con CI rotta serve togliere temporaneamente la protezione
(`gh api -X DELETE repos/coppolapaolo/tornei-biliardo/branches/main/protection`,
poi riapplicarla).

**PythonAnywhere Scheduled Tasks** (daily):
- `scripts/auto_deploy.py`: git pull, pip install, migrations e reload. Le
  migrations girano SOLO se pendenti e con la web app disabilitata via API
  (Disable → migrate → Enable; token da `$API_TOKEN`). Senza token si ferma
  con istruzioni manuali. **Legge le env di produzione dal file WSGI**
  (`read_wsgi_env`, parsing AST senza eseguirlo): il task è un processo
  separato e non le eredita, e senza `ENCRYPTION_KEY` una migration sui PII
  non solleva — fallisce la decifratura, il backfill resta vuoto e la
  migration risulta comunque applicata (incidente 2026-06-25, vedi sotto). Se
  ci sono migrations pendenti e la chiave non è ricavabile, il deploy si ferma.
- `scripts/backup_db.py`: backup giornaliero del DB (rotazione 7 copie in
  `backups/`).
- `scripts/daily_jobs.py`: **punto d'ingresso unico dei lavori di dominio
  giornalieri** (oggi: ciclo di vita dei segnali-domanda). Gli slot scheduled
  task su PythonAnywhere sono limitati, quindi un nuovo job quotidiano si
  aggiunge alla mappa `JOBS` dello script — **non** come nuovo task, e **non**
  dentro `auto_deploy`/`backup_db` (il primo esce prima del tempo quando non ci
  sono modifiche, il secondo non deve dipendere dal codice applicativo). Ogni
  job è isolato; exit code ≠ 0 se almeno uno fallisce. `python
  scripts/daily_jobs.py <nome>` per lanciarne uno solo.

**Env di produzione negli script da console/task**: console e scheduled task
sono processi separati e **non ereditano** le variabili dal file WSGI, quindi
`create_app("production")` fallirebbe subito su `SECRET_KEY`. Gli script che
avviano l'app chiamano `bootstrap_or_exit()` da `scripts/prod_env.py`, che le
legge dal WSGI (riusa `read_wsgi_env` di `auto_deploy`, parsing AST senza
eseguirlo) e, se manca qualcosa, esce dicendo cosa e da dove dovrebbe arrivare.
Un valore passato a mano sulla riga di comando resta prioritario. Uno script
nuovo che fa `create_app` va agganciato lì — chiedendo anche `ENCRYPTION_KEY`
se tocca i PII, altrimenti la decifratura degrada in silenzio sulla chiave di
sviluppo (incidente 2026-06-25). `auto_deploy.py` resta autonomo di proposito:
è il punto d'ingresso del deploy e non importa nulla dal progetto.

> ⚠️ `scripts/send_match_reminders.py` (ogni 15 min) **non risulta registrato**:
> compare solo come TODO in un handoff archiviato di gennaio. Se è così i
> promemoria dei match non partono. Cadenza diversa dal giornaliero, quindi
> serve uno slot suo — da verificare nel pannello PythonAnywhere.

**⚠️ SQLite su PythonAnywhere (incidente 2026-06-10)**: lo storage è NFS con
lock inaffidabili — due processi che SCRIVONO insieme (console + web app)
possono corrompere il DB ("database disk image is malformed"). Regola: ogni
script/comando console che scrive sul DB di produzione va eseguito con la
web app su **Disabled** (riabilitare subito dopo).

**Variabili d'ambiente richieste in produzione** (nel WSGI file
`/var/www/www_torneibiliardo_it_wsgi.py`): `FLASK_ENV=production` e
`ENCRYPTION_KEY` (la chiave cifra i PII — rotazione con
`scripts/rotate_encryption_key.py`, procedura nel docstring). Il fail-fast
scatta al **primo uso** della cifratura, non all'avvio: `_resolve_key_string`
è invocata da `EncryptionManager._initialize_cipher`, che parte all'import di
`utils.encryption` (singleton eager). Gli script da console che toccano PII
vanno lanciati con `ENCRYPTION_KEY='...' python scripts/...` (la console non
eredita le env del WSGI; `auto_deploy.py` se le legge da solo, vedi sopra).

**⚠️ Migration sui PII senza chiave (incidente 2026-06-25)**: il fail-fast
richiede `FLASK_ENV=production`. In console/task quella variabile non c'è,
quindi la mancanza di `ENCRYPTION_KEY` degrada in silenzio sulla chiave di
sviluppo. `20260625_add_email_hash` è girata così dallo scheduled task: la
decifratura falliva su ogni riga, il guard interno saltava (giustamente, per
non scrivere hash sbagliati) e il risultato è stato **0 hash su 37 utenti**,
con la migration marcata come applicata e quindi mai ritentata. Effetto:
recupero password muto per cinque settimane — `request_password_reset`
ritorna `True` anche a utente non trovato, per non esporre l'enumerazione
degli account, quindi nessun errore da nessuna parte. Diagnosi:
`SELECT COUNT(*) FROM user WHERE email IS NOT NULL AND email != '' AND
(email_hash IS NULL OR email_hash = '') AND deleted_at IS NULL`.

**Monitoring (GlitchTip)**: DSN in `GLITCHTIP_DSN` (WSGI). In `app.py`
`traces_sample_rate` deve restare **0.0**: le transaction di performance
contano nella quota GlitchTip Free (1000 eventi/mese) — con 0.1 la quota si
è esaurita in un giorno e il throttling scartava anche gli error event
(sintomo: retry `SSLEOFError ... /api/<id>/envelope/` nell'error log PA,
2026-06-10). Nota: ogni reload della web app ha una finestra di ~30s di
`502-backend` mentre l'app riparte — è normale, non un crash.

---

## Things to Remember

Before writing any code:

1. **State how you will verify** this change works (test, bash command, browser check, etc.)
2. **Write the test or verification step first**
3. **Then implement the code**
4. **Run verification and iterate** until it passes

---

## Critical Conventions

### 1. Timezone Handling
The application uses **UTC-based datetime convention** throughout via the `utc_now()` utility.

```python
# ✅ CORRECT
from models.base import utc_now
now = utc_now()

# ❌ WRONG
from datetime import datetime
now = datetime.now()       # Local time, not UTC
now = datetime.utcnow()   # Deprecated in Python 3.12+
```

`utc_now()` uses `datetime.now(timezone.utc).replace(tzinfo=None)` internally — non-deprecated API, but returns naive datetimes compatible with SQLite.

- **Column defaults**: Use `default=utc_now` (no parens — callable reference)
- **Frontend**: Use `|datetime_local` filter to display UTC → Italian time (UTC+2)

### 2. "Race to N" Terminology (NOT "Best of N")
The application uses **"Race to N"** terminology (Italian: "Al N").

- **"Race to 5"** = First player to WIN 5 racks wins
- **Maximum racks** = (2 × distance) - 1 = 9 racks for race to 5
- **Database field**: `distance` = winning score threshold

```python
# ✅ CORRECT
gara.distance = 5  # Race to 5 (first to 5 racks wins)
gara.best_of = False  # Always False for Race to N

# ❌ WRONG
gara.distance = 9  # This means "race to 9", not "best of 9"
```

### 3. Transaction Management
All service methods that modify database state MUST use `@transactional`:

```python
from models.transaction.manager import transactional

class GaraService:
    @transactional
    def create_gara(self, campionato_id: int, data: dict) -> Gara:
        gara = Gara(campionato_id=campionato_id, nome=data['nome'])
        db.session.add(gara)
        return gara  # Commit happens automatically
```

### 4. Soft Delete (User Model)
User model has soft delete with automatic session-level filtering.

```python
# Automatic filtering - excludes is_deleted=True
users = User.query.all()

# Include deleted records
all_users = User.query.with_deleted().all()

# ✅ CORRECT - Soft delete preserves relationships
user.anonymize()

# ❌ WRONG - Never hard delete User records
db.session.delete(user)  # Breaks foreign key relationships
```

### 5. Enum Comparisons
```python
# ✅ CORRECT - Use .value
if gara.status == GaraStatus.PLAYING.value:

# ❌ WRONG - Compares to enum object
if gara.status == GaraStatus.PLAYING:
```

### 6. Value Objects (Distance & Score)
Use immutable value objects for distance and score business logic:

```python
from models.match.distance import Distance

# Via factory method
distance = Distance.from_gara(gara)
winning_racks = distance.get_winning_racks()

# Via model property
distance_cfg = match.distance_config
```

**ADR-027 — `Distance` VO is the single source of truth for match scoring.**

In ogni path di scoring/validation/aggregation usa `match.distance_config` o
le property `Match.effective_*`. NON leggere `match.gara.distance` o
`match.gara.is_race_to` direttamente — gli override per turno
(`RoundConfiguration`) verrebbero silenziosamente persi.

```python
# ✅ CORRECT - rispetta override per turno
distance = match.distance_config
if distance.is_race_to_racks:
    winning = distance.get_winning_racks()
else:
    total = match.player1_score + match.player2_score
    if total == distance.racks: ...

# ❌ WRONG - bypassa RoundConfiguration
if match.gara.is_race_to:  # override per turno persi!
    winning = match.gara.distance_config.get_winning_racks()
```

L'unico posto autorizzato a leggere `self.gara.distance`/`is_race_to` sono i
fallback dentro `Match.effective_*` (per restituire il default della gara
quando non c'è override). Vedi `docs/adr/ADR-027-round-level-configuration-enforcement.md`.

### 7-8. Stringhe tradotte e attributi `onclick` nei template (CRITICAL)

`|tojson` è obbligatorio per ogni stringa tradotta incorporata in JavaScript:
gli apostrofi italiani (`l'avvio`, `l'errore`) altrimenti rompono la stringa JS
e bloccano *tutto* il JavaScript della pagina. Gli attributi `onclick` che lo
usano vogliono apici singoli, e i placeholder `%(nome)s` non vanno usati in
stringhe interpolate da JavaScript.

Regole complete con esempi corretti/sbagliati: **`templates/CLAUDE.md`**, che si
carica da solo quando si lavora sotto `templates/`.

### 9. Sequential Date Validation for Campionato Gare
Gare within a campionato must have dates in chronological order by `number`:

```python
# ✅ CORRECT - Gara 2 after Gara 1
gara1.date = date(2026, 1, 15)  # number=1
gara2.date = date(2026, 1, 22)  # number=2

# ❌ WRONG - Gara 2 before Gara 1 raises ValueError
gara1.date = date(2026, 1, 22)  # number=1
gara2.date = date(2026, 1, 15)  # number=2 → raises ValueError

# Same-day gare are allowed if time is sequential
gara1.date, gara1.time = date(2026, 1, 15), time(14, 0)  # number=1
gara2.date, gara2.time = date(2026, 1, 15), time(18, 0)  # number=2 → OK
```

**Rules**:
- Gara N must have date/time `>=` the gara with highest number `< N`
- Gara N must have date/time `<=` the gara with lowest number `> N`
- Standalone gare (no campionato) have no sequential validation

See `docs/adr/ADR-016-gara-sequential-date-validation.md` for details.

### 10. Migration Naming Convention
New migrations use date-prefixed naming:

```bash
# Create new migration file
touch migrations/20260125_description.py
```

Migration files must:
- Define `migration_name` variable for tracking
- Be idempotent (safe to run multiple times)
- Use `op.execute()` for raw SQL on SQLite

### 11. Email Service (Flask-Mail)
Use `EmailService` for all email sending:

```python
from models.shared.email_service import EmailService

email_service = EmailService()
email_service.send_email(
    to=user.email,
    subject=_("Subject"),
    template="email/template.html",
    **template_context
)
```

Configuration via environment: `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`.
See `docs/reference/AUTHENTICATION.md` for full setup.

### 12. Gamification Frontend Bridge
Domain events trigger toast notifications via the frontend bridge:

```python
from models.gamification.frontend_bridge import flash_gamification_event, GamificationEventType

flash_gamification_event(GamificationEventType.XP, {
    "amount": 50,
    "title": _("XP Guadagnati!"),
    "subtitle": _("Continua così!")
})
```

See `docs/reference/GAMIFICATION_V2.md` for event types and animation system.

### 13. Production Endpoint Allowlist (ADR-028)
Endpoint visibility in production is gated by an explicit role matrix in `utils/feature_flags.py`. **Endpoint not listed = admin-only in production.** In development (`DEBUG_MODE=true`) and tests (`TESTING=true`) the middleware is pass-through.

**ADR-028 — When you add a new route, decide its visibility explicitly.**

```python
# utils/feature_flags.py
ENDPOINT_ROLES = {
    "main.public_garas_list":     {"anonimo", "player", "director"},  # public
    "dashboard.dashboard":        {"player", "director"},              # logged-in
    "player.inscribe_to_gara":    {"player"},                          # player only
    "admin.competition.start_first_round": {"director"},               # director only
    # NOT in matrix → admin-only in prod by default
}
```

Steps when adding a route:

1. **Decide who should see it** in production. Roles: `anonimo`, `player`, `director`. Admin always sees everything.
2. **Add an entry** to `ENDPOINT_ROLES` with the role set, OR leave it out if it should stay admin-only for now.
3. **If the route appears in a menu/link**, wrap with `{% if feature_visible('endpoint.name') %}…{% endif %}` (vedi `templates/base.html`).
4. **Verify**: the test `tests/new/integration/test_endpoint_allowlist.py::test_endpoint_roles_names_are_real` catches typos in endpoint names.

A 404 reported by a real user that should NOT be 404 is evidence of a missing matrix entry. Find the real endpoint name (`app.url_map`) and add it.

See `docs/adr/ADR-028-production-endpoint-allowlist.md` (incl. **Open Items**) for full design and follow-up work.

### 14. Naming Conventions
I termini di dominio (`campionato`, `gara`, `iscrizione`, `partita`, `turno`)
sono in **italiano** con **plurale italiano**. Mai anglicizzare con `-s`.

```python
# ✅ CORRECT
campionati = Campionato.query.all()
def gare_attive(): ...
template = "campionati_list.html"

# ❌ WRONG (anti-pattern: italian root + english -s)
campionatos = ...
def garas_attive(): ...
template = "campionatos_list.html"
```

I suffissi tecnici/pattern restano in inglese (`Service`, `Builder`,
`Strategy`, ecc.). Le classi `Service` usano il singolare del modello
(es. `CampionatoService`, non `CampionatiService`).

Vedi `docs/reference/NAMING_CONVENTIONS.md` per regole complete (URL,
DB columns, test, eccezioni storiche come `Match`).

---

## Database

- **Development**: SQLite (`instance/billiard_campionato.db`)
- **Production**: SQLite su PythonAnywhere
  (`/home/paolocoppola/mysite/instance/billiard_campionato.db`)

**Matchmaking**: sia la strategia Random Anti-Rematch sia Amalfi (caso pari, vedi
ADR-029) usano `networkx` per il maximum (cardinality / weighted) matching sul
grafo anti-rematch. Non reimplementare algoritmi su grafi — usa `nx`, è già in
`requirements.txt`.

---

## Development Guidelines

### Type Safety (MANDATORY)
- Run `pyright` before every commit - maintain 0 errors
- Use proper type hints for all functions
- Pyright config (`pyrightconfig.json`) disables `reportCallIssue` due to SQLAlchemy mixin inheritance issues (pyright doesn't recognize that `db.Model` generates constructors accepting column names as kwargs)

### Code Quality Checklist
```bash
# Before every commit:
black . && flake8
pyright
pytest tests/new/unit/ -n auto && pytest tests/new/integration/ -n 4
```

### Testing Requirements
- All new features MUST have tests in `tests/new/`
- Test isolation: use `db_session.get()` not `refresh()`
- Legacy tests (`tests/legacy/`) are not maintained
- Unit tests: `-n auto` OK; Integration tests: `-n 4` (SQLite concurrency)
- **EventBus isolation**: Never clear `EventBus._handlers = {}` in tests - preserve and restore:
  ```python
  @pytest.fixture(autouse=True)
  def preserve_handlers():
      original = {k: list(v) for k, v in EventBus._handlers.items()}
      yield
      EventBus._handlers = original
  ```

---

## Common Mistakes to Avoid

| Mistake | Correct Approach |
|---------|------------------|
| `datetime.now()` or `datetime.utcnow()` | `utc_now()` from `models.base` |
| `gara.distance = 9` (thinking best of 9) | `gara.distance = 5` (race to 5) |
| `db.session.delete(user)` | `user.anonymize()` |
| `gara.status == GaraStatus.PLAYING` | `gara.status == GaraStatus.PLAYING.value` |
| `pytest tests/new/integration/ -n auto` | `pytest tests/new/integration/ -n 4` (SQLite deadlock) |
| Manual `db.session.commit()` | Use `@transactional` decorator |
| `alert('{{ _("l'errore") }}')` in JS | `alert({{ _("l'errore")\|tojson }})` |
| `{{ _("%(count)s items")\|tojson }}` + JS replace | Use `"{count} items"` with JS replace |
| `onclick="func({{ x\|tojson }})"` | `onclick='func({{ x\|tojson }})'` (single quotes) |
| Gara N with date before gara N-1 | Ensure date/time is sequential by number (ADR-016) |
| `EventBus._handlers = {}` in tests | Preserve and restore handlers (breaks notifications/gamification) |
| Manual SMTP sending | Use `EmailService` for all emails |
| `max(rack_number) WHERE is_deleted=False` | Include ALL records for sequential IDs with UNIQUE constraints |
| `@transactional` on facade AND inner service | Only decorate the innermost method (nested causes rollback) |
| `match.gara.distance` in scoring/validation | Use `match.distance_config` or `match.effective_*` (ADR-027) |
| `RoundConfiguration` salvato solo in `localStorage` | API endpoint `POST /admin/gara/<id>/round-config/<n>` (ADR-027) |
| Nuova route senza entry in `ENDPOINT_ROLES` | Sarà admin-only in prod (ADR-028) — aggiungila a `utils/feature_flags.py` se non è il comportamento voluto |
| Link a endpoint in template senza `feature_visible(...)` | In prod il link compare ma porta a 404 (ADR-028) — avvolgi con `{% if feature_visible('endpoint.name') %}` |
| `match.status in ["completed", "validated"]` (letterale raw) | `MatchStatus.is_finished(match.status)` / `is_active(...)` (typo-safe) |
| `raise ValueError(...)` per not-found / conflitto / permesso | Solleva la sottoclasse da `models.exceptions` (`NotFoundError`/`ConflictError`/`PermissionDeniedError`) → route mappano a 404/409/403 |
| Parsing form duplicato tra create / wizard / edit | Unica fonte `GaraFormParser` / `CampionatoFormParser` (vedi `routes/CLAUDE.md`) |
| `user.role == "director"` (o `"admin"`/`"player"`/`"guest"` letterali) | `UserRole.DIRECTOR.value` ecc. da `models/user/role_enum.py` — mai letterali per valori di dominio |
| Co-direttore con `role != director` | `GaraService`/`TournamentService.add_director` lo rifiutano (`ValidationError`): i co-direttori sono sempre `role=director` |

---

## Additional Documentation

- **[docs/reference/DATABASE_SCHEMA.md](docs/reference/DATABASE_SCHEMA.md)**: Auto-generated database schema (tables, columns, FKs) - regenerate with `python scripts/generate_schema_docs.py`
- **[docs/reference/AUTHENTICATION.md](docs/reference/AUTHENTICATION.md)**: Email verification, password reset, Flask-Mail setup
- **[docs/reference/GAMIFICATION_V2.md](docs/reference/GAMIFICATION_V2.md)**: Frontend bridge, toast notifications, mascot system
- **[models/CLAUDE.md](models/CLAUDE.md)**: Complete model reference with all fields and methods
- **[routes/CLAUDE.md](routes/CLAUDE.md)**: Route handlers and API endpoints
- **[tests/CLAUDE.md](tests/CLAUDE.md)**: Testing strategy and test organization
- **[models/gamification/CLAUDE.md](models/gamification/CLAUDE.md)**: Gamification system (XP, achievements, streaks)
- **[docs/reference/SPECIFICHE.md](docs/reference/SPECIFICHE.md)**: Complete platform requirements (Italian)
- **[docs/usecases/gare.md](docs/usecases/gare.md)**: Detailed workflow documentation
- **[docs/reference/UI_CONVENTIONS.md](docs/reference/UI_CONVENTIONS.md)**: UI conventions (icons, colors, design decisions)
- **[docs/reference/NAMING_CONVENTIONS.md](docs/reference/NAMING_CONVENTIONS.md)**: Naming conventions (italian plurals, italian/english split, URL, test, DB columns)
- **[docs/adr/](docs/adr/)**: Architecture Decision Records (ADR)
- **[docs/adr/ADR-027-round-level-configuration-enforcement.md](docs/adr/ADR-027-round-level-configuration-enforcement.md)**: Override per turno persistiti server-side + uso obbligatorio di `Distance` VO nello scoring
- **[docs/adr/ADR-028-production-endpoint-allowlist.md](docs/adr/ADR-028-production-endpoint-allowlist.md)**: allowlist endpoint deny-by-default in produzione, matrice ruoli (anonimo/player/director) con admin bypass — vedi anche `docs/reference/PRODUCTION_INVENTORY.md`
- **[docs/reference/PRODUCTION_INVENTORY.md](docs/reference/PRODUCTION_INVENTORY.md)**: inventario completo route/UI/permessi/feature WIP, base per la matrice di ADR-028

---

## Debugging Tips

Dati che cambiano in memoria ma non finiscono su DB: quasi sempre il decoratore
`@transactional` non è applicato davvero (o è quello sbagliato, per import
circolare). Diagnosi passo-passo in **`models/transaction/CLAUDE.md`** e
casistica completa in `docs/adr/ADR-012-transactional-circular-import-fix.md`.

---

## Development Notes

- Codebase uses Italian comments in many places
- Application usually running - no need to restart for most changes
- All 8 tournament use cases fully implemented with comprehensive integration tests
- Gamification system is event-driven and decoupled from core domains

---
