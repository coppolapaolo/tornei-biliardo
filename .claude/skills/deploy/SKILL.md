---
name: deploy
description: Portare il codice in produzione su PythonAnywhere, e diagnosticare cosa non ha funzionato. Attiva quando si parla di deploy, scheduled task, variabili d'ambiente di produzione, GlitchTip, o quando uno script da console/task si comporta diversamente dalla web app.
---

# Deploy e operativita' in produzione

Il dettaglio operativo che serve **al momento del deploy** o di una diagnosi in
produzione. Le tre cose che servono anche fuori da qui — «il merge su `main` non
deploya», il divieto di push diretti su `main`, e il divieto di rimettere
`journal_mode=WAL` — restano in `CLAUDE.md`, perche' devono essere in contesto
sempre, non solo quando si deploya.

**URL di produzione**: https://www.torneibiliardo.it

```bash
# Deploy manuale
cd /home/paolocoppola/mysite
git pull origin main
# ATTENZIONE: migrations SOLO con web app Disabled (tab Web)!
python migrations/runner.py
# poi Reload dal tab Web
```

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

  > ⚠️ **Ogni scheduled task va configurato con `venv/bin/python`, mai con
  > `python` nudo** (incidente 2026-08-17). Su PythonAnywhere `python` è
  > l'interprete **di sistema**, e da lì `pip install` non ha i permessi per
  > scrivere: falliva, `install_dependencies` tornava `False` e lo script
  > stampava un WARNING e proseguiva fino al reload. Invisibile da febbraio ad
  > agosto perché in sei mesi non era stata aggiunta nessuna dipendenza — ogni
  > `pip install` era un no-op, e un no-op fallito non si distingue da uno
  > riuscito. Al primo pacchetto nuovo (PyYAML) `/aiuto` ha risposto **500 per
  > due giorni**, sopravvivendo a due deploy; verificato dopo: il pacchetto non
  > era né in `venv/` né in `~/.local`.
  >
  > Dal 2026-08-17 lo script risolve l'interprete da solo (`venv_python()`) e
  > **si ferma** se `pip install` fallisce, invece di ricaricare con le
  > dipendenze vecchie. Presidio: `tests/new/unit/test_deploy_usa_il_venv.py`.
  >
  > La regola vale per **tutti** i task, non solo per questo: uno script che
  > importa l'app col python di sistema si porta dietro i pacchetti di sistema
  > di PythonAnywhere. È da lì che veniva il «set di pacchetti diverso» citato
  > più sotto a proposito di `pyOpenSSL`/`pymongo`.
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

## GitHub Actions (`.github/workflows/ci.yml`) — 4 job

| Job | Quando gira | Cosa fa |
|-----|-------------|---------|
| `test-and-typecheck` | push su `main` **e** PR **verso `main`** | unit test + pyright. È l'unico status check che blocca il merge. Il workflow ha `on: push: branches: [main]` e `pull_request: branches: [main]`, quindi **una PR con base diversa da `main` non fa girare nessun check** e resta bloccata per sempre: le PR impilate vanno riportate su `main` prima del merge |
| `check-migrations` | solo push su `main` | `git diff --diff-filter=A HEAD~1 HEAD -- 'migrations/*.py'`: c'è una migration **nuova**? |
| `deploy` | solo push su `main`, **e solo se NON ci sono migration nuove** | **reload** della web app via API PythonAnywhere |
| `skip-deploy-notification` | solo push su `main`, **se ci sono migration nuove** | salta il deploy e stampa la procedura manuale |

Il job `deploy` non fa `git pull` per un motivo scritto nel workflow stesso:
*«PythonAnywhere console API requires browser session, doesn't work from CI»*.
Il codice lo porta `scripts/auto_deploy.py`. La procedura manuale stampata da
`skip-deploy-notification` è un **fallback**, non un compito da assegnare a chi
fa il merge: le migration pendenti le applica `auto_deploy.py` al giro
successivo, disabilitando e riabilitando la web app via API.

