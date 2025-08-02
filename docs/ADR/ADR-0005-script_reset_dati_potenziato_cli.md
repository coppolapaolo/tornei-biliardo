# ADR-0005: Script Reset Dati Potenziato (CLI)

Data: 2025-08-01

## Stato
Accettato

## Contesto
Per lo sviluppo serviva un modo rapido per:
* ricreare lo schema su SQLite/PostgreSQL,
* popolare ruoli e utenti di esempio,
* garantire coerenza dei test end‑to‑end.

Il reset **via interfaccia web non è ancora programmato**; la Fase 1 richiedeva solo lo script CLI.

## Decisione
* Implementato `utils/reset_data.py` eseguibile con `python -m utils.reset_data` o tramite comando Flask `flask reset-data` (che reindirizza allo stesso modulo).
* Lo script:
  1. Elimina (drop) o svuota le tabelle,
  2. Ricrea lo schema con `metadata.create_all()`,
  3. Inserisce utenti **admin**, **director** (pending) e 3 **player**,
  4. Stampa in console le credenziali seed.
* Lo script **si rifiuta di partire se** `FLASK_ENV == "production"`.

## Conseguenze
+ Workflow di onboarding e test automatizzati semplificato.
+ Unica fonte di verità per la logica di semina DB.
− Nessuna UX via browser; verrà affrontata in fasi future.

## Alternative
*Endpoint HTTP protetto* – rinviato.
*Snapshot DB* – poco portabile, dipendente dal motore.
