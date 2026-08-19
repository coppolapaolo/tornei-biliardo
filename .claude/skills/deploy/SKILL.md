---
name: deploy
description: Portare il codice in produzione su PythonAnywhere, e diagnosticare cosa non ha funzionato. Attiva quando si parla di deploy, scheduled task, variabili d'ambiente di produzione, GlitchTip, o quando uno script da console/task si comporta diversamente dalla web app.
---

# Deploy e operativita' in produzione

Il dettaglio operativo che serve **al momento del deploy** o di una diagnosi in
produzione. Le due cose che servono anche fuori da qui — «il merge su `main` non
deploya» e il divieto di rimettere `journal_mode=WAL` — restano in `CLAUDE.md`,
perche' devono essere in contesto sempre, non solo quando si deploya.

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