Sulle PR girano solo `test-and-typecheck`; gli altri tre risultano `skipped`
perché condizionati a `github.event_name == 'push'`. Non vanno **mai** richiesti
come status check: resterebbero pending all'infinito. Per un hotfix urgente con
CI rotta serve togliere temporaneamente la protezione
(`gh api -X DELETE repos/coppolapaolo/tornei-biliardo/branches/main/protection`,
poi riapplicarla).

## Migrations

```bash
python migrations/runner.py                     # Run pending migrations
python migrations/runner.py --status            # Show migration status
python migrations/runner.py --mark-all-applied  # Init existing DB
```

In produzione: **solo con web app Disabled** (tab Web), poi Reload.

## Script che toccano dati storici: dry-run per default

> ⚠️ **`recalc_elo.py` è un dry-run finché non gli si passa `--commit`.**
> Senza, rigioca tutta la storia, stampa cosa cambierebbe e fa rollback: sembra
> aver lavorato, e non ha scritto niente. Vale anche per
> `repair_match_ended_at.py` e `repair_round_classification_racks.py`
> (`--apply`): è la convenzione degli script che toccano dati storici, e va
> verificata sul singolo script invece che ricordata a memoria, perché il nome
> del flag non è lo stesso per tutti.

## Env di produzione negli script da console/task

Console e scheduled task sono processi separati e **non ereditano** le variabili
dal file WSGI, quindi `create_app("production")` fallirebbe subito su
`SECRET_KEY`. Uno script che avvia l'app chiama **`bootstrap_and_create_app()`**
da `scripts/prod_env.py`: legge le env dal WSGI (riusa `read_wsgi_env` di
`auto_deploy`, parsing AST senza eseguirlo), esce dicendo cosa manca e da dove
dovrebbe arrivare, e **poi** importa l'app. Un valore passato a mano sulla riga
di comando resta prioritario. Se lo script tocca i PII gli si passa
`required=PRODUCTION_REQUIRED + ("ENCRYPTION_KEY",)`, altrimenti la decifratura
degrada in silenzio sulla chiave di sviluppo (incidente 2026-06-25).
`auto_deploy.py` resta autonomo di proposito: è il punto d'ingresso del deploy e
non importa nulla dal progetto.

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
> lanciano a mano in sviluppo (`diagnose_elo.py`, `set_gara_handicap.py`,
> `migrate_gamification_rules.py`) **non** usano `prod_env` e restano fuori
> dalla regola: non caricano env di produzione, quindi per loro l'ordine non
> significa nulla. Se un domani dovessero girare in produzione, vanno prima
> agganciati a `bootstrap_and_create_app`. `recalc_elo.py` **è già stato
> agganciato** (era in questo elenco fino al 2026-08-21): gira in console di
> produzione, e chi si fida dell'elenco vecchio gli sconsiglia il comando che
> invece funziona.

> ⚠️ `scripts/send_match_reminders.py` è **registrato** e gira ogni ora
> (confermato dal log del 2026-08-17). Non è accorpabile a `daily_jobs.py`:
> quello è il runner dei lavori *giornalieri*. Lo script era nato
> presupponendo di girare ogni 15 minuti, ma gli scheduled task di
> PythonAnywhere non scendono sotto l'ora: finestra e cadenza sono ora
> entrambe orarie, così il promemoria arriva fra le 2 e le 3 ore prima del
> match.

## SQLite su NFS: diagnosticare un `malformed`

Il divieto di `journal_mode=WAL` sta in `CLAUDE.md` perché deve valere sempre
(ADR-045). Qui il corollario diagnostico, che serve solo davanti al guasto:

Un `database disk image is malformed` che **sparisce con un reload** non è un
file corrotto — è il WAL, e il file può essere intatto. Le due cose si
distinguono solo con `PRAGMA integrity_check`, da rifare **dopo** il checkpoint
(`PRAGMA journal_mode=DELETE`), perché è lì che un'eventuale incoerenza si
materializza su disco.

Il WAL coordina i processi con un file `-shm` in **memoria condivisa via mmap**,
che su NFS non è coerente: bastavano la web app e uno scheduled task, senza
nessuno alla console. Ecco perché la regola «script di scrittura solo con web
app Disabled», da sola, non avrebbe mai fermato i due incidenti del 2026-06-10 e
2026-08-17.
