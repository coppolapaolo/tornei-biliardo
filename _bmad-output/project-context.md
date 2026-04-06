---
project_name: 'tornei-biliardo'
user_name: 'PaCo'
date: '2026-04-04'
sections_completed: ['technology_stack', 'language_rules', 'framework_rules', 'testing_rules', 'code_quality', 'workflow', 'critical_rules']
status: 'complete'
rule_count: 58
optimized_for_llm: true
---

# Contesto Progetto per Agenti AI

_Questo file contiene regole critiche e pattern che gli agenti AI devono seguire quando implementano codice in questo progetto. Focus su dettagli non ovvi che gli agenti potrebbero altrimenti ignorare._

---

## Stack Tecnologico & Versioni

### Tecnologie Core
- **Python 3.9** (target pyright)
- **Flask 2.3.3** — Application Factory pattern (`create_app()` in `app.py`)
- **SQLAlchemy** via Flask-SQLAlchemy 3.0.5
- **SQLite** — sia in sviluppo che in produzione (PythonAnywhere)

### Dipendenze Chiave
- Flask-Login 0.6.3 — autenticazione utente
- Flask-Babel 4.0.0 — internazionalizzazione (locale default: `it`)
- Flask-Mail 0.9.1 — invio email SMTP
- Flask-WTF >=1.2.0 — form e protezione CSRF
- Flask-Limiter >=3.5.0 — rate limiting
- networkx 3.1 — algoritmi di matching anti-rematch (maximum cardinality matching)
- Pillow 10.4.0 — elaborazione immagini
- Sentry/GlitchTip — error tracking
- cryptography >=42.0.0,<44.0.0

### Strumenti di Qualita
- **Pyright** — type checking (basic mode, Python 3.9 target). `reportCallIssue` disabilitato per problemi con mixin SQLAlchemy
- **Black** — formatter (line-length=88)
- **Flake8** — linter (max-line-length=88, ignora E203/W503)
- **pytest + pytest-xdist** — test paralleli (`-n auto` per unit, `-n 4` per integration)

---

## Regole Critiche di Implementazione

### Regole Specifiche Python

#### Gestione Datetime (CRITICO)
- Usare SEMPRE `utc_now()` da `models.base` — mai `datetime.now()` o `datetime.utcnow()` (deprecato in 3.12+)
- Nelle colonne DB: `default=utc_now` (riferimento callable, senza parentesi)

#### Confronto Enum
- Confrontare SEMPRE con `.value`: `gara.status == GaraStatus.PLAYING.value`
- Il DB salva stringhe, non oggetti enum

#### Transaction Management
- `@transactional` solo sul metodo piu interno — mai su facade che delegano a servizi gia decorati (silent rollback su SQLite)
- Importare SEMPRE da `models.transaction.manager`, MAI da `models.base` (rischio no-op per import circolare — ADR-012)
- Il codebase ha import legacy da `models.base` — non copiarli
- Mai chiamare `db.session.commit()` manualmente

#### Soft Delete (User)
- Mai `db.session.delete(user)` — usare `user.anonymize()`
- `User.query` filtra automaticamente `is_deleted=True`; per includere cancellati: `.with_deleted()`
- Per ID sequenziali con UNIQUE constraint: includere TUTTI i record (anche cancellati) nel calcolo

#### Value Objects
- Usare `Distance.from_gara(gara)` per logica business su distanza/score

#### Import e Struttura Codice
- Per eventi/handler usare lazy import dentro il metodo se necessario per evitare circular imports
- Property (`gara.directors`, `user.is_admin`) sono read-only — non modificabili come relazioni SQLAlchemy
- Filtrare iscrizioni attive: sempre `is_withdrawn=False, is_waitlist=False` — `gara.inscriptions` include tutte

#### Modelli e Schema
- Base class: `BaseModel` per entita business, `db.Model + mixin` per casi specifici — guardare modelli esistenti nello stesso dominio
- `__tablename__` sempre esplicito su ogni modello
- Ogni modifica schema richiede migrazione in `migrations/YYYYMMDD_desc.py` — idempotente, `op.execute()` per SQLite
- FK SQLite: funzionano solo con PRAGMA attivo (gestito in `models/base.py`) — non bypassare il setup standard

#### Testing Python
- Nei test: `db.session.get(Model, id)`, mai `db.session.refresh(obj)`
- EventBus: MAI `EventBus._handlers = {}` — salvare e ripristinare gli handler originali
- Unit test: `-n auto`; Integration: `-n 4` (concorrenza SQLite)
- Usare `uuid.uuid4().hex[:8]` per identificatori unici nei test (evita collisioni con `-n`)
- Il conftest richiede `expire_on_commit = False` per evitare DetachedInstanceError
- Usare `app.test_request_context()` per test che coinvolgono traduzioni Flask-Babel

### Regole Specifiche Flask

#### Architettura Route
- Route → Service → Model: mai logica business nelle route, mai `db.session` nelle route
- Passare `current_user.id` (intero) ai servizi, mai l'oggetto `current_user` proxy

#### Template Jinja2 / JavaScript (CRITICO)
- SEMPRE `|tojson` per stringhe tradotte in JS — l'italiano ha apostrofi che rompono le stringhe
- Attributi `onclick`: usare single quotes per l'attributo HTML (`onclick='func({{ x|tojson }})'`)
- MAI usare placeholder `%(name)s` in stringhe `_()` interpolate da JS — Flask-Babel lancia `KeyError`
- `|datetime_local` per TUTTE le date visibili all'utente — converte UTC → ora italiana

