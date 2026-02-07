# Architecture Decision Records (ADR)

Questa directory contiene le decisioni architetturali significative del progetto.

## Cos'e un ADR?

Un Architecture Decision Record (ADR) cattura una decisione architetturale importante insieme al suo contesto e alle conseguenze. E un documento che spiega **perche** abbiamo fatto una scelta, non solo **cosa** abbiamo scelto.

## Quando Creare un ADR

Crea un ADR quando:
- Scegli un pattern architetturale
- Introduci una nuova libreria/dipendenza
- Definisci una convenzione di codice significativa
- Prendi una decisione con trade-off importanti
- Modifichi un comportamento fondamentale del sistema

## Indice Decisioni

| # | Titolo | Stato | Data |
|---|--------|-------|------|
| ADR-001 | [Amalfi Strategy Pattern Unification](ADR-001-Amalfi-Strategy-Pattern-Unification.md) | Accepted | 2025-09 |
| ADR-002 | [Fix Anti-Rematch Encounter Cleanup](ADR-002-fix-anti-rematch-encounter-cleanup.md) | Accepted | 2025-12-28 |
| ADR-003 | [User Privacy System](ADR-003-user-privacy-system.md) | Accepted | 2025-12-28 |
| ADR-004 | [Challenge/Gara Decoupling](ADR-004-challenge-gara-decoupling.md) | Accepted | 2025-12-29 |
| ADR-005 | [Regole Distanza, Classifica e Trio](ADR-005-distance-classification-trio-rules.md) | Accepted | 2025-12 |
| ADR-006 | [SSE Event Bridge Architecture](ADR-006-sse-event-bridge.md) | Superseded | 2025-12 |
| ADR-007 | [Revisione Gestione SSR](ADR-007-ssr-management-revision.md) | Accepted | 2025-12 |
| ADR-012 | [Fix Circular Import in @transactional](ADR-012-transactional-circular-import-fix.md) | Accepted | 2025-12 |
| ADR-013 | [Redesign Sistema di Classificazione](ADR-013-classification-system-redesign.md) | Accepted | 2025-12 |
| ADR-014 | [Mobile-First Card Layout per Vista Gara](ADR-014-mobile-first-card-layout.md) | Accepted | 2025-12 |
| ADR-015 | [Table Assignment - PLAYING Status Fix](ADR-015-table-assignment-playing-status-fix.md) | Accepted | 2026-01 |
| ADR-016 | [Validazione Sequenziale Date Gare](ADR-016-gara-sequential-date-validation.md) | Accepted | 2026-01 |
| ADR-017 | [Campo Mancante racks_won nel Modello Classification](ADR-017-classification-model-missing-racks-won.md) | Accepted | 2026-01 |
| ADR-018 | [Separazione Jinja2 e JavaScript](ADR-018-jinja2-js-separation.md) | Accepted | 2026-01-25 |
| ADR-019 | [Gamification ABAC Migration](ADR-019-gamification-abac-migration.md) | Accepted | 2026-01 |
| ADR-020 | [Gamification System v2](ADR-020-gamification-system-v2.md) | Accepted | 2026-01 |
| ADR-021 | [SSE to Polling Migration](ADR-021-sse-to-polling-migration.md) | Accepted | 2026-01 |
| ADR-023 | [Match Status and Polling Fixes](ADR-023-match-status-and-polling-fixes.md) | Accepted | 2026-01 |
| ADR-024 | [Wizard Campionato e Sistema Playoff](ADR-024-wizard-campionato-e-sistema-playoff.md) | Accepted | 2026-01-07 |

## Come Creare un Nuovo ADR

1. Copia `TEMPLATE.md`
2. Rinomina in `ADR-NNN-titolo-kebab-case.md` (es. `ADR-004-use-transactional-decorator.md`)
3. Compila tutte le sezioni
4. Aggiorna questo README con il nuovo ADR

## Stati

| Stato | Significato |
|-------|-------------|
| **Proposed** | In discussione |
| **Accepted** | Approvato e in uso |
| **Deprecated** | Non piu raccomandato |
| **Superseded** | Sostituito (link al nuovo) |

## Riferimenti

- [ADR GitHub](https://adr.github.io/)
- [Michael Nygard - Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
