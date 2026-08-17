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
# poi Reload dal tab Web
```

**GitHub Actions** (`.github/workflows/ci.yml`) — 4 job:

| Job | Quando gira | Cosa fa |
|-----|-------------|---------|
| `test-and-typecheck` | ogni push **e** ogni PR | unit test + pyright. È l'unico status check che blocca il merge |
| `check-migrations` | solo push su `main` | `git diff --diff-filter=A HEAD~1 HEAD -- 'migrations/*.py'`: c'è una migration **nuova**? |
| `deploy` | solo push su `main`, **e solo se NON ci sono migration nuove** | **reload** della web app via API PythonAnywhere |
| `skip-deploy-notification` | solo push su `main`, **se ci sono migration nuove** | salta il deploy e stampa la procedura manuale |

> ⚠️ **Il merge su `main` NON deploya il codice.** Questo è l'errore che si continua a
> fare leggendo di fretta: il job `deploy` esegue **solo un reload** della web app, non un
> `git pull` (commento esplicito nel workflow: *«PythonAnywhere console API requires
> browser session, doesn't work from CI»*). Il codice nuovo arriva su PythonAnywhere solo
> quando gira lo scheduled task giornaliero `scripts/auto_deploy.py`, che fa `git pull` +
> `pip install` + migrations + reload. Fra il merge e il codice in produzione può quindi
> passare fino a **un giorno**.
>
> E se la PR **aggiunge una migration**, non parte nemmeno il reload: `check-migrations`
> lo rileva e la CI passa a `skip-deploy-notification`, che stampa la procedura manuale.
>
> **Quella procedura è un fallback, non un compito da assegnare a chi fa il merge.**
> Le migration pendenti le applica da solo `scripts/auto_deploy.py` al giro successivo,
> disabilitando e riabilitando la web app via API. Quindi dopo un merge **non c'è nulla
> da ricordare all'utente**: niente promemoria sul deploy, niente istruzioni su Disabled
> /Enabled, a meno che non sia lui a chiedere di andare in produzione subito.
>
> Sulle **PR** girano solo `test-and-typecheck` (verde/rosso); gli altri tre risultano
> `skipped` perché condizionati a `github.event_name == 'push'`. Vederli skipped su una PR
> è normale e **non** va segnalato come problema, né richiesto come status check
> (resterebbero pending all'infinito).

**⚠️ Branch protection su `main` (dal 2026-06)**: `main` è protetto e
`enforce_admins=true` — **niente push diretti su `main`, neanche da admin**.
Ogni modifica passa da una PR e il merge è bloccato finché lo status check
`test-and-typecheck` (unit test + pyright) non è verde. Workflow obbligatorio:

```bash
git checkout -b claude/descrizione   # branch di lavoro
# ... commit ...
git push -u origin claude/descrizione
gh pr create                          # apri la PR
# attendi che la CI sia verde, poi merge (il codice va in produzione dopo, vedi sopra)
```

Un `git push origin main` diretto viene rifiutato (`protected branch hook
declined`). Al merge parte **solo il reload** della web app — e nemmeno quello
se la PR aggiunge migration: il codice lo porta `auto_deploy.py`, non la CI
(tabella e riquadro sopra). Il gate è solo `test-and-typecheck`:
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
`create_app("production")` fallirebbe subito su `SECRET_KEY`. Uno script che
avvia l'app chiama **`bootstrap_and_create_app()`** da `scripts/prod_env.py`:
legge le env dal WSGI (riusa `read_wsgi_env` di `auto_deploy`, parsing AST
senza eseguirlo), esce dicendo cosa manca e da dove dovrebbe arrivare, e **poi**
importa l'app. Un valore passato a mano sulla riga di comando resta
prioritario. Se lo script tocca i PII gli si passa
`required=PRODUCTION_REQUIRED + ("ENCRYPTION_KEY",)`, altrimenti la decifratura
degrada in silenzio sulla chiave di sviluppo (incidente 2026-06-25).
`auto_deploy.py` resta autonomo di proposito: è il punto d'ingresso del deploy
e non importa nulla dal progetto.

> ⚠️ **`from app import create_app` in cima a uno script è un guasto**, non
> uno stile. L'import esegue `config.py`, che legge `os.environ` — e a quel
> punto `bootstrap_or_exit()` non l'ha ancora popolato. Il valore congelato
> resta per sempre. È così che `daily_jobs.py` (giornaliero) e
> `send_match_reminders.py` (orario) sono morti a ogni esecuzione con
> `RuntimeError: SECRET_KEY env var must be set in production` — con nel log,
> la riga prima, la conferma di aver letto proprio `SECRET_KEY`: le due righe
> raccontano momenti diversi. `reconcile_achievements.py` aveva lo stesso
> difetto latente. Dal 2026-08-17 `config.py` rilegge l'ambiente in
> `Config.environment_settings()` (applicata da `create_app`) e il cipher PII
> si deriva al primo uso, quindi l'ordine non è più fatale; resta però
> l'unica regola facile da rispettare, ed è presidiata staticamente da
> `tests/new/unit/test_script_import_order.py`. Gli script di analisi che si
> lanciano a mano in sviluppo (`recalc_elo.py`, `diagnose_elo.py`,
> `set_gara_handicap.py`, `migrate_gamification_rules.py`,
> `verify_classification_configs.py`) **non** usano `prod_env` e restano fuori
> dalla regola: non caricano env di produzione, quindi per loro l'ordine non
> significa nulla. Se un domani dovessero girare in produzione, vanno prima
> agganciati a `bootstrap_and_create_app`.

> ⚠️ `scripts/send_match_reminders.py` è **registrato** e gira ogni ora
> (confermato dal log del 2026-08-17). Non è accorpabile a `daily_jobs.py`:
> quello è il runner dei lavori *giornalieri*. Lo script era nato
> presupponendo di girare ogni 15 minuti, ma gli scheduled task di
> PythonAnywhere non scendono sotto l'ora: finestra e cadenza sono ora
> entrambe orarie, così il promemoria arriva fra le 2 e le 3 ore prima del
> match.

**⚠️ SQLite su PythonAnywhere (incidenti 2026-06-10 e 2026-08-17)**: lo storage
è NFS con lock inaffidabili. Regola operativa: ogni script/comando console che
scrive sul DB di produzione va eseguito con la web app su **Disabled**
(riabilitare subito dopo).

> La causa vera delle due corruzioni (`database disk image is malformed`) era
> però un'altra, e la regola qui sopra da sola non l'avrebbe mai fermata:
> `PRAGMA journal_mode=WAL` in `models/base.py`. Il WAL coordina i processi con
> un file `-shm` in **memoria condivisa via mmap**, che su NFS non è coerente —
> quindi bastavano la web app e uno scheduled task, senza nessuno alla console.
> Rimosso il 2026-08-17 (**ADR-045**), con presidio in
> `tests/new/unit/test_sqlite_pragmas.py`. **Non rimetterlo**, nemmeno
> condizionato a `FLASK_ENV`: una env var assente in un task lo riattiverebbe
> in silenzio per tutti, ed è persistito dentro il file `.db`.
>
> Corollario per la diagnosi: un `malformed` che **sparisce con un reload** non
> è un file corrotto — è il WAL, e il file può essere intatto. Le due cose si
> distinguono solo con `PRAGMA integrity_check`, da rifare **dopo** il
> checkpoint (`PRAGMA journal_mode=DELETE`), perché è lì che un'eventuale
> incoerenza si materializza su disco.

**Variabili d'ambiente richieste in produzione** (nel WSGI file
`/var/www/www_torneibiliardo_it_wsgi.py`): `FLASK_ENV=production` e
`ENCRYPTION_KEY` (la chiave cifra i PII — rotazione con
`scripts/rotate_encryption_key.py`, procedura nel docstring). Il fail-fast
scatta al **primo uso** della cifratura — cioè al primo PII toccato, non
all'import: `_resolve_key_string` è invocata da `_initialize_cipher`, che dal
2026-08-17 parte da `EncryptionManager._ensure_cipher()` e non più dal
costruttore. Il singleton eager derivava il cipher all'import di
`utils.encryption`, cioè **prima** che gli scheduled task avessero caricato le
env dal WSGI: la chiave usata era quella di sviluppo (nel log "Using default
encryption key" *precede* la riga delle env lette) e ogni email/telefono si
decifrava a stringa vuota, senza errori. Gli script da console che toccano PII
vanno comunque lanciati con `ENCRYPTION_KEY='...' python scripts/...` (la
console non eredita le env del WSGI; `auto_deploy.py` se le legge da solo,
vedi sopra).

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

Sempre in `app.py`, `auto_enabling_integrations` deve restare **False** con le
integrazioni dichiarate a mano (`FlaskIntegration`, `SqlalchemyIntegration`):
di default `sentry_sdk.init` importa ~40 moduli di integrazione per scoprire
quali pacchetti ci sono, e su PythonAnywhere quel giro vede anche i pacchetti
di sistema. `pymongo` trascina un `pyOpenSSL` incompatibile con la
`cryptography` installata, quindi ogni script da console o scheduled task
moriva in `create_app` su `AttributeError: module 'lib' has no attribute
'X509_V_FLAG_NOTIFY_POLICY'` (la web app no: set di pacchetti diverso). Le due
integrazioni dichiarate sono le stesse che si attivavano prima — l'insieme
attivo non cambia.

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
- **Frontend**: Use `|datetime_local` filter to display UTC → **ora di chi legge**
  (`User.timezone`, dedotto dal browser; ripiego su ora italiana per chi non ce
  l'ha). Il fuso lo conosce **solo** `utils/local_time.py`: `resolve_timezone()`
  per il lettore corrente, `resolve_timezone_for_user_id()` per un destinatario
  preciso. Un `ZoneInfo("Europe/Rome")` scritto altrove è un bug (ADR-043).
- **Testo scritto per qualcun altro** (notifiche, promemoria, scheduled task):
  passa `tz=` esplicito. Senza, si formatta nel fuso di chi ha premuto il
  pulsante — o, fuori da una richiesta, in quello di nessuno.

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
- `tests/legacy/` non esiste più: era rimasta indietro fino a non importarsi
  nemmeno (referenziava `UtilityMixin`, rimosso a giugno 2026), quindi nessuno
  di quei test girava. Cancellata.
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
| `<form method="POST">` senza `csrf_token()` | Prima riga dentro il form: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`, altrimenti 400 «Sessione scaduta». **I test non lo vedono** (`WTF_CSRF_ENABLED = False`): presidio statico in `tests/new/integration/test_drill_exam_manual_findings.py` |
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
| "Il merge su `main` fa scattare il deploy" | **Falso**: il job `deploy` fa solo un *reload*, e se la PR aggiunge migration non parte neanche quello. Il codice lo porta lo scheduled task `auto_deploy.py` (fino a 24h dopo) |
| Link a endpoint in template senza `feature_visible(...)` | In prod il link compare ma porta a 404 (ADR-028) — avvolgi con `{% if feature_visible('endpoint.name') %}` |
| `match.status in ["completed", "validated"]` (letterale raw) | `MatchStatus.is_finished(match.status)` / `is_active(...)` (typo-safe) |
| Credere che `"validated"` sia la validazione del direttore | È il contrario: `CONFIRMED_BY_BOTH` (valore `"validated"`) = chiusa dai **giocatori** con doppia conferma; `CLOSED_UNILATERALLY` (valore `"completed"`) = chiusa dal direttore/forfait/bye. I nomi dei membri sono stati corretti il 2026-08-17, **i valori persistiti no** |
| `match.validated_by_admin` | Non esiste su `Match` (vive su `Rack` e `Set`). La validazione del direttore *è* lo stato; per chiudere una partita mai iniziata si passa `to_completed(..., closed_by_director=True)` |
| Rinominare un membro di un enum usato da una colonna `db.Enum(...)` | **Rompe i dati già scritti**: senza `values_callable` SQLAlchemy persiste il *nome* del membro, non il valore. I test non lo vedono (scrivono e rileggono lo stesso nome nello stesso processo). Elenco delle colonne a rischio e presidio in `tests/new/unit/test_enum_columns_store_values.py` — incidente 2026-08-17 |
| `raise ValueError(...)` per not-found / conflitto / permesso | Solleva la sottoclasse da `models.exceptions` (`NotFoundError`/`ConflictError`/`PermissionDeniedError`) → route mappano a 404/409/403 |
| Parsing form duplicato tra create / wizard / edit | Unica fonte `GaraFormParser` / `CampionatoFormParser` (vedi `routes/CLAUDE.md`) |
| `user.role == "director"` (o `"admin"`/`"player"`/`"guest"` letterali) | `UserRole.DIRECTOR.value` ecc. da `models/user/role_enum.py` — mai letterali per valori di dominio |
| Interfaccia scritta "a memoria" senza aprire il prototipo | Invoca la skill `ui-7c`: la schermata di riferimento e' in `docs/redesign-7c/Redesign Mobile.dc.html` |
| `Config.DEBUG_MODE` in una route | `current_app.config.get("DEBUG_MODE", False)` — la classe base legge la env var col default `true`, quindi in produzione il guard non scatta |
| Nuova impostazione da env scritta nel corpo di `Config` | Va in `Config.environment_settings()` — il corpo della classe si esegue all'import e congela il valore: per gli scheduled task, che caricano le env *dopo*, sarebbe sbagliato per sempre |
| `from app import create_app` in cima a uno script con `prod_env` | `prod_env.bootstrap_and_create_app()` — importa l'app **dopo** aver letto le env dal WSGI (presidio: `test_script_import_order.py`) |
| Migration che solleva su una condizione permanente dell'ambiente | Deve riuscire (no-op dichiarato) o rimediare: se solleva, il runner non la marca applicata e `auto_deploy` la ritenta ogni notte, disabilitando la web app per niente |
| Co-direttore con `role != director` | `GaraService`/`TournamentService.add_director` lo rifiutano (`ValidationError`): i co-direttori sono sempre `role=director` |
| `challenge.max_score` o `challenge.name` | Non esistono su `Challenge`. Il massimo è per-esame su `ExamChallenge.max_score`; il nome mostrato è `get_display_name()` (ADR-042) |
| `datetime.strptime`/`fromisoformat` su un `datetime-local` | `utils.local_time.parse_local_datetime` — l'input arriva nell'**ora di chi scrive**, il DB tiene naive-UTC: salvarlo grezzo sposta l'orario, in silenzio (ADR-043) |
| `ZoneInfo("Europe/Rome")` scritto in un filtro o in una route | `resolve_timezone()` da `utils.local_time` — il fuso è quello del lettore, e un solo modulo lo sa (ADR-043) |
| Orario formattato una volta per N destinatari | Se il testo contiene un'ora, si compone **per destinatario** col suo `tz`: due giocatori in due fusi leggono due frasi diverse |
| `request.form.get("next")` passato a `redirect()` | `utils.safe_redirect.safe_next_url` — altrimenti è un open redirect |
| Disciplina come stringa scritta a mano (`"palla_8"`, `"8_ball"`) | `Discipline.*.value` da `models/status_enum.py` — **unico** vocabolario; per dati storici/esterni `Discipline.normalize()` (torna `None` sull'ignoto). Il nome mostrato è `display_name`, tradotto. Presidiato da `test_discipline_single_vocabulary.py` |
| `gara.matchmaking_strategy == "random"`, `campionato_type == "amalfi"` | `MatchmakingStrategy.*.value` da `models/matchmaking/configuration.py`, iniettato nei template. Esiste un **secondo enum omonimo** in `models/competition/validators.py` (`elimination`/`double_ko`) che non sta mai in colonna: citarlo dà un confronto sempre falso, senza errori. Presidiato da `test_match_status_no_raw_literals.py`, che vede anche `campionato_type\|lower == '...'` |
| Funzione visibile all'utente cambiata senza toccare `/aiuto` | Invoca la skill `help-docs`: la guida non si rompe, **invecchia** — continua a descrivere un'app che non esiste più. Contenuti in `help_content/`, schermate rigenerate da `scripts/help_docs/` |
| TPA/errori calcolati fuori da `models/tpa/engine.py` | Le regole Accu-Stats stanno **solo** li'. Il resto persiste comandi e li rigioca (ADR-044) |
| Rack segnati a mano su un match con referto TPA aperto | Il punteggio **discende** dal referto: due segnapunti si contraddicono al primo tocco (ADR-044) |
| Schermata della guida ritoccata a mano in un editor | Le immagini si **generano** dall'app (`capture_screenshots.py`) sul dataset di `seed_demo.py`: una ritoccata sopravvive al cambio di interfaccia e diventa una bugia permanente |

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
- **[help_content/](help_content/)**: contenuti del mini-sito di aiuto per gli utenti (`/aiuto`) — YAML, non HTML. `it/pages/*.yaml` le pagine, `it/hints.yaml` i micro-aiuti **già pronti per la futura interfaccia adattiva** (fumetti "?" e presentazione alla prima visita), `screenshots.yaml` il manifest delle catture. Si aggiorna con la skill `help-docs`; le schermate si rigenerano con `scripts/help_docs/seed_demo.py` + `capture_screenshots.py`
- **[models/tpa/CLAUDE.md](models/tpa/CLAUDE.md)**: referto TPA (motore Accu-Stats, registro dei comandi, sblocco)
- **[docs/adr/](docs/adr/)**: Architecture Decision Records (ADR)
- **[docs/adr/ADR-027-round-level-configuration-enforcement.md](docs/adr/ADR-027-round-level-configuration-enforcement.md)**: Override per turno persistiti server-side + uso obbligatorio di `Distance` VO nello scoring
- **[docs/adr/ADR-028-production-endpoint-allowlist.md](docs/adr/ADR-028-production-endpoint-allowlist.md)**: allowlist endpoint deny-by-default in produzione, matrice ruoli (anonimo/player/director) con admin bypass — vedi anche `docs/reference/PRODUCTION_INVENTORY.md`
- **[docs/reference/PRODUCTION_INVENTORY.md](docs/reference/PRODUCTION_INVENTORY.md)**: inventario completo route/UI/permessi/feature WIP, base per la matrice di ADR-028
- **[docs/adr/ADR-038-bracket-persistence.md](docs/adr/ADR-038-bracket-persistence.md)**: il tabellone è persistito su `Match` (`bracket_type`/`round`/`slot`/`group`), seat derivato, dimensionamento sugli iscritti effettivi e riscrittura di `rounds_count` al sorteggio
- **[docs/adr/ADR-039-team-separation-in-the-draw.md](docs/adr/ADR-039-team-separation-in-the-draw.md)**: squadre a due livelli (testo libero sul profilo, elenco per competizione) e separazione dei compagni come obiettivo lessicografico, non come vincolo rigido
- **[docs/adr/ADR-040-position-classification-ties.md](docs/adr/ADR-040-position-classification-ties.md)**: classifica POSITION per bande a pari merito, con lo spareggio **deliberatamente** spento — divergenza voluta dalla convenzione di `gara_strategies.py`
- **[docs/adr/ADR-041-grantable-roles-and-delegation.md](docs/adr/ADR-041-grantable-roles-and-delegation.md)**: ruoli concedibili ortogonali a `user.role` (`RoleGrant`), delega a catena come proprietà **per-ruolo** (`self_propagating`), revoca riservata ad admin perché unico punto di contenimento
- **[docs/adr/ADR-042-certified-exam.md](docs/adr/ADR-042-certified-exam.md)**: l'esame è una sequenza di drill con esito **booleano**, certificato solo di persona; entità gemelle di `MatchProposal` e non astrazione condivisa; `max_score` per-esame su `ExamChallenge`
- **[docs/adr/ADR-043-reader-timezone.md](docs/adr/ADR-043-reader-timezone.md)**: gli orari sono nel fuso di **chi legge**, dedotto dal browser e **salvato** su `User.timezone` (senza colonna, promemoria ed email non lo saprebbero); nessun backfill, perché «non lo so» e «è Roma» sono cose diverse
- **[docs/adr/ADR-044-tpa-scoresheet.md](docs/adr/ADR-044-tpa-scoresheet.md)**: referto TPA sui match singoli — funzione da sbloccare, punteggio **derivato** dal referto, registro dei comandi come unica verita', motore verificato per differenza contro l'app JS di riferimento
- **[docs/adr/ADR-045-no-wal-on-network-storage.md](docs/adr/ADR-045-no-wal-on-network-storage.md)**: niente `journal_mode=WAL` — su NFS la memoria condivisa del WAL non e' coerente fra processi e corrompe il DB; il file `.db` ricorda il journal mode, quindi togliere la riga non basta
- **[docs/usecases/esami.md](docs/usecases/esami.md)**: i sette journey degli esami e del ruolo esaminatore

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
