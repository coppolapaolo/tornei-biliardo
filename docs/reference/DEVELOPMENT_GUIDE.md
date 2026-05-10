# Guida allo Sviluppo

> Generato automaticamente il 2026-04-04 | Scansione esaustiva

## Prerequisiti

| Requisito | Versione |
|-----------|----------|
| Python | 3.11+ (venv incluso) |
| pip | Ultima versione |
| Git | 2.x+ |
| SQLite | 3.x (incluso con Python) |

## Setup Ambiente Locale

```bash
# 1. Clona il repository
git clone <repo-url> tornei-biliardo
cd tornei-biliardo

# 2. Crea e attiva virtual environment
python3.11 -m venv venv
source venv/bin/activate  # macOS/Linux

# 3. Installa dipendenze
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Configura variabili d'ambiente
# Copia .envrc.example (se esiste) oppure crea .envrc:
# SECRET_KEY=<tua-chiave>
# FLASK_ENV=development
# (opzionale) MAIL_USERNAME, MAIL_PASSWORD per email
# (opzionale) GLITCHTIP_DSN per error tracking

# 5. Inizializza database
python app.py
# Il database SQLite viene creato automaticamente in instance/billiard_campionato.db
# L'utente admin viene creato automaticamente (admin/admin123 in dev)

# 6. Esegui migrazioni (se DB esistente)
python migrations/runner.py
python migrations/runner.py --status  # Verifica stato
```

## Comandi Sviluppo

### Server

```bash
# Avvia server di sviluppo
python app.py
# → http://localhost:5000

# Credenziali dev: admin / admin123
```

### Test

```bash
# Tutti i test
pytest tests/new/ -n 4

# Solo unit test (parallelismo auto)
pytest tests/new/unit/ -n auto

# Solo integration test (DEVE usare -n 4 per SQLite)
pytest tests/new/integration/ -n 4

# File singolo con output
pytest tests/new/unit/test_file.py -v -n auto

# Debug test singolo (no parallel, con print)
pytest tests/new/unit/test_file.py::test_name -v -s
```

> ⚠️ **IMPORTANTE**: Integration test DEVONO usare `-n 4` (non `-n auto`) per evitare deadlock SQLite.

### Type Checking

```bash
# OBBLIGATORIO prima di ogni commit
pyright
```

Pyright è configurato in `pyrightconfig.json`:
- `typeCheckingMode: "basic"`
- `pythonVersion: "3.9"` (compatibilità)
- `reportCallIssue: false` (workaround SQLAlchemy mixin)

### Code Quality

```bash
# Formattazione (line-length 88)
black .

# Linting
flake8

# Checklist completa pre-commit
black . && flake8 && pyright && pytest tests/new/unit/ -n auto && pytest tests/new/integration/ -n 4
```

### Internazionalizzazione

```bash
# Estrai nuove stringhe traducibili
pybabel extract -F babel.cfg -o messages.pot .

# Aggiorna cataloghi traduzioni
pybabel update -i messages.pot -d translations

# Compila traduzioni
pybabel compile -d translations
```

Lingue supportate: **Italiano** (it, principale), **Inglese** (en).

### Migrazioni Database

```bash
# Crea nuova migrazione
touch migrations/20260404_description.py

# Esegui migrazioni pending
python migrations/runner.py

# Mostra stato migrazioni
python migrations/runner.py --status

# Inizializza DB esistente (segna tutto come applicato)
python migrations/runner.py --mark-all-applied
```

Le migrazioni devono:
- Definire `migration_name` per il tracking
- Essere idempotenti (safe to run multiple times)
- Usare `op.execute()` per raw SQL su SQLite

### Script Utilità

| Script | Descrizione |
|--------|-------------|
| `scripts/auto_deploy.py` | Deploy automatico PythonAnywhere |
| `scripts/backup_db.py` | Backup database |
| `scripts/generate_schema_docs.py` | Genera `docs/DATABASE_SCHEMA.md` |
| `scripts/recalc_elo.py` | Ricalcolo rating ELO |
| `scripts/send_match_reminders.py` | Invio reminder match via email |
| `scripts/verify_classification_configs.py` | Verifica configurazioni classifiche |

---

## Stack Tecnologico

