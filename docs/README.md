# Documentazione `tornei-biliardo`

Entry point della documentazione del progetto. Per la guida operativa al codice (convenzioni, pattern, errori comuni) il riferimento principale resta [`CLAUDE.md`](../CLAUDE.md) alla radice del repo.

## Struttura

| Cartella | Contenuto |
|---|---|
| [`reference/`](./reference/) | Documentazione viva: specifiche, schema DB, convenzioni UI, autenticazione, gamification, classifiche, i18n, inventario produzione |
| [`adr/`](./adr/) | Architecture Decision Records — decisioni architetturali con contesto e conseguenze |
| [`api/`](./api/) | Documentazione auto-generata: contratti API, modelli dati, albero sorgenti |
| [`usecases/`](./usecases/) | Use case del prodotto in stile user journey |
| [`usecases/stagione-amalfi-playoff.md`](./usecases/stagione-amalfi-playoff.md) | I journey di una stagione completa: quattro gare Amalfi, spareggi, playoff — con i test e2e che li percorrono |
| [`_archive/`](./_archive/) | Documentazione storica congelata (handoff, piani, refactoring completati) |

A livello principale:

- [`wishlist.md`](./wishlist.md) — funzionalità che vorrei implementare (note libere)
- [`wishlist-playoff.md`](./wishlist-playoff.md) — backlog specifico per il sistema playoff

## Reference (documenti vivi)

| Documento | Scopo |
|---|---|
| [`reference/SPECIFICHE.md`](./reference/SPECIFICHE.md) | Requisiti completi della piattaforma (italiano) |
| [`reference/ARCHITECTURE.md`](./reference/ARCHITECTURE.md) | Pattern architetturali, domini, sicurezza |
| [`reference/DEVELOPMENT_GUIDE.md`](./reference/DEVELOPMENT_GUIDE.md) | Setup, comandi, test, deployment, convenzioni |
| [`reference/DATABASE_SCHEMA.md`](./reference/DATABASE_SCHEMA.md) | Schema DB auto-generato (rigenerare con `python scripts/generate_schema_docs.py`) |
| [`reference/AUTHENTICATION.md`](./reference/AUTHENTICATION.md) | Email verification, password reset, Flask-Mail |
| [`reference/GAMIFICATION_V2.md`](./reference/GAMIFICATION_V2.md) | Frontend bridge, toast, mascot |
| [`reference/CLASSIFICATION_SYSTEM.md`](./reference/CLASSIFICATION_SYSTEM.md) | Sistema di classifiche multi-contesto |
| [`reference/UI_CONVENTIONS.md`](./reference/UI_CONVENTIONS.md) | Icone, colori, layout, design decisions |
| [`reference/INTERNATIONALIZATION.md`](./reference/INTERNATIONALIZATION.md) | Setup i18n (Flask-Babel) |
| [`reference/LOCAL_DATE_FORMATTING.md`](./reference/LOCAL_DATE_FORMATTING.md) | Date in formato italiano + DST |
| [`reference/MATCH_RESULT_FLOW.md`](./reference/MATCH_RESULT_FLOW.md) | Flusso inserimento risultati e validazione match |
| [`reference/PRODUCTION_INVENTORY.md`](./reference/PRODUCTION_INVENTORY.md) | Inventario route/UI/permessi/feature WIP — base per ADR-028 |

## Architecture Decision Records

Vedi [`adr/README.md`](./adr/README.md) per l'indice completo.

ADR più recenti (ultimi 6 mesi):

- [ADR-028](./adr/ADR-028-production-endpoint-allowlist.md) — Production endpoint allowlist (deny-by-default)
- [ADR-027](./adr/ADR-027-round-level-configuration-enforcement.md) — Override per turno persistiti server-side
- [ADR-026](./adr/ADR-026-reset-match-preserves-pair-semantics.md) — Reset match preserves pair semantics
- [ADR-025](./adr/ADR-025-savepoint-integrity-error-translation.md) — Savepoint + flush per `IntegrityError` → `ValueError`
- [ADR-024](./adr/ADR-024-wizard-campionato-e-sistema-playoff.md) — Wizard campionato e sistema playoff

## CLAUDE.md per dominio

Convenzioni e dettagli specifici per ogni area del codice:

- [`models/CLAUDE.md`](../models/CLAUDE.md) — modelli SQLAlchemy
- [`routes/CLAUDE.md`](../routes/CLAUDE.md) — route e API
- [`templates/CLAUDE.md`](../templates/CLAUDE.md) — Jinja2 / JS
- [`tests/CLAUDE.md`](../tests/CLAUDE.md) — strategia testing
- Sotto-domini: `models/{gamification,competition,match,matchmaking,user,classification,notification,events,challenge,location,rating,campionato,playoff,individual_match,transaction}/CLAUDE.md`

## Use cases

- [`usecases/gare.md`](./usecases/gare.md) — workflow completo gestione gare
- [`usecases/UC01.md`](./usecases/UC01.md), [`UC02.md`](./usecases/UC02.md) — scenari specifici
- [`usecases/convenzioni.md`](./usecases/convenzioni.md) — notazione "_(variante: …)_"

## Archivio

[`_archive/`](./_archive/) contiene documentazione storica: handoff post-sessione, piani di refactoring completati, audit chiusi, BMad snapshot precedenti. **Non è documentazione viva**: è preservata per consultazione retrospettiva e perché git history da sola non spiega *perché* furono prese certe decisioni di processo.
