# ADR-0026 — Bootstrap Admin da Configurazione & Invariante “Single Admin”

**Stato:** Accettato — 2025-08-15  
**Contesto:** La webapp deve essere pubblicata su PythonAnywhere; la password
dell’amministratore non può risiedere nel codice. È richiesto che esista
sempre **un solo** amministratore attivo.

## Decisione
1. **Parametri di configurazione** (ENV-first):
   - `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`
   - In `ProductionConfig` è obbligatoria la presenza di `ADMIN_PASSWORD`
     (`ADMIN_PASSWORD_REQUIRED=True`), altrimenti il bootstrap fallisce a startup.
   - In `TestingConfig` sono previsti default sicuri per non rompere i test.

2. **Bootstrap idempotente** (`utils.create_admin_if_not_exists`):
   - Legge le credenziali da `current_app.config`.
   - Crea l’admin solo se assente; non stampa mai la password.
   - In produzione senza variabili richieste → `RuntimeError` esplicito.

3. **Invariante “single admin”** (Service Layer):
   - In `UserService.create_user(...)`: se si tenta di creare un secondo admin attivo → `ValueError`.
   - In `UserService.delete_user(...)`: vietata l’eliminazione dell’ultimo admin attivo.

4. **Reset/seed demo** (`utils/reset_data.py`):
   - Allineato ai parametri `ADMIN_*`; default presenti solo per test/demo.

## Alternative considerate
- **Indice parziale unico su `role='admin'`**: portabile solo parzialmente tra DB;
  oggi la codebase usa SQLite → differenze semantiche. Rinvio a futura migrazione.
- **Segreti in file `.env` committato**: rifiutato (rischio sicurezza).
- **Hash pre-calcolato nel codice**: rifiutato (ancora un “segreto” nel repo).

## Impatto
- Nessun breaking cambio sui test esistenti (TestingConfig mantiene default).
- Deploy: impostare su PythonAnywhere le ENV `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`.

## Migrazioni future
- Valutare partial unique index quando si adotterà PostgreSQL.
- Rotazione credenziali admin controllata (nuovo admin → trasferimento → declassamento).
