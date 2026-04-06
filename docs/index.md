# Indice Documentazione Progetto

> Generato automaticamente il 2026-04-04 | Scansione esaustiva
> Entry point principale per AI-assisted development

## Panoramica Progetto

- **Tipo:** Monolite Flask con Domain-Driven Design
- **Linguaggio Principale:** Python 3.11
- **Architettura:** Service Layer + Strategy Pattern + Event-Driven
- **Entry Point:** `app.py` → `create_app()` (Flask Application Factory)
- **Database:** SQLite con SQLAlchemy ORM
- **Produzione:** https://www.torneibiliardo.it (PythonAnywhere)

### Quick Reference

- **Tech Stack:** Flask 2.3.3, SQLAlchemy, Jinja2 SSR, Flask-Babel, Flask-Login
- **Codice:** 116K LOC Python, 29K LOC HTML, ~50 modelli, ~50 servizi
- **Test:** pytest con 90+ file di test attivi
- **CI/CD:** GitHub Actions → PythonAnywhere

---

## Documentazione Generata (BMad DP)

- [Panoramica Progetto](./project-overview.md) — Riepilogo funzionalità, tech stack, numeri
- [Architettura](./architecture.md) — Pattern architetturali, domini, diagrammi, sicurezza
- [Source Tree Annotato](./source-tree-analysis.md) — Albero directory con annotazioni e statistiche
- [Guida Sviluppo](./development-guide.md) — Setup, comandi, test, deployment, convenzioni
- [API Contracts](./api-contracts.md) — 275 endpoint, tutti i blueprint documentati
- [Data Models](./data-models.md) — 80+ modelli, 70+ tabelle, 15 domini

---

## Artefatti BMad

- [Project Context](../_bmad-output/project-context.md) — Contesto progetto ottimizzato per LLM (GPC)
- [Implementation Artifacts](../_bmad-output/implementation-artifacts/) — Spec e deferred work

---

## Documentazione Esistente

### Guide Principali

- [CLAUDE.md](../CLAUDE.md) — ★ Guida AI principale (convenzioni, pattern, errori comuni)
- [Specifiche Complete](./SPECIFICHE.md) — Requisiti piattaforma (italiano)
- [Schema Database](./DATABASE_SCHEMA.md) — Schema auto-generato (tabelle, colonne, FK)
- [Autenticazione](./AUTHENTICATION.md) — Email verification, password reset, Flask-Mail
- [Gamification V2](./GAMIFICATION_V2.md) — Frontend bridge, toast, mascot system
- [Sistema Classifiche](./CLASSIFICATION_SYSTEM.md) — Strategie classificazione multi-contesto
- [Convenzioni UI](./UI_CONVENTIONS.md) — Icone, colori, layout, design decisions
- [Internazionalizzazione](./INTERNATIONALIZATION.md) — Setup i18n, Flask-Babel

### Architecture Decision Records (ADR)

- [ADR-001](./adr/ADR-001-Amalfi-Strategy-Pattern-Unification.md) — Unificazione pattern strategia Amalfi
- [ADR-002](./adr/ADR-002-fix-anti-rematch-encounter-cleanup.md) — Fix anti-rematch encounter cleanup
- [ADR-003](./adr/ADR-003-user-privacy-system.md) — Sistema privacy utente (GDPR)
- [ADR-004](./adr/ADR-004-challenge-gara-decoupling.md) — Disaccoppiamento challenge/gara
- [ADR-005](./adr/ADR-005-distance-classification-trio-rules.md) — Regole distance, classificazione, trio
- [ADR-006](./adr/ADR-006-sse-event-bridge.md) — SSE event bridge
- [ADR-007](./adr/ADR-007-ssr-management-revision.md) — Revisione gestione SSR
- [ADR-012](./adr/ADR-012-transactional-circular-import-fix.md) — Fix circular import @transactional
- [ADR-013](./adr/ADR-013-classification-system-redesign.md) — Redesign sistema classifiche
- [ADR-014](./adr/ADR-014-mobile-first-card-layout.md) — Layout mobile-first a card
- [ADR-015](./adr/ADR-015-table-assignment-playing-status-fix.md) — Fix assegnazione tavoli
- [ADR-016](./adr/ADR-016-gara-sequential-date-validation.md) — Validazione date sequenziali gara
- [ADR-017](./adr/ADR-017-classification-model-missing-racks-won.md) — Campo racks_won mancante
- [ADR-018](./adr/ADR-018-jinja2-js-separation.md) — Separazione Jinja2/JS
- [ADR-019](./adr/ADR-019-gamification-abac-migration.md) — Migrazione ABAC gamification
- [ADR-020](./adr/ADR-020-gamification-system-v2.md) — Gamification system V2
- [ADR-021](./adr/ADR-021-sse-to-polling-migration.md) — Migrazione SSE → polling
- [ADR-023](./adr/ADR-023-match-status-and-polling-fixes.md) — Fix stato match e polling
- [ADR-024](./adr/ADR-024-wizard-campionato-e-sistema-playoff.md) — Wizard campionato e playoff