| Categoria | Tecnologia | Versione | Scopo |
|-----------|------------|----------|-------|
| **Framework** | Flask | 2.3.3 | Web framework |
| **ORM** | Flask-SQLAlchemy | 3.0.5 | Database ORM |
| **Database** | SQLite | 3.x | Storage (dev e prod) |
| **Auth** | Flask-Login | 0.6.3 | Sessioni utente |
| **CSRF** | Flask-WTF | ≥1.2 | Protezione CSRF |
| **Rate Limit** | Flask-Limiter | ≥3.5 | Rate limiting API |
| **i18n** | Flask-Babel | 4.0.0 | Internazionalizzazione |
| **Email** | Flask-Mail | 0.9.1 | Invio email SMTP |
| **HTTP** | Werkzeug | 2.3.7 | WSGI server |
| **Grafici** | networkx | 3.1 | Anti-rematch matching |
| **Crypto** | cryptography | ≥42 | Campi crittografati |
| **Immagini** | Pillow | 10.4.0 | Upload immagini |
| **Monitoring** | sentry-sdk | ≥1.40 | Error tracking (GlitchTip) |
| **Env** | python-dotenv | 1.2.1 | Variabili ambiente |
| **Testing** | pytest + pytest-xdist | latest | Test paralleli |
| **Type Check** | pyright | latest | Static type checking |
| **Formatting** | black | latest | Code formatting |
| **Linting** | flake8 | latest | Linting |
| **E2E** | playwright | latest | Test end-to-end |

---

## Deployment

### Architettura Produzione

```
GitHub (main) → GitHub Actions CI → PythonAnywhere
                    ↓
              1. Unit tests
              2. Pyright
              3. Check migrazioni
              4. Reload web app (se no migrazioni nuove)
```

**URL Produzione**: https://www.torneibiliardo.it

### CI/CD Pipeline (`.github/workflows/ci.yml`)

| Job | Trigger | Azioni |
|-----|---------|--------|
| `test-and-typecheck` | Push/PR su main | pytest + pyright |
| `check-migrations` | Push su main | Rileva nuovi file migrazione |
| `deploy` | Push su main (no migrazioni) | Reload web app PythonAnywhere |
| `skip-deploy-notification` | Push su main (con migrazioni) | Avvisa di deploy manuale |

### Deploy Manuale (con migrazioni)

```bash
# Su PythonAnywhere console
cd /home/paolocoppola/mysite
git pull origin main
pip install -r requirements.txt  # se nuove dipendenze
python migrations/runner.py
# Reload app dal dashboard PythonAnywhere
```

### Deploy Automatico (scheduled task)

```bash
# Configurazione su PythonAnywhere → Tasks
/home/paolocoppola/mysite/venv/bin/python /home/paolocoppola/mysite/scripts/auto_deploy.py
```

Esegue: git pull → pip install → migrazioni → reload app (una volta al giorno).

---

## Convenzioni Codice Importanti

Vedi `CLAUDE.md` alla root del progetto per la lista completa. Le più critiche:

1. **UTC sempre**: `utc_now()` da `models.base`, mai `datetime.now()`
2. **Race to N**: `gara.distance = 5` significa "primo a 5 rack vince"
3. **@transactional**: Tutte le service method che modificano DB
4. **Soft delete**: `user.anonymize()`, mai `db.session.delete(user)`
5. **Enum con .value**: `gara.status == GaraStatus.PLAYING.value`
6. **JS tojson**: `alert({{ _("testo")|tojson }})` nei template
7. **Test**: unit → `-n auto`, integration → `-n 4`

---

## Struttura Test

```
tests/
├── new/                    # ★ Test attivi
│   ├── conftest.py        # Fixture: app, db_session, client, factories
│   ├── unit/              # ~60 file — logica pura, mock DB
│   │   └── gamification/  # Sotto-suite gamification
│   ├── integration/       # ~30 file — DB reale in-memory
│   │   └── gamification/  # Sotto-suite gamification
│   ├── refactor/          # Test TDD per refactoring
│   │   ├── tdd/           # Red-green-refactor
│   │   └── characterization/ # Test di caratterizzazione
│   └── e2e/               # Test end-to-end completi
├── unit/                   # Test extra (gamification unlock)
└── legacy/                 # ⚠ Non mantenuti
```

### Principi Testing

- Isolamento: `db_session.get()`, non `refresh()`
- EventBus: preserva e ripristina handlers, mai `_handlers = {}`
- Factory fixture per creazione entità di test
- 8 use case gare completamente testati in integration