#### Feedback Utente
- `flash()` per messaggi standard, `flash_gamification_event()` per toast XP/level-up/achievements
- Mai esporre `str(e)` in `flash()` in produzione — usare messaggi generici + `logger.exception()`

#### Registrazione Handler Eventi
- Handler eventi si registrano via import in `app.py` con `# noqa: F401`
- Se crei un nuovo handler, DEVI importarlo in `app.py` altrimenti non si registra mai

#### Flask-Babel i18n
- Locale default: `it` (italiano)
- Comandi: `pybabel extract`, `pybabel update`, `pybabel compile`

#### Email
- Sempre tramite `EmailService` da `models/shared/email_service.py` — mai SMTP diretto

#### Test Flask
- `client.get()/post()` NON segue redirect di default — usare `follow_redirects=True` se serve
- `app.test_request_context()` necessario per `url_for()` e traduzioni `_()` nei test
- `WTF_CSRF_ENABLED=False` gia configurato nel conftest

### Regole di Testing

#### Fixture
- Nelle fixture: `db_session.commit()` esplicito dopo add/add_all (NO @transactional nei test)
- ID SQLite assegnati SOLO dopo commit — mai accedere a `.id` prima del commit
- Username/email sempre con uuid: `f"user_{uuid.uuid4().hex[:8]}@test.com"` (evita UNIQUE violation con -n)

#### Struttura Test
- Integration: usare classi con `@pytest.mark.integration` + fixture nel metodo
- Unit: funzioni standalone OK
- Copiare pattern dal test esistente piu simile nella stessa directory
- Mai importare o copiare pattern da `tests/legacy/`

#### Pattern di Scoring nei Test
- Rack scoring interleaved per match race-to-N (alternare vincitore per realismo)
- Fixture isolamento totale: drop_all/create_all per ogni test, mai assumere dati pre-esistenti

### Qualita Codice & Stile

- `black . && flake8 && pyright` obbligatorio prima di ogni commit — 0 errori pyright
- Type hints su tutte le funzioni nuove
- Black line-length=88, Flake8 ignora E203/W503
- Naming: PascalCase per classi/modelli, snake_case per funzioni/variabili/file
- Tabelle DB: snake_case singolare (`match`, `campionato`, `inscription`)
- Codebase usa commenti in italiano in molti punti — mantenere coerenza

### Workflow di Sviluppo

#### CI/CD
- CI (GitHub Actions) esegue SOLO unit test + pyright — integration test da eseguire localmente
- Se push contiene file in `migrations/*.py`, deploy automatico SALTATO — step manuali richiesti
- CI usa Python 3.11, ma il codice deve essere compatibile Python 3.9 (no walrus `:=`, no `match/case`, no `dict | dict`)
- `PYTHONPATH=.` obbligatorio per eseguire pytest

#### Checklist Pre-Commit
1. `black . && flake8`
2. `pyright` (0 errori)
3. `pytest tests/new/unit/ -n auto`
4. `pytest tests/new/integration/ -n 4`
5. Se migrazione presente: nota che deploy sara manuale

### Regole Critiche Don't-Miss

#### Terminologia e Semantica
- "Race to N": `distance = N` = primo a vincere N rack. Max rack = (2*N)-1. NON e "best of N"
- Multi-set: settare SEMPRE `is_multi_set=True` E `match_distance` — dimenticare uno dei due corrompe gli score

#### Matchmaking
- Odd players: usare `decide_trio_or_bye()` da policies — mai hardcodare bye o trio
- Strategie: creare tramite `StrategyFactory`, mai istanziare la classe direttamente
- Anti-rematch: usa `networkx.max_weight_matching()` — mai reimplementare algoritmi di grafi

#### Dominio Gara
- Gara standalone vs campionato: verificare SEMPRE `gara.campionato_id` o `gara.is_standalone` prima di accedere a `gara.campionato.*`
- Date sequenziali (ADR-016): gare in campionato devono avere date cronologiche per `number`
- Challenge-bye (Amalfi): le challenge aggiornano il bye match — non rompere questo flusso

#### Accesso e Sicurezza
- Guest access: alcune pagine DEVONO essere pubbliche — non aggiungere `@login_required` ovunque
- Gamification disaccoppiata: opera tramite EventBus — mai chiamare servizi gamification direttamente da route/servizi di dominio

---

## Linee Guida d'Uso

**Per Agenti AI:**
- Leggere questo file PRIMA di implementare qualsiasi codice
- Seguire TUTTE le regole esattamente come documentate
- In caso di dubbio, preferire l'opzione piu restrittiva
- Consultare i file CLAUDE.md di dominio per dettagli specifici (`models/CLAUDE.md`, `routes/CLAUDE.md`, `tests/CLAUDE.md`)

**Per Umani:**
- Mantenere questo file snello e focalizzato sui bisogni degli agenti
- Aggiornare quando lo stack tecnologico cambia
- Rivedere trimestralmente per rimuovere regole obsolete
- Rimuovere regole che diventano ovvie nel tempo

Ultimo aggiornamento: 2026-04-04