### Use Cases

- [Gare Workflow](./usecases/gare.md) — Flusso completo gestione gare
- [UC01](./usecases/UC01.md) — Use case 1
- [UC02](./usecases/UC02.md) — Use case 2
- [Convenzioni](./usecases/convenzioni.md) — Convenzioni use case

### CLAUDE.md per Dominio

- [models/CLAUDE.md](../models/CLAUDE.md) — Reference completo modelli e campi
- [routes/CLAUDE.md](../routes/CLAUDE.md) — Route handler e API endpoints
- [templates/CLAUDE.md](../templates/CLAUDE.md) — Pattern integrazione Jinja2/JS
- [tests/CLAUDE.md](../tests/CLAUDE.md) — Strategia testing e organizzazione
- [models/gamification/CLAUDE.md](../models/gamification/CLAUDE.md) — Sistema gamification
- [models/competition/CLAUDE.md](../models/competition/CLAUDE.md) — Dominio gare
- [models/match/CLAUDE.md](../models/match/CLAUDE.md) — Dominio match
- [models/matchmaking/CLAUDE.md](../models/matchmaking/CLAUDE.md) — Strategie matchmaking
- [models/user/CLAUDE.md](../models/user/CLAUDE.md) — Dominio utente
- [models/classification/CLAUDE.md](../models/classification/CLAUDE.md) — Classifiche
- [models/notification/CLAUDE.md](../models/notification/CLAUDE.md) — Notifiche
- [models/events/CLAUDE.md](../models/events/CLAUDE.md) — Sistema eventi
- [models/challenge/CLAUDE.md](../models/challenge/CLAUDE.md) — Sfide
- [models/location/CLAUDE.md](../models/location/CLAUDE.md) — Location
- [models/rating/CLAUDE.md](../models/rating/CLAUDE.md) — Rating
- [models/campionato/CLAUDE.md](../models/campionato/CLAUDE.md) — Campionati
- [models/playoff/CLAUDE.md](../models/playoff/CLAUDE.md) — Playoff
- [models/individual_match/CLAUDE.md](../models/individual_match/CLAUDE.md) — Match individuali
- [models/transaction/CLAUDE.md](../models/transaction/CLAUDE.md) — Transazioni

### Altro

- [Audit/Refactoring Plan](./AUDIT_REFACTORING_PLAN.md)
- [Handoff: Classification System](./HANDOFF_CLASSIFICATION_SYSTEM.md)
- [Handoff: Technical Debt](./HANDOFF_TECHNICAL_DEBT_REFACTORING.md)
- [Match Result Flow](./MATCH_RESULT_FLOW.md)
- [Date Formatting](./LOCAL_DATE_FORMATTING.md)
- [Spec: Spareggio SSR](./specs/SPAREGGIO_SSR.md)
- [TODO Backlog](./TODO_BACKLOG.md)
- [TODO Playoff](./TODO_PLAYOFF_IMPLEMENTATION.md)

---

## Getting Started

```bash
# Setup rapido
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python app.py  # → http://localhost:5000 (admin/admin123)

# Test
pytest tests/new/unit/ -n auto && pytest tests/new/integration/ -n 4

# Type check (obbligatorio pre-commit)
pyright
```

Per dettagli completi vedi [Guida Sviluppo](./development-guide.md).
